# What Problems Do Bytecode Interpretation and Just-In-Time (JIT) Compilation Solve?

## 1. The Problem the JVM Must Solve

`javac` typically compiles Java source into **JVM bytecode** in `.class` files, not native machine code hardcoded to the current CPU. At runtime, the JVM must execute those virtual machine instructions on a specific hardware platform.

There are two complementary ways of execution:

- **Interpretation:** a bytecode interpreter directly processes JVM instructions. It allows a method to start running without necessarily generating optimized native code for that method.
- **Just-In-Time (JIT) compilation:** the JVM identifies frequently executed methods or loops, and can then translate bytecode into **native machine code** optimized for the current runtime/CPU state.
- **Profiling and adaptive optimization:** the JVM observes code paths, call frequency, loop iterations, receiver types, and common behavior to focus compilation effort on hot regions.
- **Deoptimization:** if the assumptions used during optimization no longer hold, the runtime can fall back to a compatible execution mode and preserve Java semantics.

**The main goal is to balance startup time, warmup time, and long-term performance.** The interpreter has low initial compilation cost, but must process bytecode repeatedly. JIT consumes resources to compile, in return for native code that can run faster and be optimized across methods.

This is the typical model of **HotSpot**, not a mandatory rule requiring every JVM implementation to have C1/C2 compilers or the same JIT policy.

## 2. Looking at the Entire Execution Path

~~~text
Java source
  |
  v
javac
  |
  v
Class file: bytecode + constant pool + class metadata
  |
  v
JVM: loading -> verification/linking -> initialization when needed
  |
  v
Interpreter executes bytecode
  |        |
  |        +-- tracks call counts, loop backedges, type profiles
  |
  +-- cold method -> may continue being interpreted
  |
  +-- hot method/loop -> requests JIT
                          |
                          v
                     C1/C2 compiler
                          |
                          v
                     Native code in the code cache
                          |
                          v
                     CPU executes compiled code
                          |
                          +-- assumptions invalid?
                                 |
                                 v
                          guard/fallback/deoptimization
~~~

**Do not read the diagram as a forced sequence for every method.** A method might not be compiled; another method might go through multiple tiers; a long-running loop might transition to native code via OSR without returning. Flags `-Xint` and `-Xcomp` also change the execution strategy.

### Three Different Forms of Code

| Form | Example | Execution unit |
| --- | --- | --- |
| Java source | `return a + b;` | Source program, according to the Java Language Specification |
| JVM bytecode | `iload_0`, `iload_1`, `iadd`, `ireturn` | JVM instruction set |
| Native machine code | x86-64/AArch64 instructions | Physical CPU |

**`javac` is not synonymous with JIT.** `javac` usually runs before the application runs; JIT is a compiler operating inside the JVM while the application is running.

## 3. How Does the Interpreter Execute Bytecode?

Example Java method:

~~~java
static int add(int a, int b) {
    return a + b;
}
~~~

This is an **illustrative method snippet**, not a standalone Java file with `main`. Standard `javac` generates similar bytecode:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

With `a=4` and `b=9`:

~~~text
locals: [4, 9], operand stack = []
iload_0 -> [4]
iload_1 -> [4, 9]
iadd    -> [13]
ireturn -> returns 13 to the caller
~~~

At a conceptual level, the interpreter repeats the operation “fetch bytecode, determine opcode, perform semantics, and update pc”. A pseudo-code:

~~~text
while (method is active):
    opcode = readInstruction(pc)
    dispatch(opcode)
    performJVMOperation()
    advancePcAsRequired()
~~~

This is **not the literal source code of the HotSpot interpreter**. HotSpot has a template interpreter and optimized machine-code stubs; the “a switch in C” explanation is only an introductory learning model.

### What Problems Does the Interpreter Solve?

1. Runs cold methods with minimal preparation/native-code generation cost.
2. Supports early execution during startup/class initialization according to JVM rules.
3. Records profiling data so the compilation policy can decide when code becomes hot.
4. Provides a fallback path when optimized code is invalidated or must deoptimize.
5. Maintains flexibility when class loading, type behavior, and method call sites change.

**Cost:** repeated dispatch/bytecode operation loops can be slower than optimized native code, especially in hot loops. However, not every method is worth compiling: for a method that runs only once, compilation cost can outweigh the benefit.

## 4. What Problems Does JIT Solve?

Instead of decoding bytecode instructions repeatedly, JIT can translate a hot bytecode region into native instructions following a conceptual pipeline:

~~~text
Bytecode + class metadata + runtime profiles
           |
           v
Compiler intermediate representation
           |
           v
Data-flow/control-flow analysis
Inlining, constant folding, guard insertion,
range-check optimization, escape analysis ...
           |
           v
Register allocation + machine-code generation
           |
           v
Native compiled code -> code cache
~~~

Potential benefits:

- Reduces interpreter dispatch overhead on the hot path.
- **Inlining** eliminates the overhead of many small method calls and unlocks cross-method optimizations.
- **Devirtualization** leverages observed receiver types to optimize virtual calls with appropriate guards/fallbacks.
- **Constant folding, dead-code elimination**, and common-subexpression optimizations.
- **Loop optimizations** such as hoisting/unrolling when safe.
- **Range-check elimination** when bounds are proven valid.
- **Escape analysis/scalar replacement** when an object does not need to materialize as an actual heap object.

**JIT must not violate Java semantics.** Necessary null/bounds/access checks must still be preserved; `int` overflow, exception paths, the Java Memory Model, class loading, dynamic dispatch, and GC reachability all have correctness constraints.

A JIT-compiled region is not guaranteed to run faster in every case: guard overhead, code size, cache locality, and runtime data can cause the benefit to vary.

## 5. Hotness: Hot Methods and Hot Loops

HotSpot typically uses multiple pieces of information to decide on compilation:

- **Invocation count:** the method is called many times.
- **Backedge count:** a loop iterates many times, passing through a backward branch in bytecode.
- **Type profiles:** receiver types appearing at call sites, supporting inlining/devirtualization.
- **Branch behavior:** hot/cold paths and actual probabilities.
- **Compiler queues, code cache, tier, runtime workload:** choosing which compilation yields effectiveness.

A long-running loop can make a method hot **even if the method is called only once**.

~~~java
static long countUp(int limit) {
    long sum = 0;
    for (int i = 0; i < limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

This is an illustrative method snippet. Calling `countUp(1_000_000)` once may be enough to make the loop hot depending on the JVM/settings, but **there is no promise** that “at exactly 1,000,000 iterations JIT will definitely compile”.

**Do not use magic numbers** like “every method compiles after exactly 10,000 calls”. Thresholds and decisions vary by tiered policy, backedges, code characteristics, JVM flags, and version. HotSpot's `-XX:CompileThresholdScaling` flag can affect thresholds, but does not turn this process into a uniform count.

## 6. Tiered Compilation: Why Are Both C1 and C2 Needed?

Standard HotSpot has **tiered compilation**, leveraging the interpreter and multiple compiler tiers to balance startup, profiling overhead, and peak throughput.

| Common Tier | Engine | Role |
| --- | --- | --- |
| Level 0 | Interpreter | Bytecode execution; can collect profiles |
| Level 1 | C1 | Compiled code with little/no profiling |
| Level 2 | C1 | Compiled code with limited profiling |
| Level 3 | C1 | Compiled code collecting fuller profiling |
| Level 4 | C2 | Optimized compiled code based on profiles |

Level numbers are **details of HotSpot's tiered policy**, not specified by the JVMS. Some builds/configurations use different compilers or only a subset of tiers.

**Both C1 and C2 are JIT compilers.** C1 prioritizes compilation speed and supports appropriate profiling; C2 invests in heavier optimizations for hot code with sufficient data.

Do not assume every method goes **0→1→2→3→4**. Some methods are only interpreted, some are compiled by C1, some reach C2, some undergo OSR, or get deoptimized/recompiled. The path selection policy depends on workload characteristics.

### Why Not Compile Everything with C2 Right at Startup?

Compilation consumes CPU, code-cache/native memory, and time. A program may load thousands of methods while using only a small percentage frequently. **Adaptive optimization** helps HotSpot invest only where it is likely to pay off. Compiling early with C2 before having runtime profiles can miss important information for optimization.

## 7. OSR: Switching to Compiled Code Mid-Loop

**On-Stack Replacement (OSR)** allows the JVM to transfer the state of an **actively executing method** from the interpreter (or an appropriate compiled tier) to OSR compiled code at a suitable bytecode point.

~~~text
A single method call with a very long loop
     |
     v
Interpreter executes the first few iterations
     |
     v
Loop backedge counter makes the method/loop hot
     |
     v
JIT generates an appropriate OSR entry
     |
     v
Runtime transfers execution state to the OSR compiled entry
     |
     v
Subsequent iterations can run native code
~~~

**OSR differs from compilation from method entry:** a normal entry serves calls starting the method; an OSR entry must adapt the locals/operand stack state at a loop BCI when the method is already partway through execution.

OSR is **not guaranteed** to happen for every loop. If there are too few iterations, compilation does not finish in time, the VM has interpreter-only enabled, or the JIT policy does not select it, the method may run entirely interpreted.

## 8. Speculative Optimization and Deoptimization

JIT may observe that a call site almost exclusively calls one implementation of an interface. It can optimize the common path via inlining along with a **type guard**. If the runtime later encounters a new implementation, the guard may fail.

~~~text
Profile: receiver type is usually AddOne
         |
         v
Compiled hot path with type guard
         |
         +-- AddOne -> fast inlined behavior
         |
         +-- Other type -> generic path or deoptimization
                               |
                               v
                         correct Java behavior
~~~

**Deoptimization** helps HotSpot restore/migrate a compiled execution state back to a compatible form to continue running according to Java semantics, when speculative assumptions no longer hold.

- Deoptimization is not automatically a Java exception.
- A new receiver type does not **necessarily** cause deoptimization: compiled code might already have a generic fallback or a polymorphic inline cache.
- The JVM can update the profile and then recompile more suitable code.
- Dynamic class loading and dynamic dispatch make this mechanism especially important.

**Common misconception:** saying “C2 guesses types so it can return wrong results”. Runtime guards and deoptimization exist precisely to preserve correctness even when assumptions are invalidated.

## 9. Runnable Java 17+: Same Result in Interpreter/JIT Modes

Create file **`InterpreterJitDemo.java`**:

~~~java
public class InterpreterJitDemo {
    private static volatile long published;

    static int transform(int x) {
        return x * 3 + 1;
    }

    static long sumTransformed(int limit) {
        long total = 0;
        for (int i = 0; i < limit; i++) {
            total += transform(i);
        }
        return total;
    }

    public static void main(String[] args) {
        published = sumTransformed(100_000);
        System.out.println("sum=" + published);
        System.out.println("example=" + transform(7));
    }
}
~~~

Compile/run:

~~~bash
javac -g InterpreterJitDemo.java
java InterpreterJitDemo
~~~

**Exact stdout when the program completes normally (without compilation diagnostics enabled):**

~~~text
sum=14999950000
example=22
~~~

Because:

~~~text
transform(i) = 3*i + 1
sum(i=0..99999) = 3*(99999*100000/2)+100000
                 = 14,999,950,000
transform(7) = 3*7+1 = 22
~~~

`total` is `long` so the sum does not overflow in this example; for `0 <= i < 100000`, `transform(i)` also stays within the `int` range.

### Try Three JVM Modes

On HotSpot supporting the flags:

~~~bash
java -Xint InterpreterJitDemo
java -Xmixed InterpreterJitDemo
java -Xcomp InterpreterJitDemo
~~~

| Mode | Purpose |
| --- | --- |
| `-Xint` | Interpreter-only: no JIT compilation into native methods |
| `-Xmixed` | Interpreter combined with JIT for hot code |
| `-Xcomp` | Testing mode prioritizing compilation; not recommended by Oracle for production |

**Java semantics and the two output lines must be identical** across successful runs. Execution time, compilation events, and GC logs may differ. For a short program, one must not conclude from stdout alone that method `sumTransformed` was OSR-ed or C2-compiled.

**What the example proves:** the execution strategy can differ while the logical Java result remains the same. **What it does not prove:** which compiler is definitely chosen or how many times throughput improves.

### Inspecting Bytecode with javap

~~~bash
javap -c -p InterpreterJitDemo
javap -v -p InterpreterJitDemo
~~~

Things to look for:

- `transform` has the corresponding arithmetic bytecodes.
- `sumTransformed` has a loop and a backward branch.
- `main` has method invocations and output code.

`javap` displays **JVM bytecode in the class file**, **not the native machine code generated by JIT**. Therefore, seeing `invokestatic` in `javap` output does not prove JIT will always keep the call instruction after inlining.

## 10. Runnable Java 17+: One Call Site with Two Receiver Types

Create file **`ReceiverProfileDemo.java`**:

~~~java
public class ReceiverProfileDemo {
    interface Operation {
        int apply(int n);
    }

    static final class AddOne implements Operation {
        public int apply(int n) {
            return n + 1;
        }
    }

    static final class DoubleIt implements Operation {
        public int apply(int n) {
            return n * 2;
        }
    }

    static int invoke(Operation op, int n) {
        return op.apply(n);
    }

    public static void main(String[] args) {
        Operation common = new AddOne();
        Operation other = new DoubleIt();

        long sum = 0;
        for (int i = 0; i < 20_000; i++) {
            sum += invoke(common, 3);
        }

        System.out.println("common-sum=" + sum);
        System.out.println("other-receiver=" + invoke(other, 3));
    }
}
~~~

~~~bash
javac ReceiverProfileDemo.java
java ReceiverProfileDemo
~~~

**Stdout:**

~~~text
common-sum=80000
other-receiver=6
~~~

20,000 calls with `AddOne.apply(3)` return 4 for a total of 80,000; the call to `DoubleIt.apply(3)` returns 6. JIT may observe the receiver type of previous calls and optimize the common path, but **these two lines do not prove that deoptimization occurred**. The runtime may not have compiled the method yet, or compiled code handles polymorphism/fallback.

## 11. Observing the Compiler with HotSpot Logs

Oracle JDK 25 documents the flags:

~~~bash
java -XX:+PrintCompilation InterpreterJitDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation InterpreterJitDemo
~~~

Enabling diagnostics will cause the overall JVM output to **include additional log lines**. Thus, the two stdout lines in section 9 are **the program's output without diagnostics enabled**, not the entire output when adding the flags here.

`PrintCompilation` can show:

- Compile task id and method name.
- Compiler tier, OSR BCI in cases where it is represented.
- When the VM records a compilation event.
- A method becoming non-entrant or code being replaced according to its lifecycle.

A **hypothetical line for reading the format**, not the exact output of a run:

~~~text
  94   67 %  3   InterpreterJitDemo::sumTransformed @ 4 (25 bytes)
~~~

The `%` symbol is typically associated with an OSR entry in HotSpot's format; the numbers are only examples. Do not assume the same ID, tier, BCI, or order across all JDKs/machines.

`PrintInlining` can explain which methods were inlined or rejected due to code size, profile, hotness, or compiler budget. If `transform` is inlined into the caller, a separate invocation may no longer exist in optimized machine code, yet source semantics are still preserved.

**`-Xcomp` is a testing mode**, which can increase compilation overhead and slow down startup. **`-Xint`** is a useful tool to isolate JIT's impact during diagnosis, not the fastest way to run in production.

## 12. Code Cache and the Cost of Native Compilation

Compiled machine code needs memory to live in. HotSpot uses the **Code Cache** to store compiled methods along with JVM code artifacts. This is **not the Java heap containing POJO objects**.

| Option | Purpose |
| --- | --- |
| `-XX:ReservedCodeCacheSize=...` | Limits the code cache according to the implementation |
| `-XX:+SegmentedCodeCache` | Divides the code cache into segments when appropriate |
| `-XX:-TieredCompilation` | Disables HotSpot's tiered policy |
| `-XX:CompileThresholdScaling=...` | Scales compilation thresholds |
| `-XX:+PrintCompilation` | Prints compiler events |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Prints inlining decisions |

The compiler uses CPU threads, queues, and an amount of memory for intermediate representation; compiled code also occupies the Code Cache and can affect the instruction cache. When the cache fills up, the runtime may have to reclaim compiled nmethods or restrict compiling. Therefore, “JIT compile all bytecode immediately” is not a free way to boost performance.

## 13. Interpreter/JIT Do Not Change JVM Semantics

This is a critical invariant:

- `new` must still provide correct object identity.
- `getfield`, `putfield`, `invokestatic`, `invokevirtual` must satisfy the exact linking, access, and dispatch rules.
- `NullPointerException`/`ArrayIndexOutOfBoundsException` occur when Java semantics require; JIT may only omit checks after proving safety or inserting an equivalent guard.
- `synchronized`/`volatile` and happens-before rules must be preserved.
- GC must recognize live references even in compiled frames.
- Dynamic class loading and interface polymorphism must maintain consistent behavior.

JIT **may merge, reorder, or eliminate unobservable operations** when safe, but must not alter observable program behavior protected by the spec.

**Deoptimization is part of the correctness solution**, not a confession that JIT “guesses and returns nonsense”. Assumptions have proper guards and fallbacks.

## 14. How to Measure JIT Performance Without Falling into Benchmark Traps

A measurement like:

~~~java
long start = System.nanoTime();
long answer = sumTransformed(100_000);
long duration = System.nanoTime() - start;
System.out.println(duration);
~~~

This is only an **illustrative snippet that must be placed in a class with the `sumTransformed` method**, not a reliable benchmark on its own.

Common errors:

1. **Startup and class loading** dominate a program that is too short.
2. **JIT warmup** is incomplete; compile jobs may be running concurrently.
3. **Dead-code elimination:** if the result is unused, the optimizer may remove the work.
4. **Constant folding:** fixed inputs may be simplified much more than in a real workload.
5. **GC/scheduling/CPU frequency** create noise.
6. **Compilation tiers/OSR** change between iterations.
7. **Diagnostic logging** increases measurement overhead.
8. **Measuring once** does not provide enough information about latency distribution.

**Proper process:** use JMH for microbenchmarks with warmup, forks, measurement iterations, sink/Blackhole, and an appropriate profiler. If the target is a server, look at startup, first-request latency, steady-state throughput, P95/P99, CPU, and memory on a representative workload. Do not claim “JIT is exactly N times faster” from an addition-loop example.

## 15. When Is the Interpreter Important, When Is JIT Important?

| Scenario | Interpretation |
| --- | --- |
| CLI that runs a small task and exits | Compilation cost may not pay off; startup plays a large role |
| Long-running server with a few hot handlers | JIT can optimize effectively, improving throughput after warmup |
| Application with very many rare code paths | Interpreter keeps a path for cold code without compiling everything |
| Method with a high-iteration loop called only once | OSR can help transition the hot loop to compiled code |
| Call site mostly sees one receiver type | JIT can guarded-inline the common path |
| Runtime loads a new implementation | Guard/fallback/deopt help preserve semantics |
| Limited Code Cache or compiler CPU | Compiling too much has a cost, requiring runtime observation |
| Bug only appears when JIT is enabled | Can compare with `-Xint` to diagnose; do not assume a JIT bug without evidence |

A service “running fast after 30 seconds” **is not necessarily entirely due to JIT**: caches, network/database connections, JIT, class initialization, and GC may all be involved. Measurement tools are needed to identify the cause.

## 16. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “`javac` generates machine code for the current CPU.” | `javac` typically generates JVM bytecode. |
| “The interpreter executes Java source line by line.” | It executes JVM bytecode. |
| “Java is only interpreted, not native.” | HotSpot typically combines an interpreter with JIT. |
| “JIT compiles the entire classpath at startup.” | HotSpot uses adaptive profiling/policy; many cold methods do not compile. |
| “Hot method = called exactly 10,000 times.” | Invocation/backedge counts, tiers, policies, and runtime state govern this. |
| “A method called only once cannot be JIT-compiled.” | A long loop can use OSR. |
| “C1 is the interpreter, only C2 is JIT.” | Both C1 and C2 are JIT compilers. |
| “Tiered always forces a method through all levels 0 to 4.” | There are multiple transition paths and skipped tiers. |
| “JIT optimizes by removing all null/bounds checks regardless of data.” | It may only optimize if preserving exact semantics/guards. |
| “Once JIT compiles a method, the code is immutable forever.” | Recompilation/invalidation/deoptimization exist. |
| “Deoptimization is a Java exception.” | It is a runtime mechanism to preserve execution. |
| “OSR is when a method is called again from the beginning.” | OSR can transition a running method at a loop BCI. |
| “`javap -c` shows native machine code.” | It shows the class file's JVM bytecode. |
| “`-Xint` disables GC.” | `-Xint` disables JIT; GC still needs to operate. |
| “`-Xcomp` is always faster than mixed mode.” | It is a testing mode with overhead/lack of profiles; not a production default. |
| “The Code Cache is the Java heap.” | The Code Cache stores compiled code, separate from the Java object heap. |
| “PrintCompilation ID/tier is always identical across runs.” | Events depend on VM settings/runtime. |
| “A single-run benchmark is enough to prove peak throughput.” | Warmup, forks, noise measurement, and JIT state are required. |
| “JIT makes Java non-portable.” | Bytecode is portable across the Java platform; native compilation is adapted to the CPU by the runtime. |
| “AOT and JIT are the same thing.” | AOT compiles/prepares ahead of time; JIT compiles at runtime. |

## 17. Self-Check with Answers

**1.** What does `javac` typically produce?  
**Answer:** Java class files containing JVM bytecode and metadata; not native CPU instructions for every platform.

**2.** What need does the interpreter address?  
**Answer:** Allows executing bytecode with low initial compilation cost, useful for cold code/startup and profiling.

**3.** What benefits does JIT bring?  
**Answer:** Generates native compiled code for hot code, optimizes based on runtime profiles, and reduces execution overhead.

**4.** Why doesn't the compiler optimize all methods immediately?  
**Answer:** Compilation consumes CPU/memory/code-cache; many methods do not run enough to pay off.

**5.** What are two common hotness signals?  
**Answer:** Method invocation counts and loop backedge counts, in addition to type/branch profiles.

**6.** How do Level 3 and Level 4 differ in standard HotSpot tiered mode?  
**Answer:** Level 3 is typically C1 with fuller profiling; Level 4 is typically C2 optimized code.

**7.** Can a very long loop use JIT even if the method is called only once?  
**Answer:** Yes, via OSR if the runtime selects/compiles it in time.

**8.** Does a new receiver type necessarily cause a Java exception?  
**Answer:** No. Generic dispatch, guards, and deoptimization must still yield correct Java behavior.

**9.** Why does the InterpreterJitDemo program always print the same result with `-Xint` and `-Xmixed`?  
**Answer:** Execution strategies differ but must preserve the same Java semantics.

**10.** To see which methods the compiler is compiling on HotSpot, what do you use?  
**Answer:** Try `-XX:+PrintCompilation`, noting that diagnostic output is not fixed.

**11.** Is `javap` enough to prove a method is inlined at runtime?  
**Answer:** No, it displays bytecode, not optimized machine code.

**12.** Can JIT affect startup latency?  
**Answer:** Yes. Compilation/profiling has overhead; tiered policy balances startup and throughput.

**13.** Should `-Xcomp` be used in production because “compiling is always good”?  
**Answer:** No. Oracle marks it as a testing mode; real workloads must be measured.

**14.** What is the job of deoptimization?  
**Answer:** Keep execution correct when assumptions for optimized code no longer hold, potentially falling back/recompiling.

## 18. Official Sources

- [Oracle Java SE 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): JVM/HotSpot runtime, tiered compilation, and performance.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xint`, `-Xmixed`, `-Xcomp`, `PrintCompilation`, `PrintInlining`, `TieredCompilation`, `CompileThresholdScaling`, and Code Cache options.
- [Oracle HotSpot Performance Enhancements](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html): tiered compilation, escape analysis, and optimization.
- [Oracle — Java HotSpot Performance Engine Architecture](https://www.oracle.com/java/technologies/whitepaper.html): adaptive optimization, hot-spot detection, and deoptimization; the whitepaper is a historical architecture document and does not guarantee identical policies across every JVM release.
- [OpenJDK HotSpot — compilationPolicy.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): compiler tiers and policy implementation; the master branch may differ from the version in use.
- [JVMS Java SE 25 — `2.11` Instruction Set Summary](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.11): bytecode instruction concepts.
- [JVMS Java SE 25 — Chapter 6 Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): semantics of `iadd`, `invokevirtual`, `ireturn`, and other bytecodes.
- [JDK 25 — javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): inspecting bytecode/constant pool from class files.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): JVM benchmarking more reliable than a single `nanoTime` call.
- [Microsoft Java Developers — Tiered Compilation in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): how to read C1/C2, profiling, and compilation logs; cross-check with Oracle/OpenJDK when version confirmation is needed.

**Conclusion:** The interpreter allows the JVM to **execute bytecode early and cheaply in terms of compilation**; JIT **invests in generating optimized native code for hot regions** to boost long-running performance. Tiered compilation, runtime profiling, OSR, deoptimization, and the Code Cache are the components that help HotSpot balance **startup, warmup, throughput, latency, and CPU/memory overhead** while always preserving Java semantics.