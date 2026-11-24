# 1.6 Distinguishing Observation, Profiling, Debugging, and Runtime Configuration Changes

## Learning Objectives

When a running Java application experiences rising latency, high CPU, intermittent errors, or abnormal behavior, operators face four easily confused categories of actions: **observation/monitoring**, **profiling**, **debugging**, and **runtime configuration changes**. After this lesson, you will be able to:

- Choose the right approach based on the diagnostic question and acceptable intervention level.
- Distinguish data that reveals **symptoms**, data that pinpoints **resource consumption hotspots**, evidence that explains **state/control flow**, and actions that **alter the system**.
- Use common JDK 17+/21 tools such as JMX, `jcmd`, Java Flight Recorder (JFR), and JDWP for their intended purposes.
- Evaluate observation overhead, conclusion reliability, access permissions, production impact, and reversibility.

## 1. Four Concepts and Core Boundaries

| Activity | Primary Question | Typical Signals/Actions | Typical Impact Level | Desired Outcome |
| --- | --- | --- | --- | --- |
| **Observation** | *What is happening in the system, when, and where?* | Metrics, logs, distributed traces, health/status, JMX, a few thread dumps at defined times | Low when collected with controls; not automatically zero | Identify symptoms, trends, scope, timing, and correlations |
| **Profiling** | *Where are CPU, memory, allocations, locks, or time concentrated?* | JFR events/samples, CPU/alloc profilers, flame graphs, contention profiles | Low to substantial depending on sampling, events, rate, and duration | Locate hotspots, cost distribution, and optimization hypotheses |
| **Debugging** | *Why did this branch run, why does this variable hold this value, why is this thread paused here?* | Breakpoints, step into/over, stack frames, inspect/evaluate expressions via debugger/JDWP | Can be large: pauses threads, alters scheduling, affects state | Explain a specific execution path and find logic bugs |
| **Runtime configuration change** | *If a supported parameter/behavior is adjusted, does behavior change as expected?* | Changing log levels, certain MBeans/feature flags, `jcmd VM.log`, modifiable VM flags | It is an **intervention**; can change load, behavior, security, or resources | Mitigate an incident or test a controlled change and measure impact |

One tool or action can serve multiple purposes: JFR with the `default` profile is often used for timeline observation, whereas JFR `profile` is used for deeper analysis. Enabling extra logging is a **configuration change to increase observability**; the act of toggling logging is still an intervention. Capturing a single thread dump is a state snapshot, not statistical profiling without enough samples.

**Default production sequence:** observe to narrow scope → bounded profiling to verify hotspots → debugging in a reproducible environment when logic explanation is needed → change runtime configuration only with a clear goal, risk bound, and rollback path. You can return to observation at any step to verify results.

## 2. Observation: Seeing Symptoms Without Jumping to Causes

Observation collects signals continuously or periodically to answer **what, how long, who is affected, and since when**.

**Three common application sources:**

1. **Metrics** are time-indexed measurements: throughput, error rate, p50/p95/p99 latency, queue length, heap used, GC pauses, live thread count, process CPU, file descriptors. Counters must be read as a *rate of increase over an interval* when rate is needed; a cumulative value alone does not show current speed.
2. **Logs** record events with timestamps, levels, context, and processing outcomes. Correlation IDs (request/trace ID), component names, error types, and durations are more useful than noisy `debug` lines everywhere. Restrict personal data, tokens, and sensitive payloads.
3. **Traces** connect spans within a request across layers/services, showing how time breaks down across branches, RPCs, DB calls, or queues. A slow span reflects where time was recorded; it does not by itself prove high CPU in that span.

**JVM and OS layers:** through JMX/MXBeans you can observe memory pools, GC, threads, and class loading; through OS tools you observe CPU, RSS, disk I/O, network, and container limits. Cross-check layers: stable heap does not mean stable RSS; high process CPU does not mean every request consumes CPU.

Example: `p99` climbs from 120 ms to 900 ms while request rate rises. What you can assert is that **the latency tail worsened during the measurement window**. You cannot yet conclude GC, locks, DB, or CPU. If GC pause charts stay flat while threads waiting on the connection pool increase, the investigation direction shifts. Always compare matching time windows, traffic levels, and endpoint/version groups.

**Observation also has impact:** collecting metrics with high-cardinality labels, heavy synchronous logging, very high trace sampling, frequent dumps, or heavy JMX queries all add overhead. Thread dumps reflect the capture instant and can miss rare faults. State resolution, sampling, and measurement limits explicitly.

## 3. Profiling: Locating Where Resources Are Spent

Profiling analyzes **cost distribution** during execution, typically via stack sampling or events/instrumentation recorded by the JVM or a tool.

- **CPU profile:** which threads/methods appear frequently in samples while executing on CPU; useful when process CPU is high. CPU time differs from **wall-clock latency**: requests waiting on locks/I/O can be slow while using little CPU.
- **Wall-clock/lock profile:** time spent blocked, waiting on locks, parked, or in I/O; useful when requests are slow despite low CPU. Do not infer causes from a single stack trace.
- **Allocation profile:** where the most objects/bytes are allocated; does not mean those objects live long or cause a memory leak. To find retained references/leaks, examine heap, retained size, object lifetimes, GC, and growth evidence over time.
- **GC profile:** pause frequency, pause duration, allocation rate, heap pressure; large pauses are evidence about GC at that time, yet still require correlation with latency and workload.
- **Flame graph:** frame width represents sample/cost proportion per profiler configuration; it is neither a call-count diagram nor absolute causal proof. Distinguish *inclusive* time (including callees) from *exclusive/self* time (that function alone).

**Sampling vs. instrumentation differ:** periodic sampling captures stacks with typically lower overhead but can miss rare paths; instrumentation can measure exact calls/events yet introduces higher overhead or alters timing more significantly. JFR overhead depends on enabled events and settings: `default` targets lightweight collection, while `profile` collects more data; measure on realistic workloads and bound duration and disk size.

**Workflow for trustworthy profiling:**

1. Lock in a specific question, e.g., "During the 60 seconds of elevated CPU, which Java code accounts for the most CPU samples?"
2. Record version, JVM/JDK, configuration, load, start/end times, and baseline before sampling.
3. Choose the right profile type (CPU, allocation, lock, GC); sample long enough to be representative, avoiding mixing warm-up if targeting steady state.
4. Analyze distributions and corroborate with metrics/logs/traces; verify via repeated measurements or controlled tests before optimizing.
5. Stop the recording, clean up files, and manage permissions: `.jfr` files can contain class/method names, paths, and sensitive operational data.

**Inference limits:** not seeing a method in a profile does not prove the method did not run; frequent appearance in samples only indicates concentration of activity under measured conditions. Profiling **locates** hotspots, while explaining why logic reached that state may require debugging or code inspection.

## 4. Debugging: Explaining State and a Specific Execution Path

A debugger (typically communicating with the JVM via **Java Debug Wire Protocol – JDWP**) can set breakpoints, inspect stack frames, local variables, call order, step through code, and evaluate expressions. It is useful when you have an input that reproduces a bug: "Why does this condition return `true`?" or "In which branch was this variable overwritten?"

**Difference from profiling:** a breakpoint shows where one specific run is and what variables hold at that moment; it does not show what percentage of overall CPU that method consumes. Conversely, a CPU flame graph does not show all variable values during a failing run.

**Impacts to understand before attaching a debugger:**

- Breakpoints in suspend **All** mode can freeze the entire JVM or most application threads; suspend **Thread** mode can still cause deadlocks or timing anomalies when other threads wait on it. Upstream timeouts may occur simply because of the debugger.
- Expression evaluation, method invocation, setting values, and hot swap can **mutate state**; do not treat all debugger actions as read-only.
- Pausing alters thread scheduling, which can hide race conditions or introduce new failures. For concurrency bugs, prefer correlation-ID logs, JFR lock/park events, and multiple thread dumps at relevant timestamps.
- JDWP grants process-control access; enable only in trusted environments, restricted by network address and access controls. Never expose a debug port publicly in production.

When confirming a logic bug, build a reproducible test in development/staging with matching inputs, library versions, and key conditions; place narrow breakpoints, record reasoning steps, then remove debug settings. In production, prefer snapshots and controlled instrumentation before considering a debugger.

## 5. Runtime Configuration Changes: Actions That Control the System

Changing configuration at runtime **is not mere observation**. It alters input data, diagnostic verbosity, or the behavior of the process serving live traffic.

Distinguish three layers:

1. **Application configuration:** some systems support changing log levels via API/JMX, feature flags, cache thresholds, or thread pools designed for safe updates. Takes effect only if the application actually supports reloading/reading new values; editing a config file on disk does not guarantee the process reloads it.
2. **JVM/JDK configuration:** `jcmd VM.log` can view or adjust **JVM Unified Logging** at runtime; `jcmd VM.set_flag` can only change **flags the JVM marks as dynamically writable**. Startup options such as `-Xmx`, classpath, module path, or Java agents cannot generally be changed on a running process.
3. **Environment/deployment configuration:** changing environment variables, `-D...` command-line flags, or container configs usually affects only a **restarted** process; a running JVM does not automatically pick them up. `System.setProperty` in code is a special case and matters only if the relevant component re-reads the property.

**Boundary examples:** running `jcmd ... JFR.start` enables diagnostic collection without altering business algorithms; running `jcmd ... VM.log` changes logging behavior and may increase I/O; toggling a feature flag can change request routing. All three are runtime control operations with differing risk profiles.

Before changing: save current values, state target/scope/duration, rationale, and success metrics; check operational permissions, performance impact, and rollback. During change: apply **one variable** when possible, mark the change timestamp, and watch error rate, latency, throughput, CPU, and logs. After change: verify the config actually took effect, measure over a comparable load window, revert if thresholds breach, and decide whether to persist it into long-term deployment config. In-process changes may be **lost on restart**.

Separate two questions: "Is this change supported by the API/JVM?" and "Is this change safe right now?" Technical support does not automatically mean it should be done in production.

## 6. Mini Hands-On with Java 17+: One JVM, Multiple Views

Create **`DiagnosticsLab.java`** with the following content. This is a standalone Java program that runs continuously so there is time to observe and profile it:

```java
public final class DiagnosticsLab {
    private static volatile double lastResult;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        long rounds = 0;

        while (true) {
            double sum = 0;
            for (int i = 1; i <= 1_000_000; i++) {
                sum += Math.sqrt(i);
            }
            lastResult = sum;
            rounds++;

            if (rounds % 20 == 0) {
                System.out.println("rounds=" + rounds);
            }
            Thread.sleep(100);
        }
    }
}
```

The `lastResult` field is written as `volatile` to keep the computed result observable outside the loop; the loop generates a small CPU workload interspersed with `sleep`. The PID number, rate of `rounds=...` output, and CPU percentage **depend on the environment**, so there is no fixed stdout. Stop the demo with **Ctrl+C**.

Compile and run from the directory containing the file (JDK 17 or higher):

```bash
javac DiagnosticsLab.java
java DiagnosticsLab
```

In another terminal, use the actual PID printed by the program. The commands below illustrate with **PID 12345**; replace it with the demo JVM's PID and run `jcmd` from a suitable JDK on the same machine/account with attach permissions:

```bash
jcmd 12345 help
jcmd 12345 Thread.print
jcmd 12345 VM.flags
```

- `Thread.print`: a stack/thread-state snapshot; comparing multiple snapshots across timestamps reveals waiting/running trends. Do not call this a CPU profile.
- `VM.flags`: reads current JVM flags; does not prove every flag can be modified dynamically.
- `help`: verifies which diagnostic commands actually exist on the target JVM; tools may be restricted by permissions, distribution, disabled attach flags, or container boundaries.

**Collect a short profile using Java Flight Recorder:**

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check
```

Wait the full 60 seconds, then read `triage.jfr` where the target JVM is allowed to write; with relative paths, check the target process's working directory. You can open it with **JDK Mission Control (JMC)** or run:

```bash
jfr summary triage.jfr
jfr print --events jdk.ExecutionSample triage.jfr
```

`summary` counts event types/quantities; `jdk.ExecutionSample` displays CPU execution samples if the recording actually captured that event type. Event contents and counts are not fixed. With continuous recordings, `JFR.dump` writes a snapshot **without stopping the recording**; `JFR.stop` is a separate command. `settings=profile` increases detail compared to `default`, so use appropriate recording durations in production.

**Debug the same program locally:** stop the previous demo process and restart it with JDWP listening only on loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DiagnosticsLab
```

In your IDE, attach a Java debugger to `127.0.0.1:5005`; place a breakpoint at `lastResult = sum;` and inspect `sum` and `rounds` to understand **one iteration**. `suspend=n` lets the application start immediately; hitting the breakpoint can pause the process. Do not use this JDWP command as a default diagnostic operation on production systems.

**Inspect the runtime JVM logging mechanism (test only on the demo JVM):**

```bash
jcmd 12345 VM.log list
jcmd 12345 VM.log output=stdout what=gc=debug
jcmd 12345 VM.log list
```

The middle line changes **JVM GC logging** configuration, not application `java.util.logging`, Logback, or SLF4J. The command may not emit GC logs immediately if no matching events occur yet. Save the output of `VM.log list` before changing and restore the exact previous configuration after testing; do not assume `disable` is a safe rollback since it affects all JVM logging. To change a specific flag, check which flags allow dynamic updates and their risks; `VM.set_flag` does not turn every startup option into dynamic configuration.

## 7. Same Incident, Four Different Activities

Suppose a Java service shows **a sharp spike in p99 latency**, while error rate has not risen yet:

| Step | Action | Evidence or Decision |
| --- | --- | --- |
| 1. Observation | Correlate p99 with request rate, GC pauses, CPU, connection pools, waiting threads, and traces of the affected endpoint | Confirm which endpoints/time windows show symptoms; separate busy CPU from resource waits |
| 2. Profiling | Capture a short JFR while reproducing load; inspect CPU samples, lock contention, allocations, and timeline | See whether hotspots sit in CPU processing, synchronized/park waits, or allocation; cross-verify with multiple pieces of evidence |
| 3. Debugging | Write a test reproducing slow requests; place breakpoints on retry branches or lock contention in staging | Observe variable state and call order leading to logic bugs; note that the debugger alters timing |
| 4. Runtime change | Only when appropriate, raise the log level of the relevant component briefly or adjust a parameter that supports runtime updates | Watch logs/metrics before–after, verify effect, and revert; changes do not replace verifying root cause |

**Other scenarios for picking tools:**

- CPU at 95% with low latency on most requests: start with process CPU, load, and threads; use a **CPU profiler/JFR** to find hotspots. Setting breakpoints right away can disrupt the workload you need to measure.
- Intermittent request hangs with low CPU: check traces, queues, thread states, and lock events; **wall/lock profiling** is more useful than looking solely at a CPU profile.
- A specific input returns the wrong result under normal load: reproducible tests and **debugging** usually provide more direct insight than performance profiles.
- Need more failure context for 5 minutes: adjust **log level with controls**, monitor volume, and restore the prior value. Changing the log level is a runtime change; the resulting log lines are observation.
- Want to "increase heap immediately" due to high RSS: first separate heap used, native memory, container RSS, and GC; do not assume running `-Xmx` can be changed via `VM.set_flag`. If different startup options are needed, plan a separate restart/rollout.

## 8. Impact-Bounded Production Diagnostic Workflow

1. **Define symptoms and timeline:** which SLI/SLO degraded, impact scope, which release, what load conditions? Mark the onset timestamp to avoid mistaking workload shifts.
2. **Collect low-intrusion baselines:** JVM + OS metrics, correlated errors/logs, existing traces. Separate symptoms from hypotheses; avoid debugging before knowing the scope.
3. **Formulate measurable questions:** "Is it Java CPU or waiting on an external service?", "Which method has high allocation?", "Do GC pauses align with p99 spikes?".
4. **Choose tools and overhead budget:** specify data type, attach permissions, duration, sampling rate, disk space, file sensitivity, and stop criteria. Full heap dumps can be huge and cause pauses/memory impact; do not treat them as lightweight.
5. **Collect time-bounded evidence:** use appropriate sampling/JFR or snapshots tagged with timestamp and version; verify captured data covers the incident window. If a debugger is needed, prefer reproducing in staging.
6. **Explain and verify:** separate correlation from causation; validate symptoms across at least two data sources or reproduction. Do not claim an optimization succeeded solely because a flame graph looks different.
7. **If intervention is required:** record original config, scope, owner, timeout, safety signals, and rollback plan; apply small changes and observe before–after in comparable load windows.
8. **Wrap up and learn:** stop recordings/debug logs, revert experiments, secure/delete artifacts per policy, record which hypotheses were confirmed, and note missing telemetry to improve.

A system can be observable yet still hard to debug; a good profiler cannot fix a logic bug; and a runtime change that lowers latency does not by itself prove the initial cause unless other variables are controlled.

## 9. Common Misconceptions

- **"Monitoring and profiling are the same because both use JFR."** Not quite: the tool name does not determine the purpose. Tracking trends/timelines is observation; aggregating CPU/allocation/lock samples to locate hotspots is profiling.
- **"A thread dump proves a method uses a lot of CPU."** One dump is a single instant; a thread in `RUNNABLE` is not necessarily using CPU continuously. Multiple samples and CPU checks are needed.
- **"High allocation means a memory leak."** Heavily allocated objects can be reclaimed quickly; leaks require evidence of retained objects and rising live memory over time.
- **"A debugger only reads data, so it is safe in production."** Breakpoints can freeze threads; expression evaluation/hot swap can alter data and timing.
- **"All JVM flags can be tuned with `VM.set_flag`."** Only options the JVM allows to be dynamically updated can change; verify on the actual JVM/version.
- **"Editing a config file or env var updates the running process immediately."** No guarantee without a reload mechanism or process restart; verify effective state.
- **"Enable as much `debug` logging as possible."** Log volume, CPU/I/O, cardinality, and information leakage can worsen the incident. Narrow scope and set a time limit.
- **"Seeing improvement after a config change means the root cause was found."** It could coincide with load changes, cache warm-up, or other factors; still compare against baseline and technical evidence.

## 10. Self-Check on Selection

1. **High CPU, need to know the costliest method:** start with observation to confirm scope, then CPU profiling/JFR; do not use breakpoints as a CPU measurement tool.
2. **Wrong result on just one input:** build a test and debug the code branch; metrics show impact scale but do not replace inspecting variables.
3. **Want to enable GC logs for 2 minutes to test a hypothesis:** that is a runtime configuration change serving observation; save prior config, control volume, enable, then revert.
4. **High p99 with low CPU and many waiting threads:** use traces + thread states + lock/wall-clock profiling; an empty CPU flame graph does not rule out a bottleneck.
5. **Need to change the heap limit of a running service:** identify the JVM/startup option and deployment policy; do not assume dynamic flag modification is available.

**Rule to remember:** *Observation* identifies **phenomena and scope**; *profiling* shows **where cost concentrates**; *debugging* explains **why a specific execution ran that way**; *runtime configuration change* is **an action altering the process** and must be verified by subsequent observation.

### Official References (JDK 21)

- [Oracle — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): JFR, JMC, `jcmd`, diagnostic collection guidance.
- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): syntax for `JFR.start`, `JFR.dump`, `Thread.print`, `VM.flags`, `VM.log`, `VM.set_flag`, and impact notes.
- [Oracle — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog`, JVM configuration, startup options.