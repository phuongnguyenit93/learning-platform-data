# Collector Availability Depends on Distribution, Version, and Platform

**There is no single list of garbage collectors (GC) that works across all Java programs and all environments.** Java SE specifies how a program must behave, but it does not require all Java Virtual Machines (JVM) to implement **Serial, Parallel, G1, ZGC, Shenandoah, CMS** or use the same set of control flags. A collector may exist in the OpenJDK source code but **not be built** into a distribution, exist in the binary but be **unavailable** on a specific OS/CPU, or be available but **not selected by default**.

This topic belongs to the **JVM collectors** group: the goal here is not to rank which GC algorithm is best, but to explain **how to determine whether a collector is available, usable, and actually running on the exact runtime where you will deploy**.

The most important practical rule:

> **Use the real Java binary to verify.** Record the vendor/VM implementation, JDK version, OS/architecture, build options, runtime flags, and logs. Do not copy GC configurations from one machine or an article to another environment without checking.

## 1. Six Dimensions Determining Whether a Collector Is Usable

A GC feature can be restricted at one or more layers:

| Dimension | Question to verify | Example |
| --- | --- | --- |
| **JVM implementation** | Is the JVM HotSpot, OpenJ9, a Native Image runtime, or something else? | `-XX:+UseG1GC` is a HotSpot flag; OpenJ9 uses its own GC policies |
| **Distribution / vendor** | Which binary is released, packaged, and supported? | Two vendors with the same OpenJDK major version may have different GC build options |
| **JDK release** | Has the GC been introduced, made production-ready, deprecated, or removed? | Generational ZGC changed across JDK 21/23/24 |
| **OS and CPU architecture** | Does this port have the required backend and system requirements? | OS, x86-64/AArch64, address space limits |
| **Build/feature flags** | Is the collector compiled into this VM and allowed to be enabled? | Shenandoah may be missing in some builds |
| **Runtime resource/configuration** | Can the collector start with the current heap, CPU, and page/VM constraints? | A low-latency GC may require an appropriate heap size/platform |

There is also a seventh dimension: **support policy (support lifecycle)**: a vendor may release a binary that accepts a flag without providing the same level of commercial support, security fixes, or backports as another distribution.

### Four Levels of "Availability" to Distinguish

1. **Present in documentation/design:** the algorithm has been described, with a JEP or reference implementation.
2. **Present in the binary:** the collector is actually built and has a corresponding configuration mechanism.
3. **Starts successfully in this deployment:** the option and OS/CPU/heap constraints allow the VM to enter a valid running state.
4. **Currently selected/in use:** this JVM has selected that collector in the current process, via flags or default ergonomics.

A collector can be at level 1 without reaching level 2. Having a recognized flag is not enough to prove startup reaches level 3; a list of supported flags does not tell you which collector is running at level 4.

## 2. Java SE Does Not Standardize the Collector Catalog or `-XX` Flags

`java.lang.System.gc()` is a Java SE API, whereas specific GC algorithms live at the implementation layer. A Java application does not have a standard Java SE method such as:

```text
GarbageCollector.select("Shenandoah");
```

The line above **is illustrative notation, not a Java API**. Collector selection in HotSpot usually happens **at JVM startup** via flags, or is chosen by **ergonomics** by default. You cannot arbitrarily switch collectors while the process is running like changing a Java variable.

The syntax:

```bash
java -XX:+UseG1GC MyApp
```

only has meaning when the JVM binary **supports that HotSpot flag**. The same bytecode program, if run on **OpenJ9**, uses different GC selection and policies. If compiled into a **GraalVM Native Image**, the resulting process **does not run on a regular HotSpot JVM**, so you must check Native Image's GC policy.

**Naming difference:** `Java 17` describes the Java platform version; `HotSpot 17` refers to the corresponding implementation; `Temurin 17` or `Oracle JDK 17` describes a distribution. Do not turn them all into synonymous labels.

## 3. HotSpot: Familiar Choices and Support Conditions

On common HotSpot JDK 17 builds, the frequently mentioned collectors are:

| Collector | Selection flag in HotSpot | Status to check |
| --- | --- | --- |
| **Serial GC** | `-XX:+UseSerialGC` | Single GC worker, generational/traditional STW; usually available in common HotSpot builds |
| **Parallel GC** | `-XX:+UseParallelGC` | Throughput collector with multiple GC workers; usually available |
| **G1 GC** | `-XX:+UseG1GC` | Region-based collector, selected by default in many modern HotSpot configurations |
| **ZGC** | `-XX:+UseZGC` | Low-latency collector; support depends on JDK release, OS/architecture, build, and heap constraints |
| **Shenandoah** | `-XX:+UseShenandoahGC` | Concurrent collector; **not present in every HotSpot binary** even though it is in OpenJDK sources |
| **Epsilon GC** | `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC` | No-op collector for testing/experiments, may not be built/enabled; **does not collect objects** |
| **CMS (removed)** | `-XX:+UseConcMarkSweepGC` in older JDKs | **Removed from upstream HotSpot since JDK 14**, not a valid collector option in standard JDK 17 |

This table distinguishes **what to check**, not a guarantee of availability across every vendor build, JDK minor release, processor architecture, or VM port. Collectors may restrict heap size, compressed pointer support, large pages handling, page mapping, or other requirements.

### Default Does Not Mean G1 Is Always Used

G1 is the default in **many** HotSpot configurations since JDK 9, but JVM ergonomics may choose differently depending on CPU count, memory, VM type, or environment configuration. Therefore:

- **Not passing a flag** means **letting the VM choose**, not a guarantee that the default collector is the same everywhere.
- **Passing `-XX:+UseG1GC`** expresses a specific request and may be rejected if the binary does not support it.
- **Startup logs or effective flags** are what confirm the selected collector.

Do not infer from a machine having many cores that G1 is definitely running, or from a small container that Serial is definitely running.

## 4. JDK Version Changes the Set of Collectors

Collector availability is a **time-dependent property**. A classic example: **ZGC**.

| Upstream OpenJDK/HotSpot milestone | Notable GC change | Meaning |
| --- | --- | --- |
| **JDK 9** | G1 became the default in common HotSpot configurations; CMS deprecated | JDK 8 articles about defaults no longer apply as-is |
| **JDK 11** | ZGC and Epsilon introduced as experimental on eligible builds/platforms | Need to pay attention to experimental/support flags |
| **JDK 12** | Shenandoah integrated in experimental status on supported builds | Cannot equate "in OpenJDK" with "every distribution has it in the binary" |
| **JDK 14** | CMS removed from upstream HotSpot | `UseConcMarkSweepGC` no longer selects CMS on HotSpot 17 |
| **JDK 15** | ZGC and Shenandoah promoted to production features on supported ports/builds | Does not mean every OS/CPU has both |
| **JDK 21** | Generational ZGC introduced as a selectable mode | Need to distinguish non-generational ZGC and generational ZGC |
| **JDK 23** | Generational ZGC became the default mode when selecting ZGC; old mode deprecated | Flags/modes changed |
| **JDK 24** | Non-generational ZGC removed from upstream JDK | Legacy `ZGenerational` configurations should not be copied to newer releases |

**Read the table correctly:** these are documented **upstream** milestones; they do not guarantee that vendors did not backport or ship their own patchsets. For example, a distribution with an older major number might include a GC backport, but you must verify via release notes/build and test runs; **do not assume a backport exists by default**.

### 4.1. The ZGC Case in Detail

On an eligible HotSpot JDK 17, `-XX:+UseZGC` selects the **non-generational ZGC** of that era. Regarding later versions:

- **JDK 21:** Generational ZGC appeared (JEP 439), selectable via `-XX:+UseZGC -XX:+ZGenerational`.
- **JDK 23:** Generational ZGC became the default mode (JEP 474); support status of the old mode changed.
- **JDK 24:** non-generational mode was removed (JEP 490). Do not continue using `-XX:-ZGenerational` intending to revert to the old algorithm.
- **JDK 25+:** read the documentation for the version you are using; do not try to keep a flag just because it worked on JDK 21.

**Important:** Just because the collector "ZGC" exists in both releases does not mean the **algorithm, generation policy, control flags, and memory behavior** are identical. If a migration guide says `ZGenerational` is obsolete/removed, update the configuration accordingly instead of ignoring warnings.

### 4.2. The Shenandoah Case

Shenandoah is a low-pause/concurrent GC integrated in upstream OpenJDK, but there are differences in **which distributions actually build/include it**. When encountering "Shenandoah GC is not supported" or "option not available" in a JDK, do not conclude that **all OpenJDK JDK 17** builds lack Shenandoah.

How to verify: check vendor release notes, test the startup option on the target binary, and inspect the exit code and logs. Some older JDKs also require unlocking experimental options before `UseShenandoahGC`. Do not blindly add `-XX:+UnlockExperimentalVMOptions` if the JDK already treats the feature as production; follow the exact documentation of that build.

### 4.3. CMS as a Removed Case

**Concurrent Mark-Sweep (CMS)** appeared in older HotSpot JDKs, was deprecated in JDK 9, and was **removed in JDK 14** per JEP 363. If old production documentation contains:

```text
-XX:+UseConcMarkSweepGC
-XX:+CMSParallelRemarkEnabled
-XX:CMSInitiatingOccupancyFraction=...
```

these are **historical flags for identifying legacy configurations**, not a recommended command set for JDK 17+. When migrating, you need to choose a supported collector and **re-evaluate the workload**, rather than replacing the string `CMS` with `G1` in every flag and assuming the same semantics remain.

## 5. "Distribution" and "Implementation" Are Two Different Concepts

Java has many vendors/distributions. Some distributions are based on **HotSpot/OpenJDK**, some on **OpenJ9**, or provide other runtimes. A vendor may change packaging, patches, build configurations, and the support matrix per release.

Examples of names you may see in practice:

- **Oracle JDK, Eclipse Temurin, Microsoft Build of OpenJDK, Red Hat build of OpenJDK, Amazon Corretto**: most related release lines use HotSpot/OpenJDK, but **you must check the real binary**; do not rely on a logo/vendor name for every product.
- **IBM Semeru Runtime with OpenJ9** and other OpenJ9-based runtimes: have **different GC policies and flags from HotSpot**.
- **GraalVM running Java on the JVM**: in JVM mode it may use a HotSpot-based runtime; check the mode and distribution.
- **GraalVM Native Image**: runs a native executable with its own runtime, **not a HotSpot JDK running arbitrary `-XX:+Use...GC` flags**.
- **Android ART**: has its own runtime/garbage collector; does not support HotSpot flags by default even if the app is written in Java/Kotlin.

The names here illustrate **families of environments**, not fixed GC feature claims for every product under the same brand.

### Vendor Support Is Not Equal to Availability

A binary may start up with an experimental collector, yet the vendor may not provide the same SLA/operational support as for a production collector. For production use, check:

1. Release notes and the distribution's feature list.
2. Platform support matrix (OS/CPU and containers).
3. Whether experimental/diagnostic unlock flags are required.
4. Whether the collector has long-term vendor support.
5. Heap limits, compressed references, virtual memory, and GC logging.
6. Changes between update releases within the same major version.

Do not use "enabling the flag worked on my laptop" to assume the vendor commits to supporting it in a production container.

## 6. OpenJ9 Does Not Use HotSpot's GC Flag List

**Eclipse OpenJ9** is a different JVM implementation. Its GC policies are typically selected via:

```bash
java -Xgcpolicy:gencon MyApp
```

Some policies in OpenJ9 documentation include:

| OpenJ9 policy | General characteristics | Limitations/notes |
| --- | --- | --- |
| `gencon` | Generational concurrent; nursery/tenure | Usually the default in OpenJ9 docs |
| `balanced` | Regions, multiple heap segments; aims to balance pause/throughput | Some builds only support 64-bit |
| `optthruput` | Throughput-oriented, traditional STW collection | Do not assume it is identical to HotSpot Parallel GC |
| `optavgpause` | Aims for average pause time via its own mechanisms | Cannot use this name on HotSpot by default |
| `metronome` | Real-time/incremental in eligible configurations | Has architecture/platform restrictions; check release docs |
| `nogc` | Performs no GC cycles | Only for very specific workloads/testing |

These policies are **not** 1-to-1 aliases for Serial/Parallel/G1/ZGC/Shenandoah. For example, `gencon` does not mean you are running G1; two collectors may both be generational while having different algorithms and heap structures.

### Detecting the JVM Implementation Before Choosing a GC

Use:

```bash
java -version
java --version
```

On modern Java releases, output may contain `OpenJDK 64-Bit Server VM`, `Eclipse OpenJ9 VM`, or other labels. Do not hard-code the entire version string as a mandatory standard format.

If you have identified the JVM as OpenJ9, read the **OpenJ9 GC policy docs and `java -Xgcpolicy:help`/`-Xhelp` if supported by the binary**. Do not pass `-XX:+UseZGC` to an OpenJ9 application and treat the "unrecognized option" error as a Java bug.

### Example of Non-Portable Commands

```text
HotSpot: java -XX:+UseG1GC MyApp
OpenJ9:  java -Xgcpolicy:gencon MyApp
```

They **do not mean the same thing**; they are simply valid collector configuration examples when supported by the respective implementation. The same `MyApp.class` bytecode can run on both JVMs, but startup tuning flags **cannot be copied verbatim**.

## 7. GraalVM: Separate JVM Mode from Native Image

The name "GraalVM" easily leads learners to mix up **a JVM runtime** with **a native executable created by Native Image**.

### 7.1. Running Java Bytecode on the JVM

If using a HotSpot-compatible Java launcher in a GraalVM distribution to run `java MyApp`, GC options must be checked against the actual JVM implementation/build/version. Having the Graal JIT compiler does not turn the garbage collector into an algorithm named "Graal GC".

### 7.2. Building and Running Native Image

**Native Image** compiles a Java application into a **native executable** using its own runtime memory management. For example, Native Image documentation describes:

- **Serial GC** is the default in many Native Image builds.
- **G1** and **Epsilon** may have availability depending on edition/version/OS/architecture.
- Builder configuration looks like `native-image --gc=serial ...` or `--gc=G1` when that mode is supported.

```bash
native-image --gc=serial HelloApp
```

This is an **example of selecting GC at build time**, which only runs when the Native Image tool is installed and a valid `HelloApp` class/application exists. Do not assume a native binary can switch collectors with:

```text
./helloapp -XX:+UseZGC
```

The line above **is only to illustrate a mistake**, not a recommended command. HotSpot's `-XX:+UseZGC` parameter has no automatic meaning on the Native Image runtime. Look up the exact **Native Image memory management and build options** for the edition/release in use.

**Common point of confusion:** the name "Serial GC" appearing in both HotSpot and Native Image does not prove the two runtimes share the same heap layout, collection phases, or flags.

## 8. Operating System and CPU Architecture Can Exclude a GC

Even when JVMs share the same source version, not every collector has equal port/implementation coverage across:

- Windows, Linux, macOS, and Unix variants.
- x86-64/AMD64, AArch64/ARM64, PPC64, s390x, and other architectures.
- 32-bit versus 64-bit.
- Levels of support for virtual-memory reservation, OS page mapping, and CPU instructions.
- Containers with memory cgroups, CPU quotas, page sizes, and security restrictions.

**Mental example:** a concurrent/low-latency GC may require virtual memory or address space management capabilities that an OS/CPU port does not yet support. In that case, the `Use...GC` flag may exist in project-level documentation, while the binary on the target platform refuses to start.

Do not state a blanket rule like "ZGC always supports Windows/AArch64" or "Shenandoah never supports macOS" without tying it to a specific **release/build/version**, because ports continue to expand. Instead, **run tests on the real image/container/VM** and read the vendor's support matrix.

### Containers Do Not Change the JVM Implementation, But They Change the Environment

A Docker image can:

- Use a **different JRE/JDK** than your laptop even if both print "Java 17".
- Use a different OS libc/architecture.
- Run with smaller CPU quotas and heap limits.
- Use a JVM binary compiled with different features.
- Be constrained by PID, page mapping, or native memory resource limits.

Therefore, a collector that works on a laptop **must not be considered verified in a container**. Run the same verification commands **inside the production image/container**, not only on the host machine.

## 9. Docs Say the Collector Is Available, Why Does the JVM Still Reject It?

Errors should be categorized before fixing:

| Startup symptom | Possible meaning | What to do |
| --- | --- | --- |
| `Unrecognized VM option 'UseShenandoahGC'` | Flag is not recognized in the current binary | Check VM implementation/version/build |
| `Unrecognized VM option 'UseConcMarkSweepGC'` | Flag has been removed in this release | Migrate off CMS flags |
| `Unrecognized option: -Xgcpolicy:gencon` | Using an OpenJ9 flag with HotSpot | Choose syntax matching the JVM |
| `Option ... is experimental and must be enabled via UnlockExperimentalVMOptions` | Feature is currently experimental in that build | Check docs, then enable unlock **when supported** |
| `... is not supported on this platform` | Flag/collector exists, but the current port is not eligible | Check vendor platform matrix |
| `Error occurred during initialization of VM` | JVM failed during initialization, possibly due to heap/GC/flag conflicts | Read the **next cause line**, not just the headline |
| JVM runs, but expected GC is not seen | Default ergonomics or option was not passed to the right process | Check startup logs and VM.flags |
| Warning "Ignoring option..." | Flag is obsolete/removed/no longer effective | Fix configuration; **do not treat a warning as successful collector selection** |

The message text in the table represents **classification patterns**, not guaranteed exact wording across all HotSpot/OpenJ9 builds. There are also cases where the VM accepts the syntax and then refuses to initialize due to memory constraints or conflicting options.

### Do Not Use `IgnoreUnrecognizedVMOptions` to Hide GC Misconfiguration

Some HotSpot builds allow:

```text
-XX:+IgnoreUnrecognizedVMOptions
```

This can cause a misconfiguration to **not fail startup**, and the collector you thought was enabled **is not selected**. In operations requiring a deterministic GC policy, ignoring unknown flags is dangerous: the app still runs, but latency and footprint differ from expectations.

Prefer **fail fast**, log flag selection, and verify the active collector. Only use unknown-flag ignoring mechanisms when there is a clear compatibility management reason and the fallback behavior has been verified.

## 10. Verification Workflow on a Real Runtime

You do not need to write a complex application to perform an initial availability check. With the real JDK/launcher:

### Step 1 — Identify the Binary

```bash
java -version
java --version
```

Record the **full build string**, vendor, and VM name. If multiple `java` binaries exist on the system, ensure the command is invoked from the **right `PATH`** or absolute path. Do not take the `javac` version on the host machine to infer the `java` version inside a container.

### Step 2 — Check the Default Collector

On **HotSpot** supporting unified logging:

```bash
java -Xlog:gc=info -version
```

Look for the line describing the selected collector, e.g. `Using G1` or `Using Serial`; this is only a wording/log pattern, not guaranteed stdout. If the VM does not support `-Xlog`, use the vendor's corresponding instructions.

### Step 3 — Try Starting with a Specific Collector

On HotSpot, test **one flag per run**, do not combine four conflicting `Use...GC` flags:

```bash
java -XX:+UseSerialGC -Xlog:gc=info -version
java -XX:+UseParallelGC -Xlog:gc=info -version
java -XX:+UseG1GC -Xlog:gc=info -version
java -XX:+UseZGC -Xlog:gc=info -version
java -XX:+UseShenandoahGC -Xlog:gc=info -version
```

These are **separate tests**, not a list of commands guaranteed to succeed. If a command reports an error on the target JVM, **record the error**; do not assume the flag/collector is present. For experimental Epsilon (only when supported by the JDK):

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -version
```

**Epsilon does not perform GC:** do not use it as a production collector for workloads that need continuous memory reclamation.

### Step 4 — Verify Beyond Just Checking the Exit Code

On supported HotSpot builds:

```bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
```

Look for `UseG1GC` having the appropriate effective value and no startup warnings. Also read **GC logging** if present. `PrintFlagsFinal` produces long output, and flag names vary by release. If the JVM uses a default collector, some flags may be set via ergonomic selection; read the effective values instead of inferring from application config.

### Step 5 — Measure on a Real Workload

Run the app with the same heap/CPU/container quota and GC logging, and compare **pause/throughput/after-GC live heap/native memory**. A JVM that can start with `UseZGC` does not prove that collector is suitable for a heap of a few tens of MB or a very low CPU quota.

### Step 6 — Record Reproducible Results

A good record includes:

```text
JVM vendor:
JVM implementation:
JDK version + build:
OS / architecture:
Container image digest:
CPU quota:
Memory limit:
Collector requested:
Effective collector:
Startup exit status:
GC log evidence:
Heap flags:
Observed pause/throughput:
Vendor support reference:
```

This is a **diagnostic form template**, not measured data. Keep this record in operations/CI config so that after the next JVM upgrade you know whether collector support changed.

## 11. Java 17+: Program to Identify JVM and GC via MXBeans

Using the public Java Management API, you can read the **GC bean names** exposed by the runtime. This is useful when you need to identify the actually running JVM, **but bean names are not standardized into a portable GC algorithm table across JVMs**.

Create **`GcRuntimeProbe.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class GcRuntimeProbe {
    public static void main(String[] args) {
        System.out.println("java.version: "
                + System.getProperty("java.version"));
        System.out.println("java.vendor: "
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name: "
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version: "
                + System.getProperty("java.vm.version"));
        System.out.println("os.name: "
                + System.getProperty("os.name"));
        System.out.println("os.arch: "
                + System.getProperty("os.arch"));
        System.out.println("available processors: "
                + Runtime.getRuntime().availableProcessors());

        List<String> collectors = new ArrayList<>();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            collectors.add(bean.getName());
        }
        Collections.sort(collectors);

        System.out.println("collector beans: " + collectors);
        System.out.println("bean count: " + collectors.size());
    }
}
```

Compile:

```bash
javac -encoding UTF-8 GcRuntimeProbe.java
```

Run on HotSpot with supported collectors:

```bash
java GcRuntimeProbe
java -XX:+UseSerialGC GcRuntimeProbe
java -XX:+UseG1GC GcRuntimeProbe
```

**Output lines have a fixed format, but values depend on the runtime:**

```text
java.version: <JVM version>
java.vendor: <vendor>
java.vm.name: <VM name>
java.vm.version: <VM build>
os.name: <OS>
os.arch: <CPU architecture>
available processors: <CPU count seen by runtime>
collector beans: [<bean names exposed by VM>]
bean count: <bean count>
```

Items between `<...>` are **placeholder notation describing environment-dependent data**, not literal output printed by the code. On HotSpot Serial GC, bean names usually include `Copy` and `MarkSweepCompact`; on HotSpot G1 they usually include `G1 Young Generation` and `G1 Old Generation`; some newer collectors or an OpenJ9 build will name them differently.

**Do not write a test asserting `collector beans` must have exactly 2 elements on every collector.** MXBeans describe the VM's management view; a collector may expose a different number of beans than the number of actual GC algorithms.

### Why Does `java.vm.name` Matter?

`java.version` only tells the public-facing Java version. `java.vm.name` helps distinguish a HotSpot-based VM from OpenJ9 or another runtime; `java.vendor` tells the issuer. Combining these three values with OS/arch gives a clearer picture than a single product name.

**If running Native Image:** `java.vm.name` and Java Management API tools may not apply the same way as in JVM mode; do not use this same pattern as a test for every native executable without verifying API support.

## 12. Java 17+: Workload to Exercise the Selected Collector

To check startup availability, `-version` is usually enough for an initial option check. To observe the collector executing in a workload, create **`GcAllocationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GcAllocationDemo {
    private static volatile Object last;

    public static void main(String[] args) {
        List<byte[]> keep = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 400; i++) {
            byte[] block = new byte[128 * 1024];
            block[0] = (byte) (i % 100);
            checksum += Byte.toUnsignedInt(block[0]);

            if (i % 80 == 0) {
                keep.add(block);
            }
            last = block;
        }

        System.out.println("checksum: " + checksum);
        System.out.println("retained arrays: " + keep.size());
        System.out.println("bytes per array: " + keep.get(0).length);
        System.out.println("done");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 GcAllocationDemo.java
java -XX:+UseSerialGC -Xms32m -Xmx64m GcAllocationDemo
```

**Standard output of the program when GC logs are not enabled:**

```text
checksum: 19800
retained arrays: 5
bytes per array: 131072
done
```

Explanation:

- 400 iterations; `i % 100` runs through 0..99 for **four cycles**, each cycle summing to `4950`, so checksum is **19800**.
- `keep` stores arrays at `i=0,80,160,240,320`, totaling **5**; each array is `128 × 1024 = 131072` bytes long.
- `last` is a volatile static field ensuring the allocation path has an observable effect and references the most recent array; the number of GC cycles/tenuring still depends on the collector.
- Total bytes requested for allocation in the loop exceed 50 MiB, but that does not mean 50 MiB are reachable at the same time.
- **Do not assert** that the JVM must trigger a specific young/full GC: heap ergonomics, optimizations, and collection policies differ.

Compare **separate runs** on the target HotSpot:

```bash
java -XX:+UseParallelGC -Xms32m -Xmx64m -Xlog:gc=info GcAllocationDemo
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc=info GcAllocationDemo
java -XX:+UseZGC -Xms128m -Xmx256m -Xlog:gc=info GcAllocationDemo
```

**Conditional note:** the last run is only an example to test ZGC when supported by the JDK/OS/architecture/budget. Increasing the heap for ZGC means it is no longer an apples-to-apples throughput comparison with the first two runs; it is for **checking runnability and reading logs**, not ranking performance. If the VM reports the option/heap/platform is unsupported, record it and stop testing that collector.

### Log Output Has No Single Expected Value

A HotSpot JVM might print something like:

```text
[info][gc] Using G1
[info][gc] GC(...) Pause Young (...) ...ms
```

This is an **illustrative log pattern**, not literal code stdout or a promise of exactly two lines. Logs depend on flags, collector, JDK version, and load level. Even a GC with good startup support may not trigger a cycle in a demo that is too short.

## 13. CI/CD: Verify Before and After Upgrading the JDK

When an application has GC requirements, **upgrading the JVM** is more than changing a version number:

- A flag may be deprecated/obsolete/removed.
- A collector may move from experimental to production.
- A generational mode may become the default or the only choice.
- The vendor may change the base image, OS layer, architecture, or build option.
- CPU/container memory limits may change how the JVM picks the default.
- Performance/regressions may differ even when the collector keeps the same name.

### Example of Early Check During Container Build

For HotSpot with a fixed requirement for G1:

```bash
java -XX:+UseG1GC -Xlog:gc=info -version
```

Place an equivalent step in the test image/runtime. Verify:

1. Command **exit code equals 0**.
2. No warnings for removed/unrecognized GC flags.
3. GC startup log/flags confirm the desired collector.
4. Runtime vendor/architecture matches the target.
5. Ability to run the application with realistic heap/CPU limits.
6. GC metrics on a smoke test workload and representative load.

### Do Not Use Silent Automatic Fallback

Example deployment pseudocode:

```text
If ZGC fails to start:
    automatically remove UseZGC and run default collector
```

This is **policy pseudocode**. Unless architecture has approved the fallback and SLO checks exist, automatically switching collectors can put production into a state that **runs, but with bad latency**. Fail fast + rollback/alert is usually safer for services requiring specific GC behavior.

You can proactively design a list of valid collectors for each environment, but you must document the **support conditions and benchmarks** for each choice.

## 14. Troubleshooting Real-World Scenarios

### Case A — "I am using JDK 17, but the Shenandoah flag says unrecognized"

**Do not jump to the conclusion** that the JVM is broken: identify `java -version`, vendor, build, OS/arch. Check whether the distribution builds Shenandoah and read its release notes. If production needs Shenandoah, **choose a supported runtime build**, rather than copying a flag from another JDK.

### Case B — "CMS worked on JDK 8, upgrading to 17 fails startup"

CMS was removed from upstream HotSpot in JDK 14. Old CMS configurations are no longer valid. You need to **migrate** to a supported collector (typically trying the default/G1 or another choice), remove related flags, and re-benchmark pause/throughput.

### Case C — "JDK 21 ran `ZGenerational`, JDK 24 warns/does not recognize it"

ZGC changed: generational mode became default in JDK 23; non-generational was removed in JDK 24. Use **JDK24+ GC docs** and prune obsolete flags instead of trusting old output.

### Case D — "Same Java 17, one image uses G1 while another uses Serial"

Check the **VM binary, CPU quota, memory limits, startup flags, and default ergonomics**. Having only the major version is insufficient data. If the collector matters for SLOs, pass the verified flag and log it.

### Case E — "Copied `-Xgcpolicy:balanced` from OpenJ9 to HotSpot"

Wrong implementation namespace: an OpenJ9 flag is not a HotSpot flag. Use the right runtime GC policy; do not try to map the name "balanced" to G1 by wording.

### Case F — "GraalVM Native Image app says `UseG1GC` is not supported"

Determine whether you are running **JVM mode** or a **Native Image executable**. Native Image GC selection is done via Native Image's builder/runtime options (e.g., `--gc=...` at build time). Verify the edition/OS/arch and corresponding documentation.

### Case G — "Flag is accepted, yet the process still uses a different collector"

You may be running a **different binary via PATH**, the option may be configured for the build step rather than runtime, the flag may be ignored/obsolete, or default selection differs from expectations. Capture the full startup command and flags/logs of the **exact PID/process**.

### Case H — "Suitable GC exists, but heap is too small so startup fails"

The collector exists in the binary, but **does not satisfy runtime constraints**; reasonably increase the test heap within container limits or choose another supported collector. Do not use a failed startup heap requirement to conclude that the collector is absent from the JDK.

## 15. Common Reasoning Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "Java 17 has the same GC list everywhere." | Vendor, JVM implementation, build, and platform can differ |
| "An accepted JEP means every binary builds that collector." | Build-time options and vendor packaging still apply |
| "A flag printed in the list means the collector is running." | Only startup/VM flags/logs verify selection |
| "Successful GC startup means performance is suitable." | Must benchmark and observe pause/throughput/footprint |
| "G1 is always the default on every JVM." | Default is an implementation/ergonomics decision |
| "If a JVM accepts `UseSerialGC`, it uses the HotSpot implementation in all cases." | Similar names can exist in other runtimes without the same semantics |
| "Shenandoah is in OpenJDK source so Oracle/Temurin/... must all have it." | Feature/build support varies by distribution/release |
| "ZGC mode did not change between JDK 17 and 24." | Generational transitions changed it |
| "CMS is still available on HotSpot 17 if you add experimental unlock." | CMS was removed from upstream JDK14 |
| "OpenJ9 `gencon` is just another name for G1." | Different algorithm/GC policy |
| "Native Image uses all HotSpot `-XX` flags like JVM mode." | Runtime selection differs and has its own build-time options |
| "Same OS means same GC support." | CPU arch, JDK build, vendor, and release also matter |
| "Containers do not affect collector selection." | CPU/memory limits and image binary can affect it |
| "`-Xmx` is total process memory." | Native memory/stacks/metaspace/code cache live outside the heap |
| "One `-version` test is enough to prove GC meets p99 goals." | That is only a startup availability step; a workload is needed |
| "Ignoring unrecognized flags is a fix." | Can silently switch collectors and cause regressions |
| "Two GCs with similar names are the same implementation." | Names and policies can differ by JVM |
| "Minor JDK updates definitely do not change GC behavior." | Vendor fixes/ergonomics can change |

## 16. Self-Check Exercises

**Exercise 1.** Two machines both use Java 17, but one has Shenandoah and the other does not. Does this contradict Java SE?  
**Answer:** No. Different GC implementations/builds/vendors do not violate Java semantics as long as the VM meets the Java SE contract.

**Exercise 2.** `java -version` shows OpenJ9. Can `-XX:+UseZGC` be used like on HotSpot?  
**Answer:** Not by default. You must look up OpenJ9 GC policies/flags, for example `-Xgcpolicy:gencon`.

**Exercise 3.** A HotSpot JDK 17 has `-XX:+UseZGC` but refuses to start in a container. Does this prove ZGC is absent from the binary?  
**Answer:** Not enough. Check platform/heap/memory constraint messages, CPU, build, and conflicting flags.

**Exercise 4.** Why not use `-XX:+UseConcMarkSweepGC` on HotSpot 17?  
**Answer:** CMS was removed in upstream JDK 14; you need to migrate and re-measure.

**Exercise 5.** When selecting ZGC on JDK 21, how do you enable generational mode?  
**Answer:** On a supported build, use `-XX:+UseZGC -XX:+ZGenerational` per JEP 439 and verify startup.

**Exercise 6.** On JDK 24, can you disable generational to go back to non-generational ZGC?  
**Answer:** No; non-generational mode has been removed upstream.

**Exercise 7.** Can `-Xgcpolicy:balanced` be used on HotSpot because "balanced" sounds like G1?  
**Answer:** No. That is an OpenJ9 policy, not HotSpot G1 syntax.

**Exercise 8.** Why is it necessary to check both JVM vendor and VM name?  
**Answer:** Vendor/distribution and implementation are two different axes; the vendor name alone does not guarantee the VM type or GC build.

**Exercise 9.** `GarbageCollectorMXBean` reports "G1 Young Generation". What does this prove?  
**Answer:** The VM exposes a management bean with that name; on HotSpot it is useful evidence of the active GC, though it should be combined with flags/logs when strict verification is required.

**Exercise 10.** Does a Native Image binary have G1?  
**Answer:** Depends on version/edition/platform/build-time option; do not infer from GraalVM JVM mode's `java` having G1.

**Exercise 11.** Does a GC marked experimental have production support by default?  
**Answer:** Not by default. You must check vendor release notes/support policy.

**Exercise 12.** Why is startup success not enough for choosing a GC?  
**Answer:** You do not yet know pauses, throughput, live set, memory footprint, and SLO fit under real load.

**Exercise 13.** Can the same Java image on a laptop and a different-architecture container have different GC support?  
**Answer:** Yes, if binaries/OS/architecture/features differ; you must test on the target container.

**Exercise 14.** `UseG1GC` is listed in `PrintFlagsFinal`, but `UseSerialGC` is the one selected. What is the conclusion?  
**Answer:** The G1 flag appearing does not mean it is enabled; read the effective values of the flags and the startup log.

**Exercise 15.** A deployment sets `IgnoreUnrecognizedVMOptions` to keep the service running when a GC option fails. What is the risk?  
**Answer:** The service may start with a different collector without the team knowing, causing latency/performance regressions.

**Exercise 16.** When updating JDK from 21 to 24, do ZGC flags need to be re-checked?  
**Answer:** Yes. Generational ZGC was optional in JDK21, default from JDK23, and non-generational mode was removed in JDK24.

**Exercise 17.** If two HotSpot distributions both support G1, is their performance necessarily identical?  
**Answer:** No. Build flags, JDK patch level, OS, CPU quotas, heap ergonomics, and workload still have an impact.

**Exercise 18.** To verify the collector of a running process, what should be used?  
**Answer:** JVM version/vendor/VM name, startup GC logs, effective VM flags, `jcmd VM.flags` when supported, and GC MXBeans/JFR depending on the JVM.

## 17. Checklist Before Deciding On or Upgrading a Collector

- [ ] Identified the **JVM implementation** instead of only knowing "Java 17/21/25"?
- [ ] Recorded full vendor, build number, and JDK major/update?
- [ ] Verified OS, CPU arch, container image digest, and necessary libc/page/memory constraints?
- [ ] Read the **release notes + support matrix** for the exact version/vendor?
- [ ] Distinguished experimental/production/deprecated/removed?
- [ ] Tested starting up with **one** collector option at a time?
- [ ] Checked **exit status**, warnings, and startup GC log?
- [ ] Verified the **actual** collector instead of guessing from the option name?
- [ ] Not using `IgnoreUnrecognizedVMOptions` to hide wrong GC options?
- [ ] Checked heap sizing, CPU quota, and native memory budget?
- [ ] Measured pauses, throughput, and memory footprint on representative load?
- [ ] Have tests after JDK major/minor updates to detect obsolete flags?
- [ ] Have a rollback/fail-fast policy if the required collector cannot be used?
- [ ] Not copying flags between HotSpot, OpenJ9, and Native Image without adaptation?
- [ ] Saved the results so the operations team can reproduce them?

## 18. Conclusion

**GC availability is a property of a _specific runtime_, not of the Java language in general.** A collector can be described in a JEP, named in flag help, built into HotSpot, and start on Linux x86-64, yet be absent from another distribution/architecture. A previously valid mode can also be removed across newer releases; CMS and non-generational ZGC are classic examples.

Always verify in order:

```text
JDK vendor / VM implementation
        ↓
Full JDK build and release notes
        ↓
OS + CPU + container constraints
        ↓
Is the GC option supported?
        ↓
Does startup succeed?
        ↓
Which collector is actually selected?
        ↓
Does it meet SLOs and memory budget under load?
```

**If you remember only one rule:** do not ask "Does Java have ZGC/Shenandoah?" in the abstract; ask **"Does this JVM binary, in this deployment environment, with this set of flags and heap, support and currently use that collector?"**

### Original References

- Oracle JDK 17 — **HotSpot Available Collectors**: https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- Oracle JDK 17 — **The java Command / HotSpot GC flags**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17 — **Garbage Collection Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- OpenJDK — **JEP 333: ZGC**, **JEP 377: ZGC production**, **JEP 439: Generational ZGC**, **JEP 474: Generational by default**, **JEP 490: Remove Non-Generational Mode**: https://openjdk.org/jeps/333 ; https://openjdk.org/jeps/377 ; https://openjdk.org/jeps/439 ; https://openjdk.org/jeps/474 ; https://openjdk.org/jeps/490
- OpenJDK — **JEP 189: Shenandoah**, **JEP 379: Shenandoah production**, **JEP 363: Remove CMS**: https://openjdk.org/jeps/189 ; https://openjdk.org/jeps/379 ; https://openjdk.org/jeps/363
- Eclipse OpenJ9 — **GC Policies**: https://eclipse.dev/openj9/docs/gc/ and https://eclipse.dev/openj9/docs/xgcpolicy/
- GraalVM — **Native Image Memory Management**: https://www.graalvm.org/dev/reference-manual/native-image/optimizations-and-performance/MemoryManagement/
- Java SE 17 — **GarbageCollectorMXBean**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

**Documentation may change by version:** when researching collectors on JDKs newer than JDK 17, always choose the exact documentation section for the running release; do not copy an old matrix as a fixed truth for all future JDKs.