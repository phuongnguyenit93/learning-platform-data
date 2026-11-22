# Method Compilation and On-Stack Replacement (OSR) in the HotSpot JVM

## Objectives

A Java 17+ program does not necessarily execute bytecode using the same mechanism throughout its lifecycle. **HotSpot** can start with the **interpreter**, gather runtime behavior information, and then **JIT-compile** sufficiently "hot" parts of the code into machine code. For a method that is frequently called repeatedly, the JIT can generate code **starting from the method entry** so that subsequent calls enter native code immediately. However, a method that is **called only once while executing a very long loop** can still spend millions of iterations in the interpreter. **On-Stack Replacement (OSR)** solves that exact situation: transitioning **an active invocation** from the interpreter or a lower compiled tier to a compiled version with an **entry point inside the method**, typically at the start of the loop (*loop header/backedge target*).

After this lesson, you will be able to:

- Distinguish **normal method compilation** from **OSR compilation**, and understand why a method can have **multiple nmethods** or code at multiple compilation levels.
- Explain **method invocation counter**, **backedge counter**, **profiling**, **compile queue**, **C1**, **C2**, **tiered compilation**, and **nmethod** in the HotSpot context.
- Read the **`%`** symbol, **`@ bci`**, compilation level, and **made not entrant** in `-XX:+PrintCompilation` without treating the log as an invariant execution result.
- Understand state transfer between **interpreter frame / compiled frame**, **local variables**, operand stack, stack maps, and safepoints, along with the limits of simulating this in Java source.
- Distinguish OSR from **deoptimization**, **inlining**, **uncommon trap**, **OSR bci**, and **GC safepoint**.
- Write runnable Java 17+ code to study the difference between a long loop and a frequently called method.
- Know how to use `javap`, `PrintCompilation`, `LogCompilation`, `jcmd`, JFR, and options like `-Xint`, `-XX:TieredStopAtLevel`, without "forcing" OSR with an ungrounded fixed threshold.
- Evaluate warmup, code-cache pressure, deoptimization, and benchmark pitfalls using real data.

## 1. Interpreter, JIT, and nmethod

Java source is converted by `javac` into **class file bytecode**. When the JVM executes:
1. Class loading/linking/initialization processes the class according to rules.
2. The method starts executing in the **interpreter** or enters already available compiled code, depending on HotSpot state.
3. The runtime observes which methods or loops execute frequently, accumulating counters and profile data.
4. The **compilation policy** decides whether to submit a compilation request to the **compile queue**.
5. A compiler thread uses type information, call sites, branches, loop behavior, and appropriate runtime assumptions to generate machine code.
6. If the compiled code is installed successfully, the JVM can direct appropriate executions to it.

**`nmethod`** is an internal HotSpot concept for a block of compiled native code associated with a method and metadata such as entry points, scope/deoptimization information, and runtime dependencies. It is not a new Java source method.

Diagram:

~~~text
.java -> javac -> .class / bytecode
                         |
                         v
                    HotSpot JVM
                         |
            +------------+-------------+
            |                          |
       INTERPRETER                COMPILED CODE
       bytecode dispatch        C1/C2 nmethod(s)
            |                          ^
            +-- profiling/counters ----+
                         |
                  compile queue
                         |
                  compiler threads
~~~

**Distinction:** Bytecode in the .class file is not "overwritten" by assembly when the JIT operates. The JVM manages native compiled code separately, and still needs bytecode metadata for verification, stack traces, deoptimization, and other purposes.

## 2. What is normal method compilation?

Suppose:

~~~java
static int plusOne(int value) {
    return value + 1;
}
~~~

This is an **illustrative method snippet**, which must be placed inside a class to compile. With an outer loop calling `plusOne` repeatedly, HotSpot can see a high invocation count and compile code with an **entry at the beginning of the method**.

~~~text
Caller calls plusOne() many times:
  call #1    -> interpreter
  call #2    -> interpreter
  ...
  HotSpot identifies hot method
            |
            v
      compile plusOne
      standard entry BCI / method entry
            |
  call #K+1 -> compiled nmethod
  call #K+2 -> compiled nmethod
~~~

**This is an illustrative sequence**. The number K has no fixed value, and the JIT may inline the call, use a different tier, or be constrained by flags/code cache. There is no guarantee that a method "called exactly 10,000 times will be compiled".

### Method entry point

Normal compilation generates code that can be used when **starting a new invocation**. The caller jumps to the compiled entry according to runtime dispatch/inlining decisions. If an invocation has already entered the interpreter and remains running inside a loop for a long time, having only compiled method-entry code is **not enough** to automatically transition that invocation to native code without an appropriate mechanism.

### The JIT is not required to compile every method

Methods that are rarely called, too large, lack sufficient profile, have restrictions, or perform very little work may always run interpreted. Some methods are inlined into the caller, causing them not to appear as a separate compiled method as expected. Compilation can be delayed when compiler threads are busy or the code cache is under pressure.

## 3. The special problem of a very long-running loop

Consider:

~~~java
static long oneLongCall(int limit) {
    long sum = 0L;
    for (int i = 0; i < limit; i++) {
        sum += (i & 7);
    }
    return sum;
}
~~~

This is an illustrative snippet. The method may be called only **once**, yet `limit` can reach tens of millions or hundreds of millions of iterations. The invocation count is not high, but **loop backedges** (branches jumping back to the start of the loop) occur continuously.

If it only relied on a method being called repeatedly, HotSpot might not compile a method called only once in time. If compiled "normally", the new code at the method entry would only be used when called again from the beginning, **not helping most of the currently executing loop**.

**OSR allows transitioning the current invocation itself to compiled code at a BCI inside the method.** This is the core difference from normal compilation.

### Timeline example

~~~text
T0   Method starts in interpreter
T1   Loop runs 100,000 times; backedge counter increases
T2   JVM decides to submit OSR compilation request
T3   Compile thread generates OSR nmethod (may run concurrently)
T4   Method is still executing in interpreter
T5   When a suitable transition point is reached and OSR code is ready:
       interpreter frame/state
                |
                v
       OSR entry in compiled nmethod
       continues from current loop BCI
T6   Loop and method finish; caller receives return value
~~~

The T milestones are only a **logical description**. The JVM does not guarantee that the request is submitted after exactly 100,000 iterations, that compilation always finishes before the loop ends, or that OSR is always chosen.

## 4. BCI and why the output has `@`

**BCI (bytecode index)** is the byte offset position within a method's bytecode area. The instruction at that offset is part of **a method**, not a line number in Java source.

When HotSpot OSR-compiles a method, the compilation task has an **OSR entry BCI** specifying where compiled code can accept a **running activation**. In common loops, it typically corresponds to a point at the loop header or the backedge target location.

Illustrative example of `-XX:+PrintCompilation` output:

~~~text
    75   33 %     3       OsrDemo::longLoop @ 4 (37 bytes)
   111   55       4       OsrDemo::longLoop (37 bytes)
   145   33 %     3       OsrDemo::longLoop @ 4 (37 bytes)   made not entrant
~~~

**The millisecond numbers, compile IDs, levels, BCIs, and byte counts here are purely illustrative**, not exact logs for a specific program. In the typical HotSpot format:
- The first number is usually the **time since JVM startup** (ms), depending on format.
- The next number is the **compilation ID**.
- **`%`** marks an **OSR compilation**.
- Numbers like **3** or **4** can be the compilation level in the tiered policy.
- `OsrDemo::longLoop` is the class/method name.
- **`@ 4`** is the **OSR BCI**, not the iteration count.
- `(37 bytes)` refers to the length of the **method bytecode**, not bytes of machine code.
- **`made not entrant`** is the state of an nmethod that is no longer selected for new entries, usually due to another compiled version or invalidation.

Do not infer from a `%` line that OSR **was actually used** for every running invocation: this line mainly confirms that **a corresponding compilation request/compilation occurred**. The code may become ready after the loop has already finished before the transition point, or another tier may be chosen.

### OSR BCI is different from Java line

A Java `for` statement can generate multiple bytecodes: initializing the index, comparing the limit, conditional branching, loading locals, arithmetic operators, incrementing the index, `goto` back to the start. Therefore BCI=4 does not mean "line 4". Use `javap -c -p` to view bytecode offsets and branch instructions.

## 5. Backedge counter and compilation policy

A bytecode loop typically has a backward branch to a smaller offset. The JVM can use **backedge counts** and profile information to identify a "hot" loop even when the method invocation count is low.

Different signals:

| Signal | When it typically increases | When it is valuable |
| --- | --- | --- |
| **Invocation count** | Calling a method many times | Short, frequently called methods |
| **Backedge count** | Branching back to an earlier code region many times | One or a few calls with a very long loop |
| **Branch/profile data** | Runtime observes branch ratios, call receivers, types... | C1 profiling and data-driven optimization |
| **Hotness/rate heuristics** | JVM combines counts, rate, compile-queue load... | Choosing tier and compilation timing |

**Caution:** these are not two simple independent counters with fixed thresholds. HotSpot tiered policy varies by version, compiler queue, profile maturity, and number of active methods. Flags such as `CompileThreshold` or `OnStackReplacePercentage` have meanings that depend on tiered/non-tiered mode; using an old Java 8 threshold formula to predict Java 17+ is wrong.

### Compilation can run asynchronously

When the interpreter detects a hot backedge, it can submit a compile task and then **continue running the loop in the interpreter** while the compiler thread works. If the loop finishes before the OSR code is ready, the program does not transition to OSR on that run. There are also **blocking compilation** modes or other policy situations; do not assume all JIT compilation is always background and never blocks the application thread.

### Does OSR necessarily happen at every backedge?

No. The runtime must have an appropriate checkpoint/safepoint or checking mechanism to recognize that the code is ready and ensure a valid frame transition. It is not an arbitrary "change the CPU instruction address right in the middle of a Java expression". The JIT needs to transfer state at a place with enough metadata to restore semantics.

## 6. Tiered compilation: interpreter, C1, and C2

The standard HotSpot server JVM implements **tiered compilation** to balance warmup time and machine code efficiency. A commonly seen model of levels:

| Level | Form | Role |
| --- | --- | --- |
| **0** | Interpreter | Starts execution and/or collects profile according to policy |
| **1** | C1 compiled, optimized without adding as much profiling as later tiers | Methods with a suitable selected path |
| **2** | C1 compiled with limited profiling | Collects partial data to support the next tier |
| **3** | C1 compiled with fuller profiling | Common on the path toward the optimized tier |
| **4** | C2 compiled, heavily optimized based on profile | Optimizes steady-state throughput/latency when appropriate |

**This is the traditional HotSpot C1/C2 interpretation**, not a mandatory structure of the JVMS or every build/platform. Some JVMs have a JVMCI compiler, different tuning options, and different tier policies.

In practice:
- A method may run at level 0, then move to C1 level 3, and later C2 level 4.
- A very simple method may go to level 1.
- The JVM may skip levels, stop at C1, not compile, or recompile when assumptions change.
- A method can have both a **normal nmethod** and an **OSR nmethod**; both can be at different levels.
- Level numbers in PrintCompilation only reflect the compilation task/nmethod, not "every bytecode is immediately at that level" on every invocation.

### C1 and C2 are not two versions of Java source

C1/C2 are **VM-internal compilers**. The JVM's goal remains executing exact Java semantics. C2 can inline methods, eliminate allocations, hoist invariant computations, or vectorize loops when conditions are appropriate. Optimizations may have to be invalidated when runtime observations no longer hold.

### C1 OSR and C2 OSR can coexist

A very long loop can:
1. Start interpreted.
2. Be OSR-compiled in C1 to get native execution early.
3. Continue being observed and submit a C2 OSR compilation when the profile is sufficient.
4. Transition to higher-tier code along paths allowed by the VM.

Do not assume the transition is always directly from a C1 OSR frame to a C2 OSR frame. Deoptimization/re-entry/intermediate state may be required; details depend on the HotSpot version and compiler/runtime policy.

## 7. Comparing method-entry compilation and OSR

| Aspect | Normal compilation | OSR compilation |
| --- | --- | --- |
| **Goal** | Speed up **new calls** starting at method entry | Speed up the **current execution** already inside a loop |
| **Typical signal** | Method invocations/hotness | Loop backedges/hotness |
| **Entry point** | Standard method entry | A BCI inside the method (usually loop header) |
| **Compile task** | Standard nmethod | OSR nmethod with osr_bci |
| **PrintCompilation** | Usually no `%` and no `@ bci` | Has `%`, usually has `@ bci` |
| **Optimized activation** | Mainly future invocations | Potentially current activation |
| **State transfer** | Caller passes arguments to normal entry | Runtime transfers interpreter/compiled state of current activation |
| **Optimization degree** | Can use information at method entry | Has constraints because it must accept state at OSR entry |
| **Can there be other compiled versions?** | Yes, with tiering/recompilation | Yes, multiple osr_bcis or levels |
| **Guaranteed to happen?** | No | No |

**OSR is not a Java syntax feature.** The `for`/`while` source code is identical; OSR is an internal JVM decision and mechanism to optimize execution without changing program results.

## 8. How does running state need to be transferred?

An interpreted frame currently inside a loop has state that cannot be "discarded":
- **Local variables**: parameters, loop index, counters, object references, temporaries.
- **Operand stack** at the relevant bytecode state.
- **Java monitors/locks** if the method or block is synchronized, and the OSR entry must preserve lock state.
- **Exception handlers** and control flow information.
- **GC map/reference metadata** needed for the collector to know the locations of object references.
- Information related to stack traces, inlining/deoptimization if transitioning from compiled frames.

Example of a loop:

~~~java
static long countEven(int n) {
    long sum = 0L;
    int accepted = 0;
    for (int i = 0; i < n; i++) {
        if ((i & 1) == 0) {
            sum += (i % 10);
            accepted++;
        }
    }
    return sum + accepted;
}
~~~

This is an illustrative snippet. If transitioning to OSR in the middle of the loop, the compiled code needs to continue with the **current values** of `i`, `sum`, `accepted`, and `n`. It must not reset them to 0. Nor may it repeat side effects that already occurred before the transition point.

### Frame state diagram

~~~text
Interpreter activation (at loop backedge):
  locals: [n=8,000,000, i=3,450,123,
           sum=..., accepted=...]
  operand stack: state at OSR checkpoint
  monitor state, metadata, method/BCI

                |
                | OSR runtime state transfer
                v

Compiled OSR entry @ loop BCI:
  reconstruct/register-map relevant locals,
  operand values, references and monitor state
  -> continue from current loop iteration
  -> preserve Java semantics
~~~

Simulated numbers. Physical state may reside in an interpreter frame, compiled frame, register/spill slots, or buffers; HotSpot needs metadata to reconstruct the state accurately. **Do not claim that OSR always "copies the entire stack"** or keeps every local variable in RAM in an invariant layout.

### OSR can be rejected

Conditions that can prevent an OSR request from being fulfilled: method/bci unsuitable for compilation at the current level, compiler busy, code cache constraints, insufficient profile, JVM flags, and policy. A method with a large loop can still run completely in the interpreter.

## 9. Complete Java 17+ example: one long loop and many small calls

Create the file **`OsrVsMethodDemo.java`**:

~~~java
public class OsrVsMethodDemo {
    static volatile long observable;

    static long longLoop(int limit) {
        long sum = 0L;
        for (int i = 0; i < limit; i++) {
            sum += (i & 7);
        }
        return sum;
    }

    static int plusOne(int value) {
        return value + 1;
    }

    public static void main(String[] args) {
        long loopResult = longLoop(16_000_000);
        observable = loopResult;

        long callSum = 0L;
        for (int i = 0; i < 100_000; i++) {
            callSum += plusOne(i);
        }
        observable = callSum;

        System.out.println("loopSum=" + loopResult);
        System.out.println("callSum=" + callSum);
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac --release 17 OsrVsMethodDemo.java
java OsrVsMethodDemo
~~~

**Exact business stdout:**

~~~text
loopSum=56000000
callSum=5000050000
~~~

Mathematical explanation:
- The sequence `i & 7` repeats 0,1,…,7; the sum of each group of 8 is **28**. 16,000,000 / 8 = 2,000,000 groups, total = **56,000,000**.
- `plusOne(i)` returns 1,2,…,100,000; sum = `100000×100001/2 = 5,000,050,000`, which fits in `long`.
- `observable` is a volatile field that keeps the result observable, though it does not guarantee that every intermediate allocation/instruction must exist in machine code.

**Comparison idea:** `longLoop` is **one method invocation** with very many backedges, whereas `plusOne` has very many calls. However, the compiler can inline `plusOne` into `main`, making the compilation tasks differ from the simple model. The program does not promise "there will definitely be exactly one OSR compilation".

### Observing PrintCompilation

On HotSpot supporting the flags:

~~~bash
java -XX:+PrintCompilation OsrVsMethodDemo
~~~

**Warning:** console output will contain **non-fixed compilation event lines** before, between, or after the two business lines above; the JVM also compiles JDK library methods. Therefore, **do not state a fixed full-program stdout** for this command.

Look for lines containing:
- `OsrVsMethodDemo::longLoop` and the `%` symbol.
- `OsrVsMethodDemo::main` and possibly the `%` symbol because the call loop inside main is also long.
- `OsrVsMethodDemo::plusOne` if the compiler compiles it separately; if inlined, it will not necessarily appear as a normal compilation.
- `@ <number>` after the method to identify the OSR entry BCI.
- Level 3/4 to see the tiered compilation path in that run.

### Running in interpreted mode

~~~bash
java -Xint OsrVsMethodDemo
~~~

This command uses interpreter-only mode on HotSpot; the program still prints the two lines with the **same business values**. Execution time can differ greatly, but **no fixed speedup factor is promised**. Some VM/library components have special handling, yet for the Java code in this example `-Xint` serves as a control to avoid JIT optimization.

### Running C1-only to observe tier changes

~~~bash
java -XX:TieredStopAtLevel=1 -XX:+PrintCompilation OsrVsMethodDemo
~~~

`TieredStopAtLevel=1` limits compiled tiers on HotSpot versions that support it. Observe the compilation entries and compare with default tiering, but do not read this as "forcing level 1 OSR to definitely happen". Changing the tier can change warmup, compiler overhead, and even the type of compilation requests.

## 10. Second example: OSR must preserve locals, branches, and loop exit

Create the file **`OsrStateDemo.java`**:

~~~java
public class OsrStateDemo {
    static long countEven(int n) {
        long sum = 0L;
        int accepted = 0;

        for (int i = 0; i < n; i++) {
            if ((i & 1) == 0) {
                sum += i % 10;
                accepted++;
            }
        }
        return sum + accepted;
    }

    public static void main(String[] args) {
        System.out.println("result=" + countEven(8_000_000));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 OsrStateDemo.java
java OsrStateDemo
~~~

**Exact stdout:**

~~~text
result=20000000
~~~

Explanation:
- Among the 8 million numbers `0..7,999,999`, there are exactly 4 million even numbers, so `accepted=4,000,000`.
- For even `i`, `i % 10` repeats 0,2,4,6,8; sum is 20 for 5 elements and average is 4. Over 4 million elements, `sum=16,000,000`.
- Result = `sum+accepted=20,000,000`.

If the JVM decides to OSR in the middle of the loop, the values of `sum`, `accepted`, and `i` must continue accurately so the program always prints this result. If compiled code lost state or repeated a branch that already ran, the result would be wrong — which a correct JVM must not do.

### Using javap to inspect BCI

~~~bash
javap -c -p OsrStateDemo
~~~

In `countEven`, you will see instructions such as `iload`, `iand`, `irem`, `iinc`, and `if...`/`goto` branches with bytecode offsets. The `@ bci` position in PrintCompilation must be matched against the **actual bytecode offset** of the .class file, not against Java line numbers.

## 11. Describing OSR more accurately: a compile request does not mean a successful transition

The process can be divided into independent milestones:

~~~text
(A) Hot backedge observed
           |
(B) Compilation policy decides to request?
       /                  \
     NO                    YES
     |                      |
  interpret         Enqueue OSR compile task
                           |
                    Compiler thread processes
                           |
                    Code generated/installed?
                     /               \
                   NO                 YES
                   |                   |
          still interpret      OSR nmethod ready
                                       |
                                Is activation still
                                at suitable checkpoint?
                                  /           \
                                NO             YES
                                |               |
                             Do not          Runtime can
                             transition      perform OSR
                             this time       transition
~~~

Distinguish clearly:
- **OSR task requested**: the policy has requested compilation.
- **OSR compiled**: native code has been generated/installed successfully.
- **OSR activated**: the current execution has transitioned to the OSR entry.
- **Compiled at higher tier**: the code has been upgraded in quality/tier; the current activation is not necessarily using that version.

`-XX:+PrintCompilation` is mainly useful for **observing compilation events**, not as a replacement for a runtime profiler proving the activation path in fine-grained detail. For deep study, you can use JITWatch + HotSpot compilation logs or supported profiling/diagnostic tools.

## 12. Deoptimization: the reverse transition direction of OSR

The JIT can optimize based on **assumptions** from type/branch profiles. For example, the compiler sees that a call site usually only has a receiver of one class, and then inlines the corresponding method. If another receiver type later appears, a guard may fail.

**Deoptimization** transitions execution from compiled code back to a state compatible with the interpreter (or another appropriate execution path), restoring JVM frames/locals/operand values to continue exact Java semantics.

Comparison:

| Phenomenon | Transition direction | Why it occurs |
| --- | --- | --- |
| **OSR** | Interpreter / lower tier → compiled OSR entry | Hot loop, wanting to speed up the **current activation** |
| **Deoptimization** | Optimized compiled frame → deoptimized/interpreted state | Assumption no longer holds, uncommon trap, dependency invalidation, or other runtime reason |
| **Normal compilation** | Generates compiled code for new method entry | Hot method/hot calls |
| **Recompilation** | New compiled code tier/optimization | Profile matures, invalidation, or tiering |
| **Inlining** | Places callee body into caller compiled code | Reduces dispatch/enables optimization across method boundaries |

**Do not equate OSR with deoptimization.** Both mechanisms require metadata to interpret/transfer frame state, but their purpose and transition direction are different.

### Uncommon trap and loop exit

A JIT compiler may observe an extremely long loop whose exit condition has almost never occurred in the profile. It may optimize the "common" flow and use an **uncommon trap** for the rare branch. When the loop finally ends, the exit branch may trigger deoptimization. This is a HotSpot possibility, **not a rule that every OSR loop deopts on its final iteration**.

### Example of profile shift by receiver type

Create the file **`ProfileShiftDemo.java`**:

~~~java
public class ProfileShiftDemo {
    static int read(Number value) {
        return value.intValue();
    }

    public static void main(String[] args) {
        long total = 0L;

        for (int i = 0; i < 50_000; i++) {
            total += read(Integer.valueOf(1));
        }

        total += read(Double.valueOf(2.5));

        System.out.println("total=" + total);
    }
}
~~~

Run:

~~~bash
javac --release 17 ProfileShiftDemo.java
java ProfileShiftDemo
~~~

**Exact stdout:**

~~~text
total=50002
~~~

Most calls go through Integer, then once through Double. The JVM **may** optimize based on the receiver type profile and deopt when the call site encounters Double, but it is **not guaranteed** because the compiler might not compile, might already see a polymorphic profile, or might choose generic dispatch. The business result must be correct even if no deoptimization occurs.

## 13. Compilation logs: reading the `%` symbol and reliability

### The `PrintCompilation` flag

~~~bash
java -XX:+PrintCompilation OsrStateDemo
~~~

It prints compile events for **both the application and many library methods**, which can interleave with stdout. When looking for the `OsrStateDemo::countEven` line, an OSR compilation typically looks like:

~~~text
   120   67 %     3       OsrStateDemo::countEven @ 4 (49 bytes)
   160   88 %     4       OsrStateDemo::countEven @ 4 (49 bytes)
   166   67 %     3       OsrStateDemo::countEven @ 4 (49 bytes)   made not entrant
~~~

**This is an illustrative log, not an exactly predictable output**. Bytecode counts, BCIs, IDs, and order must be taken from an actual run. HotSpot output also has attributes like `s` (synchronized), `!` (exception handlers), `b` (blocking), `n` (native), or other states depending on the release; do not interpret symbols based solely on a single example without checking the JDK version.

### Meaning of `made not entrant` and `made zombie`

- **Made not entrant:** the compiled nmethod is no longer selected by the JVM for **new entries**, though active frames may continue using that code or require appropriate transition/cleanup.
- **Made zombie:** the nmethod is no longer active in a relevant state and can wait for code-cache storage reclamation via the CodeCache/sweeper mechanism.

**Do not equate "made not entrant" with a Java object being collected by GC.** This is the lifecycle of **compiled machine code** in the code cache, not the lifecycle of an application heap object.

### JIT compilation output is not deterministic from code alone

When code is compiled is influenced by:
- JDK build and HotSpot implementation;
- compile thresholds and profiling heuristics;
- CPU speed/core counts, compile queue contention;
- JVM startup mode, tiering flags, and code cache;
- loop trip count, type profiles, and inlining;
- interpreter performance, JIT warmup, and background compilation.

Therefore, the curriculum must separate:
1. **Business stdout** of the examples — can be predicted accurately.
2. **JVM diagnostic output** — cannot promise the same compile IDs, tier levels, or number of OSR tasks across all machines.

## 14. Detailed compilation log with `LogCompilation`

Some JIT studies require XML-format logs to analyze compilation tasks, inlining, traps, and OSR code. On JDK 17 HotSpot, this is supported:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-log.xml OsrStateDemo
~~~

The `LogCompilation`/`LogFile` options are **diagnostic**, and are not necessarily available or behave identically across JVM vendors. In XML logs, you may see attributes similar to:

~~~xml
<task compile_id='67' method='OsrStateDemo countEven (I)J'
      compile_kind='osr' osr_bci='4' level='3'>
</task>
~~~

This is **illustrative XML showing the metadata style**, not a complete schema fragment or mandatory output. Use the actual log file and appropriate JDK tools/JITWatch to analyze.

Useful keywords:
- `compile_kind='osr'` / `osr_bci`: identifies an OSR task.
- `compile_id` and `level`: shows the identity/tier of the compilation.
- `task_done`: shows the state in which the task completed.
- Inlining decisions/failed optimizations: finds why a section did not optimize as expected.
- Traps and invalidations: checks deoptimization/recompilation.

**Caution:** XML contents, tag details, and log availability are HotSpot-specific and subject to change; do not treat them as a Java SE public contract.

## 15. Experimenting with JIT modes in a controlled way

| Command/flag | Learning purpose | Limitation |
| --- | --- | --- |
| `java -Xint Demo` | Primarily runs Java code interpreted | Does not represent HotSpot performance in production tiered mode |
| `java -XX:+PrintCompilation Demo` | Lists JIT compilation events | Many library methods and non-fixed timing |
| `java -XX:TieredStopAtLevel=1 ...` | Limits JIT up to C1 level 1 on supported builds | Does not force OSR on a specific method |
| `java -XX:-TieredCompilation ...` | Compares behavior when tiered compilation is disabled | Changes compilation policy and thresholds significantly, not just "turning off C1" |
| `java -Xcomp ...` | Requests more aggressive compilation on execution | Changes startup, blocking, profile quality, and can reduce performance |
| `java -XX:CompileThresholdScaling=...` | Adjusts heuristic thresholds | Not a simple OSR switch; should not be used to generate benchmark numbers |
| `java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation ...` | Records detailed compilation logs | Diagnostic overhead and non-invariant XML format |
| `javap -c -p Demo` | Views bytecode and offsets | Does not display JIT machine code or prove OSR was activated |

### Why is `-Xcomp` not "running JIT like production but faster"?

`-Xcomp` encourages aggressive compilation instead of normal interpreter-warmup profiling; the JVM may compile **before having a good profile**, increasing startup/compile overhead and sometimes making the application slower. Do not use it as proof that "JIT is always better than the interpreter" or to measure production tier choices.

### C1-only is not the same as C2-only

Tiered compilation has costs and profile-collection strategies. When setting `TieredStopAtLevel=1`, the JVM may save compile CPU and improve startup for some workloads, but misses C2 optimizations. **Do not assume** every program is slower; you must compare startup time, steady-state throughput, and tail latency.

### Should you try to force OSR with a threshold?

Usually **no**. Thresholds vary by tiered policy and JVM version. For learning purposes, choose a sufficiently long loop, enable compilation logging, and **observe**. If deep study is needed, record all flags and the exact JDK build, and use compiler directives/JITWatch/JFR; do not build a tutorial around an unverified "magic number".

## 16. Method invocation counter and backedge counter are not public APIs

There is no standard Java SE API for:

~~~java
// Hypothetical example NOT a Java API:
int count = JVM.getBackedgeCounter(MyClass.class, "method");
~~~

The snippet above is **commented-out pseudo-code** and will not compile if uncommented because the API does not exist. HotSpot has internal counters/profiling metadata; their values, storage format, and lifetime depend on the VM build/tier.

**Do not use Reflection** to guess the location of backedge counters in a method/class. Similarly, `Thread.getStackTrace()` does not expose the compiled vs interpreted state of each frame under a general contract.

If you need to observe HotSpot internals:
- Appropriate JVM logging/profiling.
- JFR compilation events if supported by the recording/event set.
- `jcmd` diagnostics.
- JITWatch or research tooling on the exact JDK.
- OpenJDK HotSpot source for the corresponding JDK version.

Some diagnostic VM flags exist only in debug builds; do not use them as universal run instructions on production binaries.

## 17. OSR and safepoint: related but not synonymous

The JVM needs appropriate points to:
- check requests from the runtime;
- synchronize GC/safepoints;
- transition interpreter/compiled execution when new code is ready;
- deopt or resolve certain runtime conditions.

Backedges are often a natural place for certain checks. However:

- **OSR entry** is a state transition point into a compiled nmethod, identified by BCI.
- **GC safepoint** is a VM state/coordination mechanism that allows the runtime to perform operations needing knowledge of object references and thread states.
- **Deoptimization point** is where the VM has enough information to reconstruct compatible state when leaving optimized code.
- These concepts are related at the metadata/checkpoint level, but **an OSR transition does not equal a GC pause**.

A loop with no object allocations can still be "hot" enough to attract JIT attention. OSR is not triggered only by the garbage collector, and GC is not a prerequisite for compiling a method.

## 18. OSR in synchronized methods and exception handling

A running method may have:
- a `synchronized` method monitor;
- a `synchronized(lock)` block;
- `try/catch/finally`;
- local references needing accurate GC;
- object state mutated on each loop iteration.

OSR must preserve exact Java semantics regarding locks, exception flow, and locals.

Example (illustrative snippet):

~~~java
static synchronized long count(int n) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += i;
    }
    return total;
}
~~~

If HotSpot OSR-compiles the loop, monitor ownership **cannot vanish** during the transition. When the method finishes or throws an exception, Java synchronization semantics must still hold.

OSR is not "skipping the code before the loop". It continues from a point compatible with the **state created by the already-executed code**, and must preserve those side effects.

## 19. OSR and inlining of call sites

When the compiler compiles `caller()` and can inline `callee()`, HotSpot can generate **compiled code containing callee logic directly inside the caller**. Therefore:
- Logs for `callee()` will not necessarily have a separate normal nmethod.
- A method may reside inside a compiled caller frame, and stack traces still need to display accurate Java-level frames.
- Counters/hotness may be attached to the inlined method, not just the top-level owner.
- OSR policy may consider suitable loops/inlinees when selecting compile requests; details belong to the compiler policy.

**Important example:** `plusOne` in the program in section 9 is so small that it is very easy to inline. If you do not see `plusOne` in PrintCompilation, **do not conclude it was "not optimized"**. It may have been inlined and heavily optimized into the outer loop.

### Want to force a method not to inline?

You can use compiler directives or `-XX:CompileCommand=dontinline,...` on supported HotSpot for a specific study, but this **changes the profile and code shape**. Do not present flags forcing inline/no-inline as production performance conclusions; measure both baseline and experimental runs.

## 20. Warmup: why a very short benchmark easily misjudges the JIT

HotSpot has warmup time due to:
- class loading/verification/initialization;
- interpreter profiling;
- C1 compilation and OSR;
- C2 compilation/recompilation;
- dynamic linking, caches, and data structure initialization;
- JIT recompilation/deoptimization and code-cache management.

A single-shot microbenchmark:

~~~java
long before = System.nanoTime();
// Run a loop and print elapsed...
~~~

is an **illustrative snippet**, not yet a good benchmark. The first run may incur compilation overhead or a mid-way OSR transition, while a later run enters an optimized nmethod directly. Measuring once and concluding "the loop got OSR so it's 10x faster" is unreliable.

### JMH and proper measurement

**OpenJDK JMH** is a project designed for microbenchmarks with warmup iterations, measurement iterations, forks, controlled state, and blackholes. When evaluating:
1. Write a workload that reproduces the application logic.
2. Ensure results are consumed to avoid dead-code elimination.
3. Separate class loading/setup from the timed region when the goal is steady-state.
4. Use multiple forks/runs and compare distributions.
5. Record JDK build, flags, CPU quota, and compiler modes.
6. Measure both performance and compilation events if the question is about warmup/OSR.
7. For live services, cross-check real request latency and throughput, not just microbenchmarks.

**A very long loop in a single method** can leverage OSR, but benchmarks are also affected by branch prediction, vectorization, CPU caches, scheduling, and type profiles. Do not guess that OSR is the sole source of speedup.

## 21. Code cache and compiled code lifecycle

Native JIT output must be stored in the **code cache**. HotSpot may use a **segmented code cache**, dividing storage areas for non-method/profiled/non-profiled code depending on configuration.

When many methods and OSR variants are compiled:
- code cache memory increases;
- the compiler must maintain metadata and nmethods;
- the code sweeper may clean up code that is no longer active;
- states such as `made not entrant`, `made zombie` may appear;
- when the code cache is full or constrained, JIT compilation may be restricted/paused, changing performance.

**Do not confuse the code cache with the Java heap.** The code cache stores machine code and runtime metadata, not where `new Person()` allocates Java objects.

Observation commands on supported HotSpot (replace with actual PID):

~~~bash
jcmd PID Compiler.codecache
jcmd PID Compiler.codelist
jcmd PID Compiler.queue
~~~

These diagnostic commands have availability/output that vary by JDK; check with `jcmd PID help` on the exact runtime. Some commands may require attach permissions and impact the system; do not run arbitrarily on production without authorization.

### When the code cache runs out

A code cache warning can explain why compilation stopped, rather than meaning the OSR algorithm is broken. Check code cache usage, `ReservedCodeCacheSize`, and compiled-method churn before changing heap `-Xmx` — because **-Xmx controls the Java heap, not directly the code cache limit**.

## 22. Using JFR to observe compilation

**Java Flight Recorder (JFR)** has event types related to compilation/code cache/tiered execution depending on the JDK/event configuration. JFR can be used to analyze:
- compilation activity and compiler threads;
- compilation durations;
- code cache statistics;
- CPU profile during warmup;
- deoptimization/code-cache events when enabled/supported;
- external latency or throughput correlated with the warmup phase.

Example running a program under a recording:

~~~bash
java -XX:StartFlightRecording=filename=jit-study.jfr,dumponexit=true,settings=profile OsrVsMethodDemo
~~~

The binary output `jit-study.jfr` does not have fixed contents. Read it with JDK Mission Control or `jfr print` on an appropriate JDK. On a workload that is too short, the recording may not have enough events to interpret. JFR sampling does not prove every OSR activation occurred, especially when the event set does not record the specific transition.

To capture data from a running process:

~~~bash
jcmd PID JFR.start name=JitStudy settings=profile duration=60s filename=jit-study.jfr
jcmd PID JFR.check
~~~

`PID` is a placeholder for the process ID; replace with the real number. Diagnostic data may contain application information; protect the files.

## 23. Diagnostic workflow for "hot loop that isn't fast"

If a loop runs slowly even though you expected OSR/JIT to optimize it:

1. **Check the exact JVM**: `java -version`, vendor/HotSpot build, architecture, flags.
2. **Identify the mode**: are `-Xint`, `-XX:-TieredCompilation`, `TieredStopAtLevel`, or flags restricting compilation present?
3. **Check PrintCompilation**: is there a method/OSR compile task, at what level, is there `made not entrant`?
4. **Cross-reference javap**: which loop does `@ bci` correspond to?
5. **Check the compile queue**: are compiler threads busy, is the code cache nearly full, or was the method excluded from compilation?
6. **Profile the actual hot path**: was the method inlined into the caller? Are there virtual calls/megapolymorphic receivers, bounds checks, or memory stalls?
7. **Check deoptimization/traps**: did changing assumptions cause optimized code to be invalidated repeatedly?
8. **Check CPU/GC**: is the loop contending for CPU, blocked, limited by memory bandwidth, or experiencing GC pauses?
9. **Measure after warmup**: use JMH/service metrics; do not conclude from a single run.
10. **Optimize algorithm/data**: if the algorithm is O(n²) or cache locality is poor, JIT/OSR cannot replace algorithm design.

### Common signs and how to reason about them

| Symptom | What to check | What not to jump to concluding |
| --- | --- | --- |
| No `%` symbol seen | OSR task not printed/did not occur, JIT flags, threshold/policy, short loop, inlining | "The JVM does not support OSR" |
| `%` present but method still slow | Whether OSR code was activated, workload, memory/GC/CPU, optimizer | "OSR automatically makes it fast" |
| Multiple levels 3 and 4 | Tiered C1→C2 progression, recompile | "The loop runs multiple versions concurrently on the same thread" |
| `made not entrant` present | New tier/invalidation/nmethod lifecycle | "The application errored/GC collected the object" |
| Deoptimization present | Guard/profile change, uncommon traps | "The Java result is wrong" |
| `-Xint` is slower | Interpreter overhead and missing JIT optimizations | "OSR alone creates all the speedup" |
| Small method does not appear separately | Inlining, compile policy | "The method was not optimized" |
| Compilations drop as service runs long | Warmup completed or code cache pressure | "The JIT was turned off" |
| Some runs have no OSR | Timing/queue/loop finishes before compilation | "PrintCompilation is broken" |

## 24. Misconceptions to avoid

| Misconception | Reality |
| --- | --- |
| "Normal method compilation makes the currently running call automatically switch to the new code." | Standard entry code is mainly for new invocations; OSR handles the current activation in a loop. |
| "OSR is a compiler different from C1/C2." | OSR is a **compilation/entry type**; C1/C2 can generate OSR nmethods. |
| "OSR only needs to swap a pointer in a Java variable." | The VM must transfer frame state/locals/operand/monitors with exact semantics. |
| "OSR bci is the iteration number." | BCI is the bytecode offset within the method. |
| "The % sign in PrintCompilation is CPU percentage." | The `%` sign is the OSR compilation marker. |
| "Any loop of 10,000 iterations triggers OSR." | Policy/threshold/timing vary by JVM and workload. |
| "If a method has a normal nmethod, it cannot have an OSR nmethod." | It can have both variants. |
| "C1 OSR and C2 OSR are always used in a deterministic order." | Tier policy, queue, compilation latency, deopt, and profiling decide. |
| "OSR is a GC pause." | OSR relates to JIT execution transition, not the name of a GC event. |
| "OSR is deoptimization." | Different direction/purpose; OSR enters optimized code, deopt leaves optimized code when needed. |
| "`-Xcomp` reflects production throughput." | It alters compile timing/profile and can reduce performance. |
| "`-Xint` also has OSR native code." | Interpreter-only mode does not use JIT for Java methods in the normal way. |
| "`made zombie` log reports a dead Java object." | This is the nmethod/code-cache lifecycle. |
| "`javap` shows C2 assembly." | `javap -c` inspects bytecode; JIT machine code requires other tools/flags. |
| "Not seeing a compiled callee means the JIT skipped it." | The callee may have been inlined into the caller. |
| "Having an OSR task means OSR was definitely activated." | Compilation and transition are two separate moments/conditions. |
| "OSR always speeds up every loop." | Compilation/transition has overhead and the loop may finish early. |

## 25. Self-check questions

**1. Can a method called once but running 50 million iterations attract JIT attention?**

Yes. Backedge counts/profiling can trigger an **OSR compilation**, even when the invocation count is low.

**2. Why is normal compiled method entry not enough to speed up an already running call?**

Because the compiled entry serves the start of the method; the current invocation is already deep inside a loop. OSR provides an entry point at an appropriate BCI along with state transfer.

**3. What is the `%` symbol in PrintCompilation?**

An OSR compilation marker, not a CPU load percentage.

**4. What does `@ 8` in an OSR log line usually indicate?**

An **OSR BCI** in the method's bytecode, not Java line 8 or the 8th loop iteration.

**5. How do C1/C2 relate to OSR?**

C1/C2 are compilers; both can generate OSR variants at appropriate compilation levels.

**6. Why must the value of the `sum` variable be transferred into OSR code?**

So that the partial result already accumulated in the interpreter is not lost and the method continues from its current state.

**7. Is OSR a Java syntax feature?**

No. The `for` or `while` source does not change; OSR is managed by the VM.

**8. Will using `-Xint` show normal JIT method compilation?**

Not in typical interpreted-only Java execution; this flag is mainly used as an interpreter control.

**9. Why does a small frequently called method not appear as a separate compilation entry?**

It may have been inlined into the caller or not qualify for separate compilation.

**10. Does a compiled OSR task guarantee the current loop transitions to compiled code?**

No. The loop may have already finished, or the policy/transition may not select that OSR code.

**11. Why can an nmethod be `made not entrant`?**

When the code is no longer used for new entries, for example due to a new tier or dependency invalidation. This is not Java heap object GC.

**12. How do OSR and deoptimization differ?**

OSR aims to **enter compiled code** mid-activation; deoptimization restores execution state when having to **leave optimized code**.

**13. If a loop has a synchronized monitor, is OSR allowed to drop the lock?**

No. Monitor ownership and Java synchronization semantics must be preserved.

**14. Why use JMH instead of timing a for loop on its first run?**

Because warmup, OSR/JIT compilation latency, JIT dead-code elimination, caching, and scheduling make a single measurement unreliable.

**15. Which metrics should you look at when the compiler queue is overloaded?**

Compile events/queue, compiler CPU/time, tiering progression, code cache, and actual workload CPU/latency, along with the JVM flags state.

**16. Why can PrintCompilation timestamps/method IDs not be expected stdout?**

Because compilation is decided at runtime, affected by different JDK builds, thread scheduling, CPU, profiles, and flags.

## 26. Mind map

~~~text
                 JAVA BYTECODE METHOD
                          |
                      INTERPRETER
                          |
             +------------+-----------+
             |                        |
        Many method calls      One long-running loop
             |                        |
       invocation counters        backedge counters
             |                        |
             v                        v
     NORMAL COMPILATION         OSR COMPILATION
     method entry code          osr_bci inside method
             |                        |
       future invocations      current active invocation
             |                        |
             +-------------+----------+
                           |
                       TIERED JIT
               0 interpreter -> C1 -> C2
                           |
               nmethod(s) in CODE CACHE
                           |
             +-------------+--------------+
             |                            |
       OPTIMIZED EXECUTION           DEOPTIMIZATION
                                    (if assumptions fail)
             |                            |
             +----------------------------+
                           |
                 JAVA SEMANTICS UNCHANGED
                           |
                  DIAGNOSTICS / MEASUREMENT
           javap -c; PrintCompilation (% / @bci)
           LogCompilation; JFR; jcmd; JITWatch
                           |
                  JMH / service metrics
~~~

**Conclusion:** **Normal method compilation** speeds up new calls from the method entry; **OSR** allows a call already in the middle of a **hot loop** to enter compiled native code at an appropriate **BCI** while preserving exact locals/operand/monitor state. OSR is a **JIT execution transition** mechanism, not a separate compiler or a GC operation. Identify it via `%` and `@ bci` in HotSpot logs, and measure actual performance with warmup and diagnostics instead of promising fixed thresholds or speedups.

## Standard References

- [Oracle JDK 17 — The java Command: PrintCompilation, TieredCompilation, LogCompilation, CompileThresholdScaling, CompileCommand](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JVMS Java SE 17 — §2 Runtime Data Areas, JVM Frames and Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html).
- [JVMS Java SE 17 — §6 Java Virtual Machine Instruction Set, BCI/branches](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- [OpenJDK HotSpot — compilationPolicy.hpp, tiered compilation levels, backedge events](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp).
- [OpenJDK HotSpot — compileBroker.cpp, OSR compilation tasks and statistics](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compileBroker.cpp).
- [OpenJDK HotSpot — compiler_globals.hpp, OnStackReplacePercentage and diagnostics](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compiler_globals.hpp).
- [OpenJDK HotSpot — C2 parse1.cpp, OSR BCI and type flow](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/parse1.cpp).
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/).
- [Oracle JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [OpenJDK JITWatch project](https://github.com/AdoptOpenJDK/jitwatch).
