# JFR, JMX, and monitoring tool compatibility

In **Java Advance Compatibility Migration**, upgrading the JDK does more than alter bytecode, libraries, and application behavior. It can also change **what monitoring systems observe**: garbage collector names, MBean sets, JMX attributes, JFR event types, measurement units, how tools attach to the JVM, or how the JVM detects container CPU and memory.

This lesson belongs to the **JVM and performance** chapter. Its goal is understanding Java's two major observability mechanisms—**Java Flight Recorder (JFR)** and **Java Management Extensions (JMX)**—and designing a migration workflow so dashboards, alerts, profilers, and operational tools keep producing accurate conclusions after the runtime changes.

An especially dangerous failure is not the application crashing, but **the application staying up while monitoring goes blind**: an exporter stops reading an MBean, alerts lose data, dashboards display 0 instead of missing, or the same metric name quietly shifts meaning after switching GC.

Examples focus on modern Java applications and common HotSpot deployments. **Availability, event metadata, extended MXBeans, and per-command capabilities depend on JDK vendor, release, image, and runtime config.** In real deployments, verify against the exact artifact running in production.

## 1. JFR, JMX, and distinct observability layers

### 1.1. JMX: live state and management operations

**Java Management Extensions (JMX)** provides infrastructure for programs and administrative tools to inspect or interact with runtime components via **MBeans**.

Commonly exposed data includes:

- Heap and non-heap memory usage.
- Thread counts and select thread CPU statistics.
- Garbage collection statistics.
- Class loading.
- Compilation and memory pools.
- Custom application configuration attributes exposed by developers.
- Administrative operations such as toggling a feature, if exposed by an MBean and permitted by access controls.

JMX is well suited for **periodic sampling of state or counters**, such as every 15 or 30 seconds.

### 1.2. JFR: event streams and time-ordered diagnostic data

**Java Flight Recorder (JFR)** is an event-recording technology whose overhead is designed to suit many live-production recording scenarios, depending on configuration and event frequency.

Example events:

- A garbage collection cycle executing.
- Object allocation activity.
- CPU execution samples.
- Threads blocked entering monitors.
- File or socket reads/writes.
- Class loading or JIT code compilation.
- Custom application-defined events.

JFR answers **what happened over a time interval**, rather than showing only a heap snapshot sampled at one point in time.

### 1.3. Monitoring, profiling, and tracing are different

| Need | JMX | JFR | Other mechanisms |
|---|---|---|---|
| Reading heap usage periodically | Suitable | Possible via events | Metrics exporter |
| Tracking GC count/time | Commonly uses MXBeans | Detailed GC events | GC logs |
| Analyzing CPU hotspots | Not its primary purpose | Execution samples | Async profiler |
| End-to-end latency analysis | Limited | Supporting events, needs context | Distributed tracing |
| Periodic threshold alerting | Suitable via exporter | Needs event-to-metric pipeline | Prometheus/OTel |
| Post-mortem incident investigation | Only if metrics were stored | Recording holds detailed timeline | Logs/traces |
| Runtime management via MBeans | Supported | Not its primary purpose | Management API |
| Profiling with stack traces | Limited | Can capture stack traces per event | Profiling tools |

A strong observability architecture combines multiple sources rather than forcing JFR to replace JMX or vice versa.

### 1.4. Overall architecture diagram

~~~text
Java application + JVM
       |
       +--> JMX / MXBeans --> JMX Exporter --> Time-series DB --> Dashboard/Alert
       |
       +--> JFR events ----> .jfr recording --> JMC / jfr CLI / analysis
       |              |
       |              +--> RecordingStream --> observability pipeline
       |
       +--> Application metrics --> Micrometer / OpenTelemetry --> Backend
       |
       +--> GC logs / application logs ------------------------> Log storage
       |
       +--> Distributed traces -------------------------------> Trace backend
~~~

Data from these branches complement each other during investigations, yet **measurements should never be assumed completely equivalent**. For instance, GC time from JMX and the summed duration of JFR events may differ in scope, calculation, and update timing.

## 2. What can change when upgrading the JDK?

A migration can alter several layers at once:

1. JDK runtime and vendor.
2. GC algorithm or default GC selection.
3. Heap layout, memory pools, and GC MBean naming.
4. JFR events, metadata, settings, and recording availability.
5. Command-line syntax or diagnostic tools shipped in the JDK image.
6. Module availability when building with **jlink**.
7. Security, attach, RMI, or network configurations.
8. Container CPU/memory accounting.
9. Versions of JMX exporters, JMC, profilers, Java agents, and dependencies.
10. Metric names/labels emitted by exporters.
11. Dashboards and alerts tied directly to old names/units.
12. Startup time and instrumentation overhead.

### 2.1. Risk matrix

| Change | Impact on monitoring | Verification direction |
|---|---|---|
| Changing JDK/HotSpot build | Events/attributes and runtime flags may differ | Compare discovery across both runtimes |
| Switching GC from G1 to ZGC | GC MBeans, events, and semantics change | Avoid hardcoding collector names |
| Using minimal jlink images | Missing modules/tools needed by JFR or JMX | Inspect module graph/runtime image |
| Deploying in containers | PID namespaces, cgroup metrics, file paths differ | Test on real image and orchestrator |
| Tightening security | Remote JMX or attach may be blocked | Authenticate and test access permissions |
| Upgrading exporters/agents | Metric names, labels, and mapping rules change | Diff scrape output before/after |
| Dashboard changes | Queries stop matching series | Test panels, rules, and absence detection |
| Enabling continuous JFR profiling | Overhead/disk volume rises depending on events | Measure under representative load |
| Changing sampling intervals | Alert rates and sensitivity shift | Check sampling steps and evaluation windows |

What matters is not preserving every internal JVM detail, but keeping **the operational signals your system relies on to detect incidents**.

## 3. JFR: architecture and core concepts

JFR is an event-recording engine integrated with HotSpot. Since **JDK 11**, JFR has been available in OpenJDK under **JEP 328**. Other releases and runtimes may provide varying levels of support; verify against your running JDK.

Key concepts:

- **Event:** a recorded piece of telemetry, such as jdk.GarbageCollection.
- **Event type:** name, fields, annotations, category, and metadata describing an event.
- **Recording:** a capture session with configuration, start/end timestamps, and recorded data.
- **Settings:** configuration controlling enabled events, duration thresholds, periods, or stack traces.
- **.jfr file:** output recording artifact for analysis.
- **JDK Mission Control (JMC):** GUI tool commonly used to analyze recordings.
- **jfr CLI:** command-line tool to view summaries, print events, and inspect metadata.
- **RecordingStream:** API enabling consumption of selected JFR events emitted live by the JVM.

### 3.1. Event classification

| Telemetry area | Illustrative event | Purpose |
|---|---|---|
| JVM CPU | **jdk.CPULoad** | Inspects CPU load over time |
| GC | **jdk.GarbageCollection** | Identifies GC activity |
| Heap | **jdk.GCHeapSummary** | Analyzes heap state at relevant checkpoints |
| Execution sampling | **jdk.ExecutionSample** | Locates CPU-heavy code paths via sampling |
| Allocation | **jdk.ObjectAllocationSample** | Observes object allocation trends |
| Synchronization | **jdk.JavaMonitorEnter** | Investigates monitor lock wait times |
| File I/O | Runtime-supported file read/write events | Inspects I/O latency and transfer sizes |
| Socket I/O | Runtime-supported socket read/write events | Investigates network operations |

Event names in the table illustrate common HotSpot events. **Never hardcode this list while ignoring target runtime metadata.** Events can change default enabled state, fields, subtypes, or availability across JDKs/vendors.

### 3.2. Recording is not necessarily full-force profiling

JFR collects varied telemetry at different costs. Some events record infrequently or use sampling; others can generate high volume if enabled indiscriminately.

Distinguish:

- **default settings:** generally suited to capturing broad telemetry at lower overhead.
- **profile settings:** enables richer profiling events and can increase overhead.
- **custom settings:** tunes events, periods, thresholds, and stack traces to specific needs.

A short recording with profile settings during incident triage does not mean it is safe to run continuously under all production traffic.

## 4. Using jcmd to record JFR

**jcmd** sends diagnostic commands to HotSpot JVMs when the caller has matching permissions. It normally ships in full JDK distributions; minimal runtime images may omit this executable.

### 4.1. Inspecting processes

~~~bash
jcmd -l
~~~

Returns JVM processes visible and reachable by the tool. Inside containers, PID namespaces and execution privileges can affect visibility.

### 4.2. Starting a recording

~~~bash
jcmd 12345 JFR.start \
  name=migration_check \
  settings=default \
  duration=2m \
  filename=/tmp/migration-check.jfr
~~~

Assumes **12345** is a live PID and the runtime supports these commands. On Windows, pass all arguments on one line.

Parameters:

- **name**: label for managing the recording.
- **settings=default**: selects the default event profile.
- **duration=2m**: caps recording length.
- **filename**: output file path.

The path must be writable inside the process/container filesystem. In orchestrated environments, files can disappear when pods rotate; establish artifact retrieval workflows compliant with security policies.

### 4.3. Checking status and dumping

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=migration_check filename=/tmp/diagnostic.jfr
~~~

**JFR.dump** captures a snapshot from an active recording. If a recording already stopped automatically with a configured output path, retrieve the artifact from that target location.

### 4.4. Stopping a recording

~~~bash
jcmd 12345 JFR.stop name=migration_check
~~~

Do not leave multiple unmonitored profile recordings running on the same process. Log who started it, purpose, duration, expected size cap, and cleanup steps.

### 4.5. Recording from JVM startup

Example JVM option:

~~~bash
java \
  -XX:StartFlightRecording=name=startup,settings=default,duration=120s,filename=/tmp/startup.jfr \
  -jar app.jar
~~~

Useful when observing startup behavior or failures occurring before **jcmd** can attach. Configuration must match your actual Java launcher, container filesystem, and security controls.

## 5. Reading and analyzing recordings with jfr CLI

JFR recordings can be analyzed offline. You do not need to open remote JMX simply to inspect a collected .jfr file.

### 5.1. Recording summary

~~~bash
jfr summary /tmp/migration-check.jfr
~~~

Displays overall info, event types, and recorded event counts.

### 5.2. Filtering specific events

~~~bash
jfr print \
  --events jdk.CPULoad,jdk.GarbageCollection \
  /tmp/migration-check.jfr
~~~

Avoid drawing conclusions from raw event counts alone. Varying GC durations or differing enablement thresholds make naive count comparisons meaningless.

### 5.3. Inspecting metadata

~~~bash
jfr metadata /tmp/migration-check.jfr
~~~

Metadata is vital during migration because it describes **the exact event types and fields present in the actual recording**. When upgrading JDKs, never assume a field read by an older parser keeps the same name and type.

### 5.4. JDK Mission Control (JMC)

JMC provides visual analysis of timelines, threads, GC, allocations, and code execution. JMC has its own releases and compatibility matrix. An older JMC build may not fully parse metadata/event schemas produced by newer JDKs.

During migration:

1. Record which JDK generated the recording.
2. Record which JMC version opens it.
3. Open both baseline and target recordings.
4. Verify key report pages render properly.
5. If UI omits an event, inspect **jfr summary/metadata** before concluding the runtime stopped emitting it.
6. Upgrade JMC to a release supporting the target JDK's recordings when needed.

**Being able to open a .jfr file** does not mean every chart or heuristic inside the UI holds identical meaning across changed collectors or event versions.

## 6. JFR API in Java applications

The JDK provides the **jdk.jfr** API for creating recordings programmatically.

Example:

~~~java
package example.monitoring;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class JfrRecordingExample {
    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.setName("sample");
            recording.enable("jdk.ExecutionSample")
                .withPeriod(Duration.ofMillis(20));

            recording.start();

            runWorkload();

            recording.stop();
            recording.dump(Path.of("sample.jfr"));
        }
    }

    private static void runWorkload() throws InterruptedException {
        Thread.sleep(1_000);
    }
}
~~~

In modular applications, modules using this API must declare a dependency on **jdk.jfr** appropriately:

~~~java
module example.monitoring {
    requires jdk.jfr;
}
~~~

Custom runtime images built with **jlink** might omit this module. You cannot add a Maven dependency to restore a JDK runtime module omitted from the image; adjust runtime packaging instead.

### 6.1. Custom events for business operations

Custom events can capture meaningful domain operations:

~~~java
package example.monitoring;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderProcessed")
@Label("Order Processed")
@Category({"Application", "Orders"})
public final class OrderProcessedEvent extends Event {
    @Label("Status")
    public String status;

    @Label("Item Count")
    public int itemCount;
}
~~~

Usage:

~~~java
public void processOrder() {
    OrderProcessedEvent event = new OrderProcessedEvent();
    event.begin();
    try {
        // Execute business logic.
        event.status = "SUCCESS";
        event.itemCount = 3;
    } catch (RuntimeException ex) {
        event.status = "ERROR";
        throw ex;
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
~~~

These classes are assumed to live in the same package or have matching imports.

**Design considerations:**

- Never write tokens, passwords, customer details, or sensitive request payloads into events.
- Do not turn every request into numerous stack-trace-capturing events without measuring overhead.
- Keep event names, categories, and fields stable for downstream pipelines.
- Do not store high-cardinality values in event fields if downstream converts them into metric labels.
- If a field's meaning changes, version the event or define explicit conversion rules.

### 6.2. Custom events are also contracts

Suppose a pipeline filters **com.example.OrderProcessed** and reads field **itemCount**. Renaming it to **numberOfItems** without updating parsers causes telemetry drops.

This is **telemetry data compatibility**. Even while the application keeps running, monitoring pipelines can silently lose signals.

## 7. JFR Event Streaming

Since JDK 14, **JEP 349** has provided JFR Event Streaming. APIs like **jdk.jfr.consumer.RecordingStream** receive events in real time or near-real time inside the same JVM.

Example:

~~~java
package example.monitoring;

import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public final class JfrStreamExample {
    public static void main(String[] args) throws Exception {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                .withPeriod(Duration.ofSeconds(1));

            stream.onEvent("jdk.CPULoad", event -> {
                float jvmUser = event.getFloat("jvmUser");
                System.out.println("JVM user CPU load: " + jvmUser);
            });

            stream.startAsync();
            Thread.sleep(10_000);
        }
    }
}
~~~

This snippet illustrates the API; verify exact event fields and availability against target runtime metadata.

### 7.1. Do not use streaming to replace all metric types

Streaming fits event-reactive use cases, yet monitoring pipelines must weigh:

- Delivery latency.
- Event volume.
- Sampling periods and event drops.
- Backpressure or slow downstream consumers.
- Stream lifecycle management.
- Sensitive-data protection.
- Cost of converting events into metrics/traces.
- Recovery across JVM restarts.

If the goal is merely polling heap usage every 30 seconds, reading an MXBean or using an exporter can be simpler.

### 7.2. Event schemas require validation

Code calling directly:

~~~java
event.getFloat("jvmUser");
~~~

depends on a field named **jvmUser** having a compatible type. If the JDK/vendor alters event metadata or disables the event, pipelines can stop receiving data or throw exceptions.

For out-of-process collectors/parsers, include a step to **inspect metadata and verify expected event fields** on startup or in compatibility test suites rather than silently swallowing all errors.

## 8. JMX: MBean Server, ObjectNames, and attributes

JMX offers a management model centered on **MBeans**.

Components:

- **MBean Server:** registry where MBeans are registered and queried.
- **ObjectName:** identifier naming an MBean via a domain and key properties.
- **Attribute:** readable/writable property per access rules.
- **Operation:** management action exposed for invocation.
- **Notification:** administrative event emitted by an MBean.
- **JMX Connector:** transport endpoint allowing remote tools to access the MBean server.

Standard ObjectName examples:

~~~text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=ClassLoading
java.lang:type=Runtime
java.lang:type=OperatingSystem
java.lang:type=GarbageCollector,name=*
java.lang:type=MemoryPool,name=*
~~~

**GarbageCollector** and **MemoryPool** names depend on the active collector and JVM implementation. Wildcard ObjectName queries are far more resilient than hardcoding collector names in rules.

### 8.1. Platform MXBeans

Java defines standard management interfaces under **java.lang.management**:

- **MemoryMXBean**
- **ThreadMXBean**
- **RuntimeMXBean**
- **ClassLoadingMXBean**
- **OperatingSystemMXBean**
- **GarbageCollectorMXBean**
- **MemoryPoolMXBean**
- **CompilationMXBean** if supported by the runtime
- **ManagementFactory** to obtain beans

**java.management** is the standard module providing these APIs. Extensions may reside in separate modules/packages, such as HotSpot/vendor extensions.

### 8.2. Reading MXBeans locally inside the JVM

Example:

~~~java
package example.monitoring;

import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public final class JmxLocalExample {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();

        System.out.println("Heap used: " + heap.getUsed());
        System.out.println("Heap committed: " + heap.getCommitted());
        System.out.println("Heap max: " + heap.getMax());

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println(
                gc.getName() + " collections=" + gc.getCollectionCount()
                    + " time(ms)=" + gc.getCollectionTime()
            );
        }
    }
}
~~~

Certain statistics return **-1** when unsupported by the JVM. Monitoring code must treat -1 as **unknown/unsupported**, never blindly as 0.

**Collection time** in an MXBean does not necessarily equal total application stop-the-world pause time under all collectors. It is an implementation-reported statistic and may differ from how readers interpret total GC pauses.

### 8.3. ThreadMXBean and capability checking

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean threads = ManagementFactory.getThreadMXBean();

System.out.println("Threads: " + threads.getThreadCount());

if (threads.isThreadCpuTimeSupported()) {
    if (!threads.isThreadCpuTimeEnabled()) {
        System.out.println("Thread CPU time disabled");
    } else {
        long cpuNanos =
            threads.getThreadCpuTime(Thread.currentThread().getId());
        System.out.println("Current thread CPU ns: " + cpuNanos);
    }
}
~~~

When querying thread CPU time, check both JVM support and whether tracking is enabled. Never turn -1 or empty samples into performance alarms without capability checks.

### 8.4. JVM/vendor-specific MXBeans

Extended APIs exist such as **com.sun.management.OperatingSystemMXBean** and HotSpot-specific MBeans. Tools leverage them for CPU load, thread allocation, or diagnostics.

Avoid confusing:

- **Standard Java Management APIs:** contracts specified by Java SE.
- **Extended JDK/vendor MXBeans:** availability/semantics may vary across implementations.
- **Framework/application-registered MBeans:** tied to framework lifecycles and versions.
- **MBean exporters:** map MBean values into external metric formats using their own rules and versions.

If pipelines work only when **com.sun.management** MBeans exist, document that JDK-implementation assumption explicitly in the support matrix.

## 9. Why can switching GC break dashboards?

Suppose a dashboard queries a G1-specific series:

~~~text
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

Switching collectors can make that MBean name disappear. The application keeps running while charts lose data.

Similarly, memory pool names vary:

- G1 exposes pools tied to G1 Eden, Survivor, and Old Generation.
- Other collectors publish different pool names and structures.
- Metaspace, Code Cache, or custom pools split and name regions differently by implementation.

### 9.1. Do not compute total heap by summing fixed memory pool names

Rules summing familiar pool names risk skipping pools on the target JVM. To track **total heap used**, prefer a metric with clear aggregate semantics like **MemoryMXBean.getHeapMemoryUsage().getUsed()**, using pool metrics for drill-down analysis.

### 9.2. GC count does not equal pause count

A concurrent collector performs phases non-equivalent to predominantly stop-the-world collectors. When comparing performance across migrations:

- Focus on application goals: latency, throughput, allocations, CPU, memory pressure.
- Track GC pause distributions where supported.
- Distinguish concurrent work from stop-the-world pauses.
- Compare event/metric semantics specific to each collector.
- Never judge a new collector solely by total GC count or summed collector time.

### 9.3. Normalize metrics by meaning, not old names

Example application-level metric design:

~~~text
jvm_heap_used_bytes
jvm_heap_committed_bytes
jvm_thread_live_count
process_cpu_usage_ratio
application_request_duration_seconds
~~~

These names are illustrative. Real pipelines may follow Micrometer, OpenTelemetry, Prometheus, or JMX exporter naming conventions.

When changing runtimes, verify each new metric's source, unit, and semantics. Never relabel **G1 collection count** as **all GC pauses** when the two measurements are non-equivalent.

## 10. Remote JMX: connectivity and security boundaries

JMX can operate in-process or over the network. Remote JMX usually relies on the RMI connector, involving more than a single static port.

Common factors:

- JMX registry port.
- RMI connector endpoint and port.
- Hostname/IP advertised by the JVM to clients.
- Authentication.
- TLS/SSL.
- Firewalls and network policies.
- Authorization to connect and invoke MBean operations.
- Container port mappings.
- Access via bastion/VPN or isolated management networks.

### 10.1. Why does local JMX succeed while remote JMX fails?

A JMX client may reach the registry port and then fail when RMI instructs it to connect to a different address/port returned by the JVM.

Configuration failure illustration:

~~~text
Registry endpoint: monitoring.example.internal:9010
RMI server advertises: localhost:random-port
Client on another host:
  -> connects to registry successfully
  -> tries to connect to client's own localhost
  -> fails
~~~

In containers/Kubernetes, NAT, hostnames, and port forwarding complicate this further.

### 10.2. Reference configuration options

Commonly involved JVM flags:

~~~text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=<host-reachable-by-client>
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
~~~

This is **not a complete production configuration**. Production use requires configuring authentication/authorization, TLS certificates/keystores, file permissions, and network policies per JDK/vendor documentation and infrastructure standards.

**Never disable authentication or SSL and expose JMX to public networks to bypass connectivity issues.** MBeans exposing write operations or management actions create severe security risks.

### 10.3. Prefer restricted management channels

Safer operational approaches:

- Restrict access strictly to private management networks.
- Use authenticated tunnels or authorized port-forwarding.
- Enforce firewall/network-policy egress and ingress controls.
- Enforce TLS and authentication whenever enabling remote JMX.
- Never expose JMX ports on public load balancers.
- Separate read-only permissions from mutating operations where architecture permits.
- Keep credentials outside source code and public command lines.

Test examples disabling security must never serve as production rollout templates.

## 11. Reading JMX remotely from a Java client

A standard Java JMX client connects remotely using **JMXServiceURL** and **JMXConnectorFactory**.

~~~java
package example.monitoring;

import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteJmxRead {
    public static void main(String[] args) throws Exception {
        String url =
            "service:jmx:rmi:///jndi/rmi://monitoring.example.internal:9010/jmxrmi";

        Map<String, Object> env = new HashMap<>();

        // Credentials must be fetched from a secret manager/secure config,
        // never hardcoded in source or committed.
        String username = System.getenv("JMX_USER");
        String password = System.getenv("JMX_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Missing JMX credentials");
        }

        env.put(JMXConnector.CREDENTIALS,
            new String[] {username, password});

        try (JMXConnector connector = JMXConnectorFactory.connect(
                new JMXServiceURL(url), env)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName memory =
                new ObjectName("java.lang:type=Memory");

            Object usage =
                connection.getAttribute(memory, "HeapMemoryUsage");

            System.out.println(usage);
        }
    }
}
~~~

This snippet **only illustrates the connection API** and assumes the server enforces TLS, authentication, and network isolation. Real systems must configure SSL socket factories/truststores matching deployment, timeouts, and error handling. Never assume passing a username/password means the transport channel is encrypted.

### 11.1. Attributes can be `CompositeData`

Some JMX attributes like **HeapMemoryUsage** return as **CompositeData** over `MBeanServerConnection`. Tools/exporters must read **used**, **committed**, and **max** fields per the composite schema rather than assuming every attribute is a primitive number.

### 11.2. Distinguish lost connections from zero metrics

When connections fail, dashboards should report **absent/unavailable**. Never substitute CPU usage = 0 or GC count = 0, as this hides an exporter failing to reach the JVM.

Configure dedicated alerts for exporter scrape failures, target down states, and metric absence.

## 12. JMX and the module system

JDK 9 and newer support the Java Platform Module System (JPMS). In custom runtime images, modules determine tool/API availability:

- **java.management**: management APIs and core standard MXBeans.
- **java.management.rmi**: supports the JMX RMI connector.
- **jdk.management**: extended JDK MXBeans/management features.
- **jdk.jfr**: JFR API/runtime.
- **jdk.jcmd**: diagnostic command executables in the JDK image, depending on packaging.

A modular application may declare:

~~~java
module example.monitoring {
    requires java.management;
    requires jdk.jfr;
}
~~~

If remote JMX connectors are required inside a custom runtime image, ensure all supporting modules are included. Packaging with **jlink** can exclude modules/tools always present in full JDKs.

### 12.1. Do not confuse Java modules with Maven artifacts

Not every Java SE/JDK module can be added back via a dependency in `pom.xml` or `build.gradle`. If the runtime image omits **jdk.jfr**, changing application Maven dependencies will not supply it.

Inspect:

~~~bash
java --list-modules
~~~

For custom images, execute against the exact **java** binary inside the image rather than inferring from a developer workstation's **java**.

### 12.2. Diagnostic tools may not be packaged

Minimal container runtime images often omit **jcmd**, **jfr**, **jstack**, and other diagnostic binaries.

Solutions include:

- Designing startup JFR recording workflows where needed.
- Using the in-process JFR API when appropriate.
- Using approved diagnostic/tooling images.
- Retrieving .jfr artifacts via mounted volumes or secure channels.
- Avoiding shipping full JDKs and broad attach privileges into production without review.

## 13. Attach and containers: frequently overlooked root causes

### 13.1. PID namespaces

The host may see PID 24107 while inside the container the Java process holds PID 1. Running **jcmd** from a different namespace may fail to see or attach to the target process.

When debugging:

1. Identify whether `jcmd` runs on the host or inside the container.
2. Identify the process's PID inside that exact namespace.
3. Check process owner and OS permissions.
4. Check JDK/JVM diagnostic capabilities.
5. Check whether dynamic attach mechanisms were disabled.
6. Fall back to startup recording if attach is unavailable.

### 13.2. Filesystems and write permissions

JFR dumps can fail because:

- Containers mount root filesystems read-only.
- The destination directory does not exist.
- The service process lacks write permission.
- The volume ran out of space.
- Ephemeral recording files vanish on pod restarts.
- Security policies deny file creation.

Never grant root privileges or mount broad host directories just to write recordings. Use dedicated directories with narrow permissions and secure retention/retrieval policies.

### 13.3. Cgroup CPU and memory

Modern JDKs offer extensive container resource awareness. Yet reported CPU counts, heap ergonomics, and process load vary across JDK releases, cgroup versions, vendors, and flags.

When comparing metrics:

- What units measure process CPU?
- What are CPU quotas, requests, and limits?
- Does the JVM detect the container quota?
- Did the JVM's visible processor count change?
- Is max heap calculated from container memory limits or host RAM?
- Is there swap or native memory pressure?
- Do dashboards normalize against host CPU or container CPU?

A change in the denominator of CPU usage shifts charts even when workload stays identical.

### 13.4. GC and process restarts reset counters

JMX counters like collectionCount or collectionTime are bound to the JVM's lifetime. Rolling deployments reset these counters.

When exporters publish cumulative counter metrics, compute rates/increases per your metrics system's semantics so counter resets are not misread as negative numbers or "GC suddenly became faster".

## 14. JMX exporters and conversion to time-series metrics

Many systems use Prometheus JMX Exporter to scrape MBeans and convert attributes into time-series metrics. Micrometer/Actuator and OpenTelemetry also provide JVM telemetry collectors.

### 14.1. Why exporter config is also a compatibility contract

Mapping rules commonly rely on:

- ObjectName domains.
- MBean key properties.
- Attribute names.
- CompositeData fields.
- MemoryPool/GC collector names.
- Regex pattern matching.
- Type/name/unit transformations.
- Labels extracted from ObjectNames.

If a newer JDK alters an ObjectName or a newer exporter changes naming conventions, dashboards can go blank.

### 14.2. Example of a brittle rule

A configuration matching only one exact collector:

~~~text
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

loses meaning when switching collectors. Better approaches include:

- Using wildcards for dynamic MBean object name properties.
- Keeping collector/pool labels instead of assuming one hardcoded name.
- Defining canonical metrics with unified aggregate semantics.
- Relying on recordings/GC logs when analyzing collector-specific details.
- Testing alerts/queries against both legacy and target collectors.

### 14.3. Metric names and units can change even if JMX stays identical

Metrics libraries normalize names differently:

~~~text
jvm.memory.used
jvm_memory_used_bytes
jvm.memory.used.bytes
~~~

These illustrate naming styles across metrics ecosystems; never assume they automatically alias each other.

During migration, verify:

- Base units: bytes, KiB, MB, seconds, milliseconds, nanoseconds.
- Metric types: gauge, cumulative counter, delta, histogram.
- Label sets and value cardinality.
- Resource attributes like `service.name` and runtime version.
- Scrape/export intervals.
- Handling of disappeared series.
- Duplicate telemetry if two agents export the same source.

If two exporters emit the same metric name with different semantics, summing them on a dashboard produces false conclusions.

## 15. JFR events and analysis tool compatibility

JFR recordings embed metadata describing event types and fields. Custom `.jfr` analysis tools often depend tightly on that schema.

### 15.1. Risk of hardcoding event schemas in parsers

Suppose a parser expects:

~~~text
Event type: jdk.CPULoad
Fields: jvmUser, jvmSystem, machineTotal
~~~

If a field is absent, changes type, or is disabled on the target runtime, the parser might:

- Crash when reading the field.
- Skip the event.
- Record null/0 as metrics.
- Miscompute aggregates.
- Produce incomplete reports with zero warnings.

Being able to open a `.jfr` file does not prove your pipeline processes every event accurately.

### 15.2. Designing resilient parsers

Prefer:

1. Reading the recording's embedded metadata.
2. Checking whether required event types exist.
3. Validating expected field names and types.
4. Providing explicit fallbacks for optional fields.
5. Never defaulting missing fields to 0.
6. Distinguishing disabled events from zero occurrences.
7. Emitting warnings when schemas fall outside the support matrix.
8. Running automated tests against recordings from both baseline and target JDKs.

### 15.3. Do not compare raw event counts across different settings

Recordings captured under **default** versus **profile** emit vastly different event counts. Thresholds and sampling periods reshape event volume.

Example:

~~~text
JFR A: execution sample every 20 ms
JFR B: execution sample every 10 ms
~~~

Higher sample counts in B happen simply from a shorter sampling interval—not because the app suddenly doubled its CPU consumption.

When comparing recordings, document:

- JFR settings.
- Event enablement status.
- Sampling periods/thresholds.
- Recording duration.
- Active workload.
- JVM flags.
- JDK/vendor.
- Container resource limits.
- Dropped or truncated event counts if any occurred.

## 16. Profiling overhead and operational safety

Observability introduces overhead and can perturb measurements. JFR is engineered for low cost in typical modes, yet actual overhead scales with enabled events and configuration.

### 16.1. Factors that raise overhead

- High event emission rates.
- Enabling stack traces on high-frequency events.
- Fine-grained allocation profiling.
- Overly aggressive sampling periods.
- Continuous disk writes onto slow storage.
- Slow streaming event consumers.
- Multiple instrumentation agents attached to the same JVM.
- Running a Java debugger, profiler, and JFR simultaneously.
- Latency-sensitive workloads or tight container CPU/I/O quotas.

No single fixed overhead number fits all applications. Measure under representative workloads.

### 16.2. Incident capture plan template

~~~text
Incident ID:
Service / pod / JVM PID:
JDK vendor/version:
Collector:
JFR settings:
Recording name:
Expected duration:
File destination:
Expected size cap:
Operator / approval:
Sensitive-data policy:
Start time:
Stop time:
Storage/transfer policy:
Cleanup:
~~~

Use time-bounded recordings, explicit size/retention caps, and controlled access procedures. Never leave production `.jfr` files on unmanaged personal laptops if they might contain sensitive details.

### 16.3. JFR does not replace load testing

A recording taken under light traffic does not predict overhead at peak throughput. Before enabling continuous profiling, verify:

- Throughput and p95/p99 latencies.
- CPU usage.
- Allocation rates and GC behavior.
- Heap and native memory footprint.
- Disk write rates.
- Event volume.
- Impact on autoscaling signals.
- Compliance with acceptable SLO degradation bounds.

## 17. Upgrade-resilient monitoring architecture

To avoid locking dashboards to one JDK's internal implementation, decouple the layers:

~~~text
Raw JVM telemetry
   JMX beans / JFR events / GC logs
               |
               v
Exporter / Collector / Adapter
               |
               v
Normalized internal contract
   metric name + unit + labels + semantics
               |
               v
Time-series / Event storage
               |
               v
Dashboards, SLO, Alerts, Automation
~~~

### 17.1. Benefits of an adapter layer

An adapter can translate both legacy and modern JMX sources into unified metrics with clear semantics, provided:

- Critical meaning is preserved.
- Non-equivalent quantities are never summed together.
- Runtime/collector metadata is retained.
- Missing/unsupported states are handled explicitly.
- Contract tests guard the mapping.

For instance, **jvm_heap_used_bytes** can be derived consistently from `MemoryMXBean`, whereas emitting a single **gc_pause_seconds** series from arbitrary GC MXBeans is unsafe if the source does not actually measure pause duration.

### 17.2. Separating business metrics from JVM metrics

When deciding whether to roll back a migration, prioritize user-perceivable signals:

- p50/p95/p99 latencies.
- Error rates.
- Throughput.
- Queue lag.
- Database connection saturation.
- Request timeouts.
- Memory pressure.
- Crashes, OOMs, and restarts.

JVM metrics explain root causes, yet a higher **GC event count** does not mean the application degraded if latency and throughput meet targets.

## 18. Scenario analysis: migrating from G1 to ZGC

Suppose a Java service upgrades its JDK and switches garbage collectors.

Pre-migration:

~~~text
Baseline JDK
GC: G1
Dashboard:
  - G1 Young Generation collection count
  - G1 Old Generation collection time
  - G1 heap pools
Alerts:
  - pause time > threshold
~~~

Post-migration:

~~~text
Target JDK
GC: ZGC
Old dashboard:
  - Several G1 MBeans/series disappear
  - Alerts lack sufficient data
  - Operators assume GC is operating normally
~~~

This is an **observability compatibility failure**, not necessarily a performance regression in the new GC.

### 18.1. Transition workflow

1. Baseline latency, throughput, heap usage, CPU usage, and pause distributions.
2. Inspect JMX beans and JFR events on the target runtime.
3. Distinguish collector-independent metrics from collector-specific metrics.
4. Update exporter rules to remove inappropriate hardcoded G1 assumptions.
5. Update dashboards and alerts to match target collector semantics.
6. Run representative workloads under both G1 and the target collector.
7. Compare application SLOs and resource envelopes.
8. Verify alerts actually fire when telemetry drops or thresholds breach.
9. Canary deploy while monitoring both performance and scrape/recording health.
10. Retire legacy G1 dashboards/rules only after no active runtimes require them.

### 18.2. Avoid fabricating uniform metrics across incompatible collectors

Collectors often define phases and pauses incompatibly. Never rename or merge incompatible counters merely to preserve old queries.

Better practices:

- Keep high-level dashboards built around unified definitions of heap, CPU, and latency.
- Maintain collector-specific GC drill-down dashboards/rules.
- Include **collector** or **runtime version** labels for clear segmentation.
- Focus operational alerts on application symptoms and hard error signals.

## 19. Scenario analysis: JMX exporter stops receiving data after container migration

Suppose a JMX exporter scrapes metrics fine on VMs, yet collects nothing after containerization.

Likely causes:

- RMI server advertises a hostname unreachable from clients.
- JMX port or RMI port is blocked.
- Service account lacks permissions.
- TLS or credential configurations changed.
- Exporter targets the wrong process/JVM.
- Custom runtime image lacks required management modules.
- Exporter sits in an isolated network namespace.
- Misconfigured firewalls, service discovery, or port mappings.
- Remote management was disabled in JVM args.
- Container restarts changed PIDs/hostnames.

### 19.1. Ordered triage

1. Verify the target JVM is still running.
2. Verify network reachability and permissions.
3. Inspect registry/RMI endpoints and advertised hostname.
4. Test auth/TLS using a trusted JMX client.
5. Verify target MBeans exist on the destination JVM.
6. Check exporter mapping rules.
7. Inspect the exporter's scrape endpoint output.
8. Verify the time-series backend ingests expected labels.
9. Verify dashboard/alert queries match updated metric names/labels.

Never fix connectivity by disabling SSL/auth and exposing open ports publicly. When debugging, use restricted admin tunnels and follow organizational logging policies.

### 19.2. Do not turn "missing" into 0

If an exporter loses connectivity, absent metrics must surface as unavailable telemetry. Rendering missing values as 0 misleads operators into believing zero GC occurred, zero CPU is used, or memory pressure vanished.

Alert specifically on **up/scrape health**, missing metrics, and target-discovery failures.

## 20. Scenario analysis: JFR recording opens yet reports skewed data

Suppose a custom analysis tool opens a `.jfr` recording from the new JDK yet computes wrong CPU metrics.

Possible causes:

- **jdk.CPULoad** fields differ from parser expectations.
- The event is disabled in target settings.
- Sampling period changed.
- Container CPU quotas changed.
- Ratio-to-percentage conversion bug in the parser.
- JDK altered how process/system CPU is accounted.
- Recording duration or workload differed.
- Parser aggregates samples without duration/weight normalization.
- Events were dropped due to policy or buffer pressure.

### 20.1. How to verify

1. Run **jfr summary** to check which events are actually recorded.
2. Run **jfr metadata** to inspect exact field names and types.
3. Run **jfr print** on representative sample events.
4. Verify active recording settings.
5. Cross-check process/container CPU via independent OS telemetry.
6. Verify unit conversions.
7. Re-test under matched workload and sampling settings.
8. Update parsers and metric contracts if schemas genuinely shifted.

A parser completing without runtime exceptions can still misinterpret numbers. Acceptance criteria must cover **metric accuracy**, not merely file readability.

## 21. Telemetry security and privacy

JFR recordings, heap diagnostics, and JMX management interfaces can expose sensitive system details.

Risks:

- Internal class and package names.
- Thread names containing request IDs or tenant IDs.
- File paths and socket hostnames.
- System properties containing sensitive configuration.
- Custom events accidentally logging PII.
- JMX operations capable of mutating service state.
- Agents or remote tools granted excessive access.
- Recordings shared outside authorized personnel.
- Diagnostic logs leaking credentials or tokens.

### 21.1. Baseline controls

- Restrict who and which systems may access recordings.
- Never include sensitive data inside custom JFR events.
- Enforce retention and encryption policies for `.jfr` files.
- Protect remote JMX with authentication, TLS, and network isolation.
- Isolate management endpoints from public ingress traffic.
- Keep credentials out of source code and shell histories.
- Audit access to administrative tools when required.
- Grant least-privilege permissions to exporters and agents.
- Delete temporary recordings promptly after triage concludes.
- Sanitize and inspect contents before sharing externally or with vendors.

Apply security controls across collection, transit, storage, access, and sharing boundaries.

## 22. Monitoring compatibility testing strategy

### 22.1. Capture baselines prior to migration

Save:

- JDK vendor, version, and build.
- JVM flags, GC, and memory configs.
- Container images and resource requests/limits.
- JFR recording settings.
- Critical event lists and metadata schemas.
- Critical MBean/ObjectName/attribute lists.
- Versions of JMX exporters, agents, and JMC.
- Scrape configs and metric naming rules.
- Dashboard JSON/queries and alert rules.
- Baseline metrics and recordings under representative workloads.
- Required security/network specs without storing secrets.

### 22.2. Runtime and tooling test matrix

| Component | Baseline | Target | Verification focus |
|---|---|---|---|
| JVM | JDK A | JDK B | Startup, performance, modules |
| GC | Collector A | Collector B | MBeans, event semantics |
| JFR | Recordings from A | Recordings from B | File readability, event schema |
| JMC/parser | Legacy tool version | Version supporting B | Accurate parsing and visuals |
| JMX | Attributes on A | Attributes on B | ObjectNames, types, availability |
| Exporter | Old rules | Updated rules | Metric names, units, labels |
| Dashboard | Queries for A | Queries for B | Panels render completely and accurately |
| Alerts | Rules for A | Rules for B | Threshold triggers and missing-data handling |
| Container | Image A | Image B | PIDs, cgroups, filesystems, ports |
| Security | Policy A | Policy B | Auth, TLS, permissions |

This serves as a planning framework; not every cell requires testing on every release. Focus on combinations actually running in production.

### 22.3. JMX-level tests

A verification test can:

1. Start the target JVM with production-like flags.
2. Query the platform MBean server.
3. Run wildcard queries for GC and MemoryPool beans.
4. Assert expected attributes exist.
5. Verify data types and units.
6. Verify `-1`/unavailable values are handled properly.
7. If using remote JMX, test auth/TLS and port mappings.
8. Verify matching exporter scrape outputs.

Do not assert hardcoded collector names unless your support matrix fixes one collector.

### 22.4. JFR-level tests

A verification test can:

1. Start a recording with documented settings.
2. Run workloads exercising CPU, allocations, and representative I/O.
3. Confirm the `.jfr` file exists and opens cleanly in target tooling.
4. Check critical event types and fields.
5. Confirm parsers handle missing/optional fields cleanly.
6. Reconcile units, sampling periods, and recording durations.
7. Cross-check normalized metrics against an independent reference if needed.
8. Verify recording cleanup and data-retention controls.

### 22.5. Testing alerts on telemetry loss

Do not test only high heap or high request latency. Simulate exporter downtime or dropped metrics, then verify:

- Dashboards do not silently render fake zeros.
- Missing-data alerts trigger reliably.
- Alerts route to the correct on-call owners.
- Alerts recover cleanly once metrics resume.
- Rolling restarts do not unleash noisy alert storms.

### 22.6. Canary and parallel monitoring

One migration stage can run side by side:

~~~text
Canary target JDK
      |
      +--> Target collector/exporter
      +--> Representative JFR recording
      +--> New dashboard

Baseline JDK
      |
      +--> Legacy collector/exporter
      +--> Baseline JFR
      +--> Legacy dashboard

Compare:
  - SLOs
  - Metrics coverage
  - Units/labels/semantics
  - Tool overhead
  - Alerts and gaps
~~~

When comparing dashboards side by side, never compare rates across mismatched time windows or non-equivalent workloads.

## 23. Rollout gates and Go/No-Go criteria

### Gate A — Inventory

- All JMX/JFR/agent collection paths mapped.
- Dependencies on JDK vendor and GC identified.
- Dashboard/alert definitions and owners identified.
- Telemetry baselines and incident runbooks captured.

**Go:** all signals relied on in operations are testable.

### Gate B — Tool readiness

- JMC and parsers handle target JFR recordings.
- JMX exporters understand target MBeans.
- Runtime images ship required modules/tools.
- Remote management security/networking designed.

**Go:** zero known tooling blockers.

### Gate C — Staging/canary

- JFR capture and parsing succeed cleanly.
- JMX metrics scrape reliably.
- Metric names, units, and labels verified.
- Dashboards render accurate values.
- Missing-telemetry alerts fire properly.
- SLOs and performance verified.
- Recording/agent overhead stays within budget.

**Go:** trustworthy observability under representative load.

### Gate D — Rollout

- Canary/rolling rollout plan ready.
- Rollback-compatible exporters and dashboards active.
- Metrics distinguish runtime versions cleanly.
- Updated incident runbooks handed over.
- JFR collection fallback documented if attach is blocked.
- Zero unapproved observability blind spots.

**Go:** operations retains full signal coverage to detect and mitigate incidents during cutover.

### Gate E — Cleanup

- No instances remain requiring legacy out-of-support rules.
- Legacy unused dashboards/queries retired.
- Workarounds and temporary ports/flags removed.
- Documentation, ownership, and support matrices updated.
- Temporary recordings governed by retention policies.

Do not delete legacy monitoring configs until all unmigrated instances have drained.

## 24. Practical checklist

### JDK, runtime, and GC

- [ ] Documented JDK vendor, version, JVM flags, and collector.
- [ ] Verified container CPU/memory visibility.
- [ ] Audited modules inside the runtime image.
- [ ] Confirmed `jcmd`/`jfr` availability or alternative capture methods.
- [ ] Assessed collector-specific names and semantics.

### JFR

- [ ] Confirmed JFR availability on the target JDK/runtime.
- [ ] Defined explicit recording settings.
- [ ] Validated operational start/dump/stop procedures.
- [ ] Opened and parsed `.jfr` files cleanly with target analysis tools.
- [ ] Validated critical events and fields.
- [ ] Verified parsers handle missing/optional events and fields safely.
- [ ] Checked overhead, storage sizing, and retention.
- [ ] Confirmed custom events exclude sensitive information.

### JMX and exporters

- [ ] Confirmed required MBeans/attributes exist on target runtimes.
- [ ] Avoided hardcoding GC/MemoryPool names outside support policies.
- [ ] Handled unavailable attributes as unknown rather than 0.
- [ ] Tested exporter rules against target MBeans.
- [ ] Verified metric units, types, and labels.
- [ ] Configured remote JMX with auth, TLS, and network isolation.
- [ ] Tested RMI ports, advertised hostnames, and container connectivity.

### Dashboards, alerts, and rollout

- [ ] Verified dashboards have no broken panels or silent zero displays.
- [ ] Tested alert rules on both live metrics and missing telemetry.
- [ ] Established baseline and canary comparisons.
- [ ] Tracked application SLOs alongside JVM metrics.
- [ ] Verified connectivity and telemetry on production-like images.
- [ ] Prepared runbooks for collecting container diagnostics.
- [ ] Prepared rollback plans for tools, agents, and configs.
- [ ] Assigned owners to every critical telemetry contract.

## 25. References

Consult documentation matching your project's exact JDK/vendor and tool versions:

- **JEP 328 – Flight Recorder:** https://openjdk.org/jeps/328
- **JEP 349 – JFR Event Streaming:** https://openjdk.org/jeps/349
- **JFR API (jdk.jfr):** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html
- **java.management module:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html
- **ManagementFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- **javax.management.remote APIs:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- **jcmd command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **jfr command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- **JDK Mission Control:** https://www.oracle.com/java/technologies/jdk-mission-control.html
- **Prometheus JMX Exporter:** https://github.com/prometheus/jmx_exporter
- **Micrometer:** https://docs.micrometer.io/micrometer/reference/
- **OpenTelemetry Java:** https://opentelemetry.io/docs/languages/java/

Never extrapolate documentation describing JDK 21 as a guarantee for every vendor and future release. Reconcile APIs, runtime flags, module availability, and live event/MBean metadata in your target environment.

---

**Conclusion:** In Java migration, **JFR reveals performance dynamics over time via events**, while **JMX exposes live JVM states and counters**. Both can harbor hidden couplings: dashboards bound to GC MBean names, parsers tied to JFR event fields, exporters expecting specific units/labels, or remote JMX relying on specific network topologies. Upgrading the JDK safely requires inventorying telemetry contracts, verifying them on the target runtime, distinguishing missing data from 0, accounting for overhead and security, and deploying runtime and monitoring changes together. A migration is only truly production-ready when **the team retains reliable visibility and incident detection after the JVM changes**.
