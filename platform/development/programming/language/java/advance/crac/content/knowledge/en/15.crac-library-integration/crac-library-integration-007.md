# Java Agents, Profilers, and Resources Opened by Monitoring Tools

Java agents, profilers, and monitoring tools help observe an application, measure performance, collect traces, or add instrumentation without modifying individual business classes. However, these tools may also create additional threads, sockets, file descriptors, executors, native buffers, JVM hooks, and connections to telemetry systems. When an application uses CRaC, those resources reside in the same process or are attached to the process to be checkpointed, so they must be treated as part of the application lifecycle.

CRaC does not automatically know how to stop a profiler, flush telemetry, close exporters, or reinitialize a native agent. Instrumentation already applied to bytecode may remain part of the JVM state, while active resources such as sockets, sampling threads, or file descriptors may need to be closed before checkpoint and recreated after restore. Compatibility depends on the specific agent, profiler, JDK version, and checkpoint engine.

To use monitoring tools safely with CRaC, first identify how the tool is loaded, which components run inside the JVM, which resources are owned by an external process, and whether the vendor supports checkpoint/restore. Then design a stop, release, reinitialization, and testing procedure tailored to each component.

## 1. Distinguishing Java Agents, Profilers, and Monitoring Agents

These terms can overlap. An APM agent may both instrument bytecode and collect traces, metrics, and profiles. A profiler can be a Java agent, a native JVMTI agent, or an external process sampling from the operating system.

| Tool type | Primary goal | Components it may create |
|---|---|---|
| Java instrumentation agent | Modify or add bytecode to observe application behavior. | Class transformers, classloaders, hooks, object caches, threads, and runtime configuration. |
| APM/monitoring agent | Collect metrics, traces, logs, and send them to a backend. | Exporters, queues, schedulers, HTTP/gRPC clients, sockets, credentials, and background threads. |
| Java profiler | Measure CPU, allocation, lock contention, call stacks, or latency. | Sampling threads, timers, recordings, event buffers, and profile data. |
| Native/JVMTI agent | Observe or control the JVM at a low level. | Native threads, callbacks, JVMTI environments, native memory, signal handlers, and file descriptors. |
| External profiler/controller | Control or sample a JVM from another process. | Attach connections, perf events, control sockets, and state tied to PID/target. |

The distinction to make is that instrumentation does not equate to all resources of an agent. A registered transformer may still be needed after restore to preserve instrumented behavior; however, threads sending telemetry or sockets to a backend may have to be recreated.

## 2. Ways to Load an Agent into the JVM

Java provides several mechanisms for loading agents. The loading method affects initialization timing and operation, but does not by itself determine whether an agent is CRaC-compatible.

### 2.1. Java Instrumentation Agent via `-javaagent`

A Java agent is typically packaged in a JAR and declares `Premain-Class` in its manifest. The JVM invokes the `premain(...)` method before calling the application's `main(...)`. The agent receives an `Instrumentation` object to register a `ClassFileTransformer`, query loaded classes, or request retransformation/redefinition if permitted.

Example launch command:

```bash
java -javaagent:/opt/agents/monitoring-agent.jar=service=orders -jar application.jar
```

The agent's manifest may declare:

```text
Premain-Class: com.example.agent.MonitoringAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
```

Example entry point:

```java
public final class MonitoringAgent {

    public static void premain(
            String agentArgs,
            java.lang.instrument.Instrumentation instrumentation) {
        AgentRuntime.install(agentArgs, instrumentation);
    }
}
```

`premain(...)` runs during JVM startup. If the agent initializes remote connections, opens files, or creates threads right here, those resources exist before the application completes startup and may affect checkpointing. The agent should separate transformer registration from starting exporters or background workers if the latter components require separate lifecycle management.

### 2.2. Dynamic Attach via `agentmain`

Some agents are loaded after the JVM is already running through the Attach API. The JVM invokes the agent's `agentmain(...)` method after a successful attach. This approach is commonly used by profilers or diagnostic tools to start observing a running process.

```java
public final class MonitoringAgent {

    public static void agentmain(
            String agentArgs,
            java.lang.instrument.Instrumentation instrumentation) {
        AgentRuntime.install(agentArgs, instrumentation);
    }
}
```

With dynamic attach, note:

- The agent is installed after startup, so its initial state differs from an agent loaded with `-javaagent`.
- Attach may be restricted by JDK configuration, OS permissions, containers, or security policies.
- Re-attaching after restore may create duplicate transformers, threads, or exporters if installation logic is not idempotent.
- An external profiler/controller process has its own lifecycle and may need to reconnect or re-attach after the JVM restores.

Do not assume that an agent attached before checkpoint will be properly managed by an external tool after restore. Verify how the tool identifies targets, PIDs, control sockets, and session state.

### 2.3. Native Agent via JVMTI

Low-level profilers, debuggers, and monitoring tools may use the JVM Tool Interface (JVMTI). Native agents are typically loaded using `-agentlib` or `-agentpath`:

```bash
java -agentlib:sampleprofiler=interval=10 -jar application.jar
```

Or specify the native library path:

```bash
java -agentpath:/opt/profiler/lib/libsampleprofiler.so=interval=10 -jar application.jar
```

JVMTI allows an agent to register event callbacks, request capabilities, and access runtime information. The agent runs in the same process as the JVM and may use native memory, native threads, file descriptors, or signals. These components must be carefully examined during checkpointing.

A JVM can have multiple JVMTI agents simultaneously. Each agent has its own JVMTI environment, yet the agents still observe and act on the same VM/native process; one agent can affect another. Therefore, the fact that one profiler is CRaC-compatible does not prove that the remaining agents are compatible as well.

## 3. Resources That Agents and Profilers May Open

Do not inspect only the agent's heap objects. Inventory every resource the tool uses.

| Resource | Examples | Checkpoint/restore issues |
|---|---|---|
| Java threads | Exporter threads, samplers, schedulers, polling workers. | May be processing work or waiting on I/O; need to stop at a safe point or be reinitialized. |
| Native threads | JVMTI workers, sampling threads, native event loops. | Native lifecycle and state are agent-dependent; vendor guidance is required. |
| Sockets | HTTP/gRPC exporters, agent control channels, remote profilers. | Peer may close connections during checkpoint; typically must be recreated. |
| File descriptors | Log files, profile outputs, perf events, pipes. | Files or descriptors may no longer be valid in the restore environment. |
| Buffers and native memory | Direct buffers, mmap, native allocations. | Ownership and release/recreation mechanisms must be known. |
| JVM hooks | Transformers, JVMTI event callbacks, native hooks. | May still need to be kept for instrumentation to continue; do not remove arbitrarily. |
| Telemetry queues | Span queues, metric batches, profile samples. | Need to flush or intentionally discard before checkpoint to avoid data loss/duplication. |
| Credentials/configuration | Tokens, endpoints, certificates, API keys. | May expire or change while the process is stopped; reload if appropriate. |

CRaC checkpoints process state. It does not act as a lifecycle manager for monitoring backends or external profiler processes. Open sockets and files are classic examples of resources that need to be released or handled according to compatibility policies before checkpoint.

## 4. Distinguishing Instrumentation State from Monitoring Activity

This is a key point when deciding which components to keep versus reinitialize.

### 4.1. Applied Instrumentation

A Java agent can register transformers to modify bytecode when classes are loaded. Once a class is instrumented, the loaded bytecode and transformer state belong to the running JVM.

Do not remove transformers or retransform all classes merely because a checkpoint is about to occur. Doing so can:

- Lose instrumentation needed after restore.
- Alter class behavior while other threads are still running.
- Create discrepancies between already-loaded classes and classes loaded after restore.
- Incur heavy initialization overhead or corrupt measurement data.

Determine whether the agent needs to retain its transformers and instrumentation state. Only remove or reinstall them when agent documentation requires it. If retransformation is needed, verify capabilities, idempotency, and safe timing.

### 4.2. Exporters and Background Workers

An exporter sending telemetry data typically has a lifecycle independent of transformers. It may hold HTTP clients, gRPC channels, batch queues, and scheduled flushes. Before checkpoint, the agent can:

1. Stop accepting new spans/metrics/profiles or switch to a bounded buffer.
2. Wait for in-flight batches to finish within an allowed deadline.
3. Flush remaining data according to policy.
4. Close channels/sockets and stop scheduler/exporter threads.

After restore, the agent creates new channels, loads current credentials/configuration, restarts schedulers, and resumes exporting. If the backend is not yet ready, perform bounded retries and avoid blocking the entire restore indefinitely.

### 4.3. Sampling and Profiler Recordings

Profilers may use timers, sampling threads, JFR recordings, JVMTI events, or native perf events. Distinguish:

- Recordings/sessions that may be kept in JVM state.
- Sampler threads or native descriptors that may need to be stopped and reinitialized.
- External control tools that may need to reconnect or re-attach.
- Profile data during checkpoint/restore that may not represent normal workload.

There is no universal rule that all profilers automatically resume accurately after restore. Follow the CRaC compatibility documentation of the specific profiler. Without confirmation, the safe choice is to stop recordings, release closeable resources, and start a new recording after restore.

## 5. Integrating an Agent with the CRaC Resource API

If the agent is controlled by the development team and its lifecycle can be managed, the agent can register an `org.crac.Resource` to coordinate with the runtime. A Resource should represent a group of resources sharing the same owner, such as a telemetry exporter or profiler runtime.

Simple structural example:

```java
package com.example.agent;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.lang.instrument.Instrumentation;

public final class MonitoringAgent {

    private static AgentRuntime runtime;

    public static void premain(
            String args,
            Instrumentation instrumentation) {
        install(args, instrumentation);
    }

    public static void agentmain(
            String args,
            Instrumentation instrumentation) {
        install(args, instrumentation);
    }

    private static synchronized void install(
            String args,
            Instrumentation instrumentation) {
        if (runtime != null) {
            return;
        }

        AgentRuntime candidate = AgentRuntime.start(args, instrumentation);
        Core.getGlobalContext().register(candidate);
        runtime = candidate;
    }
}

final class AgentRuntime implements Resource {

    private volatile TelemetryExporter exporter;
    private volatile ProfilerSampler sampler;

    static AgentRuntime start(String args, Instrumentation instrumentation) {
        AgentRuntime runtime = new AgentRuntime();
        runtime.installInstrumentation(instrumentation);
        runtime.startExporter(args);
        runtime.startSampler(args);
        return runtime;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        sampler.pauseAndAwaitSafePoint();
        exporter.flushWithTimeout();
        exporter.close();
        sampler.releaseNativeResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        exporter = TelemetryExporter.createAndStart();
        sampler = ProfilerSampler.createAndStart();
    }

    private void installInstrumentation(Instrumentation instrumentation) {
        // Register the transformer once; keep instrumentation if needed after restore.
    }

    private void startExporter(String args) { /* ... */ }
    private void startSampler(String args) { /* ... */ }
}
```

`AgentRuntime`, `TelemetryExporter`, and `ProfilerSampler` are illustrative abstractions, not classes built into the JDK or CRaC. `install(...)` is synchronized and only records the runtime after successful creation and registration; a real implementation still needs to clean up partially initialized components if `AgentRuntime.start(...)` fails. The example also assumes the agent packages and can use the `org.crac` compatibility API. For commercial agents, use the vendor's official integration mechanism if available; do not add a second Resource that also closes resources the agent already manages itself.

### 5.1. Why Should the Resource Be Registered Exactly Once?

An agent can be loaded via `premain`, dynamic attach, or framework mechanisms. If both entry points invoke installation, or a tool re-attaches after restore, multiple runtimes may be created and multiple Resources registered for the same exporter.

Design installation to be idempotent:

- Create only one runtime owner per JVM/classloader managed by the agent.
- Do not register duplicate Resources when the agent is attached multiple times.
- Clearly handle cases where the agent uses a separate classloader or is loaded by multiple modules.
- Do not assume a static flag in another classloader can prevent duplicate installation JVM-wide.

If an agent supports multiple classloaders or multiple instances, a clearly scoped registry is required instead of relying only on a simple static boolean.

### 5.2. Handling Callback Errors

If `beforeCheckpoint(...)` cannot stop the sampler or flush the exporter within the deadline, the agent needs to report an error per defined policy. Do not close resources while the sampler is still using them, or ignore errors and let the checkpoint proceed in an unclear state.

If `afterRestore(...)` fails to recreate the exporter or native sampler, the agent should remain in a non-ready state, perform bounded retries, or report an error so the application can apply its degraded/fail-stop policy. Do not pretend telemetry is working just because the Resource callback was invoked.

## 6. Specific Considerations for Profilers and Native Agents

Native profilers may depend on OS resources that the Java Resource API does not automatically understand. Examples include perf event descriptors, signal handlers, native sampling threads, mmap buffers, or file outputs. The agent needs corresponding stop/detach and start/attach APIs.

A general workflow:

**Before checkpoint**

1. Stop creating new samples.
2. Wait for in-flight callbacks or native sampling loops to reach a safe point.
3. Flush profile buffers if data must be retained.
4. Close perf event/file descriptors or release native handles per the profiler's API.
5. Stop agent-owned native threads.
6. Retain the necessary configuration so a new recording can be created after restore.

**After restore**

1. Verify the profiler runtime and native library remain compatible with the environment.
2. Recreate native handles, buffers, and sampling threads.
3. Reload configuration, permissions, and output paths.
4. Start a new recording or resume according to vendor-supported capabilities.
5. Verify new sample data is actually being recorded.

Do not manually serialize native pointers, `JNIEnv*`, file descriptors, or internal handles for manual restoration. Those values are tied to threads or OS state and must be created/released via official APIs. For native agents, keeping a pointer in the heap does not make the resource that the pointer points to valid after restore.

## 7. Out-of-Process Profiler Tools

Some profilers run as separate processes and attach to the target JVM. An external profiler process is not part of the application's checkpoint image. When the target is restored:

- Old attach sessions may no longer be valid.
- The PID or target identification information may differ depending on the checkpoint engine and restore method.
- Control sockets or perf events may have been closed.
- The profiler may need to rediscover the JVM, detach old sessions, and re-attach.
- Re-attaching may require special permissions or configuration inside containers.

Distinguish resources belonging to the target JVM from resources belonging to the profiler/controller process. Do not try to close external profiler file descriptors from Java callbacks inside the target. Reconnection needs to be handled by the controller or orchestration system per tool documentation.

If the goal is to measure restore time, determine whether the profiler alters the startup path or slows down restore. Include a baseline run without the profiler to know the actual overhead.

## 8. Monitoring Agents and Telemetry Exporters

Monitoring agents typically have multiple continuously running components:

- Span processors and batch queues.
- Metric readers and periodic exporters.
- Log appenders or log shippers.
- HTTP/gRPC clients to the telemetry backend.
- Background threads sending batches and retries.
- Credential providers, TLS contexts, and endpoint configuration.

Before checkpoint, the agent should stop creating new batches or put them into a controlled state, flush queues within a timeout, close channels, and pause schedulers. After restore, the agent creates new channels, reloads credentials if needed, and starts periodic exporting.

### 8.1. Avoiding Lost or Duplicate Telemetry

If a checkpoint is taken after a batch has been sent but before the agent receives an acknowledgment, after restore the agent may resend that batch. Conversely, if the queue is cleared before the backend acknowledges, data may be lost.

Telemetry typically accepts at-least-once or best-effort delivery guarantees depending on configuration. Understand the semantics of your exporter and backend:

- Does flush guarantee waiting for backend acknowledgment or only pushing data into the socket?
- Is the queue persistent or only in the heap?
- Does the exporter have batch IDs or deduplication?
- When a flush times out, is data kept, dropped, or retried?
- What do span timestamps and durations mean when the process was stopped for a long period?

Exactly-once guarantees cannot be provided by checkpoint/restore alone. If duplicate telemetry is an issue, deduplication or batch identification is needed at the exporter/backend layer.

### 8.2. Credentials and Configuration After Restore

Telemetry tokens may expire during checkpoint. Endpoints, proxies, certificates, or service identity may also change. Agents should fetch credentials from a provider according to the appropriate lifecycle rather than assuming token objects kept in the heap are always valid.

Do not log tokens, API keys, authentication headers, or sensitive payloads to diagnose checkpoints. A checkpoint image may contain telemetry objects in the heap, so read permissions and image retention must be protected.

## 9. Java Flight Recorder and Built-in JDK Profilers

Java Flight Recorder (JFR) is an event recording mechanism built into the JDK, distinct from a standalone Java agent. However, applications and profiling tools can control JFR via API or command line, and recordings remain part of the observability state that must be checked around checkpoints.

Before using JFR with CRaC, decide:

- Is an active recording preserved and resumed as expected on the CRaC JDK being used?
- How are event buffers and data not yet written to file handled?
- Does the recording include the checkpoint/restore interval, making durations or timestamps hard to interpret?
- Should the recording be dumped/stopped before checkpoint and a new recording started after restore?
- Is the output file safely closed and reopened after restore?

Do not assert that JFR recordings always continue or always must be stopped. Behavior depends on the JDK distribution, version, how the recording is configured, and specific CRaC support. Test on the exact runtime. If the goal is to compare post-restore performance, clearly mark pre-restore and post-restore recordings so process downtime is not merged into the same measurement window.

## 10. Lifecycle Ordering and Coordinating Multiple Agents

A JVM can have multiple agents running simultaneously. One agent may own an exporter, another may own a profiler sampler, while a framework manages thread pools itself. If each side independently closes and recreates resources without knowing each other's ownership, the following can happen:

- Closing the same socket or executor multiple times.
- Agent A stopping a thread that agent B is still waiting on.
- Restarting an exporter before the credential provider is ready.
- Re-attaching a profiler while the old session has not detached.
- Multiple periodic tasks sending the same type of telemetry.

Map out ownership and dependencies. If agents share resources, only one component should be responsible for closing/opening. With multiple Resources, register them in dependency order as supported by CRaC documentation: `beforeCheckpoint(...)` runs in registration order and `afterRestore(...)` runs in reverse order. If relationships are complex, use a coordinator rather than relying on implicit ordering between unrelated agents.

## 11. Deployment Configuration When Using Agents with CRaC

Before taking a checkpoint, record the exact agent configuration:

- Java command line and order of `-javaagent`, `-agentlib`, `-agentpath`.
- JDK version and related JVM options.
- Versions of agents/profilers/native libraries.
- Environment variables and configuration paths.
- Endpoints, proxies, TLS trust stores, and credential providers.
- Permissions for perf events, attach, files, and sockets.
- Resources registered by agents with CRaC.

After restore, ensure the environment has compatible native libraries and configuration. If a checkpoint is restored on another machine, native libraries, CPU architecture, OS, and file paths can affect operability. Do not treat a checkpoint image as an artifact independent of runtime/agent versions without verified compatibility.

If an agent does not support CRaC, it may be necessary to disable the agent during checkpoint creation or use an agent mode recommended by the vendor. However, disabling an agent can alter bytecode instrumentation, class state, or warmed-up workload; measure and test separately rather than arbitrarily adding/removing `-javaagent`.

## 12. Testing Agents and Profilers Across Checkpoint/Restore

Test each tool type individually before combining multiple agents.

### 12.1. Baseline Testing

Run the application without agents to measure cold start, checkpoint duration, restore duration, time-to-readiness, memory footprint, and request behavior. This serves as the comparison benchmark when enabling agents.

### 12.2. Testing Individual Agents

For each agent:

1. Identify the loading mechanism: `-javaagent`, `-agentlib`, `-agentpath`, or dynamic attach.
2. Identify threads, sockets, file descriptors, native handles, and queues owned by the agent.
3. Check vendor documentation for CRaC/checkpoint support.
4. If the agent manages a Resource itself, confirm callbacks are registered and not duplicated.
5. Generate a representative workload and start the profiler/monitoring.
6. Stop/flush resources per policy before checkpoint.
7. Create a checkpoint and restore on the exact runtime.
8. Confirm instrumentation still works, the exporter reconnects, and the profiler produces new samples.
9. Compare overhead, memory, and timing against the baseline.

### 12.3. Testing Multiple Agents Simultaneously

After each agent works independently, enable them in the production configuration. Check for conflicts in transformers, native libraries, signal handlers, threads, exporters, and attach permissions. JVMTI allows multiple agents, yet agents still affect the same VM and native process, so combinatorial compatibility cannot be inferred from individual runs.

### 12.4. Scenario Matrix

| Scenario | What to verify |
|---|---|
| Java agent loaded via `-javaagent` | `premain` completes; necessary transformers remain effective after restore. |
| Agent loaded via dynamic attach | Agent is not doubly installed on re-attach; external sessions can reconnect. |
| Native JVMTI agent | Native threads, event callbacks, and descriptors are handled per vendor guidance. |
| Exporter sending batches | Bounded flush; queues are not lost or duplicated outside policy. |
| Profiler actively sampling | Sampler reaches a safe point, native resources are released, and a new recording works after restore. |
| Telemetry backend unavailable | Agent performs bounded retries and does not block the application indefinitely. |
| Token expires during checkpoint | Agent obtains new credentials or exposes an observable export error state. |
| Two agents sharing native hooks | No conflicts in signals, callbacks, or class transformers. |
| Agent callback fails | Checkpoint/restore errors are propagated; do not assume the tool still works. |

## 13. Diagnosing Checkpoint or Restore Failures Involving Agents

When a checkpoint fails, classify the error by owner:

- A Java Resource registered by an agent reports an error in `beforeCheckpoint(...)`.
- Files or sockets opened by an agent remain active.
- A native agent holds descriptors, threads, or handles unsupported by the checkpoint engine.
- An external profiler is attached or holding a control session.
- An agent exporter hangs during flush or waiting for the backend.
- After restore, an agent fails to restart due to missing libraries, permissions, or credentials.

Some CRaC-enabled JDKs have diagnostic options to list resources or dump the heap when a checkpoint fails. JVM flags and output depend on the distribution; consult documentation for your exact JDK. Do not enable vendor-specific flags across all environments assuming they exist on every CRaC JDK.

Gather information:

- JDK vendor, version, build, and OS/kernel.
- Agent/profiler version, loading method, and full command line.
- Agent logs before checkpoint and after restore.
- Thread dumps and file descriptor lists when possible.
- Callback, native library, or checkpoint engine errors.
- State of exporters, profiler sessions, and backends.

Do not include secrets or sensitive telemetry payloads in error reports. When reproduction is needed, strip the configuration down to a single agent to isolate, then re-enable components one by one.

## 14. Common Design Mistakes

**Assuming a Java agent only adds bytecode and has no resources to handle.** An agent can create exporters, threads, sockets, native memory, and file descriptors. Inventory runtime components, not just transformers.

**Removing all transformers before checkpoint.** This can lose instrumentation needed after restore and leave class state inconsistent. Only alter transformers when required by the vendor.

**Keeping the exporter as-is because the object still exists on the heap.** Sockets or TLS sessions may have been closed by the peer. Recreate channels after restore following the appropriate lifecycle.

**Flushing telemetry indefinitely in a callback.** The backend may be unavailable and hang the checkpoint. Set clear deadlines, queue retention/drop policies, and error states.

**Re-attaching a profiler without checking old sessions.** This can create duplicate sampling threads, transformers, or recordings. Detach/reconnect must be idempotent.

**Assuming a native agent is automatically compatible because another Java agent ran successfully.** JVMTI agents use native state and may depend on specific OS resources. Test each agent and combination.

**Assuming an out-of-process profiler is part of the target's checkpoint.** External controllers are not in the checkpoint image. Sessions must be managed in the controller/orchestrator.

**Treating the checkpoint exit code as proof the agent works.** Actual samples, traces, metrics, and connections must be verified after restore.

## 15. Checklist for Integrating Agents, Profilers, and Monitoring with CRaC

- [ ] List every Java agent, native agent, profiler, and monitoring tool.
- [ ] Document loading methods: `-javaagent`, `-agentlib`, `-agentpath`, or dynamic attach.
- [ ] Record JDK, agent, profiler, and native library versions.
- [ ] Identify which transformers/instrumentation must be kept after restore.
- [ ] Inventory threads, executors, sockets, file descriptors, native buffers, and queues owned by agents.
- [ ] Check official CRaC support documentation from each vendor.
- [ ] Register a Resource if the agent is self-managed and the API is compatible.
- [ ] Stop samplers/workers at a safe point before checkpoint.
- [ ] Flush exporters within a deadline and handle queues according to clear semantics.
- [ ] Close sockets, files, and native handles that must be recreated.
- [ ] After restore, recreate exporters, samplers, and necessary credentials.
- [ ] Prevent duplicate registration of Resources, transformers, threads, or periodic tasks.
- [ ] Manage out-of-process profilers/controllers via separate reconnect/re-attach.
- [ ] Test each agent independently and test the production combination.
- [ ] Confirm traces, metrics, profiles, and instrumentation work after restore.

## 16. Terms to Remember

- **Java agent:** A JAR loaded by the JVM via the instrumentation API, typically having `premain` or `agentmain`.
- **`premain`:** The entry point of an agent loaded at JVM startup via `-javaagent`.
- **`agentmain`:** The entry point of an agent loaded after startup via the attach mechanism.
- **Instrumentation:** The mechanism of adding or modifying bytecode to observe/alter class behavior.
- **`ClassFileTransformer`:** A component that receives class bytes and returns transformed bytecode.
- **JVMTI:** A native interface for profilers, debuggers, and JVM analysis tools.
- **Native agent:** An agent using native libraries and typically interacting with the JVM via JVMTI/JNI.
- **Dynamic attach:** The mechanism of attaching an agent to a running JVM.
- **Exporter:** A component that sends telemetry to a backend.
- **Sampler:** A component that samples threads, stacks, or events to produce profile data.
- **Telemetry queue:** A queue holding unexported spans, metrics, logs, or profiles.
- **CRaC Resource:** An object registering `beforeCheckpoint(...)` and `afterRestore(...)` callbacks to manage resource lifecycles.

Java agents, profilers, and monitoring tools can continue providing value after restore if each of their parts is properly lifecycle-managed. Preserve necessary instrumentation, stop and release threads, connections, and native handles that cannot be used across checkpoints, and then reinitialize exporters or samplers after restore. For third-party tools, rely only on vendor-confirmed CRaC support and test on the exact JDK, agent versions, and deployment environment.

## References

- [Java Instrumentation API — Java SE](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `premain`, `agentmain`, `Instrumentation`, and class transformation.
- [Java Instrumentation Package Specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): how the JVM loads Java agents and entry point requirements.
- [JVM Tool Interface (JVMTI) Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jvmti.html): agent environments, event callbacks, capabilities, and multiple JVMTI agents coexisting.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore and application resource coordination responsibilities.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource API and how applications release/recreate resources.