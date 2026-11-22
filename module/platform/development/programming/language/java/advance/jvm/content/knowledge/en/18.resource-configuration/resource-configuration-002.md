# Standard Options, -X, -XX, and How to Verify Supported Flags in the JVM

## Objectives

In a real-world Java application, the JVM receives several kinds of arguments: launcher options, JVM parameters, system properties, and **application arguments**. They do not share the same semantics, do not share the same stability guarantees, and not all of them are supported across every vendor/JDK build.

For example:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Dapp.profile=prod -jar service.jar --port=8080
~~~

The illustrative command above has:
- `-Xms256m` and `-Xmx1g`: the **-X** group configures the initial/minimum heap and maximum Java heap.
- `-XX:+UseG1GC`: the **-XX** group selects the G1 garbage collector for HotSpot.
- `-Dapp.profile=prod`: a **standard launcher option** passing a system property to Java code.
- `-jar service.jar`: the launcher runs a JAR with a valid Main-Class.
- `--port=8080`: an **application argument**, not a JVM option when placed after `-jar service.jar`.

A flag written in configuration does not automatically mean it takes effect: a flag can be rejected, require unlocking, be supported only on one platform, be marked **deprecated**, **obsolete** (accepted but ignored), **expired/removed** (rejected), or have its final value changed by the JVM due to ergonomics or flag precedence.

After this lesson, you will be able to:
1. Classify **standard options**, **extra/non-standard -X**, and **advanced HotSpot -XX**.
2. Write Boolean `-XX:+Flag`/`-XX:-Flag` and value `-XX:Flag=value` syntax correctly; understand that `-Xmx2g` is not like `-XX:+Xmx`.
3. Check the support scope via `java --help`, `java -X`, `-Xlog:help`, JDK release documentation, `-XX:+PrintFlagsFinal`, and `jcmd`.
4. Distinguish between **a flag accepted by the parser**, **enabled**, **final value**, **having an effect on a subsystem**, and **stably supported**.
5. Detect the wrong JDK binary, flags placed on the wrong side of `-jar`, `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` environments, flags requiring unlock, and end-of-life options.
6. Configure Java heap, CPU, native resources, and GC according to actual requirements, without inferring total process memory from a single command-line flag.
7. Use Java 17+ examples with deterministic stdout, along with a safe smoke-test process for CI/CD and production.

## 1. Three Option Groups: Names and Stability Levels

The official documentation for the `java` command distinguishes:

| Group | Examples | Characteristics |
| --- | --- | --- |
| **Standard Java launcher options** | `--class-path`, `-cp`, `-jar`, `-Dkey=value`, `--module-path`, `--enable-assertions`, `--version` | Documented by the Java command documentation and expected to have broader compatibility across JVM implementations |
| **Extra/non-standard options (-X)** | `-Xms`, `-Xmx`, `-Xss`, `-Xint`, `-XshowSettings`, `-Xlog` | HotSpot-specific or not guaranteed to be supported by every JVM; subject to change |
| **Advanced HotSpot options (-XX)** | `-XX:+UseG1GC`, `-XX:MaxRAMPercentage=75`, `-XX:+PrintFlagsFinal` | Deep configuration of runtime, GC, JIT, serviceability; stability depends on flag and release |

**Stability cannot be judged solely by flag name length.** `-Xmx` belongs to -X yet is very widely used; meanwhile, a `-XX` flag can be a familiar product flag, a diagnostic flag requiring unlock, or an experimental flag suitable only for testing. Even so, both -X and -XX **are not a Java SE contract unconditionally applicable to every JVM**. <https://dev.java/learn/jvm/tools/core/java/>

### Standard does not mean a program can skip version checks

An option documented in a current JDK might **not have existed in an earlier JDK**. For example, module options appeared with the history of the Java Platform Module System, and `--enable-preview` requires matching between compiler/runtime and release. With real toolchains, always consult the documentation of the exact JDK being deployed.

### An application has multiple "paths" for receiving arguments

~~~text
Operating system / shell
         |
         +-- environment variables
         |      JDK_JAVA_OPTIONS / JAVA_TOOL_OPTIONS
         |
         +-- java launcher args
                  |
           JVM / module/class loader
                  |
            main(String[] args)
                  |
          application framework parser
~~~

A common mistake is mixing `-Dserver.port=8080` (system property), `--server.port=8080` (which may be a framework application argument), and `-XX:...` (VM flag). They **are not automatically interchangeable**.

## 2. Launcher Syntax: Place JVM Options Before the Main Target

Three common invocation styles:

~~~bash
java [options] com.example.Main [app-args]
java [options] -jar application.jar [app-args]
java [options] --module module.name[/MainClass] [app-args]
~~~

In the code fence, the parts in square brackets are **illustrative notation** of the command grammar and must not be typed literally unless they have a specific meaning. `options` are normally read by the launcher parser **before the main class or -jar artifact**. Tokens after the main target are normally passed to the application's `main(String[] args)`.

Compare:

~~~bash
java -Dapp.mode=study -Xmx128m -jar demo.jar input.txt
~~~

This is a **command template**, requiring a valid JAR. The JVM sees the system property `app.mode=study` and a maximum heap of ~128 MiB; the application receives `input.txt`.

Conversely:

~~~bash
java -jar demo.jar -Xmx128m
~~~

Here `-Xmx128m` is normally an **application argument string** after the JAR, and **does not set the maximum heap**. A framework may have its own parser and even report "unknown app argument". Look at the actual JVM command line, not just a string appearing somewhere in a launch script.

### `-jar` is not the same as classpath mode

~~~bash
java -cp lib/app.jar:lib/dependency.jar com.example.Main
~~~

The command above illustrates **Linux/macOS** with the `:` classpath separator; Windows uses `;`. When running `-jar`, the launcher uses the corresponding entry point/JAR rules; adding `-cp` may not take effect the way you expect. Do not try to "fix a missing dependency" by rearranging flags without reading the `-jar` and manifest/classpath documentation.

### System properties

~~~bash
java -Ddemo.mode=study com.example.Main
~~~

In Java, read via `System.getProperty("demo.mode")`. This is not an environment variable. `System.getenv("DEMO_MODE")` reads a different source. An application framework may add a mapping between properties/environment, but that is not the behavior of the JVM option parser.

## 3. -X: Common Extra Options

| Flag | Primary effect | Caveat |
| --- | --- | --- |
| `-Xms256m` | Sets initial/minimum heap size per HotSpot semantics | Not total process RSS |
| `-Xmx2g` | Hard maximum Java heap | Native memory also includes metaspace, thread stacks, code cache, direct memory... |
| `-Xss1m` | Sets stack size for platform threads per HotSpot/OS | Not "total stack of all threads" |
| `-Xint` | Interpreted-only mode for Java code | Drastically changes performance; do not use to simulate natural production |
| `-Xcomp` | Biased toward early compilation | Can consume compilation CPU and alter the profile |
| `-Xbatch` | Runs JIT compilation in foreground instead of background per policy | Can make warmup/latency very different |
| `-XshowSettings:vm` | Prints useful VM settings | Output varies by JDK version |
| `-Xlog:gc*=info` | Unified GC logging on supported HotSpot versions | Log I/O has overhead; output is not immutable |
| `-Xshare:off` / `-Xshare:on` | Controls CDS sharing | ON enforces archive usage and easily fails on mismatch |

**Do not use all flags at once just because they appear in the table.** If you are measuring GC, enabling `-Xint` or `-Xcomp` changes the JIT execution model, making comparisons meaningless.

### Resource sizes: correct units

Example:

~~~bash
java -Xms512m -Xmx2g -Xss1m -jar application.jar
~~~

-X options typically take `k`/`m`/`g` suffixes interpreted as binary units in HotSpot. Read the actual `MaxHeapSize`/`InitialHeapSize` using VM diagnostics to confirm. Do not conclude "container RAM=2 GiB is enough because -Xmx2g": the process needs memory **outside the Java heap**.

### -Xlog: syntax and logging configuration

Example:

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

This is a **run template**, requiring a real JAR file. Unified logging separates selectors (tags/levels), output, and decorators; tags may vary across releases. Run `java -Xlog:help` on the exact JDK to find the available syntax and tags.

Warning: verbose logging generates CPU/disk I/O and can record application activity details. In production, consider log size, rotation, read permissions, and information scope.

## 4. -XX: Two Common Syntax Forms

### Boolean flags: + and - signs

~~~bash
java -XX:+UseG1GC -version
java -XX:-UseCompressedOops -version
~~~

- `-XX:+FlagName` means requesting to enable that Boolean flag.
- `-XX:-FlagName` means requesting to disable it.
- **Do not** use `-XX:UseG1GC=true` as an arbitrary substitute because the documented syntax for boolean flags is `+/-`.
- A flag being disabled or unsupported **does not mean** the JVM cannot run: depending on constraints or dependencies between flags, the parser may fail or the runtime may behave according to policy.

`UseCompressedOops` is a HotSpot flag that may be subject to heap/platform/JDK release constraints; do not disable it arbitrarily as it affects memory/performance and varies by version. The example above **only illustrates grammar**, not tuning advice.

### Value-taking flags: equals sign

~~~bash
java -XX:MaxRAMPercentage=65 -version
java -XX:ActiveProcessorCount=2 -version
java -XX:MaxMetaspaceSize=256m -version
java -XX:ReservedCodeCacheSize=128m -version
~~~

Distinguish carefully:
- `MaxRAMPercentage` is a **percent value** (e.g., 65 means 65%, not 0.65).
- `ActiveProcessorCount` adjusts the number of processors the JVM **reports/detects for ergonomics** such as GC/ForkJoin; it does not create CPU cores or impose a hard OS scheduler limit.
- `MaxMetaspaceSize` sets an appropriate metaspace limit; too low can cause class loading to fail.
- `ReservedCodeCacheSize` adjusts the region holding JIT-compiled code; it is not the Java heap.
- For each flag, read the constraints and defaults in the **Java command docs of the exact release**.

Some flags have other option-specific syntax. Do not assume every option with an argument uses an equals sign, or substitute an `m` suffix onto a percent flag.

## 5. Four Levels of Meaning When Saying "A Flag Is Supported"

Four questions must be separated:

| Question | Primary check | Why they differ |
| --- | --- | --- |
| **Does the parser accept the option?** | Try starting `java [flag] -version`, check exit code/stderr | An obsolete flag is sometimes accepted yet ignored |
| **Does the flag exist at runtime?** | `PrintFlagsFinal`, `jcmd VM.flags -all`, exact JDK docs | An option may be hidden behind an unlock or exist only in another HotSpot build |
| **What is the final effective value?** | `PrintFlagsFinal` or `jcmd PID VM.flags -all` | Ergonomics, defaults, command line, and constraints can all influence it |
| **Does the feature actually work?** | Subsystem logs/behavior, metrics, workload smoke test | "flag true" does not prove GC/JIT/memory performance meets expectations |

For example, `-XX:+UseZGC` may be accepted by the parser, yet the claim "every ZGC mode like in JDK 21 still exists in JDK 25" is false: underlying algorithms/legacy flags have changed. Similarly, a JVM accepting an old flag and printing a warning may **apply no effect at all**.

**Note:** `java -version` can return 0 even when a valid flag specifies a rarely used feature and the runtime workload never triggers it. A smoke test checks startup capability, which is not enough to prove performance.

## 6. Step 1: Know the Exact JDK Being Executed

Start with:

~~~bash
java -version
java --version
javac -version
~~~

Output from `java -version` includes version/build/vendor/VM details depending on the JDK; there is no fixed universal stdout. `javac` may belong to a different JDK than `java` in PATH.

Especially when using:
- IDE run configurations;
- Maven/Gradle toolchains;
- application servers with a private bundled JRE;
- Docker/Podman images or Kubernetes Pods;
- systemd/Windows services and shell aliases;
- multiple side-by-side JDK17/21/25 installations.

**Run verification commands in the exact runtime/container/launch environment that will start the service**, do not infer from your personal machine's shell. For a running application, obtain the process command line and VM version using tools attached to the exact PID.

### JAVA_HOME does not by itself guarantee which binary is invoked

`JAVA_HOME` is an environment variable often used by scripts/toolchains; when typing `java`, the shell also applies PATH/resolution rules. On Windows there is `Get-Command java` in PowerShell; on Linux/macOS there is `command -v java`. Never claim `JAVA_HOME` and `java -version` always match without checking.

## 7. Step 2: Which Options Does the Java Launcher Advertise?

Common commands:

~~~bash
java --help
java -X
java -Xlog:help
~~~

Meaning:
- `java --help` describes launcher syntax and applicable **standard options**.
- `java -X` displays many extra/non-standard HotSpot options on that build.
- `java -Xlog:help` provides supported logging tags, levels, decorators, and syntax.

**No `java -X` command necessarily lists every -XX option**, especially diagnostic/experimental/internal flags. Similarly, a flag appearing in help does not guarantee it has the same range/default on another JDK.

You can use `java --help-extra` on JDKs that support it to see additional option descriptions. Output depends on the binary and version.

### How to check in PowerShell

~~~powershell
java --help
java -X
java -Xlog:help
~~~

Output from some launcher options may go to stderr; when filtering results, account for both stdout and stderr. Do not use "not found in a `Select-String`" as absolute proof that a flag does not exist.

## 8. Step 3: Inspect HotSpot -XX Flag Values

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

On supported HotSpot builds, this command lists many VM flags along with:
- type (e.g., bool, intx, uintx, size_t, double...);
- name (e.g., `MaxHeapSize`);
- final computed value;
- category and/or origin (product, diagnostic, experimental, command line, ergonomic, default...) depending on the build and output format.

**Illustrative** line structure example, not a fixed log:

~~~text
   size_t MaxHeapSize = 536870912 {product} {ergonomic}
     bool UseG1GC = true         {product} {ergonomic}
~~~

Numbers, `=` or `:=` signs, name/value, and category/origin vary by JDK/flags/container. **Do not copy illustrative output to verify a production instance**.

### Comparing default vs. explicitly set

~~~bash
java -XX:+PrintFlagsFinal -version
java -Xmx512m -XX:+PrintFlagsFinal -version
~~~

Compare `MaxHeapSize` between the two runs. With `-Xmx512m`, the expected maximum Java heap in an appropriate HotSpot configuration is 512 MiB (536,870,912 bytes). However, the command line can be affected by hidden environment flags; to control the experiment, check both the environment and the actual input args.

With `-XX:MaxRAMPercentage=65` and **no** `-Xmx` set, the maximum heap is normally calculated from the container/host resources detected by the VM and related constraints. The actual number cannot be inferred simply from "65% of 8 GiB host RAM" if the container memory limit is only 2 GiB or if other minimum/maximum limits apply.

### Check ranges when validating input values

On supported HotSpot JDKs:

~~~bash
java -XX:+PrintFlagsRanges -version
~~~

Range data only appears completely for flags with declared ranges; the output does not replace **inter-flag constraints** or runtime limitations. A value within range that conflicts with the memory budget/GC mode can still cause startup to fail.

### PrintFlagsInitial and PrintFlagsFinal

Some HotSpot builds allow:

~~~bash
java -XX:+PrintFlagsInitial -version
java -XX:+PrintFlagsFinal -version
~~~

`PrintFlagsInitial` shows many initial/default flag values where applicable; `PrintFlagsFinal` reflects the final chosen values at startup. They do not describe **every dynamic change occurring throughout the lifetime** and do not mean all flags can be modified live.

## 9. Step 4: Inspect the Running Process, Not Just a New Test JVM

A JVM started by a Helm chart/script/IDE may use very different arguments than your `java -version` test command. For a target HotSpot process you have permission to attach to, use:

~~~bash
jcmd
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID VM.flags -all
jcmd PID VM.version
~~~

**`PID` here is a placeholder to replace with a real process ID**, not a valid string to copy literally. Use `jcmd PID help` to see available diagnostics on that exact process; availability and output may vary by JDK.

Interpretation:
- `VM.command_line` shows the actual VM/Java command line according to the diagnostic implementation.
- `VM.flags` summarizes a subset of VM flags.
- `VM.flags -all` requests the full list of flags, usually with values/origins, if supported.
- `VM.version` confirms the actual runtime VM build.

A few flags are **manageable** and can be adjusted live via tools like `jinfo`/management, but **most startup flags cannot be changed dynamically**, and live changes in production are an operational action requiring control.

### Not every JVM allows attach

Container namespace restrictions, filesystem permissions, OS privileges, flags disabling the attach mechanism, JDK installation, and security settings can cause `jcmd` to fail. Do not treat an attach failure as proof that a flag is unsupported; first check permissions/PID/VM build.

### Java API reading some args itself

`ManagementFactory.getRuntimeMXBean().getInputArguments()` returns the input arguments received by the VM per the API contract, which is useful when logging startup configuration. It **does not necessarily include every launcher/application argument**, and some options belong only to the launcher, not the VM. When you want to know the final flags, prefer `PrintFlagsFinal`/`jcmd` over parsing a list of Java args.

## 10. Lifecycle States: Active, Deprecated, Obsolete, Expired

`-XX` options do not have an infinite lifespan. OpenJDK HotSpot has a flag management mechanism, described in the `arguments.cpp` source.

| State | Usually has effect? | Signs |
| --- | --- | --- |
| **Active/supportable** | Yes, per semantics and constraints | Launcher accepts the flag and VM applies it |
| **Deprecated** | Usually still has effect | Warning, notifying that it may be removed in a future release |
| **Obsolete** | **No longer has effect** | VM may still accept the syntax for compatibility, print a warning, and ignore it |
| **Expired/removed** | No longer accepted as a valid option | VM refuses startup, usually reporting an unrecognized flag |
| **Experimental** | May have effect but is unstable | Requires `UnlockExperimentalVMOptions` if the flag is locked |
| **Diagnostic** | May have effect, used for investigation | Requires `UnlockDiagnosticVMOptions` for locked flags |

**Distinction:** An obsolete option can still return exit code 0. Therefore **startup success is not enough** to conclude a flag is working. If there is an "Ignoring option..." warning or equivalent, the configuration must be fixed.

### Examples of flags removed across releases

On HotSpot JDK 17:
- `-XX:MaxPermSize=...` and `-XX:PermSize=...` are historical PermGen options that have been removed; modern JVMs use metaspace.
- `-XX:+TraceClassLoading` was removed, with replacement `-Xlog:class+load=info` in Unified Logging.
- `--illegal-access=...` became obsolete in JDK 17: it may be accepted but no longer relaxes encapsulation as in earlier releases.

On JDK 24, some old `MaxRAMFraction`-style flags were removed in favor of the corresponding `MaxRAMPercentage` flags. In newer JDKs, another flag may go through deprecated -> obsolete -> expired, though not every flag follows the exact same release schedule. Read the **Deprecated / Obsolete / Removed Options** list for the **exact JDK**.

### When migrating from JDK 17 to 21/25/26

Do not infer from "the flag worked on Java 8" that "the flag is still valid on Java 25". When upgrading versions:
1. List the entire command line and environment-injected options.
2. Consult the exact Java launcher docs and release notes.
3. Build a test runtime image matching the exact vendor/architecture.
4. Start with the exact production flags, capturing exit code and warnings.
5. Inspect `PrintFlagsFinal`/`VM.flags` and subsystem logs.
6. Remove deprecated/obsolete flags and find documented replacements.
7. Run integration/performance tests before rollout.

If a flag changes semantics between JDKs, **version-conditional config** may be needed rather than just deleting a warning.

## 11. Diagnostic and Experimental Flags: Unlocking Properly

Some HotSpot options belong to the **diagnostic** or **experimental** groups and are not available on a production command line without unlocking.

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -version
java -XX:+UnlockExperimentalVMOptions -XX:+SomeExperimentalFlag -version
~~~

The second line is a **syntax illustration**; `SomeExperimentalFlag` is not a real flag name and must not be run literally. For a diagnostic flag like `LogCompilation`, follow the exact requirements of the HotSpot build. Placing the unlock flag **before the flags to be unlocked** avoids parse errors in the corresponding versions.

**This does not mean:** "just enabling UnlockDiagnosticVMOptions makes every secret flag supported and safe". Diagnostic/experimental flags may not be part of a stable API and can change/be removed. Only enable them when there is a clear measurement/investigation need, accompanied by a rollout and rollback plan.

### Do not use `-XX:+IgnoreUnrecognizedVMOptions` to hide configuration errors

Some HotSpot builds have a flag that allows ignoring unrecognized options. Using it to "push one shared JVM_FLAGS file across all JDKs" can mask incidents:
- the JVM unintentionally fails to enable the GC mode the team expects;
- heap/native memory bounds are ignored;
- the container runs with unexpected defaults;
- warnings disappear from CI pipelines and only surface when the service is overloaded.

For flags affecting correctness/resource budgets, **fail-fast and verification** is better than silently ignoring. If a library/agent uses different version conditions, configure branches per specific runtime.

## 12. Essential Resource Flags: Heap Does Not Equal RSS

A JVM application uses multiple memory regions:

~~~text
JVM PROCESS
 |
 +-- Java heap        -Xms, -Xmx, MaxRAMPercentage
 +-- Class metadata   Metaspace, Compressed Class Space
 +-- JIT code cache   ReservedCodeCacheSize
 +-- Thread stacks    -Xss for eligible platform threads
 +-- Direct/native    ByteBuffers, JNI, JVM internals
 +-- GC bookkeeping   card tables, remembered sets, etc.
 +-- OS mapped data   CDS archives, mapped files, libraries
 |
 +-- CPU threads/scheduler limits
      ActiveProcessorCount, GC thread ergonomics, container quota
~~~

`-Xmx1g` only constrains part of the **Java heap**, not the total process resident set size. A container with a 1 GiB limit and `-Xmx1g` can easily hit an OOM kill due to native components, even when the Java heap is not full.

| Goal | Commonly inspected flags | Configuration risks |
| --- | --- | --- |
| Maximum Java heap | `-Xmx`, `-XX:MaxRAMPercentage` | Low Xmx: GC pressure/OOME; high: insufficient RSS/native headroom |
| Initial heap | `-Xms` | Large initial/committed memory; too small causes expansion churn |
| Thread stack | `-Xss` | Stack too small: StackOverflowError; too large: native memory pressure |
| Class metadata | `-XX:MaxMetaspaceSize` | Class loading fails if too tight |
| Direct memory | `-XX:MaxDirectMemorySize` | Native/direct buffer limits, depending on JDK semantics |
| JIT code cache | `-XX:ReservedCodeCacheSize` | Compilation may be limited when too low |
| CPU ergonomics | `-XX:ActiveProcessorCount` | Does not grant more CPU, only changes sizing/policy logic |
| Collector | `-XX:+UseG1GC`, `-XX:+UseZGC` | Algorithms/flags have version-specific behavior |
| GC logs | `-Xlog:gc*` | Helps observability, creates overhead/disk logs |

**Do not** set multiple flags controlling the same goal simultaneously without understanding precedence. When an explicit `-Xmx` is present, `MaxRAMPercentage` may no longer determine the maximum heap as it does when Xmx is unset.

## 13. Configuration in Containers: An Operational Example

Suppose a container has a 2 GiB memory limit, and the application has a live heap set of a few hundred MiB and uses direct buffers/native libraries. An initial experiment might start with:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc*=info -jar service.jar
~~~

This is an **exploratory template**, not an optimal numeric recommendation. Only set a 1 GiB heap if you have measured:
- peak live heap and allocation spikes;
- thread count/stacks;
- metaspace/class loading;
- direct/native memory;
- JIT code cache, GC native overhead;
- container RSS/working set and CPU throttling.

If the container limit is 2 GiB, **do not substitute a table of Java flags for real memory metrics**. For a running process, you can use:
- `jcmd PID GC.heap_info` to view the heap picture;
- `jcmd PID VM.flags` to inspect VM config;
- JFR, GC logs, and monitoring systems;
- `jcmd PID VM.native_memory summary` if the process enabled appropriate Native Memory Tracking from startup, e.g., `-XX:NativeMemoryTracking=summary`.

**NMT cannot be arbitrarily enabled in full after the JVM has started** on many HotSpot configurations and carries overhead. Do not arbitrarily enable `NativeMemoryTracking=detail` in production before evaluating its cost.

### Why does ActiveProcessorCount require caution?

`-XX:ActiveProcessorCount=2` affects the JVM's view of processors in ergonomics such as sizing worker pools, but it is not a Linux `cgroups` CPU quota, does not pin the application to use only two OS CPUs, and does not stop native libraries from creating threads. Measure actual process CPU and inspect container metrics.

## 14. Java 17+ Example: Demonstrating Launcher vs. System Property vs. App Args

Create the file **`JvmOptionProbe.java`**:

~~~java
import java.util.Arrays;

public class JvmOptionProbe {
    public static void main(String[] args) {
        boolean assertionsEnabled = false;
        assert assertionsEnabled = true;

        String mode = System.getProperty("demo.mode", "missing");
        int sum = 19 + 23;

        System.out.println("mode=" + mode);
        System.out.println("assertions=" + assertionsEnabled);
        System.out.println("args=" + Arrays.toString(args));
        System.out.println("sum=" + sum);
    }
}
~~~

Compile:

~~~bash
javac --release 17 JvmOptionProbe.java
~~~

Run on JDK 17+:

~~~bash
java -ea -Ddemo.mode=study -Xms32m -Xmx128m JvmOptionProbe alpha beta
~~~

**Exact business stdout:**

~~~text
mode=study
assertions=true
args=[alpha, beta]
sum=42
~~~

Explanation:
- `-ea`/`--enable-assertions` enables `assert` evaluation for classes in this context; assignment inside an assert is only a **demo**, not a pattern for writing production logic.
- `-Ddemo.mode=study` creates a system property, not going into `args`.
- `-Xms32m` and `-Xmx128m` pass options to HotSpot, not going into `args`.
- `alpha beta` are after the main class, going into `String[] args`.
- The addition 19+23 may be folded into a constant by `javac`, but the business output is still 42.

Try placing `-Xmx128m` after the class:

~~~bash
java -ea -Ddemo.mode=study JvmOptionProbe alpha -Xmx128m
~~~

The application will receive `args=[alpha, -Xmx128m]`; this token is **not a JVM heap option** in that position. Do not assign meaning to the substring `-Xmx` while ignoring argument order.

## 15. Java 17+ Example: Observing Effective Heap Inside the Application

In HotSpot, you can use the management API to query certain VM flags. Create the file **`HotSpotFlagProbe.java`**:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.lang.management.ManagementFactory;

public class HotSpotFlagProbe {
    public static void main(String[] args) {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        if (bean == null) {
            System.out.println("hotspotBeanAvailable=false");
            return;
        }

        VMOption option = bean.getVMOption("MaxHeapSize");
        long bytes = Long.parseLong(option.getValue());

        System.out.println("hotspotBeanAvailable=true");
        System.out.println("maxHeapMiB=" + (bytes / 1024 / 1024));
        System.out.println("origin=" + option.getOrigin());
    }
}
~~~

Compile and run on **HotSpot JDK 17+**:

~~~bash
javac --release 17 HotSpotFlagProbe.java
java -Xmx128m HotSpotFlagProbe
~~~

When `HotSpotDiagnosticMXBean` is supported and `-Xmx128m` is applied, the example typically prints:

~~~text
hotspotBeanAvailable=true
maxHeapMiB=128
origin=VM_CREATION
~~~

This is the **expected output on standard HotSpot JDK 17+ with the configuration above**, not a contract for every JVM vendor or future version. The bean may be absent on another VM, and `VMOption.Origin` reflects the configuration mechanism reported by the runtime. Do not use equality between `Runtime.getRuntime().maxMemory()` and `MaxHeapSize` as an absolute check across every collector/build, due to ergonomics and alignment.

### Distinguishing management-origin from effective behavior

`origin=VM_CREATION` normally indicates an option was set at JVM startup, but it does not prove business performance. An option may have been accepted and have the expected origin yet only be used when a specific subsystem is active. For GC, verify further with `-Xlog:gc*`; for heap, check actual memory metrics; for JIT, read compilation diagnostics.

## 16. Method for Verifying Flags via Standalone Smoke Test

If you want to know whether a Boolean flag is accepted by the current HotSpot build:

~~~bash
java -XX:+UseG1GC -version
~~~

Check the **exit status** and output. When successful, the command proves:
- the option is accepted by the launcher/VM;
- the VM can start up through printing the version;
- there are no immediate syntax/constraint errors in that configuration.

However, it does not prove:
- the actual application runs correctly;
- a specific GC event has occurred;
- the container heap limit will not cause OOM under load;
- throughput or latency has improved.

You should add:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info -version
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
~~~

For other Boolean flags, verify the exact name, product/diagnostic/experimental flag group, and version-specific restrictions. If the parser returns an error, record the exact error/exit code instead of adding `-XX:+IgnoreUnrecognizedVMOptions` to hide it.

### GC flags can change meaning across releases

Example with ZGC:
- JDK 21 introduced Generational ZGC as a selectable mode;
- JDK 23 made generational mode the default when ZGC is selected;
- JDK 24 removed non-generational ZGC;
- some legacy flags such as `ZGenerational` move toward obsolete/expired in newer JDKs.

**Do not copy a specialized set of flags from one JDK and apply it verbatim to another JDK.** If an app image needs to run across multiple releases, create version-specific `JVM_ARGS` and smoke-test each image.

## 17. System Properties, Environment Variables, and Injected JVM Options

Three distinct mechanisms:

| Source | Example | Who handles it |
| --- | --- | --- |
| CLI system property | `-Ddemo.mode=study` | Launcher/VM provides `System.getProperty` |
| Application environment variable | `DEMO_MODE=study` | OS/environment; app reads `System.getenv` |
| `JDK_JAVA_OPTIONS` | `-Ddemo.mode=study -Xmx128m` | Java launcher prepends before parsed CLI args |
| `JAVA_TOOL_OPTIONS` | `-Ddemo.mode=study` | JVM startup instrumentation/config path per implementation/contract |
| `_JAVA_OPTIONS` | Internal syntax often seen in some vendors | Do not use as a publicly guaranteed portable mechanism |

**Note on JDK_JAVA_OPTIONS:** per the Java command documentation, it is **prepended** to launcher options, prints a reminder message on stderr, and **forbids** options that select the main class or exit the launcher early such as `-jar`, `-h`. An `@argument-file` is permitted per launcher semantics.

**Note on JAVA_TOOL_OPTIONS:** often used to pass VM options to processes whose startup is controlled by a wrapper, but it does not have the same permission to handle launcher-only options as `JDK_JAVA_OPTIONS`; some runtime environments also restrict injection for security reasons.

### The "removed the flag from the startup script yet still seeing it" bug

The flag may be injected via:
- `JDK_JAVA_OPTIONS` or `JAVA_TOOL_OPTIONS`;
- IDE configuration/Gradle JVM args;
- service wrapper/application server;
- Docker `ENTRYPOINT`/`CMD`;
- Helm chart config map/env;
- Kubernetes mutating admissions;
- shell alias or inherited script;
- vendor-specific launcher.

When investigating, inspect the **actual process VM.command_line** and environment injection rather than reading just one startup file. Do not expose secrets that might be in `-Dpassword=...` when sharing logs; command lines/JVM input args can leak sensitive information.

## 18. Argument Files and Quoting: Avoiding Hard-to-Spot Bugs

The Java launcher supports **@argument files** to store multiple options. Example text file `vm.args`:

~~~text
-Xms64m
-Xmx256m
-Ddemo.mode=study
-ea
JvmOptionProbe
alpha
beta
~~~

This is **launcher argument file content**, not application data. If `vm.args` exists:

~~~bash
java @vm.args
~~~

This executes equivalently to the program in section 14 if the environment and quoting match. Note:
- This is a **Java launcher** feature; not every wrapper/VM embedding API understands `@vm.args`.
- Encoding, escaping/quoting, and wildcard expansion have their own rules; see the *java Command-Line Argument Files* section of the exact JDK.
- Options before the main class are still launcher/VM options; tokens after the class are app args.
- If configuration contains whitespace in a property value, use proper quoting per shell/argument-file rules.
- Do not write passwords/tokens into widely readable argument files or commit secrets into source control.

Some tools like Maven/Gradle also use `@argfile`, but **do not automatically assume the Java launcher's quoting rules/option parser match all other tools**.

## 19. How to Check on Windows PowerShell

Identify the binary being used:

~~~powershell
Get-Command java
java -version
java -X
~~~

Inspect relevant flags (filter output; may also need stderr depending on the tool):

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "MaxHeapSize|InitialHeapSize|UseG1GC|ActiveProcessorCount"
~~~

When you need to inspect a PID:

~~~powershell
jcmd
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
~~~

**12345 is an illustrative PID** and must be replaced with a real PID. Do not read results from another Java process and attribute them to the service under investigation. `jcmd` may require matching permissions (same user, attach permissions).

PowerShell handles quoting/escaping differently from Bash. Especially for properties containing whitespace, verify the actual argument received by the JVM using a Java test app instead of relying solely on syntax that looks plausible.

## 20. How to Check on Linux/macOS

~~~bash
command -v java
java -version
java -X
java -XX:+PrintFlagsFinal -version
~~~

Filtering example:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 |
    grep -E 'MaxHeapSize|UseG1GC|ActiveProcessorCount'
~~~

Use `jcmd PID VM.command_line` if the JVM is running and attachable. In containers, the PID in the host namespace may differ from the PID inside the container; run diagnostics in the exact namespace/context.

**Do not use `ps` output as the sole source:** some wrappers/launchers can alter the displayed argv, and environment-injected flags do not necessarily appear completely in standard OS tools.

## 21. Distinguishing Defaults, Command Line, and Ergonomics

HotSpot often computes many values automatically based on:
- number of logical processors detected by the JVM;
- heap budget/memory limit;
- selected GC;
- OS/architecture;
- JDK build, flavor, and VM tuning;
- CPU ratio/quota/container support;
- constraint relationships between flags.

For example, if `-Xmx` is not set, `MaxHeapSize` is chosen by HotSpot via ergonomics. When `-Xmx512m` is set, the final value differs. However, not every printed default value is "used at runtime": a flag belonging to an unselected collector may still exist and have a default value.

### Why look at origin?

The provenance column helps distinguish:
- `{default}`: kept at the default in the build/context;
- `{ergonomic}`: adjusted by the VM via heuristics;
- `{command line}`: set via startup arguments;
- other origins may relate to environment, management, or attach.

Origin formatting/names depend on the build. Do not assume the source is always represented by the same string across JDK versions. If multiple layers set the same flag, the final value and the actual command line must be examined together.

### A flag does not replace a metric

`-XX:MaxRAMPercentage=65` does not prove the JVM uses exactly 65% of host RAM; it is an **input to heap-sizing policy**. `-XX:+UseG1GC` does not prove latency <200ms; `-XX:ActiveProcessorCount=2` does not restrict the process to running on only two CPU cores.

Separate *configuration intent*, *effective VM option*, *subsystem behavior*, and *business outcome*. This is the foundation of every serious resource configuration check.

## 22. Case Study: JVM Fails to Start After Upgrading the JDK

A service previously used:

~~~text
JAVA_OPTS="-Xms512m -Xmx2g -XX:MaxRAMFraction=4 -XX:+TraceClassLoading"
~~~

This is a **historical example configuration**, not a set of flags to keep using. On a newer JDK, `TraceClassLoading` or `MaxRAMFraction` may be removed and cause the VM to fail.

Troubleshooting procedure:
1. Capture exact stderr, exit code, and JDK vendor/build/runtime image.
2. Determine whether JVM options come from a wrapper's `JAVA_OPTS` or directly from the environment; `JAVA_OPTS` **is not a variable that the java launcher natively recognizes by standard**, and only takes effect if a script uses it.
3. Run each group of flags on the **exact JDK**; do not edit production immediately.
4. Consult the *Removed Options* section of the release in use.
5. Replace `-XX:+TraceClassLoading` with Unified Logging `-Xlog:class+load=info` if the goal is observing class loading.
6. Consider replacing `MaxRAMFraction` with `MaxRAMPercentage` **when explicit -Xmx is no longer present**, rather than keeping a redundant flag.
7. Run the smoke test `java ... -version`, then start the application with test traffic.
8. Cross-check `PrintFlagsFinal`, `VM.command_line`, and GC/heap/CPU metrics.
9. Document version-conditional config and a rollback plan.

**Do not simply add** `IgnoreUnrecognizedVMOptions` to make the service start, because you may lose memory constraints that the deployment relies on.

## 23. Situations Where a Flag Is Accepted Yet the Result Contradicts Expectations

### A. Heap set properly, yet container is still OOMKilled

The cause may be native memory, metaspace, stacks, direct buffers, JIT code cache, file mappings, and GC overhead. The solution is not simply continuing to lower `-Xmx` blindly; you need to measure NMT/RSS/heap and evaluate the whole-process budget.

### B. ActiveProcessorCount=2 set, yet process still shows many threads

The flag affects JVM ergonomics, not a strict OS thread cap. GC threads, JIT threads, application workers, and native libraries still exist under their own policies.

### C. PrintFlagsFinal enabled, yet user-defined property not visible

`-Ddemo.mode=study` is a Java system property, not a `-XX` flag. Check via the Java API or `-XshowSettings:properties` depending on the JDK instead of searching for "demo.mode" in the HotSpot flag table.

### D. -Xmx placed before JAR, yet app reports it as input

If the JVM really sees the flag before `-jar` and the app reports `-Xmx` as an argument, a launcher wrapper may have reordered tokens. Read the actual command line from `VM.command_line` and inspect the script/container ENTRYPOINT.

### E. PrintFlagsFinal shows a value for the flag, yet the feature does not work

The flag may only be a heuristic, in an obsolete state (no longer having effect), or its subsystem is not selected. Read warnings, docs, and subsystem logs; do not infer from a printed value.

### F. Same flags, yet two JDKs yield different heaps

Defaults/ergonomics/container support/architecture/collector may differ. If you want to benchmark performance, pin the JDK or explicitly record the version as an independent variable.

## 24. JVM Args Verification Pipeline in CI/CD

A reliable pipeline should use the exact production runtime image.

**Tier A — Syntax / startup smoke:**
- Capture `java -version`.
- Run `java [JVM_FLAGS] -version` on the exact binary.
- Assert exit code = 0 and no unacceptable warnings.
- Do not use `IgnoreUnrecognizedVMOptions` unless the reason is proven.

**Tier B — Effective configuration:**
- Run `java [JVM_FLAGS] -XX:+PrintFlagsFinal -version`.
- Extract key flags: `MaxHeapSize`, `InitialHeapSize`, selected GC, `ActiveProcessorCount`, metaspace/code cache if needed.
- Compare against deployment budgets and constraints; do not compare output verbatim across releases.

**Tier C — Application smoke:**
- Start the actual JAR/class; verify entrypoint, module/classpath, and app arguments.
- Readiness health check, basic request, timeout, error logs, resource availability.
- Inspect the exact runtime process with `jcmd PID VM.command_line` when permitted.

**Tier D — Load/performance verification:**
- GC logs, heap/RSS/CPU throttling, NMT (if enabled), p95/p99 end-to-end latency.
- Set budgets and limits; do not use flags as KPIs.
- Canary + rollback when changing JDK/GC/heap.

**Tier E — Configuration governance:**
- Store exact JDK vendor/build, JVM args, environment-provided args, and generated manifests.
- Assign an owner for every non-default flag: why it is enabled, measured baseline, how to verify, removal plan.
- Add tests both when a flag is missing and when it becomes deprecated/obsolete.
- Audit secrets in system properties and logs.

## 25. Do Not Use Flags as a "Performance Optimization Collection"

A configuration like:

~~~text
-Xms4g
-Xmx4g
-XX:+AlwaysPreTouch
-XX:+UseG1GC
-XX:ActiveProcessorCount=2
-XX:MaxMetaspaceSize=128m
-XX:ReservedCodeCacheSize=64m
~~~

may suit certain experiments, but **is not a good configuration for every Java server**. For example:
- `-Xms=-Xmx` can increase committed memory; in return, heap size is more stable in certain situations.
- `AlwaysPreTouch` can lengthen startup and alter memory commitment.
- 128 MiB metaspace may be too small for applications using many frameworks/proxies.
- 64 MiB code cache may throttle JIT compilation on large workloads.
- ActiveProcessorCount=2 can undersize GC/JIT/pool heuristics relative to real hardware if set incorrectly.

A configuration should have **target resources, workload profile, measured evidence, and rollback**. Do not keep flags just because they were copied from a Java 8 article.

## 26. Practice Exercises

### Exercise 1 — Classify options

Classify the options in the command:

~~~bash
java -Ddemo.env=test -Xmx512m -XX:+UseG1GC -jar app.jar hello
~~~

**Answer:** `-D` standard launcher property; `-Xmx` extra; `-XX:+UseG1GC` advanced; `-jar` standard launch mode; `hello` application argument.

### Exercise 2 — Wrong position

Command:

~~~bash
java -jar app.jar -Xmx512m
~~~

**Answer:** `-Xmx512m` goes into app args per launcher target grammar and does not configure the maximum heap.

### Exercise 3 — Boolean flag

To enable G1 in HotSpot, use `-XX:+UseG1GC`, not `-XX:UseG1GC` arbitrarily. To disable a Boolean flag, the basic syntax is `-XX:-FlagName` — but **do not disable G1** without specifying an alternative GC and constraints.

### Exercise 4 — Value flag

To hint the JVM to auto-size the heap from the memory budget with `MaxRAMPercentage`, use the form `-XX:MaxRAMPercentage=65`, not `-XX:+MaxRAMPercentage`.

### Exercise 5 — Is a flag supported or not?

Propose three checks:
1. Consult the Java command docs of the **exact release**.
2. Run a smoke test using the exact binary and read exit status/warnings.
3. Inspect `PrintFlagsFinal`/`jcmd` and feature logs under an application workload.

### Exercise 6 — Why is `-Xmx=1g` not enough to contain a 1 GiB container?

**Answer:** The heap is not all of process memory. Native memory, metaspace, stacks, direct buffers, JIT, and mappings also consume additional memory.

### Exercise 7 — Why is `-XX:+IgnoreUnrecognizedVMOptions` risky?

**Answer:** It can mask removed/misspelled flags, causing the JVM to run with defaults instead of the intended resource limits.

### Exercise 8 — Distinguish PrintFlagsFinal and VM.command_line

**Answer:** PrintFlagsFinal helps inspect effective VM flag values at startup; VM.command_line reflects the command line the JVM process received. Combine both to know intent and outcome.

### Exercise 9 — Why doesn't `java -X` list every -XX?

**Answer:** It is help for extra options advertised by the launcher; -XX flags have their own groups/levels, and many flags are gated/implementation-specific.

### Exercise 10 — An obsolete flag is accepted by the parser; does that mean it still works?

**Answer:** No. Obsolete flags are normally accepted and then ignored with a warning. You must check lifecycle and behavior.

### Exercise 11 — -D not visible in PrintFlagsFinal?

**Answer:** Because a system property is different from a VM flag. Check via `System.getProperty` or appropriate VM/launcher property diagnostics.

### Exercise 12 — A process running in Docker gets a smaller MaxHeapSize than expected even though the host has 64 GiB?

**Answer:** Container memory limits/HotSpot ergonomics/flags can cause the JVM to see a smaller budget than the host. Verify exact process flags/container limits.

### Exercise 13 — Is a Java source-level preview option an advanced -XX flag?

**Answer:** No. `--enable-preview` belongs to the launcher/compiler workflow related to preview language/API features; it is not synonymous with an experimental VM GC flag.

### Exercise 14 — How to unlock diagnostic flags?

**Answer:** Use `-XX:+UnlockDiagnosticVMOptions` before flags marked diagnostic, on a supported HotSpot build. Do not invent nonexistent flags.

### Exercise 15 — A flag worked on JDK 8 but fails on JDK 25: is the JVM buggy?

**Answer:** Not necessarily. The flag may have been removed/expired. Consult the exact JDK docs, replace with a supported option, and test behavior.

## 27. Mind Map

~~~text
                     java LAUNCHER
                           |
         +-----------------+-----------------+
         |                 |                 |
      STANDARD            -X               -XX
 -D, -cp, -jar         -Xms/-Xmx       +Flag / -Flag
 --module-path         -Xss, -Xlog     Flag=value
 --version, -ea        -Xint, -X       GC/JIT/memory
         |                 |                 |
         +-----------------+-----------------+
                           |
                 EXACT JDK VENDOR/BUILD
                           |
                   ARE FLAGS ACCEPTED?
               /                         \
             NO                           YES
             |                             |
        stop; fix                    ACTIVE vs OBSOLETE?
        version/syntax              /               \
                                   warning?         effect?
                                      |                |
                                inspect docs       PrintFlagsFinal
                                                   jcmd VM.flags
                                                      |
                                               SUBSYSTEM LOGS
                                                      |
                                                RESOURCE METRICS
                                                      |
                                               APPLICATION SLO
                           |
                  DO NOT CONFUSE WITH:
             app arguments after main/-jar
             env JAVA_TOOL_OPTIONS
             JDK_JAVA_OPTIONS
             process RSS vs Java heap
             parser acceptance vs semantic effect
~~~

**Summary:** **Standard**, **-X**, and **-XX** options differ in parser, scope, stability level, and purpose. Before putting a flag into resource configuration, check the **exact Java binary/version**, read `java --help`/`java -X` and release docs, run a startup smoke test, inspect **effective VM flags** with `PrintFlagsFinal` or `jcmd`, and then confirm behavior and resources using logging/metrics. An accepted flag can still be obsolete or unsuitable for the workload; a set flag is not a performance guarantee. Manage JVM args as **versioned, evidence-backed operational configuration with a rollback**, not a collection of unverified tricks.

## References

- [Oracle JDK 17 — The java Command, Standard/Extra/Advanced options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [Oracle JDK 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Dev.java — Java Application Launcher: Standard, -X and -XX options](https://dev.java/learn/jvm/tools/core/java/).
- [Oracle JDK 17 — jcmd utility](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Oracle JDK 17 — jinfo utility](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html).
- [Oracle JDK 17 — Java ManagementFactory and RuntimeMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html).
- [Oracle JDK 17 — HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html).
- [Oracle JDK 17 — VMOption and Origin](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/VMOption.html).
- [OpenJDK HotSpot runtime — arguments.cpp, deprecated/obsolete/expired flags](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/arguments.cpp).
- [OpenJDK — JEP 158, Unified JVM Logging](https://openjdk.org/jeps/158).
- [OpenJDK — JEP 271, Unified GC Logging](https://openjdk.org/jeps/271).
