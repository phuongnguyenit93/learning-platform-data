# Comparing -Xint Mode with Mixed Execution in a Controlled Experiment

## 1. Purpose: Measuring a JVM Change Without Equating Speed with Correctness

In the **HotSpot JVM**, the same bytecode file can be executed by the **interpreter**, **JIT-compiled machine code**, or a combination of both. Two important options when observing the difference are:

- **`-Xint`:** instructs HotSpot to execute **Java bytecode using the interpreter only**, disabling JIT compilation for bytecode. There is no longer any benefit from JIT-generated machine code for Java methods.
- **`-Xmixed`:** **mixed interpreter + JIT** execution mode: bytecode is interpreted when appropriate; sufficiently hot methods/loops can be compiled into native machine code. This is the **default** in standard HotSpot; it can be specified explicitly for easy comparison.

These modes **do not change the semantics of the Java language**. If a program is valid and does not depend on data races or unspecified behaviors, the logical result must be consistent whether the bytecode runs interpreted or JIT-compiled. What can differ is **time**, **CPU usage**, **warm-up**, **compilation activity**, and how the JVM allocates resources.

### Experimental Questions to Answer

1. Do the two modes produce the **same checksum/output** with the same program and input?
2. How does a repeatedly computed workload differ in **latency** between the two modes?
3. Why must the initial startup, warm-up phase, and steady state be **measured separately**?
4. What signs indicate that the JIT actually compiles methods in `-Xmixed`?
5. What can be concluded from a single measurement, and what **cannot be concluded**?
6. How do `-Xcomp`, `-XX:-TieredCompilation`, and `-XX:TieredStopAtLevel` differ from `-Xint`?

**Scope:** this guide walks through a **small programmatically reproducible experiment** on HotSpot JDK 17+, without promising the same runtime, speedup ratio, or identical JIT compilation events across all machines.

## 2. Two Base Commands and What Actually Differs

After compiling a Java file into a class file:

```bash
java -Xint ExecutionModeDemo
java -Xmixed ExecutionModeDemo
```

At an intuitive level:

```text
                     Same .class bytecode
                              |
                     HotSpot JVM startup
                              |
              +---------------+----------------+
              |                                |
            -Xint                            -Xmixed
              |                                |
    Interpreter executes                 Interpreter starts
    application bytecode                  executing bytecode
              |                                |
      No JIT compilation                  invocation/backedge
      of Java bytecode                    hotness/profile data
              |                                |
              |                        sufficiently hot?
              |                           /          \
              |                         no            yes
              |                         |              |
              |                    interpreter     C1 / C2 JIT
              |                                         |
              +----------------+------------------------+
                               |
                         Same Java semantics
                               |
                      Different CPU and timing
```

The illustrative diagram **is not a fixed compilation schedule**: the JVM may generate C1/C2 code, OSR code for loops, inline methods, deoptimize code, or never JIT-compile methods that run too infrequently.

### 2.1. Does `-Xint` Disable All Native Code in the Process?

**No.** HotSpot still has runtime code written in C/C++, native stubs, VM services, system calls, JNI, and parts of the JVM that are not pure Java bytecode. `-Xint` states that **Java bytecode is executed by the interpreter**, not that “the CPU is not allowed to run any native instruction.”

An application calling a native library still uses that library; do not describe `-Xint` as a mode where “every operation runs under the interpreter.”

### 2.2. Does `-Xmixed` Mean All Methods Are JIT-Compiled Immediately?

**No.** A cold method may remain interpreted. JIT compilation is decided by the **HotSpot compilation policy**, counters, profiling, and compiler/code cache resources. In a HotSpot tiered configuration, hot methods may go through C1 and then C2, and long loops may trigger on-stack replacement (OSR).

### 2.3. Both Modes Still Use GC

Interpreter-only does not disable garbage collection, class loading, the verifier, synchronization, heap management, or Java's memory safety. An `-Xint` measurement may be slow due to interpreted execution and still have GC pauses; an `-Xmixed` measurement may exhibit both JIT compilation and GC.

**Only conclude the cause of slow execution time when there is evidence**, do not automatically attribute every millisecond of difference to JIT.

## 3. Defining a “Controlled Experiment” in the JVM

For this article, the **independent variable** is the execution mode `-Xint` or `-Xmixed`. Other factors are kept as constant as possible:

| Component | Experiment Setup |
| --- | --- |
| JVM vendor/build | Same `java` path, same `java -version` |
| Java class files | Same `ExecutionModeDemo.class` produced by `javac --release 17` |
| Input | Same warm-up calls, measured calls, steps per call |
| Heap flags | Initially leave JVM defaults identical; if setting `-Xms/-Xmx`, use the same for both modes |
| Machine | Same host/container, CPU quota, and background workload as stable as possible |
| Execution mode | Separate process each time, changing only `-Xint`/`-Xmixed` per run |
| Measurement | Same `System.nanoTime` call pattern, no console printing inside the computation loop |
| Results | Compare correctness checksum first, latency second |
| Repetition | Multiple independent runs, alternating/swapping order to reduce bias |

**Why are separate processes needed?** A running JVM accumulates profiling/compiled methods state, heap, and caches over time. Running the two modes in two fresh processes prevents accidentally reusing already warmed-up compiled code from the previous trial.

### 3.1. Dependent Variables to Observe

- **Correctness:** checksum and printed logical values.
- **Elapsed time:** duration of the *measured section* calculated using `System.nanoTime()`.
- **Time per call:** can be calculated from elapsed time and the number of calls, but must be understood as the average of the measured workload, not the duration of each individual invocation.
- **Compilation activity:** `-XX:+PrintCompilation` log when using `-Xmixed`.
- **Whole-process time:** can be measured separately from outside, including JVM startup, class loading, and teardown.
- **CPU/memory:** OS metrics, if the experiment's scope expands.

### 3.2. Things That Cannot Be Strictly Controlled

- CPU frequency/boost, temperature, and power management.
- Scheduling, JVM compiler threads, background services.
- GC timing and safepoints.
- Cache state, JIT inlining choices, deoptimization.
- JDK ergonomics and container available CPUs.
- Native code/intrinsics used by the Java standard library.

Therefore, you must **measure multiple times and report the distribution of results**, rather than a single “standard value for every machine.”

## 4. Preparing the Java 17+ Environment

First, verify the runtime:

```bash
java -version
javac -version
```

To check which HotSpot flags the JVM supports:

```bash
java -Xint -version
java -Xmixed -version
```

The commands above **are not benchmarks**: they only check that the parser/runtime accepts the options and print JVM information. Do not infer that `java -Xint -version` being faster/slower than `java -Xmixed -version` represents a result for a real application.

Use a JDK with compatible `java` and `javac`. If an IDE configures multiple JDKs, **verify the exact binary** used to run both modes; otherwise, version differences could outweigh execution mode differences.

### 4.1. Same JVM Implementation Required

`-Xint` and `-Xmixed` in this article are **HotSpot-specific execution mode switches**. Other VMs may support, reject, or implement them differently. Do not claim that every JVM is required to have these two options under the Java Language Specification.

### 4.2. Do Not Add Logging to the Measurement Loop Initially

`PrintCompilation`, `PrintInlining`, and verbose logging flags can generate I/O and alter timing/scheduling. First measure the baseline **without diagnostic output enabled**, then **re-run separately** to observe compiler events.

## 5. Complete Java 17+ Example for Both Modes

Create the file **`ExecutionModeDemo.java`** with the following complete content:

```java
public final class ExecutionModeDemo {
    private static volatile long sink;

    static int mix(int x) {
        x ^= x >>> 13;
        x *= 0x5bd1e995;
        x ^= x >>> 15;
        return x;
    }

    static long work(int calls, int steps) {
        long total = 0;
        for (int c = 0; c < calls; c++) {
            int value = c + 1;
            for (int i = 0; i < steps; i++) {
                value = mix(value + i);
            }
            total += Integer.toUnsignedLong(value);
        }
        sink = total;
        return total;
    }

    public static void main(String[] args) {
        final int warmupCalls = 800;
        final int measuredCalls = 1500;
        final int steps = 1024;

        work(warmupCalls, steps);
        long start = System.nanoTime();
        long checksum = work(measuredCalls, steps);
        long nanos = System.nanoTime() - start;

        System.out.println("warmupCalls=" + warmupCalls);
        System.out.println("measuredCalls=" + measuredCalls);
        System.out.println("stepsPerCall=" + steps);
        System.out.println("checksum=" + checksum);
        System.out.println("sinkMatches=" + (sink == checksum));
        System.out.printf(java.util.Locale.ROOT,
                "elapsedMs=%.3f%n", nanos / 1_000_000.0);
    }
}
```

The program includes:

- A **small `mix` method** simple enough for the JIT to consider inlining.
- A **`work` method** containing two loops; a workload clear enough to count the number of executions.
- **Data dependency**: the result of the previous iteration is the input to the next, reducing the risk of the entire loop becoming a trivial invariant calculation.
- **`volatile sink`** making the final computed value an observable side effect; it does not by itself guarantee identical machine instructions between the two modes.
- **Warm-up before measurement** and using `System.nanoTime` for the **measurement interval**.
- **No logging inside the computation loop**, preventing I/O from dominating computation.
- **`Locale.ROOT`** to format the decimal point in the timing line more consistently across locales.

### 5.1. Compiling

```bash
javac --release 17 ExecutionModeDemo.java
```

Use the same class file for all runs. There is no need to build with `-Xint`/`-Xmixed` flags because they are **runtime options** of the `java` command, not `javac` source compilation options.

### 5.2. Default and Explicit Mixed Run

```bash
java ExecutionModeDemo
java -Xmixed ExecutionModeDemo
```

On HotSpot, `-Xmixed` is the typical default execution mode, though in practice you should check JVM options/environment if there are special configurations.

### 5.3. Interpreter-Only Run

```bash
java -Xint ExecutionModeDemo
```

### 5.4. Deterministic Stdout Lines

When running successfully in both modes, the **first five lines** must be:

```text
warmupCalls=800
measuredCalls=1500
stepsPerCall=1024
checksum=3215795315003
sinkMatches=true
```

**The last line is a variable measurement**, for example formatted as:

```text
elapsedMs=2.291
```

The value `2.291` is **one local measurement from a single `-Xmixed` run** during testing, **not a fixed exact stdout**. Re-running or using `-Xint` will yield a different `elapsedMs`. You must distinguish between **verified logical results** and **unguaranteed timing measurements**.

### 5.5. Empirical Checks Performed

The example was compiled with `javac --release 17`, then run on OpenJDK/HotSpot in four configurations:

- `-Xmixed`
- `-Xint`
- `-XX:-TieredCompilation`
- `-Xcomp`

All four runs printed the same **checksum `3215795315003`** and `sinkMatches=true`. The fact that they had different timings does not prove that each configuration will have the same speed ranking on every system; the JDK implementation/build and amount of warm-up have a major impact.

## 6. Explaining Exactly What the Program Measures

### 6.1. What Did the Workload Do?

`work(warmupCalls, steps)` calls `mix` inside 800 × 1024 iterations. Next, `work(measuredCalls, steps)` performs another 1500 × 1024 iterations under the `nanoTime` interval.

Total `mix` operations according to the Java loop structure:

```text
Warm-up:   800 × 1024 =   819,200 iterations
Measured: 1500 × 1024 = 1,536,000 iterations
Total:                = 2,355,200 iterations
```

This is the **logical evaluation count** from the Java structure, not necessarily the number of machine-level call instructions. The JIT may inline `mix` into `work`.

### 6.2. Why Is the Checksum Identical?

The computation uses integer arithmetic with Java semantics:

- Unsigned right shift `>>>`.
- `int` multiplication following overflow/wrap-around rules modulo \(2^{32}\).
- Bitwise XOR.
- `Integer.toUnsignedLong` converting `int` to the corresponding unsigned `long` value.

Whether executed by the interpreter or compiled code, **the Java result must be the same** if the JVM is compliant.

### 6.3. What Does `sinkMatches=true` Do?

`sink` is a static volatile field assigned in `work`. After measuring, the code reads it back to verify that the result was preserved. Writing to a volatile field is an **observable side effect** under the Java Memory Model, avoiding some simple benchmark pitfalls where the JIT might eliminate the computation entirely because the result is unused.

However, this **is not a perfect JMH blackhole** and does not prevent all forms of compiler optimization. This demo is suitable for learning execution modes; it does not replace a dedicated benchmarking tool.

### 6.4. What Does `System.nanoTime()` Measure?

It returns a monotonic time value suitable for measuring **elapsed durations** by taking differences, not a wall-clock calendar time. The measurement:

```java
long start = System.nanoTime();
long result = work(1500, 1024);
long elapsed = System.nanoTime() - start;
```

is an illustrative snippet taken from the program. `elapsed` is the **elapsed time between two clock reads**, including potential interruptions such as scheduler preemption, GC pauses, or interleaved JIT compilation. It is not the pure CPU time of the `work` method alone.

### 6.5. Why Not Print a Fixed “Standard Time”?

Across different JDKs/OSes/CPUs, elapsed time can vary. Even on the same machine, the first run, subsequent runs, CPU load, and compilation timing also differ. **Never compare `elapsedMs` against a fixed constant to grade pass/fail**.

## 7. Warm-up Means Different Things in `-Xmixed` and `-Xint`

In **`-Xmixed`**, warm-up can:

- Load, verify, link, and initialize required classes.
- Execute paths via the interpreter.
- Increment invocation/backedge counters.
- Collect branch/type profiles.
- Trigger C1/C2 compilation and OSR when eligible.
- Warm up code/data caches.

In **`-Xint`**, warm-up can still perform tasks like **class loading, initialization, cache warming, and GC activity**, but **it does not convert Java bytecode to JIT-compiled native code** under that mode.

Therefore:

> Warm-up is a step to control startup state, but “warming up for the same number of iterations” **does not mean the JVM reaches the same optimization state**.

### 7.1. Warm-up Does Not Guarantee Steady State by Itself

800 × 1024 iterations in the demo is a practical threshold, **not a guarantee** that the JIT has reached C2 level 4 for every method before `start = System.nanoTime()` is captured. Compiler threads may still be processing work when the measured phase begins.

To seriously analyze steady state, you must observe JIT logs/traces or increase warm-up under properly designed benchmark conditions, rather than simply assuming a fixed count is enough.

### 7.2. When Can `-Xint` Appear Similar to `-Xmixed`?

If the program is **very short**, process startup/shutdown and I/O take up most of the time, so the difference in compiled bytecode may be very small. JVM startup cost can also mask computation differences.

Therefore, if you only measure `java -Xint -version` vs `java -Xmixed -version`, you have not measured the actual benefit of JIT on hot code.

### 7.3. Conversely, Very Hot Work Can Create a Large Gap

When the same calculation runs millions of times, the interpreter must process bytecode for many iterations, whereas the JIT can perform optimizations/inlining/strength reduction based on runtime data. However, the exact speedup **is not guaranteed by the Java Specification** and depends on the workload.

## 8. A Local Test Result and How to Interpret It

In one run using OpenJDK/HotSpot, the program returned the following elapsed times:

| Mode | Measured section | Correctness |
| --- | ---: | --- |
| `-Xmixed` | **2.291 ms** | PASS — same checksum |
| `-Xint` | **25.124 ms** | PASS — same checksum |
| `-XX:-TieredCompilation` | **2.230 ms** | PASS — same checksum |
| `-Xcomp` | **4.327 ms** | PASS — same checksum |

**This is a single local sample, only illustrating how to read data**, not sufficient benchmark data to claim `-Xmixed` is exactly 10.97 times faster than `-Xint` for all programs. Do not use this table as an SLA, threshold, or production flag selection guideline.

### 8.1. Correct Interpretation

In the local sample, the measured section with `-Xmixed` is shorter than `-Xint`. This **aligns** with the expectation that hot computation benefits from JIT. However, from `elapsedMs` alone, you cannot accurately separate the exact milliseconds spent on compilation, GC, CPU scheduling, and machine-code execution.

### 8.2. Incorrect Interpretations

Do not conclude:

- “Every Java service is ten times slower if `-Xint` is enabled.”
- “`-Xcomp` is always faster than `-Xint` but slower than `-Xmixed`.”
- “`-XX:-TieredCompilation` is always the fastest production configuration.”
- “There is no GC/JIT overhead because the program only prints six lines.”
- “One measurement is enough to rank VM flags.”

**All performance conclusions require repetitions, environment descriptions, and measurement distributions.**

## 9. Repeating Experiments and Preventing Order Bias

A controlled approach:

1. Compile the file **once**, do not rebuild between the two modes.
2. Run **at least several independent rounds** for each mode.
3. Avoid running heavy IDE builds/indexing in parallel if possible.
4. Interleave the order instead of always running all `-Xint` first and then all `-Xmixed`.
5. Record each `elapsedMs`, not just the fastest run.
6. Compare the median, spread (p25/p75 or p95), and check for outliers.
7. When numbers are unstable, increase repetitions or investigate CPU/GC/I/O.

### 9.1. Command on Bash-style Shells

A trial round, each mode in a separate process:

```bash
for mode in -Xmixed -Xint; do
  echo "MODE: $mode"
  for run in 1 2 3 4 5; do
    java "$mode" ExecutionModeDemo
  done
done
```

This is a **Bash/POSIX-like shell command**, not directly applicable to PowerShell.

### 9.2. Command on Windows PowerShell

```powershell
foreach ($mode in @("-Xmixed", "-Xint")) {
    Write-Output "MODE: $mode"
    foreach ($run in 1..5) {
        java $mode ExecutionModeDemo
    }
}
```

The command above only executes multiple times and displays results; it **does not automatically compute the median**. You can export `elapsedMs` to a file and analyze it with a spreadsheet/script if needed.

### 9.3. Keep Correctness Stdout as Well

Do not just save the `elapsedMs` line and discard the checksum. If the program computes incorrectly, hits an OOME, fails due to a flag, or has altered input, those timing numbers are no longer comparing the same work.

### 9.4. Why Alternate the Order?

If the JVM/OS has just started or the CPU switches power states, later runs may be faster/slower. When always running one mode first, **mode order** becomes a confounding variable. Alternating `-Xint` and `-Xmixed` helps reduce some bias, though it cannot eliminate all external factors.

### 9.5. JVM Startup vs Measured Section

The program's `elapsedMs` **does not include process creation and startup before `main`**; it measures the code region between the two `nanoTime` calls. If the goal is end-to-end CLI time, you need an additional measurement from outside the process:

```powershell
Measure-Command { java -Xint ExecutionModeDemo }
Measure-Command { java -Xmixed ExecutionModeDemo }
```

The output of `Measure-Command` differs from the `elapsedMs` line because it includes **JVM startup + class loading + program + shutdown + shell/process overhead**. These are two different metrics and should not be added together or substituted for one another.

## 10. Verifying the JIT Path with `PrintCompilation`

To see whether `-Xmixed` actually triggers JIT, run a **separate diagnostic pass**:

```bash
java -Xmixed -XX:+PrintCompilation ExecutionModeDemo
```

On a supporting HotSpot build, this option prints **compilation events**, typically containing:

- Relative timestamp since VM startup.
- Compile ID.
- Compilation level (if tiered).
- `%` marker when OSR is used.
- Class/method, bytecode size.
- Events marking compiled code as no longer used for method entry.

The command can interleave compilation logs with the program's stdout. **Do not directly use the timing of a diagnostic run as a clean baseline**, because log I/O can affect scheduling/performance.

### 10.1. Some Sample Lines Observed

```text
27   13       3       ExecutionModeDemo::mix (21 bytes)
27   14       4       ExecutionModeDemo::mix (21 bytes)
28   15 %     3       ExecutionModeDemo::work @ 20 (62 bytes)
28   17 %     4       ExecutionModeDemo::work @ 20 (62 bytes)
```

This is a **sample excerpt from a test run** in a test environment. Leading numbers, IDs, compilation levels, and event order **are not fixed standard output**. Another machine or another run may not produce these exact lines.

### 10.2. How to Read Levels 3 and 4

In the standard HotSpot tiered C1/C2 model:

- **Level 0:** Interpreter.
- **Level 1:** C1 simple (no profiling).
- **Level 2:** C1 with limited profiling.
- **Level 3:** C1 with full profiling.
- **Level 4:** Heavily optimized C2.

A method **can follow the path 0 → 3 → 4**, but is not required to go through all levels or compile up to level 4.

### 10.3. What Is `%`?

In `PrintCompilation`, the `%` symbol usually indicates **OSR (On-Stack Replacement)** compilation, meaning the JVM can transfer the execution state of a running loop to compiled code at an appropriate **bytecode index (BCI)**.

For example, `ExecutionModeDemo::work @ 20` indicates a loop-related BCI position, **not the 20th invocation**.

### 10.4. Is `(21 bytes)` the Machine Code Length?

No. In a `PrintCompilation` line, the displayed size is normally the **bytecode size of the method**, not the total generated machine instructions. C2-compiled code can be longer or shorter depending on optimizations/code shape.

### 10.5. Why Are There `made not entrant` Lines?

An older nmethod can be put into a state where it is no longer used for new entries after a better version of compiled code appears or an assumption becomes invalid. This **is not by itself an application error**.

## 11. Checking Differences Between `-Xint` and `-Xmixed` in Logs

### 11.1. `-Xmixed`

```bash
java -Xmixed -XX:+PrintCompilation ExecutionModeDemo
```

You may see `ExecutionModeDemo::mix`, `ExecutionModeDemo::work`, and JDK methods being JIT-compiled. However, **not every method is guaranteed to appear in the log**: policy, inlining, startup, and compilation timing can vary.

### 11.2. `-Xint`

```bash
java -Xint -XX:+PrintCompilation ExecutionModeDemo
```

On interpreter-only HotSpot, the JVM does not JIT-compile the demo's Java bytecode, so you **should not expect C1/C2 compilation events** for Java methods as in `-Xmixed`. Other diagnostics or JVM information may still be printed depending on options/runtime.

**Avoid over-inferring from an “empty log”**: the log only shows information that the enabled tool and VM record, not an absolute proof of all code/native instructions being executed.

### 11.3. Compiler Print Lines Do Not Determine Speedup

Seeing `level 4` may show that a method was C2-compiled in that run, but actual speed is also influenced by inlining, CPU, GC, code cache, data distributions, and workload.

You should not rank code quality solely by “how many level 4 methods” there are.

## 12. Important Differences with `-Xcomp`

**`-Xcomp`** is a mode used to **stress/test the compiler** by prioritizing compiling methods instead of running them interpreted. According to OpenJDK/Oracle documentation, this is a **testing mode**, not an option recommended for production to increase speed.

```bash
java -Xcomp ExecutionModeDemo
```

### 12.1. Why Can `-Xcomp` Start Up Slower?

A very short application has many methods that only run once. Compiling these methods can take more time than the benefit gained from machine code when they are barely reused.

Therefore, you should not assume “compiling everything early” is definitely faster than interpreter + selective JIT.

### 12.2. `-Xcomp` Does Not Guarantee C2 Level 4 for Every Method

This flag changes the execution/compilation policy to stress the JIT; it **does not guarantee** compiler level 4 in all cases. The JVM may have other limits/compiler policies, or some methods may not be suitable to compile as expected.

### 12.3. Do Not Put `-Xcomp` in a Production Baseline

In an extended experiment, you can run `-Xcomp` to observe compilation/startup overhead, but **the most sensible comparison focus remains `-Xint` vs `-Xmixed`** when analyzing the benefits of HotSpot's selective JIT.

## 13. `-XX:-TieredCompilation` Is Not Synonymous with `-Xint`

The two flags:

```bash
java -XX:-TieredCompilation ExecutionModeDemo
java -Xint ExecutionModeDemo
```

**do not mean the same thing**.

- `-Xint`: disables JIT compilation for Java bytecode.
- `-XX:-TieredCompilation`: disables the **tiered compilation policy**, not necessarily disabling JIT; depending on the HotSpot build, an optimizing compiler may still compile methods.

If two runs happen to have nearly equal `elapsedMs`, **you cannot conclude they use the same engine**.

### 13.1. `-XX:TieredStopAtLevel=1`

```bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 ExecutionModeDemo
```

On HotSpot tiered C1/C2 builds supporting the flag, this configuration caps the maximum compilation level at the corresponding tier, useful for exploring C1. It **is not** interpreter-only because C1 is a JIT compiler that generates machine code.

### 13.2. Why Not Compare All Flags in an Absolute “Win/Lose” Table?

The flags differ in purpose:

| Mode | Experimental Question | Limitation |
| --- | --- | --- |
| **`-Xint`** | How long does interpreted bytecode take? | No JIT hot-path optimizations |
| **`-Xmixed`** | How does interpreter + selective JIT behave? | Has warm-up and compiler scheduling |
| **`-XX:-TieredCompilation`** | What happens without tiered heuristics? | JIT can still operate |
| **`-XX:TieredStopAtLevel=1`** | What is a C1-only-like path like? | Does not use C2 level 4; build-dependent |
| **`-Xcomp`** | What happens during compiler stress/testing? | Startup and compilation cost can be large |

If the goal is only to compare `-Xint` with the default JVM, there is no need to automatically conclude some third mode is “better.”

## 14. Inlining: Why Java Method Calls Are Not Equivalent to Machine-Code Calls

In the demo:

```java
static int mix(int x) {
    x ^= x >>> 13;
    x *= 0x5bd1e995;
    x ^= x >>> 15;
    return x;
}
```

A loop in `work` calls the `mix` method on every iteration. The JIT can **inline the body of `mix` into the loop**, meaning the machine code does not necessarily have to perform a separate native method call for every iteration.

### 14.1. Why Does This Matter?

With the interpreter, the JVM executes according to the bytecode execution model; the HotSpot JIT can eliminate method call overhead and optimize across method boundaries. This is one reason compute-intensive repeated workloads can benefit from `-Xmixed`.

However, the same code may yield different results if the JIT decides not to inline due to size, profile, code cache, or heuristics.

### 14.2. `PrintInlining`

On some HotSpot builds:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining ExecutionModeDemo
```

The output can print inlining decisions and reasons. This is a **diagnostic run** and should not be mixed into baseline measurements requiring clean conditions.

### 14.3. Do Not Conclude Each `mix` Call Takes Exactly One Fixed Nanosecond

Timing can depend on instruction scheduling, CPU cache, inlining, arithmetic throughput, branch predictors, and measurement. Method-call overhead does not equal a fixed number for every JVM.

## 15. OSR: A Loop Can Be Hot Even If the Method Is Not Called Often

**On-Stack Replacement (OSR)** allows HotSpot to transition a loop running in interpreted/C1 mode to a corresponding native compiled entry while the method has not yet returned.

In the demo, the `work` method has an inner loop. A single call `work(800, 1024)` executes many iterations while the invocation count of `work` itself may be low. **Backedge counts** of the loop can trigger OSR.

```text
work() method invocation
      |
      v
Interpreter / lower tier
      |
      v
loop backedge activity increases
      |
      +---- compiler policy requests OSR at BCI
                           |
                           v
                      OSR nmethod
                           |
                   execution transfers state
                           |
                           v
                    continues loop correctly
```

### 15.1. `%` in `PrintCompilation`

A record:

```text
28   15 %     3       ExecutionModeDemo::work @ 20 (62 bytes)
```

is an example of an **OSR compilation event**, not “the `work` method was called 15 times” or “the method becomes hot after exactly 28 ms on every machine.”

### 15.2. OSR Is Not Forced to Appear

When a loop is too short, interpreter-only is enabled, or the compiler chooses another path, OSR may not occur. Do not write a unit test asserting “must see the `%` symbol exactly once.”

### 15.3. OSR Differs from Compiled Method Entry

An OSR nmethod for a bytecode index inside a loop **differs** from an nmethod for a normal method entry. Both can be observed for the same Java method.

## 16. Benchmark Biases to Avoid

### 16.1. Constant Folding

If a benchmark always calls a calculation with the same constant and the result is unused, the JIT can **fold** the entire expression into a constant or eliminate it when valid. At that point `-Xmixed` appears unreasonably fast, but the experiment is no longer measuring the intended work.

The demo uses inputs varying via `c`, `i` and a mixing operation dependent on previous state to reduce this trap, though it still does not create a guarantee of “no optimizations.”

### 16.2. Dead-Code Elimination

If a benchmark computes an unobserved value:

```java
for (int i = 0; i < 1_000_000; i++) {
    expensiveButPureCalculation(i);
}
```

this is an **illustrative snippet**, and the `expensiveButPureCalculation` method is undefined. The compiler can eliminate the computation if the result has no observable effect. Use proper result consumption/blackholes, ideally with JMH.

### 16.3. Class Loading and JIT Warm-up

If you only measure the first call to `work`, you may be measuring both interpreter execution and compilation scheduling. A steady-state measurement requires sufficient warm-up and proper measurement methodology, not just placing a timer around the first call.

### 16.4. GC Noise

If a workload allocates many objects, GC pauses can intrude into the measurement interval; you might inadvertently compare GC behavior instead of execution engine behavior. The demo primarily uses arithmetic and does not allocate large arrays in the inner loop, aiming to **reduce rather than eliminate** GC impact.

### 16.5. Console I/O

Printing on every iteration causes I/O to dominate the computation, making the data unrepresentative of a hot numeric loop. The demo only prints after the timed section.

### 16.6. Clock Granularity and Measurement Overhead

If the measured section is too short (close to clock resolution), noise from `System.nanoTime`/scheduling can be relatively large. Increase workload/repetitions appropriately, or use JMH which has better timer/sampling design.

### 16.7. Compiling and Running Concurrently with Heavy Processes

IDE indexing, antivirus, other JVMs, or CPU thermal throttling can affect results. An unusual `elapsedMs` value is not necessarily caused by the Java optimizer.

### 16.8. Benchmarking Based on GC Log Content

Do not use `-XX:+PrintCompilation` when measuring the baseline and then compare it against `-Xint` without logging: that changes **two factors at once** — the engine and log I/O.

## 17. Extension: Measuring Cold Startup Separately from Steady-State

Two problems need to be distinguished:

1. **Cold CLI:** a user runs a command, the JVM starts up, does a short task, and exits. `-Xmixed` may not benefit much from JIT because the workload finishes before code becomes hot enough.
2. **Long-lived service:** an application runs for hours, handling many similar requests, building sufficient profiles for the JIT to compile hot paths. `-Xmixed` can have a much larger benefit compared to interpreter-only.

### 17.1. Why Does “Mixed Execution” Help Startup?

For cold methods, the JVM avoids compiling them before knowing they are worth optimizing. C1 can compile faster than C2 on initial hot paths, while C2 is used after sufficiently high-quality profiles are gathered.

Thus HotSpot tiered compilation attempts to balance **startup time and peak performance**, unlike the notion of “compiling everything before running.”

### 17.2. Do Not Transfer CLI Demo Results Directly to a Web Service

A request-based service has:

- JIT profiles that change with traffic.
- Many classes/frameworks/threads.
- GC and allocation patterns.
- Database/network I/O.
- Thread scheduling and container CPU quotas.

If you only use a compute demo to conclude “the service will be N times faster,” you have ignored the components that dominate end-to-end latency.

## 18. Reading Results Like an Experimenter

A reliable result report should record:

| Item | Example Entry |
| --- | --- |
| Hypothesis | “For a hot numeric loop, mixed JIT can reduce measured elapsed time compared to interpreter-only” |
| Java/JVM | `java -version` of the host machine |
| Input | warm-up 800 calls, measured 1500 calls, 1024 steps/call |
| Process isolation | Each run starts a fresh Java process |
| Modes | `-Xint` and `-Xmixed` |
| Correctness | Identical checksum: `3215795315003` |
| Data collection | Each `elapsedMs`, at least several runs/mode |
| Summary | Median, spread, number of runs, outliers |
| Diagnostics | `PrintCompilation` run separately, not mixed into baseline |
| Conclusion | Conclusion scope limited to the measured workload/JVM/host |

### 18.1. Must Check Correctness Before Comparing Speed

If a mode produces a different checksum, prioritize investigating the code/VM flags, version, and differing state. Do not treat a faster run with a wrong checksum as a “successful optimization.”

### 18.2. Report Effects Using Ratios with Proper Units

If both timed sections measure the same number of operations, the ratio *elapsedMs_Xint / elapsedMs_Xmixed* can be used as the **observed speedup in the sample**. However, report it along with experimental conditions and interval/spread; do not turn a single-run ratio into a general performance claim.

### 18.3. Consider CPU Quota and Thermal Effects

If a container only has 1 vCPU, `-Xmixed` compiler threads compete with the application for CPU. If the CPU quota differs between runs, the experiment no longer maintains equivalent conditions.

### 18.4. If the Goal Is True Speed Comparison, Use JMH

**OpenJDK JMH — Java Microbenchmark Harness** is the appropriate tool for microbenchmarks with warm-up, measurement iterations, forks, and blackholes. The demo in this article helps observe concepts and verify correctness, not replace a benchmark optimized for production decisions.

Reference: https://openjdk.org/projects/code-tools/jmh/

## 19. JMH Extension: What Should Be Checked?

To use JMH for comparing execution modes, you should:

1. Write a benchmark method that returns a result consumed by JMH (or uses `Blackhole`) to avoid DCE.
2. Include `@Warmup` with sufficient time/iterations for the environment.
3. Include `@Measurement` with sufficient runs.
4. Run **separate forks** with `-Xint` and `-Xmixed`.
5. Use the same inputs, JDK build, heap, and CPU quota.
6. Specify **score units** such as operations/second or ns/op.
7. Read variance and error bars.
8. Inspect the JIT compilation profile if you want to explain the cause of speed differences.
9. Do not forget startup and compiler CPU when evaluating real-world applications.

**Do not confuse `ns/op` of an isolated method with p99 request latency** of the entire system.

### 19.1. Be Careful with `-Xint` When Warm-up Is Too Long

In interpreter-only mode, a calculation can be significantly slower. JMH with iteration counts/measurement times designed for JIT mode can take a long time if run in interpreter-only mode. Adjust the benchmark plan for sufficient data, while **keeping comparable operations and clear reporting**.

### 19.2. Why Is Running Two Modes Not Just Changing an Annotation?

Execution mode is a **VM option at process startup time**. With JMH, pass the appropriate JVM args to the forks; do not try to switch `-Xint` and `-Xmixed` mid-flight inside the same running JVM.

## 20. Common Misconceptions

| Misconception | Correct Interpretation |
| --- | --- |
| “`-Xint` disables all native instructions of the JVM.” | It disables JIT for Java bytecode; runtime/native services still exist. |
| “`-Xmixed` compiles every method before main.” | It selects selective JIT for hot paths; cold code can be interpreted. |
| “Producing the same checksum means timing must be the same.” | Correctness is the same, performance can differ. |
| “`-Xint` disables GC.” | GC and heap management still operate. |
| “`-Xmixed` means every method is always both interpreted and compiled.” | A method may only be interpreted, or compiled according to tier/policy. |
| “`-Xcomp` is the most optimal production mode.” | Testing mode; can add large startup/compilation costs. |
| “`-XX:-TieredCompilation` is the same as `-Xint`.” | Tiered off does not mean JIT off. |
| “`TieredStopAtLevel=1` is interpreter-only.” | Level 1 uses C1 compiled code on supporting HotSpot builds. |
| “PrintCompilation always outputs exactly four lines for the demo.” | Compile events depend on runtime/timing; non-deterministic. |
| “Level 4 means exactly four nanoseconds.” | It is a compilation tier, not a unit of time. |
| “`%` means CPU utilization percent.” | In compilation logs, it is usually the OSR marker. |
| “`@ 20` means 20 method calls.” | It is the bytecode index (BCI) in an OSR entry. |
| “800 warm-up calls guarantees steady state.” | There is no such guarantee. |
| “One measurement gives a universal speedup.” | It is only one sample with many confounding variables. |
| “Adding `PrintInlining` does not affect measurement.” | Diagnostic output has overhead/log I/O. |
| “`System.nanoTime` returns pure CPU time.” | It measures elapsed interval, including scheduling delays. |
| “Keeping sink volatile eliminates all compiler optimizations.” | Volatile preserves side effects; JIT still optimizes what it can. |
| “All JIT speedups come from method call overhead.” | Inlining, loop optimizations, branch/type profiles, and many other factors. |
| “A method called once cannot become hot.” | A long loop can trigger OSR via backedge counts. |
| “A CLI benchmark is enough to conclude HTTP server p99.” | Startup, I/O, workload, and concurrency are very different. |

## 21. Self-Check Exercises with Answers

**Question 1.** What is the main difference between `-Xint` and `-Xmixed`?

**Answer:** `-Xint` executes Java bytecode interpreted-only, disabling JIT; `-Xmixed` allows the interpreter and JIT-compiled hot methods to work together.

**Question 2.** Does `-Xint` disable GC, native libraries, and OS system calls?

**Answer:** No. It affects the execution mode of Java bytecode, without removing runtime services.

**Question 3.** Why must the same bytecode running in both modes produce the same checksum?

**Answer:** Java semantics are not altered by whether the VM chooses the interpreter or compiler; the modes are just ways to execute the instructions correctly.

**Question 4.** Is the line `checksum=3215795315003` a timing measurement?

**Answer:** No. It is the logical value of the workload, used to verify correctness.

**Question 5.** Should `elapsedMs` be expected to be the same across all runs?

**Answer:** No. Timing depends on CPU, JIT, GC, scheduling, warm-up, and environment.

**Question 6.** Why is it necessary to start a separate process for each mode?

**Answer:** Because the compiled/profile/cache state of a running JVM cannot simply be reset between two modes; the mode is a VM startup option.

**Question 7.** How does warm-up help `-Xmixed`?

**Answer:** It provides an opportunity for class loading/profiling and JIT compiling hot code before the measured section; it does not guarantee every method is C2-compiled.

**Question 8.** Does warming up `-Xint` cause bytecode to be C2-compiled?

**Answer:** No, because this mode disables JIT compilation for bytecode.

**Question 9.** How do you observe JIT events on HotSpot?

**Answer:** Run separately with `-XX:+PrintCompilation`; look for the demo's class/method and compilation levels/OSR markers.

**Question 10.** If `PrintCompilation` prints levels 3 and 4, what does that usually indicate?

**Answer:** C1 full-profiling compilation and C2 optimized compilation in the HotSpot tiered model, respectively.

**Question 11.** What does `%` in the log usually mean?

**Answer:** OSR compilation for a bytecode point inside a loop.

**Question 12.** Why not measure `elapsedMs` while thousands of `PrintCompilation` lines are enabled?

**Answer:** Logging/I/O changes execution conditions and can introduce latency noise.

**Question 13.** Does `-Xcomp` mean “every method is level 4”?

**Answer:** No. It prioritizes compilation as a testing mode but does not guarantee a specific optimization tier.

**Question 14.** Does `-XX:-TieredCompilation` completely disable JIT?

**Answer:** Not necessarily. It disables the tiered policy, which differs from interpreter-only.

**Question 15.** For an I/O-heavy workload, is `-Xmixed` guaranteed to be many times faster than `-Xint`?

**Answer:** No. If time is mostly spent waiting on I/O, the benefit of bytecode optimization may be small relative to end-to-end latency.

**Question 16.** Why might the code in `mix` no longer be a separate native call on each iteration?

**Answer:** The JIT can inline `mix` into the caller's loop.

**Question 17.** Why use `System.nanoTime` instead of `System.currentTimeMillis` for short measurement intervals?

**Answer:** `nanoTime` is designed for measuring elapsed durations; `currentTimeMillis` is a wall-clock whose resolution/adjustments are less suitable for microtiming.

**Question 18.** Why report median/spread instead of taking the fastest run?

**Answer:** The min value can be skewed by lucky scheduling/cache; the distribution helps understand variance and outliers.

**Question 19.** If the checksum differs between modes, can you conclude JIT is faster?

**Answer:** No. You must verify the program/environment/correctness before interpreting performance.

**Question 20.** Which tool is more suitable than a hand-written `nanoTime` demo for serious microbenchmarking?

**Answer:** OpenJDK JMH, with forks, warm-up, measurement, and blackholes.

## 22. Practical Experiment Checklist

1. Fix the same `ExecutionModeDemo.java` file and compile once with `javac --release 17`.
2. Record `java -version` and `javac -version`.
3. Use `-Xint` and `-Xmixed` in **two independent processes**.
4. Keep warm-up calls, measured calls, and steps per call equal.
5. Verify the five deterministic stdout lines and checksum before measuring timing.
6. Record `elapsedMs` for each run, do not take a single run as a rule.
7. Repeat multiple runs and alternate execution mode order.
8. Measure whole-process startup separately when that is the goal.
9. Record CPU/container quotas if applicable.
10. Run `PrintCompilation` separately to observe interpreter vs C1/C2/OSR.
11. Do not apply fixed compile event counts or C2 thresholds to every HotSpot build.
12. Do not lump `-Xint`, `-Xcomp`, and tiered-off into a single concept.
13. Do not enable extra heap/GC/JIT tuning flags without a clear hypothesis.
14. Avoid output I/O inside timed computation.
15. Use JMH if results need to inform production performance decisions.
16. Read profiler/JFR/JIT logs when explaining the causes of differences.
17. Keep code compliant with Java semantics; do not write code relying on timing races/undefined assumptions.
18. Disclose experiment limitations: CPU, JVM, build, number of runs, warm-up, inputs.

### Summary

```text
                  SAME JAVA BYTECODE
                          |
                +---------+----------+
                |                    |
              -Xint               -Xmixed
                |                    |
        Interpreter only    Interpreter + selective JIT
                |                 /        \
         No C1/C2 for       Cold paths    Hot paths
         Java bytecode     interpreted   C1/C2 / OSR
                |                    |
                +----------+---------+
                           |
                 SAME LOGICAL RESULTS
                           |
                Different elapsed time,
                compiler CPU, warm-up
                           |
            Measure multiple isolated runs
            Check correctness before timing
```

**Core takeaway:** `-Xint` is a useful control for understanding the cost of interpreted execution, while `-Xmixed` lets HotSpot **interpret cold code and JIT-compile hot code when beneficial**. A proper experiment must keep the same bytecode/input/JVM conditions, distinguish **fixed logical stdout** from **variable timing**, measure multiple times, and use compiler logs to confirm JIT events. Speed measured on one machine does not become a Java guarantee.

### References

- [Oracle JDK 17 — `java` command, `-Xint`, `-Xmixed`, `-Xcomp` modes](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): definitions of interpreter-only, mixed (default), and testing compilation mode.
- [OpenJDK — `java` command source documentation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): HotSpot options with explanatory descriptions.
- [Microsoft OpenJDK Engineering — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): C1/C2 profiling, compilation levels, and caveats regarding `-Xint`/`-Xcomp`.
- [Oracle — HotSpot Compilation Optimization](https://docs.oracle.com/javacomponents/jrockit-hotspot/migration-guide/comp-opt.htm): interpreter/JIT and tiered compilation from a runtime perspective.
- [OpenJDK — Compiler configuration/source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compiler_globals.hpp): flags related to compiler and tiered policy, version-dependent.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): benchmarks with warm-up, forks, instrumentation, and statistics.
- [JVMS `2` — The Structure of the Java Virtual Machine (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): Java execution semantics do not require all JVMs to use HotSpot C1/C2.
