# 7.3 JConsole for viewing charts, attributes, and JVM management operations

## Learning objectives

**JConsole** is a graphical user interface (GUI) tool bundled with the JDK that uses **Java Management Extensions (JMX)** to observe and, when authorized, **manage** a running Java Virtual Machine. Unlike a read-only chart dashboard, JConsole also accesses the **MBeans** tree: reading attributes, viewing notifications, and invoking operations. Those capabilities are valuable during diagnostics yet carry risk: a single button click can trigger GC, alter logging settings, or execute administrative functions inside the target JVM process.

This lesson walks through JConsole around three practical pillars: **viewing charts**, **reading attributes**, and **performing JVM management operations** in a controlled manner.

After this lesson, you will be able to:

- Launch JConsole from JDK 17+, connect to the right **local or remote JVM** via JMX, and verify PID, start time, and access permissions.
- Read the **Overview, Memory, Threads, Classes, VM Summary, and MBeans** tabs accurately; understand whether each chart/value is a snapshot or a time series captured since monitoring began.
- Navigate the `java.lang` tree and custom MBeans, distinguishing **read-only attributes**, **writable attributes**, **operations**, and **notifications**.
- Distinguish observational actions from state-changing actions such as **Perform GC**, **set Verbose**, **invoke operation**, or **heap dump**, and know when operational approval is required.
- Build a standalone Java 17+ program registering an MBean with attributes and operations; connect JConsole to read, write, invoke methods, and observe charts.
- Collect data with timestamps, units, context, and limitations; secure remote JMX using authentication, encryption, least privilege, and network boundaries.

> Primary scope: Java SE/JDK 21 with illustrative behavior applicable to JDK 17+. Specific screens may differ by JDK, operating system, look-and-feel, JVM implementation, and application-registered MBeans. **Sensitive actions must be practiced on test JVMs, never run casually in production.**

## 1. JConsole, JMX, and MBeans: understanding each role

To use JConsole effectively, separate three layers:

| Component | Role | Example |
| --- | --- | --- |
| **Target JVM** | The real process running application code and exposing management metrics | Service PID or demo program |
| **JMX agent / MBeanServer** | Exposes MBeans, serves attribute reads, operation invocations, and notifications | The JVM's Platform MBeanServer |
| **JConsole** | **Client** GUI tool connecting via JMX to display and control information | Memory, Threads, MBeans tabs |

Platform MXBeans such as `MemoryMXBean`, `ThreadMXBean`, `ClassLoadingMXBean`, and `RuntimeMXBean` provide standard data. Applications or libraries can also register **custom MBeans** for queues, caches, feature state, counters, or administrative operations.

A diagram:

```text
+---------------------------+           JMX connector           +---------------------------+
| JConsole (GUI, client)    | <--------------------------------> | Target JVM (process)      |
|  - Overview / Memory      |     local attach or authorized     |  Platform MBeanServer     |
|  - Threads / Classes      |            remote JMX              |   - java.lang:* MXBeans   |
|  - VM Summary / MBeans    |                                    |   - app custom MBeans     |
+---------------------------+                                    +---------------------------+
              |                                                               |
              +-- Read attributes, display series                             +-- MXBeans reflect the VM
              +-- Invoke operations, write attributes when authorized         +-- Operations run in JVM
              +-- Subscribe to notifications when supported                   +-- May change state/cost
```

**JConsole is not an all-purpose profiler.** It offers basic CPU/memory/threads/classes charts and thread stack inspection, but it does not collect full flamegraphs, allocation stacks, distributed traces, query latencies, or pre-connection history. Use JFR, GC logs, thread dumps, metrics, and tracing when investigations require deep data or longer timelines.

### 1.1 Read-only or management?

Reading `HeapMemoryUsage`, `ThreadCount`, or `LoadedClassCount` is generally **monitoring**. Conversely:

- Writing a **writable** MBean attribute invokes the setter in the target JVM.
- Clicking an **operation** button can invoke an MBean method in the target JVM.
- `Perform GC` in the Memory tab requests the JVM to run garbage collection.
- Some operations like `dumpHeap` can cause pauses, heavy I/O, and create files containing sensitive data.
- Enabling verbose class loading/GC or modifying logging configuration can increase log volume and overhead.

**JMX view access does not mean operation access.** In production, policy should default to read-only; grant separate administrative privileges for approved actions and audit changes.

## 2. Preparing before connecting

### 2.1 Where is JConsole located?

On JDK distributions that include this tool, the executable usually resides at:

```text
<JDK_HOME>/bin/jconsole
```

From a terminal:

```bash
jconsole
```

This command launches a **graphical interface**, not a CLI printing metrics to stdout. It requires a GUI display environment; minimal containers, headless servers, and custom runtimes built with `jlink` may omit `jconsole`. Run the GUI JDK tool from an authorized administrative workstation instead of installing a desktop into production containers just to view charts.

Per JDK 21 documentation, JConsole supports local/remote connections. For a local application with a known PID:

```bash
jconsole 12345
```

**12345 is an illustrative PID.** Replace it with the verified PID of the target process. Run JConsole and the target JVM under compatible user permissions. In HotSpot environments supporting attach, JConsole can start the management agent on local connect if not already enabled; however, this **is not guaranteed** if the JVM disables attach, policy blocks it, namespaces/containers differ, or tools/JDKs are incompatible.

### 2.2 Selecting the right Java process

Before picking a row in Local Process, confirm:

1. Service/application name, host, and container/pod or session.
2. PID alongside **process start time**, since PIDs can be reused after restarts.
3. JDK/runtime version and the specific instance serving failing requests; do not attribute another replica's data to a failing replica.
4. Active JVM and attach/JMX permissions; one machine may run multiple `java`/`javaw` processes.
5. Compatible GUI environment and target system, plus approved monitoring policy.

On Linux, you can use authorized OS process metadata:

```bash
ps -p 12345 -o pid,lstart,etime,comm,args
```

This command may reveal **arguments containing secrets**; inspect it in a trusted terminal and save only redacted excerpts. `jps`/`jcmd -l` are also helpful where supported, though they may not list JVMs inside isolated container namespaces.

In JConsole, once connected, inspect **VM Summary** to cross-check runtime version/uptime and JVM arguments; never interpret charts before confirming you attached to the right target.

### 2.3 Local vs. remote differences

| Mode | Typical connection method | Conditions and limitations |
| --- | --- | --- |
| **Local** | Run `jconsole`, select Local Process, or `jconsole <PID>` | Same machine, matching user/permissions, attach, and namespace; may fail on non-attachable JVMs |
| **Remote host:port** | `jconsole host.example:9010` or enter host/port in GUI | Target must expose a JMX remote connector; involves TLS, authentication, authorization, network/firewall/RMI |
| **JMX Service URL** | Choose Remote/Advanced connection in UI and enter URL | For custom connectors or full URLs; syntax depends on connector |
| **Across restricted networks** | Connect inside approved admin network/VPN/tunnel | Do not turn JMX into a public endpoint; remote network topology/RMI ports must match |

For Remote JMX over RMI in HotSpot, distinguish the **RMI registry port** from the **RMI connector/server port**, and sometimes configure `java.rmi.server.hostname` so the stub advertises an address reachable by clients. A valid host:port that hangs on "Connecting..." may stem from the second port or an unreachable hostname inside the RMI stub; never disable TLS/authentication as a "quick fix."

JDK 21 documents system properties such as `com.sun.management.jmxremote.port`, `com.sun.management.jmxremote.rmi.port`, and `java.rmi.server.hostname`. These are configured under operational/deployment policies; **never open remote JMX in production just because you want to use JConsole**.

### 2.4 Securing remote JMX connections

Remote JMX is an **application management control plane**, not a plain metrics port. When authorized for deployment:

- Restrict access via network/firewall/VPN/bastion and only required RMI ports; never expose directly to the Internet.
- Configure TLS/SSL and server/client authentication per policy with explicit credentials and authorization.
- Apply least privilege: `readonly` accounts for observation; write/invoke permissions strictly for authorized personnel or systems.
- Never run authentication-less, TLS-less configs (`authenticate=false`, `ssl=false`) in production.
- Never store passwords in command history, tickets, screenshots, or shared URLs; manage keys/secrets according to policy.
- Verify RMI registry protection, password/access file permissions, and container/NAT compatibility.
- Do not assume opening the GUI makes every MBean action safe; **access permission and mutation permission** are separate decisions.

JConsole/management agents also add overhead and can affect the JVM, especially when polling heavy data. Oracle advises caution with local JConsole in production; diagnostics typically use a separate JConsole client over a secured remote connection when required.

## 3. The six standard tabs: what can you read?

The JDK 21 JConsole interface typically has **six tabs**:

| Tab | Primary data | Issues commonly narrowed down |
| --- | --- | --- |
| **Overview** | CPU, memory, thread count, loaded classes charts | Comparing resource fluctuations over the same time window |
| **Memory** | Heap/non-heap, memory pools, used/committed/max, GC count/time | Heap pressure, GC activity, growing memory regions |
| **Threads** | Live/peak threads, thread names/states/stacks, deadlock detection | Stuck requests, block/lock contention, thread growth |
| **Classes** | Current loaded, total loaded, unloaded classes | Class loading churn, suspected classloader retention |
| **VM Summary** | VM/runtime facts, uptime, CPU time, flags/args, GC and OS summary | Confirming target JVM and execution context |
| **MBeans** | ObjectName, attributes, operations, notifications for platform/custom MBeans | Reading granular fields, inspecting domain counters, controlled management |

All of them are **views into the same JVM**, though getters and charts may sample data at different instants. Never assume every value shown together forms an "atomic transaction snapshot."

## 4. Overview: reading the summary charts

The **Overview** tab displays CPU, memory, threads, and loaded classes charts on one screen. It helps answer: "Did the latency spike window coincide with rising heap, thread counts, or class loading?"

### 4.1 What questions do the charts answer?

- **CPU:** represents CPU consumption based on OS/MXBean metrics JConsole can obtain; does not identify which methods used CPU. On multi-core hosts, interpret percentages according to the VM/JMX implementation's definition.
- **Memory:** displays memory usage over time, typically heap-oriented; a rising chart alone does not prove a retained-object leak.
- **Threads:** observed platform/live thread count; increases can stem from pool scaling, workload, blocked requests, or uncontrolled thread creation.
- **Classes:** currently loaded class count; growth during warm-up is normal, whereas continuous growth across redeploys/plugin reloads warrants checking classloader lifecycles.

A **simultaneous spike** on two charts is **correlation**, not proof of a causal chain. For example, rising CPU alongside heap used can result from request throughput, allocation churn, or GC; corroborate with CPU samples/JFR/GC events, request metrics, and traces.

### 4.2 Time Range and historical data

JConsole displays data gathered while actively monitoring the JVM within the GUI session's buffers; changing the **Time Range** menu does not retrieve history from before you connected unless a separate recording system exists. Opening JConsole after an incident ends and seeing flat lines **does not prove** the system never spiked.

When choosing a time range:

1. Pick a window wide enough to show baseline, incident, and recovery.
2. Check resolution/sampling density. A 1-second spike may be invisible if the polling interval is large.
3. Compare the exact same time window across Overview and detail tabs.
4. Record UTC timestamps and JVM uptime; never merge two processes across a restart into one continuous series.

### 4.3 Saving chart data as CSV

JDK 21 documentation describes **right-click chart → Save data as...** to export chart series to **CSV**. The CSV file is saved on **the machine running JConsole**, not automatically on the remote JVM host. After exporting, verify timestamps/timezones, column headers, units, observation window, and sample count.

CSV reflects only the samples JConsole held in its chart buffer, not the ground truth of the JVM's entire lifetime. For multi-day monitoring, dedicated metrics systems with retention and alerting are appropriate; JConsole fits interactive investigation and live inspection.

## 5. Memory: heap, non-heap, and memory pool charts

The **Memory** tab lets you pick scopes from the chart dropdown: total heap, non-heap, and individual **memory pools** exposed by that JVM. Pool count and names depend on the implementation and GC. On HotSpot JDK 21, you may see Metaspace, Code Cache, and G1/ZGC pools; never use legacy JDK diagrams showing "Permanent Generation" to claim PermGen exists in JDK 21.

### 5.1 Three critical values

| Value | Meaning | Must not be interpreted as |
| --- | --- | --- |
| **Used** | Bytes currently used in the managed Java region; may include unreachable objects not yet GC'd | "Confirmed retained/live objects" or "process RSS" |
| **Committed** | Memory the JVM has guaranteed/reserved for the measured region | Physical resident RAM or current used |
| **Max** | Maximum limit if the JVM can expose one; may be undefined | Already allocated memory or sole limit of the entire container |

Opening MBeans and reading `java.lang:type=Memory`, attribute `HeapMemoryUsage` returns a composite containing `init`, `used`, `committed`, and `max` per the Java Management API. A `max` of `-1` means "undefined," **not 0 or unlimited**.

**Illustrative arithmetic example** (not output from a live JVM):

```text
heap.used      = 300 MiB
heap.committed = 600 MiB
heap.max       = 1,200 MiB

used / committed = 50%
used / max       = 25%
```

A dashboard saying "heap usage 50%" without stating whether the denominator is `committed` or `max` causes confusion. Same snapshot, different questions.

### 5.2 Reading the heap used curve

Normally heap used rises during object allocation and drops after GC events; a sawtooth pattern can be completely normal. Do not diagnose a leak without a **post-GC** trend under comparable workload, allocation/retention evidence, or proper heap analysis. Heap used cannot be converted directly into RSS: native memory, thread stacks, direct buffers, mappings, code cache, and other regions all contribute to footprint.

To correlate GC with latency:

1. Identify the incident time window.
2. Record heap used/committed/max at relevant points.
3. Cross-check GC count/time in Memory alongside GC logs/JFR for frequency and pause durations.
4. Correlate throughput, allocation rate, request latency, and container memory.
5. When retained objects are needed, use heap dumps/histograms only after weighing overhead, disk size, and sensitive data.

GC time from the Management API is typically a **cumulative total** per collector since JVM startup, not the duration of the specific request you are inspecting; computing rates/deltas requires two snapshots and the elapsed time interval.

### 5.3 The Perform GC button is an action, not "view more"

JConsole has a **Perform GC** button in the Memory tab. Clicking it asks the JVM to execute garbage collection; it **can affect latency/throughput** and alters the very state under investigation. Depending on GC/VM flags, the JVM handles the request according to its own policy; manual GC should not be used to establish a standard baseline.

Therefore:

- During a production incident, **never click Perform GC** just to see the chart "after cleanup."
- Never use a drop in `used` after a forced GC to prove there is no leak.
- If truly needed in a lab environment, log the click timestamp and mark it as an intervention, no longer pure observation.
- Do not assume JConsole prompts for confirmation on all operations; several actions execute immediately.

## 6. Threads: thread counts, stacks, and Detect Deadlock

The **Threads** tab plots live/peak thread counts over time and lists threads the VM exposes for management. Selecting a thread displays its **name, state, and stack trace**.

### 6.1 Interpreting thread states

| State | General meaning | What else to check |
| --- | --- | --- |
| `RUNNABLE` | Thread is executing or ready to execute in the JVM model | Does not prove high CPU alone; check CPU samples/OS counters |
| `BLOCKED` | Waiting for a monitor lock | Lock owner, relevant frames, duration stuck |
| `WAITING` | Waiting indefinitely, e.g. on a queue, condition, or join | Can be completely normal for idle workers |
| `TIMED_WAITING` | Waiting with a timeout (sleep, wait, park, etc.) | Inspect task and timeout value |
| `NEW` / `TERMINATED` | Not yet started / finished in the thread model | Active thread list snapshots may omit these states |

A `WAITING` thread may be healthy and awaiting work. A `RUNNABLE` thread is not automatically a CPU hotspot. To diagnose hung requests, capture **multiple spaced snapshots** and correlate with thread pool queues, lock metrics, request traces, and JFR.

### 6.2 Detect Deadlock

In the Threads tab, **Detect Deadlock** issues a JVM-supported deadlock check and shows any cycles found. Per JDK 21, the tool can detect deadlocks involving **object monitors** and supported `java.util.concurrent` ownable synchronizers.

Limitations:

- Not every hang is a tool-detectable deadlock. Threads can stall on network I/O, external database locks, queue starvation, or waiting on signals without forming an explicit lock cycle.
- "No deadlock detected" only means **no supported deadlock type was found at measurement time**; it does not prove the app cannot deadlock or is not hung.
- When supported and authorized, `java.lang:type=Threading` under MBeans also exposes `ThreadMXBean` operations/attributes. Operations inspecting locks/stacks can scale in cost with thread count.

### 6.3 Java 21 virtual threads: a critical limitation

`ThreadMXBean` in Java SE 21 **supports platform threads and does not manage or monitor virtual threads in the same way**. Because JConsole's Threads tab relies primarily on `ThreadMXBean`, never use that tab's thread count to conclude "the app has exactly n virtual threads" or "no virtual threads are blocked."

If a service uses virtual threads, use JDK-appropriate tools/recordings such as JFR events, especially when suspecting pinning, blocking, or large numbers of parked virtual threads. Always interpret data **strictly within the scope supported by the source**, without over-extrapolating.

### 6.4 When is the Threads tab useful?

- Thread count climbs steadily over time, suggesting unreleased threads.
- Many requests stall on the same monitor/lock with similar stacks.
- Thread pool starvation: workers blocked on downstream calls while queues grow.
- Checking for deadlocks across Java monitors/ownable synchronizers.
- Inspecting a thread's stack shape before deciding whether deeper thread dumps/JFR are warranted.

JConsole does not provide a **full statistical CPU profile** across all methods; for hotspots, use a profiler or JFR CPU sampling.

## 7. Classes: class loading and potential classloader leaks

The **Classes** tab reports:

- **Current loaded:** number of classes currently held loaded by the JVM.
- **Total loaded:** cumulative classes loaded since VM startup, including later unloaded ones.
- **Total unloaded:** cumulative classes unloaded since VM startup.

The chart usually separates **total loaded** from **current loaded** over time. Total loaded is a cumulative counter so it rarely decreases, even when many classes unload; current loaded can rise and fall. Never mistake rising total loaded for a "classloader leak."

In environments with plugin hot-reload, reflection/proxies, bytecode generation, or app server redeploys:

1. Observe current class count across cycles with matching workloads.
2. Correlate with the Metaspace pool, GC/class unloading events, and classloader lifecycles.
3. Note exactly when redeploys or new modules/plugins occurred.
4. Only if current classes and Metaspace keep climbing across multiple cycles is there a signal for deeper investigation—**still not proof of a leak on its own**.

JConsole includes a **Verbose** control to toggle class loading output on some VMs. This is a **state-changing logging action** on the JVM that can increase output and overhead; never turn it on merely while observing. Class counts rising during warm-up can be completely normal.

## 8. VM Summary: knowing which JVM you are inspecting

The **VM Summary** tab provides context missing from individual charts: runtime/VM version, uptime, process CPU time, classpath, library path, JVM input arguments, and threads/classes/GC/OS summaries (exact visibility varies by JVM).

Useful fields:

| Field | Purpose | Notes |
| --- | --- | --- |
| JVM/version/uptime | Confirm exact instance and process lifecycle | Uptime resets on restart; PID may change or be reused |
| VM arguments | Inspect input arguments reported by the VM | May contain `-Dpassword`/tokens; not equivalent to all app args |
| Heap/GC information | Cross-check against Memory tab | Snapshot figures may differ due to sampling timing |
| Threads/classes | Status summary | Does not replace detailed tabs |
| Process CPU time | Total CPU time consumed since JVM startup | **Not** "current CPU usage" without computing delta/interval |
| Classpath/library path | Locate artifact/dependency paths | Can expose filesystem layout; does not guarantee exact repo code version |
| OS information | Check CPU/RAM/OS context | Does not replace container limits or native process metrics |

JConsole shows input arguments but does not automatically list all **effective VM flags** altered by ergonomics, container constraints, or runtime tuning. To distinguish explicit `-Xmx` from effective `MaxHeapSize`, check `jcmd <PID> VM.command_line` and `VM.flags` when authorized.

Potentially sensitive fields include command line, JVM properties, file paths, and classpath. Review before capturing screenshots or exporting CSVs; never publish raw arguments containing secrets.

## 9. MBeans: viewing attributes, invoking operations, and receiving notifications

This is the core of **JVM management**. The **MBeans** tab accesses MBeans registered in the platform MBeanServer. Each MBean typically exposes:

- **ObjectName:** JMX identifier with domain and key properties, such as `java.lang:type=Memory` or `demo.jmx:type=LabControl`.
- **Attributes:** values or configuration; may be **read-only**, **write-only**, or **read-write** depending on the MBean.
- **Operations:** methods invocable via JMX; may be read-only lookups or mutate state/perform I/O.
- **Notifications:** events from certain MBeans that clients can subscribe to.
- **MBeanInfo/Descriptor:** metadata on names, data types, parameters, descriptions, and capabilities.

This tab does not contain only platform MXBeans; custom MBeans registered by applications/libraries also appear. MBeans can appear or disappear as application components change lifecycle.

### 9.1 Reading ObjectNames and the MBeans tree

Common examples on Java 17+/21:

| ObjectName / pattern | Role |
| --- | --- |
| `java.lang:type=Memory` | Heap/non-heap usage, GC verbosity, memory notifications, and related |
| `java.lang:type=Threading` | Platform thread counts, CPU time/stack/lock operations where supported |
| `java.lang:type=ClassLoading` | Loaded/unloaded classes and verbose class loading |
| `java.lang:type=Runtime` | VM name/vendor/version, uptime, input arguments |
| `java.lang:type=OperatingSystem` | OS/process counters per Java Management API |
| `java.lang:type=MemoryPool,name=...` | Current/peak/collection usage and per-pool thresholds |
| `java.lang:type=GarbageCollector,name=...` | Collection count/time and GC pools |
| `com.sun.management:type=HotSpotDiagnostic` | HotSpot-specific diagnostics, including heap dump / VM options |
| `demo.jmx:type=LabControl` | Custom MBean from the hands-on lab below |

Patterns with `...` are **illustrative**: actual names depend on the VM, collector, and application libraries. Never assume every MBean or operation exists on OpenJ9, different HotSpot versions, stripped-down runtime images, or custom MBean servers.

JConsole groups the tree by ObjectName; key properties affect tree layout, so identify beans by their full name and domain rather than visual position alone.

### 9.2 Attributes: how reading and writing differ

Select **MBeans → java.lang → type=Memory → Attributes → HeapMemoryUsage** (exact path labels may vary slightly by UI). This attribute is a composite with `init, used, committed, max`; expanding it shows current JVM values. On numeric attributes, JConsole often allows opening a **chart** by double-clicking; values update as the tool polls.

Per JDK 21 documentation, **writable attributes** may render values in blue in JConsole. For example, `Verbose` on Memory/ClassLoading can be edited in the GUI — yet doing so **invokes the MBean setter** and alters JVM logging. Never treat "just editing a field in the GUI" as harmless.

Attribute properties:

| Attribute | Type | Action |
| --- | --- | --- |
| `HeapMemoryUsage` | Read-only composite data | Read and observe; do not modify |
| `ThreadCount` | Read-only numeric | Read/observe |
| `Verbose` | Writable boolean on supporting MBeans | Sets value and alters tracing/logging |
| Custom `Counter` | Numeric getter in demo | Read, can be charted |
| Custom `Ready` | Boolean getter + setter in demo | Read and mutates demo state |

**Never assume an attribute looks "harmless" and invoke its setter in production.** Even when MBean metadata marks an attribute writable and you have permission, understand the side effects from the MBean's own contract first.

### 9.3 Operations: buttons can invoke real code

In the MBean tree, select **Operations** to view registered methods. JConsole renders buttons for each operation and its parameters; clicking one **invokes the method inside the target JVM** via JMX.

Distinguish:

- Getter-like operations: may return current info yet still incur overhead.
- Mutation/maintenance: e.g., `resetCounter`, `setVMOption`, enabling tracing, clearing caches; can alter business behavior.
- Heap dump: `com.sun.management:type=HotSpotDiagnostic` offers `dumpHeap` on HotSpot; invoking it can create large files, trigger pauses, and expose sensitive heap contents.
- GC operation: equivalent to asking the JVM to run GC, not a read operation.
- Custom MBean operations: **contract defined by the application**; JConsole cannot guarantee they are idempotent, fast, thread-safe, or safe.

MBean metadata may display an operation "impact" such as `INFO`, `ACTION`, `ACTION_INFO`, or `UNKNOWN`, which **does not replace analyzing actual impact** and policy. An MBean might misdeclare metadata or perform I/O/blocking inside the method; never click just to "see what it does."

### 9.4 Notifications: an event channel from MBeans

MBeans can emit JMX notifications. In the MBeans tab, open **Notifications** and click **Subscribe** if supported and permitted. This is a live session event feed inside JConsole, not a replacement for full alert history or a message queue.

For instance, `MemoryMXBean` can emit notifications when the JVM detects a **memory usage threshold** or **collection usage threshold** crossing on supported pools. If thresholds are not configured, seeing zero notifications **does not prove** memory never spiked high.

Notes:

- Subscribing keeps a listener active for the JMX session; check lifecycle/unsubscribe as needed.
- Notification counts are not failed request counts or allocated byte counts.
- An MBean notification arrives when the JVM detects the condition, not necessarily at the exact timestamp of every allocation.
- In production, a dedicated alerting system with retention and policy is far more reliable than leaving a JConsole window open continuously.

## 10. Action classification table: observation, light management, and risky actions

| JConsole action | Nature | Recommended handling |
| --- | --- | --- |
| View Overview, Memory, Threads, Classes | Mostly read-only | Permitted with monitoring access; consider polling overhead |
| View VM Summary | Read-only, may expose args/paths | Capture/share redacted versions only |
| View read-only attributes | Read-only | Verify scope/units/timestamps and permissions |
| Chart a numeric attribute | Continuous polling/reading | Limit frequency and number of polled attributes |
| Detect Deadlock | Invokes diagnostic lock-cycle check | Use only when needed; avoid frequent repetition |
| Subscribe notifications | Registers listener | Understand lifecycle and event semantics |
| Write `Verbose` attribute | **Changes tracing configuration** | Needs approval/rollback and log-cost check |
| Invoke demo `incrementCounter` operation | Mutates **lab JVM** state | Use in lab; never apply blindly to production MBeans with unclear contracts |
| Perform GC | **Requests GC** | Never invoke casually in production |
| `dumpHeap` or heavy diagnostic operations | **Heavy I/O/disk/memory**, possible pause | Plan impact, disk space, permissions, and artifact security |
| `setVMOption` or control operations | **Alters VM/app state** | Execute only under approved change/incident procedures |

An operational rule with lasting value: **opening a tab to look does not grant permission to press every button**. JMX calls travel over the wire but execute inside the target JVM; consequences can directly hit latency, throughput, logging, memory, or application consistency.

## 11. Java 17+ hands-on lab: creating an MBean to read, write, and invoke operations

This lab uses **a standalone lab JVM**, requires no remote JMX, and never touches any real application. We create a **Standard MBean** named `demo.jmx:type=LabControl` with:

- `Counter` attribute (**read-only**): starts at 0.
- `Ready` attribute (**read-write**): starts as `true`; changing it affects only the demo variable.
- `ping()` operation (**no state change**): returns `"pong"`.
- `incrementCounter()` operation (**mutates state**): increments the counter and returns the new value.
- `resetCounter()` operation (**mutates state**): resets the counter to 0.

### 11.1 Complete, compilable code

Create **`JConsoleLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class JConsoleLab {

    // Nested public interface is the MBean's standard management interface.
    public interface LabControlMBean {
        long getCounter();
        boolean isReady();
        void setReady(boolean ready);
        String ping();
        long incrementCounter();
        void resetCounter();
    }

    public static final class LabControl implements LabControlMBean {
        private final AtomicLong counter = new AtomicLong();
        private volatile boolean ready = true;

        @Override
        public long getCounter() {
            return counter.get();
        }

        @Override
        public boolean isReady() {
            return ready;
        }

        @Override
        public void setReady(boolean ready) {
            this.ready = ready;
        }

        @Override
        public String ping() {
            return "pong";
        }

        @Override
        public long incrementCounter() {
            return counter.incrementAndGet();
        }

        @Override
        public void resetCounter() {
            counter.set(0L);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("demo.jmx:type=LabControl");

        LabControl lab = new LabControl();
        server.registerMBean(
                new StandardMBean(lab, LabControlMBean.class), name);

        System.out.println("JConsoleLab READY");
        System.out.println("MBean=demo.jmx:type=LabControl");
        System.out.println("PID=" + ProcessHandle.current().pid());

        // Keep process alive to open JConsole GUI in another terminal.
        Thread.sleep(120_000L);
        System.out.println("JConsoleLab DONE");
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac JConsoleLab.java
java JConsoleLab
```

**First two stdout lines are exact across OS/JVMs:**

```text
JConsoleLab READY
MBean=demo.jmx:type=LabControl
```

The next line is `PID=<actual-value>`, machine-dependent. After roughly 120 seconds, the program prints `JConsoleLab DONE` and exits. If you take too long launching JConsole, restart the **lab JVM**; never assume an exited PID remains valid. On JDK 17+/21, a successful `javac` typically prints nothing; that is not an error.

### 11.2 Why use StandardMBean?

`LabControlMBean` is a **public** interface declaring the JMX contract. Class `LabControl` implements that contract. `StandardMBean` registers the implementation against the specified interface, avoiding hand-written MBean metadata. The bean is registered on the **platform MBeanServer**, so local JConsole finds it in the MBeans tab once connected to the right process.

The program uses:

- `AtomicLong` to increment/reset the counter safely under concurrent JMX client calls.
- `volatile boolean` so `Ready` getter/setter updates are visible across threads; in the demo, changing `Ready` **does not shut down a service, pause workers, or control the JVM runtime**.
- `Thread.sleep` solely to keep the JVM alive long enough for the lab—not to suggest JMX blocks applications for 120 seconds.
- `ProcessHandle.current().pid()` to print the **demo JVM's own** PID, not a PID from another machine.

JConsole or JMX can call getters frequently to plot charts; custom MBean getters should be **fast, safe, and free of significant side effects**. Never put expensive DB queries or blocking network I/O inside `getCounter()`.

### 11.3 Connecting to the right demo JVM

Open JConsole in another terminal on the same machine under the same user:

```bash
jconsole
```

In the Local Process dialog, pick `JConsoleLab` matching the PID printed by the demo; or:

```bash
# Replace 12345 with the real PID printed in JConsoleLab's terminal.
jconsole 12345
```

GUI walkthrough order:

1. Connect to the demo JVM and open **VM Summary**; confirm uptime/process context.
2. Open **Overview** to view charts; because the demo is nearly idle, expect low CPU and steady memory.
3. Open **MBeans**, locate domain `demo.jmx` and ObjectName `type=LabControl`.
4. Select **Attributes**: read `Counter = 0` and `Ready = true` before using operations.
5. Try double-clicking the numeric `Counter` value to open a chart (if supported for that type/view in the GUI).
6. Select **Operations → ping** and invoke; expected result is `"pong"`.
7. Select **Operations → incrementCounter** and invoke once; expected return value is **1**, and `Counter` after refresh is **1**.
8. Invoke `incrementCounter` once more; expected return value is **2**, and `Counter` after refresh is **2**.
9. Change `Ready` to `false` under **writable attributes** if GUI and permissions permit; refresh to verify state. This only changes the lab flag.
10. Invoke `resetCounter`; after refresh, `Counter` returns to **0**.
11. There is no need to test `Perform GC` or `HotSpotDiagnostic.dumpHeap` to prove the custom MBean works.

Attribute/operation display order in the GUI may vary, and chart values update only when JConsole polls. The 0→1→2→0 expectations hold **provided only one person interacts with this demo JVM** and no other client invokes operations concurrently.

### 11.4 Differences between read-only, writable, and operation

| Demo member | Mechanism | Impact |
| --- | --- | --- |
| `getCounter()` | Getter → attribute `Counter` | Reads atomic counter only |
| `isReady()` | Boolean getter → attribute `Ready` | Reads state only |
| `setReady(boolean)` | Setter → writes attribute `Ready` | Mutates state in demo JVM |
| `ping()` | MBean operation | Returns `pong`; leaves counter/state unchanged |
| `incrementCounter()` | MBean operation | **Increments Counter** |
| `resetCounter()` | MBean operation | **Resets Counter** |

Invoking setters/operations via JMX executes **real actions**, not simulated JConsole interactions. In real systems, custom MBeans can drain queues, rotate secrets, clear caches, reload configs, or shut down services; never invoke without understanding the contract and authorization.

### 11.5 Stopping the lab safely

Before 120 seconds elapse, return to the lab JVM terminal and press Ctrl+C to exit. JConsole may report a lost connection, which is expected when the target process terminates. On restart, the JVM gets a **new PID or a reused PID**, and the custom MBean/Counter returns to its initial state.

Do not assume JConsole "reset the counter on its own" when seeing 2 drop back to 0 if you actually connected to a **new JVM session**.

## 12. Interpreting three realistic scenarios

### 12.1 Memory chart climbing continuously: leak or workload?

Suppose Overview/Memory shows heap used rising 200→700 MiB over 20 minutes with a 1 GiB max. This is **illustrative data**, not proof of a leak yet.

Steps:

1. Verify same PID/uptime, time range, and GC collector.
2. Watch GC cycles: does `used` drop after GC, and is the post-GC baseline climbing steadily?
3. Check heap committed/max and container memory limits; never confuse committed with used or RSS.
4. Correlate request mix, throughput, caches, batch jobs, and JFR allocation/GC events.
5. If retained references are suspected, plan heap analysis/dumps with an overhead budget and data protection.
6. Never use **Perform GC** to alter measurements while trying to observe natural behavior.

The cause might be normal allocation churn, cache warm-up, long-lived objects, classloader issues, or a leak; JConsole **points toward hypotheses** rather than proving root cause alone.

### 12.2 Rising threads and high p99 latency

When the Threads chart climbs, inspect thread lists/stacks; look for workers waiting on locks, downstream calls, or queues; run Detect Deadlock if there is evidence of Java lock cycles.

Do not conclude a deadlock exists just because thread count rose. Thread pools scale with load; `WAITING` threads may simply be idle; high p99 may stem from DB/network timeouts invisible to Java Deadlock Detection. Capture multiple snapshots over time and correlate with service metrics, thread pool queues, and distributed traces.

If the JVM uses **virtual threads**, remember Java 21 `ThreadMXBean` does not fully reflect them: the JConsole Threads chart shows only part of the picture, not all logical tasks.

### 12.3 Current classes and Metaspace climbing across redeploys

Open the Classes tab and the Metaspace Memory pool:

1. Record current loaded, total loaded, total unloaded, and Metaspace usage.
2. Correlate timestamps of reloads/deploys, plugin generation, and GC/class unloading.
3. When total loaded grows while current stays flat, classes are likely unloading properly.
4. If current loaded and Metaspace keep climbing across multiple similar cycles, investigate classloader retention or dynamic code generation.
5. Never enable verbose class loading from JConsole just to "test" in production, as it increases logging and alters overhead.

## 13. Troubleshooting JConsole connections by root cause

| Symptom | Likely causes | How to verify |
| --- | --- | --- |
| JVM missing from Local Process list | Different user, namespace/container, non-attachable JVM, process exited | Check PID/start time, OS permissions, JDK/attach policy |
| "Connection failed" with PID | Wrong PID, JVM restarted, permission denied, or attach disabled | Check target, user, and logs; never escalate privileges to bypass policy |
| Remote host:port reachable yet JConsole hangs | RMI stub returns another host/port, firewall/NAT, TLS/certificate | Check connector/server port and advertised hostname, admin network |
| Authentication rejected | Wrong credentials/role, access file, TLS settings | Use official credential provisioning; never disable auth/SSL |
| Custom MBean missing in MBeans tab | Wrong JVM connected, bean unregistered, different MBeanServer, lifecycle bug | Verify ObjectName and platform registration in app |
| Attribute/operation reports permission denied | Read-only role, access control, or MBean policy | Use only granted permissions; never bypass |
| Chart stays flat | JVM idle, not yet refreshed, unsupported series, wrong scope | Check timestamps, raw attributes, and workload |
| Chart history lost after reconnect | New JConsole session holds only current session/buffer samples | Use metrics/recording systems designed for retention |
| GUI fails to launch | JDK lacks `jconsole` or no display server | Run GUI client on an appropriate workstation per policy |

A remote JMX issue **must never be "fixed" by adding `authenticate=false`/`ssl=false`** in production. Fix TLS, role permissions, RMI ports, hostnames, and admin network routing properly instead.

## 14. Overhead and limitations of JConsole

### 14.1 Polling carries cost

JConsole polls getters periodically to render charts; depending on attribute count, custom MBean complexity, and network paths, it can increase CPU, heap allocations, safepoint/management activity, or network traffic. A custom getter scanning a million-item cache can cost orders of magnitude more than a simple platform getter.

If CPU rises after opening JConsole, do not automatically blame application workload. Compare baselines, review invoked operations, and check which attributes are being polled for charts.

### 14.2 Not a replacement for long-term telemetry

- Overview charts reflect only the GUI window, not multi-day monitoring retention.
- JConsole does not provide cross-service distributed traces.
- CPU/Memory charts do not replace CPU flamegraphs, allocation profilers, or heap object graphs.
- JVM memory does not cover all native memory or full process RSS.
- A CSV from one chart is not an atomic consistent snapshot across all MBeans.
- A JMX read-only role is not "zero overhead"; getters can still perform computation.
- JConsole GUI version and target VM version may differ; if an operation is missing, check the target VM's contract.

### 14.3 Balancing GUI interaction and automation

JConsole excels at **interactive exploration, hands-on learning, and inspecting a single process**. For continuous monitoring and alerting, use metrics/exporters or retention-backed observability stacks. For production incident deep dives, JFR/thread dumps/GC logs may be more suitable depending on the question.

Never write "Observed at 10:00" from JConsole and extrapolate "it has been like this for the past 24 hours." Report only the window where data was actually observed.

## 15. Controlled JConsole operating workflow

### Step 1: Verify authorization and target

Record:

- Service and environment, host/node/container/pod.
- PID and process start time, Java version/vendor, application/build.
- Operator, purpose, incident/ticket, JMX role permissions.
- Are operations/attribute writes permitted, or monitoring only?

If using a remote connection, confirm secure network/TLS, RMI hostname/ports, and authorization. Never publish credentials in notes.

### Step 2: Gather context from VM Summary

Read uptime/version/arguments for the exact PID and record UTC timestamps. Redact paths/tokens before sharing. If you notice you connected to the wrong JVM, disconnect immediately; do not read or write MBeans on another process.

### Step 3: Observe Overview, then target tabs by symptom

- Memory pressure → Memory; distinguish heap/non-heap and pools, GC times, used/committed/max.
- Thread stall → Threads, multiple snapshots and deadlock detection when appropriate.
- Classloader/metaspace → Classes + Memory pools.
- Custom application state → MBeans → ObjectName/Attributes, read-only first.
- Cross-team correlation → align time windows and export CSV/metrics when authorized.

### Step 4: Before invoking a setter or operation

Answer completely:

1. What does this attribute/operation **change inside the JVM/app**?
2. What side effects, concurrency behavior, and permissions are documented by the MBean owner?
3. Can it trigger pauses, run GC, dump large files, clear caches, lose data, or spike logs?
4. Are there stop conditions, rollback steps, and a way to measure post-change impact?
5. Is this production, multi-replica, or sensitive data?
6. Is there formal operational approval?

If any answer is unknown, **do not invoke it**. Inspect MBean metadata and contact the owner instead of clicking blindly.

### Step 5: Collect evidence and exit the session

Save chart CSVs/screenshots if policy allows, labeled with timestamps, units, time range, PID/start time, and target. Never leave GUIs or remote JMX sessions open unattended; disconnect and manage sessions/credentials per policy. Store or delete any recordings/heap artifacts created by operations according to retention and access controls.

### Step 6: State bounded conclusions

**Illustrative** record example:

```yaml
captureTimeUtc: "2026-10-29T08:30:00Z"
service: "inventory-api"
instance: "inventory-2"
processId: 12345
jvmUptimeSeconds: 3600
connection: "secured remote JMX"
observations:
  heapUsedMiB: 300
  heapCommittedMiB: 600
  heapMaxMiB: 1200
  livePlatformThreads: 64
  loadedClasses: 8600
  deadlockDetection: "no supported deadlock detected at capture"
actions:
  - "read Overview/Memory/Threads/VM Summary"
  - "read MBean attributes"
mutationsPerformed: false
limitations:
  - "No JFR CPU profile"
  - "Data available only during observed time window"
```

Numbers and names in the sample are **fictional**. Fill in only actually observed values and never insert sensitive secrets. `deadlockDetection` explicitly scopes to "supported types at capture time," never claiming the entire program can never deadlock.

## 16. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "JConsole is just for viewing; clicking buttons is harmless." | Writable attributes and operations execute directly inside the target JVM. |
| "Local JVM attach always works with zero setup." | Depends on user/permissions, namespaces, attach policy, runtime, and platform. |
| "Enabling remote JMX only needs opening one port." | RMI involves registry, connector port, stub hostname, firewalls, and TLS/auth. |
| "Disable JMX auth to troubleshoot production faster." | Risks unauthorized access and mutation; maintain security and role separation. |
| "The CPU chart reveals which class/method is slow." | Requires profiler/JFR CPU samples and workload context. |
| "Rising memory used means a leak." | May be allocation churn, cache/warm-up, or GC policy; requires post-GC trend and retained references. |
| "Committed heap equals RSS." | Committed heap differs from physical resident/process memory. |
| "Perform GC only refreshes the chart." | Triggers a garbage collection request and can alter state and latency. |
| "Java 21 ThreadCount includes all virtual threads." | `ThreadMXBean` monitors platform threads only per the JDK 21 contract. |
| "Detect Deadlock finding nothing means nothing is stuck." | Checks only supported deadlock types at that instant. |
| "Total loaded classes rising always means a classloader leak." | Total loaded is cumulative; inspect current, unloaded, Metaspace, and context. |
| "A writable MBean attribute is just a GUI text box." | Writing a value invokes the setter inside the process. |
| "An MBean operation named `ping` is guaranteed side-effect-free." | For custom MBeans, verify the owner's contract/code; names do not guarantee safety. |
| "Exported chart CSV includes data from before JConsole opened." | CSV exports only chart samples held in the active session/buffer. |
| "A demo JVM proves production JVM behavior." | Always collect data from the exact target PID/instance/runtime. |
| "JConsole always shows old PermGen memory pools." | Pool names vary by GC/JDK; Java 17/21 do not use PermGen like Java 7 did. |
| "A read-only JMX role has zero overhead." | Getters and polling still consume resources, especially unoptimized custom MBeans. |

## 17. Self-check questions

**Question 1.** You connect JConsole to a JVM and see CPU and heap used rising together. Is that enough to conclude a memory leak is causing high CPU?

**Answer:** Not yet. That is temporal correlation; you need GC/CPU sampling, allocation rates, workload data, and retained-object evidence. Two charts alone do not prove a causal chain.

**Question 2.** Under MBeans, `HeapMemoryUsage` shows `used=300`, `committed=600`, `max=1200` MiB. What are used/max and used/committed?

**Answer:** **25%** and **50%**. The two ratios measure against different capacities; never change labels without tracking the denominator.

**Question 3.** An observer wants to "clean the heap before looking at the chart" by clicking `Perform GC`. Can this be considered read-only?

**Answer:** No. It requests GC, can impact the service, and alters the very state under measurement. In real environments, intervention requires approval procedures.

**Question 4.** In the demo, `Counter` is read as an attribute, `incrementCounter()` is invoked as an operation, and `Ready` is edited via setter. How do the three differ?

**Answer:** Reading `Counter` does not mutate state; `incrementCounter` increments state; writing `Ready` invokes the setter and flips the flag in the demo process. The latter two are mutations.

**Question 5.** `Detect Deadlock` finds nothing, yet requests remain hung. Is that a contradiction?

**Answer:** No. Requests may be stalled on I/O, starvation, external database locks, or wait patterns that do not form a deadlock cycle checkable by JConsole.

**Question 6.** A Java 21 app spawns 100,000 virtual threads, yet the Threads tab does not show that number. Why?

**Answer:** JDK 21 `ThreadMXBean` does not monitor virtual threads the same way as platform threads. Use JFR or virtual-thread-aware tools to evaluate them.

**Question 7.** A remote JMX connection requires login, and an operator wants to set `authenticate=false` and `ssl=false` to connect from a laptop. Should they?

**Answer:** Never in production. JMX exposes operations and writable state and requires authentication, TLS, role separation, and network restrictions. Fix credentials, RMI, and SSL properly.

**Question 8.** JConsole is charting the demo's `Counter`, and you invoke `incrementCounter` twice. The chart does not update immediately. Does that prove the operation failed?

**Answer:** Not yet. Polling intervals, refresh timing, and chart selection can delay visual updates. Verify the operation's return value and re-read raw `Counter`.

**Question 9.** Why is VM Summary not conclusive proof of all effective flags and application parameters?

**Answer:** VM input arguments differ from application arguments and from VM flags adjusted automatically by ergonomics; `jcmd`/JVM APIs, deployment configs, and runtime state may be needed.

**Question 10.** A custom MBean exposes a `clearCache` operation. When is it appropriate to invoke it?

**Answer:** Only when you understand its contract and side effects, blast radius, concurrency/rollback behavior, and hold proper operational authorization. Never click it just to test if the GUI works.

## 18. End-of-lesson practical checklist

- Verified exact **JVM/PID/start time**, Java version, and connection permissions.
- Used matching user/namespace for local attach; enforced TLS, authentication, authorization, and network limits for remote JMX.
- Know all six tabs: **Overview, Memory, Threads, Classes, VM Summary, MBeans**.
- Distinguished **used/committed/max**, current/peak threads, loaded/current classes, and cumulative metrics.
- Never confuse JConsole charts with a profiler or long-term historical storage.
- Under MBeans, identified **ObjectName**, **read-only/writable attributes**, **operations**, **notifications**, and metadata.
- Treated every writable attribute, GC trigger, heap dump, or custom operation as a **state change** until side effects are verified.
- Ran `JConsoleLab.java`, located `demo.jmx:type=LabControl`, read `Counter`/`Ready`, and invoked `ping`/`incrementCounter`/`resetCounter`.
- Recorded timestamps, scope, units, source, window, and measurement limitations; protected sensitive data before exporting screenshots/CSVs.
- Used JFR, GC logs, thread dumps, and metrics/tracing when depth or timelines exceed JConsole's scope.

**Conclusion:** JConsole lets you "see inside the JVM" through charts and MBeans, while also serving as a **control tool** that can directly impact the application. The safe workflow is **verify the exact process → observe first → understand MBean contracts → perform only authorized actions → verify impact and archive context-rich evidence**.

### Official references

- [Oracle JDK 21 — Using JConsole](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html): launching JConsole, local/remote connections, six tabs, chart CSV export, attributes, operations, and notifications.
- [Oracle JDK 21 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html): management agent, remote RMI ports/hostname, authentication, TLS, and role access.
- [Oracle JDK 21 — The jconsole Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html): launcher command, `-J` options, and invocation syntax.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): managing platform threads and virtual thread limitations.
- [Java SE 21 — MBeanServer](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html): registering, querying, reading, setting, and invoking MBeans in a server.
- [Java SE 21 — StandardMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html): registering a Standard MBean via its management interface.
- [Java SE 21 — MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): semantics of init/used/committed/max.