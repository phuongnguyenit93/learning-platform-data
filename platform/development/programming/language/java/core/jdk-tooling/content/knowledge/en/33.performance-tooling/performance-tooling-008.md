# Benchmarking Java with JMH

## 1. What is Benchmarking?

**Benchmarking** is the process of measuring the performance of a program or a part of a program under controlled conditions. The goal is to understand how a change affects processing time, throughput, latency, memory allocation, and scalability.

A good benchmark must answer three questions:

1. Which exact operation is being measured?
2. Are the measurement conditions representative of how the application actually runs?
3. Are the results stable and repeatable enough for comparison?

In Java, measurements can be strongly influenced by the JVM and the JIT compiler. A piece of code that runs fast on the first execution might become slower after class loading, JIT compilation, or garbage collection occurs. Therefore, Java benchmarks need to account for warmup, forks, input data, threads, and runtime state.

## 2. Microbenchmark vs. Macrobenchmark

| Benchmark Type | Scope | Example | Suitable Tools |
|---|---|---|---|
| Microbenchmark | A small method or operation | String concatenation, number parsing, collection lookup | JMH |
| Component benchmark | A component with multiple methods and dependencies | Serializer, cache client, repository | JMH or a custom controlled harness |
| Macrobenchmark | A complete business flow | Processing an HTTP request or batch job | Load testing and production-like tests |
| System/load test | The entire system under concurrent load | Throughput, p95/p99 latency, saturation | Gatling, k6, JMeter, and system metrics |

JMH is designed for microbenchmarks on the JVM. It does not automatically prove that an HTTP endpoint or an entire system will be faster in production.

If you need to evaluate a business flow, measure it with a realistic workload that includes network, database, cache, concurrency, and representative data. You can use JMH to find the cost of a small operation within that flow.

## 3. Why You Should Not Measure with a Manual nanoTime Loop

A common approach to measurement:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    calculate();
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

This code easily produces misleading results:

- The JIT has not warmed up yet or is compiling the method during measurement.
- Dead-code elimination may remove unused results.
- Constant folding may precompute expressions that only depend on constants.
- Inlining, escape analysis, and scalar replacement may alter the executed code.
- Large loops may be unrolled or optimized in ways that do not resemble the real operation.
- Timer, loop overhead, GC, and scheduling can account for a large share of very short operations.
- A single run does not reflect variance across JVM processes.

System.nanoTime() is the appropriate clock for measuring monotonic elapsed time in Java, but writing a loop yourself does not replace a benchmark harness with controlled warmup, measurement, forks, and result consumption.

## 4. What Problems Does JMH Solve?

**Java Microbenchmark Harness (JMH)** is an OpenJDK toolkit for building and running Java microbenchmarks.

JMH provides:

- An annotation processor that generates the benchmark harness for marked methods.
- Separate warmup and measurement iterations.
- Forking JVM processes to reduce the impact of JIT state from other benchmarks.
- Thread and state management according to declared scopes.
- Benchmark modes such as average time, throughput, and sample time.
- Blackhole to prevent results from being optimized away.
- Built-in profilers to inspect allocation, GC, and runtime information.
- Statistical results across multiple iterations instead of a single measurement.

JMH helps standardize how measurements are taken, but it cannot automatically fix a benchmark with an unrepresentative workload, unsuitable data, or uncontrolled comparisons.

## 5. Creating a Maven Project with JMH

The example below uses JMH 1.37, Java release 17, Maven Compiler Plugin 3.13.0, and Maven Shade Plugin 3.6.0.

Directory structure:

~~~text
jmh-demo/
  pom.xml
  src/
    main/
      java/
        benchmarks/
          StringJoinBenchmark.java
~~~

Create **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>jmh-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
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
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
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

jmh-core provides the benchmark API and runner. jmh-generator-annprocess is declared as an annotation processor to generate harness code at compile time. The shade plugin packages dependencies and sets the entry point to org.openjdk.jmh.Main.

From the directory containing pom.xml, build:

~~~bash
mvn package
~~~

If the build succeeds, the executable JAR is created at:

~~~text
target/benchmarks.jar
~~~

A fresh machine may need to download dependencies from the Maven repository on the first build.

## 6. Writing Your First Benchmark

Create **StringJoinBenchmark.java**:

~~~java
package benchmarks;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 2, time = 200, timeUnit = TimeUnit.MILLISECONDS)
@Measurement(iterations = 3, time = 200, timeUnit = TimeUnit.MILLISECONDS)
@Fork(1)
public class StringJoinBenchmark {
    @Param({"8", "64"})
    public int elements;

    private String[] parts;

    @Setup(Level.Trial)
    public void setup() {
        parts = new String[elements];
        for (int i = 0; i < elements; i++) {
            parts[i] = "item-" + i;
        }
    }

    @Benchmark
    public String plusInLoop() {
        String result = "";
        for (String part : parts) {
            result += part;
        }
        return result;
    }

    @Benchmark
    public String stringBuilder() {
        StringBuilder result = new StringBuilder();
        for (String part : parts) {
            result.append(part);
        }
        return result.toString();
    }
}
~~~

The benchmark compares two ways of joining the same string array:

- plusInLoop uses the string concatenation operator inside a loop.
- stringBuilder uses StringBuilder.append().

The input array is created in setup(), not inside the measured methods. @Param runs the benchmark with two input sizes. Each benchmark method returns its result so JMH consumes it, preventing the result from being eliminated as dead code.

This example illustrates how to structure a benchmark; it does not claim StringBuilder is always faster for every workload. Results depend on string sizes, JDK, data, garbage collector, and runtime environment.

## 7. Meaning of Key Annotations

| Annotation | Role |
|---|---|
| @Benchmark | Marks a method to be measured. |
| @State | Declares a state object and its sharing scope. |
| @Param | Provides multiple input values for a benchmark. |
| @Setup | Prepares state before a trial, iteration, or invocation. |
| @TearDown | Releases or resets state at the corresponding lifecycle level. |
| @BenchmarkMode | Selects how performance is expressed. |
| @OutputTimeUnit | Selects the time unit for displaying results. |
| @Warmup | Configures warmup iterations. |
| @Measurement | Configures measurement iterations. |
| @Fork | Number of independent JVM processes used to run the benchmark. |
| @Threads | Number of threads running the benchmark. |
| @OperationsPerInvocation | Declares the number of logical operations in a single benchmark method call. |

Benchmark methods are typically public, can accept state parameters supported by JMH, and return a value or void. Do not call benchmark methods directly from main to get results; let the JMH runner control the lifecycle.

## 8. Warmup, Measurement, and Fork

These three concepts are critical for the JVM.

### Warmup

Warmup runs the benchmark before recording measurement results. It gives the JVM time to perform class loading, profiling, and JIT compilation.

Example:

~~~java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Five warmup iterations of one second each is an example configuration. Complex workloads may require longer warmups. Do not assume a fixed number of iterations will always stabilize every benchmark.

### Measurement

Measurement is the phase where JMH collects metrics.

~~~java
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Multiple iterations help observe variance across measurements. Measurements that are too short can be noisy due to scheduling, GC, or background activity.

### Fork

Forking runs the benchmark in a fresh JVM process. This isolates JIT profiles, heap state, and runtime state across trials.

~~~java
@Fork(3)
~~~

Three forks create three independent JVM processes. When comparing two implementations, use the same fork count, warmup, measurement, and JVM arguments.

Warmup does not replace forks, and forks do not replace measurement. Together, all three make results more reliable.

## 9. Benchmark Modes

JMH supports multiple modes:

| Mode | Meaning | Common Units |
|---|---|---|
| Throughput | Number of operations completed per unit of time. | ops/s |
| AverageTime | Average time per operation. | ns/op, us/op, ms/op |
| SampleTime | Samples operation execution times to show distribution. | ns/op and percentiles |
| SingleShotTime | Measures individual single-shot executions in an iteration. | ns/op, us/op |
| All | Runs all modes supported by JMH. | Depends on mode |

Choose the mode based on your question:

- Want to know how many requests/operations a method handles per second: Throughput.
- Want to know how long an operation takes on average: AverageTime.
- Want to see time distribution and percentiles: SampleTime.
- Want to measure one-shot or cold-path behavior: SingleShotTime, while designing forks/warmup appropriately.

Example AverageTime configuration:

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
~~~

You can use another mode via annotation or command line:

~~~java
@BenchmarkMode(Mode.Throughput)
~~~

~~~bash
java -jar target/benchmarks.jar -bm thrpt
~~~

Do not directly compare scores from two different modes as if they share the same unit.

## 10. State Scope and Concurrency

@State defines how a state object is shared across threads.

| Scope | Sharing Behavior | Use Case |
|---|---|---|
| Scope.Thread | Each benchmark thread has its own state. | Measuring independent operations, avoiding contention from shared state. |
| Scope.Benchmark | All threads in the benchmark share one state instance. | Measuring shared data structures or resources. |
| Scope.Group | State is shared within a thread group. | Simulating reader/writer groups or workloads with distinct roles. |

Example:

~~~java
@State(Scope.Thread)
public class ThreadLocalState {
    int counter;
}
~~~

With Scope.Benchmark, multiple threads can access the same object. If the benchmark updates shared data, you must handle thread safety just as in a real application. Synchronization, lock contention, and false sharing can become part of the measured cost.

You can set the thread count on the command line:

~~~bash
java -jar target/benchmarks.jar -t 4
~~~

Do not assume increasing threads always increases throughput. When contention, memory bandwidth, or CPU saturation occurs, throughput can plateau and latency can increase.

## 11. Lifecycle-Based Setup and Teardown

JMH has three commonly used lifecycle levels:

| Level | When It Runs | Used For |
|---|---|---|
| Trial | Once per trial of the state. | Creating data or resources shared across the entire benchmark trial. |
| Iteration | Before/after each warmup or measurement iteration. | Resetting data between iterations. |
| Invocation | Before/after each call to the benchmark method. | Preparing very specific state for each invocation. |

Example:

~~~java
@Setup(Level.Trial)
public void setupTrial() {
    // Create data used in the trial.
}

@Setup(Level.Iteration)
public void setupIteration() {
    // Reset state between iterations.
}
~~~

Setup/teardown execution time is not directly counted as benchmark method execution, but preparing state can still affect caches, GC, and runtime behavior.

Avoid @Setup(Level.Invocation) for very short operations unless truly necessary. Lifecycle overhead, allocation, and data warming on every invocation can make the workload diverge from the real application.

## 12. Dead-Code Elimination and Blackhole

The JIT may eliminate computations if their results are not used. Example:

~~~java
@Benchmark
public void brokenBenchmark() {
    calculateValue();
}
~~~

If calculateValue() has no side effects and its result is unused, the compiler may eliminate part or all of the work.

The simplest approach is to return the result:

~~~java
@Benchmark
public int returnResult() {
    return calculateValue();
}
~~~

JMH automatically consumes the return value of the benchmark method.

If you need to consume multiple results or the method must return void, use Blackhole:

~~~java
import org.openjdk.jmh.infra.Blackhole;

@Benchmark
public void consumeResult(Blackhole blackhole) {
    int value = calculateValue();
    blackhole.consume(value);
}
~~~

There is no need to create a shared volatile field yourself just to retain results. Writing to a volatile field has its own cost and can alter the operation being measured.

Blackhole prevents dead-code elimination, but it does not guarantee the benchmark reflects a real-world workload. Inspect generated code or use a profiler if you suspect unexpected optimizations.

## 13. Constant Folding, Inlining, and Input Data

An expression that depends only on constants can be precomputed:

~~~java
@Benchmark
public int constantExpression() {
    return 42 * 42;
}
~~~

This benchmark might measure returning a precomputed constant instead of the multiplication the author intended.

Use runtime-meaningful input data:

~~~java
@State(Scope.Thread)
public class CalculationBenchmark {
    @Param({"17", "29", "41"})
    public int input;

    @Benchmark
    public int square() {
        return input * input;
    }
}
~~~

JMH runs multiple trials with the @Param values. However, @Param does not prevent all optimizations; ensure the data and operations still represent realistic cases.

Inlining and escape analysis are valid JVM optimizations. Do not try to disable every optimization just to produce a nice-looking number. If the real application benefits from those JIT optimizations, the benchmark should reflect that.

## 14. Loops and OperationsPerInvocation

Do not wrap a small operation in a large loop just to extend measurement time:

~~~java
@Benchmark
public int looped() {
    int result = 0;
    for (int i = 0; i < 1000; i++) {
        result += calculate(i);
    }
    return result;
}
~~~

The loop may be unrolled, vectorized, or optimized differently than individual invocations. JMH already invokes the benchmark method enough times to collect samples.

If the actual business logic processes a fixed batch, a loop in the benchmark is reasonable. You can use:

~~~java
@OperationsPerInvocation(1000)
~~~

to declare that one benchmark method call corresponds to 1000 logical operations and normalize the score by that operation count.

Only use this annotation when the operation count is truly fixed and every invocation always executes the exact declared number. For variable-size batches, interpret scores and units clearly.

## 15. Allocation and Garbage Collection

Allocation benchmarks should measure both allocation cost and GC impact if that is part of the workload's behavior.

You can use the built-in GC profiler:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

Common metrics:

- gc.alloc.rate: memory allocation rate.
- gc.alloc.rate.norm: normalized bytes allocated per operation.
- gc.count: number of garbage collections during measurement.
- gc.time: total GC time recorded by the profiler.

If one implementation is faster but allocates more objects, its advantage may disappear over long runs or under high load.

Do not disable GC by default when benchmarking allocation. Only change GC configuration when the primary goal is comparing collectors or measuring the impact of a specific flag.

## 16. Profiling Benchmarks

When a benchmark appears slow, you need to know where time is being spent.

Profilers you can use with JMH:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

On Linux, depending on the system and permissions, you can try the perf-based profiler:

~~~bash
java -jar target/benchmarks.jar -prof perf
~~~

Profilers depend on the OS, kernel, permissions, and installed tools. Do not assume every profiler works on Windows or inside containers.

You can use Java Flight Recorder or async-profiler to inspect CPU samples, allocations, locks, and call stacks. When profiling, separate metrics from a profiled run from non-profiled benchmark results because the profiler itself can add overhead.

## 17. Running Benchmarks and Listing Available Benchmarks

After building:

~~~bash
java -jar target/benchmarks.jar -l
~~~

With the sample project, JMH lists:

~~~text
Benchmarks:
benchmarks.StringJoinBenchmark.plusInLoop
benchmarks.StringJoinBenchmark.stringBuilder
~~~

Run both benchmarks with a longer measurement configuration:

~~~bash
java -jar target/benchmarks.jar 'benchmarks.StringJoinBenchmark.*' -wi 5 -i 8 -f 3 -w 1s -r 1s -t 1
~~~

Parameter meanings:

| Parameter | Meaning |
|---|---|
| -wi 5 | Five warmup iterations. |
| -i 8 | Eight measurement iterations. |
| -f 3 | Three independent JVM forks. |
| -w 1s | Each warmup iteration lasts one second. |
| -r 1s | Each measurement iteration lasts one second. |
| -t 1 | One benchmark thread. |

Run a short configuration to verify the project or debug the harness:

~~~bash
java -jar target/benchmarks.jar 'benchmarks.StringJoinBenchmark.*' -p elements=8 -wi 1 -i 2 -f 1 -w 100ms -r 100ms
~~~

A short configuration is suitable for smoke tests. Do not use scores from one warmup iteration, two measurement iterations, and one fork to draw performance optimization conclusions.

## 18. Saving Results and Comparing

You can export results to JSON:

~~~bash
java -jar target/benchmarks.jar -rf json -rff results.json
~~~

A JMH result typically contains these fields:

| Field | Meaning |
|---|---|
| Benchmark | Name of the measured method. |
| Mode | Benchmark mode. |
| Cnt | Number of iterations used to compute the result. |
| Score | Measured performance value. |
| Error | Reported statistical error margin. |
| Units | Unit of the score. |

When comparing two implementations:

1. Run on the same machine and same JVM configuration.
2. Use the same JDK, GC, JVM flags, and thread count.
3. Keep warmup, measurement, forks, and input data identical.
4. Compare within the same benchmark mode and same units.
5. Check error margins and variance across forks.
6. Re-run if results vary significantly between runs.
7. Record the commit, JDK, CPU, OS, and command line.

Differences smaller than the noise level do not prove one implementation is better. Prioritize looking at improvement ratio, variance range, allocation, and impact on real workloads.

## 19. Controlling the Benchmark Environment

Performance depends on both code and execution environment.

Before measuring, record:

- CPU model, core count, and hyper-threading configuration.
- RAM and disk type if the benchmark involves I/O.
- OS, kernel, and JDK version.
- JVM vendor, GC, heap size, and JVM flags.
- CPU frequency scaling, turbo boost, and thermal throttling.
- Other processes consuming CPU.
- Container CPU quota, memory limit, and cgroup if applicable.
- Power source and power plan on laptops.

Avoid running benchmarks alongside large builds, antivirus scans, backups, or other CPU/I/O-contending workloads. If measuring inside a container, record the CPU quota and memory limit so others can reproduce the conditions.

Do not compare absolute numbers between two differently configured machines without normalizing the environment. When upgrading the JDK or changing CPUs, establish a new baseline.

## 20. Common Benchmarking Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Measuring once with nanoTime | Affected by JIT, GC, and scheduling. | Use JMH with warmup, measurement, and forks. |
| No warmup | Mixes interpreter and JIT compilation into measurements. | Configure sufficient warmup for the workload. |
| No forks | Earlier benchmarks warm up or alter profiles for later ones. | Use multiple independent JVM forks. |
| Not consuming results | JIT eliminates computations without side effects. | Return the result or use Blackhole. |
| Using only constants | Constant folding can precompute the result. | Use state and representative runtime inputs. |
| Creating data inside benchmark method | Measures setup instead of the target operation. | Use @Setup when setup is not part of the workload. |
| Using too many threads | Introduces contention that does not exist in the real app. | Choose thread count based on the target workload. |
| Large loops inside the method | Loop unrolling and loop optimizations distort the unit of measurement. | Measure per operation or declare OperationsPerInvocation for real batches. |
| Disabling GC arbitrarily | Hides allocation and collection costs. | Measure GC with a profiler when appropriate. |
| Comparing profiled and non-profiled runs | Profiler overhead alters the score. | Compare runs with the same profiler or measure separately. |
| Using overly small datasets | Cache stays hot, unrepresentative of the workload. | Choose a dataset reflecting realistic size and distribution. |
| Looking only at average score | Ignores variance and latency distribution. | Inspect error, percentiles, and multi-fork results. |
| Comparing runs across environments | Cannot attribute differences to code. | Fix or record environment and JVM flags. |

## 21. Repeatable Benchmarking Workflow

A practical workflow:

1. Define the hypothesis to test, e.g., changing a data structure will reduce lookup time.
2. Choose the right scope: microbenchmark, component benchmark, or load test.
3. Implement the baseline and the candidate implementation to compare.
4. Choose input data with representative distribution and size.
5. Move setup out of the measured region if setup is not part of the workload.
6. Choose state scope and thread count matching how data is shared.
7. Select the benchmark mode matching the metric to measure.
8. Configure sufficiently long warmup, measurement, and forks.
9. Run the benchmark without profilers to get the baseline.
10. Run profilers separately when needed to explain root causes.
11. Save JSON, command line, JVM flags, and machine info.
12. Repeat measurements and check variance.
13. Evaluate throughput, latency, allocation, and GC together.
14. Validate improvements in a broader benchmark or production-like workload.
15. Draw conclusions only when results are stable and the cause is explained.

## 22. Example Project Verification Results

The sample project above was built with Maven using Java release 17 and JMH 1.37. Running the JMH runner on JDK 24.0.2 listed the two benchmarks:

~~~text
Benchmarks:
benchmarks.StringJoinBenchmark.plusInLoop
benchmarks.StringJoinBenchmark.stringBuilder
~~~

A short smoke run executed both methods successfully and exited with code 0. Because the smoke run only used one fork, one warmup iteration, and two short measurement iterations, its scores only confirm the harness works; do not use them to conclude which approach is faster.

JMH 1.37 on JDK 24.0.2 may print deprecation warnings related to sun.misc.Unsafe inside JMH internals. During verification, the warnings did not cause the build or benchmark to fail. When upgrading JDK/JMH, check release notes and re-verify the harness.

## 23. Checklist Before Trusting a Benchmark

- [ ] Identified the exact operation and unit to measure.
- [ ] Chose the appropriate microbenchmark or macrobenchmark approach.
- [ ] Used JMH for JVM microbenchmarks.
- [ ] Verified results are not eliminated by dead-code elimination.
- [ ] Avoided constant folding from constant inputs.
- [ ] Moved setup outside the measured region where appropriate.
- [ ] Chose Scope.Thread, Scope.Benchmark, or Scope.Group to match the goal.
- [ ] Selected the benchmark mode matching the metric.
- [ ] Configured separate warmup, measurement, and forks.
- [ ] Checked allocation and GC if the workload creates objects.
- [ ] Ran profilers separately when investigating root causes.
- [ ] Kept thread count, JVM flags, and environment stable.
- [ ] Reviewed error margins, variance, and multi-fork results.
- [ ] Saved JSON, command line, JDK, and hardware details.
- [ ] Validated improvements on a workload close to the real application.

## 24. References

- OpenJDK JMH project: https://github.com/openjdk/jmh
- JMH samples: https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples
- JMH Maven artifact: https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core
- Java SE 17 System.nanoTime(): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()

JMH helps build microbenchmarks with consistent warmup, measurement, forks, and result consumption. Results are only meaningful when the benchmark measures the right workload, uses representative data, controls the environment, and is repeated enough times to distinguish real improvements from measurement noise.