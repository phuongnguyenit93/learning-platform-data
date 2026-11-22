# Measuring Numeric Computation Performance with Realistic Data Domains and Edge Cases in Java

## 1. Quick Timing on a Few Clean Numbers Does Not Reflect Real Performance

Suppose there are two ways to add, divide, or normalize numbers in Java. One approach may look faster when tested on 100 small integers or a few short decimal values. That conclusion can reverse when real-world data includes many digits, widely differing scales, negative numbers, zeros, or a high exception rate.

Therefore, meaningful performance measurement requires **both**:

1. **A representative data domain:** input sizes, value distributions, precision/scale, operation frequencies, and typical input ratios must closely match the workload being optimized.
2. **Edge cases:** boundary inputs can make algorithms switch branches, overflow, allocate far more memory, throw exceptions, or run with completely different complexity.

This lesson focuses on how to design, verify, and interpret measurements for `int`, `long`, `double`, `BigInteger`, `BigDecimal`, and related aggregation operations. The goal is choosing an implementation that **meets arithmetic requirements** and **is fast enough under real load**, rather than picking code that is only fast in a tiny toy test.

Three questions must be answered before benchmarking:

- **Which operation is being measured?** For example, parsing strings into `BigDecimal`, adding pre-built `BigDecimal` instances, multiplying `BigInteger`, summing an `IntStream`, or formatting outputs.
- **What do real inputs look like?** How many elements per call? How many digits? Are there negative numbers, zeros, very large numbers, mixed scales, or malformed inputs?
- **What defines correctness?** Must results be absolutely exact, rounded under which rule, allowed to overflow, and how are invalid inputs handled?

You cannot compare two calculations solely because they return a number that looks similar. For instance, replacing `BigDecimal` with `double` may be faster yet breaks decimal exactness required for money. That is a **semantic change**, not merely an optimization.

## 2. Building a Data Profile Before Measuring

A benchmark may accurately measure the runtime of the data it receives, yet still answer the wrong question if that data does not represent real production.

For example, a transaction-processing service receiving monetary amounts as strings:

- Most amounts have two decimal places and fall within ordinary bounds.
- A small percentage are zero, negative (refunds), very large, or have many fractional digits.
- Some lines are malformed input and must be rejected.
- Transaction volume per batch may be 1, 100, 10,000, or more.

If you only measure `new BigDecimal("1.00").add(new BigDecimal("2.00"))` in a loop, you have omitted parsing, memory, element counts, scale, extreme values, and batch characteristics.

### 2.1. Representative data matrix

| Data axis | What to record | Why it affects performance |
|---|---|---|
| Dataset size | 0, 1, tens, thousands, millions; realistic distribution | Pipeline startup cost, loops, caches, allocation, and GC |
| Integer magnitude | Small values, near `Integer.MAX_VALUE`/`Long.MAX_VALUE`, very long `BigInteger` | Overflow, internal limb counts, multiplication/division algorithms |
| `BigDecimal.precision()` | Few digits, many digits, valid extreme lengths | Operation and formatting costs change |
| `BigDecimal.scale()` | Scale 0, 2, negative, large, scale differences | Addition may require scale alignment; `setScale`/`divide` need extra work |
| Sign and value | Positive, negative, 0, near 0, alternating signs | Branching, cancellation, rounding rules |
| Operation | Add, multiply, divide, round, parse, format | Each operation has its own complexity and allocation pattern |
| Input form | Strings, primitive arrays, wrapper collections | Parsing, boxing/unboxing, and conversion costs |
| Access pattern | Sequential, parallel, many concurrent requests | CPU, cache, allocator, and GC contention |

The **typical set** and **edge-case set** should be two separate result groups. A rare extreme case can be recorded, yet should not be conflated with the average latency of all requests. At the same time, an edge case may be a formal requirement, such as a maximum latency threshold or overload guard; in that case it needs its own criteria.

### 2.2. Distribution matters more than averages

Suppose one million requests have 99% 6-digit `BigDecimal` inputs and 1% thousand-digit numbers. Taking the average length and benchmarking only one value of average length **is not equivalent** to benchmarking the real mixture: multiplication/division time and memory allocation can grow nonlinearly with digit count.

Good practice:

1. Separate **buckets** by size: e.g., 1–9, 10–99, 100–999, and 1000+ digits (merely an example; boundaries must match real data).
2. Measure each bucket to learn the cost of each input class.
3. Measure a **weighted mixed workload matching real proportions** to estimate typical load.
4. Measure worst cases separately if an SLO threshold or safety limit must be met.

When production sources contain sensitive data, generate synthetic data with the **same statistical characteristics**; do not copy raw personal information or sensitive values into benchmarks.

## 3. Edge-Case Suites by Numeric Type

Boundary categories must derive from the numeric domains and operations actually used.

### 3.1. `int` and `long`: checking bounds and overflow

~~~java
int maxInt = Integer.MAX_VALUE;            // 2147483647
long beyondInt = (long) maxInt + 1;        // 2147483648

int overflow = maxInt + 1;                 // -2147483648 (wrap)
~~~

At minimum, test `0`, `1`, `-1`, `MIN_VALUE`, `MAX_VALUE`, and addition/multiplication combinations near thresholds. When using `Math.addExact` or `Math.multiplyExact`, test both the success path and the `ArithmeticException`-throwing path.

**Compare two approaches only when semantics match**: racing wrapping `int` addition against `Math.addExact` is not an equivalent race if the business logic requires overflow detection. In real systems, the exception-throwing path can carry substantial cost, yet checks must never be dropped solely because they are slower.

### 3.2. `double`: precision, `NaN`, `Infinity`, and magnitude

~~~java
double[] sample = {
        0.0, -0.0, 0.1, -0.1,
        Double.MIN_VALUE,
        Double.MIN_NORMAL,
        Double.MAX_VALUE,
        Double.NaN,
        Double.POSITIVE_INFINITY,
        Double.NEGATIVE_INFINITY
};
~~~

Test numbers near 0, subnormals, very large numbers, canceling values, and cases producing `Infinity`/`NaN`. `Double.MIN_VALUE` is the smallest positive nonzero subnormal number, **not** the most negative value in magnitude; remember `-Double.MAX_VALUE` when you need the extreme finite negative value.

A `double` sum depends on calculation order because floating-point addition is not strictly associative. Running in parallel or using compensated summation can yield slightly different results; define an appropriate tolerance instead of checking every result with `==`. For `NaN`, comparisons typically require `Double.isNaN(...)`.

### 3.3. `BigInteger`: digit counts and specific operations

~~~java
BigInteger small = BigInteger.valueOf(7);
BigInteger large = BigInteger.TEN.pow(1000);
BigInteger boundary = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
~~~

Test differing operand lengths (e.g., 1, 20, 100, 1000 digits), negative/positive signs, zero, and combinations where operands differ sharply in length. Multiplication and division costs can change with number size, and even with the internal algorithm chosen by the JVM. Benchmarking addition on small `BigInteger` instances and extrapolating to multiplication of thousand-digit numbers is unfounded.

**Note:** `BigInteger.TEN.pow(1000)` produces `10^1000`, which has 1001 decimal digits. When generating data by digit count to measure, distinguish "power of 1000" from "having exactly 1000 digits".

### 3.4. `BigDecimal`: precision, scale, rounding, and formatting

~~~java
BigDecimal[] values = {
        new BigDecimal("0"),
        new BigDecimal("0.00"),
        new BigDecimal("-0.005"),
        new BigDecimal("1.00"),
        new BigDecimal("1E+8"),
        new BigDecimal("0.00000001"),
        new BigDecimal("999999999999999999.99")
};
~~~

Objects equal in arithmetic value can have **different scales**. For example, `new BigDecimal("1.0")` and `new BigDecimal("1.00")` satisfy `compareTo() == 0`, yet `equals()` returns false. Benchmarking only a single scale does not represent a mixed-scale workload.

For division, boundary data must cover both terminating and non-terminating decimal results:

~~~java
BigDecimal.ONE.divide(new BigDecimal("8")); // 0.125

// BigDecimal.ONE.divide(new BigDecimal("3"));
// ArithmeticException because there is no finite exact representation.
BigDecimal rounded = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new java.math.MathContext(12, java.math.RoundingMode.HALF_EVEN));
~~~

An implementation cannot be considered "faster" if it silently changes scale, rounds at a different step, or drops required exceptions. Benchmarks with large `BigDecimal` magnitudes need realistic bounds to avoid accidental resource exhaustion; document the input limits supported by the system.

## 4. Separating Data Construction Cost from the Measured Operation

A measurement can accidentally include **parsing from strings** or **object construction**:

~~~java
// Includes both parsing and addition: reasonable if this is the entire real path.
BigDecimal result = new BigDecimal("123.45")
        .add(new BigDecimal("67.89"));
~~~

However, if the question is "how fast is `BigDecimal.add` on two pre-prepared operands?", you must construct the operands before the timed region:

~~~java
BigDecimal left = new BigDecimal("123.45");
BigDecimal right = new BigDecimal("67.89");

// Only the add operation is the target of the benchmark.
BigDecimal result = left.add(right);
~~~

Both measurements are valid **if named accurately**:

- **Operation benchmark:** operands already exist; measures add/multiply/divide.
- **End-to-end benchmark:** includes parsing, validation, calculation, rounding, and formatting, reflecting the real request path.
- **Allocation benchmark:** tracks bytes/operation and GC when creating/transforming many numbers.

With immutable numbers, operations can allocate new result objects. If you measure only CPU time while ignoring allocations, a "faster" approach may trigger high GC frequency under heavy system load.

Do not reuse the same mutable object modified continuously across runs if doing so alters inputs or introduces unintended contention. Clearly separate pre-prepared data, per-invocation data, and state the benchmark is allowed to mutate.

## 5. Correctness Is a Prerequisite Before Comparing Speed

Every candidate must pass **result verification** on the same dataset before reporting speed. You can use a simple reference implementation as an *oracle*, though the oracle itself must also be tested.

Example measuring two ways to sum pre-created `BigDecimal` values:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

BigDecimal[] input = {
        new BigDecimal("12.50"),
        new BigDecimal("-3.20"),
        new BigDecimal("0.70")
};

BigDecimal loop = BigDecimal.ZERO;
for (BigDecimal x : input) {
    loop = loop.add(x);
}

BigDecimal stream = Arrays.stream(input)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(loop.toPlainString());   // 10.00
System.out.println(stream.toPlainString()); // 10.00
~~~

You must verify results first. If requirements only check arithmetic value, use `compareTo(...) == 0`. If scale/formatting is part of the contract, verify `scale()` or string representations. For certain operations such as division or intermediate rounding, changing order can yield different results even without concurrency bugs.

Checks should cover:

- Correct sum for 0-element and 1-element sets.
- Negative/0 signs; same-sign and opposite-sign values.
- Overflow for primitives; exception handling if required.
- Precision/scale and `RoundingMode` for decimals.
- Malformed/invalid input paths if present in the application.
- Correctness in parallel execution when the implementation uses parallelism.

**Never skip business-required validation/exceptions to make a benchmark look faster.** If two implementations differ in output contract, timing numbers do not justify substituting one for the other.

## 6. Standalone Runnable Java 17+ Example: Creating Typical and Edge Data, Comparing Results

The program below checks fixed sample sets and measures **raw time for preliminary observation**. The printed nanoseconds depend on machine, JDK, CPU load, and JVM state; this program **is not a reliable microbenchmark**. Its goal is illustrating how to preserve input suites, verify results, and avoid confusing typical data with edge-case data.

Create the file `NumericWorkloadsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

public class NumericWorkloadsDemo {
    private record Case(String name, String[] values) {}

    private static final Case[] CASES = {
        new Case("typical",
                new String[] {"12.50", "-3.20", "0.70"}),
        new Case("zeros",
                new String[] {"0.00", "0.00", "0.00"}),
        new Case("different-scale",
                new String[] {"1E+8", "0.00000001", "-0.00000001"}),
        new Case("large",
                new String[] {"999999999999999999.99", "0.01", "-1.00"}),
        new Case("empty", new String[] {})
    };

    private static BigDecimal sumLoop(BigDecimal[] values) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value);
        }
        return total;
    }

    private static BigDecimal sumStream(BigDecimal[] values) {
        return Arrays.stream(values)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public static void main(String[] args) {
        for (Case testCase : CASES) {
            // Prepare inputs outside the measurement:
            BigDecimal[] data = Arrays.stream(testCase.values())
                    .map(BigDecimal::new)
                    .toArray(BigDecimal[]::new);

            // Verify correctness before measuring:
            BigDecimal expected = sumLoop(data);
            BigDecimal actual = sumStream(data);
            if (expected.compareTo(actual) != 0
                    || expected.scale() != actual.scale()) {
                throw new AssertionError("Mismatch: " + testCase.name());
            }

            System.out.println(testCase.name()
                    + " | inputs=" + data.length
                    + " | sum=" + actual.toPlainString());

            // Preliminary diagnostic only, not for ranking:
            long start = System.nanoTime();
            BigDecimal measured = sumLoop(data);
            long elapsed = System.nanoTime() - start;
            if (measured.compareTo(expected) != 0) {
                throw new AssertionError("Unexpected result");
            }
            System.out.println("  timing-ns=" + elapsed);
        }
    }
}
~~~

Run:

~~~bash
javac NumericWorkloadsDemo.java
java NumericWorkloadsDemo
~~~

The **arithmetically deterministic** output lines (followed after each line by a non-fixed `timing-ns=...` line):

~~~text
typical | inputs=3 | sum=10.00
zeros | inputs=3 | sum=0.00
different-scale | inputs=3 | sum=100000000.00000000
large | inputs=3 | sum=999999999999999999.00
empty | inputs=0 | sum=0
~~~

Actual output interleaves a timing line after each arithmetic line, e.g. `timing-ns=12345`; that number is **unstable** and must not be interpreted as a performance conclusion. On a tiny program, noise from JIT, GC, OS, clock resolution, and measurement overhead can exceed the operation itself. Moreover, the program computes each case only once. To rank options, use a dedicated benchmark such as JMH in the next section.

Notably on the `different-scale` input: even though `0.00000001` and `-0.00000001` cancel out, the sum keeps scale 8 due to `BigDecimal.add` rules. This is why testing both value and scale matters.

## 7. Using JMH When Reliable Micro-Measurements Are Needed

**JMH (Java Microbenchmark Harness)** is the standard benchmarking tool commonly used for JVM code. It supports warmup, measurement iterations, forks, result modes (`AverageTime`, `Throughput`...), input parameters, and result-consumption mechanisms that reduce the risk of the JVM optimizing the benchmark away in unrepresentative ways.

A minimal benchmark for adding pre-parsed `BigDecimal` values can be written as follows (this is a **JMH fragment**, not directly runnable with only the JDK's `javac`; the project must add the JMH dependency and annotation processor):

~~~java
import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class DecimalAddBenchmark {
    @Param({"8", "64", "512"})
    public int elements;

    private BigDecimal[] values;

    @Setup(Level.Trial)
    public void prepare() {
        values = IntStream.range(0, elements)
                .mapToObj(i -> new BigDecimal(
                        i % 2 == 0 ? "123.45" : "-23.40"))
                .toArray(BigDecimal[]::new);
    }

    @Benchmark
    public void sumLoop(Blackhole blackhole) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value);
        }
        blackhole.consume(total);
    }

    @Benchmark
    public void sumStream(Blackhole blackhole) {
        BigDecimal total = java.util.Arrays.stream(values)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        blackhole.consume(total);
    }
}
~~~

Meaning:

- `@Param` measures multiple collection sizes rather than a single short list.
- `@Setup(Level.Trial)` prepares data **outside the measured section**; thus the benchmark compares addition with pre-existing operands.
- `Blackhole.consume(...)` prevents accidentally discarding computed results, expressing that the result is used.
- `@BenchmarkMode(Mode.AverageTime)` requests average invocation time across measurements; not the p99 latency of a real system.
- `@State(Scope.Thread)` gives each worker its own state. When you need to simulate contention on shared state, choose an appropriate state/thread setup for that scenario, though that benchmark answers a different question.

This example **does not yet represent all real data**, because each element is merely one of two short strings. To measure real workloads, replace `prepare()` with a dataset matching the precision, scale, sign, and length distribution derived from source data analysis; edge groups should be separated into distinct case parameters. For random inputs, generate them using a **fixed seed** before measurement so all candidates operate on identical data; avoid generating random numbers inside the benchmark itself unless intentionally measuring the RNG.

### 7.1. Reproducible measurement process

1. **Define operation and output:** name the case, inputs, measurement unit, pass/fail, and completion criteria.
2. **Prepare corpus:** typical data in realistic ratios, varying-size cases, edge cases, and explicit error cases.
3. **Verify correctness:** run oracle/tests for every implementation, including value and scale where required.
4. **Warmup:** let the JVM compile and optimize hot code paths before collecting results.
5. **Measurement:** run multiple iterations and multiple independent JVM forks, recording variance and harness-reported error.
6. **Document environment:** JDK/vendor/version, CPU, RAM, JVM flags, OS, GC, thread count, heap size, and data source.
7. **Measure allocation/GC:** use a profiler or JMH profiling features if `BigDecimal`/`BigInteger` creation is a major cost.
8. **Repeat on target load:** verify end-to-end workloads and appropriate concurrency, since microbenchmark results describe only the measured snippet.

Do not pick a single result after one run as your conclusion. If the gap is small relative to measurement variance, treat it as insufficient evidence.

### 7.2. Microbenchmark pitfalls

| Pitfall | Why it is dangerous | How to avoid |
|---|---|---|
| Benchmark code uses only constants | JVM can constant-fold or optimize away work | Varying data from `@State`/`@Param`, consume results |
| Output goes unused | JVM can eliminate unobservable computation | Return result from benchmark or use `Blackhole` |
| No warmup | Measures interpreter/class loading/JIT too | Configure separate warmup + measurement |
| Single `nanoTime` over a few ops | Clock overhead and noise dominate | JMH with iterations/forks |
| Creating objects inside measurement when only wanting arithmetic | Result mostly measures parsing/allocation | Prepare in `@Setup` when contract fits |
| Pre-building inputs when goal is end-to-end | Skips parsing/formatting/validation | Benchmark real request path separately |
| Generating random numbers per call inside benchmark | Measures RNG too, different data per candidate | Pre-generate fixed-seed corpus outside measurement |
| Running candidates under different system loads | Noise makes comparison unreliable | Stable environment, multiple trials/forks |
| Equating average with p99 | Misses real system tail latency | Measure latency distribution at request level |
| Comparing code with different overflow/rounding rules | "Faster" due to changed semantics | Correctness gate before performance |
| Choosing one extreme dataset as sole representative | Fails to reflect production frequency | Both mixed workloads and separate edge cases |

## 8. Choosing Metrics Tied to Goals

No single speed metric fits every system. When reporting, specify **unit and scope**:

| Metric | Question answered | When useful |
|---|---|---|
| `ns/op` or `µs/op` | How long does one calculation take in a microbenchmark? | Comparing two algorithms for the same operation |
| `ops/s` | How many operations can a worker/system process per second? | Aggregate throughput |
| `bytes/op` | How much memory does each operation allocate? | `BigDecimal`/`BigInteger` creating many objects |
| `GC pauses`, allocation rate | How much GC pressure do large data or frequent allocations cause? | Long-running, high-load services |
| `p50/p95/p99 latency` | Within what time do 50%, 95%, 99% of requests finish? | Ensuring response-time targets |
| `CPU utilization`, request concurrency | How does concurrent load affect performance? | Real server production behavior |

For example, a rare `BigInteger` multiplication taking a long time may barely affect average throughput yet spike tail latency. Conversely, adding a small allocation on every calculation repeated millions of times can cause substantial GC even when each invocation is fast.

**Do not interpret the arithmetic mean of a microbenchmark as request p99.** Requests can involve parsing, I/O, queueing, dispatching multiple calculations, and GC pauses. If the system has a p99 SLO, measure with a load generator at the real request tier with accurate request ratios and concurrency.

## 9. Edge Suites Must Test Errors Too, Not Just Large Numbers

Edge data includes **business-meaningful error paths**:

- `new BigDecimal("invalid")` throws `NumberFormatException`.
- `BigDecimal.ONE.divide(new BigDecimal("3"))` throws `ArithmeticException` if finite exact division is required.
- `Math.addExact(Integer.MAX_VALUE, 1)` throws `ArithmeticException`.
- `BigDecimal` with huge precision/scale can cause memory pressure or hit execution/representation limits.
- `DoubleStream` containing `NaN` can make aggregations return `NaN`, requiring handling per application rules.

Determine the error rate in production: rare yet valid cases need dedicated benchmarks, while malformed requests may need measurement on the input-validation path. Still, do not generate unbounded dangerous data just to prove a point; define valid input limits and test right at those marks.

If resources are scarce, use a comprehensive functional test suite for extreme inputs and a bounded, reproducible benchmark suite; document measured limits to avoid over-extrapolating.

## 10. Designing an Experiment Comparing Two Implementations

Suppose the goal is choosing between a `for` loop and `Stream.reduce` to sum a `BigDecimal` array.

### Step 1 — define the contract

The input is a pre-parsed `BigDecimal[]`; elements are non-`null`. Both solutions use exact addition (`add` without `MathContext`) and outputs must match in both value **and scale**. Do not mutate the input data.

### Step 2 — design the measurement suite

- **Typical:** array length occurring most often, mostly low precision and scale 2.
- **Large batch:** large element count representing peak batches.
- **Mixed scale:** includes negative scale, scale 0, scale 2, and high scale.
- **Long precision:** `BigDecimal` with hundreds/thousands of digits at allowed thresholds.
- **Empty/single:** 0 or 1 element; checks pipeline overhead.
- **Mixed sign:** positive/negative/0 values, including near-canceling pairs.

Each case is measured separately. Afterward, a mixed workload can be built in production proportions to estimate overall impact.

### Step 3 — verify correctness first

Check `compareTo` and `scale`, or compare canonical strings if the contract requires. Avoid normalizing with `stripTrailingZeros()` inside tests if preserving scale is mandatory: that operation alters representation.

### Step 4 — benchmark and collect secondary metrics

Use JMH to measure time per array summation on identical data. Enable allocation profiling when needed. In microbenchmarks with a few operands, differences may be tiny; with large batches, stream setup, looping, and result object counts all contribute to the outcome.

### Step 5 — interpret within evidence bounds

A good report does not merely say "A is 30% faster than B". It states **dataset**, **JDK/CPU**, **mode**, **trial counts**, **variance**, **allocation**, **correctness**, and which cases win/lose. A conclusion might be "For 100-element batches, A is meaningfully faster; for 10,000-element batches, results are equivalent within error margins", rather than an absolute proclamation.

Result recording table (fill with real measurements, **never fabricate values**):

| Case | Size | Precision/scale | Approach A ns/op | Approach B ns/op | bytes/op | Correctness | Notes |
|---|---:|---|---:|---:|---:|---|---|
| Typical | Per real data | Short, scale 2 | *Fill measured* | *Fill measured* | *Fill measured* | PASS/FAIL | Warmup/forks |
| Mixed scale | Per real data | Mixed scales | *Fill measured* | *Fill measured* | *Fill measured* | PASS/FAIL | Verify scale |
| Large precision | Per real data | Hundreds of digits | *Fill measured* | *Fill measured* | *Fill measured* | PASS/FAIL | Memory/GC |
| Empty/single | 0 or 1 | Cardinality edge | *Fill measured* | *Fill measured* | *Fill measured* | PASS/FAIL | Overhead |

This is a **measurement recording template**, not benchmark results. Never replace the cells with estimated numbers and claim they were measured in production.

## 11. Common Mistakes and Fixes

| Mistake | Impact | Fix |
|---|---|---|
| Using only one small numeric value | Misses branches/complexity on other data | Use real distribution + multiple buckets |
| Measuring edge cases and calling it "average performance" | Distorts occurrence rates | Separate edge results from weighted workload |
| Measuring only average time | Misses slow requests and GC pauses | Collect p95/p99 at system level when SLO exists |
| Using `new BigDecimal("1.00")` inside loop unintentionally | Mixes parsing cost with arithmetic | Clearly choose operation vs. end-to-end |
| Benchmark takes constants, discards output | JIT may optimize away operation | Use JMH `@State`, `@Param`, and consume results |
| Skipping output checks before benchmarking | Selects arithmetically wrong option | Correctness gate and oracle |
| Ignoring overflow/non-terminating cases | Production bugs despite fast benchmark | Test at boundaries and error scenarios |
| Comparing `double` and `BigDecimal` as same semantics | Undisclosed precision trade-off | Clarify arithmetic contract |
| Assuming parallel is always faster | Adds overhead, contention, and alters float results | Measure by workload + core count |
| Changing data between candidates | No longer comparing same work | Use fixed seed/dataset |
| Omitting JDK/flags/CPU | Hard to reproduce conclusions | Record full configuration |
| Reporting `ns/op` as real latency | Microbenchmark does not simulate requests | Also measure end-to-end under real load |

## 12. Self-Check Quiz

**Question 1.** Why does a `BigInteger` addition being fast for single-digit numbers not prove it is fast for thousand-digit operands?

**Answer:** Arithmetic cost depends on representation length and the algorithm used. Benchmarks must include length buckets representative of the supported domain.

**Question 2.** A system returns money as `BigDecimal` with mandatory scale 2. If an optimized version returns the same value with scale 1, is it considered correct?

**Answer:** If scale is part of the contract, no. Both value and scale must be verified before measuring performance.

**Question 3.** A benchmark only calls `sumLoop(input)` with pre-parsed operands. Does it measure request parsing cost?

**Answer:** No. That benchmark measures the summation step on prepared data. To measure end-to-end, include parsing and realistic steps inside the measured region of a separate benchmark.

**Question 4.** What does `IntStream.of(Integer.MAX_VALUE, 1).sum()` return, and what does it mean for benchmarking?

**Answer:** It returns `-2147483648` due to `int` overflow. An implementation with great speed yet this result violates a requirement needing large integer sums, so fix the contract/data type before ranking performance.

**Question 5.** If 1% of requests carry large, slow data, is measuring only the 99% typical data enough to report p99 latency?

**Answer:** No. You must observe the latency distribution across all requests at real proportions and check tail latency; measuring the large case separately is also useful to understand root causes.

**Question 6.** Why are warmup/forks needed when benchmarking short Java code?

**Answer:** The JVM may start in the interpreter and later JIT-optimize; heap and cache states can differ across runs. Warmup and forks help reduce bias, though variance should still be reported.

**Question 7.** Option A uses less CPU yet allocates many times more memory. Can it be declared strictly better?

**Answer:** Not yet. Extra allocations can increase GC and p99 latency under high load. You must compare multiple metrics and production limits.

---

**Takeaway:** Numeric benchmarking in Java must use **a representative data domain** and **reasoned edge cases**, verify value/precision/scale/exception correctness **before comparing speeds**, and measure with warmup, multiple trials, and documented environments. To make practical decisions, combine microbenchmarks with end-to-end data, throughput, tail latency, allocation, and GC; never generalize from a single addition or a lone `System.nanoTime()`.
