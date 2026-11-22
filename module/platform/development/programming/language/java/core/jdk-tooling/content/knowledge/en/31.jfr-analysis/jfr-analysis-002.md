# Analyzing CPU Hot Methods with JFR

A **CPU hot method** is a method that frequently appears in stack trace samples of threads executing code. When JVM CPU usage spikes, identifying the right hot method helps pinpoint the code consuming the most processing time and prioritize optimizations where they matter most.

Java Flight Recorder (JFR) collects execution samples, CPU state, thread activity, JIT events, and other runtime data. JDK Mission Control (JMC) visualizes recordings through views such as Hot Methods, Call Tree, Hot Threads, and CPU. Starting in JDK 24, the `jfr` command-line tool also includes a `hot-methods` view to inspect results directly in the terminal.

This guide covers creating a recording, finding hot methods, reading stack traces, distinguishing CPU-bound work from I/O or lock waiting, practicing with a Java 17+ program, and verifying optimization results.

## 1. What Is a Hot Method?

A method is considered hot when it accounts for a large share of the CPU execution samples collected in a recording.

For example, a request might pass through a call chain like this:

~~~text
RequestHandler.handle()
  -> OrderService.calculate()
     -> PricingEngine.applyRules()
        -> DiscountRule.evaluate()
~~~

If JFR frequently samples threads while they are running inside `PricingEngine.applyRules()`, that method may appear prominently in Hot Methods.

A hot method can be:

- A computational method with a large loop.
- A search, sorting, encryption, or compression algorithm.
- A string, regex, or JSON processing method.
- A data conversion function called too frequently.
- A method in a library or framework.
- A native method called via JNI or system libraries.

A method called many times is not necessarily a hot method. Conversely, a method with a low invocation count that takes a long time per call can still consume most of the CPU.

### Hot Method Does Not Mean High Invocation Count

It is important to distinguish between:

| Concept | Meaning |
|---|---|
| Invocation count | Number of times a method is called |
| Execution samples | Number of stack samples capturing the method while executing |
| CPU hot method | A method accounting for a large share of CPU samples |
| Wall-clock latency | Actual elapsed time the user waits |
| CPU utilization | CPU usage of the process or system |

JFR sampling estimates where the CPU spends its time. It does not count every method invocation exactly, nor does it directly measure user wait time.

## 2. How JFR Collects CPU Data

JFR is an event-recording and profiling framework built into the JDK. The JVM can record events over time, save them to a `.jfr` file, and allow post-recording analysis.

For CPU hot methods, the key events include:

| Event | Role |
|---|---|
| jdk.CPULoad | Tracks JVM and system-wide CPU load |
| jdk.ThreadCPULoad | Helps identify CPU-consuming threads via method sampling |
| jdk.ExecutionSample | Captures stack trace samples of threads executing Java code |
| jdk.NativeMethodSample | Captures execution samples in native methods |
| jdk.Compilation | Records JIT compilation activity |
| jdk.CompilerPhase | Records phases of the JIT compilation process |

### jdk.CPULoad

Used to answer whether the JVM is actually consuming significant CPU.

This event lets you compare JVM CPU load against system-wide CPU load:

- High JVM and high system load: the JVM may be a significant CPU consumer.
- Low JVM and high system load: other processes may be consuming CPU.
- Low JVM and low system load, yet slow requests: the issue may lie in I/O, locks, network, or external dependencies.

### jdk.ThreadCPULoad

Helps identify which threads have prominent CPU activity. Once you find a thread, switch to stack samples and Hot Threads to see which call paths that thread is executing.

This information is based on method sampling, so it is not an exact CPU measurement per thread. When sample counts are low, thread rankings can be unstable.

### jdk.ExecutionSample

This is the most important event when hunting for hot Java methods.

The JVM periodically samples the stack of threads executing code. Each sample shows where a thread is in its call stack at the moment of sampling.

Threads waiting on I/O, sleeping, or waiting on a lock are generally not sampled as actively executing code. Therefore, many execution samples in a method indicate that the method or its call path is consuming significant execution time.

### jdk.NativeMethodSample

If the application consumes CPU in native code, inspect native method samples as well. A Java method might simply be the entry point into a native library; optimizing the outer Java code may not resolve a CPU bottleneck inside the native library.

## 3. JFR and JDK Mission Control

These two components serve different roles:

- **JFR:** collects runtime events and method samples from the JVM.
- **JMC:** opens recordings and displays charts, summary tables, and call trees for analysis.

JFR is built into modern JDKs. JMC is a separate application not included in a standard JDK installation; you need to install JMC to use its graphical analysis UI.

Useful areas in JMC:

| Area | Purpose |
|---|---|
| Code → Hot Methods | Ranks methods by execution sample percentage |
| Code → Call Tree | Shows call paths leading to hot methods |
| Threads → Hot Threads | Shows threads with high CPU activity |
| Threads → Overview | Observes thread activity and CPU usage |
| JVM Internals → Compiler | Inspects JIT compilation activity |
| JVM Internals → Garbage Collections | Checks CPU and time spent on GC |
| I/O | Identifies file and socket wait time |
| Locks / Contention | Finds threads blocked on synchronization |

JMC lets you select a method in Hot Methods to inspect related stack traces. The Call Tree helps trace call paths starting from a thread entry point such as `Thread.run()` down to the branches with the most samples.

## 4. Creating a JFR Recording for CPU Profiling

To find hot methods, record while the application is processing a representative workload. A recording that is too short or taken while the application is idle may not reflect the real bottleneck.

### Checking Tools

~~~bash
java --version
jcmd -l
jfr --help
~~~

Use `jcmd` to find running JVMs. Verify the correct PID, host, and user before starting a recording.

### Recording a Running JVM

Syntax:

~~~bash
jcmd <pid> JFR.start name=cpu-hot settings=profile duration=30s filename=cpu-hot.jfr
~~~

Explanation:

- **pid:** PID of the target JVM.
- **name=cpu-hot:** recording name.
- **settings=profile:** uses profile settings to collect more profiling data.
- **duration=30s:** records for 30 seconds.
- **filename=cpu-hot.jfr:** output file.

Relative paths are resolved against the target JVM's working directory. In production environments, use an absolute path to a writable, properly secured directory.

Windows example:

~~~powershell
jcmd 12345 JFR.start name=cpu-hot settings=profile duration=30s filename=C:\diagnostics\cpu-hot.jfr
~~~

Linux example:

~~~bash
jcmd 12345 JFR.start name=cpu-hot settings=profile duration=30s filename=/var/tmp/cpu-hot.jfr
~~~

Replace the PID and path with values from your actual environment.

### Checking Recordings

~~~bash
jcmd <pid> JFR.check
~~~

This command shows active recordings on the JVM. A recording with a `duration` will stop automatically and write the file when time expires.

### Choosing the Right Profile

JFR provides two commonly used templates:

| Template | Characteristics | Best Fit |
|---|---|---|
| default.jfc | Collects basic data with low overhead | Continuous recording, long-term monitoring |
| profile.jfc | Collects more method profiling data, higher overhead | Investigating bottlenecks over a short window |

The `profile` recording is better suited for finding CPU hot methods because method sampling runs more aggressively. However, overhead varies by application and configuration; measure the impact on a realistic workload.

Do not enable all events at high detail for extended periods without evaluating overhead.

## 5. Analyzing Recordings with the jfr Tool

Once the recording file is created, use the `jfr` CLI to inspect it.

### Viewing Summary Information

~~~bash
jfr summary cpu-hot.jfr
~~~

The summary displays recording metadata, duration, event counts by type, and other key details.

Before inspecting hot methods, verify that the file covers enough recording time and contains method sampling events.

### Viewing Hot Methods Directly in the Terminal

In JDK 24, `jfr` supports the `view` command:

~~~bash
jfr view hot-methods cpu-hot.jfr
~~~

You can widen the table output:

~~~bash
jfr view --width 160 hot-methods cpu-hot.jfr
~~~

The `hot-methods` view aggregates sample data to help identify prominent methods in the recording.

### Viewing Thread CPU Load

~~~bash
jfr view thread-cpu-load cpu-hot.jfr
~~~

### Viewing CPU Load Samples

~~~bash
jfr view cpu-load-samples cpu-hot.jfr
~~~

These views help correlate hot methods with threads and CPU conditions within the same recording.

### Printing Raw Events

If you need to inspect specific stack samples:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.NativeMethodSample cpu-hot.jfr
~~~

To inspect additional CPU and thread details:

~~~bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-hot.jfr
~~~

Raw events can produce a lot of output. Filter by event type to narrow down the data and avoid dumping the entire recording unnecessarily.

## 6. Finding Hot Methods in JDK Mission Control

Open `cpu-hot.jfr` in JMC.

Workflow:

1. Open JDK Mission Control.
2. Select Open File and open the recording.
3. Wait for JMC to finish analyzing.
4. Open the Code section.
5. Select Hot Methods.
6. Sort by execution time percentage or sample count.
7. Select a prominent method to view its stack traces.
8. Open Call Tree to find callers and related call paths.
9. Switch to Threads to see which threads generate the most samples.
10. Cross-reference with CPU, GC, I/O, and lock events.

### Reading the Hot Methods Table

The Hot Methods table ranks methods by their estimated share of execution time based on samples.

When reviewing the table:

- Look for methods with a high sample percentage.
- Check whether the sample count is large enough to be meaningful.
- Check whether the method belongs to an application package, a third-party library, or the JDK.
- Select the method to inspect its stack trace.
- Check which callers invoke the method.
- Evaluate whether the method lies on a critical business processing path.

A library method can top the list because many callers use it. In that case, inspect the callers and input data before modifying library code or optimizing the call sites.

### Using the Call Tree

The Call Tree shows the call paths leading to a hot method.

Example:

~~~text
Thread.run()
  ApplicationWorker.run()
    OrderService.process()
      PricingEngine.calculate()
        DiscountEngine.evaluate()
          RuleMatcher.match()
~~~

If `RuleMatcher.match()` appears frequently in samples, check:

- Is there an expensive loop or complex regex?
- Is the same computation being repeated?
- Can results be precomputed or cached?
- Can the number of calls be reduced?
- Would a more suitable data structure help?

The Call Tree helps establish the context of a hot method so you avoid optimizing at the wrong layer.

## 7. Example: Distinguishing CPU-Bound Work from Thread Waiting

High request latency in a system does not automatically mean a CPU hot method is to blame.

There are three common scenarios:

### Scenario A: CPU-Bound

Threads continuously execute code and generate many execution samples. JVM CPU usage is high.

How to handle:

- Open Hot Methods.
- Inspect the Call Tree.
- Find loops, algorithms, or calculations consuming the most samples.
- Check how many threads have high CPU usage.
- Optimize the code and re-measure.

### Scenario B: I/O-Bound

Threads spend significant time waiting on sockets or files. CPU usage may be low despite high request latency.

Check:

- jdk.SocketRead
- jdk.SocketWrite
- jdk.FileRead
- jdk.FileWrite

Identify the slow endpoint or dependency, wait durations, and volume of data transferred.

### Scenario C: Lock Contention

Multiple threads wait on the same monitor or are parked. CPU usage is not necessarily high.

Check:

- jdk.JavaMonitorEnter
- jdk.JavaMonitorWait
- jdk.ThreadPark
- jdk.ThreadSleep

Identify which locks are contended and inspect the stack traces of waiting threads.

Some Java Application duration events only record when durations exceed 20 ms by default. Thus, the absence of events does not prove the application has no short waits. You can lower the threshold to capture more data, though the recording will contain more events and may incur higher overhead.

## 8. Example: JIT Compilation Can Also Consume CPU

When an application starts up or goes through warm-up, CPU usage can rise as the JIT compiler compiles hot methods.

Related events:

- jdk.Compilation
- jdk.CompilationFailure
- jdk.CompilerPhase

In JMC, open the Compilations section to inspect compiled methods and compiler activity.

Do not confuse CPU spent on JIT compilation with CPU spent processing business requests.

If a recording only captures the startup phase, Hot Methods may reflect warm-up work rather than steady-state workload.

To get reliable results:

1. Start the application.
2. Run a warm-up workload.
3. Wait for the system to reach steady state.
4. Start the recording.
5. Record during a representative workload window.
6. Compare recordings across different phases if needed.

## 9. Java 17+ Lab: Creating a CPU Hot Method

The following program runs a continuous computation loop so it can be observed with JFR. The `hotLoop()` method performs integer operations and stores the result in a `volatile` field so the JVM does not optimize away the entire workload.

Create **CpuHotMethodsDemo.java**:

~~~java
public final class CpuHotMethodsDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        long seconds = args.length == 0
                ? 90L
                : Long.parseLong(args[0]);

        if (seconds <= 0) {
            throw new IllegalArgumentException(
                    "seconds must be positive");
        }

        long deadline = System.nanoTime()
                + seconds * 1_000_000_000L;

        long state = 0x1234ABCD5678EF90L;

        System.out.println("READY");

        while (System.nanoTime() < deadline) {
            state = hotLoop(state, 500_000);
        }

        sink = state;
        System.out.println("DONE");
    }

    private static long hotLoop(long state, int rounds) {
        for (int i = 0; i < rounds; i++) {
            state ^= state << 13;
            state ^= state >>> 7;
            state ^= state << 17;
            state += 0x9E3779B97F4A7C15L ^ i;
        }

        return state;
    }
}
~~~

Compile:

~~~bash
javac --release 17 CpuHotMethodsDemo.java
~~~

Run the program in the first terminal:

~~~bash
java CpuHotMethodsDemo 90
~~~

Stdout:

~~~text
READY
DONE
~~~

`READY` is printed before the loop begins. `DONE` is printed after the program finishes running for the specified duration.

### Starting the Recording from a Second Terminal

Find the JVM:

~~~bash
jps -l
~~~

Find the PID of `CpuHotMethodsDemo`, then run:

~~~bash
jcmd <pid> JFR.start name=cpu-lab settings=profile duration=30s filename=cpu-lab.jfr
~~~

After about 30 seconds, the recording file is created. Inspect it:

~~~bash
jfr summary cpu-lab.jfr
~~~

View hot methods:

~~~bash
jfr view hot-methods cpu-lab.jfr
~~~

In the recording, `hotLoop()` is the main computational method and should appear prominently in stack samples. The JIT may inline methods or alter how stack frames are displayed, so exact names and rankings depend on runtime behavior.

When the program completes, the first terminal prints:

~~~text
DONE
~~~

This is a single-threaded CPU-bound lab. It demonstrates the profiling workflow; its results do not represent a real production application workload.

## 10. How to Interpret Hot Method Results Properly

A method with a high sample percentage must be evaluated in context.

### Checking Sample Counts

If a recording has very few samples, hot method rankings can swing wildly between runs.

Best practices:

- Record long enough to gather a representative number of samples.
- Repeat recordings when results look anomalous.
- Use a workload close to production.
- Avoid drawing conclusions from a single stack sample.

### Checking Callers and Callees

A method that appears frequently in stacks is not necessarily the place that needs fixing.

Example:

~~~text
OrderService.handle()
  JsonParser.parse()
    StringDecoder.decode()
      Character.isWhitespace()
~~~

If `Character.isWhitespace()` has many samples, the root cause may be that the parser is processing oversized payloads or being called too often. Optimizing the caller or reducing parse frequency can be far more effective than changing the low-level method.

### Checking Threads

A method may be hot because a single worker thread is overloaded, or because many workers call it concurrently.

Use Hot Threads and thread filters to distinguish:

- A single thread consuming high CPU.
- Multiple threads executing the same method.
- A background job thread causing a CPU spike.
- An imbalanced workload across a thread pool.

### Checking JIT Inlining

The JIT compiler can inline small methods into their callers. Stack traces may represent logical inline frames depending on recording data and runtime behavior.

Consequently, if a small method is missing from the table, you cannot conclude it is not executing. Inspect the call tree, compiler events, and neighboring frames.

## 11. Optimizing Hot Methods by Root Cause

Once you identify a hot method, understand the work it performs before changing code.

| Symptom | Optimization Direction to Consider |
|---|---|
| Loop repeating the same calculation | Eliminate redundant computation, reduce loop iterations |
| Many temporary objects | Reduce allocations, reuse data where appropriate |
| CPU-heavy regex or parsing | Optimize patterns, parse once, bound input size |
| Linear search on large datasets | Choose a better data structure such as HashMap or Set |
| Repeated string conversions | Reduce copying and intermediate string creation |
| Expensive serialization/deserialization | Shrink payloads, optimize schemas and codecs |
| Library method dominating samples | Check callers, configuration, and library version |
| CPU spike from JIT | Evaluate warm-up, compilation, and steady-state workload |
| Hot native method | Inspect native library, JNI, and data crossed over Java/native boundary |

Do not add caching or increase concurrency reflexively. Caching can increase memory pressure; higher concurrency can increase contention and context switching.

### Data-Driven Optimization

A solid workflow:

1. Record a baseline before making changes.
2. Identify the hot method and call path.
3. Formulate a specific hypothesis.
4. Change one primary factor.
5. Re-run the exact same workload.
6. Take another JFR recording.
7. Compare CPU, throughput, latency, and GC.
8. Keep the change only if results improve without regressions.

Do not compare sample percentages alone. If throughput increases, a method may take a larger share of samples even though per-request processing time dropped. Always check actual CPU usage and business metrics.

## 12. Distinguishing Self Work from Callee Work

A call stack contains multiple nested methods. A sample in a deep method also attributes inclusive samples to its callers above.

When analyzing:

- **Self work:** work performed directly inside the method itself.
- **Inclusive work:** total work of the method plus all methods it calls.
- **Caller:** the method invoking the method under inspection.
- **Callee:** a method invoked by the method under inspection.

Example:

~~~text
Controller.handle()
  Service.process()
    Repository.load()
      JsonParser.parse()
~~~

If `Service.process()` appears heavily in the call tree, that may be because time is spent in `Repository.load()` or `JsonParser.parse()`, rather than inside `Service.process()` itself.

Expand child branches and inspect deeper methods before deciding where to optimize.

## 13. Limitations of CPU Method Sampling

JFR sampling is a statistical technique, not an exact timer for every invocation.

Limitations to keep in mind:

- Short-lived methods may miss being sampled.
- Recordings that are too short may lack sufficient samples.
- Non-representative workloads skew rankings.
- Threads waiting on I/O or locks are not sampled like actively running threads.
- Native code requires checking native method samples.
- JIT inlining can alter how frames appear.
- A hot library method may simply reflect workload driven by its caller.
- Sampling does not provide exact invocation counts.
- Sample percentage does not directly equal percentage of request wall-clock latency.

Do not rely on Hot Methods as the sole evidence for diagnosing an incident. Correlate with CPU load, thread states, GC, I/O, lock contention, and application metrics.

## 14. Controlling Overhead and Protecting Recordings

JFR is designed for low-overhead data collection, though overhead varies with workload, event settings, and recording duration.

A `profile` recording can collect more method samples than a continuous recording using `default` settings. Keep in mind:

- Record long enough to obtain representative samples.
- Avoid enabling unrelated events.
- Measure overhead in a test environment when possible.
- Monitor CPU, memory, disk, and latency while recording.
- Cap recording duration and size.
- Use `default` settings for continuous monitoring when appropriate.

`.jfr` files can contain class names, packages, thread names, system properties, file paths, endpoints, and internal runtime details. Treat recording files as sensitive operational data:

- Store them in directories with least-privilege access.
- Do not commit recording files to Git.
- Do not share recordings over public channels.
- Redact sensitive information before including data in reports.
- Apply a retention policy and delete files when no longer needed.

## 15. Common Pitfalls

### Hot Methods Has No Data

Check whether the recording includes execution sampling events. If using default continuous settings, method sample counts may be lower than in a profile recording.

Use a short profile recording to collect more data when needed.

### High CPU, Yet Hot Methods Shows No Prominent Application Methods

Check:

- JVM CPU vs. system-wide CPU.
- NativeMethodSample.
- JIT compiler events.
- Garbage collection.
- Other processes on the host.
- Workload and recording duration.

### Hot Methods Change Between Recordings

This can be caused by differences in workload, warm-up state, thread scheduling, or sample counts. Re-record under consistent conditions and for a sufficient duration before comparing.

### Top Method Is a JDK Library Method

Check callers in the Call Tree. A JDK method may accumulate many samples because the application calls it too frequently or passes large data payloads.

### Slow Requests with Low CPU

Check `SocketRead`, `SocketWrite`, `FileRead`, `FileWrite`, `JavaMonitorWait`, `ThreadPark`, and GC pauses. The bottleneck may be network, disk, locks, or an external dependency.

### CPU Spike Right After Startup

Check JIT compilation and warm-up. Recording too early may capture startup overhead rather than steady-state workload.

### Recording File Too Large

Reduce duration, choose appropriate settings, limit `maxsize`/`maxage`, or enable only necessary events. Do not delete older files until you have verified they are safely archived.

## 16. End-to-End CPU Hot Method Analysis Workflow

1. Identify the service, JVM PID, JDK version, and target workload to investigate.
2. Check JVM and system-wide CPU load.
3. Warm up the application if needed.
4. Start a JFR recording with `profile` settings for a representative window.
5. Check the summary and `ExecutionSample` count.
6. Open Hot Methods to find methods with a high sample share.
7. Open Call Tree to understand callers, callees, and call paths.
8. Inspect Hot Threads to identify CPU-consuming threads.
9. Check native samples, JIT, GC, I/O, and lock events.
10. Read the source code and identify optimization opportunities.
11. Propose a small change, capture a baseline, and run an experiment.
12. Record again after the change using an equivalent workload and configuration.
13. Compare CPU, throughput, latency, GC, and sample distribution.
14. Record results alongside JDK version, JVM flags, recording settings, and test duration.

## 17. CPU Hot Method Checklist

- Identify the correct JVM and PID.
- Record JVM and system-wide CPU load.
- Choose `profile` recording when detailed method sampling is needed.
- Record during a representative workload for a sufficient duration.
- Verify the `ExecutionSample` count.
- Inspect Hot Methods and Call Tree.
- Distinguish self work from inclusive work.
- Filter by thread to locate CPU hotspots.
- Check `NativeMethodSample` when native code is involved.
- Check JIT compilation and warm-up.
- Check I/O, locks, parking, and GC if CPU is not the root cause.
- Do not treat sample percentage as exact per-invocation duration.
- Optimize based on a testable hypothesis.
- Re-measure with the same workload and configuration.
- Protect JFR files and delete them according to retention policy.

## 18. Key Terms to Remember

| Term | Meaning |
|---|---|
| CPU hot method | A method that appears frequently in CPU execution samples |
| JFR | Java Flight Recorder, framework for recording runtime events and profiling |
| JMC | JDK Mission Control, tool for analyzing recordings |
| ExecutionSample | Stack trace sample of a thread executing Java code |
| NativeMethodSample | Execution sample in a native method |
| CPULoad | Statistics on JVM and system CPU load |
| ThreadCPULoad | Data supporting identification of CPU-using threads |
| Hot Methods | Table ranking methods by execution samples |
| Call Tree | Tree of method call paths |
| Hot Threads | Group of threads with prominent CPU activity |
| Sampling | Periodically sampling state rather than recording every execution |
| JIT | Just-In-Time compiler |
| Compilation event | Event recording JIT method compilation |
| Self work | Work performed directly inside the method |
| Inclusive work | Work of the method and all methods it calls |
| CPU-bound | Workload limited by CPU processing capacity |
| I/O-bound | Workload limited by I/O wait time |
| Lock contention | Contention when multiple threads need the same lock |
| Warm-up | Phase where the JVM loads classes, profiles, and performs JIT compilation |

Analyzing CPU hot methods with JFR turns a vague observation that an application uses too much CPU into concrete methods and call paths to inspect. Combine Hot Methods, Call Tree, Hot Threads, and CPU/I/O/lock events, then optimize and re-measure on an equivalent workload.

## References

- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle — [Java Mission Control and Flight Recorder Demo](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)
- Oracle — [JDK Mission Control](https://docs.oracle.com/en/java/java-components/jdk-mission-control/index.html)