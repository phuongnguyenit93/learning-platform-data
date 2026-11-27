# JFR, Heap Dumps, and Monitoring Capabilities by Version and Platform

When running Spring Boot on the JVM, operations teams are typically used to JDK Flight Recorder (JFR), heap dumps, JMX, and HotSpot diagnostic tools. When compiling an application into a **GraalVM Native Image**, these capabilities can still exist, but they are not enabled by default and do not have the same scope across every version or operating system.

Native Image has its own runtime and does not run inside HotSpot. Diagnostic features such as JFR, heap dumps, Native Memory Tracking (NMT), Java Diagnostic Command (jcmd), and JVMStat must be included in the binary at build time. Only then can the application start recordings, generate dumps, or accept diagnostic commands at runtime.

This lesson explains how to enable and use JFR, heap dumps, NMT, and jcmd for Spring Boot Native Image; distinguishes the Java heap from process memory; points out version and platform limitations; and combines them with Spring Boot Actuator metrics, logs, and traces to establish a production observability workflow.

## 1. Why Must You Distinguish Observability Tools?

Each tool answers a different question. Using the wrong tool can lead operations teams to the wrong conclusion about the root cause of an incident.

| Tool | Primary question | Data obtained |
|---|---|---|
| JFR | How do CPU, allocations, GC, threads, and events change over time? | Timestamped event recording, with stack traces on supported events |
| Heap dump | Which objects are currently alive in the Java heap at capture time? | Object graph snapshot in HPROF format |
| NMT | Which native memory regions is the Native Image runtime tracking and how much do they use? | Categorized report of runtime-tracked native memory |
| jcmd | What diagnostic information or actions can the process be asked to provide? | Thread dumps, heap dumps, JFR control, VM information, and NMT reports |
| Actuator/Micrometer | How many requests is the service handling, what are latency/errors, and how do metrics trend? | Periodic metrics and data exportable to monitoring backends |
| Logs and traces | Which components did a specific request traverse and where did errors occur? | Log events and distributed traces |

JFR is suited for identifying when CPU spikes, GC becomes frequent, or allocations behave abnormally. Heap dumps are useful when you need to find objects retaining references and growing the Java heap. NMT helps observe the portion of native memory tracked by the runtime. Spring Boot metrics and traces are suited for continuous service-level monitoring.

No single dump file can replace all of these data sources.

## 2. Diagnostic Features Must Be Enabled at Build Time

Native Image only includes monitoring features selected when running the `native-image` builder. Example:

~~~bash
native-image \
  --enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat \
  -jar application.jar
~~~

The `--enable-monitoring` option accepts a comma-separated list of features. Common values:

| Feature | Value | Purpose |
|---|---|---|
| JDK Flight Recorder | `jfr` | Event recording and profiling |
| Heap dump | `heapdump` | Creating Java heap snapshots |
| Native Memory Tracking | `nmt` | Tracking native memory supported by the runtime |
| Java Diagnostic Command | `jcmd` | Receiving diagnostic commands via the jcmd tool |
| JVMStat | `jvmstat` | Supporting process discovery and listing tools such as VisualVM or jcmd -l |
| JMX server/client | `jmxserver`, `jmxclient` | JMX connectivity in supported scenarios; check limitations and experimental status |

Supported values may vary by GraalVM version and distribution. Check the documentation for your exact toolchain before configuring.

**Runtime flags cannot add features excluded from the binary.** For example, passing `-XX:StartFlightRecording` when the binary was built without JFR support will not make JFR appear. If you need JFR or heap dumps after release, you must rebuild the artifact with the corresponding feature.

You do not necessarily need to enable every feature for every service. Choose based on operational needs, binary size, build cost, and deployment platform.

## 3. Configuring Monitoring in Gradle

If your project uses the GraalVM Native Build Tools Gradle plugin, add build arguments to the main binary:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

Then build the native executable:

~~~bash
./gradlew nativeCompile
~~~

If your project uses the Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

This is a build-time configuration. If you only want JFR in a diagnostic variant, you can create a separate build profile or binary, provided the pipeline clearly tracks which artifact is deployed. Avoid accidentally using two different binaries for testing and production without knowing which monitoring features were included.

## 4. Configuring Monitoring in Maven

With the GraalVM Native Build Tools Maven plugin, add the build argument to the plugin configuration:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Build using the project's native profile:

~~~bash
./mvnw -Pnative package
~~~

The example above assumes the project already has the plugin and native profile configured. If the plugin is inherited from a parent POM, verify how `buildArgs` are merged to ensure the option is not overridden. Native Build Tools requires each `buildArg` to be a single Native Image option expression; do not combine multiple shell arguments into one element.

## 5. JDK Flight Recorder in Native Image

JFR records time-stamped events to help analyze CPU, allocations, GC, threads, lock contention, and process activity. Native Image supports the `jdk.jfr.Event` API along with many system events, though the event set is not identical to HotSpot.

To enable JFR, the binary must be built with:

~~~text
--enable-monitoring=jfr
~~~

Start the application and begin a recording:

~~~bash
./application \
  -XX:StartFlightRecording="filename=/diagnostics/orders.jfr,duration=5m,maxsize=256M,dumponexit=true"
~~~

Key parameters:

- `filename`: path to the recording file.
- `duration`: recording duration, such as `5m` or `300s`.
- `maxsize`: file size limit.
- `maxage`: maximum retention age for events.
- `dumponexit`: dump the recording when the process exits.
- `settings`: JFR configuration file such as `default.jfc` or `profile.jfc`, if that profile is compatible with the runtime.

The `/diagnostics` directory must exist and the container user must have write permissions. In production containers, mount a dedicated volume to store files rather than writing to a temporary filesystem or a container layer that may be deleted.

## 6. Reading and Analyzing JFR Files

Once you have `orders.jfr`, use the `jfr` tool bundled with the JDK for a summary:

~~~bash
jfr summary /diagnostics/orders.jfr
~~~

Print the events you want to analyze:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection /diagnostics/orders.jfr
~~~

You can open the file in JDK Mission Control or VisualVM to view the timeline, method profiles, allocations, and threads. JFR snapshots from Native Image can include stack traces for supported events; event streaming has its own limitations.

A basic analysis workflow:

1. Identify the time window when users reported increased latency.
2. Inspect `jdk.ExecutionSample` events to see which methods consumed CPU.
3. Check GC events and heap summaries to determine whether GC occurred frequently or pauses were prolonged.
4. Inspect allocation samples to locate hotspots creating many objects.
5. Correlate thread, lock, and socket events with request logs/traces.
6. Compare the same workload before and after code or configuration changes.

Do not conclude an application has a memory leak from a single snapshot showing a large heap. Compare across multiple timestamps, observe trends in long-lived objects, and verify reference chains retaining objects.

## 7. Known Limitations of JFR

JFR on Native Image is not a complete clone of JFR on HotSpot.

Important limitations:

- Some events are only available when using Serial GC; Serial GC is the default collector in many Native Image configurations.
- Java events generated by HotSpot via bytecode instrumentation, such as certain file I/O or exception events, are not fully available on Native Image.
- `jdk.OldObjectSample` is only partially supported; path-to-GC-root information is not as complete as expected on HotSpot.
- JFR event streaming can deliver continuous callbacks, but stack traces are not yet available in callbacks; stack traces in snapshot files can still work for supported events.
- Remote JMX to control `FlightRecorderMXBean` must be enabled separately and is documented as experimental.
- The JFR profiling sampler depends on the operating system and sampling mechanism. On Windows, the POSIX `SIGPROF`-based sampler is unavailable; the runtime uses the documented recurring-callback mechanism.

Therefore, when an expected event does not appear, check whether that event is supported on your version, GC, and platform before suspecting application code.

## 8. JFR Differences Across Versions and Operating Systems

JFR capabilities have evolved across GraalVM releases. GraalVM 25.5 (Innovation) documentation notes that Windows supports local recording to `.jfr` files. Remote JMX to `FlightRecorderMXBean` and JFR control via `jcmd` are not yet available on Windows. Oracle GraalVM documentation for JDK 25.0 still notes that JFR recording is not yet available on Windows.

This shows you should not apply an older support matrix across all distributions.

| Platform | JFR local file | Remote JMX/JFR via jcmd | Notes |
|---|---|---|---|
| Linux | Available in GraalVM releases supporting JFR | Available when built with corresponding features | Can use POSIX signal-based sampler if supported by version |
| macOS | Available in GraalVM releases supporting JFR | Verify version and JMX/jcmd configuration | Check file write permissions and profiler |
| Windows with GraalVM 25.5 | Can write local recordings per 25.5 documentation | Remote JMX and jcmd not available | Uses recurring-callback sampler |
| Windows with some GraalVM JDK 25.0 or older builds | Corresponding docs may state JFR unsupported | Do not assume availability | Check exact distribution/version |

When upgrading GraalVM, run a JFR smoke test on the exact OS/architecture of your release artifact. Do not merely verify that native compilation succeeds; confirm that a recording file is actually created and opens in analysis tools.

## 9. Heap Dumps in Native Image

A heap dump is a snapshot of objects in the **Java heap managed by the garbage collector**. It helps answer:

- Which objects are currently alive?
- Which collections or caches hold the most objects?
- Are there unusually many objects of the same type?
- Is an object graph holding references to data that is no longer needed?
- After a processing cycle, does the heap shrink when GC runs or keep growing?

To enable heap dump support, build with:

~~~text
--enable-monitoring=heapdump
~~~

A native heap dump can be generated in several ways: when the Java heap runs out of memory, via an administrative tool, via an OS signal on supported platforms, or via GraalVM's API.

**A heap dump is not a snapshot of the process's entire RSS.** It focuses on the object heap. Thread stacks, executable images, shared libraries, memory mappings, and certain native memory regions must be observed with NMT or OS tools.

## 10. Automatic Dump on OutOfMemoryError

The simplest approach is enabling `-XX:+HeapDumpOnOutOfMemoryError`:

~~~bash
./application \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/diagnostics/orders-heap.hprof
~~~

When the native executable throws an `OutOfMemoryError` because the Java heap has no room left, the runtime attempts to write a heap dump. Per GraalVM documentation, if no path is specified, the default file is named `svm-heapdump-<PID>-OOME.hprof` in the working directory.

Verify that:

- The path exists.
- The process has write permissions.
- The volume has sufficient disk space.
- Retention policies do not delete the file before investigation.
- The dump file is protected because it may contain tokens, personal data, request payloads, or sensitive data.

Heap dumps can be very large and create extra I/O pressure. Do not write them to a space-constrained production volume without quotas/retention.

## 11. Generating Heap Dumps on Demand

You can request dumping the initial heap and exiting with:

~~~bash
./application -XX:+DumpHeapAndExit
~~~

This is useful for inspecting objects placed into the image's initial heap, such as objects initialized at build time. It does not represent the heap after the service processes production traffic.

On Linux and macOS, you can send `SIGUSR1` to a running process to generate a heap dump:

~~~bash
kill -USR1 <PID>
~~~

With Docker, you can send the signal to the process inside the container:

~~~bash
docker kill --signal=USR1 orders-native
~~~

This signal mechanism does not exist on Windows. It also requires GraalVM's Signal API; the API is enabled by default in normal cases, though it may differ when building shared libraries.

An application can call `org.graalvm.nativeimage.VMRuntime.dumpHeap` to create a dump under application-controlled conditions. This suits internal diagnostic endpoints or protected admin actions, though you should verify the API for your GraalVM version.

## 12. Using VisualVM to Capture Heap Dumps

VisualVM can open HPROF files generated by Native Image. For VisualVM to discover running processes, also build with `jvmstat`:

~~~text
--enable-monitoring=heapdump,jvmstat
~~~

On Linux/macOS, VisualVM can list Native Image processes and request a heap dump similarly to working with JVM applications.

On Windows, VisualVM can open heap dump files created on other platforms, but Native Image JDK 25 documentation states that creating a heap dump from a running Native Image process on Windows is not supported. Do not confuse the ability to open an HPROF file with the ability to ask a Windows process to create one.

During an investigation, record the capture timestamp, workload, request count, heap level, and GC state. A heap dump without temporal context is very hard to compare against another dump.

## 13. Analyzing Heap Dumps and Avoiding False Conclusions

After opening an HPROF file in VisualVM or a compatible tool, you can inspect:

- Class histogram to find object types occupying many instances/bytes.
- Dominator tree to find objects retaining large amounts of data.
- Retained size to estimate how much heap would be freed if a reference were removed.
- Reference chains to trace what keeps an object alive.
- Comparison between two snapshots taken at the same workload phase.

For example, if a cache holds millions of entries, a heap dump may show `ConcurrentHashMap` and cached value objects occupying most of the heap. That alone is not enough to conclude the cache has a leak: the cache may simply be unbounded by design, or the test may be loading more data than normal.

A solid workflow:

1. Take a dump after warm-up.
2. Run a controlled workload for a period of time.
3. Take a second dump after the workload ends and GC has had a chance to run.
4. Compare object counts and retained sizes.
5. Verify reference chains in the code retaining those objects.
6. Retest after fixing and running the same workload.

If RSS grows while the Java heap does not grow correspondingly, inspect NMT, native libraries, thread stacks, direct/native buffers, and container metrics rather than relying solely on heap dumps.

## 14. Native Memory Tracking for Observing Memory Outside the Java Heap

Native Memory Tracking (NMT) tracks native memory managed by the Native Image runtime. This is critical when a process's RSS is much larger than its Java heap.

Enable NMT at build time:

~~~text
--enable-monitoring=nmt
~~~

Print a report when the process exits:

~~~bash
./application -XX:+PrintNMTStatistics
~~~

In Native Image, NMT is active whenever included in the build and has no HotSpot-like runtime enable/disable toggle. According to GraalVM documentation, NMT has relatively small overhead compared to JFR.

Current limitations to remember:

- Native Image supports NMT summary; HotSpot's detailed mode and baseline comparison are not fully available.
- NMT only tracks allocation regions observable by the runtime.
- Direct `malloc` calls from native code or JNI libraries may not be counted in the report.
- NMT does not replace OS RSS/cgroup measurements.

Therefore, combine NMT with container and OS metrics when investigating memory footprint.

## 15. Combining NMT with JFR

Native Image can emit JFR events for native memory when both JFR and NMT are enabled:

~~~text
--enable-monitoring=jfr,nmt
~~~

Relevant events include:

- `jdk.NativeMemoryUsage`
- `jdk.NativeMemoryUsageTotal`
- `jdk.NativeMemoryUsagePeak`
- `jdk.NativeMemoryUsageTotalPeak`

The two events with the `Peak` suffix are Native Image–specific and are marked experimental in documentation. Tools like JDK Mission Control may require enabling the display of experimental events.

You can filter events in a recording:

~~~bash
jfr print --events jdk.NativeMemoryUsage,jdk.NativeMemoryUsagePeak /diagnostics/orders.jfr
~~~

If native memory events do not appear, verify that NMT was enabled at build time and that those events are available in the GraalVM version you are using.

## 16. Using jcmd to Control Native Processes

Native Image supports a subset of Java Diagnostic Command (jcmd) commands in versions with this feature. It is disabled by default and must be enabled at build time:

~~~text
--enable-monitoring=jcmd
~~~

Multiple features can be combined:

~~~text
--enable-monitoring=jcmd,jfr,heapdump,nmt,jvmstat
~~~

Find the process PID and list supported commands:

~~~bash
jcmd <PID> help
~~~

Commonly used commands:

| Command | Required build feature | Purpose |
|---|---|---|
| `Thread.print` | `jcmd` | Print threads and stack traces |
| `Thread.dump_to_file` | `jcmd` | Write thread dump to a file |
| `GC.heap_dump` | `jcmd,heapdump` | Generate an HPROF heap dump |
| `JFR.start` | `jcmd,jfr` | Start a JFR recording |
| `JFR.stop` | `jcmd,jfr` | Stop a recording |
| `JFR.check` | `jcmd,jfr` | View active recordings |
| `JFR.dump` | `jcmd,jfr` | Dump a recording to a file |
| `VM.native_memory` | `jcmd,nmt` | Print native memory report |
| `VM.command_line` | `jcmd` | View process command line |
| `VM.system_properties` | `jcmd` | View system properties |
| `VM.uptime` | `jcmd` | View uptime |

Example starting and dumping JFR:

~~~bash
jcmd <PID> JFR.start name=incident settings=profile
jcmd <PID> JFR.dump name=incident filename=/diagnostics/incident.jfr
jcmd <PID> JFR.stop name=incident
~~~

To make `jcmd -l` discover processes more easily, you can also enable `jvmstat`. On Windows, current GraalVM documentation states that Native Image jcmd is not yet supported.

## 17. Platform Differences for Heap Dumps and jcmd

The capabilities below represent notable limitations in current GraalVM JDK 25/25.5 documentation. Verify against your specific distribution and patch version.

| Capability | Linux | macOS | Windows |
|---|---|---|---|
| Heap dump support when built with `heapdump` | Yes | Yes | JDK 25 docs state heap dump generation is unsupported |
| Heap dump via `SIGUSR1` | Yes | Yes | No POSIX signal available |
| VisualVM requesting heap dump from running process | Yes | Yes | Unsupported per JDK 25 docs |
| JFR local recording in GraalVM 25.5 | Yes | Yes | Yes, writes `.jfr` file |
| JFR remote JMX via FlightRecorderMXBean | Can be enabled separately; experimental | Can be enabled separately; experimental | Not yet supported |
| JFR control via jcmd | Yes when built with `jcmd,jfr` | Yes when built with `jcmd,jfr` | Not yet supported |
| Native Memory Tracking | Yes in supported releases | Yes in supported releases | Check specific release/platform |

Oracle GraalVM JDK 25.0 documentation notes that JFR recording is not yet available on Windows, whereas GraalVM 25.5 Innovation documentation updates support for local recordings on Windows. When a project uses JDK 25.0 or another distribution, do not automatically apply conclusions from 25.5.

For Linux containers, also check whether signals are forwarded properly to the process, whether the dump volume is writable, and whether PID namespaces change the PID targeted by commands.

## 18. Distinguishing JFR and Heap Dumps from Spring Boot Actuator

Spring Boot Actuator/Micrometer and GraalVM diagnostics complement each other:

| Need | Tool to use |
|---|---|
| Tracking request rate, latency, error rate, connection pools | Actuator/Micrometer |
| Periodically exporting metrics to Prometheus/OTLP/backends | Micrometer registry |
| Analyzing CPU, allocations, GC, and threads on a timeline | JFR |
| Finding live objects and retaining references | Heap dump |
| Investigating native memory tracked by the runtime | NMT |
| Taking thread dumps or controlling JFR remotely | jcmd/JMX when supported by version |

Spring Boot can expose metrics via `/actuator/metrics` or `/actuator/prometheus` once a registry is added and endpoints are exposed. Available meters depend on the runtime and dependencies. Verify actual meters in Native Image rather than assuming every HotSpot JVM-named metric has the same meaning in the native runtime.

In particular, Actuator documentation describes the `heapdump` endpoint using HPROF on HotSpot JVM and PHD on OpenJ9. That does not prove the endpoint will produce a heap dump properly in Native Image. For a native executable, use `--enable-monitoring=heapdump` and verify directly on the exact binary.

## 19. Protecting Diagnostic Files in Production

JFR files and heap dumps can contain sensitive data. JFR can capture system properties, environment variables, socket events, and details about application activity. Heap dumps can contain objects holding tokens, sessions, request payloads, customer data, and cache contents.

Before enabling diagnostic capture in production:

- Choose a dedicated directory with restricted permissions.
- Use a volume with clear capacity limits and a retention policy.
- Do not place dump files inside directories served statically by a web server.
- Do not expose dump endpoints to the public internet.
- Restrict who can download or read files.
- Encrypt at rest/in transit according to organizational policy.
- Delete files after the investigation window.
- Strip secrets from logs and collected metadata whenever possible.

Do not expose all Actuator endpoints just to get metrics or heap dumps. Expose only the necessary endpoints and protect them with network policies or Spring Security.

## 20. Runbook: Investigating Memory Growth in Native Image

Suppose a Spring Boot container shows steadily rising RSS after hours of running. Follow this sequence:

1. **Confirm the numbers:** correlate RSS/cgroup memory, request rate, workload, heap metrics, and when growth began.
2. **Inspect JFR:** examine allocations, GC, threads, and related events in the same time window.
3. **Capture heap dumps:** take two snapshots at two timestamps with comparable workloads.
4. **Compare object graphs:** identify classes growing in count, retained size, and reference chains.
5. **Check NMT:** determine whether runtime-tracked native memory grew correspondingly.
6. **Check JNI/native libraries:** if RSS grows without explanation from heap/NMT, investigate allocations in native code, direct buffers, mmap, and thread stacks.
7. **Correlate metrics/traces:** find endpoints or requests creating many objects, holding sessions, or growing caches.
8. **Fix and rerun the same workload:** confirm heap, RSS, latency, and error rate stabilize.

Do not conclude there is a memory leak solely because RSS rises. Native Image may retain reserved heap regions, the allocator may not immediately return memory to the OS, and GC can temporarily raise RSS. Look at trends over multiple cycles and cross-check multiple data sources.

## 21. Common Errors and Resolutions

| Symptom | Possible cause | Resolution |
|---|---|---|
| `StartFlightRecording` does not work | Binary was not built with `jfr` | Add `--enable-monitoring=jfr` and rebuild |
| Cannot create JFR file | Directory does not exist or user lacks write permissions | Check path, volume, and permissions |
| JFR lacks expected events | Event unsupported, different GC, or code path never executed | Check event support matrix and workload |
| Windows cannot connect JFR via jcmd | jcmd/remote JFR unsupported on Windows | Write a local JFR file if supported by your GraalVM release |
| Cannot create heap dump on OOME | Binary missing `heapdump` or path is not writable | Build with `heapdump` and check `HeapDumpPath` |
| SIGUSR1 terminates the process | Signal handler disabled/unsupported or wrong PID | Verify Signal API, PID namespace, and platform |
| VisualVM cannot find the process | Missing `jvmstat` or incompatible tool | Build with `jvmstat` and check local attach |
| No NMT report appears | Binary missing `nmt` or `PrintNMTStatistics` not enabled | Build with `nmt` and check runtime flags |
| NMT is low but RSS is high | Allocations untracked by NMT, such as direct `malloc` in JNI | Use OS/container metrics and a native profiler |
| jcmd reports process does not exist | Wrong PID, namespace, or missing `jvmstat` for listing | Retrieve PID inside the matching host/container namespace |
| Actuator heapdump does not work as expected | Endpoint is documented for HotSpot/OpenJ9 | Use the native heapdump feature and test directly |

## 22. Lab: Enabling JFR, Heap Dump, and NMT for Spring Boot

The goal is to build a native executable equipped with sufficient diagnostics to inspect allocations, Java heap, and native memory on Linux.

### Step 1 — Add Monitoring Options

In Gradle:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat")
        }
    }
}
~~~

Or in Maven:

~~~xml
<buildArgs>
    <buildArg>--enable-monitoring=jfr,heapdump,nmt,jcmd,jvmstat</buildArg>
</buildArgs>
~~~

### Step 2 — Build the Executable

~~~bash
./gradlew nativeCompile
~~~

Or:

~~~bash
./mvnw -Pnative package
~~~

Record the GraalVM version, JDK version, OS, and architecture. Do not use a build result on one OS to conclude that tool support is identical on another OS.

### Step 3 — Run JFR

~~~bash
mkdir -p diagnostics
./application \
  -XX:StartFlightRecording="filename=diagnostics/orders.jfr,duration=3m,maxsize=256M,dumponexit=true"
~~~

Send test traffic for three minutes, then inspect:

~~~bash
jfr summary diagnostics/orders.jfr
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostics/orders.jfr
~~~

### Step 4 — Verify Heap Dump on OOME

In an isolated test environment, run:

~~~bash
./application \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=diagnostics/orders-heap.hprof
~~~

Do not intentionally exhaust memory in production to test. You can use a test workload with a bounded heap to verify the feature before deployment.

### Step 5 — Verify NMT and jcmd

Start the application with monitoring compiled in, obtain its PID, and run:

~~~bash
jcmd <PID> help
jcmd <PID> VM.native_memory
jcmd <PID> Thread.print
~~~

When JFR via jcmd is needed:

~~~bash
jcmd <PID> JFR.start name=load-test settings=profile
jcmd <PID> JFR.dump name=load-test filename=diagnostics/load-test.jfr
jcmd <PID> JFR.stop name=load-test
~~~

### Step 6 — Review Results and Save Evidence

Record:

| Item | Evidence |
|---|---|
| Native toolchain | GraalVM distribution, JDK, version |
| Target | OS, CPU architecture |
| Build flags | `--enable-monitoring` values |
| JFR | `.jfr` file, duration, event summary |
| Heap dump | `.hprof` file, capture timestamp, workload |
| NMT | Native memory report |
| jcmd | Executed commands and output |
| Runtime metrics | RSS/cgroup, heap, GC, latency, request rate |
| Data protection | Storage location, access permissions, retention |

## 23. Pre-Release Checklist for Native Binaries

- [ ] Determined whether JFR, heap dump, NMT, jcmd, or only metrics/logs are needed.
- [ ] Added monitoring features to build arguments.
- [ ] Rebuilt and verified the exact binary contains the features.
- [ ] Tested JFR on the exact GraalVM version, OS, and architecture.
- [ ] Verified heap dump works on the target platform.
- [ ] Verified jcmd/JMX and restricted remote access.
- [ ] Confirmed volume, capacity, and write permissions for diagnostics files.
- [ ] Ensured NMT is not mistaken for total RSS.
- [ ] Distinguished Java heap, native memory, and container memory.
- [ ] Combined JFR/dumps with Micrometer metrics, logs, and traces.
- [ ] Restricted access permissions and retention for diagnostic files.
- [ ] Saved version/toolchain/build flags alongside the release artifact.

## 24. Key Takeaways

JFR, heap dumps, NMT, and jcmd can still support observability for Spring Boot Native Image, but they must be selected and enabled at build time. JFR helps analyze events, CPU, allocations, and GC over time; heap dumps reveal live objects in the Java heap; NMT tracks a portion of native memory; and jcmd provides diagnostic commands compiled into the binary.

Support depends on the GraalVM version, distribution, and platform. In particular, local JFR recording on Windows changed between GraalVM JDK 25.0 and 25.5 documentation; native heap dumps and jcmd still have documented Windows limitations. Test on the exact release artifact and deployment environment.

Combine deep diagnostic tools with Actuator/Micrometer, logs, and traces. **A heap dump is not the entire process memory, NMT does not track every native allocation, and Native Image JFR does not include every HotSpot event.** Understanding each data source's scope helps operations teams find true root causes without jumping to conclusions from a single metric.

### References

- GraalVM 25.5 — JDK Flight Recorder with Native Image: https://www.graalvm.org/jdk25.5/reference-manual/native-image/debugging-and-diagnostics/JFR/
- GraalVM 25.5 — Native Memory Tracking: https://www.graalvm.org/jdk25.5/reference-manual/native-image/debugging-and-diagnostics/NMT/
- Oracle GraalVM JDK 25.0 — JFR platform note: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/debugging-and-diagnostics/JFR/
- Oracle GraalVM JDK 25.0 — Heap dump platform note: https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/guides/create-heap-dump/
- GraalVM — Create a Heap Dump from a Native Executable: https://www.graalvm.org/dev/reference-manual/native-image/guides/create-heap-dump/
- GraalVM — Java Diagnostic Command with Native Image: https://www.graalvm.org/dev/reference-manual/native-image/debugging-and-diagnostics/jcmd/
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html

Monitoring options and platform limits change across GraalVM releases. At deployment time, pin the toolchain and consult documentation for the exact distribution/version in use.
