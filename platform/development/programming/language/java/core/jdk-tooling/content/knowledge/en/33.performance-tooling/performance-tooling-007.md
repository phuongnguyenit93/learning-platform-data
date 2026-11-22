# Profiling instrumentation in Java

Profiling instrumentation is the technique of adding observability mechanisms to an application or the JVM to collect performance data such as execution time, invocation counts, allocations, lock waits, and runtime events. This data helps identify which methods, threads, classes, or components are consuming resources.

In Java 17+, multiple layers of tooling are available: Java agents and the Instrumentation API to observe or transform bytecode; the JVM Tool Interface (JVMTI) to build native agents; Java Flight Recorder (JFR) to collect events and samples; and JMX to read aggregate metrics. Choosing the right mechanism helps gather the required evidence with controllable overhead.

## 1. What are profiling and instrumentation?

**Profiling** is the process of measuring and analyzing runtime behavior to understand how an application uses CPU, memory, threads, and I/O.

**Instrumentation** is the act of adding observation code or hooks into a program to collect data. For example:

- Recording the start/end time of an operation.
- Counting how many times a method is called.
- Recording when classes are loaded.
- Emitting a JFR event when an important business operation completes.
- Inserting bytecode to time methods or trace calls.
- Receiving events from the JVM about threads, GC, monitors, or compilation.

Instrumentation can be implemented directly in source code, via a Java agent, using a native agent, or through an event framework built into the JVM.

The goal is to generate enough data to answer a specific performance question. You should not instrument every method and every object from the start, because the data volume and overhead can alter the very behavior being measured.

## 2. Distinguishing sampling and instrumentation

Two common approaches to observing code execution are sampling and instrumentation.

| Characteristic | Sampling profiler | Instrumentation profiler |
|---|---|---|
| How it works | Samples stacks/threads periodically or on events | Inserts hooks into methods/events to record activity |
| Scope | Locations sampled within the observation window | Only the instrumented methods/events |
| Granularity | Statistical; does not capture every call | Can observe every individual call or event |
| Overhead | Usually lower with reasonable sampling rates | Can grow rapidly if high-frequency methods are instrumented |
| Best suited for | Finding CPU hotspots, call trees, overall behavior | Measuring a specific business operation, counting invocations, selective tracing |
| Limitations | May miss short-lived or infrequent methods | Hooks can alter the timing and behavior being measured |

Sampling answers the question "where are threads usually spending time when sampled?". Instrumentation answers "how many times did the selected methods/events occur, and how long did they take?".

Neither technique is universally more accurate. Start with sampling to narrow down hotspots; then instrument selectively when you need detailed numbers for a specific business flow.

## 3. Profiling mechanisms in Java

| Mechanism | Level | Use cases |
|---|---|---|
| JFR | Built-in JVM events and sampling | CPU, allocation, GC, locks, I/O, custom events |
| Java agent / Instrumentation API | Java bytecode | Observing class loading or transforming methods |
| JVMTI | Native JVM interface | Profilers/native tooling requiring deep events and control |
| JMX / MXBean | JVM/application management metrics | Thread count, heap, GC count, uptime, aggregate metrics |
| Source-level instrumentation | Application code | Measuring business operations, request stages, queues, or specific dependencies |
| JMH | Benchmark framework | Comparing performance of code snippets in a controlled benchmark environment |

JFR and JMC are usually the first choice for production investigations because many runtime events are already built in. A Java agent is suitable when you need to observe or transform bytecode. JVMTI is intended for native tools needing deeper access. JMX provides aggregate metrics, while JMH is used for benchmarking and validating changes in a test environment.

## 4. How does a Java agent work?

A Java agent is a JAR loaded by the JVM on demand. An agent can receive an **Instrumentation** object to register class transformers, inspect class information, and request JVM retransformation/redefinition when supported by the runtime.

There are two common entry points:

- **premain(String agentArgs, Instrumentation inst):** the agent is loaded at JVM startup via **-javaagent**.
- **agentmain(String agentArgs, Instrumentation inst):** the agent is loaded after the JVM is already running, if the runtime and policy allow dynamic attach.

When launched with **-javaagent**, the JVM invokes **premain** before the application's **main** method. The agent JAR must declare **Premain-Class** in its manifest.

Example:

~~~powershell
java -javaagent:profiling-agent.jar -jar application.jar
~~~

An option string can be passed:

~~~powershell
java -javaagent:profiling-agent.jar=include=demo,verbose=true -jar application.jar
~~~

The agent receives everything after the equals sign in the `agentArgs` parameter; parsing the option string is up to the agent itself.

If `premain` throws an unhandled exception, the JVM may abort application startup. Therefore, production agents should initialize cleanly, handle errors explicitly, and avoid breaking startup over a non-critical metric.

## 5. Instrumentation API and ClassFileTransformer

The API resides in the **java.instrument** module, package **java.lang.instrument**.

Key components:

- **Instrumentation:** provides services for instrumenting Java programs running in the JVM.
- **ClassFileTransformer:** receives bytecode when a class is loaded, redefined, or retransformed.
- **addTransformer(...):** registers a transformer.
- **retransformClasses(...):** asks the JVM to re-apply transformers to already-loaded classes if supported.
- **redefineClasses(...):** replaces class definitions with new bytecode if supported.
- **isModifiableClass(...):** checks whether a class can be modified.

`ClassFileTransformer.transform(...)` receives the class name, class loader, protection domain, and the class file byte array. The transformer can return transformed bytecode. If it returns `null`, the class remains unchanged from that transformer's perspective.

A transformer that only observes class loading can count or log class names. To measure individual method durations, the agent must insert bytecode that invokes hooks on method entry/exit, typically using a bytecode library such as ASM or Byte Buddy.

### 5.1. Load-time and retransformation

**Load-time transformation** happens when the JVM loads a class. This is a convenient point to process bytecode before the class is defined.

**Retransformation** re-applies transformers to classes that have already been loaded. The agent must declare retransformation capability in its manifest and check `Instrumentation.isRetransformClassesSupported()` before calling the API.

Certain structural class changes are restricted. Standard retransformation/redefinition is not a mechanism for arbitrarily adding/removing fields or methods, changing method signatures, or altering inheritance hierarchies. You must adhere to the limits of the Instrumentation API and the JVM.

### 5.2. Agent manifest

Minimal manifest example:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProfilingAgent
~~~

If the agent needs retransformation, you can also declare:

~~~text
Can-Retransform-Classes: true
~~~

If class redefinition is needed, declare `Can-Redefine-Classes: true` and check whether the runtime supports it. Do not declare capabilities that the agent does not use.

## 6. Example: Java agent observing class loading

This example registers a transformer to count classes in the `demo` package. It illustrates the agent lifecycle and the `ClassFileTransformer` callback. The transformer returns `null`, so this example only observes class loading and does not insert method-timing bytecode.

Create `src/demo/ProfilingAgent.java`:

~~~java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.concurrent.atomic.AtomicInteger;

public final class ProfilingAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        AtomicInteger observed = new AtomicInteger();

        inst.addTransformer((loader, className, classBeingRedefined,
                             protectionDomain, classfileBuffer) -> {
            if (className != null && className.startsWith("demo/")) {
                int count = observed.incrementAndGet();
                if (count <= 10) {
                    System.out.println("[agent] observed "
                            + className.replace('/', '.'));
                }
            }
            return null;
        });

        Runtime.getRuntime().addShutdownHook(new Thread(
                () -> System.out.println(
                        "[agent] demo classes observed: " + observed.get()),
                "profiling-agent-summary"
        ));
    }
}
~~~

Create manifest `manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProfilingAgent

~~~

Create application file `src/demo/TargetApp.java`:

~~~java
package demo;

public final class TargetApp {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            process(i);
        }
        System.out.println("Application completed.");
    }

    private static void process(int id) {
        String payload = "task-" + id;
        System.out.println("processed " + payload);
    }
}
~~~

Compile the agent and application:

~~~powershell
javac -d agent-classes src/demo/ProfilingAgent.java
jar --create --file profiling-agent.jar --manifest manifest.mf -C agent-classes .
javac -d app-classes src/demo/TargetApp.java
~~~

Run:

~~~powershell
java -javaagent:profiling-agent.jar -cp app-classes demo.TargetApp
~~~

With the sample program having only one application class in the `demo` package, the output looks like:

~~~text
[agent] observed demo.TargetApp
processed task-0
processed task-1
processed task-2
Application completed.
[agent] demo classes observed: 1
~~~

The order of class messages may vary when an application has multiple classes or multiple threads loading classes concurrently. This example does not measure method duration. To measure individual methods, you need to transform bytecode and insert entry/exit hooks, or use custom JFR events/source instrumentation.

## 7. Bytecode instrumentation for method timing

A profiler using bytecode instrumentation typically performs these steps:

1. Select classes/methods to instrument based on package, annotation, or configuration.
2. The transformer reads the class file.
3. A bytecode library inserts a hook at the beginning of the method.
4. The hook records a timestamp or starts an event.
5. Hooks on every exit path of the method record the duration and completion status.
6. The transformer returns the new bytecode for the JVM to define the class.

Method duration measurement must handle both normal returns and exceptions. If you only add a hook at the end of a method, exceptions will cause the end event to be missed. Bytecode typically needs a `try`/`finally` equivalent to close the event on every exit path.

Commonly used libraries:

- **ASM:** low-level bytecode manipulation library offering fine-grained control over instructions and stack frames.
- **Byte Buddy:** higher-level API for creating and transforming classes/methods.
- **Javassist:** library supporting bytecode editing via a more source-oriented API.

These libraries are not part of the standard JDK. You must declare dependencies, package the agent, and test compatibility with the JDK, class loaders, and application frameworks.

### 7.1. Inclusive and exclusive time

If method A calls B and then C:

- **Inclusive time of A** includes the time spent in A plus the child methods called inside it.
- **Exclusive/self time of A** is the time spent executing A itself, excluding the time spent in child methods.

If you sum the inclusive times of all methods, the same time interval can be counted multiple times. When reading a profile tree, make sure you know whether a column displays inclusive or self time.

### 7.2. Counting invocations and duration

A profiler can collect invocation count, total duration, average duration, min/max duration, and error count. Tags such as endpoint, operation type, or workload class can be added if needed.

Averages can hide tail latency. If a method has a skewed latency distribution, inspect histograms or percentiles such as p50, p95, and p99 instead of looking only at the average.

## 8. JFR: built-in JVM profiling

Java Flight Recorder is a runtime event collection framework built into the JVM. JFR includes events for diagnosing CPU, threads, allocations, GC, locks, I/O, and many other activities.

JFR supports two main collection modes:

- Instant events: record an event occurring at a single point in time.
- Duration events: call `begin()` and `end()` to measure a time interval.

JFR also provides sampling events such as `jdk.ExecutionSample` and `jdk.ObjectAllocationSample`. Sampling is useful for finding hotspots without inserting hooks into every method.

A recording can be started at JVM startup:

~~~powershell
java -XX:StartFlightRecording=name=profile,settings=profile,duration=60s,filename=profile.jfr -jar application.jar
~~~

For a running JVM:

~~~powershell
jcmd <PID> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
jcmd <PID> JFR.check
~~~

Dump an active recording:

~~~powershell
jcmd <PID> JFR.dump name=profile filename=profile-snapshot.jfr
~~~

Stop a recording:

~~~powershell
jcmd <PID> JFR.stop name=profile
~~~

Open the file in JDK Mission Control (JMC) to inspect method profiling, allocations, locks, threads, I/O, and GC. JMC is a separate tool; not every JDK distribution bundles JMC by default.

## 9. Creating custom JFR events to instrument business operations

When you need to measure a business operation, you can define a custom event by extending `jdk.jfr.Event`.

A custom event can contain the operation name, input size, completion status, non-sensitive result code, and duration from `begin()` to `end()`. Stack traces can be enabled if requested by the recording settings.

Use annotations to specify the event name, label, category, and description. Fields must have types supported by JFR. Avoid putting passwords, tokens, sensitive request contents, or personal identifiers into the payload.

### 9.1. Event.begin, end, commit, and shouldCommit

- `begin()` marks the start of a duration event.
- `end()` marks the end time.
- `commit()` writes the event to the recording.
- `isEnabled()` checks whether the event is currently enabled.
- `shouldCommit()` checks whether the event qualifies to be recorded under the current settings.

You can use `isEnabled()` to avoid gathering expensive payload data when the event is disabled. After ending the event, call `shouldCommit()` before `commit()` when you want to avoid preparing/writing unnecessary data.

## 10. Java 17+ example: runnable custom JFR event

Create `ProfilingEventDemo.java`:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class ProfilingEventDemo {
    @Name("com.example.WorkUnit")
    @Label("Work Unit")
    @Category({"Application", "Profiling"})
    public static final class WorkUnitEvent extends Event {
        @Label("Work ID")
        int workId;

        @Label("Input Size")
        int inputSize;

        @Label("Result")
        long result;
    }

    private static long processWork(int workId) {
        long sum = 0;
        for (int i = 1; i <= 200_000; i++) {
            sum += (i * 31L + workId) % 97;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.setName("profiling-instrumentation");
            recording.enable(WorkUnitEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.start();

            for (int id = 1; id <= 5; id++) {
                WorkUnitEvent event = new WorkUnitEvent();
                if (event.isEnabled()) {
                    event.workId = id;
                    event.inputSize = 200_000;
                    event.begin();
                    event.result = processWork(id);
                    event.end();

                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }
            }

            recording.stop();
            recording.dump(Path.of("profiling-events.jfr"));
        }

        System.out.println("Work units processed: 5");
        System.out.println("Recording written: profiling-events.jfr");
    }
}
~~~

Compile and run on JDK 17:

~~~powershell
javac --add-modules jdk.jfr ProfilingEventDemo.java
java --add-modules jdk.jfr ProfilingEventDemo
~~~

Stdout:

~~~text
Work units processed: 5
Recording written: profiling-events.jfr
~~~

Inspect the recording:

~~~powershell
jfr summary profiling-events.jfr
jfr print --events com.example.WorkUnit profiling-events.jfr
~~~

In JMC, look for the **Work Unit** event under the **Application / Profiling** category. Each event contains the work ID, input size, result, duration, and stack trace. This example instruments exactly the five selected operations; the event count does not depend on method sampling.

`Duration.ZERO` allows the demo recording to capture even short operations. In production, consider an appropriate threshold and enable only necessary events to avoid generating overly large recordings.

## 11. JMX and MXBeans: aggregate metrics

JMX (Java Management Extensions) provides a management and monitoring interface for the JVM and applications. Built-in platform MXBeans are available via `ManagementFactory`:

- `ThreadMXBean`: thread count, peak, daemon count, and thread info.
- `MemoryMXBean`: heap/non-heap usage.
- `ClassLoadingMXBean`: currently loaded classes, total loaded, and unloaded counts.
- `GarbageCollectorMXBean`: collection count and collection time.
- `RuntimeMXBean`: uptime, VM arguments, and runtime info.
- `CompilationMXBean`: total compilation time if supported by the runtime.

JMX is useful for tracking metrics over time and building dashboards/alerts. It does not by itself provide detailed per-method call trees. When you need to know which methods cause CPU hotspots, use JFR or a profiler.

You can combine JMX with JFR: metrics tell you when an anomaly occurs; a recording shows which threads/events/stacks may explain that anomaly.

## 12. JVMTI: native profiling agent

JVMTI (JVM Tool Interface) is a native interface for tools that need to inspect or control JVM state. JVMTI agents are typically written in C/C++ and use the `jvmti.h` header in the JDK.

JVMTI provides event callbacks for class loading, threads, methods/compiled methods, and many VM activities; queries for threads, stack frames, monitors, and heap based on capabilities; and hooks to observe class file loading and instrument bytecode.

A native agent can be loaded with:

~~~powershell
java -agentlib:profiler -jar application.jar
~~~

Or by specifying the library path:

~~~powershell
java -agentpath:C:\tools\profiler.dll -jar application.jar
~~~

On Linux, native libraries typically have a `.so` extension; on macOS they may be `.dylib`. Naming and paths depend on the platform.

JVMTI is not a Java agent. It requires a native library, a C/C++ toolchain, and familiarity with JNI and the JVM lifecycle. Not every JVM implementation supports all of JVMTI. Choose JVMTI when you need a native profiler or observability capabilities that JFR/Java agents cannot provide.

## 13. JMH is not a profiler

JMH (Java Microbenchmark Harness) is a framework for measuring microbenchmark performance. JMH helps manage warm-up, forking, iterations, dead-code elimination, and other factors that can easily skew benchmark results.

Key distinctions:

- A profiler answers where the application is spending time or resources.
- Instrumentation adds observability data to methods or operations.
- JMH measures the timing/throughput of a code snippet in a controlled benchmark.

You can run JMH alongside a profiler to investigate why a benchmark is slow, but benchmark results do not replace production recordings. Do not use a simple `System.nanoTime()` loop as a substitute for JMH when doing serious microbenchmark comparisons.

## 14. Measuring time properly

When instrumenting manually, use `System.nanoTime()` to measure elapsed time. Do not use `System.currentTimeMillis()` for short durations because it is a wall-clock time source that can be adjusted.

Example:

~~~java
long start = System.nanoTime();
try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    recordDuration(elapsedNanos);
}
~~~

`nanoTime()` is a monotonic clock suitable for measuring time differences; do not use its absolute value as a date-time timestamp.

If measuring a method that can throw exceptions, place the duration recording in `finally`. For nested methods, decide clearly whether you want inclusive or exclusive time. With async code, method return may only mark task creation rather than work completion; instrument the actual start and completion points of the operation.

## 15. Overhead and the observer effect

Instrumentation consumes CPU and memory, and can alter application timing. This is the observer effect: the observation tool affects the system being measured.

Common sources of overhead:

- Invoking hooks on every method call.
- Taking timestamps too frequently.
- Allocating objects/events/strings on every call.
- Writing synchronous logs inside callbacks.
- Using shared locks to update counters.
- Capturing stack traces or large payloads.
- Instrumenting the JDK, frameworks, and libraries instead of only the packages under investigation.

Ways to reduce overhead:

1. Pick a specific question and instrument only the points needed.
2. Prefer JFR sampling first to narrow down hotspots.
3. Filter packages/classes/methods; do not instrument the entire classpath.
4. Use efficient counters like `LongAdder` when multiple threads update them.
5. Do not perform synchronous logging on hot paths.
6. Use `isEnabled()`/`shouldCommit()` for custom JFR events.
7. Limit recording duration and event thresholds.
8. Compare throughput/latency with the profiler enabled versus disabled.

Never assume a profiler has "zero overhead". Measure the impact on a representative workload and document the instrumentation configuration alongside the results.

## 16. Pitfalls when instrumenting methods and bytecode

### 16.1. Exceptions and all exit paths

The end hook must run whether a method returns normally or throws an exception. Bytecode transformers must handle all return opcodes and exception handlers; missing an exit path will leave events unclosed or produce inaccurate counters.

### 16.2. Recursion and reentrancy

If a hook calls back into an instrumented method, the profiler can create an infinite loop. Use appropriate guards/reentrancy flags, avoid instrumenting the agent's own packages, and avoid calling complex APIs from within a transformer.

### 16.3. Class loaders and modules

An agent may encounter multiple different class loaders and modules. Agent helper classes are not necessarily visible from every loader. Instrumenting bootstrap classes or modules may require adjusting module reads/opens and the bootstrap search path; this is error-prone and should only be done when truly necessary.

### 16.4. Concurrency in transformers

The JVM may invoke transformers concurrently from multiple threads. Transformers should be thread-safe, avoid holding locks for long periods, avoid heavy I/O, and avoid triggering recursive class loading during transformation.

### 16.5. JIT and method inlining

The JIT compiler may inline methods or compile code in ways that make stack traces or profiling views differ from the source structure. A profiler must understand whether an event represents an interpreted frame, compiled frame, or inlined frame. Do not assume every method call appears as an independent frame.

## 17. Choosing a tool based on the question

| Question | Mechanism to start with |
|---|---|
| Which methods consume the most CPU? | JFR execution sampling / sampling profiler |
| Which classes/stacks cause high allocations? | JFR allocation events |
| Which threads are waiting on locks? | JFR monitor/park events and JMC |
| How long does a specific business operation take? | Custom JFR event or source instrumentation |
| Need to observe which classes are loaded? | Java agent + ClassFileTransformer |
| Need to modify bytecode to measure invocations? | Java agent + ASM/Byte Buddy |
| Need deep native stacks or JVM-level hooks? | JVMTI/native profiler |
| Want a dashboard of heap/thread/GC counts? | JMX/MXBean |
| Want to compare two algorithms in a benchmark? | JMH |

A practical workflow is to use JFR/JMC to narrow down the issue, add a custom event or agent for the specific operation, and then use JMH to benchmark changes in a controlled environment.

## 18. Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Failed to find Premain-Class | Missing or incorrect Premain-Class in manifest | Check the manifest inside the agent JAR |
| ClassNotFoundException for agent | JAR missing the class or wrong package | Verify JAR structure and fully qualified class name |
| JVM exits immediately at startup | `premain` threw an exception or agent init failed | Log errors clearly, check dependencies and startup logs |
| Transformer is not invoked | Agent registered after class loaded, or filter too narrow | Register early via `premain`, check internal class names like `pkg/Class` |
| Transformer runs but methods are not measured | Transformer only observes classes or returns original bytecode | Integrate a bytecode library and insert entry/exit hooks |
| `retransformClasses` fails | Capability not enabled or class is not modifiable | Check manifest, `isRetransformClassesSupported()`, and `isModifiableClass()` |
| Custom JFR event does not appear | Event not enabled, not committed, or threshold too high | Check `isEnabled`, `shouldCommit`, settings, and `jfr summary` |
| Incorrect duration or missing events | Exceptions/nested/async completion not handled | Use `finally`, define clear boundaries, and check all exit paths |
| CPU spikes when agent is enabled | Instrumentation too broad or hooks too heavy | Narrow scope, reduce allocations/logging, and measure overhead |
| Class loading errors after instrumentation | Invalid bytecode/frames/modules/classloader visibility | Check transformer, bytecode verifier, and JDK/library compatibility |

## 19. Security and operations

Agents and profilers run in the same process as the application and can access runtime data. Only load agent JARs or native libraries from trusted sources.

- Verify the origin and contents of agent JARs before deployment.
- Restrict write permissions on recording files and logs.
- Do not record secrets, tokens, request contents, or personal data in custom events.
- Restrict dynamic attach according to runtime and environment policies.
- Use appropriate JMX permissions; do not expose management endpoints to untrusted networks.
- Document JDK version, agent version, bytecode dependencies, and profiler configuration.
- Have a safe way to disable the agent/recording if overhead or errors occur.

## 20. Workflow for deploying profiling instrumentation

1. Identify the symptom and the question to answer.
2. Choose the appropriate mechanism: sampling, JFR event, Java agent, JVMTI, or JMX.
3. Start with a small scope and limited duration.
4. Verify that collected data includes timestamps, threads, stacks, and required fields.
5. Measure overhead using a representative workload.
6. Cross-check measurements against a baseline and independent metrics.
7. Expand instrumentation only when initial evidence is insufficient.
8. Verify exception handling, recursion, async completion, and thread safety.
9. Test on staging/canary before broad rollout.
10. Document configuration, results, and how to roll back/disable instrumentation.

## 21. Profiling instrumentation checklist

- [ ] Defined a specific performance question.
- [ ] Distinguished sampling from bytecode/source instrumentation.
- [ ] Selected the right mechanism: JFR, Java agent, JVMTI, JMX, or JMH.
- [ ] Java agent has the correct manifest and entry point.
- [ ] Transformer filters classes accurately and is thread-safe.
- [ ] Bytecode instrumentation handles returns, exceptions, and all exit paths.
- [ ] Clarified inclusive/exclusive time and invocation counts.
- [ ] Custom JFR event has useful fields, clear labels, and categories.
- [ ] Used `isEnabled()`/`shouldCommit()` where appropriate.
- [ ] Measured duration using `System.nanoTime()` or JFR duration.
- [ ] Checked overhead and the observer effect.
- [ ] Verified class loader, module, recursion, and JIT behavior.
- [ ] Protected recordings, agents, and sensitive data.
- [ ] Compared results against a baseline/equivalent workload.
- [ ] Prepared a way to disable or roll back instrumentation.

Profiling instrumentation provides additional data to understand runtime behavior. Sampling such as JFR helps locate hotspots with typically low cost; Java agents and JVMTI enable deeper instrumentation; custom JFR events measure exact business operations; JMX tracks aggregate metrics; and JMH validates microbenchmarks. Start with a specific question, limit the scope, measure overhead, and distinguish observed data from conclusions inferred from that data.

## References

- Oracle, Java SE 17 API — java.lang.instrument package: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle, Java SE 17 API — Instrumentation: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle, Java SE 17 Specification — JVM Tool Interface (JVMTI): https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
- Oracle, Java SE 17 API — jdk.jfr package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle, Java SE 17 — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, JDK Mission Control 9 User Guide: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html