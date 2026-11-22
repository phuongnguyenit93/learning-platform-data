# Measuring Performance with Benchmarks for Java Pattern Matching (Java 21+)

## 1. Ask the Right Question Before Measuring

When replacing Java code that uses `instanceof` and casting with a type pattern or record pattern, many developers want to know: **"Is pattern matching faster than the traditional approach?"**. A reliable answer cannot be inferred merely from shorter syntax, fewer lines of code, or a single run.

There are at least three code styles to distinguish:

~~~java
// Approach A: type check + cast
if (value instanceof Order) {
    Order order = (Order) value;
    return 31L * order.units() + order.sku().length();
}

// Approach B: type pattern
if (value instanceof Order order) {
    return 31L * order.units() + order.sku().length();
}

// Approach C: record pattern (Java 21+)
if (value instanceof Order(var units, var sku)) {
    return 31L * units + sku.length();
}
~~~

The snippets above **only illustrate the branching part**, and are not standalone Java methods yet. The complete runnable code is in Section 4 and Section 6.

All three approaches can result in very similar work after `javac` and JIT optimizations. There is no language guarantee that a type pattern or record pattern is **always faster** than using a cast. You must measure on the exact JDK, workload, CPU, and configuration of your application.

In this topic, a benchmark is a **reproducible experiment** aimed at answering a specific question about time, throughput, or resources. For pattern matching, a reasonable experiment is:

> Given the same input objects and the same computation, is there a measurable and reproducible difference in the cost of branching via cast, type pattern, and record pattern?

A **microbenchmark** focuses on a very small piece of code; an **end-to-end benchmark** measures an entire business flow such as request parsing, I/O, validation, database, and serialization. Microbenchmark results **do not automatically become** the latency of an API or the speed of the entire application.

## 2. Why Naive `System.nanoTime()` Measurement Is Easy to Get Wrong

A common approach is to run the code in a loop and divide the total time by the number of calls:

~~~java
// Illustrative anti-pattern; score and value are not declared here.
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    score(value);
}
long nanos = System.nanoTime() - start;
System.out.println(nanos / 1_000_000.0);
~~~

This is not yet a reliable microbenchmark because of:

1. **Dead-code elimination:** if the result of `score(value)` is ignored, the JIT compiler may eliminate work that produces no observable effect.
2. **Constant folding:** if `value` is a known constant value, the result may be precomputed.
3. **Loop optimization:** unrolling, vectorization, hoisting, or cross-iteration optimizations can make the measurement no longer representative of a single invocation.
4. **JIT warm-up:** early runs may measure the bytecode interpreter, C1/C2 compilation, and profiling data collection.
5. **GC and system noise:** garbage collection, scheduler, other threads, thermal throttling, and CPU frequency affect the results.
6. **Branch prediction:** checking the same subtype one million times is completely different from a mixed dataset with multiple subtypes.
7. **Clock overhead:** clock calls, resolution, and noise can be on the same order of magnitude as the operation being measured.

`System.nanoTime()` is still useful for observing a sufficiently large task or local tracing; the point is **not to treat a single nanos/op number as proof of syntactic superiority**.

For JVM microbenchmarks, use OpenJDK's **JMH (Java Microbenchmark Harness)**. JMH supports warm-up, measurement iterations, JVM forks, output consumption, and mechanisms that help mitigate common measurement errors. JMH still cannot turn a poorly designed workload into a valid conclusion: the author remains responsible for the equivalence of the approaches and the representativeness of the input.

## 3. Designing a Fair Experiment

The example uses two records:

~~~java
record Order(int units, String sku) {}
record Payment(String currency, long cents) {}
~~~

All three approaches must compute the exact same score:

- If `x` is `Order`: return `31L * units + sku.length()`.
- If `x` is `Payment`: return `cents % 97 + currency.length()`.
- If `x` is `null` or another type: return `0`.

In this way, we test **the access method and type classification**, without accidentally comparing one version that does less work against another.

| Factor to Control | Principle |
| --- | --- |
| Logic | All versions have the same computation, same results, and same null policy |
| Data | Same seed, same type distribution, and same data size |
| JVM | Same JDK version, JVM flags, GC, and compilation mode |
| CPU/machine | Same hardware; minimize background tasks, avoid throttling |
| Initialization | Prepare inputs outside the measured code if not measuring allocation |
| JIT | Sufficient warm-up; measure across multiple iterations and forks |
| Result | Consumed by the harness to prevent optimizing away the operation |
| Conditions | Document the ratio of subtypes, nulls, and non-matching types |
| Interpretation | Distinguish benchmark operation cost from system latency |

**Workload premise:** `sku` and `currency` in both records are always non-null. If real-world data allows null components, **identical** handling must be added to all three approaches before measuring. A record pattern does not by default guarantee that every reference component is non-null.

## 4. Equivalence Testing Before Measuring Performance

Create the file **`PatternBenchmarkCheck.java`**. This is a **JDK-only** program, without JMH, to cross-check all three implementations.

~~~java
public class PatternBenchmarkCheck {
    record Order(int units, String sku) {}
    record Payment(String currency, long cents) {}

    static long classic(Object x) {
        if (x instanceof Order) {
            Order o = (Order) x;
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment) {
            Payment p = (Payment) x;
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long typePattern(Object x) {
        if (x instanceof Order o) {
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment p) {
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long recordPattern(Object x) {
        if (x instanceof Order(var units, var sku)) {
            return 31L * units + sku.length();
        }
        if (x instanceof Payment(var currency, var cents)) {
            return cents % 97 + currency.length();
        }
        return 0;
    }

    static int passed = 0;

    static void verify(String name, Object input, long expected) {
        long a = classic(input);
        long b = typePattern(input);
        long c = recordPattern(input);

        if (a != expected || b != expected || c != expected) {
            throw new AssertionError(
                    name + ": " + a + " / " + b + " / " + c);
        }
        ++passed;
        System.out.println("PASS " + name + " -> " + expected);
    }

    public static void main(String[] args) {
        verify("order-one", new Order(1, "A"), 32);
        verify("order-zero", new Order(0, "XYZ"), 3);
        verify("order-seven", new Order(7, "AB"), 219);
        verify("order-negative", new Order(-1, "P"), -30);
        verify("payment-usd", new Payment("USD", 1234), 73);
        verify("payment-vnd-zero", new Payment("VND", 0), 3);
        verify("payment-eur-mod", new Payment("EUR", 97), 3);
        verify("payment-jpy-negative", new Payment("JPY", -1), 2);
        verify("null", null, 0);
        verify("other-string", "other", 0);
        verify("other-integer", 42, 0);
        verify("other-boolean", Boolean.TRUE, 0);

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac --release 21 PatternBenchmarkCheck.java
java PatternBenchmarkCheck
~~~

**Deterministic output:**

~~~text
PASS order-one -> 32
PASS order-zero -> 3
PASS order-seven -> 219
PASS order-negative -> -30
PASS payment-usd -> 73
PASS payment-vnd-zero -> 3
PASS payment-eur-mod -> 3
PASS payment-jpy-negative -> 2
PASS null -> 0
PASS other-string -> 0
PASS other-integer -> 0
PASS other-boolean -> 0
ALL PASSED: 12
~~~

`classic` uses an explicit cast after `instanceof`; `typePattern` combines the type check and variable declaration; `recordPattern` deconstructs the record (Java 21+). For all inputs in the list, all three approaches return the same result.

**This is a correctness test, not a performance measurement.** It shows that a fair comparison can be made on the tested values. Before benchmarking production data, you should add tests for real-world business rules such as null strings, invalid fields, and other input types.

## 5. Setting Up JMH with Maven

Official project page: [OpenJDK JMH](https://github.com/openjdk/jmh). JMH recommends a dedicated Maven benchmark project for stable builds and execution; annotation processing is required to generate the harness code—**adding only `jmh-core` is not enough**.

Example structure:

~~~text
pattern-jmh/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── bench/
                └── PatternJmh.java
~~~

### Complete `pom.xml` File

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.example</groupId>
    <artifactId>pattern-jmh</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>21</release>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <finalName>benchmarks</finalName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation=
                                    "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:

- `jmh-core` provides annotations, the runtime, and the benchmark execution engine.
- `jmh-generator-annprocess` runs at compile time to generate JMH support classes.
- `maven-compiler-plugin` uses `--release 21` to support record patterns.
- `maven-shade-plugin` packages the code and dependencies into a JAR with JMH as `Main-Class`.

The example pins **JMH 1.37** so the configuration is reproducible. When upgrading versions, update `jmh-core` and `jmh-generator-annprocess` together. Do not assume that a version written in this article is the latest version at all times.

**Execution prerequisites:** JDK 21+ and Maven, along with permission to download dependencies or an existing Maven cache. If JMH does not recognize the benchmarks, check annotation processing and the list of generated benchmarks instead of assuming the command measured successfully.

## 6. Complete `PatternJmh.java` File

Save in **`src/main/java/bench/PatternJmh.java`**:

~~~java
package bench;

import java.util.SplittableRandom;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class PatternJmh {
    record Order(int units, String sku) {}
    record Payment(String currency, long cents) {}

    @State(Scope.Thread)
    public static class Input {
        private static final int SIZE = 4096;

        @Param({"0", "50", "90"})
        public int orderPercent;

        private Object[] values;
        private int cursor;

        @Setup(Level.Trial)
        public void setup() {
            values = new Object[SIZE];
            cursor = 0;
            SplittableRandom random = new SplittableRandom(2026L);
            int paymentLimit =
                    orderPercent + (100 - orderPercent) / 2;

            for (int i = 0; i < values.length; i++) {
                int draw = random.nextInt(100);
                if (draw < orderPercent) {
                    values[i] = new Order(
                            1 + random.nextInt(20), "AB");
                } else if (draw < paymentLimit) {
                    values[i] = new Payment(
                            "USD", 100 + random.nextInt(1000));
                } else {
                    values[i] = (i & 1) == 0 ? null : "ignored";
                }
            }
        }

        Object next() {
            int current = cursor;
            cursor = (current + 1) & (SIZE - 1);
            return values[current];
        }
    }

    static long classicScore(Object x) {
        if (x instanceof Order) {
            Order o = (Order) x;
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment) {
            Payment p = (Payment) x;
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long typePatternScore(Object x) {
        if (x instanceof Order o) {
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment p) {
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long recordPatternScore(Object x) {
        if (x instanceof Order(var units, var sku)) {
            return 31L * units + sku.length();
        }
        if (x instanceof Payment(var currency, var cents)) {
            return cents % 97 + currency.length();
        }
        return 0;
    }

    @Benchmark
    public long classic(Input input) {
        return classicScore(input.next());
    }

    @Benchmark
    public long typePattern(Input input) {
        return typePatternScore(input.next());
    }

    @Benchmark
    public long recordPattern(Input input) {
        return recordPatternScore(input.next());
    }
}
~~~

Each `@Benchmark` returns a `long` value so the harness observes the result instead of letting the computation be optimized away. Data is created in `@Setup(Level.Trial)`, so no new records are allocated on the measured path.

### Why Use `Input.next()`?

`Input` holds an array of 4096 values of various types. `next()` retrieves **one** element and advances the cursor to the next position. `SIZE == 4096` is a power of two, so `(cursor + 1) & (SIZE - 1)` acts as an index wrap-around.

Returning one element per invocation to the harness avoids the anti-pattern of manually looping millions of times inside a `@Benchmark` body. JMH can measure many invocations without requiring the author to manually divide total time by loop count.

**Measurement scope:** the `ns/op` number includes **array read, cursor update, and the classification/scoring operation**. This is the cost of the defined benchmark operation, **not** a single `instanceof` opcode in isolation. The data access cost is shared across all three approaches; when it is large compared to a small pattern difference, the results will be hard to distinguish.

### Why Are Multiple Input Ratios Needed?

`@Param({"0", "50", "90"})` creates three configurations with target `Order` ratios of approximately 0%, 50%, and 90%. The remainder consists of `Payment`, `null`, and non-matching strings.

- Changing subtype ratios alters the number of branch checks and branch prediction behavior.
- The fixed seed `2026L` ensures trials in the same configuration regenerate a reproducible data sequence.
- Actual ratios are **approximate** to the parameter because generation is probabilistic; there is no guarantee of the exact count of each type.
- All `String` values in `Order`/`Payment` are non-null so all three scoring methods share the same contract.

`@State(Scope.Thread)` creates per-thread state, preventing other threads from concurrently incrementing `cursor`. When a real application involves concurrency, measure multi-threaded or contention scenarios separately; this example measures a single classification path without attempting to simulate all application contention.

### Meaning of JMH Configuration

- `@BenchmarkMode(Mode.AverageTime)`: measures average time per operation.
- `@OutputTimeUnit(TimeUnit.NANOSECONDS)`: reports `ns/op`.
- `@Warmup(iterations = 3, time = 1)`: three warm-up iterations, approximately one second each.
- `@Measurement(iterations = 5, time = 1)`: collects data from five measurement iterations.
- `@Fork(2)`: runs two independent JVM forks to reduce dependence on a single JVM process.
- `@Param`: outputs separate results per workload configuration.

This is a reproducible learning configuration, **not an absolute guarantee that the numbers have stabilized**. For very small differences, you may need to increase the number of forks/iterations or review background tasks, CPU temperature, and input representativeness.

## 7. Building, Running, and Saving Results

From the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar 'bench.PatternJmh.*'
~~~

The first command builds the benchmark JAR with dependencies. The `-l` command lists discovered benchmarks; verify that `classic`, `typePattern`, and `recordPattern` are all present. The last command runs all three approaches across the defined `@Param` values.

Run a single benchmark:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.recordPattern'
~~~

Save JSON results:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.*' -rf json -rff result.json
~~~

`result.json` is generated by JMH when running the command and is not included in this document. Use `java -jar target/benchmarks.jar -h` to view all options supported by the running JMH version.

**There is no "standard" benchmark stdout in nanoseconds**: results depend on JVM, CPU, OS, memory, machine load, branch prediction, and many other factors. Because the actual JMH workload has not been executed on the target environment, this article does not fabricate `Score` numbers and does not declare a winning version.

Further reading: [Official JMH](https://github.com/openjdk/jmh) and [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples).

## 8. Reading JMH Results Properly

In `Mode.AverageTime`, a JMH table typically has these columns:

| Column | Meaning |
| --- | --- |
| `Benchmark` | The benchmark method being measured |
| `(orderPercent)` | The input ratio parameter currently running |
| `Mode` | `avgt`: average time |
| `Cnt` | Number of statistical data points from measurements |
| `Score` | Central estimate of the time |
| `Error` | Statistical error reported by JMH; does **not** cover all bias from experiment design |
| `Units` | `ns/op`, nanoseconds per invocation for the defined workload |

For `ns/op`, **lower is faster** under the same conditions. You must compare **at the same `orderPercent`**. Do not compare `classic(orderPercent=0)` with `recordPattern(orderPercent=90)` because those are two different workloads.

**Purely hypothetical example** of how to interpret results:

- Approach A: `12.0 ± 0.5 ns/op`.
- Approach B: `11.8 ± 0.6 ns/op`.

Do not conclude that B is definitely faster just from `11.8 < 12.0`. A 0.2 ns difference is small compared to the reported error margin; you must check stability and run further measurements. These numbers **are not measured results from the code in this article**.

Even when a difference is statistically clear, you still need to consider **practical significance**: if pattern dispatch accounts for a tiny fraction of a request and does not affect production latency/throughput, refactoring solely to save a few nanoseconds may not be worth trading off readability.

## 9. JVM Pitfalls When Benchmarking Pattern Matching

### 9.1. JIT Warm-Up and Compilation Tiers

Early runs may use the bytecode interpreter, compile at different tiers, or still be accumulating profiling data. Short measurements easily reflect the startup phase rather than the hot execution path.

**How to handle:** warm up, inspect per-iteration trends, and run multiple JVM forks. If production cares about cold-start, design a **separate cold-start** benchmark instead of treating warm-up data as startup measurements.

### 9.2. Dead-Code Elimination

~~~java
// Illustrative anti-pattern: not a standalone benchmark.
@Benchmark
public void broken() {
    score(fixedValue); // Result is unused.
}
~~~

The JIT can eliminate work that has no observable effect. In the main JMH code, the methods return a `long` result to the harness. For multiple results, you can use JMH's `Blackhole`. **Do not add `System.out.println` in the measured path** because I/O will dominate most of the pattern cost.

### 9.3. Constant Folding and Devirtualization

A benchmark that always processes `new Order(1, "A")` may be optimized as a single constant type case. The multi-type array in the example helps avoid an unrealistic workload, but it does not prove that all JIT optimizations match a production system.

**How to handle:** choose representative data, vary ratios according to controlled scenarios, and verify on the target JVM version.

### 9.4. Loop Hoisting and Unrolling

Manually looping millions of times and dividing the result can make each iteration artificially cheap because the JIT moves computations outside the loop or merges operations. OpenJDK JMH Samples has examples explaining why **you should not add your own loop just to make `ns/op` numbers look better**.

**How to handle:** let the harness call one processing step per invocation; if the business case requires measuring an entire batch, explicitly define the batch as one operation and interpret the result units accordingly.

### 9.5. Branch Prediction and Data Layout

If 90% of inputs are `Order`, the CPU can predict the `Order` branch better. If ratios are mixed, nulls appear frequently, or objects are scattered in memory, measurements can differ.

**How to handle:** record the type distribution and dataset size. Do not compare two implementations on two different distributions and attribute the difference to syntax.

### 9.6. Allocation and Escape Analysis

A record pattern is used to **match and deconstruct an existing record object**; the deconstruction syntax does not by default allocate a copy of the record. Conversely, if you call `new Order(...)` inside the measured method, the results will mix allocation cost with dispatch.

**How to handle:** create data in `@Setup` if you want to measure classification. Use a separate experiment if the goal is object instantiation cost.

### 9.7. Results Too Small to Be Actionable

When the cost is only a few nanoseconds, clock noise, CPU frequency, and general benchmark overhead can account for a significant share. Measurements must be reproducible; consider **effect size**, not just the central value.

**How to handle:** repeat measurements, check error margins, vary workloads, and verify whether there is any impact on the real application.

## 10. Extended Experiment: Pattern Switch and Null

Java 21 also allows comparing `if + instanceof` with `switch` using record patterns:

~~~java
// Illustrative method in a scope containing the Order and Payment records.
static long switchPattern(Object x) {
    return switch (x) {
        case Order(var units, var sku) ->
                31L * units + sku.length();
        case Payment(var currency, var cents) ->
                cents % 97 + currency.length();
        case null -> 0;
        default -> 0;
    };
}
~~~

This method has the same return contract as the three approaches above. `case null` is important because in a Java 21 pattern switch, `default` does not automatically catch a null selector.

To benchmark this version:

1. Add `switchPatternScore(Object x)` to the JMH class with the logic above.
2. Add a `@Benchmark` returning `switchPatternScore(input.next())`.
3. Extend the equivalence tests before measuring.
4. Compare under the same `orderPercent` distributions and the same JMH parameters.

Do not assume `switch` definitely uses a jump table or is always faster than multiple `if`s. A pattern switch can be compiled differently depending on the case, JDK, and JIT. To explain differences, you must measure and, if needed, further analyze bytecode/generated machine code with specialized tools.

## 11. Do Not Stop at Microbenchmarks: Allocation, GC, and Real Applications

A syntax change may produce a small difference in an isolated measurement, but the real execution path may spend far more time on I/O, serialization, queries, and networking.

Appropriate next steps include:

- Run JMH with the GC profiler when you want to observe allocation/GC of the workload.
- Use a CPU profiler to determine actual time spent in pattern dispatch compared to other work.
- Measure p50/p95/p99 latency or throughput of the real pipeline under a controlled load scenario.
- Also test concurrent load if the application runs across multiple threads.
- Monitor effectiveness after changes in an environment close to production.

Example:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.*' -prof gc
~~~

A profiler can alter measurements, so clearly note when a profiler is enabled and compare carefully against runs without a profiler. If the workload here allocates almost nothing inside `@Benchmark`, **do not extrapolate** that all code using record patterns is allocation-free: the records were already created in `@Setup`.

## 12. Reproducible Benchmark Workflow

A practical workflow:

1. **State a clear hypothesis:** "Under a 50% Order load, record pattern reduces average cost by at least 5% compared to cast."
2. **Verify correctness:** run `PatternBenchmarkCheck` and add tests for edge cases of the real application.
3. **Choose a representative workload:** subtype ratios, nulls, other types, data structures, and array sizes.
4. **Use JMH with warm-up/forks:** avoid a single run outside the IDE with a manual stopwatch.
5. **Keep the environment stable:** JVM, CPU, OS, memory, GC, JVM flags, background tasks.
6. **Record experiment metadata:** JDK/JMH versions, source revision, parameters, and JSON results.
7. **Read both score and error:** do not rank solely based on a single number.
8. **Check sensitivity:** test multiple type ratios and datasets matching production scenarios.
9. **Cross-check end-to-end performance:** does the microbenchmark improvement actually affect users?
10. **Decide with readability in mind:** if performance is equivalent or the difference is negligible, prefer code that is clearer, easier to review, and less error-prone.

When real work spends most of its time waiting on I/O, changing pattern syntax may not be an optimization priority. Benchmarks help decide **where to invest**, rather than proving beforehand that one syntax is faster.

## 13. Common Mistakes and How to Avoid Them

**Mistake 1 — benchmarking on a single constant object.** The JIT can aggressively optimize a single-subtype case. Use data with type ratios resembling real load.

**Mistake 2 — measuring non-equivalent algorithms.** A version that skips null or a calculation will be faster because **it does less work**, not because the pattern is better.

**Mistake 3 — allocating data inside `@Benchmark`.** `new` and GC costs can drown out dispatch. Use `@Setup` when not measuring allocation.

**Mistake 4 — discarding results or logging in the measured path.** Discarding results can cause dead-code elimination; logging turns the experiment into an I/O measurement. Return results to JMH or use `Blackhole`.

**Mistake 5 — manually looping millions of times.** Dividing loop time does not guarantee reflecting individual operations; the JIT can unroll, hoist, or merge work. Let JMH control invocations.

**Mistake 6 — running only once, without warm-up or forks.** Noise and JIT compilation make measurements unreliable.

**Mistake 7 — treating `Error` as a guarantee of no bias.** Statistical error does not eliminate workload design flaws, an overloaded machine, or optimized-away computations.

**Mistake 8 — calling `ns/op` "request time".** Results apply only to the operation defined in the benchmark, not the entire API.

**Mistake 9 — comparing different input configurations.** Always compare under the same `orderPercent`, JVM, and environmental conditions.

**Mistake 10 — optimizing at the expense of readability when differences are negligible.** When timings are similar, readability and safety are usually more important than a small, unreproducible difference.

**Mistake 11 — treating a record pattern as record allocation.** Patterns deconstruct existing records. Allocation must be measured and analyzed separately.

**Mistake 12 — forgetting the null contract when adding `switch`.** In a Java 21 pattern switch, omitting `case null` can lead to a `NullPointerException` whereas `instanceof` returns false. Both versions must have the same behavior before benchmarking.

## 14. Checklist Before Publishing Results

| Question | Requirement |
| --- | --- |
| Do all approaches produce the same result? | Comparison tests exist, including null and other types |
| Is the input representative of the application? | Subtype ratios, data, and seed are documented |
| Is data created outside the measured path? | Yes, unless allocation itself is the target |
| Are results consumed by JMH? | Yes |
| Are warm-up and multiple forks used? | Yes |
| Are JVM/JDK, CPU, OS, and flags recorded? | Yes |
| Are comparisons made with the same workload parameters? | Yes |
| Are score and error evaluated together? | Yes |
| Is end-to-end impact evaluated? | When using results to optimize an application |
| Are extrapolations from microbenchmarks avoided? | Conclusions are scoped to the measured conditions |

### Practice Exercises

1. Add `switchPatternScore` to the test program, ensure all four versions produce the same results across all 12 cases, then add the corresponding JMH benchmark.
2. Change `@Param({"0","50","90"})` to a different range of ratios and explain the differences in terms of branch prediction.
3. Create an `Order`-only workload, compare it with a mixed workload, and analyze why the two results should not be used interchangeably.
4. Add the GC profiler; distinguish records created in `@Setup` from allocations inside `@Benchmark`.
5. Take a real business processing path and compare the percentage of CPU spent on pattern classification with the time spent on parsing, I/O, and queries.

**Remember:** To measure pattern matching performance, first prove that **all approaches do the same work**, then use JMH with warm-up, forks, a representative workload, and consumed results. Do not conclude that pattern syntax is always faster than casting or that a pattern switch is always faster than `if` based on intuition or a single stopwatch number. **Measure, check stability, state limitations, and prioritize readability when performance differences are not significant.**