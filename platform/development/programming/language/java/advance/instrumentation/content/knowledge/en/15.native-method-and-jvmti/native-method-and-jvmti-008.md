# Selection Boundaries for Java Instrumentation, JVM TI, Debuggers, and Sampling Tools

> **Context:** Java Advance → Instrumentation → **Native and JVM TI**. When you need to understand what a JVM is doing, you should not immediately ask “should I use a Java agent or a debugger?”. Determine the kind of evidence you need: **every time a method is called**, **the state of a thread at a point in time**, **JVM-level events**, or **statistical samples of where CPU/time is spent**. The four tool groups — Java Instrumentation, JVM TI native agent, debugger via JPDA, and profiler/sampling tools — have different boundaries in control level, completeness, intrusiveness, and overhead. This article uses Java 17+; the Java agent and JFR sections were verified with OpenJDK 24.

## 1. Start with the question to answer, not the tool name

Imagine a Java service is running slowly. There are at least five *very different* questions:

1. **“How many times does `OrderService.pay()` run, how long does each call take, and which exceptions does it throw?”** If you need the exact instrumented invocations, this is usually a **Java bytecode instrumentation** or application-level hooks/tracing problem.
2. **“When the error occurs, what is the value of `orderId` in the current frame, and which thread is holding the lock?”** This is a **debugger** problem; you want breakpoints, stepping, stack frames, and state inspection at a specific point in time.
3. **“Do we need low-level VM events, interaction with class-loading hooks, thread/heap/JVM state, or a capability not wrapped by Java APIs?”** You may need a **JVM Tool Interface (JVM TI)** native agent.
4. **“Where is most of the CPU being spent, which hot functions are worth optimizing, and are allocation/lock/GC involved?”** First, use a **profiler/JFR/sampling** tool with an appropriate configuration.
5. **“Can we get sufficiently reliable data in production without pausing requests or modifying the application?”** This is a question of **overhead and operational risk**, not merely whether an API exists.

Common mistakes: using a debugger to infer production latency, using sampling to “prove an invocation ran”, or adding a transformer to every method when you only need to identify hot paths. Each tool answers **a distinct kind of question**.

### Four core concepts

- **Instrumentation:** replacing/wrapping code or inserting probes into execution paths to receive data at **specific points**. This can be a Java `ClassFileTransformer`, libraries like ASM/Byte Buddy, or source code that already has hooks.
- **JVM TI:** a native interface provided by the JVM for C/C++ agents to query/control the VM and receive events; some features depend on capabilities/VM.
- **Debugger:** a product or client that supports breakpoints, stepping, inspecting frames/local variables, and suspending/resuming. In Java, the standard architecture is **JPDA**: JDI ↔ JDWP ↔ VM back-end/JVM TI.
- **Sampling/profiling:** collecting a set of **samples** of stacks/CPU/wall time/allocation, then inferring the distribution of activity. It can also include **non-sample** JVM events, especially in **Java Flight Recorder (JFR)**.

**Architectural layer note:** these four groups are **not four independent, peer, mutually exclusive interfaces**. A debugger often uses JVM TI on the VM side; a native profiler can use JVM TI; a Java agent can combine with JFR; JFR does not only do sampling. The table below is a **solution selection** boundary, not a classification saying “each tool uses only a single technology”.

## 2. Quick decision table

| Criterion | Java Instrumentation | JVM TI native agent | Debugger / JPDA | Profiler / sampling (JFR, async-profiler...) |
|---|---|---|---|---|
| Typical entry point | `-javaagent:agent.jar` / Java Attach if permitted | `-agentpath:/path/lib...` or `-agentlib:name`, sometimes native attach | IDE/`jdb`, local/remote JDWP | JFR startup/`jcmd`; profiler attach/start |
| API level | Java `Instrumentation`, `ClassFileTransformer` | C/C++ `jvmti.h` and JNI | JDI client, JDWP transport, JVM back-end | JFR events/recordings; native/JVM sampling depending on tool |
| Strongest data | **Probed** execution points: invocation, latency, arguments/outcomes by design | Low-level VM events/state/capabilities, class load, threads, heap, and many VM hooks | Breakpoints, local variables, exact frame **when suspended**, step/exception | Hot paths, CPU/wall/allocation distribution, GC/locks, and timeline depending on profile |
| Coverage | Depends on classes/loader/timing, instrumented methods, and retransform capability | Depends on VM/capabilities/phase and enabled events | Depends on debug symbols, thread suspension, and debuggee state | Depends on sampling rate/event settings, recording duration, and stack walking capability |
| Completeness | Can count **the exact calls passing through probes**, if probes and error paths are accurate | Events enabled and emitted by the VM; not all event types are available/lightweight by default | Exact for **the state observed at the breakpoint**, not representative of normal workload | **Statistical**, not guaranteed to see every invocation or absolute ordering |
| Cost | Adding code to hot paths, allocations, logging, class-transform startup, retransform | Native lifecycle, callbacks, capabilities, native errors affect the process; some events are very expensive | Pause/scheduling changes significantly, can expose data/lock threads | Usually suitable for broad diagnosis; overhead depends on settings, frequency, stack depth |
| When to prioritize | Need long-term business-specific **per-call telemetry** | Need VM primitives unavailable in Java APIs/higher-level tools | Need to know **why one specific execution failed** | Hot spots unknown; optimizing CPU/memory/GC; production triage |
| Main pitfall | Assuming the whole VM is instrumented with zero overhead | Assuming native == always fast/complete/safe | Assuming a breakpoint represents normal timing | Assuming sample count == exact call count |

**There is no absolute “best” order.** An investigation can start with JFR to narrow down the area, continue with Java instrumentation on 2–3 key methods, and end with a debugger to identify the faulty variable in a reproducible request. JVM TI is usually an escalation step for **VM-level specific** needs, not the default choice.

## 3. Java Instrumentation: when you need targeted probes in Java code

Main API:

~~~java
public static void premain(String options,
                           java.lang.instrument.Instrumentation inst) {
    inst.addTransformer(transformer);
}
~~~

This is an **illustrative snippet**: you need an entry-point class, a manifest, and a defined `transformer` variable. The agent JAR declares `Premain-Class` and the JVM calls `premain` before `main`. For agents supporting dynamic loading, use `Agent-Class` and `agentmain`.

### What does the API allow?

- Use `ClassFileTransformer.transform(...)` to receive **class-file bytes** when the JVM defines or redefines a class; if registered with `canRetransform=true` and the matching capability, it can be called during retransformation.
- Return `null` to leave the bytes unchanged; or return a **valid new `byte[]`** containing instrumented class code. A transformer is **not a “per method call” callback**. The transformer callback occurs at **class definition/redefinition/retransformation**; to capture method invocations, you must **actually insert probes into the method body** or use hooks in application code.
- You can use `getAllLoadedClasses()`, `isModifiableClass()`, and `retransformClasses(...)` when you need to add instrumentation to already-loaded classes, subject to corresponding capabilities and schema limits.
- Can support module access/search paths using specialized instrumentation APIs, but does not automatically bypass all loader/JPMS barriers.

### Boundaries that must not be ignored

1. **Do not assume all already-loaded classes will be instrumented.** A newly registered transformer does not retroactively apply automatically to all old classes. You must account for startup timing, retransform capability, and `isModifiableClass`.
2. **Do not arbitrarily change class structure after JVM definition.** Retransformation/redefinition does not allow freely adding/removing fields/methods or changing superclass, signatures, or metadata such as nest/record/sealed.
3. **Probes have overhead:** measuring `System.nanoTime()`, creating spans, reading arguments, or serializing payloads on a hot path all have a cost. A Java probe can be fast, but it is not zero-cost.
4. **Do not define latency incorrectly:** a method returning `Future`/`CompletionStage` quickly does not mean the async task has finished. To measure completion, you must observe **the actual completion stage** or the producer work lifecycle.
5. **The error path is also an outcome:** bytecode instrumentation needs to handle normal return, exceptions, nested calls, async context propagation, class loaders, and recursion guards.
6. **Correct class identity:** the same binary name defined by two different defining loaders results in two different classes. Bootstrap targets cannot automatically see system-only helpers.
7. **Do not use bytecode rewriting as a fake debugger:** continuous method probes do not replace the ability to pause at a line and inspect current local variables.

### When to choose a Java agent?

Use it when the question requires **quantifying business execution paths** such as exact counts of calls passing through instrumented methods, duration per invocation, stable tags, and exception outcomes; when you already know the points to measure and want long-term collection. An agent integrated into APM/tracing can provide more useful data than stack samples for a specific transaction. Conversely, if you **do not yet know where the hot spots are**, instrumenting all methods easily creates overhead and noisy data.

## 4. JVM TI: when you truly need VM-level control points

**JVM Tool Interface (JVM TI)** is a native API serving debugging, profiling, monitoring, and VM state/control tools. A native agent typically uses `Agent_OnLoad`, calls `JavaVM.GetEnv(..., JVMTI_VERSION_...)` to obtain `jvmtiEnv*`, requests capabilities, and then registers callbacks/enables events.

~~~text
Native shared library (C/C++)
  └─ Agent_OnLoad(JavaVM*, char* options, void*)
       └─ GetEnv(... JVMTI_VERSION_1_2 ...)
            ├─ GetPotentialCapabilities / AddCapabilities (if needed)
            ├─ SetEventCallbacks (only callbacks with a purpose)
            ├─ SetEventNotificationMode(JVMTI_ENABLE, ...)
            └─ event callbacks in VM/thread context
~~~

The common mechanism is to run:

~~~text
java -agentpath:/absolute/path/to/native-agent-library ... Main
~~~

This is **example syntax**, not a library built in this article. On Windows, the path uses the appropriate OS format; with `-agentlib:shortName`, the JVM searches for the native library according to native library search rules. If C/C++ is needed, you must compile for the matching ABI/architecture of the JVM, with JDK headers `jni.h`, `jvmti.h`, and the corresponding toolchain.

### Some things JVM TI can support

- **VM/class lifecycle:** `ClassFileLoadHook`, class load/prepare, VM init/death.
- **Threads and execution:** events such as `MethodEntry`, `MethodExit`, `Breakpoint`, `SingleStep`, exceptions, and monitor contention; depending on capabilities.
- **Heap/memory:** VM object allocation events, sampled allocation events, and heap inspection per API/capability.
- **Runtime state/control:** stack frames, threads, class/method metadata, and class retransform/redefine, depending on VM state and capabilities.

**Important:** some capabilities are **optional** and not every VM/JDK supports them. JVM TI has **phases** (onload, start, live, dead); many functions are only valid in the appropriate phase. The JVMTI documentation explicitly states that agents must check `jvmtiError` return codes, capabilities, and callback safety.

### Why not use native JVM TI for every problem?

- A native agent runs **in the same process** as the JVM, with strong privileges and high risk: a null pointer, use-after-free, data race, or ABI error can crash the JVM, rather than merely throwing a Java exception.
- Some callbacks run on an **application thread** in sensitive contexts. Blocking, `malloc`, JNI calls, or heavy logging inside a callback can slow down/alter program behavior, or even cause deadlock.
- `MethodEntry`/`MethodExit` at JVM-wide scale can be very expensive; “real low-level events” does not imply lower overhead than bytecode probes.
- A native agent must manage **lifecycle, capabilities, thread safety, reentrancy, synchronization, and GC/JNI references**. Old callbacks must not use resources after they are freed.
- Some native JVMTI agents also **transform Java bytecode** via `ClassFileLoadHook`. This shows that the layers can work together, not that they are two completely disjoint approaches.

### C sketch — for structural understanding only, not a compiled lab

~~~c
#include <jni.h>
#include <jvmti.h>
#include <string.h>

static void JNICALL on_entry(jvmtiEnv *ti, JNIEnv *jni,
                              jthread thread, jmethodID method) {
    // Illustrative callback; do not perform I/O or blocking on hot paths.
    // A real agent must handle state, reentrancy, and overhead.
}

JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM *vm, char *options, void *reserved) {
    jvmtiEnv *ti = NULL;
    jint rc = (*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2);
    if (rc != JNI_OK || ti == NULL) return JNI_ERR;

    jvmtiCapabilities caps;
    memset(&caps, 0, sizeof(caps));
    caps.can_generate_method_entry_events = 1;
    if ((*ti)->AddCapabilities(ti, &caps) != JVMTI_ERROR_NONE)
        return JNI_ERR;

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.MethodEntry = &on_entry;
    if ((*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks))
            != JVMTI_ERROR_NONE)
        return JNI_ERR;

    if ((*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE,
            JVMTI_EVENT_METHOD_ENTRY, NULL) != JVMTI_ERROR_NONE)
        return JNI_ERR;

    return JNI_OK;
}
~~~

This is an **educational skeleton**, **not compiled/run in this article**, and the callback intentionally collects no data. It lacks full lifecycle/cleanup, method filtering, and JNI pending exception handling, and would enable `MethodEntry` broadly if run — **do not deploy as-is in production**. `AddCapabilities` failing is a normal branch if the VM lacks the requested capability. In a real native agent, every JVMTI call needs `jvmtiError` and phase checks.

**Choose JVM TI when:** a clear requirement mandates native VM event/state/control that Java `Instrumentation`, JFR, or standard debuggers do not satisfy; and the team can control the native ABI, JVM version, callback safety, and operations. **Do not choose it just because “JVM TI sounds closer to the JVM so it must be more accurate”.**

## 5. Debugger: when you need to pause at the right place and inspect state

The Java Platform Debugger Architecture (**JPDA**) has three layers:

~~~text
Debuggee JVM + JDWP back-end (often uses JVM TI)
       ⇅ Java Debug Wire Protocol (JDWP)
Debugger front-end using Java Debug Interface (JDI)
       ↓
IDE debugger / jdb / other debugger client
~~~

Thus, **debuggers are often built on JVM TI-level services** on the VM side. It is a **workflow** for finding specific bugs, not simply “another Java agent”.

### What does a debugger do well?

- Set **breakpoints** by line/method/exception.
- Suspend one thread or a set of threads according to a suspend policy, then inspect the call stack and values of locals/fields at that moment.
- `step`/`next` to follow code/logic branches; inspect state at the time of an error; view exception stacks.
- You can use JDI to develop custom debuggers without writing a native JVM TI agent yourself.

But it has limitations:

- Breakpoints **alter execution timing and scheduling**. A suspended thread may hold locks; other threads continue or wait; network/distributed system timeouts may be triggered. You should not treat timing during a breakpoint as normal latency.
- A debugger does not automatically produce a **statistical workload distribution**; it only sees state at the moments you pause. A thread being in method `slow()` at a breakpoint does not prove it is the largest hot path.
- Locals depend on **debug information, JIT optimizations, class version, and JVM support**. Not every variable is always inspectable.
- JDWP exposes a **VM control** surface; do not leave a debug port listening publicly in production. Loopback/ACL/tunnels, authentication, and environment policies are required. An exposed debug port can lead to unwanted process access/control.

### `jdb` exercise tied to the example in section 9

After compiling the application, run:

~~~bash
jdb -classpath out/app demo.app.DecisionDemo
~~~

At the `jdb` prompt:

~~~text
stop in demo.app.DecisionDemo$Work.compute
run
where
cont
exit
~~~

Depending on the breakpoint state, `where` must be called **while the thread is suspended** to print the appropriate stack. `jdb` may report a deferred breakpoint when the nested class is not yet loaded; that is normal. **There is no fixed stdout** for an interactive debug session: breakpoints, source lines, thread IDs, and the `where` output depend on the JVM/JDK/debug information. If you see class not found, verify `-classpath out/app` and the binary class name including the `$` character.

### Remote debugger: loopback only for self-study

Example of launching the JVM waiting for a debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out/app demo.app.DecisionDemo
~~~

Then open a second terminal:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

These are **connection-illustration commands**, not part of an automated script with fixed stdout. The port must **not already be in use**, and the target JVM will **pause before running `main`** until the debugger connects/continues. Only use localhost in a lab; **do not** change `address=127.0.0.1:5005` to wildcard `address=*:5005` without understanding the security risks, especially on servers.

**Choose a debugger when:** you can reproduce a bug, need to examine exact objects/stacks at a point, perform unit-level debugging, or inspect an exception branch. **Do not choose it** to measure p99 production latency or method call counts over several hours.

## 6. Sampling/profiling: first choice for finding hot spots

**Sampling** means observing certain points in time or events periodically or by a sampling rule, then estimating a distribution. For example, 65% of samples containing `OrderService.calculate` on the stack may suggest that method accounts for a significant share of **time measured under that sampling mode**, but it **does not** prove 65% of requests called that method, or that the method ran for exactly 65% of total milliseconds.

### Ask the right questions about sample types

| Mode | What does it measure? | What does it not prove? |
|---|---|---|
| **CPU sampling** | Stacks at samples related to CPU execution/hot code | Exact invocation count, wall time of each request, every blocking wait |
| **Wall-clock sampling** | Stacks over elapsed time, which may include waiting threads depending on tool/config | Pure CPU utilization, exact ordering of every event |
| **Allocation sampling** | Where allocations occur with sample/threshold statistics | Every object created, object lifetime/leak from a single sample alone |
| **Lock/GC/IO events** in JFR | Events with corresponding configuration and thresholds | That every event is sampled; or that a recording file always contains every event |

**Important about JFR:** Java Flight Recorder is the JDK's **event recorder**, not just a CPU sampler. It includes both stack samples like `jdk.ExecutionSample` and events for GC, class loading, locks, sockets, allocation, and many other metrics, depending on configuration. **Do not promise every event is present**: some are disabled, filtered by threshold, or did not occur during the recording window.

### JFR: a good starting point for many production cases

The JDK provides:

- `-XX:StartFlightRecording=...` — start JFR together with the JVM.
- `jcmd <PID> JFR.start ...`, `JFR.check`, `JFR.dump`, `JFR.stop` — control recordings in a running JVM, if attach/diagnostic commands are permitted.
- `jfr summary file.jfr` — list event types and counts.
- `jfr print --events jdk.ExecutionSample file.jfr` — view CPU execution samples, if the configuration recorded that event type.
- JDK Mission Control or corresponding analysis tools to view timelines, flame graphs, and event relationships.

JFR has two built-in configurations:

- **`default.jfc`:** suitable for long-running recording, balancing overhead and data volume.
- **`profile.jfc`:** collects richer data, useful for short-duration profiling; **may increase overhead**.

Do not claim JFR overhead is always a single fixed number across all workloads. Sampling period, enabled events, stack depth, allocation thresholds, JDK, data, and machine load all affect both accuracy and cost.

### async-profiler and other sampling tools

A dedicated profiler like **async-profiler** has CPU, wall-clock, allocation modes and multiple mechanisms for sampling Java/native code stacks depending on the platform. On Linux, CPU mode can rely on OS `perf_events` combined with Java stacks; how stacks are captured and native frame coverage depend on the tool/OS/runtime permissions. This is a **third-party tool, not a Java SE API**.

Use a dedicated profiler when you need deeper CPU/native/wall/alloc analysis, to compare flame graphs, or to reduce the bias of methods that only wait for threads to reach a safepoint. However, **a profiler is also sampling**: do not use it as exact proof of how many times a specific transaction called method `X`.

### Why is a debugger stack or a single `jstack` not a profiler?

A thread dump is a **snapshot** of thread states/stacks at one point in time. It is useful for diagnosing deadlocks, blocked threads, and thread pools, but one snapshot does not produce a reliable statistical distribution for an hour of workload. You can take multiple samples by design, but do not confuse a one-off `Thread.print` with CPU sampling that has intervals, sampling rules, aggregation, and statistics.

**Choose JFR/sampler when:** you do not yet know where the bottleneck is; you need to see CPU, allocation, GC, locks, and timelines/hot paths in a real workload, especially when you do not want to suspend the application with a debugger. After narrowing down the area, add precise instrumentation if you need per-invocation counts/measurements.

## 7. Choosing a tool by scenario

| Scenario | Reasonable starting point | If still insufficient |
|---|---|---|
| Request p99 increased without knowing why | Short JFR `profile.jfc` or suitably configured profiler | Java instrumentation/tracing on endpoints, dependencies, async completion |
| Want exact `charge()` call counts and exception rate per request | Java Instrumentation at the method/business span | App metrics/hooks at boundaries; JFR to investigate CPU |
| Deadlock, BLOCKED threads, starvation | `jcmd Thread.print` / JFR lock events | Debugger in a reproducible lab; JVM TI if low-level hooks are needed |
| Bug only occurs when a specific `customerId` takes the wrong logic branch | Debugger with breakpoints/conditional breakpoints | Add controlled logging or method probes if not reproducible |
| Need native heap/thread/VM events not in Java APIs | Check JVM TI capabilities | Write a native JVMTI agent when truly necessary |
| High CPU but request latency dashboard is low | CPU sampling first to find hot stacks | Check GC, contention, executors, and distinguish CPU vs wall |
| Async method returns `CompletableFuture` early | Instrument method return **and stage completion** | Worker/executor hooks to measure actual queue/runtime |
| Want to find allocation hot spots and GC pressure | JFR allocation/GC or allocation profiler | Heap dump/retained size analysis if a leak is suspected |
| Just want to know if the process is alive and which threads are running | `jcmd Thread.print`/health metrics | No native agent or debugger needed |
| Need very deep native+Java execution inspection | Appropriate profiler/async-profiler; consider JVM TI if requirements are special | Analyze native stacks, symbols, OS permissions |
| Production restricts attach/debug | Enable JFR at startup or use existing metrics | Configure via deployment, do not try to bypass policy |
| Test whether instrumentation hits the right class loader? | Java agent logging in transform callback, test class identity | `getAllLoadedClasses`/retransform as appropriate; JVM TI if Java API lacks it |

### Least-intrusive escalation workflow

~~~text
State the question / SLO / symptom
           |
           v
Existing data? metrics, logs, spans, thread dump
           |
           v
JFR / sampling with appropriate config and duration
           |
           +--- Found hot path? ---------> add targeted Java probes
           |                                  |
           |                                  +--- Need to inspect one failure? -> debugger (lab)
           |
           +--- Specific VM primitive required? -> evaluate JVM TI capabilities,
                                                   ABI, and native agent cost
~~~

**Reasonable exceptions:** if you are developing a debugger, choose JDI right away. If a native-only requirement is already clear, you do not have to go through JFR just to follow a process. The main point is **do not escalate intrusiveness before the need is proven**.

## 8. Boundaries of accuracy, overhead, and safety

### “Having events” is different from “measuring everything accurately”

**Instrumentation** can accurately record **the invocations of methods that are actually instrumented** and the control paths covered by probes. It is not a theorem for every JVM method because many classes may already be loaded, excluded, in bootstrap/custom loaders, or non-modifiable.

**JVM TI events** come from the VM when capabilities/events are enabled; each event type has its own semantics. Some events are delivered on application threads, requiring safe callbacks. If the agent does not enable the event or the VM lacks the capability, no data is produced.

**Debuggers** see the real state of threads/frames when a breakpoint is hit, but pausing can alter the problem being measured. Race conditions sometimes disappear under a debugger due to altered execution scheduling (*Heisenbug*).

**Sampling** provides a distribution estimate, typically using stack attribution. It does not guarantee seeing short methods, rare requests, or events occurring between two samples. A stack sample can also be biased by JIT, stack walking, interval, and thread eligibility.

### Impact on production

| Impact | Instrumentation | Native JVM TI | Debugger | Sampling/JFR |
|---|---|---|---|---|
| Startup / class loading | Present when premain/transforming many classes | Present during native agent init/hooks | Possible when JDWP is enabled | Present when starting JFR or attaching profiler |
| Hot path | Inserted probes add cost on every traversal | Callbacks/events can be very heavy if broadly enabled | Breakpoints cause significant suspension | Statistical cost depends on rate/events |
| Sensitive data scope | Arguments/results/payloads from probes | VM memory, heap, thread state | Locals, heap, object state, remote control | Stacks, method names, threads/events, may contain data |
| System risk | Verify/linkage errors, recursion/locks | **Native crash**/JNI/VM state corruption, not just exceptions | Request/lock pauses, debug port security | Disk buffers, overhead, attach permissions, statistical resolution |
| Rollback ability | Removing transformer does not undo already-installed bytecode | Depends on each event/VM capability | Detach/resume does not reverse debugging side effects | Stopping recording changes no code, but does not erase collected data |

**No tool has absolute “zero overhead”.** Benchmarks should check throughput, p50/p95/p99, GC, allocations, JIT warmup, and logs before/after under a representative workload. In particular, do not use latency while a debugger is suspending threads to conclude how slow production is.

### Access safety

- With Java agents/JVM TI, native code or bytecode can have very high privileges in the process. Only run trusted agents, and control JAR/native-library integrity and deployment flags.
- With JDWP, **do not expose the debug listener to the Internet**. Bind to loopback, use tunnels/ACLs, and follow operational policies; a debugger can inspect and modify process state.
- With JFR/profilers, review who has permission to attach, read `.jfr` files, and view method names, stacks, class names, or application data. Recordings are artifacts that must be protected.
- In environments that disallow attach, respect the policy; you can use pre-configured JVM startup flags/observability, without trying to bypass restrictions.

## 9. Runnable lab: Java Instrumentation and JFR observing the same program

Goal: on the same CPU-bound app, observe **deterministic events when a class is transformed** from a Java agent and **stack samples** from JFR. This compares a “specific milestone” with “statistical evidence”, **without** claiming the logging agent transformed bytecode.

### 9.1 Directory structure

~~~text
tool-choice-lab/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── ChoiceAgent.java
│       └── app/
│           └── DecisionDemo.java
└── out/
    ├── agent/
    ├── app/
    └── choice-agent.jar
~~~

Requires **JDK 17+**, with `java`, `javac`, `jar`, and `jfr`. If using a debugger, add `jdb`. Run commands from the `tool-choice-lab/` root directory.

### 9.2 Java agent — `src/demo/agent/ChoiceAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ChoiceAgent {
    private ChoiceAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        System.out.println("[AGENT] premain");

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain, byte[] classfileBuffer) {
                if ("demo/app/DecisionDemo$Work".equals(className)) {
                    System.out.println("[AGENT] transform=" + className);
                }
                return null;
            }
        });
    }
}
~~~

Meaning:

- The JVM calls `premain` before the app's `main`.
- The transformer is registered **once**, logging only when the JVM defines the class with internal name `demo/app/DecisionDemo$Work`.
- `return null` means **do not modify bytecode**; the `[AGENT] transform=...` marker is **not** a method invocation marker.
- `DecisionDemo$Work` is a static nested class of the app, loaded when the app first uses it after `[APP] begin`. This is why the log appears in that exact position during the test.
- `"literal".equals(className)` avoids a null pointer when the callback passes a null name.
- Do not use `System.out.println` in a production transformer when there are thousands of classes: logging on the class-loading path can slow down the JVM, cause recursive class loading, and create lock contention.

### 9.3 App — `src/demo/app/DecisionDemo.java`

~~~java
package demo.app;

public final class DecisionDemo {
    private static volatile long checksum;

    public static void main(String[] args) {
        System.out.println("[APP] begin");
        checksum = Work.compute();
        System.out.println("[APP] checksumPositive=" + (checksum > 0));
        System.out.println("[APP] end");
    }

    static final class Work {
        static long compute() {
            long total = 0;
            for (int round = 0; round < 10; round++) {
                for (int i = 0; i < 20_000_000; i++) {
                    total += i % 7;
                }
            }
            return total;
        }
    }
}
~~~

This is **synthetic CPU work with a deterministic result**. `checksum` is a `volatile` field so the work result is used and printed; the exact numeric value is not the focus, so only the `> 0` condition is printed. The CPU block runs once and the app exits; actual runtime will vary by CPU/JIT/JVM, so the example does not hard-code milliseconds.

### 9.4 Agent manifest — `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ChoiceAgent

~~~

A newline and trailing blank line are required at the end of the manifest. This example does **not** use `Agent-Class` or `Can-Retransform-Classes` because it does not attach dynamically and does not retransform already-loaded classes.

### 9.5 Build on macOS/Linux

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/demo/agent/ChoiceAgent.java
javac --release 17 -d out/app src/demo/app/DecisionDemo.java
jar --create --file out/choice-agent.jar --manifest manifest.mf -C out/agent .
~~~

Build on **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/demo/agent/ChoiceAgent.java
javac --release 17 -d out/app src/demo/app/DecisionDemo.java
jar --create --file out/choice-agent.jar --manifest manifest.mf -C out/agent .
~~~

Checking `jar --list --file out/choice-agent.jar` shows `META-INF/MANIFEST.MF` and `demo/agent/ChoiceAgent.class` (along with the anonymous transformer class). Use `--release 17` so the class files/API are compatible with Java 17+.

### 9.6 Run without agent

~~~bash
java -cp out/app demo.app.DecisionDemo
~~~

**Verified stdout on OpenJDK 24:**

~~~text
[APP] begin
[APP] checksumPositive=true
[APP] end
~~~

Without a Javaagent, there is no `premain` or transformer callback. The app runs normally.

### 9.7 Run with Java Instrumentation

**Bash:**

~~~bash
java -javaagent:out/choice-agent.jar -cp out/app demo.app.DecisionDemo
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/choice-agent.jar" -cp out/app demo.app.DecisionDemo
~~~

**Verified stdout:**

~~~text
[AGENT] premain
[APP] begin
[AGENT] transform=demo/app/DecisionDemo$Work
[APP] checksumPositive=true
[APP] end
~~~

Reading the log:

- `[AGENT] premain`: the JVM invokes the startup agent before the application.
- `[APP] begin`: the app has entered `main`.
- `[AGENT] transform=...`: the JVM defines the nested class; the transformer observes a **class file load event**.
- `[APP] checksumPositive=true`: the CPU work completed and the result was used.
- `[APP] end`: the app finishes.

**What must not be inferred:** seeing one transform callback does not mean `Work.compute()` ran only once according to agent statistics. The transformer logs by **class definition**, not by method call. In this app version, the fact that `compute()` was called once is due to **the app's source code**, not something the transformer proves.

### 9.8 Run with JFR (no Java agent needed)

**Bash:**

~~~bash
java -XX:StartFlightRecording=filename=choice.jfr,settings=profile,dumponexit=true -cp out/app demo.app.DecisionDemo
~~~

**PowerShell:**

~~~powershell
java "-XX:StartFlightRecording=filename=choice.jfr,settings=profile,dumponexit=true" -cp out/app demo.app.DecisionDemo
~~~

The JVM writes `choice.jfr` to the working directory when the process exits, if the runtime supports JFR. You may see a few `[jfr,startup]` log lines before the three `[APP]` lines. **Do not hard-code** PID, timestamp, recording ID, sample count, or file byte size into expected stdout: these values depend on the JDK and machine.

View statistics and some CPU samples:

~~~bash
jfr summary choice.jfr
jfr print --events jdk.ExecutionSample --stack-depth 5 choice.jfr
~~~

A sample event has a **similar** structure (timestamp and thread ID vary):

~~~text
jdk.ExecutionSample {
  startTime = ...
  sampledThread = "main" (...)
  state = "STATE_RUNNABLE"
  stackTrace = [
    demo.app.DecisionDemo$Work.compute() ...
    demo.app.DecisionDemo.main(String[]) ...
  ]
}
~~~

In the verification run, `choice.jfr` was created; `jfr summary` listed `jdk.ExecutionSample` and `jfr print` showed stack samples involving `Work.compute()`. **There is no guarantee a short program will always have a sample of that exact method**; sampling intervals and short workload durations can miss some frames. You can increase the loop count or recording length when experimenting, without changing the statistical meaning.

### 9.9 Both Java agent and JFR can be enabled together

**Bash:**

~~~bash
java -XX:StartFlightRecording=filename=combined.jfr,settings=profile,dumponexit=true -javaagent:out/choice-agent.jar -cp out/app demo.app.DecisionDemo
~~~

**PowerShell:**

~~~powershell
java "-XX:StartFlightRecording=filename=combined.jfr,settings=profile,dumponexit=true" "-javaagent:out/choice-agent.jar" -cp out/app demo.app.DecisionDemo
~~~

Actual verification on OpenJDK 24:

- Stdout still contains `[AGENT] premain`, `[APP] begin`, `[AGENT] transform=demo/app/DecisionDemo$Work`, and exits normally.
- The JVM emits separate `[jfr,startup]` lines, varying by runtime.
- The file `combined.jfr` is created.
- `jfr print --events jdk.ExecutionSample --stack-depth 2 combined.jfr` showed at least one sampled stack containing `Work.compute()` and `DecisionDemo.main(...)` in the verification environment.

Thus, **the two mechanisms complement each other**: the Java agent logs an exact class-loading point; JFR records multiple events/samples to view the execution distribution. Do not add “1 transform callback” and “N execution samples” together as two counters with the same unit.

### 9.10 JFR with a running JVM using `jcmd`

When the JVM is still running and you know the PID, the JDK provides these commands:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=triage settings=profile duration=30s filename=triage.jfr
jcmd 12345 JFR.check
~~~

`12345` is an **illustrative PID** and must be replaced with the actual process PID; do not run that literal value. The `JFR.start` command requests a **30-second** recording; the `triage.jfr` file is usually written **when the recording stops** after the duration, and does not necessarily exist as soon as `JFR.start` returns. Once the file exists, use `jfr summary triage.jfr` to view events.

If you want to take a snapshot mid-recording without stopping the recording:

~~~bash
jcmd 12345 JFR.dump name=triage filename=triage-snapshot.jfr
~~~

A point-in-time snapshot may differ from the final recording. Attach permissions and same-user/OS policies can restrict the commands; do not infer a lack of JFR support from an attach error.

**Do not use the short-lived process from section 9.6 to try attaching after the app has exited.** To test `jcmd`, you need an app that stays alive long enough, or an already-running service. The `jcmd` commands here are interactive instructions, not actions performed on a production PID.

### 9.11 Debugger and Java agent can coexist

You can debug the `DecisionDemo` application with `jdb` as in section 5 while using a Java agent or JFR. However, when the debugger suspends threads at a breakpoint, **sampling and durations can be significantly altered**. Avoid comparing two performance results “with debugger” and “without debugger” as if under the same conditions.

## 10. Do not equate different metric types in dashboards

The following metrics are **different** things being measured:

| Reasonable metric name | Source | Definition |
|---|---|---|
| `class_transform_count` | Java transformer | Number of class-file transform callbacks matching the filter |
| `method_invocation_count` | Probe inserted in method | Number of invocations **that passed through the probe** |
| `method_duration_nanos` | Entry/exit probe | Method duration under synchronous semantics |
| `async_stage_completion_latency` | Completion listener on returned stage | Duration until the callback observes a terminal outcome; does not assume the worker stopped after cancel |
| `jfr_execution_sample_count` | JFR | Number of samples recorded during the recording window |
| `jvmti_method_entry_event_count` | JVM TI if enabled | Number of events emitted by the VM and received by the agent per capability/filter |
| `debugger_breakpoint_hit_count` | Debugger | Number of times a breakpoint was hit during a debug session |

For example, if JFR records 12 samples containing `Work.compute`, that **does not** mean `Work.compute` was called 12 times. Conversely, a transformer logging the `Work` class once does not mean its method ran only once. For method instrumentation, a callback at **method entry** is what can count invocations, after properly handling classloading, inlining, exceptions, and exclusions according to how the agent injects probes.

### When measuring async workloads

A method returning a `Future` does not prove the task has finished. If you need end-to-end latency, you must:

1. Record the API entry timestamp.
2. Record the method returning the handle separately.
3. Attach a listener to **the actual `CompletionStage`** or instrument the producer/executor to record the appropriate completion timestamp.
4. Distinguish success, failure, cancellation, and timeout; a canceled promise may complete before the underlying worker actually stops.
5. Do not call `future.get()`/`join()` in a method-exit probe just to wait for completion: that breaks nonblocking semantics and can cause deadlock.

A CPU sampler can tell you “CPU time is in `Worker.run()`”; it **does not** replace business tracing to correlate a task with a request ID and completion outcome.

## 11. Common mistakes and how to avoid them

| Wrong observation / proposal | Why it is wrong | What to do instead |
|---|---|---|
| “Just use JVM TI, it's close to the VM so it's fastest” | Native capabilities/events have overhead and crash risk | Choose low-level primitives **only when Java/JFR/JDI are insufficient** |
| “`ClassFileTransformer` gives a callback on every method call” | Callback occurs on class definition/redefinition/retransform | Insert probe code into the method or use another hook |
| “`retransformClasses` will automatically instrument every loaded class” | Must select classes, capabilities, modifiable ones, and valid bytes | Check `isRetransformClassesSupported`, `isModifiableClass`, and filters |
| “A debugger gives accurate p99 latency” | Suspension alters timing | Measure production with metrics/tracing/sampling, debug in lab |
| “One thread dump is a CPU profile” | A single point in time does not give a distribution | Use JFR/sampler with an appropriate interval |
| “5% of samples means 5% of requests called the method” | Samples do not represent request counts | Count invocations with probes/spans |
| “JFR only samples CPU, it has no other events” | JFR records many event types/thresholds | Choose `default.jfc`/`profile.jfc` or configure purposefully |
| “JFR is always under 1% overhead” | Depends on settings and workload | Benchmark overhead and bound duration/size |
| “JDWP is just a port for reading logs” | A debugger can inspect/control the VM | Protect the listener, bind loopback only in lab |
| “Enabling JVM TI MethodEntry globally is cheap” | Event callbacks can affect every method/thread | Filter, limit, and measure cost; consider bytecode probes |
| “A native agent throws a Java exception if it fails” | Native errors can crash the entire process | Control ABI/threads/JNI references, test on staging |
| “JFR has no sample so the method didn't run” | Sampling can miss short methods or lack configuration | Check settings/window; if exact evidence is needed, use probes |
| “Having method probes tells you the cause of a race” | Probes can alter scheduling and only record instrumented events | Use a debugger, deterministic tests, and concurrency analysis |
| “Stopping JFR or removing a transformer erases previous telemetry/bytecode” | Already-recorded data and already-instrumented classes remain | Design lifecycle, retention, and rollback according to capabilities |
| “Installing multiple agents won't interact” | They share the same VM/process and can affect each other | Test combinations, clarify ownership, classloader, and transform order |

## 12. Self-check questions

1. **Need to inspect local variables when a request fails, what should you start with?** Debugger/JDI if you have a reproducible case and a safe environment; instrumentation if you need to record a selective set of fields across many requests.
2. **Need to find the top 3 CPU-consuming methods when the location is unknown?** JFR/profiler CPU sampling first, then instrument if you want per-call metrics.
3. **Does `ClassFileTransformer.transform` receive a callback on every method invocation?** No. It processes classfile bytes on class load/redefine/retransform.
4. **What must a JVM TI native agent check before enabling an event?** VM phase, supported capabilities, error codes, callback signatures, and concurrency constraints.
5. **Are a Java debugger and JVM TI two completely unrelated technologies?** No. In standard JPDA, the JDWP backend uses JVM TI on the debuggee side.
6. **What is JDWP used for?** The protocol for transmitting requests/events between the debugger and target VM, not a profiler.
7. **Does JFR only do sampling?** No. It records both sampling events and many other event types.
8. **How many times does a `jdk.ExecutionSample` containing `Work.compute` prove the method ran?** You cannot determine the exact call count from that sample.
9. **Is JFR `profile.jfc` suitable to leave on indefinitely in all production environments?** It should not be the default; consider overhead, size, duration, and workload.
10. **When an async method returns a Future quickly, where should you measure?** Distinguish method-return latency, future/stage terminal outcome, and actual worker completion.
11. **Is binding a debug port to `*:5005` safe for every machine?** No; restrict the listener, prefer loopback and protective layers.
12. **What if you need to inspect a VM primitive not available in Java APIs/JDI/JFR?** Evaluate JVM TI, capabilities, and native engineering cost.
13. **Can a native profiler observe Java/native stacks while still being sampling?** Yes; it may have less bias than other methods, but it does not turn into an exact trace of every call.
14. **Can a Java agent and JFR be used together?** Yes. They produce two kinds of data that can complement each other if overhead is managed.
15. **What criterion should you base tool selection on first?** The question needing evidence, accuracy, observation duration, production impact, deployment permissions, and operational skills.

## 13. Pre-deployment decision checklist

- [ ] State the question clearly: *exact per-invocation*, *snapshot state*, *VM event*, or *statistical hotspots*?
- [ ] Identify the environment: Java/JDK version, vendor, OS, JVM/agent capabilities, and attach policy.
- [ ] Prefer existing low-intrusiveness data (metrics, logs, spans, JFR) if it meets the requirement.
- [ ] For Java instrumentation, check loader/module, class-load timing, retransform support, probe coverage, and overhead.
- [ ] For JVM TI, check native ABI, capabilities, VM phases, callback safety, JNI exception state, and native failure risk.
- [ ] For a debugger, only use breakpoints in environments that allow suspension and protect the JDWP port.
- [ ] For sampling, choose CPU vs wall vs allocation; target duration, rate, stack depth, and event settings.
- [ ] Do not conclude “it didn't happen” just because **samples missed it**; do not conclude “the method was called” just because the transformer saw the class file.
- [ ] Keep conditions identical when benchmarking tool on/off; observe overhead and tail latency.
- [ ] Do not log secrets from arguments, stacks, or heap; manage `.jfr` files, debug access, and retention.
- [ ] Test interactions if running multiple agents/profilers concurrently.
- [ ] For async APIs, clearly define start/end points before recording latency.
- [ ] When capability/attach permission is unavailable, use permitted fallbacks instead of bypassing.
- [ ] Document the evidence type and limitations so statistics are not turned into “absolute truth”.

## 14. Official and technical references

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): Javaagent startup, agent manifest, and class loader/module loading.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, capabilities, and limitations.
- [JVM Tool Interface 21 Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): native agent, capabilities/phases, callbacks, errors, and events.
- [JPDA Architecture](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/architecture.html): relationship between JVM TI, JDWP, JDI, and debuggers.
- [Java SE 21 — `jdb` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html): breakpoints, step, `where`, `cont`, debugger attach.
- [Java SE 21 — JDWP connection/invocation](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, transports, and connection configuration.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start/check/dump/stop`, `Thread.print`.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `jfr summary`, `jfr print --events`, and analyzing recordings.
- [Java Flight Recorder configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html): `default.jfc` and `profile.jfc`.
- [async-profiler — Profiling Modes](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md): CPU/wall/allocation sampling, Java/native stack collection (third-party tool, environment-dependent).
