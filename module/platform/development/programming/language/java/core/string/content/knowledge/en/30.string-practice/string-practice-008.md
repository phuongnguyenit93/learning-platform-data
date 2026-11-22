# Comparing Performance of String Concatenation Approaches on Identical Data in Java

## 1. Practice goal

In Java, there are multiple ways to build one string from multiple parts: `+`/`+=` operators, `StringBuilder`, `StringJoiner`, `String.join`, and `Collectors.joining`. These APIs can produce identical text output, yet **object allocation counts, copying work, total allocation volume, pipeline overhead, and JVM optimization behavior** can differ.

A trustworthy comparison must answer **two separate questions**:

1. **Is it functionally identical?** Every approach must produce *the exact same string*, with the same delimiter, same order, and identical handling of empty/single-element arrays and defined inputs.
2. **Does performance differ?** Measure repeatedly in a controlled environment on the same data, same work, and same runtime conditions; distinguish elapsed time from allocation volume.

**Goal of this lesson:** build a reproducible dataset, implement six concatenation approaches, verify identical outputs, and then feed them into a JMH benchmark to compare yourself. There is no universal constant like "`StringBuilder` is always X times faster" across all Java versions, JVMs, and data sizes.

## 2. Defining a shared problem before comparing

Given a `null`-free `String[] values` array with elements formatted like `v0_0`, `v1_1`, ..., the desired output is:

```text
values = ["v0_0", "v1_1", "v2_2"]
result = "v0_0|v1_1|v2_2"
```

Fixed rules:

- Place `|` **only between adjacent elements**; no leading or trailing delimiter.
- Preserve the original order and all characters of each element.
- An empty array produces `""`; a single-element array produces that element itself.
- This practice uses **non-null** elements; how `null` is handled in real data must be specified separately, and one method must not use a different policy while still claiming to do "the same work."
- Do not include **array generation time** in concatenation timing. For pre-sized `StringBuilder`, state explicitly whether capacity calculation is part of the functional test or precomputed in benchmark setup.

Inputs are generated deterministically rather than randomly inside the timed code:

```java
static String[] input(int size) {
    String[] values = new String[size];
    for (int i = 0; i < size; i++) {
        values[i] = "v" + i + "_" + (i % 17);
    }
    return values;
}
```

This is an illustrative method included in the standalone program below. Having every approach read the same `String[]` removes noise from file I/O, database queries, random string generation, or data normalization.

## 3. Six approaches compared

| Approach | Core mechanism | Measurement considerations |
| --- | --- | --- |
| `+=` in a loop | Each step requires a new `String` value per concatenation semantics | May repeatedly copy the accumulated prefix across steps |
| Default `StringBuilder` | Appends segments into a mutable character buffer | Buffer may resize multiple times |
| Pre-sized `StringBuilder` with `capacity` | Pre-allocates expected capacity then calls `append` | Requires knowing/estimating capacity; computing capacity has its own cost |
| `StringJoiner` | Adds elements with API-managed delimiter | Directly matches the "delimited joining" task |
| `String.join` | Convenience API for arrays/`Iterable` | May have implementation-specific overhead depending on JVM |
| `Arrays.stream(...).collect(Collectors.joining(...))` | Stream pipeline with string-joining collector | May incur stream and collector setup overhead |

**Important:** `StringBuilder` is **mutable**, while `String` is **immutable**. However, you cannot deduce exact allocation counts for every `+` solely from `invokedynamic` bytecode (on `javac` Java 9+). The JVM can optimize aggressively in certain contexts; benchmark rather than relying purely on intuition.

In a short single expression like `"id=" + id + ",name=" + name`, modern compilers usually optimize well. **Repeatedly appending with `+=` in a loop to grow an accumulator string** is a different workload, often risking repeated copying as the result grows.

## 4. Java 17+ program verifying all methods produce identical output

Create the file `ConcatCases.java`:

```java
import java.util.Arrays;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class ConcatCases {
    static String plusLoop(String[] values) {
        String result = "";
        for (int i = 0; i < values.length; i++) {
            if (i > 0) result += "|";
            result += values[i];
        }
        return result;
    }

    static String builder(String[] values) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) out.append('|');
            out.append(values[i]);
        }
        return out.toString();
    }

    static String builderSized(String[] values) {
        int capacity = Math.max(0, values.length - 1);
        for (String value : values) capacity += value.length();
        StringBuilder out = new StringBuilder(capacity);
        for (int i = 0; i < values.length; i++) {
            if (i > 0) out.append('|');
            out.append(values[i]);
        }
        return out.toString();
    }

    static String joiner(String[] values) {
        StringJoiner out = new StringJoiner("|");
        for (String value : values) out.add(value);
        return out.toString();
    }

    static String joining(String[] values) {
        return String.join("|", values);
    }

    static String stream(String[] values) {
        return Arrays.stream(values).collect(Collectors.joining("|"));
    }

    static String[] input(int size) {
        String[] values = new String[size];
        for (int i = 0; i < size; i++) values[i] = "v" + i + "_" + (i % 17);
        return values;
    }

    public static void main(String[] args) {
        for (int n : new int[] {0, 1, 8, 128, 1024}) {
            String[] data = input(n);
            String expected = String.join("|", data);
            String[] actual = {
                plusLoop(data), builder(data), builderSized(data),
                joiner(data), joining(data), stream(data)
            };
            for (String candidate : actual) {
                if (!expected.equals(candidate)) {
                    throw new AssertionError("Different output at n=" + n);
                }
            }
            System.out.println("n=" + n + " methods=6 identical=true chars="
                    + expected.length());
        }
    }
}
```

Run from the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 ConcatCases.java
java ConcatCases
```

Output **verified by compiling and running**, not benchmark timing data:

```text
n=0 methods=6 identical=true chars=0
n=1 methods=6 identical=true chars=4
n=8 methods=6 identical=true chars=39
n=128 methods=6 identical=true chars=834
n=1024 methods=6 identical=true chars=7501
```

The program reports `methods=6 identical=true` because **all six approaches produce character-for-character identical `String` values** matching the reference output at each size. This rules out common bugs such as trailing `|`, wrong element order, or skipping the first element. This is a *functional check*, not evidence of which is fastest.

### Why test `n = 0` and `n = 1` as well?

- `n=0` yields `""`. A buggy joiner might emit a delimiter even with zero elements.
- `n=1` must add no delimiter at all. Manual loops easily leave a stray leading or trailing `|`.
- `n=8` illustrates small payloads typical of forms, messages, or a single log line.
- `n=128` and `n=1024` test longer outputs, exposing cumulative copying costs and buffer growth.

When real data includes `null`, long Unicode strings, delimiters inside values, or length caps, add matching test cases and **align expected outputs** across all approaches before measuring.

## 5. Why identical results are not enough to compare performance

Two approaches can yield identical output yet differ because one:

- Spends more CPU copying accumulated prefixes.
- Allocates more intermediate objects or buffers, increasing garbage collector (GC) pressure.
- Has to grow buffer capacity in stages.
- Pays overhead for creating streams, collectors, or API wrappers.
- Is optimized differently by the JIT after warming up; overly short runs easily misjudge performance.

Conceptually, with `n` chunks of similar length, if each `+=` step must copy all accumulated content so far, total characters copied can grow like the sum:

\[
1 + 2 + \cdots + n = \frac{n(n+1)}{2}
\]

This intuitively explains the risk of **roughly quadratic growth in elements** for naive cumulative concatenation when element lengths are similar. It is **not a guarantee of actual complexity across every compiler and JVM**: compilers and JITs can apply optimizations, especially in predictable contexts.

Meanwhile, `StringBuilder` accumulates into a buffer and creates the resulting `String` at the end, typically avoiding recreating the whole string at every step. Pre-sizing `capacity` large enough also avoids buffer resizes. However, if you have to scan all values to compute length, that scan is also a **cost**; do not include it for one method while omitting it for another when the goal is comparing total end-to-end work.

## 6. Controlled measurement with JMH

For Java microbenchmarks, use **JMH (Java Microbenchmark Harness)** instead of subtracting `System.nanoTime()` around a single loop. JMH provides warm-up, multiple iterations, JVM forks, and proper result consumption to reduce dead-code elimination and unwanted optimizations.

### Creating a JMH project

With JDK and Maven installed, use the JMH archetype (e.g., version `1.37`):

```bash
mvn archetype:generate -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=org.example \
  -DartifactId=concat-bench \
  -Dversion=1.0
```

The command block above uses POSIX shell line continuation `\` (Linux/macOS). On PowerShell, write it on **a single line** with the same arguments and omit `\`. The archetype sets up the scaffolding to run JMH as a Maven project. Place `ConcatBenchmark.java` under `concat-bench/src/main/java/org/example/`, using package `org.example` as shown next.

### Complete JMH benchmark class

```java
package org.example;

import java.util.Arrays;
import java.util.StringJoiner;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ConcatBenchmark {
    @Param({"8", "128", "1024"})
    public int n;

    private String[] data;
    private int exactCapacity;

    @Setup(Level.Trial)
    public void setup() {
        data = new String[n];
        int chars = Math.max(0, n - 1);
        for (int i = 0; i < n; i++) {
            data[i] = "v" + i + "_" + (i % 17);
            chars += data[i].length();
        }
        exactCapacity = chars;

        String expected = String.join("|", data);
        if (!expected.equals(plusLoop())
                || !expected.equals(builder())
                || !expected.equals(builderSized())
                || !expected.equals(joiner())
                || !expected.equals(joining())
                || !expected.equals(streamJoining())) {
            throw new IllegalStateException("Different concatenation outputs");
        }
    }

    @Benchmark
    public String plusLoop() {
        String result = "";
        for (int i = 0; i < data.length; i++) {
            if (i > 0) result += "|";
            result += data[i];
        }
        return result;
    }

    @Benchmark
    public String builder() {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < data.length; i++) {
            if (i > 0) out.append('|');
            out.append(data[i]);
        }
        return out.toString();
    }

    @Benchmark
    public String builderSized() {
        StringBuilder out = new StringBuilder(exactCapacity);
        for (int i = 0; i < data.length; i++) {
            if (i > 0) out.append('|');
            out.append(data[i]);
        }
        return out.toString();
    }

    @Benchmark
    public String joiner() {
        StringJoiner out = new StringJoiner("|");
        for (String value : data) out.add(value);
        return out.toString();
    }

    @Benchmark
    public String joining() {
        return String.join("|", data);
    }

    @Benchmark
    public String streamJoining() {
        return Arrays.stream(data).collect(Collectors.joining("|"));
    }
}
```

Key benchmark design choices:

- `@State(Scope.Thread)` provides state per benchmark thread.
- `@Param` runs all three dataset sizes as separate benchmark cases.
- `@Setup(Level.Trial)` builds the array and computes `exactCapacity` **outside the timed section**. This isolates concatenation cost rather than data generation.
- `builderSized()` receives a precomputed capacity, modeling scenarios where final length is already known. This is a **conditional advantage**: if the real application must scan the array to compute capacity, add an end-to-end benchmark that includes that scan.
- Each `@Benchmark` returns the resulting `String`, letting JMH observe the return value and prevent forms of dead-code elimination.
- `@Fork(2)` runs two independent JVM forks; `@Warmup` and `@Measurement` reduce JIT warm-up noise.
- Do not print to console, read files, allocate the input array, or generate random data inside benchmark methods, as those are not what you want to measure.

### Running JMH

From the `concat-bench` project directory:

```bash
mvn clean verify
java -jar target/benchmarks.jar ConcatBenchmark
```

Each combination of size and method reports its own timing statistics. The `@Warmup`, `@Measurement`, and `@Fork` settings above take noticeable time because multiple warm-up and measurement runs are needed; during quick sanity checks you can reduce counts via command-line flags, then use the full config for final reporting.

Example adding **GC allocation profiling**:

```bash
java -jar target/benchmarks.jar ConcatBenchmark -prof gc
```

Depending on profiler/JDK, output may include `gc.alloc.rate.norm` (normalized bytes allocated per operation) and related GC metrics. Allocation figures can reflect JIT optimizations (such as escape analysis) and output size; do not infer retained heap size solely from allocated bytes. If the profiler is unavailable in your environment, report it as unmeasured rather than filling in numbers.

**Do not hardcode fixed `μs/op` numbers into the lesson**: JMH must run on a specific machine, JDK, heap, CPU, GC state, and workload. A pre-filled "results" table before measuring leads learners to trust unverified rankings.

## 7. How to present comparison tables

After running, record at least `java -version`, CPU model, JMH version, JVM options, fork count, warm-up/measurement counts, dataset, output length, and measurement units. Use one table per **fixed `n`**:

| Method | Avg time (`μs/op`) | Error/CI | Alloc (`B/op`) if available | Notes |
| --- | ---: | ---: | ---: | --- |
| `plusLoop` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | Cumulative `+=` concatenation |
| `builder` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | Default capacity |
| `builderSized` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | Precomputed capacity |
| `joiner` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | Delimiter API |
| `joining` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | `String.join` API |
| `streamJoining` | Fill from JMH | Fill from JMH | Fill from `-prof gc` | Stream + collector |

This is a **template for measured results**, not simulated data. Under `AverageTime` mode, **lower** `μs/op` means less time per operation in that workload. The error/uncertainty column prevents over-interpreting tiny differences inside measurement noise.

When comparing multiple sizes (`n=8`, `128`, `1024`), do not collapse all sizes into a single "average" to rank methods. Trends can shift with size: a concise method with low setup overhead can fit small element counts, while buffering approaches typically pull ahead on larger workloads.

### Example of reading results accurately

Suppose an empirical run shows `builderSized` taking fewer `μs/op` than `builder` at `n=1024`; you may conclude that **in that benchmark**, pre-knowing capacity reduced overhead. You cannot conclude the whole application will speed up, because real code may spend time computing capacity, parsing input, hitting the network, or writing files.

If `streamJoining` and `joining` fall within each other's error margin, there is insufficient evidence to declare one faster. Nor should you assume lower `B/op` always means lower latency; CPU, allocation, memory bandwidth, and GC are related but distinct quantities.

## 8. Traps that make benchmarks unfair

1. **Different outputs:** one implementation has a trailing delimiter and another does not, or one skips empty elements. Verify output equality before measuring.
2. **Generating data inside one benchmark but precomputing in another:** accidentally measures data generation, skewing the comparison.
3. **One side knows capacity upfront while the other computes it:** both can be valid scenarios, yet you must separate benchmarks measuring **pure concatenation** from those measuring **total output-creation cost**.
4. **Using `System.nanoTime()` once and ranking:** noise from JIT compilation, class loading, GC, OS scheduling, and CPU frequency scaling can exceed real differences.
5. **Not consuming the result:** the JVM may eliminate computations with no observable side effects. JMH supports return values or `Blackhole`.
6. **Putting console I/O inside timed code:** `System.out.println` is expensive and shifts measurement away from string concatenation.
7. **Benchmarking only tiny or only huge arrays unrepresentative of your app:** a single size is insufficient to establish trends.
8. **Confusing `String` length with UTF-8 bytes:** `String.length()` counts UTF-16 code units; UTF-8 byte length varies by content. If your workload has real Unicode, use a representative dataset.
9. **Looking only at the mean while ignoring error and GC:** inspect variance, allocation/GC stats, and repeat with proper settings.
10. **Generalizing a short `+` expression to loop concatenation:** those are two different workloads. Do not use a loop `+=` benchmark to claim every `+` operator is slow.
11. **Omitting JVM/JDK versions:** bytecode emission by the compiler and runtime JIT behavior matter greatly. Record both compile JDK and runtime JDK versions.
12. **Drawing conclusions from a single run on a heavily loaded machine:** use independent forks, prefer a quiet environment, and note limitations when noise exists.

### Comparing both output and scaling

Once outputs match, ask how the resulting string **scales as it grows**. A `+=` loop over `n` progressively longer strings can sharply increase intermediate bytes copied. With `StringBuilder`, repeated `append` calls operate on a resizable buffer, so cost growth is usually easier to keep predictable. Still, these descriptions are **explanatory models**, not substitutes for JMH numbers on your actual application.

## 9. Which approach should you choose in real Java code?

- **Joining a few fixed expressions:** prefer `+` for readability. Java 9+ `javac` often compiles dynamic concatenations via `invokedynamic` and `StringConcatFactory`; do not manually rewrite to `StringBuilder` without reason.
- **Accumulating many parts in a loop:** `StringBuilder` is the clear choice, avoiding reliance on whether the JVM detects and optimizes repeated `+=`.
- **Delimited joining from a ready list or array:** `String.join(delimiter, values)` is very readable; `StringJoiner` fits when adding elements incrementally during processing.
- **Already inside a stream pipeline:** `Collectors.joining(delimiter)` integrates naturally; measure if it sits on a hot path, especially when joining elements with no other stream transformations.
- **Result length is known fairly accurately:** pre-size `StringBuilder` capacity to reduce buffer resizes; include capacity-calculation cost when evaluating end-to-end performance.
- **Very large outputs:** consider streaming directly to a `Writer`/`OutputStream` with an explicit charset instead of materializing the whole `String` in memory. That is a different problem from returning one string and must be benchmarked separately.

Code readers should prioritize **correct semantics and maintainability, then measure real bottlenecks**. JMH illuminates the impact of each technique, yet a micro-optimization in string concatenation will not save a design spending most of its time in I/O, queries, or other work.

## 10. Practice completion checklist

- All six methods receive **the same input array** and produce the exact string with `|` between elements.
- Verified `n=0`, `1`, `8`, `128`, `1024` yield identical content, not merely identical length.
- Dataset is built outside the timed JMH benchmark; all trials share the same element-generation logic.
- Warm-up, measurement iterations, JVM forks, and result consumption are configured.
- Results are reported per size, in `μs/op`, with error bounds and `B/op` if collected.
- Pre-sized `builderSized` is clearly distinguished from scenarios that must compute capacity per call.
- Avoid generalizing loop `+=` benchmarks to every `+` expression.
- Fast/slow claims are grounded solely in **empirical measurements**, with environment and caveats stated clearly.

**Takeaway:** a string concatenation performance comparison is meaningful only after **all six methods produce identical output before timing**. For multi-part accumulation, `StringBuilder` and delimiter-joining APIs are the practical candidates to compare; `+=` in loops risks substantial copying overhead. Final rankings and margins must be verified with proper benchmarks on a representative workload.