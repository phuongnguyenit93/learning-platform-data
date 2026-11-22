# Java Benchmarking: Avoiding Constant Folding and Dead-Code Elimination

A Java operation running in "0 ns" or faster than reading a variable does not necessarily mean the algorithm was brilliantly optimized. Sometimes the JVM has proven **the output is always a constant** and replaced the entire calculation with a precomputed value (*constant folding*), or proven **the result affects nothing observable** and eliminated the calculation (*dead-code elimination*, DCE). If the goal is to measure the cost of a calculation actually used by the application, these two legal JVM optimizations can cause the benchmark to measure the wrong thing.

This lesson belongs to the **Performance** topic in Java Core - Numbers. The goal is to understand when numeric benchmarks get optimized away by the JVM, how to design inputs and outputs to measure the real work, how to use **Java Microbenchmark Harness (JMH)**, and how to interpret results cautiously. The lesson uses Java 17+ syntax and also explains cases where code "runs correctly" yet the measurement no longer represents a real workload.

## 1. What Does a Benchmark Measure?

A *microbenchmark* isolates a small operation, such as `long` multiplication, a number conversion method, `BigDecimal.add()`, or a condition check. Its goal is to estimate cost and/or throughput once the JVM executes the code in the corresponding context.

A measurement is meaningful only when you can answer:

1. **What task is measured:** exactly which method and which inputs?
2. **Is the result used?** In the real application, does the calculation affect a return value, stored data, or observable state?
3. **How much do inputs vary?** Is it a constant in bytecode, a `final` field, a state field assigned at runtime, or realistic data?
4. **Is anything else being measured?** Object creation, I/O reads, allocation, library initialization, data conversion, and method dispatch may be mixed into the computation time.
5. **Has the JIT warmed up?** The JVM can interpret and optimize-compile the same method across different phases; initial runs rarely represent steady state.
6. **Measurement overhead and execution conditions:** are there independent JVM forks, warmup, measurement intervals, GC, CPU contention, and proper statistical handling?

The reported unit `ns/op` means **nanoseconds per benchmark operation** under the harness configuration. It does not prove that the clock has single-nanosecond resolution or that an equivalent operation will take that exact time in every application.

## 2. What Is the JVM Allowed to Optimize?

Java allows the compiler/JIT to perform transformations that preserve the **observable behavior** of the program. For pure calculations without side effects, eliminating them or replacing them with a constant is legal when doing so does not change any observable output.

Simplified model:

~~~text
Java source
    |
    v
javac produces bytecode
    |
    v
JVM interprets / JIT-compiles hot paths
    |
    +--> constant propagation / constant folding
    +--> inline method / hoist loop-invariant work
    +--> dead-code elimination / escape analysis
    |
    v
Machine code is executed
~~~

This is a conceptual diagram; where and how much optimization occurs varies across JVMs, versions, workloads, and execution profiles. `javac` can fold certain constant expressions at compile time, while the JIT can optimize after gathering information about actual calls.

**A benchmark needs to measure code *after optimization*** because that is what the real application runs. You do not try to "disable all optimizations". You need to construct an input and output context **true to the real scenario**, so the JIT does not eliminate the very work the benchmark assumes it is measuring.

## 3. Constant Folding: When the Entire Calculation Becomes a Constant

*Constant folding* happens when the compiler knows the operands and can determine the result ahead of time, for example:

~~~java
int result = 12 * 12; // Result 144 may be precomputed.
~~~

For benchmarks, the dangerous scenario is passing all inputs as constants:

~~~java
static long compute(long x) {
    long result = x;
    for (int i = 0; i < 8; i++) {
        result = (result * 31 + i) ^ (result >>> 3);
    }
    return result;
}

// Calculation with fixed input:
long result = compute(7L);
~~~

If the JIT inlines `compute` and deduces that the loop and `x = 7L` are invariant, it **can** precompute or fold away most of the work. Having many multiplications, additions, and XORs in source code does not guarantee the corresponding machine instructions actually run in each measured iteration.

Note three levels:

- **Constant folding:** simplifying an expression when inputs are known.
- **Constant propagation:** propagating known constant values through variables or calls, creating folding opportunities.
- **Loop-invariant code motion:** hoisting an invariant computation outside a loop when legal; a hand-rolled benchmark repeating the same calculation may execute the work only once.

Some optimizations can occur right inside `javac`, while others are decided by the JIT. You should not say the JVM **always** folds every pure function into a constant; whether it does depends on program structure, inlining eligibility, runtime conditions, and the compiler. The benchmark risk is that **the JVM is allowed and may have the opportunity to do so**, so an ultra-fast result alone is not proof that the computation ran as expected.

## 4. Dead-Code Elimination: Computed, Yet Nobody Uses It

*Dead-code elimination* (DCE) removes operations whose results are never observed by the program. For example:

~~~java
static long compute(long x) {
    return (x * 31 + 17) ^ (x >>> 3);
}

static void wrongBenchmark(long input) {
    compute(input); // Result discarded; no side effect.
}
~~~

The snippet above is an illustration, **not a complete program**. If `compute` is inlined, the JVM can recognize that the calculation changes no observable state and remove it entirely. The benchmark may end up measuring mostly harness overhead or leftover transformations rather than the operation's cost.

Key insight: **varying inputs are not enough** if the output is discarded. Conversely, **using the output is not enough** if the entire computation can be replaced with a constant result. A good benchmark must guard both ends:

~~~text
Realistic input data, not treated as constant by compiler
                        |
                        v
                  Measured work
                        |
                        v
Result used/consumed in a way observable by harness
~~~

Do not fix this by adding `System.out.println(result)` **inside the benchmark loop itself**: console I/O is far more expensive and variable than arithmetic operations, turning the measurement into a log-printing benchmark. Do not use `Thread.sleep()` to make timings "visible": that measures waiting and the OS scheduler, not the computation.

## 5. Both Mistakes Can Happen Together

Consider a manual benchmark:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    long result = compute(7L);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

The code may report a tiny number or swing erratically even though one million iterations appear in the source:

- `result` is unused; the JVM can eliminate calling `compute`.
- The input `7L` is fixed; the compiler can fold or hoist the work outside the loop.
- Self-timing with `nanoTime()` lacks controlled warmup/forks and suffers from JIT/GC/OS scheduling noise; timing overhead can be substantial relative to small operations.
- If you switch to accumulating results in a variable used at the end, the JIT can still transform the repeated calculation, and for tiny operations the loop/accumulator itself becomes most of the cost.
- If you print the result on every iteration, I/O cost overwhelms the computation.

Do not conclude "Java multiplication takes 0 ns" from such a measurement. It is quite possible **the multiplication is no longer in the executed machine code being measured**.

## 6. JMH: A Harness Built for JVM Microbenchmarks

**Java Microbenchmark Harness (JMH)** is an OpenJDK project designed for writing and running microbenchmarks on the JVM, supporting warmup, measurement iterations, JVM forks, measurement modes, and result-consumption mechanisms. For small Java performance benchmarks, it is a much more reliable starting point than a hand-written `nanoTime()` loop.

JMH helps control measurement conditions, yet **cannot know what business logic you intend to measure**. If the author supplies constant inputs, discards results, or measures the wrong task, JMH will still run that benchmark and return valid measurements for the code *that actually ran*. Workload design remains the benchmark author's responsibility.

To get standard annotation processing and packaging configured, use the JMH Maven archetype to create an isolated project. Example using JMH 1.37:

~~~bash
mvn archetype:generate -B -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=example.bench -DartifactId=jmh-demo -Dversion=1.0-SNAPSHOT
cd jmh-demo
~~~

The command requires Maven and access to download dependencies if not already cached. The generated project contains `pom.xml`, sample code, and JMH configuration. The following examples go in `src/main/java/example/bench/`. Version `1.37` is a version verified in Maven Central; when a project has its own dependency version management process, use an appropriate version tested in the project's environment.

Do not call `@Benchmark` like an ordinary method and wrap `System.nanoTime()` around it yourself; doing so bypasses the harness features.

## 7. Complete JMH Example: Keeping Runtime Inputs and Using Results

Create `src/main/java/example/bench/ComputeBench.java` in the archetype project:

~~~java
package example.bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ComputeBench {

    @Param({"7", "11", "19"})
    public long input;

    private static long compute(long x) {
        for (int i = 0; i < 8; i++) {
            x = (x * 31 + i) ^ (x >>> 3);
        }
        return x;
    }

    @Benchmark
    public long resultReturned() {
        return compute(input);
    }

    @Benchmark
    public void resultConsumed(Blackhole blackhole) {
        blackhole.consume(compute(input));
    }
}
~~~

Compile/package with Maven inside the project directory:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar ComputeBench -t 1
~~~

**Explanation of anti-bad-benchmark safeguards:**

1. `@State(Scope.Thread)` provides one state instance per benchmark thread. We measure against a JMH-managed object, rather than relying on a local variable that the compiler could immediately recognize as constant.
2. `@Param({"7", "11", "19"})` instructs JMH to run parameterized cases. The `input` field is not declared `final` and is assigned by the harness at runtime. This avoids passing the same literal directly into an expression that can fold to a constant. If the real application only ever has a few constants and the JIT is genuinely allowed to fold them, that benchmark needs a different goal rather than artificially "blocking the JIT" out of context.
3. `resultReturned()` returns the result from `@Benchmark`. JMH **consumes the return value** to prevent DCE; returning a different value or a dummy constant instead of the real result defeats the goal.
4. `resultConsumed(Blackhole)` demonstrates passing results directly into `Blackhole.consume(...)` when the benchmark method must return `void` or produces multiple intermediate results. JMH uses this mechanism to prevent the compiler from treating the output as unneeded.
5. `@Warmup` and `@Measurement` separate the optimization warmup phase from the data-collection phase; `@Fork(2)` runs two independent JVM forks to reduce dependence on a single run's state.
6. `@BenchmarkMode(Mode.AverageTime)` with `@OutputTimeUnit(NANOSECONDS)` asks JMH to report average time per operation. This is **not** a promise that every individual call's latency is an exact fixed number of nanoseconds.

The two methods use two different ways of retaining the result; they are **not expected to produce digit-for-digit identical measurements**, because result-consumption/harness paths have different overhead and optimization traits. The lesson's goal is designing a measurement that does not accidentally drop all the work. Timing results depend on CPU, JVM, environment, and run; **no fabricated `ns/op` table is provided**.

If the Maven build reports `org.openjdk.jmh.generated` not found or benchmarks are not registered, check the JMH annotation processor in the archetype/build config. Merely copying `ComputeBench` into a regular Java program and calling `main` is not enough for JMH to run properly.

## 8. Distinguishing Wrong Examples from Right Examples

The following snippets **illustrate the issue**, not standalone JMH benchmarks to run for drawing performance conclusions.

### Wrong A: using a constant input

~~~java
@Benchmark
public long foldable() {
    return compute(7L);
}
~~~

Even though the result is returned to the harness, the JIT can still inline and constant-fold `compute(7L)`. The output is used, **yet the work meant to be measured may have been folded away**. Compare this to the right example `compute(input)` where `input` is a runtime state field.

### Wrong B: discarding the result

~~~java
@Benchmark
public void unused() {
    compute(input);
}
~~~

Even though `input` comes from runtime state, a pure computation has no observable effect when the result is discarded. DCE can remove it. Compare this to the right example `return compute(input)` or `blackhole.consume(compute(input))`.

### Wrong C: creating a constant with `final`

~~~java
private static final long FIXED = 7L;

@Benchmark
public long foldedConstant() {
    return compute(FIXED);
}
~~~

Declaring `final` is usually good practice in application code; however, when the benchmark goal is **computing with varying data**, `static final` and literals invite folding. Do not "ban `final`" everywhere; distinguish benchmark data that must be dynamic from parameters that are genuinely fixed by the application contract.

### Right for measuring runtime data

~~~java
@State(Scope.Thread)
public static class Inputs {
    @Param({"7", "11", "19"})
    public long value;
}

@Benchmark
public long runtimeInput(Inputs inputs) {
    return compute(inputs.value);
}
~~~

This snippet needs to reside inside a benchmark class with `compute` and the corresponding JMH imports. `@Param`/`@State` do not absolutely guarantee every single operation survives in machine code; they help the benchmark reflect runtime-supplied data and reduce the risk of constant folding. Inspecting generated machine code when a measurement is suspiciously tiny or abnormal remains valuable.

## 9. Standalone Java 17 Program for Functional Verification, Not Performance Measurement

Before measuring time, prove that the calculation function **truly depends on its input** and verify what the expected outputs are. Simple example without JMH dependencies:

Create `BenchmarkPitfallsDemo.java`:

~~~java
public final class BenchmarkPitfallsDemo {
    private static volatile long sink;

    static long compute(long x) {
        for (int i = 0; i < 8; i++) {
            x = (x * 31 + i) ^ (x >>> 3);
        }
        return x;
    }

    public static void main(String[] args) {
        long a = compute(7);
        long b = compute(11);
        sink = a;
        System.out.println("a = " + a);
        System.out.println("b = " + b);
        System.out.println("different results = " + (a != b));
        System.out.println("sink = " + sink);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 BenchmarkPitfallsDemo.java
java BenchmarkPitfallsDemo
~~~

Deterministic output for the illustrative values:

~~~text
a = 5985353341353
b = 9465354105287
different results = true
sink = 5985353341353
~~~

The program proves `compute` yields two different results for two inputs; the `volatile sink` variable demonstrates one way of consuming a result observably. **This is not a timing benchmark.** Adding `volatile` does not replace JMH's warmup, forks, statistics, and safeguards against out-of-context compiler optimizations. If you wrap a timing loop around this program, you still have to analyze optimizations and `volatile` access costs separately.

## 10. `Blackhole`: Consuming Results Properly

JMH provides `org.openjdk.jmh.infra.Blackhole`. You can use:

~~~java
@Benchmark
public void benchmark(Blackhole blackhole) {
    long value = compute(input);
    blackhole.consume(value);
}
~~~

If the benchmark is `public long benchmark()`, simply writing `return compute(input)` is usually enough: JMH handles the return value. `Blackhole` is more useful when a single iteration computes multiple results or the benchmarked operation has no convenient return type.

**Do not call `Blackhole.consumeCPU(...)` just to ensure the CPU does work**: that method is meant for simulating artificial CPU load in specific experiments; it does not prove the work you wanted to measure ran, and it adds cost outside the workload.

**Do not invent a static `volatile` variable as a universal solution.** Volatile writes carry cost, memory effects, and contention when multiple threads share it. They can skew the comparison between two algorithms by the extra overhead added by the benchmark itself.

**Do not print results inside `@Benchmark`** and avoid updating a shared `List`/`Map` merely to retain results if the real application does not do that. Faking "observable use" can end up measuring unrelated allocation, synchronization, and contention. Prefer `return` or `Blackhole` first, then verify the JVM did not eliminate or transform the critical part.

## 11. `@State`, `@Param`, and Realistic Input Data

A trustworthy benchmark must reflect the application's **input distribution**, not just a single convenient constant.

`@Param` lets you report multiple cases, such as small, large, negative, and near-boundary integers. For numeric problems, runtime can depend on digit counts or internal representation size, especially with `BigInteger` and `BigDecimal`. Measuring a special object like `BigInteger.ONE` and generalizing performance to thousands of digits is unfounded.

`@State(Scope.Thread)` creates dedicated state per benchmark thread; `Scope.Benchmark` creates benchmark-wide shared state per JMH's contract, suitable if you **genuinely want to measure contention**. If your goal is single-threaded computation speed, accidentally using shared mutable state can make you measure contention instead of the algorithm.

For complex numeric data, you can use `@Setup(Level.Trial)` to prepare data outside the measurement path:

~~~java
@State(Scope.Thread)
public static class DecimalInputs {
    @Param({"16", "128"})
    public int digits;

    public java.math.BigInteger value;

    @Setup(Level.Trial)
    public void setup() {
        value = java.math.BigInteger.TEN.pow(digits)
                .add(java.math.BigInteger.valueOf(12345));
    }
}
~~~

This snippet requires JMH imports `@State`, `Scope`, `@Param`, `@Setup`, and `Level`. Do not construct a large `BigInteger` inside every `@Benchmark` call if the goal is **only measuring the operation on pre-existing numbers**; conversely, if the real application must parse/convert numbers on every task, including that step makes sense. State the measurement scope in the benchmark name and explanation.

Do not turn all inputs into `final static` to reduce noise when you need performance on runtime data. And do not update a parameter with an artificial pattern on every invocation if updating the parameter itself will dominate the tiny operation being measured.

## 12. Warmup, Forks, and Measurement Modes

When running Java, the JVM may go through interpretation, tiered compilation, profile collection, inlining, cache warming, class loading, and GC. Timing the first few calls and dividing gives results heavily dependent on startup state.

Important JMH settings:

| Setting | Meaning |
|---|---|
| `@Warmup(iterations = 3, time = 1)` | Runs warmup intervals excluded from final results |
| `@Measurement(iterations = 5, time = 1)` | Collects 5 measurement intervals per fork |
| `@Fork(2)` | Runs two independent JVM forks |
| `@BenchmarkMode(Mode.AverageTime)` | Reports average time per operation |
| `@BenchmarkMode(Mode.Throughput)` | Reports operations per unit of time |
| `@OutputTimeUnit(TimeUnit.NANOSECONDS)` | Specifies reporting unit |
| `-t 1` | Runs one benchmark thread, avoiding mixing contention into single-threaded measurements |

An example JMH command after building can override annotation settings:

~~~bash
java -jar target/benchmarks.jar ComputeBench -wi 3 -i 5 -w 1s -r 1s -f 2 -t 1
~~~

These options select 3 warmup iterations, 5 measurement iterations, one second per interval, two forks, and one thread. CPU conditions, temperature, OS, power plan, and competing workloads can all affect measurements.

JMH output typically shows benchmark name, sample count, mode, score, error, and units. `Score Error` is an uncertainty indicator calculated by the harness; **it does not mean all measurements in a real-world application will fall within that exact interval**. When differences are smaller than noise or system-dependent, do not declare a performance victory from a single benchmark run.

## 13. Other Optimizations That Also Skew Benchmark Goals

Constant folding and DCE are two prominent examples, yet Java microbenchmarks also encounter:

- **Inlining:** the JIT replaces a method call with the method body. This is a real optimization to account for; if a benchmark tries to measure "call overhead", verify whether the application actually fails to inline it.
- **Escape analysis and scalar replacement:** an object that is created without "escaping" can have its allocation eliminated or replaced by scalar fields by the JVM. If measuring real allocation, ensure object lifetimes/escapes match the application, without artificially retaining objects out of context.
- **Loop unrolling and loop-invariant hoisting:** a loop repeating the same input can be unrolled or have computations hoisted out. JMH normally manages the inner loop, so avoid adding a large `for` loop inside a benchmark unless genuinely measuring a batch.
- **Profile-guided/speculative optimization:** the JVM optimizes for commonly observed types/branches; overly uniform benchmark inputs can make branch prediction and inlining far more favorable than real workloads.
- **Allocation and GC:** benchmarks creating new arrays or `BigDecimal` instances may show uneven garbage collection costs across runs. Choose whether to measure allocation too or only processing of existing data.
- **Cache locality and memory layout:** tiny datasets that always stay in cache can yield vastly different results from large inputs on real machines.
- **Autoboxing:** measuring `Long`/`Integer` when the application uses primitives, or vice versa, injects unwanted costs.

These optimizations are **not bad**. They skew benchmarks when data setup or result usage differs from the measurement target. The goal is a measurement faithful to the workload, not fighting the compiler at all costs.

## 14. Numbers Example: Measuring `BigDecimal` at the Right Scope

Suppose you need to compare the cost of `BigDecimal.add()` and `BigDecimal.multiply()`. Creating both objects from strings inside each `@Benchmark` will make the timing include **decimal parsing + allocation + arithmetic**, unlike a scenario where the application already holds the data.

Suggested design:

~~~java
@State(Scope.Thread)
public static class NumberState {
    @Param({"12.345", "123456789.012345"})
    public String text;

    public BigDecimal left;
    public BigDecimal right;

    @Setup(Level.Trial)
    public void setup() {
        left = new BigDecimal(text);
        right = new BigDecimal("7.8901");
    }
}

@Benchmark
public BigDecimal add(NumberState state) {
    return state.left.add(state.right);
}

@Benchmark
public BigDecimal multiply(NumberState state) {
    return state.left.multiply(state.right);
}
~~~

This is an **illustrative snippet to place inside a JMH class** with `BigDecimal`, JMH annotations, and `Level` imports; it is not a directly runnable Java file. Outside the measurement path, `@Setup(Level.Trial)` constructs the data so the benchmark reflects operations on existing `BigDecimal` instances. The `BigDecimal` result is returned and consumed by JMH, preventing DCE from deleting the operation.

However, pre-selecting fixed `left/right` values can still let the JIT exploit data/operation specifics depending on code structure; it does not automatically prove the benchmark covers all real values. To measure distributions of large/small, positive/negative, or varying `scale` inputs, use multiple cases and data varying realistically per business rules. When comparing processors, always verify the operation actually computes rather than being "returned from cache" due to a special input property.

## 15. Checklist for Evaluating a Microbenchmark

Before trusting performance conclusions, check item by item:

1. **Define the operation:** are you measuring a pure function, parsing, initialization, I/O, synchronization, or an entire workflow?
2. **Prevent inappropriate constant folding:** does real application data vary? If so, do benchmark parameters come from runtime state (e.g., `@Param`) rather than literals or `static final`?
3. **Prevent DCE:** is the measured work's result returned via `return` or `Blackhole.consume` in JMH? Are there realistic side effects?
4. **Keep extraneous costs out of the measurement path:** are console printing, sleeping, test-fixture allocation, RNG creation, unnecessary parsing, or global `volatile` updates taking up time?
5. **Use JMH properly:** annotation processor works, benchmark runs through the harness, and warmup, measurement, and forks are configured appropriately.
6. **Ensure functional correctness:** computed results on inputs can be verified; a logically wrong yet super-fast benchmark has no value.
7. **Examine machine optimizations:** for suspiciously fast/abnormal timings, inspect profiling/disassembly if the environment supports it to understand generated machine code and how much work was eliminated; do not guess from `ns/op` alone.
8. **Control noise sources:** JVM/JDK version, CPU, GC, system load, concurrency level, and thermal/power conditions must be recorded.
9. **Do not mistake short-term variance for improvement:** re-run when justified, examine error margins and scope of applicability; report results with conditions instead of generalizing one absolute number to every machine.
10. **Compare fairly:** both approaches must share the same inputs, same correctness criteria, and same included costs. Do not let one side do less work simply because the benchmark forgot to consume its result.

There is no single "anti-optimizer trick" sufficient for every benchmark. `Blackhole` helps curb DCE, `@State`/`@Param` help supply runtime inputs, and **experimental design** determines whether the benchmark represents the problem.

## 16. Prediction and Debugging Exercises

**Exercise 1 — Discarded result.** What is wrong with the method below?

~~~java
@Benchmark
public void test() {
    expensivePureCalculation(input);
}
~~~

**Answer:** If the method has no side effects, the output is discarded so the JVM can apply DCE. Change it to return the result or pass the result into `Blackhole.consume`. Also check that `input` is not an unintended constant.

**Exercise 2 — Returning a value can still be wrong.**

~~~java
@Benchmark
public long test() {
    return compute(123L);
}
~~~

**Answer:** Returning the result prevents DCE, yet the fixed `123L` enables constant folding, inlining, and hoisting. If the application processes varying runtime numbers, use `@State` and `@Param` or equivalent runtime data.

**Exercise 3 — Is using `volatile` enough?** A developer replaces `Blackhole` with `private static volatile long sink;`, then writes `sink = compute(7L);` after each call. Is it safe for comparing performance yet?

**Answer:** Not yet. A calculation with a literal can still constant-fold; the volatile write becomes a significant part of the cost. You need JMH, runtime inputs, and context-appropriate result consumption.

**Exercise 4 — When is a fixed input valid?** The real application always calls `compute(7L)` and the JIT genuinely turns it into a constant. Should you force the benchmark to execute eight loop iterations?

**Answer:** If the goal is measuring **the real cost of that exact call site**, letting the JIT optimize under real conditions can be the reasonable choice. Only when you want to measure the algorithm with varying inputs should you design runtime state to prevent folding. A benchmark must reflect requirements, not mechanically "block every optimization".

**Exercise 5 — A `0.001 ns/op` result.** A complex multiplication is reported at an unbelievable speed. What should you do before advertising this as a superior optimization?

**Answer:** Check whether the result is consumed, whether inputs can constant-fold, whether the benchmark batches loops so the `op` unit is divided incorrectly, whether it ran properly via JMH, and if needed inspect machine/JIT code. Never conclude an algorithm is fast from an anomalous timing without verifying what was actually measured.

## 17. Key Takeaways and References

- **Constant folding:** if data/expressions are sufficiently determined, the JVM can replace the calculation with a precomputed result. For benchmarks needing to measure runtime data, use non-`final` state fields, `@Param`, and scenarios with representative input distributions.
- **Dead-code elimination:** if the result is unused, the JVM can drop a pure calculation altogether. In JMH, `return` the result or call `Blackhole.consume(...)`.
- **The two conditions are independent:** using the result does not automatically prevent folding; using runtime inputs does not automatically prevent DCE.
- **JMH provides the harness**, warmup, forks, measurement, and result handling; the author must still choose the right work, data, and observation method.
- **Evaluate results according to the workload contract and machine conditions**, without extrapolating an absolute rule from a single `ns/op` number.

Official docs and examples worth reading:
- [OpenJDK JMH](https://github.com/openjdk/jmh): project, Maven archetype setup, running microbenchmarks.
- [JMHSample_08_DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): comparing a benchmark that discards results with one that returns results.
- [JMHSample_09_Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java): using `Blackhole` when results must be consumed.
- [JMHSample_10_ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): `final` inputs, constant folding, and data in runtime state fields.
- [JMH Core on Maven Central](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core): published dependency versions.
