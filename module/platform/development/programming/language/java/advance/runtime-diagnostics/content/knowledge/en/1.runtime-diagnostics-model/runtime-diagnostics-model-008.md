# 1.8 Java 21 Standard API Scope, HotSpot Tools, and Version Variability

In the **JVM diagnostics model**, the first crucial distinction is knowing whether a measurement or diagnostic command is guaranteed by **Java SE 21**, provided by **a JDK distribution**, or dependent on the **HotSpot VM**. These three layers differ in compatibility scope, implementation, operational cost, and upgrade risk. Running on Java 21 does not mean all of them share Java SE guarantees.

## Learning Objectives

After this lesson, you will be able to:
- Classify diagnostic APIs into Java SE contracts, public JDK APIs, and HotSpot-specific mechanisms.
- Choose sufficiently portable observation points before relying on VM-specific tools.
- Inspect the actual capabilities of the **JDK 21 running the application**, instead of inferring from version names or a developer laptop.
- Anticipate what needs re-testing when changing JDK patch updates, JVM vendors, deployment images, or Java versions.

## 1. Three Tiers of the Diagnostic Contract

| Tier | Java 21 Examples | Guarantee Level and Usage Scope |
| --- | --- | --- |
| **Java SE 21 (standard API)** | **java.management** with JMX, **java.lang.management.ManagementFactory**, **ThreadMXBean**, **MemoryMXBean**; **java.instrument** with standard agent interfaces | Types and behavior specified by Java SE; enables portable monitoring logic, yet individual measurement capabilities may still be optional and must be queried via API. |
| **Public JDK API, outside Java SE** | **jdk.jfr** with **Recording**; **jdk.attach** with **VirtualMachine**; **jdk.management** with **com.sun.management.HotSpotDiagnosticMXBean** | Documented by the JDK and useful on supporting JDKs; not required to exist in every Java SE implementation or custom runtime image. Public API does not equal standard Java SE API. |
| **VM tools/commands and options** | **jcmd** with **Thread.print**, **GC.heap_info**, **JFR.start**; **jstat**, **jmap**, **jhsdb**; **-XX:** flags | Syntax, command set, output format, attach permissions, cost, and presence depend on JDK, VM, platform, and release. Must be verified against the target process. |

Per the Java 21 API specification, **java.*** modules are part of Java SE, while **jdk.*** modules provide JDK-specific APIs. However, **package names alone are not enough to classify**: package **com.sun.management** is a JDK API exported by module **jdk.management**; conversely, **jdk.internal.*** packages are not public contracts for applications to depend on. Do not work around this by arbitrarily opening internal modules with **--add-exports** or **--add-opens** solely for diagnostics.

Also separate **standard interfaces** from **optional features**. For example, **ThreadMXBean** is a standard API, yet measuring CPU time or lock monitoring may not be supported/enabled by the VM. Check methods like **isThreadCpuTimeSupported()**, **isThreadCpuTimeEnabled()**, and **isSynchronizerUsageSupported()** before relying on the measurement. An API's existence does not guarantee every metric produces data.

## 2. Portable Observation Points: Java SE 21

**JMX / ManagementFactory** fits the foundational in-app data-collection layer: JVM identity, uptime, memory/GC info, platform thread count, platform thread deadlocks, class loading info, and certain counters. Internal access via MXBeans requires no attach to another process; remote JMX access is a separate operational setup requiring authentication, encryption, and network restrictions.

The complete example below uses Java SE APIs to collect data, and uses only **ModuleFinder** (also Java SE) to check whether the JFR module exists in the runtime image.

**File DiagnosticCapabilities.java**

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import java.lang.module.ModuleFinder;

public class DiagnosticCapabilities {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("Java feature: " + Runtime.version().feature());
        System.out.println("VM name: " + runtime.getVmName());
        System.out.println("VM vendor: " + runtime.getVmVendor());
        System.out.println("Process ID: " + ProcessHandle.current().pid());
        System.out.println("Platform threads: " + threads.getThreadCount());
        System.out.println("Thread CPU time supported: "
                + threads.isThreadCpuTimeSupported());
        System.out.println("JFR module installed: "
                + ModuleFinder.ofSystem().find("jdk.jfr").isPresent());
    }
}
~~~

Compile and run with **JDK 21**:

~~~bash
javac --release 21 DiagnosticCapabilities.java
java DiagnosticCapabilities
~~~

Label lines always appear in the order coded; **values** for VM, vendor, PID, thread count, and the two boolean flags vary with the environment. **--release 21** checks this example's standard Java 21 API subset; it does not verify the availability of **jcmd** or JDK-specific modules. **ModuleFinder.ofSystem()** answers whether **jdk.jfr** is in the image, not that a recording will start successfully or that external attach is allowed.

**An easily missed Java 21 limitation:** **java.lang.management.ThreadMXBean** only monitors **platform threads**, not **virtual threads**. Therefore thread counts, thread IDs, CPU times, stack snapshots, and deadlock results from this MXBean do not represent all virtual threads in an application. For applications using virtual threads, combine diagnostic mechanisms that support them (such as corresponding JFR events when available and enabled) and verify the specific version.

**java.instrument** is the standard API for agents to interact with classes when permitted; however, how **dynamic agent attach/load** works and related warnings belong to JDK/VM deployment policy, not a guarantee that every JVM allows attaching an agent to any process.

## 3. Public JDK APIs: More Powerful, Yet Conditional

**Java Flight Recorder (JFR)** is a key choice when needing a time-ordered event stream: GC, allocations, I/O, locks, CPU, classes, threads, or custom application events. Java 21 provides the public APIs **jdk.jfr.Recording**, **jdk.jfr.Event**, and file-reading APIs in **jdk.jfr.consumer**. These are **JDK-specific** APIs, distinct from standard **java.management** modules. Event sets, event names/attributes, settings, and overhead must be verified on the actual JDK.

The standalone example below demonstrates creating a short recording on **JDK 21 with JFR**. This program actively records its own data without attaching to another JVM.

**File JfrSample.java**

~~~java
import java.nio.file.Path;
import jdk.jfr.Recording;

public class JfrSample {
    public static void main(String[] args) throws Exception {
        Path destination = Path.of("sample.jfr");

        try (Recording recording = new Recording()) {
            recording.setName("short-sample");
            recording.start();
            Thread.sleep(1000);
            recording.stop();
            recording.dump(destination);
        }

        System.out.println("Created sample.jfr");
    }
}
~~~

~~~bash
javac --add-modules jdk.jfr JfrSample.java
java --add-modules jdk.jfr JfrSample
jfr summary sample.jfr
~~~

When the first two commands succeed, the program prints exactly **Created sample.jfr** and creates **sample.jfr** in the working directory. The **jfr summary** command then prints dynamic statistics depending on recorded events and the JDK build. **--add-modules jdk.jfr** explicitly declares the JDK dependency; images lacking this module cannot run the example. Do not mechanically apply **javac --release 21** to code using non-Java-SE APIs without checking JDK compilation behavior and module configuration.

Other JDK API examples to distinguish:
- **com.sun.management.OperatingSystemMXBean** extends OS/process info; check JDK Javadoc for methods and metric semantics.
- **com.sun.management.HotSpotDiagnosticMXBean** can support taking heap dumps and diagnostic options where the VM supports it; this is not a cross-JVM contract.
- **com.sun.tools.attach.VirtualMachine** in **jdk.attach** provides the attach mechanism; having the class does not guarantee the target process allows attach, has matching permissions, or permits dynamic agents.

Do not rely on internal reflective APIs, VM memory addresses, or parsing tool text output as though it were a stable format. When programmatic parsing is needed, prefer strongly typed APIs or documented supported formats/readers.

## 4. HotSpot/JDK Tools: Identify First, Execute Second

**Terminology note:** **HotSpot** is a JVM implementation. **JDK** is the distribution comprising runtime, tools, and modules. Many OpenJDK builds use HotSpot yet differ in packaging and patches; other JVMs like OpenJ9 have their own tools/capabilities. Having **Java 21** does not guarantee every executable in the **bin** directory is present.

| Tool or Mechanism | What It Is For | Scope and Important Conditions |
| --- | --- | --- |
| **java -version**, **java --list-modules** | Inspect the invoked runtime and modules in the image | Run on the exact machine/container; **java** on PATH may differ from the JVM running the app. |
| **jcmd -l**, **jcmd PID help** | Discover JVMs and list available commands | Requires the tool, attach mechanism/permissions, and process visibility; the command list is determined by the target JVM. |
| **jcmd PID VM.version / VM.command_line** | Check the VM and actual startup arguments | Usually helpful before interpreting metrics; do not infer configuration solely from a terminal java command. |
| **jcmd PID Thread.print -l** | Stack/lock snapshot of threads supported by the command | Can be slow with very many threads; not automatically a complete dump of all virtual threads. |
| **jcmd PID GC.heap_info** | General overview of heap/GC | Cannot replace a heap dump; still has an impact on the process. |
| **jcmd PID JFR.start / JFR.check / JFR.dump** | Collect, check status, and export recordings | Requires target JFR support, proper permissions, and disk space; files are created on the filesystem seen by the target JVM. |
| **jfr summary / jfr print** | Read and filter JFR files | Requires a reader tool compatible with the recording format; data/events depend on collection settings. |
| **jstat**, **jmap**, **jstack**, **jhsdb** | Various statistics/heap/thread/Serviceability Agent operations | Supported tools and modes vary by VM, OS, and JDK. Some operations pause or heavily impact the JVM; do not use blindly in production. |
| **-XX:...**, Native Memory Tracking | HotSpot-specific options and statistics | VM-dependent; NMT must be enabled via its option at JVM startup—never assume data is always present. |

### Workflow to Identify a Real Process

The example commands below use **PID 12345 as an illustration**; replace with the actual PID obtained from the target environment's process management tool.

~~~bash
java -version
javac -version
java --list-modules
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 help
jcmd 12345 help Thread.print
~~~

The order is deliberate: know **which tool you are invoking** first, know the **target VM** next, and only then discover commands **the target supports**. If **jcmd -l** does not list the process, do not conclude the application is not running: PID namespaces/containers, JVM user, attach mechanisms, trimmed runtime images, and permissions can all affect discovery.

**Do not run a JDK tool on the host and assume it can attach to a JVM inside a container.** Check PID namespaces, OS permissions, the filesystem used for attach, and where output files appear. Images built with **jlink** or minimal runtime images may exclude **jcmd**, **jfr**, **jmap**, and strip out JDK modules unnecessary for the application.

## 5. Selecting Tools by Problem and Cost

A diagnostic pass can escalate in impact:

1. **Confirm context:** incident time, PID, VM name/vendor/version, uptime, startup flags, container, and application load. Running **java -version** in a shell only checks the shell environment, not the target JVM.
2. **Low-intrusion observation:** existing JMX/MXBean numbers, application metrics, logs, and informational commands like **VM.version**; align measurements with time and load.
3. **Time-bounded collection:** JFR with defined settings, duration, and target file; thread dumps when investigating stalls or deadlocks. Read the impact documentation of each **jcmd** diagnostic command.
4. **Controlled deep dive:** class histograms, heap dumps, dynamic agents, debuggers/Serviceability Agent, or VM flag changes only when current signals justify the cost and effects on latency, memory, CPU, and storage.

Example assuming a **HotSpot/JDK 21** JVM supports these exact commands:

~~~bash
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=/tmp/triage.jfr
jcmd 12345 JFR.check
~~~

Once the recording finishes and the file exists, run **jfr summary /tmp/triage.jfr** where the file is accessible and a compatible JFR tool is installed. **/tmp/triage.jfr** is a path from the **target JVM's** perspective; in containers, you may need to copy the file out to an analysis environment.

**Do not treat these commands as "zero overhead."** Even **Thread.print** has impact scaling with thread count; **GC.heap_info** has impact; **GC.class_histogram** and **GC.heap_dump** are classified by JDK 21 documentation as high impact depending on heap size/contents. Heap dumps can be huge, pause the application, consume disk, and contain sensitive data. JFR is generally suitable for time-bounded observation, yet overhead still depends on events and settings, especially profile/stack traces.

When remote collection is required, distinguish **remote JMX** (opening a monitoring channel with authentication and transport protection) from **jcmd local attach**. The two mechanisms have different permission models and operational surfaces. Never open public JMX ports or relax attach permissions just to try diagnostics.

## 6. Important Changes Across Versions

Distinguish at least **four axes of change**:

| Axis | What Can Change | Verify Before Use |
| --- | --- | --- |
| **Java SE 21 vs. other Java SE versions** | APIs, language, feature limits, and platform compatibility rules | Javadoc and specs for the **exact feature release**; compile Java SE parts with **--release 21** when targeting Java 21. |
| **JDK vendor, VM implementation** | Presence/absence of JFR, attach providers, extended MXBeans, diagnostic commands, default settings | **VM.version**, modules in image, vendor docs, capability checks inside the target process. |
| **Updates and configuration within JDK 21** | Bug fixes, permissions, options, diagnostics/JFR behavior, resource limits | Record **full runtime version + vendor + flags**, not just **21**; re-test procedures after updates. |
| **Deployment environment** | Stripped tools in image, removed modules, container permissions, filesystem, PID, and security policy | Test inside the actual container/host running the service; verify modules, executables, permissions, and writable paths. |

Specifically in **JDK 21**, **JEP 451** introduces **warnings when agents are loaded dynamically** to prepare for stricter policies in future releases. Do not equate the JDK 21 warning with all dynamic agents already being blocked in JDK 21. If a product needs instrumentation, prefer explicitly specifying agents loaded at startup vs. via attach, check target JVM policies, and test before upgrading.

With **virtual threads** standardized in Java 21, observability must be viewed per specific API and tool: standard **ThreadMXBean** sees only platform threads, whereas JFR/other tools can supply additional data according to the JDK build's capabilities. Do not use total platform-thread count to claim how many virtual threads are active.

Also do not treat **text output formats** printed by **jcmd**, **jstack**, or **jmap** as a stable protocol for long-term automation. If automation is required, record tested versions, check exit status, handle missing commands/columns, and provide fallback branches; avoid parsers tied to fixed line positions.

## 7. Compatibility Strategy Pattern for Diagnostic Tooling

A library or operational runbook can separate into three tiers:

- **Java SE baseline first:** read standard MXBeans, structured logs, and application metrics; check capability flags for each measurement.
- **Upgrade when capability exists:** if **jdk.jfr** is present and a test recording succeeds, enable JFR per policy; if the target JVM permits it and **jcmd** exists, use diagnostic commands actually listed by **jcmd PID help**.
- **Explicit fallback:** when modules/tools/permissions are missing or the VM is non-HotSpot, continue observing via the baseline; explicitly record which evidence could not be gathered instead of outputting 0 or reporting "no issues."

Example: a service on JDK 21 HotSpot in development has full **jcmd + jfr**, while the production image contains only runtime modules. Both environments may share identical application bytecode and Java feature version, yet shell-based diagnostics differ. The right solution is declaring operational requirements at image packaging time or provisioning supported observability, rather than coupling business logic to external executables.

For diagnostic outputs, record **timestamp, PID, Java feature/full version, VM name/vendor, source (API or command), capability set, and collection configuration**. That makes data comparable across upgrades and lets readers tell whether an empty field means "unsupported/not collected" or a true zero.

## 8. Common Misconceptions

1. **"An API is in JDK 21, so it is Java SE 21."** False: **jdk.jfr**, **jdk.attach**, and **jdk.management** are JDK-specific; distinguish them from **java.management** or **java.instrument**.
2. **"The JVM is Java 21, so `jcmd` is definitely available."** False: commands are JDK tool components that may be omitted from images or unusable with the current VM/permissions.
3. **"ThreadMXBean counts all threads."** False in Java 21: it manages only platform threads, excluding virtual threads.
4. **"No deadlock in MXBean means no synchronization problem."** False: API scope, lock types, and virtual threads govern what is detected; lack of a signal does not prove system health.
5. **"If a command runs, it is safe in production."** False: dump/heap/agent commands can induce pauses, heavy I/O, and sensitive data exposure; assess impact first.
6. **"Patch updates or VM changes do not affect scripts."** False: command lists, flags, text formats, events, and attach conditions must be re-verified.
7. **"Module present means the feature works."** False: permissions, runtime flags, VM policies, configs, and filesystems can still block execution.

## 9. Self-Check

- If you want platform thread counts and memory from **multiple Java 21 JVMs**, start with **java.management** and capability checks. If an event timeline is needed, consider **jdk.jfr** after verifying the runtime.
- If **jcmd** exists on your dev machine but is missing in the production container, inspect the image type and tools in the container; do not infer from the Java version or dev machine PATH.
- If a metric disappears after enabling virtual threads or switching VMs, ask **what target that API measures, whether it is supported, and which runtime produced the data** before concluding application behavior changed.

**Applicability criterion:** for every diagnostic metric/command, you can clearly state **which contract guarantees it**, **where it can run**, **what conditions/permissions are required**, **collection overhead**, and **how to handle its absence or change**. This boundary is essential for designing a reliable JVM diagnostics model.

## Primary References

- [Java SE 21 & JDK 21 API Specification — distinguishing Java SE and JDK modules](https://docs.oracle.com/en/java/javase/21/docs/api/)
- [ThreadMXBean, Java SE 21 — platform threads scope and optional capabilities](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [jcmd, JDK 21 — diagnostic commands and impact levels](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [jfr, JDK 21 — reading JFR files](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [jlink, JDK 21 — custom runtime images](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [JEP 451 — warnings for dynamic loading of agents in JDK 21](https://openjdk.org/jeps/451)