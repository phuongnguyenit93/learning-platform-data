# Measuring Execution Time in Java

Measuring execution time helps answer a specific question: how long does a piece of code, a task, or a request take to complete? In Java, the most common choice for measuring **elapsed time** is **System.nanoTime()**. If you need a calendar timestamp or start/end points for logging, use **Instant.now()** or **System.currentTimeMillis()**.

For a large block of code or a business operation, measuring with nanoTime is usually sufficient to know the actual duration. For microbenchmarks that need to compare very fast methods, use **JMH (Java Microbenchmark Harness)** to handle warm-up, JIT compilation, dead-code elimination, forking, and statistical error.

This article distinguishes between wall-clock time, elapsed time, and CPU time; explains how to measure accurately, convert units, handle async/concurrency, avoid JVM-induced bias, and build reliable benchmarks.

## 1. Three Types of Time to Distinguish

No single clock fits every question. Before writing code, determine which quantity you want to measure.

| Time Type | Question | Common API |
|---|---|---|
| Wall-clock time | What time is it now? When did an event occur? | Instant.now(), System.currentTimeMillis() |
| Elapsed time | How much time passed from start to finish? | System.nanoTime() |
| Thread CPU time | How long did a thread actually use the CPU? | ThreadMXBean |

### Wall-clock time

Wall-clock time represents a calendar point in time, typically measured from the Unix epoch. It is suitable for recording timestamps in logs, storing data creation times, or correlating events across multiple systems.

Example:

~~~java
Instant startedAt = Instant.now();
// Perform work
Instant finishedAt = Instant.now();

System.out.println("Started at: " + startedAt);
System.out.println("Finished at: " + finishedAt);
~~~

The system clock can be adjusted by NTP, administrators, hypervisors, or the operating system. Therefore, the difference between two wall-clock timestamps is not the best choice for measuring exact duration.

### Elapsed time

Elapsed time is the actual time that passes between two points within the same measurement process. It includes the time a thread runs on the CPU, is paused by the scheduler, waits for locks, waits for file/network I/O, and other waiting intervals.

Use System.nanoTime() for this purpose:

~~~java
long start = System.nanoTime();

performTask();

long elapsed = System.nanoTime() - start;
~~~

nanoTime has an arbitrary time origin, not a Unix timestamp. Its value can be negative and has no meaning when compared across two machines or across JVM runs. Only compute the difference between two readings within the same JVM.

### Thread CPU time

Thread CPU time measures the amount of CPU time a thread has actually used. It does not include time the thread spends sleeping or waiting for I/O.

For example, a request that takes 500 ms of elapsed time while the thread uses only 20 ms of CPU time might be waiting on the database, network, locks, or scheduler.

Use java.lang.management.ThreadMXBean when you need to separate CPU work from waiting. Support depends on the JVM and operating system.

## 2. System.nanoTime(): The Choice for Elapsed Time

System.nanoTime() returns the value of a high-resolution time source in nanoseconds. This method is designed for measuring elapsed time intervals.

Example:

~~~java
long start = System.nanoTime();

performTask();

long end = System.nanoTime();
long elapsedNanos = end - start;

System.out.println("Elapsed: " + elapsedNanos + " ns");
~~~

Formula to remember:

~~~java
elapsed = end - start;
~~~

Do not use end or start individually as a timestamp. Only the difference between two values is meaningful.

### Precision and Resolution Are Not the Same

The returned unit is nanoseconds, but that does not guarantee the clock updates every single nanosecond. Actual resolution depends on the operating system, hardware, and JVM.

- **Precision:** the level of detail in how a number is represented.
- **Resolution:** the smallest time interval the clock source can distinguish.
- **Accuracy:** how close the measurement is to the true time being measured.

A value with many decimal digits does not automatically mean the measurement is more accurate.

### Do Not Compare Absolute Values

Do not use nanoTime values as timestamps or global points in time. When checking timeouts, compare differences to avoid issues with the time source's arbitrary origin and potential value wrap-around:

~~~java
long start = System.nanoTime();
long timeoutNanos = TimeUnit.SECONDS.toNanos(5);

while (System.nanoTime() - start < timeoutNanos) {
    // Wait or check condition
}
~~~

Subtracting two nanoTime readings is the proper way to compute elapsed time. For practical application durations, wrap-around is not an issue; do not use absolute values as timestamps.

## 3. System.currentTimeMillis() and Instant.now()

### System.currentTimeMillis()

This method returns the number of milliseconds since the Unix epoch (1970-01-01T00:00:00Z).

~~~java
long timestamp = System.currentTimeMillis();
System.out.println("Epoch millis: " + timestamp);
~~~

Use it when you need a numeric timestamp compatible with legacy systems or APIs that accept epoch milliseconds.

Do not prefer currentTimeMillis for measuring very short durations because:

- Resolution may be coarser than nanoseconds.
- The system clock can be adjusted.
- Two consecutive readings may return the same value.
- Clock corrections can cause the difference not to reflect actual elapsed time.

### Instant.now()

Instant represents a point on the UTC timeline. It is better suited for strongly typed timestamps than long.

~~~java
Instant startedAt = Instant.now();

// Perform work

Instant finishedAt = Instant.now();
Duration elapsed = Duration.between(startedAt, finishedAt);

System.out.println("Started: " + startedAt);
System.out.println("Elapsed: " + elapsed);
~~~

Instant.now() still reads wall-clock time from the system clock. It is appropriate for recording points in time, but not the best choice for measuring elapsed time that requires monotonicity.

### When to Use Clock?

If business code needs to know the current time, consider injecting java.time.Clock instead of calling Instant.now() directly in many places. In tests, you can use Clock.fixed() to control time.

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Instant now = Instant.now(testClock);
~~~

Clock.fixed makes date/time-based logic tests repeatable. It does not replace nanoTime for benchmarking.

## 4. Converting Time Units

nanoTime returns nanoseconds. Common units:

| Unit | Conversion |
|---|---:|
| 1 microsecond (µs) | 1,000 ns |
| 1 millisecond (ms) | 1,000,000 ns |
| 1 second (s) | 1,000,000,000 ns |

You can convert units using division:

~~~java
long elapsedNanos = 1_234_567;

double elapsedMicros = elapsedNanos / 1_000.0;
double elapsedMillis = elapsedNanos / 1_000_000.0;
double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
~~~

Illustrative results:

- 1.234567 ms
- 1234.567 µs
- 0.001234567 s

Use floating-point numbers when you need to preserve fractional parts. If you divide two integers, the fractional part is truncated.

### Using TimeUnit

~~~java
long elapsedNanos = 1_234_567;

long millis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
long micros = TimeUnit.NANOSECONDS.toMicros(elapsedNanos);
~~~

Conversions to larger units return integers and truncate the fractional part. If you need to display down to microseconds or fractional milliseconds, use double or BigDecimal according to your reporting requirements.

### Using Duration

Duration represents a time interval:

~~~java
Duration duration = Duration.ofNanos(elapsedNanos);

System.out.println(duration.toNanos());
System.out.println(duration.toMillis());
System.out.println(duration.toSeconds());
~~~

toMillis() and toSeconds() return integers and therefore truncate fractional parts. Duration.toNanos() may throw ArithmeticException if the value exceeds the range of a long in nanoseconds.

Do not arbitrarily multiply elapsed by a large constant if it could cause long overflow. Compute the nanoTime difference first, then convert using an appropriate unit.

## 5. Measuring a Code Block Properly

A basic measurement should place start right before the region to measure and end right after that region completes.

~~~java
long start = System.nanoTime();

Result result = service.calculate(input);

long elapsed = System.nanoTime() - start;

System.out.printf(
        Locale.ROOT,
        "calculate took %.3f ms%n",
        elapsed / 1_000_000.0
);
~~~

Some principles:

- Place the timer around the exact region to be measured.
- Do not include logging, string formatting, or console output inside the measured region if they are not part of the work being measured.
- If measuring end-to-end, include all steps to be evaluated.
- If measuring a single method in isolation, do not accidentally include setup or teardown.
- Use the same measurement approach when comparing before and after optimization.
- Do not draw conclusions from a single run.

### Measuring Even When a Method Throws an Exception

If you need to record duration even when a task fails, use finally:

~~~java
long start = System.nanoTime();

try {
    service.process();
} finally {
    long elapsed = System.nanoTime() - start;
    metrics.recordDuration(elapsed);
}
~~~

If process() throws an exception, finally still runs and the duration is recorded. Make sure metrics.recordDuration() does not mask the original exception; in production systems, use a safe metrics-recording mechanism.

### Do Not Measure Too Many Things at Once

If the goal is to measure a database call, do not accidentally include JSON serialization, HTTP response rendering, and logging. Conversely, if the goal is user-perceived request latency, you must measure the entire relevant pipeline.

Set measurement boundaries based on the question you need to answer.

## 6. Java 17+ Example: Measuring Execution Time with nanoTime

The following program warms up the summation method first, then measures the average of five runs. The checksum result is used after the measurement to prevent the result from being eliminated.

Create the file **ExecutionTimeDemo.java**:

~~~java
import java.util.Locale;

public final class ExecutionTimeDemo {
    private static volatile long warmupSink;

    private static long sumUpTo(int limit) {
        long sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i;
        }
        return sum;
    }

    public static void main(String[] args) {
        final int limit = 1_000_000;
        final int warmupIterations = 20;
        final int measuredIterations = 5;

        for (int i = 0; i < warmupIterations; i++) {
            warmupSink = sumUpTo(limit);
        }

        long start = System.nanoTime();
        long checksum = 0;

        for (int i = 0; i < measuredIterations; i++) {
            checksum += sumUpTo(limit);
        }

        long elapsedNanos = System.nanoTime() - start;
        double averageMillis =
                elapsedNanos / 1_000_000.0 / measuredIterations;

        System.out.println("Checksum: " + checksum);
        System.out.printf(
                Locale.ROOT,
                "Average: %.3f ms/op%n",
                averageMillis
        );
    }
}
~~~

Compile:

~~~bash
javac --release 17 ExecutionTimeDemo.java
~~~

Run:

~~~bash
java ExecutionTimeDemo
~~~

The checksum line has a deterministic value:

~~~text
Checksum: 2499997500000
~~~

The timing line has the form:

~~~text
Average: <varying value> ms/op
~~~

The timing value varies depending on CPU, JDK, operating system, machine load, and JIT/GC state. This is an example for learning how to place a timer, not a reliable benchmark for comparing two algorithms.

## 7. Measuring Asynchronous Execution Time

A common mistake is only measuring the time to call a method that returns a CompletableFuture. The method may return very quickly while the actual work is still running.

An example that misses the end-to-end goal:

~~~java
long start = System.nanoTime();
CompletableFuture<Result> future = service.calculateAsync(input);
long elapsed = System.nanoTime() - start;
~~~

The snippet above only measures the time to create or return the future.

To measure until the future completes:

~~~java
long start = System.nanoTime();

CompletableFuture<Result> future =
        service.calculateAsync(input);

future.whenComplete((result, error) -> {
    long elapsed = System.nanoTime() - start;

    if (error != null) {
        System.err.println("Task failed after " + elapsed + " ns");
    } else {
        System.out.println("Task completed after " + elapsed + " ns");
    }
});
~~~

This snippet records the elapsed time from calling the async method until the completion callback executes. The time it takes for the scheduler to run the callback can also contribute to the result; if you need exact latency according to the service's semantics, clearly define the business start and end points.

### Measuring a Group of Concurrent Tasks

If you want to measure total wall-clock time for all tasks to finish, start the timer before submitting and stop after allOf completes:

~~~java
long start = System.nanoTime();

CompletableFuture<Void> all =
        CompletableFuture.allOf(task1, task2, task3);

all.join();

long elapsed = System.nanoTime() - start;
System.out.println("All tasks elapsed: " + elapsed + " ns");
~~~

This is the elapsed time for the entire group of tasks. Do not sum the durations of individual tasks as a substitute for total time, because tasks can run in parallel.

If you need individual task latency, measure each task separately and associate the result with a task ID.

## 8. Measuring a Thread's CPU Time

Elapsed time includes the time a thread spends waiting. If you want to know how long a thread actually used the CPU, use ThreadMXBean.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

if (bean.isCurrentThreadCpuTimeSupported()) {
    if (!bean.isThreadCpuTimeEnabled()) {
        bean.setThreadCpuTimeEnabled(true);
    }

    long cpuStart = bean.getCurrentThreadCpuTime();

    performTask();

    long cpuElapsed =
            bean.getCurrentThreadCpuTime() - cpuStart;

    System.out.println("Thread CPU ns: " + cpuElapsed);
}
~~~

Notes:

- CPU time is only supported if the JVM and platform allow it.
- Enabling thread CPU time may require appropriate management permissions.
- The value may be unavailable on some JVMs.
- One thread's CPU time does not equal the CPU time of the entire process.
- CPU time does not include time spent waiting on I/O or locks.

For example, if a task takes 1 second of elapsed time but uses only 50 ms of CPU, most of the time is likely spent waiting. If elapsed and CPU time are close on a single thread, the task may be CPU-bound.

## 9. Why a Single Measurement Is Usually Unreliable

The JVM is a dynamic runtime. The result of the first run can differ significantly from subsequent runs.

### Class Loading and Initialization

The first time a class is used, it may need to be loaded, verified, linked, and initialized. If you only measure the first run, the result may include startup overhead that subsequent runs do not have.

### JIT Compilation

HotSpot begins executing bytecode with an interpreter or unoptimized code. When a method becomes hot, the JIT compiler can compile it to native code and apply inlining, escape analysis, loop optimizations, and other techniques.

Consequently, a method can run much faster after warm-up.

### Garbage Collection

Allocations inside the measured region can trigger GC. A measurement paused by GC can be significantly longer. Conversely, the next measurement might not encounter GC and produce a different result.

You should not eliminate all GC impact from a benchmark if allocation is a natural part of the workload; determine whether the goal is to measure pure code or real application behavior.

### OS Scheduling and Background Activity

A thread can be paused by the scheduler due to other processes, antivirus, backups, updates, CPU throttling, or system load. These factors cause elapsed time to fluctuate.

### CPU Frequency and Thermal Throttling

The CPU can change its clock speed based on load and temperature. Two runs on the same machine can still yield different performance.

### Dead-Code Elimination and Constant Folding

The JIT can eliminate work that produces no observable result or precompute expressions with constant values.

If a method's result is not used, a hand-written benchmark might end up measuring code that was optimized away.

## 10. Do Not Use Hand-Written nanoTime Loops for Microbenchmarking

A common pattern:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    doWork();
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

This approach is useful for demonstrating elapsed time or measuring a large business batch. However, it is not reliable enough for microbenchmarking because:

- The JIT may optimize away the entire loop.
- Warm-up is not controlled.
- GC and class loading can skew results.
- There is no independent fork to isolate JVM state.
- Results can depend on execution order.
- There is no statistical error or distribution analysis.
- Calling nanoTime and loop overhead can affect measurements of extremely short methods.

If you need to compare methods taking a few nanoseconds or microseconds, use JMH.

## 11. JMH: The Standard Tool for Java Microbenchmarking

JMH is the Java Microbenchmark Harness, a framework specifically designed for building and running Java benchmarks on the JVM.

JMH handles many difficult issues of manual measurement:

- Warm-up iterations.
- Measurement iterations.
- Forking JVM processes.
- Benchmark state and setup.
- Dead-code elimination.
- Consuming results via return values or Blackhole.
- Multiple benchmark modes.
- Aggregating results and statistical error.

JMH does not automatically make every benchmark correct. The author still needs to choose a representative workload, reasonable inputs, proper state, and avoid benchmarking the wrong question.

### Benchmark Modes

| Mode | What It Measures | When to Use |
|---|---|---|
| AverageTime | Average time per operation | Comparing method latency |
| Throughput | Operations per unit of time | Evaluating processing rate |
| SampleTime | Distribution of operation times via sampling | Inspecting percentiles and tail behavior |
| SingleShotTime | Time of a single execution | Measuring controlled cold/single invocations |
| All | Runs multiple modes | Broad overview, takes longer |

AverageTime typically displays ns/op, µs/op, or ms/op depending on OutputTimeUnit. Throughput typically displays ops/s. For AverageTime, lower values are generally better; for Throughput, higher values are generally better.

## 12. Creating a JMH Benchmark with Java 17+

The example below compares a for loop with a Stream for summing the same integer array.

Directory structure:

~~~text
timing-benchmarks/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── SumBenchmark.java
~~~

### pom.xml

Uses JMH 1.37, the Maven Compiler Plugin, and the Shade Plugin to create an executable benchmark JAR.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>timing-benchmarks</artifactId>
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
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-generator-annprocess</artifactId>
            <version>1.37</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
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
                <version>3.5.3</version>
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

### SumBenchmark.java

~~~java
package org.example;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SumBenchmark {
    @Param({"1000", "100000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];

        for (int i = 0; i < values.length; i++) {
            values[i] = i % 100;
        }
    }

    @Benchmark
    public long sumWithLoop() {
        long sum = 0;

        for (int value : values) {
            sum += value;
        }

        return sum;
    }

    @Benchmark
    public long sumWithStream() {
        return Arrays.stream(values)
                .asLongStream()
                .sum();
    }
}
~~~

### Running the Benchmark

From the timing-benchmarks directory:

~~~bash
mvn clean package
java -jar target/benchmarks.jar SumBenchmark
~~~

You can explicitly specify the number of warm-up, measurement, and fork runs from the command line:

~~~bash
java -jar target/benchmarks.jar SumBenchmark -wi 5 -i 5 -f 2
~~~

In this example:

- -wi 5: 5 warm-up iterations.
- -i 5: 5 measurement iterations.
- -f 2: run 2 independent JVM forks.

The annotations in the class also set the corresponding configuration. Command-line arguments allow overriding them when experimenting.

### Reading JMH Results

JMH prints a results table with benchmark name, mode, count, score, error, and unit. Illustrative example:

~~~text
Benchmark                  Mode  Cnt   Score   Error  Units
SumBenchmark.sumWithLoop   avgt   10   12.5 ± 0.4  us/op
SumBenchmark.sumWithStream avgt   10   18.2 ± 0.7  us/op
~~~

The numbers above only illustrate the format. Actual results depend on machine, JDK, workload, and configuration.

Do not look only at Score. Check Error, fork count, input size, JVM version, and run conditions as well. Run multiple times and verify whether results are stable.

## 13. Principles for Designing Reliable Benchmarks

### Warm Up Sufficiently Before Measuring

Warm-up allows the JVM to load classes, run the interpreter, collect profiling information, and compile hot methods with the JIT. If you measure from the very first run, the benchmark may reflect startup rather than steady-state performance.

### Use Independent Forks

Forking creates a new JVM process for each benchmark run. This reduces interference from previous JIT states, heap layouts, and prior benchmarks. Multiple forks help evaluate stability better.

### Prepare Inputs Outside the Measured Region

Use @Setup to create arrays, objects, or fixtures before measurement if the goal is not to measure setup cost. If setup is part of the business operation to evaluate, include it in the benchmark intentionally.

### Ensure Results Are Used

If a result is not observed, the JIT may eliminate the computation. JMH handles this by consuming the return value or using Blackhole:

~~~java
@Benchmark
public void calculate(Blackhole blackhole) {
    long result = expensiveCalculation();
    blackhole.consume(result);
}
~~~

Do not use Blackhole mechanically if the benchmark method can return the result; returning a value is usually simpler.

### Do Not Benchmark Constants or Overly Simple Data

If the input is always the same and the compiler can precompute the result, the benchmark does not reflect a real workload. Use @Param or properly prepared state to control inputs.

### Avoid Benchmarking Unrelated Work Together

Do not mix network calls, file I/O, logging, random generation, and algorithms into one benchmark if the question is simply comparing two implementations of an algorithm.

If you want to measure end-to-end, measure the entire workload as a separate integration/load test.

### Run in a Stable Environment

- Use the same JDK vendor/version and JVM flags.
- Close unnecessary background tasks.
- Use equivalent inputs and datasets.
- Record CPU, RAM, OS, container limits, and power profile.
- Avoid running two CPU-competing benchmarks at the same time.
- Do not cherry-pick the best result out of multiple runs while ignoring the rest.

## 14. Execution Time Measurement vs. System-Wide Performance Measurement

A faster method does not necessarily make the entire service faster. The bottleneck may lie in the database, network, queues, locks, or GC.

Choose the measurement level:

| Level | Goal | Appropriate Tool |
|---|---|---|
| A code region | Actual elapsed time | System.nanoTime() |
| Microbenchmark | Comparing small methods/algorithms | JMH |
| A single request | End-to-end latency | Application timing, tracing |
| Many concurrent requests | Throughput, p95/p99, error rate | Load testing and metrics |
| Diagnosing CPU/I/O causes | Method samples, events, stack traces | JFR/JMC |
| Thread CPU time | Time a thread actually runs on CPU | ThreadMXBean |

Do not use microbenchmarks to replace service load testing. Do not use JFR event counts as an end-to-end latency measurement.

## 15. Combining with JFR to Find Root Causes of Slowness

JMH tells you which implementation is faster in a benchmark. JFR helps investigate why a real application is slow.

Start a short recording for a running JVM:

~~~bash
jcmd <pid> JFR.start name=runtime-check settings=profile duration=30s filename=runtime-check.jfr
~~~

View the summary:

~~~bash
jfr summary runtime-check.jfr
~~~

Open the file in JDK Mission Control to inspect:

- CPU hot methods.
- Execution samples and thread CPU load.
- Garbage collection.
- File/socket I/O events.
- Lock contention.
- Allocations and object statistics.

Profile settings collect more data than default and have higher overhead. Use them for short durations, with a representative workload, and monitor the impact.

## 16. Common Pitfalls When Measuring Time

### Using currentTimeMillis for Very Fast Methods

Resolution may be insufficient and the clock can be adjusted. Use nanoTime to measure elapsed time.

### Treating nanoTime as a Timestamp

nanoTime's origin is arbitrary. Do not store this value as a calendar point in time or compare it across machines.

### Forgetting to Compute end - start

Only the difference between two nanoTime readings represents elapsed time. Do not compare absolute values directly.

### Measuring Only Once

Results are affected by JIT, class loading, GC, and OS scheduling. Use warm-up, multiple iterations, and JMH when benchmarking.

### Integer Division Losing Fractional Parts

elapsedNanos / 1_000_000 is integer division if both operands are integers. Use 1_000_000.0 to preserve the fractional part.

### Stopping the Timer Too Early for Async Methods

If a method returns a CompletableFuture, you must measure until the future completes if the goal is task duration. Measuring around the call only tells you the submission time.

### Results Being Optimized Away

If the result is not used, the JIT may eliminate the computation. Return the result, use a checksum, or use JMH Blackhole.

### Comparing Two Implementations in Different Environments

JDK, CPU, JVM flags, heap, inputs, and background load can skew results. Compare under identical conditions and multiple forks.

### Using Thread.sleep to Create Timed Intervals

sleep only requests that the thread pause for at least a given duration; the scheduler may wake it up later. It is not an accurate timer.

## 17. A Repeatable Measurement and Optimization Workflow

1. Define the question: elapsed time, CPU time, method latency, or service throughput.
2. Choose the right clock: nanoTime, Instant/currentTimeMillis, or ThreadMXBean.
3. Define the exact boundaries of the measured region.
4. Use representative inputs and workloads.
5. Separate setup, warm-up, and measurement when needed.
6. For microbenchmarks, write a JMH benchmark instead of a hand-rolled nanoTime loop.
7. Run multiple warm-up iterations, measurement iterations, and forks.
8. Record JDK version, JVM flags, hardware, OS, and benchmark parameters.
9. Check error margins, stability, and result distribution.
10. Use JFR or a profiler to find root causes when discrepancies appear.
11. Optimize one major factor at a time.
12. Re-run the same workload to confirm improvement and avoid regressions.

## 18. Execution Time Measurement Checklist

- Use nanoTime for elapsed time.
- Use Instant/currentTimeMillis for calendar timestamps.
- Use ThreadMXBean when you need thread CPU time.
- Always compute end - start.
- Do not compare or store nanoTime as a global timestamp.
- Remember nanosecond precision does not mean nanosecond resolution.
- Convert units using double if fractional parts are needed.
- Measure the exact business boundaries.
- Measure through async task completion if you need end-to-end duration.
- Do not use a single run as a benchmark.
- Avoid dead-code elimination and constant folding.
- Use JMH for microbenchmarks.
- Include warm-up, measurement iterations, and forks.
- Use representative workloads and identical environments when comparing.
- Use JFR/JMC to diagnose root causes, not as a replacement for benchmarks.
- Record error, units, JDK, flags, and run configuration.

## 19. Key Terminology

| Term | Meaning |
|---|---|
| Wall-clock time | Calendar point in time |
| Elapsed time | Actual time passed between two points |
| CPU time | Time the CPU actually spent on a thread/process |
| System.nanoTime() | High-resolution API for measuring elapsed time |
| System.currentTimeMillis() | Millisecond timestamp since the Unix epoch |
| Instant | A point on the UTC timeline |
| Duration | Time interval between two points |
| Clock | Abstraction providing wall-clock time, injectable into code |
| Warm-up | Phase for the JVM to load classes and perform JIT optimizations |
| JIT | Just-In-Time compiler |
| Dead-code elimination | Optimization that removes computations producing no observable result |
| Constant folding | Precomputing expressions with deterministic constant values |
| Fork | Running a benchmark in an independent JVM process |
| Iteration | A single warm-up or measurement cycle |
| JMH | Java Microbenchmark Harness |
| Blackhole | Mechanism for consuming results to prevent computation elimination |
| Throughput | Number of operations completed per unit of time |
| Latency | Time to complete a single operation/request |
| Percentile | Quantile such as p50, p95, or p99 |
| JFR | Java Flight Recorder used to record runtime events |

Accurate execution time measurement starts with choosing the right quantity. Use nanoTime for elapsed time, wall-clock APIs for timestamps, and ThreadMXBean for thread CPU time. For very small methods, use JMH to control warm-up, JIT, and error margins; for real-world applications, combine benchmarks, JFR, and metrics to understand both performance and root causes.

## References

- Oracle Java SE 24 API — System.nanoTime(): https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle Java SE 24 API — System.currentTimeMillis(): https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#currentTimeMillis()
- Oracle Java SE 24 API — Instant: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 24 API — Duration: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Duration.html
- Oracle Java SE 24 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- OpenJDK — Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh
- Oracle JDK 24 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf
