# JVMTI, Profilers, APM, and Observability Tools After Upgrading

After upgrading the JDK, a Java application may start normally and pass unit tests while observability tooling fails: a Java agent fails to initialize, a profiler fails to capture stack traces, APM drops traces, a native agent crashes the JVM, or performance numbers shift noticeably. This is not solely an application issue. **Agents and observability tools are also part of the execution environment that must undergo compatibility testing.**

Specifically, these tools can run **inside the JVM process itself**, access internal APIs, transform bytecode, rely on JVMTI, or call native libraries. A plugin may be compatible with Java 17 yet fail to parse Java 21 class files; a profiler may support the new JVM yet lack permission to read performance counters in a container; an APM agent may start up yet stop creating HTTP client spans after the framework was upgraded.

This lesson explains the roles of the **JVM Tool Interface (JVMTI)**, Java instrumentation agents, profilers, Java Flight Recorder (JFR), APM, and diagnostic tools. The focus is on verifying these tools after Java Advance Compatibility Migration without sacrificing stability or production safety.

## 1. Distinguishing Java Observability Tooling Layers

Tools grouped under "monitoring" have different goals and levels of intrusion.

| Tool Category | What It Usually Collects | Underlying Technologies | Risks When Upgrading JDK |
|---|---|---|---|
| **Native JVMTI agent** | Class loads, threads, methods, heap, JVM events | `jvmti.h`, JNI, `.so`/`.dll` libraries | ABI, capabilities, JVM implementation, native crashes |
| **Java agent** | Instrumentation, traces, metrics, method timings | `java.lang.instrument`, bytecode transformers | Class-file versions, framework APIs, module access |
| **CPU/Allocation profiler** | Hot methods, CPU time, allocations, lock contention | JFR, async sampling, JVMTI, OS perf events | Sampling semantics, OS permissions, native symbols |
| **JFR/JMC** | JVM events, GC, allocations, threads, compilation, execution samples | JDK Flight Recorder and JDK Mission Control | Event availability, settings, parser/tool versions |
| **APM/tracing agent** | HTTP spans, SQL spans, trace context, errors, JVM metrics | Java agent, instrumentation, OpenTelemetry | Instrumentation coverage, context propagation, overhead |
| **Metrics exporter** | JVM heap, GC, threads, process metrics | JMX, Micrometer, MXBeans, HTTP exporters | Metric names/types, GC changes, dashboard assumptions |
| **Diagnostic CLI** | Thread dumps, heap histograms, JVM flags, JFR recordings | `jcmd`, `jstack`, `jmap` depending on JDK | Permissions, attach availability, container restrictions |

**Do not treat every tool in the table above as a JVMTI agent.** JFR can be enabled with built-in JDK tooling without loading a third-party Java agent. A Java agent can use `Instrumentation` without writing any C/C++ code. Conversely, a native profiler can use JVMTI and OS sampling without modifying application bytecode.

### 1.1. One JVM Can Carry Multiple Instrumentation Layers

Example topology:

~~~text
Java service running in container
    |
    +--> -javaagent:/opt/agents/apm-agent.jar
    |        +--> transforms HTTP/JDBC bytecode
    |        +--> exports traces/metrics to collector
    |
    +--> -agentpath:/opt/profiler/libprofiler.so
    |        +--> uses native/JVMTI and sampling
    |
    +--> JVM built-in JFR
    |        +--> writes events to .jfr file
    |
    +--> JMX / MXBeans / exporters
             +--> heap, GC, thread, CPU metrics
~~~

During a JDK upgrade, **each layer has its own version, configuration, and compatibility mechanisms**. A failure in just one layer can render observability data unreliable.

## 2. What Is the JVM Tool Interface (JVMTI)?

**JVMTI** is the native programming interface for JVM development and monitoring tools. It provides a way to inspect state and control certain aspects of JVM execution such as classes, threads, stacks, objects, breakpoints, heap, or event callbacks.

By specification, JVMTI is designed for profiling, debugging, monitoring, thread analysis, and coverage. It is a **native interface**, typically used via C/C++ code and the `jvmti.h` header. JVMTI is not an ordinary Java API like `java.util.logging`.

### 2.1. Agents Live Inside the JVM Process

A JVMTI agent is usually packaged as a native library:

- Linux: `.so` file.
- Windows: `.dll` file.
- macOS: `.dylib` file per platform convention.

The agent is loaded into the same process as the application. It can register callbacks to receive JVM events, query class/method information, or request specific capabilities depending on the startup phase.

~~~text
JVM process
    |
    +-- Java application classes
    |
    +-- GC / JIT / thread runtime
    |
    +-- JVMTI environment
            |
            +-- Native agent A
            |      callbacks + capabilities
            |
            +-- Native agent B
                   callbacks + capabilities
~~~

JVMTI can support multiple agents coexisting, each with its own environment, yet **they still affect the same JVM and the same native process**. Two agents can conflict if both transform classes, process events, or generate CPU/memory pressure.

### 2.2. Starting a Native Agent

For example, the HotSpot JVM supports:

~~~bash
# Load by library name; the JVM searches the native library path.
java -agentlib:sampleProfiler=option1,option2 -jar app.jar

# Load a native library by explicit path.
java -agentpath:/opt/agents/libsampleProfiler.so=option1,option2 -jar app.jar
~~~

These commands illustrate syntax only; a valid vendor-supplied agent library is required. Do not run with arbitrary unverified files.

For a native JVMTI agent, the JVM invokes a startup function such as:

~~~c
#include <jni.h>
#include <jvmti.h>

/* Example entry-point signature, not a complete agent. */
JNIEXPORT jint JNICALL Agent_OnLoad(
    JavaVM *vm,
    char *options,
    void *reserved
) {
    return JNI_OK;
}
~~~

Real agents must also obtain a `jvmtiEnv`, check API return codes, negotiate capabilities, register callbacks, and manage JNI references and native resources. An `Agent_OnLoad` returning a non-zero error can prevent the JVM from starting.

### 2.3. Capabilities and Phases Matter More Than a Single Flag

JVMTI defines many capabilities such as observing events, retransforming classes, inspecting the heap, or catching breakpoints. Certain capabilities must be requested early; not all are available when an agent attaches to a running JVM.

Key phases:

1. **OnLoad:** native agent initializes before the application starts running.
2. **Start / Live:** the JVM has started, can emit most events, and executes the application.
3. **Dead:** the JVM is shutting down or has terminated.

If a profiler attaches only after the application is already running, it may miss class loads or startup events. Startup benchmarks with late attach are **not equivalent** to startup agents.

## 3. Java Agents and `java.lang.instrument`

A Java agent is written in Java and packaged as a JAR. It can inject measurement logic by transforming class bytecode before or after classes load, within the scope supported by the Instrumentation mechanism.

### 3.1. Startup Agents with `premain`

The agent JAR contains a manifest declaring `Premain-Class`. The JVM can load the agent right at startup:

~~~bash
java -javaagent:/opt/agents/telemetry-agent.jar -jar app.jar
~~~

A minimal entry point:

~~~java
package com.example.monitoring;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {
        System.out.println("Instrumentation agent started");
        System.out.println(
            "Retransform supported: " +
            instrumentation.isRetransformClassesSupported()
        );
    }
}
~~~

Example manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.monitoring.StartupAgent
Can-Retransform-Classes: true
~~~

This illustrates structure, not a complete APM agent. Actual retransform capability also depends on JVM and agent support; declaring the manifest header does not automatically allow every class to be rewritten.

### 3.2. Dynamic Attach with `agentmain`

A Java agent can declare an `agentmain` entry point to be loaded into a running JVM in runtimes that still permit this operation:

~~~java
public static void agentmain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Initialize instrumentation while JVM is running
}
~~~

Startup agents and dynamic agents are not identical:

| Aspect | Startup `-javaagent` | Dynamic Attach |
|---|---|---|
| Timing | When the JVM starts | After the application is already running |
| Entry point | `premain` | `agentmain` |
| Startup visibility | Can observe early phases | May miss startup phases |
| Security policy | Explicitly configured at launch | Subject to attach and dynamic agent loading policies |
| Rollout | Typically requires process restart | Can attach under runtime conditions |
| Risks | Startup fails if agent breaks | Attach blocked, missing capabilities, runtime perturbation |

### 3.3. Multiple Java Agents Can Transform the Same Classes

An application may simultaneously run an APM agent, a coverage agent, and a profiling agent. Transformers can execute sequentially and modify already transformed bytecode. If they are incompatible, failures can include:

- `VerifyError` or `ClassFormatError` when bytecode is invalid.
- `LinkageError` when classes/methods mismatch.
- `NoClassDefFoundError` because an agent dependency is missing.
- `InaccessibleObjectException` when the framework/agent uses disallowed deep reflection.
- Missing spans/metrics because a transformer fails to recognize a class modified by another agent.
- Increased CPU, allocations, or latency when instrumenting too many points.

Do not conclude an issue is a JDK bug merely because it appeared after upgrading the JDK: agents and bytecode libraries must be evaluated too.

## 4. Dynamic Agent Loading Policy and JEP 451

**JEP 451 – Prepare to Disallow the Dynamic Loading of Agents** was introduced in JDK 21 to prepare for stricter policies governing loading agents into a running JVM.

In HotSpot/JDK releases applying JEP 451 behavior, the JVM warns when loading a Java agent or JVMTI agent dynamically. The goal is clarifying that instrumentation can alter application code and must be approved by the runtime owner.

Example warnings may look like:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: Dynamic loading of agents will be disallowed
         by default in a future release
~~~

**What to understand accurately:**

- The warning does not mean all Java agents are banned.
- Agents loaded at startup via `-javaagent` or `-agentpath` remain the standard model approved explicitly by the runtime owner.
- **Dynamic agent loading** falls under separate attach-mechanism policies, and whether it is allowed or disallowed must be checked on the exact deployed JDK and vendor.
- Do not infer from JDK 21's warning that all subsequent JDK releases share the exact same default; inspect release notes for the target release.

On HotSpot, dynamic agent loading can be explicitly permitted with the option:

~~~bash
java -XX:+EnableDynamicAgentLoading -jar app.jar
~~~

Enabling this option must be a controlled decision, not a reflex to silence warnings across every application.

### 4.1. Distinguishing Dynamic Attach from Diagnostic Commands

Certain operations such as `jcmd`, thread dumps, or capturing JFR can use JVM diagnostic mechanisms **without loading an arbitrary external agent**. Do not assume all diagnostic attach actions are governed identically to `loadAgent`.

Conversely, a profiler using attach to load a native JVMTI agent into the JVM may be subject to dynamic agent loading restrictions and OS/JVM permissions.

### 4.2. When Older Profilers Rely on Production Attach

Determine:

1. Must the profiler attach dynamically, or can it start via `-agentpath`?
2. Does the target JDK allow or deny dynamic agent loading by default?
3. Is there process access under the same user and container/PID namespace?
4. Does organizational security policy allow attaching agents to production JVMs?
5. Can built-in JFR be used instead of loading a third-party native agent?

If attach capability is essential, prepare a clear deployment approach and verify it in a production-like environment. Avoid weakening cluster-wide security policies just to run one profiler briefly.

## 5. Why Upgrading the JDK Can Break Agent Compatibility

### 5.1. Class File Versions and Bytecode Processing Libraries

A new JDK can generate class files with newer major versions and structures. A Java agent using ASM, Byte Buddy, or similar libraries may reject class files it does not yet support.

Example major versions:

| Java | Class file major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

If an old agent encounters newer class files, errors may look like:

~~~text
java.lang.IllegalArgumentException:
    Unsupported class file major version ...
~~~

or stack traces involving `ClassReader`, transformers, or retransform/redefine. Upgrade the agent or its bytecode dependency to a release vendor-supported for the target JDK, rather than arbitrarily downgrading the application's bytecode target to hide the error when the runtime has upgraded.

### 5.2. Bytecode Instrumentation Must Pass the Verifier

When an agent injects instructions or alters control flow, resulting bytecode must maintain valid operand stacks, stack map frames, and metadata. Class-file structure changes or verifier policies can expose transformer bugs.

Errors like `VerifyError`, `ClassFormatError`, or JVM crashes occurring **only when an agent is enabled** strongly signal isolating the agent.

Comparison workflow:

~~~text
Same JDK, same artifact, same workload
   |
   +-- Run without agents
   |
   +-- Run with APM agent only
   |
   +-- Run with profiler only
   |
   +-- Run with both APM + profiler
        |
        v
Compare crashes, errors, throughput, traces, class loading
~~~

This isolates the cause rather than proving an agent itself is always wrong if benchmark figures differ.

### 5.3. JPMS and Strong Encapsulation

Many agents need to intercept JDK or framework classes. Valid mechanisms go through `Instrumentation.redefineModule`; older agent versions instead use direct reflection into un-opened packages and may hit:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Do not copy `--add-opens` or `--add-exports` flags wholesale from logs without understanding:

- Which module/package requires access?
- Why does the agent need that access?
- Does the agent vendor already offer a release compatible with the new JDK?
- Does the flag increase risks of accessing JVM internals?
- Can privileges be narrowed or replaced with public APIs?

Module-opening flags are strictly scoped measures; they cannot fix too-new class files, incompatible native ABIs, or transformer logic bugs.

### 5.4. Native Binaries, ABIs, and Architecture

A native JVMTI agent is machine code. Verify:

- CPU architecture: `x86_64`, `aarch64`, etc.
- OS and kernel version.
- Base libraries/glibc and dynamic linker.
- JVM/HotSpot release and supported JVMTI features.
- Bundled native libraries, such as unwind libraries or profiler-specific dependencies.
- Container packaging and file permissions.

For example, an `.so` built for `x86_64` cannot load into an `aarch64` JVM. JDK upgrades often accompany container base-image updates or ARM migrations, so never automatically attribute everything to the JDK.

### 5.5. Native Crashes Differ from Java Exceptions

A bug in C/C++ code or a JVMTI callback can crash the entire process without necessarily producing a Java stack trace. The JVM may write an error file such as:

~~~text
hs_err_pid12345.log
~~~

Inspect that file for:

- Fatal error signal and problematic frame.
- Native library/agent on the active stack.
- JVM version/vendor/build.
- Crashing thread.
- VM arguments, loaded libraries, and GC/compiler context.

If the `problematic frame` points inside a native agent or bundled library, collect logs safely and coordinate with the vendor. Never re-enable an unverified agent in production just to "reproduce it for sure".

## 6. Profilers Differ from APM in Purpose and Collection Mechanisms

### 6.1. Profilers: Finding Resource Consumption

Profilers answer questions such as:

- Which threads consume the most CPU?
- Which methods appear most frequently in CPU samples?
- Which paths allocate the most objects?
- Is code waiting on locks or waiting on I/O?
- Do native stacks consume significant time?

A sampling profiler periodically captures thread stacks. It provides approximate statistical distributions over the sampling window, not an exact call list of every method invocation. Profiling for too short a window or under unrepresentative workloads leads to false conclusions.

### 6.2. APM: Observing Business-Flow Transactions

An APM agent typically provides:

- Transaction/endpoint latency.
- Distributed tracing and trace/span context.
- HTTP, RPC, JDBC, or messaging spans.
- Error/exception counts.
- JVM/runtime metrics.
- Service maps and request propagation metadata.

An APM agent can modify bytecode at ingress/egress points to time calls and propagate context. These instrumentation points depend on framework versions: moving from servlet to reactive stacks, or upgrading Netty or JDBC drivers, can leave spans missing even though the agent reports "loaded".

### 6.3. Metrics Do Not Replace Traces and Profilers

| Question | Appropriate Data |
|---|---|
| "Did request error rate increase after upgrading?" | Metrics/SLO dashboards |
| "Which endpoint is slower?" | HTTP metrics, latency histograms, tracing |
| "Is slowdown in the DB or the application?" | Distributed traces + DB metrics |
| "Which method consumes CPU?" | CPU profiler/JFR execution samples |
| "Are too many objects being allocated?" | Allocation profiling/JFR + GC metrics |
| "Which thread is waiting on a lock?" | JFR lock events, thread dumps, lock profiler |
| "Is the APM agent slowing the app down?" | Compare with and without agent under identical workload |

Never use a flame graph to replace APM wholesale, or rely solely on a latency dashboard to conclude which specific method burns CPU.

## 7. Understanding CPU Time, Wall Time, and Allocation Samples

### 7.1. CPU Profiling

CPU profiling records code actively using CPU cycles. It fits scenarios where throughput drops and CPU climbs. When the application spends most of its time waiting on network or locks, however, CPU profiles may look quiet despite high request latency.

### 7.2. Wall-Clock Profiling

Wall-clock profiling samples elapsed real time; depending on the profiler, it can capture waiting, blocked, or sleeping threads. This gives a useful lens into latency, provided you check how the profiler filters thread states or applies sampling policies.

### 7.3. Allocation Profiling

Allocation profiling helps pinpoint object allocation sites and GC pressure. Many profilers **sample allocations** rather than recording every single allocation, so rare or tiny allocations can be missed. When comparing two JDKs, hold sampling settings and workloads constant.

### 7.4. Reading Flame Graphs Correctly

Flame graphs usually visualize a set of stack samples:

~~~text
main
  -> HTTP handler
      -> OrderService
          -> ValidateOrder
          -> DatabaseQuery
~~~

Frame width typically reflects relative sample counts, not automatically the exact elapsed duration of a single call. A wide method frame is not automatically a "bug"; it can represent normal high-frequency work.

Never compare two flame graphs directly when capture duration, sampling rate, workload, or stack-capture methods differ.

## 8. Java Flight Recorder (JFR): A Useful Starting Point After Upgrading

**Java Flight Recorder** is the event-collection engine built into modern HotSpot JDKs, well suited for observing GC, JIT compilation, thread scheduling, execution samples, allocations, I/O, and many other JVM activities.

JFR usually carries low overhead under proper settings and can run continuously in production, yet **not every event or stack-trace depth is free**. A heavy profiling configuration collecting detailed events can consume significantly more CPU, memory, and disk space than `default`.

### 8.1. Starting a Recording with the JVM

~~~bash
java \
  -XX:StartFlightRecording=filename=upgrade-baseline.jfr,duration=5m,settings=profile \
  -jar app.jar
~~~

Unix-style shell example; on Windows write on a single line or use the appropriate line-continuation syntax.

Meaning:

- `filename`: output JFR file.
- `duration=5m`: recording duration.
- `settings=profile`: uses the profiling settings profile, typically capturing richer detail than `default`.

Choose duration according to a representative workload and bound the recorded file size.

### 8.2. Using `jcmd` Against a Running Process

When the JVM permits diagnostics and proper permissions exist:

~~~bash
# List accessible Java processes
jcmd

# Start a 2-minute recording
jcmd 12345 JFR.start name=UpgradeProfile settings=profile duration=2m filename=upgrade.jfr

# Check active recordings
jcmd 12345 JFR.check
~~~

PID `12345` is only an example. Inside containers, target the right PID namespace and the user running the Java process. `jcmd` usually requires the same host and appropriate privileges; a sidecar in a separate container cannot always attach.

If a recording has no fixed `duration` and is still active, data can be dumped:

~~~bash
jcmd 12345 JFR.dump name=UpgradeProfile filename=upgrade-snapshot.jfr
~~~

`JFR.dump` produces a snapshot while keeping the recording running. To stop it completely, use `JFR.stop` with the recording name.

### 8.3. Analyzing Recordings

Commands built into the JDK:

~~~bash
jfr summary upgrade.jfr
jfr print --events jdk.ExecutionSample upgrade.jfr
~~~

`.jfr` files can be opened in **JDK Mission Control (JMC)** or analysis tools compatible with the format/events of the JDK that created the recording.

When upgrading the JDK, upgrade JMC/analyzers accordingly. An older viewer failing to recognize newer events does not necessarily mean the recording or application is broken.

### 8.4. Notable Events

| Goal | JFR Event Group / Info |
|---|---|
| CPU hotspots | `jdk.ExecutionSample` and stack traces |
| Allocation | Allocation samples/events, depending on JDK config |
| GC pauses and heap | Garbage collection events, heap summaries |
| Contention | Monitor enter/park events |
| Thread behavior | Thread start/end, park, execution samples |
| Compilation | JIT compilation/optimization events |
| Class loading | Class loading statistics/events |
| I/O | File/socket read/write events |
| Virtual threads | Virtual-thread-specific events if provided by runtime |

Event names, granularity, and defaults can vary across JDKs. Before relying on an event, inspect `jfr metadata` and `.jfc` profiles on the target runtime.

## 9. Async-Profiler and Native Profilers

Tools such as **async-profiler** can sample CPU, wall-clock time, allocations, or lock contention on HotSpot, typically combining JVMTI, AsyncGetCallTrace/stack walking, and OS mechanisms depending on version and platform.

Do not assume all profiling modes use the same APIs or share identical overhead. Both the tool and the JVM version must appear in the vendor/profiler support matrix.

### 9.1. Common Linux/Container Constraints

A native profiler may require access to:

- Linux perf events or equivalent sampling mechanisms.
- `/proc` for the Java process.
- The namespace hosting the JVM.
- The native library loader.
- The Java process under the same user/permissions.
- Appropriate Linux `perf_event_paranoid` and `seccomp`/capabilities policies.

A profiler working on a dev laptop yet unable to attach in Kubernetes may be blocked by **container security policy** rather than the JDK.

Avoid defaulting to fully privileged containers just so a profiler can sample. Prefer narrower, least-privilege options aligned with environment security policy.

### 9.2. Native Stack Walking and Symbolization

When a profiler also captures native stacks, debug symbols and unwinding capabilities affect flame-graph quality. Changing the JDK image or Linux distro can introduce unnamed frames even while the application functions normally.

Record:

- OS/kernel and architecture.
- JDK vendor/build.
- Profiler version/build.
- Sampling mode, interval, and duration.
- Availability of native symbols/debug information.
- Container security permissions.

### 9.3. When to Prefer JFR vs Native Profilers

Start with JFR when needing a holistic JVM view using built-in JDK tooling. Use specialized profilers when needing CPU/native/wall-clock/allocation details beyond what the active JFR profile captures.

In both cases, compare data across **matching workloads and time windows**; never judge a JDK faster or slower from recordings captured in mismatched environments.

## 10. APM After Upgrading: "Loaded" Does Not Guarantee "Observing"

An APM agent can start cleanly and continue sending heartbeats yet **drop business telemetry** because framework instrumentation is no longer compatible.

Examples when upgrading:

- Spring Boot or Servlet API.
- Netty, Reactor, or HTTP clients.
- JDBC drivers, Hibernate, or database clients.
- Kafka/RabbitMQ clients.
- gRPC and other RPC libraries.
- OpenTelemetry SDK/semconv mappings.
- Virtual thread scheduling in asynchronous code.

Symptoms can include:

- HTTP request counts continue while DB spans vanish.
- Traces have a root span yet downstream spans are unlinked.
- Parent/child context gets lost across executors, virtual threads, or reactive pipelines.
- Exceptions stop attaching to spans.
- Latency distributions shift because agent hook points changed.
- Log correlation fields like `trace_id`/`span_id` disappear.
- The agent increases CPU/heap or the count of transformed classes.

### 10.1. Comparing Three Versions

You can build a matrix:

| Application | JDK | APM Agent | Goal |
|---|---|---|---|
| Old version | Old JDK | Old agent | Baseline |
| Old version | New JDK | Old agent | Check JDK impact, if supported |
| Old version | New JDK | New agent | Check agent compatibility with JDK |
| New version | New JDK | New agent | Verify the complete new stack |

Not every cell needs to be supported; explicitly mark cells unrunnable due to vendor support. Never extrapolate from one row to declare the entire migration safe.

### 10.2. Testing an End-to-End Trace

Business example:

~~~text
HTTP POST /orders
       |
       v
OrderController
       |
       v
OrderService
       |
       +--> JDBC INSERT orders
       |
       +--> Kafka publish OrderCreated
       |
       v
HTTP 201
~~~

Tests should confirm:

1. An HTTP request root span exists.
2. Database spans exist if JDBC is instrumented.
3. Messaging spans exist if that integration is supported.
4. Trace IDs propagate per system standards/configs.
5. Status, errors, latency, and key attributes are accurate.
6. Credentials, tokens, and personal data outside policy are not collected.
7. When the APM agent fails to export telemetry, the application adheres to its designed fail-open/fail-safe behavior.

One clean trace in a dashboard does not prove every endpoint has coverage. Select representative samples across HTTP, DB, messaging, and async contexts.

### 10.3. OpenTelemetry Java Agent

With an OpenTelemetry-based Java agent, startup typically resembles:

~~~bash
java \
  -javaagent:/opt/otel/opentelemetry-javaagent.jar \
  -Dotel.service.name=orders-service \
  -Dotel.exporter.otlp.endpoint=https://otel-collector.example \
  -jar orders-service.jar
~~~

The endpoint above is an illustrative placeholder, not a real collector. Configure authentication/TLS, exporters, sampling, and resource attributes for the target system.

OpenTelemetry Java agent versions, semantic conventions, and instrumentation modules can change; check documentation and release notes for the exact agent release. Never copy an exporter configuration from an arbitrary version and assume it works across every release.

## 11. Virtual Threads, GC, and JIT: Why Numbers Can Differ After Upgrading the JDK

### 11.1. Virtual Threads (Java 21 and Later)

Java virtual threads change how applications model concurrency. Older APM/profiling tools may assume "one request maps to one platform thread", causing distorted metrics or dropped trace context.

Check:

- Does trace context follow tasks/requests across async boundaries?
- Does the profiler display virtual threads and carrier threads clearly?
- Do thread counts on dashboards still mean what they used to?
- Does JFR provide virtual-thread events on the running JDK?
- Are blocked/parked/active thread metrics interpreted accurately?

Do not treat old-JDK thread-count thresholds as absolute limits once an application adopts the virtual-thread model.

### 11.2. Garbage Collectors May Change

Moving to a new JDK can bring GC changes, different tuning flags, or altered GC behavior. Compare:

- Pause-time percentiles.
- Allocation rates and heap occupancy.
- Concurrent GC CPU consumption.
- Humongous allocations or promotion rates where the GC defines those concepts.
- Off-heap / native memory.
- Container CPU throttling.

Do not blame every latency shift on "agent overhead" when the GC/runtime also changed. Keep a new-JDK **agent-free** baseline to separate causes.

### 11.3. JIT and Warmup Skewing Benchmarks

Profilers can alter how HotSpot optimizes code, and new JDKs can change compiler heuristics. A benchmark running only a few seconds after startup measures warmup more than steady state.

Practice:

- Warm up under an identical schedule.
- Hold workloads constant.
- Run multiple trials.
- Record p50/p95/p99 distributions instead of averages alone.
- Monitor CPU, GC, JIT compilation, and allocations.
- Keep resource limits and concurrency identical.

### 11.4. Observability Telemetry Names and Labels Can Change

After upgrading the JDK or exporters, metric names, histogram types, units, or labels can shift. For instance, a dashboard filtering on a specific GC name may go blank if the collector or new instrumentation renamed labels even while GC operates normally.

Therefore, check the **data pipeline all the way to dashboards and alerts**, not merely whether the agent file loaded.

## 12. Diagnostic Workflow Using JDK Tools

### 12.1. Starting from JVM Identity

~~~bash
java -version
jcmd
~~~

When process access is permitted:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
~~~

These commands verify runtime vendor/build, startup flags, and command lines. Never paste full command lines into public tickets if JVM arguments contain secrets.

### 12.2. Inspecting Native Libraries and Class Loaders

Available diagnostic commands depend on JVM/version:

~~~bash
jcmd 12345 help
jcmd 12345 VM.dynlibs
jcmd 12345 VM.classloader_stats
~~~

Some commands may be unavailable or format outputs differently on a given runtime. `jcmd <pid> help` lists available commands before use.

`VM.dynlibs` helps inspect loaded shared libraries when triaging native agent crashes. `VM.classloader_stats` helps analyze class-loader counts/metadata when suspecting excessive class generation by instrumentation.

### 12.3. Thread Dumps and Heap

~~~bash
jcmd 12345 Thread.print
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
~~~

Some commands carry significant impact; `GC.heap_dump` can also write large files and/or pause the application. Execute only per approved runbooks with adequate disk capacity. In production, JFR is often a less intrusive choice for investigating many phenomena.

### 12.4. Native Memory Tracking

On HotSpot with appropriate NMT configuration, `jcmd` can inspect native memory:

~~~bash
# Example startup configuration:
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Then:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT helps when suspecting native memory growth after enabling an agent, though it adds overhead and cannot automatically track every native allocation managed by external libraries. Understand measurement limits and baselines. Never assume detailed NMT can be enabled dynamically after JVM startup if it was not configured at launch.

## 13. Pre-JDK-Upgrade Compatibility Matrix

A minimal matrix may include:

| Axis | Values to Verify |
|---|---|
| JDK | 17 / 21 / target JDK with vendor/build |
| Operating system | Linux/Windows/macOS per production |
| Architecture | x86_64/aarch64 if both are deployed |
| Container | Base image, libc, kernel, security context |
| Application | Pre- and post-migration versions |
| Agent | APM, native profiler, coverage agent versions |
| Framework | Spring, Netty, Hibernate, HTTP/JDBC clients |
| Runtime mode | Classpath/module path, virtual/platform threads |
| Startup mode | `-javaagent`, `-agentpath`, or dynamic attach |
| Workload | Startup, steady state, spikes, graceful shutdown |
| Telemetry | Traces, metrics, logs, profiles, JFR |
| Reliability | Crashes, error rates, leaks, stalled threads |
| Performance | CPU, RSS/native memory, GC, p95/p99 latency |

Running the full Cartesian product is unnecessary if costly; prioritize combinations that are genuinely supported and high-risk. Still, combinations included in the production support matrix require clear verification evidence.

### 13.1. Checking Vendor Compatibility

Before upgrading the JDK:

1. Verify the agent/profiler supports the target **JDK feature version**.
2. Check supported JDK patch updates and JVM vendors.
3. Check OS/architecture for native binaries.
4. Read agent release notes on bytecode libraries, virtual threads, and module access.
5. Check dynamic attach policies on the target JDK.
6. Test APM instrumentation coverage across framework versions.
7. Document known issues/limitations published by the vendor.

Do not rely on "Java compatible" claims without knowing which Java versions and instrumentation capabilities are actually supported.

## 14. Measuring Agent and Profiler Overhead

A JDK upgrade can alter the overhead of the exact same agent due to differing JIT, class loading, or GC behavior. Measure each layer's impact independently.

### 14.1. Four-Experiment Matrix

~~~text
A. Old JDK + no agent
B. Old JDK + agent
C. New JDK + no agent
D. New JDK + agent
~~~

From this you can distinguish:

- **C - A:** runtime/JDK difference without agents.
- **B - A:** agent overhead on the old JDK.
- **D - C:** agent overhead on the new JDK.
- **(D - C) vs (B - A):** shift in agent impact after migration.

This is an analytical framework, not simple linear arithmetic valid for every metric. For example, p99 latency behaves nonlinearly under concurrency, GC, and queueing.

### 14.2. Metrics to Record

| Metric | Role |
|---|---|
| Throughput | Requests/transactions per second |
| p50/p95/p99 latency | User experience and SLO impact |
| Process/container CPU | Execution and sampling overhead |
| RSS/native memory | Native agents, buffers, symbols, JFR |
| Java heap/GC pauses | Allocations caused by instrumentation |
| Errors/timeouts | Stability while instrumentation is active |
| Class load/transformation counts | Level of transformer activity |
| Trace export queue/dropped spans | APM quality under heavy load |
| JFR file size/sampling overhead | Diagnostic cost |
| Process crashes/core dumps | Native agent compatibility |

### 14.3. Do Not Confuse Sampling Overhead with "Application Cost"

When a profiler runs at aggressive sampling rates, CPU increases can come from the profiler; when an APM agent sets trace sampling to 100%, latency can differ markedly from production 1–10% sampling configurations. Keep sampling/exporter settings aligned with real usage and record exact settings when interpreting results.

Do not run multiple heavy profilers simultaneously in a benchmark and then assume each profiler individually consumes negligible resources.

## 15. Post-JDK-Upgrade Testing and Rollout Runbook

### Phase A – Inventory

- List `-javaagent`, `-agentlib`, and `-agentpath` flags on JVM startup.
- Locate agents injected via `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, container entrypoints, or platform operators.
- Record vendors/versions of APM, profiler, coverage, debugger, and security agents.
- Identify whether agents attach dynamically, capture JFR, or rely solely on JMX.
- Check JDK, OS, architecture, and framework support matrices.

### Phase B – Agent-Free Compatibility Verification

Run the application artifact on the target JDK **without third-party agents** in a test environment. Record baseline startup, throughput, latency, CPU, GC, and JFR if needed.

This clarifies whether the application/JDK itself has issues before adding an instrumentation layer.

### Phase C – Enabling Tools One by One

In a structured sequence:

1. Enable the APM Java agent and check startup and traces.
2. Enable metrics exporters/JMX and check dashboard labels.
3. Enable native profilers or JFR per runbook.
4. Enable coverage/security agents if required in production.
5. Run the exact combination of agents planned for production.

At each step, confirm the JVM can restart and gracefully shut down without crashes or loss of essential telemetry.

### Phase D – Comparing Under Identical Workloads

Use identical artifacts, datasets, concurrency, container resource limits, and warmup durations. Measure overhead across p95/p99, error rates, CPU, allocations, native RSS, and exporter drops.

If regressions occur, isolate by agent/version/config and logs. Never upgrade JDK, agents, framework, and dashboards together without a root-cause isolation strategy.

### Phase E – Canary and Alerting

Route a small traffic share while ensuring the **canary runs the same monitoring tools** as production. Verify:

- No startup/attach errors.
- No increase in native crashes.
- Representative APM spans appear.
- Metrics preserve required labels and units.
- Sampling/exporters do not overload.
- JFR can be captured when needed.
- Alerts have not gone "silent" due to renamed metrics.

### Phase F – Rollback Decisions

If a new agent causes errors, roll back **only the agent** if configuration allows and the issue has been isolated. If the new JVM fails even without agents, evaluate rolling back the JDK/application. Never downgrade the JDK while forgetting binary or data-state compatibility with older versions.

Rollback paths must be tested separately: can the older agent run on the current JDK, and can the older application version handle already written data?

## 16. Quick Diagnostic Table

| Symptom | Plausible Hypothesis | Investigation Direction |
|---|---|---|
| JVM fails to start when adding `-javaagent` | Missing JAR, broken manifest, `premain` threw exception | Startup logs, JAR, agent version |
| `Unsupported class file major version` | Outdated ASM/Byte Buddy/transformer | Agent version, class-file version |
| `VerifyError` after enabling APM | Invalid bytecode transformation or conflict | Compare without agent, test agents singly |
| JVM crash with `hs_err_pid` | Native agent/JVM/library bug | Problematic frame, native stack, vendor |
| Profiler fails to attach | Dynamic attach policy or OS permissions | JDK policy, user, PID namespace |
| `InaccessibleObjectException` | Deep reflection into closed module | Agent version, module/opens |
| APM sends heartbeats but zero HTTP spans | Instrumentation lacks support for new framework | Agent logs, framework compatibility |
| Traces break across async/virtual threads | Context propagation/instrumentation mismatch | Trace tests, async executors/virtual threads |
| High CPU only with profiler active | Overly dense sampling or conflict | Profiler mode/interval, baseline comparison |
| RSS grows while Java heap stays stable | Native agent/buffers/threads | NMT, native libraries, JFR |
| JFR tool cannot parse new events | Outdated analyzer or schema changes | JDK/JMC versions, `jfr metadata` |
| Metrics dashboard goes blank | Metric/label renamed or exporter broken | Raw scrape/exporter logs, dashboards |
| Integration tests green, production fails attach | Different container security context | User, namespace, `seccomp`, perf permissions |
| Startup fails only with two agents | Transformer/capability/ordering conflict | Enable one agent at a time, adjust versions |
| Tests unexpectedly slower after JDK upgrade | GC/JIT/framework/agent all shifted | A/B/C/D performance matrix |

## 17. Security and Sensitive Data in Observability

Agents and profilers often hold broad privileges inside the application process. Native agents can inspect memory, class state, or method arguments; APM tools can capture HTTP headers, query parameters, and SQL statements. Consequently, they belong inside the trusted supply chain.

Recommendations:

- Fetch agent binaries from approved vendors/repositories and verify checksums/provenance.
- Pin versions; never pull "latest" directly into production without testing.
- Restrict filesystem read/write and network egress permissions of agents.
- Do not expose exporter tokens in `-D...` flags visible in process listings when safer secret mechanisms exist.
- Configure redaction for PII, credentials, and sensitive payloads.
- Encrypt telemetry in transit and control retention.
- Restrict who can run `jcmd`/attach or read heap/JFR dumps.
- Collect diagnostics through approved workflows and purge temporary files after investigation.

**A JFR file or heap dump is never a benign artifact.** It can contain method names, stack traces, internal paths, and sensitive data fragments depending on recorded events and metadata. Manage them under organizational security policy.

## 18. Post-JDK-Upgrade Checklist

- [ ] Inventoried all Java/native agents loaded at startup or dynamically attached.
- [ ] Confirmed agent/profiler versions support the target JDK vendor/build, OS, and CPU architecture.
- [ ] Verified class-file versions and Byte Buddy/ASM inside instrumentation tools.
- [ ] Checked JVMTI capabilities and startup/attach modes.
- [ ] Evaluated JEP 451 and dynamic agent loading policies on the target JDK.
- [ ] Audited `-javaagent`, `-agentpath`, `-agentlib`, and injected JVM options.
- [ ] Identified which module access / `--add-opens` flags remain required.
- [ ] Verified agent-free startup and runtime for a clean baseline.
- [ ] Tested each agent individually and then the real production agent combination.
- [ ] Verified APM spans across HTTP, JDBC, messaging, and async contexts.
- [ ] Confirmed metrics, labels, trace propagation, and alert rules.
- [ ] Captured JFR or profiler samples under representative workloads.
- [ ] Checked CPU, p95/p99 latency, allocations, GC, and RSS/native memory.
- [ ] Tested container permissions/PID namespaces/perf access for profilers.
- [ ] Recorded agent versions, JDK build, OS/kernel, and sampling settings.
- [ ] Tested virtual-thread scenarios or newly upgraded framework instrumentation.
- [ ] Prepared isolated agent disable/rollback procedures alongside JDK rollback plans.
- [ ] Complied with data-protection policies for JFR/heap/profile/trace exports.

## 19. Official References

- [JVM Tool Interface (JDK 25 specification)](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): agent startup, capabilities, events, bytecode instrumentation, native agent lifecycle.
- [`java.lang.instrument` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agents, `premain`/`agentmain`, and dynamic loading policy.
- [JEP 451](https://openjdk.org/jeps/451): warnings on dynamic agent loading and controls over dynamic attach.
- [`jcmd` tool reference (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): JFR, diagnostic commands, and JVM introspection.
- [`jfr` tool reference (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): inspecting and manipulating recording files.
- [Oracle JDK 25 Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, thread dumps, heap, and diagnostic tools.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): JFR analysis tool.
- [OpenTelemetry Java instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): Java agent and observability configuration.
- [async-profiler project](https://github.com/async-profiler/async-profiler): native sampling profiler for the JVM; check specific version compatibility.

When upgrading from older JDKs to newer releases, consult documentation for the **exact target release** and **exact agent/profiler version**. Observability tools often release independently of the JDK, so support matrices can shift faster than the application's own upgrade cycle.

## 20. Conclusion

JVMTI and agent tooling provide deep visibility into the JVM yet introduce an additional compatibility risk layer during Java upgrades. **Native JVMTI agents**, **Java bytecode instrumentation agents**, **JFR/profilers**, and **APM** differ in how they load, their privileges, performance overhead, and the telemetry they collect.

A successful Java Advance Compatibility Migration must prove that **the application operates correctly without agents**, that **agents/profilers/APM remain compatible**, that **observability telemetry stays complete and accurate**, and that **overhead remains acceptable** on the target JDK. Control dynamic attach, verify module and native compatibility, roll out tooling incrementally, test canaries, and always maintain a tested agent-disable/rollback plan. Monitoring tools deliver value only when they help diagnose the system without becoming the source of a new outage.
