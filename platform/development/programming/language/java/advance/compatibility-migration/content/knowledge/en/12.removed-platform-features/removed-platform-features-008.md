# javah, Legacy Monitoring Tools, and How to Replace Them with Supported Tools

When upgrading a Java application that has existed for many years, migration errors do not come only from source code or libraries. Build scripts may still call the javah command to generate JNI headers; operations teams may rely on jhat or jvisualvm bundled with an older JDK, pre-JDK 9 GC logging flags, or a diagnostic script that runs only with tools from a specific JVM vendor. In newer JDKs, those executables, options, or packaging mechanisms may have been removed, separated into standalone products, or changed in usage.

**The goal of this lesson** is to identify legacy Java tools, determine their support status on the target JDK, and replace them with actively maintained mechanisms. The two main areas of work are replacing javah in the JNI build process and replacing legacy monitoring/diagnostic approaches with jcmd, Java Flight Recorder (JFR), JDK Mission Control (JMC), VisualVM, Eclipse Memory Analyzer (MAT), JMX, and the application's observability stack.

What must be preserved is **the ability to produce the right artifacts, collect critical operational information, and verify results on the target JDK**. Do not assume all tools familiar from JDK 8 have been removed: some remain supported in newer JDKs or only changed how they are packaged.

## 1. Categorizing Tools Before Migration

An executable disappearing from the bin directory does not necessarily mean the corresponding capability is gone. There are at least four situations:

| Situation | Characteristics | Migration approach |
|---|---|---|
| Tool removed | No longer in the target JDK | Use an API, compiler option, or replacement tool |
| Tool separated from JDK | Still usable, but as a standalone product | Install separately, pin versions, and manage lifecycle |
| Tool changed syntax or output | Command still exists; flags/format changed | Update scripts and parsers; verify at runtime |
| Tool still supported | Still included in many newer JDKs | Can continue to be used within supported scope |

Typical examples:

- **javah** has been removed since **JDK 10**. Replace it with the **javac -h** option, available since JDK 8.
- **jhat** (Java Heap Analysis Tool) was removed starting in **JDK 9**. Eclipse MAT or VisualVM can be used to analyze heap dumps.
- **jvisualvm** is no longer bundled by default in many modern JDKs. **VisualVM** continues to be released and installed independently.
- **JDK Mission Control** is a JFR analysis tool that can be installed separately; availability of the jmc command depends on the distribution and packaging.
- **jcmd, jstack, jmap, jstat, jinfo, jconsole** may still exist in newer JDKs. Do not lump all of them into the “removed” category.
- **Pre-JDK 9 GC logging** flags must be mapped to unified logging using the **-Xlog** syntax; do not copy old configurations verbatim without verification.

The actual set of tools depends on version, vendor, operating system, permissions, and runtime image. A minimal image created with jlink or a runtime-only container may lack diagnostic tools provided by a full JDK of the same version.

## 2. Finding Where the System Depends on Legacy Tools

Before making changes, you must know who invokes the tool and who consumes its output:

| Source | What to look for | Example |
|---|---|---|
| Build script | Tasks generating JNI headers or calling executables | Gradle Exec, Maven plugin, shell calling javah |
| CI/CD | JDK/tool paths and diagnostic steps | Jenkins, GitHub Actions, GitLab CI |
| Container/image | Which tools are packaged | Runtime image lacking jcmd |
| Operations runbook | Incident investigation commands | jhat, jmap, jstack, jvisualvm |
| JVM option | Legacy logging or agent flags | -Xloggc, -XX:+PrintGCDetails, -agentlib:hprof |
| Monitoring | Collectors, parsers, dashboards | JDK 8 GC log parser |
| Access permissions | Who can attach to the JVM, where dumps are stored | Service account, filesystem, policy |

A quick way to search in the repository:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'javah|jhat|jvisualvm|jmc|jstack|jmap|jinfo|jstat|jconsole|jcmd' .

rg -n --hidden -g '!**/.git/**' \
  -- '-Xloggc|-XX:\+PrintGC|-agentlib:hprof|-Xprof|-verbose:gc|-Xlog:' .
~~~

Search results in source code are only part of the inventory. Commands may also reside in application server scripts, service manager configurations, shared CI pipelines, cron jobs, or runbooks not stored in the repository. For each usage point, record the purpose, owner, inputs, outputs, environment, and mechanism for verifying correct results.

In particular, distinguish between the JDK running the build, the JDK running the application, and the JDK containing diagnostic tools. The java version in a developer's terminal does not prove the runtime of a production service.

## 3. What Was javah Used For?

Java Native Interface (JNI) allows Java methods to call native code such as C/C++. A native method is declared with the native keyword and has no Java method body:

~~~java
package demo.bridge;

public final class NativeMath {
    public native int add(int left, int right);
}
~~~

On the C/C++ side, the implementation must comply with the JNI ABI: symbol name, export macros, JNI types, and environment parameters. Previously, the workflow was typically:

~~~bash
javac -d build/classes src/demo/bridge/NativeMath.java
javah -jni -classpath build/classes -d build/headers demo.bridge.NativeMath
~~~

javah read the compiled class information and generated a header containing the corresponding native symbol declarations. Starting in JDK 8, javac supported the -h option to generate native headers during compilation. javah was removed in JDK 10, so builds using javah can fail right at the header generation step when upgrading to JDK 17 or 21.

Common error message:

~~~text
javah: command not found
~~~

On Windows, a message may appear stating that the javah command is not recognized. The fix is to integrate **javac -h** into the compilation step, instead of continuing to download an old javah executable or writing headers manually.

## 4. Replacing javah with javac -h via a Complete JNI Example

### 4.1. Demo Structure

~~~text
jni-demo/
├── src/demo/bridge/NativeMath.java
├── native/native_math.c
└── build/
    ├── classes/
    ├── headers/
    └── native/
~~~

File src/demo/bridge/NativeMath.java:

~~~java
package demo.bridge;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    public native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(new NativeMath().add(2, 3));
    }
}
~~~

System.loadLibrary accepts the logical name of the native library. The actual file name depends on the OS, for example libnative_math.so on Linux, libnative_math.dylib on macOS, or native_math.dll on Windows. In addition to the file name, the native library may depend on other operating system libraries.

### 4.2. Generating Class Files and Headers Simultaneously

Inside the jni-demo directory:

~~~bash
mkdir -p build/classes build/headers build/native

javac \
  -h build/headers \
  -d build/classes \
  src/demo/bridge/NativeMath.java
~~~

Meaning:

- **-h build/headers:** where javac places the generated native headers.
- **-d build/classes:** where javac places the class files.
- The compiler reads native method declarations and generates the corresponding headers, synchronized with the Java bytecode just produced.

The header is typically named demo_bridge_NativeMath.h and contains declarations similar to:

~~~c
#include <jni.h>

#ifdef __cplusplus
extern "C" {
#endif

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add
  (JNIEnv *, jobject, jint, jint);

#ifdef __cplusplus
}
#endif
~~~

This is an abbreviated illustration; an actual header may also contain include guards, comments, and other details. **The header generated by javac is the primary reference**, because symbol names for overloaded methods, packages, classes, and parameter types must match exactly.

### 4.3. Writing the C Implementation

File native/native_math.c:

~~~c
#include "demo_bridge_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add(
    JNIEnv *env,
    jobject self,
    jint left,
    jint right
) {
    (void)env;
    (void)self;
    return left + right;
}
~~~

An instance native method receives jobject as its second parameter; a static native method receives jclass in that position. JNI provides types such as jint, jlong, jstring, and jbyteArray. Mixing incompatible C/C++ types or mismanaging JNI resources can cause crashes, memory leaks, or data corruption.

### 4.4. Building the Native Library on Linux

GCC example:

~~~bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_math.c \
  -o build/native/libnative_math.so
~~~

On macOS and Windows, use the appropriate native compiler, library creation flags, OS-specific JNI header directory (darwin or win32), output file name, and linker mechanism. Do not copy the Linux GCC command verbatim across all platforms.

Run on Linux:

~~~bash
java \
  -Djava.library.path=build/native \
  -cp build/classes \
  demo.bridge.NativeMath
~~~

Output:

~~~text
5
~~~

The -Djava.library.path flag must appear before the main class name. In real deployments, also check the native dependency graph and compatibility between the JVM architecture and the shared library (32/64-bit, CPU architecture, ABI).

### 4.5. JNI Errors Commonly Exposed After Migration

| Symptom | Possible cause | How to verify |
|---|---|---|
| javah does not exist | JDK 10+ removed javah | Switch the task to javac -h |
| Header is not generated | Wrong source set, task, or output path | Inspect javac output and header directory |
| Missing jni.h when building C | Include path points to the wrong JDK | Check JAVA_HOME/include and OS subdirectory |
| UnsatisfiedLinkError: no native_math | JVM cannot find the shared library | Check java.library.path, file name, and loader |
| UnsatisfiedLinkError with native method name | Exported symbol mismatches JNI descriptor or native version | Compare header against exported symbols |
| Native crash | Wrong ABI, pointer, reference lifetime, or thread issue | Collect crash logs and inspect native code |
| Runs on Linux but fails on Windows | Native built for a single platform only | Build and test artifacts for each platform |

When methods are overloaded, JNI has signature-based symbol mangling rules. Do not guess function names by concatenating strings; use the exact header generated by the compiler. The JVM successfully loading the native library does not itself prove that every JNI method in the library has a matching implementation.

## 5. Integrating Header Generation into Gradle and Maven

In a project with a build tool, the header generation step must be managed as an output of Java compilation and must run before the native code build step. Do not keep a separate javah task just to run JDK 8 alongside it.

### 5.1. Gradle

For a Gradle Java project, you can configure compiler arguments or JavaCompile's native header output API depending on the capabilities of the Gradle version in use. Illustrative Groovy DSL configuration:

~~~groovy
tasks.named("compileJava", JavaCompile) {
    options.compilerArgs += [
        "-h",
        layout.buildDirectory.dir("generated/jni-headers")
            .get().asFile.absolutePath
    ]
}
~~~

This is an illustrative configuration. On Gradle versions with a dedicated native header directory API, use the official API so Gradle recognizes the output for incremental builds and the build cache. Verify that compiler args are not duplicated with existing configuration.

The native build task must depend on the header generation task. If compileJava is marked UP-TO-DATE yet the headers were deleted by an external step outside Gradle, the native build may fail; declaring outputs and dependencies accurately prevents this.

### 5.2. Maven

With the Maven Compiler Plugin, you can pass -h to javac in modules containing JNI declarations. Example:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>-h</arg>
      <arg>target/generated/jni-headers</arg>
    </compilerArgs>
  </configuration>
</plugin>
~~~

Verify that the output directory exists or is created by the plugin/compiler appropriately for the current version. In a multi-module project, this configuration should only be applied to modules with native methods. Check compile executions, profiles, and build order so the native compiler always receives the latest headers.

### 5.3. Controlling the Toolchain

If building with JDK 21 while the product still supports Java 17, specify the target source/API/bytecode release, for example via --release 17, and test the native library on the exact target runtime. A header generated by a newer javac does not make the native library portable across every OS or architecture.

There is no need to commit auto-generated headers to the repository if the build can reproduce them deterministically; if there is a reason to publish headers as an API for native partners, tie them to the library version and compatibility policy.

## 6. jhat and the Modern Heap Dump Analysis Workflow

jhat was a legacy tool used to browse Java heap dump data through a web interface. It was removed starting in JDK 9. The operational needs remain: capturing heap dumps, analyzing the object graph, retained heap, GC roots, and finding where references are held causing memory leaks.

### 6.1. Capturing Heap Dumps on Newer JDKs

With HotSpot/OpenJDK and appropriate attach permissions:

~~~bash
jcmd <pid> GC.heap_dump /secure/dumps/app-heap.hprof
~~~

You can configure automatic heap dump generation on OutOfMemoryError:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/secure/dumps \
  -jar app.jar
~~~

Heap dumps can be very large, consume time/I/O, and cause pauses during generation. The file may also contain sensitive data from the heap such as tokens, credentials, or personal information. Restricted access permissions, sufficient disk space, retention duration, deletion procedures, and secure transfer locations are required. Never commit dumps to a repository or attach them publicly.

### 6.2. Analyzing with Eclipse MAT and VisualVM

**Eclipse Memory Analyzer (MAT)** is well-suited for analyzing retained heap, dominator trees, paths to GC roots, and many memory leak scenarios on large heap dumps.

**VisualVM** can display memory, threads, profiling, and open heap dumps depending on version/plugins. With modern JDKs, install and pin an appropriate standalone VisualVM release instead of relying on the jvisualvm binary bundled in JDK 8.

Not every tool replaces jhat's UI or features 1:1. What needs to be verified is the incident investigation workflow: whether dumps can be generated, transferred, opened in the chosen tool, and used to answer leak questions.

### 6.3. Do Not Confuse the HPROF Format with the HPROF Agent

The .hprof file remains widely used as a **heap dump format**. The removal of the jhat tool does not mean the .hprof format is obsolete. Conversely, the legacy profiler agent such as -agentlib:hprof is a separate mechanism and should not be assumed to be supported across newer JDKs. For CPU/allocation profiling needs, JFR and supported profilers are usually more appropriate.

## 7. Centralizing JVM Diagnostics with jcmd

jcmd is a multi-purpose tool on many HotSpot/OpenJDK JVMs. Instead of hardcoding a set of commands from an older JDK, you can query the current JVM directly to see which diagnostic commands it supports.

~~~bash
jcmd -l
jcmd <pid> help
~~~

Commonly used commands:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

| Need | Common approach | Notes |
|---|---|---|
| Inspect runtime | VM.version, VM.command_line | Must select the correct PID |
| View JVM flags | VM.flags, VM.flags -all depending on JDK | Some flags are vendor-specific |
| View system properties | VM.system_properties | May contain secrets |
| Thread dump | Thread.print | Output can be very large |
| Heap summary | GC.heap_info | Does not by itself prove a memory leak |
| Class histogram | GC.class_histogram | Can consume resources or cause a pause |
| Heap dump | GC.heap_dump | Large and sensitive file |
| Flight recording | JFR.start, JFR.check, JFR.dump, JFR.stop | Requires controlling duration, events, and permissions |

Not every diagnostic command exists across all releases/vendors. When exact syntax is needed, run jcmd <pid> help <command> on the exact runtime. Some diagnostic operations trigger safepoints/GC or increase overhead; do not run them arbitrarily in production.

### 7.1. jmap, jstack, jstat, and jinfo Have Not All Been Removed

These tools remain useful on many JDKs:

- **jstack** collects thread dumps; jcmd Thread.print is another option in many situations.
- **jmap** provides several memory/heap operations; jcmd GC.heap_info, GC.class_histogram, or GC.heap_dump can cover several of those needs.
- **jstat** observes JVM/GC statistics in its own way; there is no single jcmd command that replaces all of its periodic sampling capabilities.
- **jinfo** reports certain flags and configurations; much of that information can also be viewed via jcmd.
- **jconsole** is a JMX GUI tool that may be shipped with a full JDK; it may be absent in minimal images.

Choose tools based on the data actually needed and runtime constraints. Switching to jcmd provides a unified invocation model, but it is not a mandatory rule to replace every older executable.

## 8. Java Flight Recorder and JDK Mission Control

**Java Flight Recorder (JFR)** is a mechanism for recording JVM/application events over time. Depending on configuration and runtime, JFR can collect data on CPU execution, allocations, garbage collection, threads, lock contention, and I/O. It helps investigate phenomena not easily visible through a single heap snapshot or thread dump.

**JDK Mission Control (JMC)** is the tool for analyzing JFR recordings. JMC is typically managed as a separate product/tooling package depending on the vendor; do not assume every JDK image includes jmc.

### 8.1. Capturing a Short Recording

Example on a JDK supporting JFR:

~~~bash
jcmd <pid> JFR.start \
  name=migration-check \
  settings=profile \
  duration=60s \
  filename=/secure/recordings/migration-check.jfr

jcmd <pid> JFR.check
~~~

You can use JFR.dump to export a running recording; check the diagnostic command help on the target runtime for exact parameters. Open the .jfr file with JMC or a compatible tool to inspect the timeline, samples, allocations, GC, and related events.

| Symptom | What JFR can help analyze |
|---|---|
| High CPU | Execution samples and stack traces |
| High allocation | Classes/methods allocating objects and allocation events |
| Long GC pauses | GC timeline, heap, and GC phases |
| Blocked threads | Lock contention and thread states |
| Intermittent latency | Thread/I/O events and correlation over time |
| Hard-to-reproduce incidents | Short recordings around the incident window |

JFR does not replace all long-term metrics or distributed tracing. Recordings may contain method/class names, paths, arguments, or application data depending on enabled events; protect them as diagnostic artifacts. Overhead depends on events, settings, sampling, and duration, so measure on staging before applying profile recordings in production.

## 9. Long-Term Monitoring via JMX and Telemetry

A runbook that only instructs operators to open a GUI on the server is insufficient for reliable monitoring. The system needs metrics, alerts, logs, and traces maintained throughout the JDK migration.

### 9.1. JMX

Java Management Extensions (JMX) allows the JVM and applications to expose MBeans for memory pools, GC, threads, class loading, and business components. JConsole/VisualVM can consume JMX, while exporters/collectors can scrape data into centralized monitoring systems.

If remote JMX is needed, enforce authentication, TLS or an equivalent protection layer, access permissions, and network exposure controls. Do not enable a public JMX endpoint with authentication disabled merely for diagnostic convenience.

### 9.2. Metrics, Logs, and Traces

Signals typically needing to be preserved across migration:

- Heap/non-heap memory, memory pools, and memory pressure per instance.
- GC pauses, frequency, throughput, or allocation according to the GC/JDK in use.
- Thread count, thread pool saturation, and queue depth.
- Request rate, error rate, latency percentiles, timeouts, and retries.
- Structured logs, cross-service traces, and deployment version metadata.

Micrometer, OpenTelemetry, or framework-appropriate exporters can forward metrics/traces to the observability system. They are not built-in JDK executables. Cross-check dependency versions, exporters, metric names/labels, and dashboards after upgrading.

An application that runs successfully yet loses metrics or alerts after migration still creates serious operational risk.

## 10. Migrating Legacy GC Logging to Unified Logging

An application running on JDK 8 might use:

~~~text
-verbose:gc
-XX:+PrintGCDetails
-XX:+PrintGCDateStamps
-Xloggc:/var/log/app/gc.log
~~~

Starting in JDK 9, HotSpot uses unified logging with the -Xlog syntax. Example on a newer JDK:

~~~bash
java \
  -Xlog:gc*:file=/var/log/app/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

This is an equivalent-purpose configuration, not a byte-for-byte mapping of every old flag. gc* selects GC-related tags; file and decorators control the output destination and metadata. Detail level and format may differ across JDK/GC versions, so parsers or dashboards relying on old logs must be tested.

Migration procedure:

1. Record old options, log paths, rotation/retention, and parsers in use.
2. Verify the -Xlog syntax for the exact target JDK vendor/release.
3. Run a test, confirming the JVM does not reject the option and the log file is created.
4. Generate a representative GC workload and inspect log content/volume.
5. Confirm dashboards, alerts, and log collectors still operate properly.

Some old flags may be mapped, emit warnings, or be removed depending on version. Do not use -XX:+IgnoreUnrecognizedVMOptions as a default workaround; ignoring flags can silently drop critical logging or tuning.

Example combining GC and safepoint logging:

~~~bash
java \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

GC logs serve time-series progression analysis, whereas jcmd GC.heap_info only gives a snapshot at invocation time. Do not treat the two sources as equivalent.

## 11. Checking Tool Availability on the Target JDK

In Linux/macOS environments:

~~~bash
command -v java
command -v javac
command -v jcmd
command -v jconsole
java -version
javac -version
~~~

In PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
Get-Command jcmd -All
Get-Command jconsole -All
java -version
javac -version
~~~

If multiple JDKs exist, invoke via the explicit path:

~~~bash
"$JAVA_HOME/bin/jcmd" -l
"$JAVA_HOME/bin/javac" -version
~~~

You must check the deployment environment itself. Having jcmd on a build machine does not prove the application's runtime image also includes it. When a production container lacks tooling, an appropriately authorized debug image/diagnostic sidecar or a pre-designed telemetry channel may be needed.

### 11.1. When jcmd Cannot Attach

| Symptom | What to check |
|---|---|
| Process not visible | PID namespace, user, container, and whether the process has already exited |
| Permission denied | OS permissions, owner, and attach policy |
| Attach disabled | JVM configuration and security policy |
| Command does not exist | jcmd <pid> help, JVM vendor/version |
| Dump/recording not written | Directory permissions, disk space, read-only filesystem |
| Output from wrong process | Overlapping PID across namespaces or wrong container |

Do not arbitrarily expand permissions of a production process just to run diagnostic commands. Record the constraints and use an authorized diagnostic channel.

## 12. Java 8 to JDK 21 Migration Scenario

Suppose a Java 8 application uses JNI and operates relying on jhat and a legacy GC log parser. The target is JDK 21.

### Step 1: Lock Down the Baseline

Record the JDK/vendor/OS/architecture, JNI header generation command, native library location, heap dump output/owner, GC logging flags, and related dashboards. Create representative JNI functional tests and operational metric baselines.

### Step 2: Migrate the JNI Build

Replace the task calling javah with javac -h, generate headers from source, rebuild the native library against the new headers, and verify exported symbols. Run System.loadLibrary and native method tests on the exact target OS/architecture/JDK.

### Step 3: Replace Heap Analysis

Set up a protected heap dump storage location, use jcmd GC.heap_dump or HeapDumpOnOutOfMemoryError, and test opening the dump with Eclipse MAT/VisualVM. Update the runbook: who is authorized to generate dumps, storage location, transfer procedure, and deletion timeline.

### Step 4: Migrate Logging and Observability

Convert GC flags to -Xlog; confirm logs are collected and dashboards work. Add JFR/JMC for deep investigation while maintaining long-term metrics/alerts via JMX or application telemetry.

### Step 5: Test on the Target JDK

Run compilation, unit/integration tests, JNI smoke tests, realistic workloads, thread dumps, heap dumps, and a short JFR recording in a controlled environment. Distinguish application bugs, native ABI issues, tooling issues, class file issues, and attach permissions.

### Step 6: Rollout

Deploy by instance group or environment, monitoring error rates, crashes, native load errors, GC pauses, latency, and telemetry ingestion. Keep a rollback plan ready if stability evidence is not yet sufficient.

## 13. Common Mistakes

- **Continuing to call javah from an old JDK:** mixes build toolchains, is hard to control, and does not fix the root issue; switch to javac -h.
- **Writing JNI headers manually:** error-prone for symbol names, overloads, JNI types, and static/instance signatures; let the compiler generate headers.
- **Checking only Java compilation:** native compilers, shared libraries, OS loaders, and architecture can still fail.
- **Assuming all familiar tools were deleted:** many JDKs still provide jstat, jmap, jstack, jinfo, or jconsole.
- **Confusing the removal of jhat with deprecation of the .hprof format:** heap dumps can still be analyzed with MAT/VisualVM.
- **Assuming VisualVM/JMC are included in the JDK:** availability and installation depend on vendor/version.
- **Keeping JDK 8 GC logging flags verbatim:** newer JVMs may warn/reject them or parsers may fail to understand the output.
- **Running jcmd against the wrong PID/container:** collects data from the wrong JVM or fails to attach.
- **Collecting dumps/JFR without controls:** sensitive data and overhead can impact production.
- **Relying solely on GUI monitoring:** lacks alerting and long-term telemetry.
- **Testing only on developer machines:** production images may lack tools or restrict permissions.
- **Failing to rehearse runbooks after migration:** outdated commands are only discovered during an incident.

## 14. Pre-Completion Checklist

- [ ] Listed legacy commands and where they appear across builds, CI, images, and runbooks.
- [ ] Categorized each tool: removed, separated from the JDK, changed syntax, or still supported.
- [ ] No remaining tasks requiring javah invocations.
- [ ] javac -h generates the right headers from current source and the build tool tracks the output.
- [ ] Native libraries run on the target OS/architecture/JDK.
- [ ] A heap dump generation and analysis workflow exists to replace jhat.
- [ ] Standalone VisualVM/JMC is installed/managed if needed.
- [ ] jcmd commands have been tested in the right runtime, PID namespace, and permissions.
- [ ] GC logging has been migrated/verified together with parsers and dashboards.
- [ ] Metrics, logs, and alerts continue working after the upgrade.
- [ ] Heap dumps, JFR, and diagnostic outputs have security/retention policies.
- [ ] Runbooks and pipelines have been updated with actually supported commands.
- [ ] Diagnostics and tests have been exercised in a representative environment.
- [ ] Owners, versions, and a support matrix exist for the new toolset.

## 15. Conclusion

Migrating legacy Java tools must start from **the task that needs to be performed**, then select a mechanism supported on the target JDK. For JNI, javah has been replaced by javac -h, allowing headers to be generated during Java compilation and kept in sync with native declarations. For monitoring, jhat is replaced by a heap dump workflow and tools such as Eclipse MAT/VisualVM; many diagnostic tasks use jcmd, JFR, and JMC, while long-term observability requires JMX and application telemetry. Verifying the exact vendor/version, runtime permissions, native artifacts, diagnostic overhead, and dashboards ensures that Java migration preserves operational capability and incident troubleshooting.