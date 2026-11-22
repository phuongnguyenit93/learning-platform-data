# Identifying the Right Running JDK, Vendor, VM Version, and Architecture

## 1. The problem: what does “this machine has Java 17 installed” fail to answer?

When configuring resources, choosing a garbage collector, running a program that requires JNI, investigating a deployment error, or tuning HotSpot, the question to answer is not just “whether the machine has Java or not”. You need to know exactly **which runtime the running Java process is actually using**, **which vendor**, **which VM implementation/build**, and **which architecture**.

There are at least four layers that are easy to confuse:

1. **JDK used for building**: `javac`, `jar`, and the tools that CI/IDE invoked.
2. **Java launcher used to start**: the `java` executable resolved via an absolute path, `PATH`, wrapper, or container entrypoint.
3. **JVM executing the application process**: the actual information reported by `Runtime.version()`, `System` properties, and `jcmd` of the **exact PID**.
4. **Host/OS/container/native ABI**: where the process is running, CPU/memory limits, the actual architecture of the binary, and native libraries.

The four layers may **not overlap**. For example:

```text
Developer laptop:
  JAVA_HOME = /opt/jdk17
  PATH      = /usr/local/bin:/opt/jdk21/bin:...

Build pipeline:
  ./gradlew runs on JDK 21 but uses --release 17 when compiling

Production container:
  /opt/runtime/bin/java is a custom JDK 17 image
  host kernel reports x86_64, container limits 2 CPUs

Application:
  System.getProperty("java.vendor") and
  System.getProperty("java.vm.name") come from the process runtime
```

Do not take the `JAVA_HOME` value of the current shell to assert that another process is using that same runtime; do not look at `javac -version` and infer the JVM version of the service; do not look at `uname -m` on the host and assert the architecture of every JVM inside containers.

**Goal of this lesson**: accurately identify runtime identity, distinguish **Java feature release / update / build**, **vendor / VM name / VM version**, **OS/CPU architecture / process bitness / native ABI**, read the configuration of the **exact process**, and build a reproducible investigation checklist on **Java 17+**.

---

## 2. Minimum set of questions to answer before tuning

Before applying `-Xmx`, `-Xss`, `-XX:+UseG1GC`, or opening a JNI library, clearly note:

| Question | Common sources | Why is it important? |
| --- | --- | --- |
| Which Java feature is the JVM using? | `Runtime.version().feature()`, `java.version` | Check APIs/class-file compatibility |
| Which exact release/update/build? | `Runtime.version()`, `java -version` | Bug fixes, compiler/GC behavior, and vendor-specific incidents |
| Who distributes the runtime? | `java.vendor`, `java.vendor.url` | Support, security updates, distribution |
| Which JVM implementation? | `java.vm.name`, `java.vm.vendor` | HotSpot/OpenJ9 or other implementations have different options |
| VM implementation version? | `java.vm.version`, `jcmd PID VM.version` | Diagnostics and build-dependent flags |
| Where is the runtime installed? | `java.home`, executable command/path | Trace the launcher or libraries bundled with the exact runtime |
| What architecture is the runtime process? | `os.arch` plus OS binary inspection | Choose the right JNI native lib, CPU-specific features |
| Is the runtime 64-bit? | VM output, binary/ABI tools, HotSpot-specific `sun.arch.data.model` | Native pointer width, address space, memory limits |
| What are the host OS and container like? | `os.name`, container/OS tools, `-XshowSettings:system` (when supported) | CPU quota, memory limits, and Linux cgroup |
| What are the effective VM flags? | `jcmd PID VM.flags`, `-XX:+PrintFlagsFinal` | Ergonomic defaults may differ from declared options |
| Are the Java executable and javac from the same JDK? | Absolute paths, `java -version`/`javac -version` | Avoid building right but deploying wrong |
| Is this the exact application PID of interest? | PID + `VM.command_line` + `VM.version` | One machine can run multiple Java services |

Capture information by **actual process and point in time**, especially after a rolling deployment or when pods are replaced.

## 3. Java release, patch, build: don't just read “17”

**Java feature version** is the major language/API generation such as 8, 11, 17, 21. Updates within the same feature release can differ significantly in bug fixes, security patches, CPU/OS support, and HotSpot behavior.

Since Java 10, the version string is interpreted according to these components:

```text
$FEATURE.$INTERIM.$UPDATE.$PATCH
       -<PRE_RELEASE>+<BUILD>-<OPTIONAL>
```

Trailing zero components are usually omitted; prerelease/build/optional metadata labels depend on the release and vendor.

Example **illustrating the format**, not asserting that it is the latest version:

```text
17.0.12+7
  feature = 17
  interim = 0
  update  = 12
  patch   = 0 (absent in string)
  build   = 7
```

With Java 17:

```java
Runtime.Version v = Runtime.version();
int feature = v.feature();
int interim = v.interim();
int update = v.update();
int patch = v.patch();
java.util.Optional<Integer> build = v.build();
```

This is an **illustrative API snippet**; the standalone runnable file is in section 10. `Runtime.Version` also provides information about pre-release/optional metadata. Do not parse the version string yourself with `split("\\.")` and assume every build only has three plain numbers: there may also be a `+` sign, a prerelease tag, or vendor-specific metadata.

### 3.1. Why is the feature version not enough to evaluate compatibility?

- **Class files:** Java 17 has major class-file version **61**. A Java 11 runtime cannot execute major 61 classes according to the normal spec.
- **API:** `javac --release 17` controls source/target/public API compatibility for Java 17, but does not make a native library of one architecture run on another architecture.
- **JVM options:** two HotSpot 17 patch builds may differ in behavior/supported diagnostics or default heuristics.
- **Binary archive:** a CDS archive created from JDK build A must not be considered portable to JDK build B just because both print “17”.
- **Security:** an older runtime and a newer runtime both on Java 17 may differ in security fixes.

### 3.2. `java.version`, `java.runtime.version`, and `java.vm.version` are different

| Property | Main meaning | Should not be inferred |
| --- | --- | --- |
| `java.version` | Version of the Java Runtime Environment | Not the entire identity of the JVM binary |
| `java.runtime.version` | Version string of the Java runtime if provided by the implementation | Not necessarily the same string as the JVM version |
| `java.vm.version` | Version of the VM implementation | Does not itself identify the Java launcher path |
| `java.specification.version` | Java SE runtime specification feature version | Does not include vendor/patch/build |
| `java.vm.specification.version` | JVM specification version | Not equal to the JIT compiler implementation version |
| `java.class.version` | Highest class-file format version the runtime reports supporting | Does not mean every loaded class was compiled with that version |

**Note:** The JDK 17 `System` API describes standard system properties, but some properties are implementation-specific, optional, or can be modified by code/launch commands. Important conclusions should **cross-check at least two sources**, for example `java -version`, `System` runtime properties, and `jcmd PID VM.version`.

### 3.3. Do not confuse JVM specification vendor with runtime vendor

For example, `java.vm.specification.vendor` describes the **entity issuing the JVM specification**; it is not necessarily the vendor of the HotSpot binary you are running. To identify the distribution/vendor, prioritize reading `java.vendor`, and cross-check `java.vm.vendor`, `java.vm.name`, and the startup banner.

## 4. Vendor, distribution, implementation, and “VM name”

**Vendor/distribution** answers “who built/distributed/supports the runtime you installed?”. **Implementation** answers “which JVM engine executes bytecode/JIT/GC?”. One vendor can distribute multiple types of runtimes; conversely, multiple vendors build based on OpenJDK/HotSpot.

| Component | Illustrative example | Thing to remember |
| --- | --- | --- |
| JDK distribution/vendor | Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK | Vendor does not by itself determine the GC/VM implementation |
| VM implementation | HotSpot, Eclipse OpenJ9, GraalVM Java runtime based on HotSpot in certain configurations | Diagnostics/flags may differ |
| `java.vm.name` | May report `OpenJDK 64-Bit Server VM` or a vendor-specific form | The string is not a unique standard identifier |
| `java.vm.vendor` | VM implementation vendor/distributor metadata | May differ from `java.vendor` or have the same value |
| `java.vm.version` | VM build/version | Do not infer “VM build number = JDK patch number” |
| `java.home` | Directory of the current Java runtime | Not `JAVA_HOME` of the build shell |
| `java.vendor.version` | Vendor version, if provided | May be absent (`null`) |

**The name “OpenJDK” does not mean a single vendor**. OpenJDK is a source code project and many distributions are built from it. “OpenJDK 64-Bit Server VM” describes a type of VM; the vendor is in another field.

### 4.1. Is the vendor string as stable as an enum?

No. The vendor name can change by distribution/build or packaging method; it is an **identifying string**, not a standard enum with all vendors fixed.

Do not write production logic like:

```java
if (System.getProperty("java.vendor").equals("Oracle Corporation")) {
    // Wrong to assume every other implementation definitely does not support Java 17 APIs.
}
```

The snippet above is a **counterexample**. If you need the Java API version, use `Runtime.version().feature()` and appropriate feature-detection. If you need a **HotSpot-only flag**, check **VM implementation + actual flag availability**; do not assume only one vendor has HotSpot.

### 4.2. “JDK 17” does not guarantee the VM is HotSpot

Some Java 17 distributions may use a VM implementation other than HotSpot. Tools/options such as `-XX:+PrintFlagsFinal`, Native Memory Tracking, `jcmd` subcommands, and HotSpot code cache/G1 internals are not portable Java SE APIs.

If `java.vm.name` is OpenJ9 or another VM, use the **manual for the exact implementation** instead of applying a set of HotSpot diagnostics and concluding “the JVM is broken because it doesn't accept the flag”.

## 5. JDK vs JRE/runtime image vs Java launcher vs `javac`

Previously learners often distinguished JDK/JRE, but with JDK 17 you also have a **custom runtime image** built with `jlink`. An application can run with a runtime image **without `javac`**, even though the Java 17 runtime is complete for the modules the application needs.

```text
Full JDK:
  bin/java
  bin/javac
  bin/jar
  bin/jcmd
  ... modules/tools

Custom runtime (jlink):
  bin/java
  selected modules
  may not contain javac/jcmd
```

**`java.home`** inside the process points to the actual runtime installation directory reported by the JVM. Its lack of a `javac` compiler does not prove “not Java 17” or “broken runtime”.

### 5.1. Commands to run on the exact machine

**Linux/macOS (POSIX shell):**

```bash
command -v java
command -v javac
type -a java
type -a javac
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
"$JAVA_HOME/bin/java" -version
```

Commands using `"$JAVA_HOME/bin/java"` assume `JAVA_HOME` **is already set properly and points to a valid JDK**; if the variable is empty/non-existent, the command will fail. `type -a` is a utility commonly available in Bash, not a portable feature of all POSIX shells. On macOS, `readlink -f` is not always available; do not copy Linux symlink resolution instructions to macOS without checking.

**Windows PowerShell:**

```powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
$env:JAVA_HOME
& "$env:JAVA_HOME\bin\java.exe" -version
```

You need to distinguish **PowerShell PATH resolution**, functions/aliases/wrappers, and the final binary path. A shell may invoke a script shim, package manager launcher, or symlink rather than `java.exe` directly.

### 5.2. Why can `java -version` and `javac -version` differ?

- `PATH` prioritizes the `java` binary of JDK A, while `javac` is from JDK B.
- Build tools use Java Toolchains and separately pick a compiler from another JDK.
- The IDE uses a project SDK or boot JDK separate from the shell.
- The Maven/Gradle daemon was already started earlier with a different JDK.
- The CI worker configured `JAVA_HOME` after the daemon/service started.
- The runtime image only has the Java launcher, while the compiler comes from another JDK.
- The container runtime image differs from the builder stage.

If `javac` belongs to JDK 21 while `java` belongs to JDK 17, the default compile command produces a newer class version that can cause `UnsupportedClassVersionError` at runtime. Use `javac --release 17` to target Java 17 and **test on the exact target runtime**, not just by looking at a toolchain named “Java”.

### 5.3. `java -version` is not `java --version` on every older JVM

On the Java 17 launcher, both `-version` and `--version` are supported. Some older guides for Java 8 have different syntax; identify the JDK before applying modern flags.

**Output stream note:** `java -version` traditionally writes the banner to **standard error**, whereas `java --version` is designed to print the version to standard output in common launchers. Do not build a pipeline depending on stdout of a variant without checking shell redirection.

## 6. Architecture: host, process, JVM bitness, CPU, and native ABI

**`os.arch` is the architecture name reported by the Java runtime**, with common examples like `amd64`, `x86_64`, `aarch64`, or `arm64` depending on the implementation/platform. It is **a signal about the runtime environment**, not a complete description of the host CPU, actual CPU instruction set, or layout of every native library.

```text
                     Physical machine
                      architecture
                            │
                   OS kernel / hypervisor
                            │
             container / VM / process namespace
                            │
                   executable architecture
                            │
                 JVM process data model
                            │
                 os.arch / java.vm.name
                            │
               JNI native libraries (ABI)
```

Values may coincide in ordinary systems, but must not be assumed by default in all cases of cross-arch emulation, Rosetta, WoW64, multi-arch containers, or remote development.

### 6.1. `os.arch` is not `uname -m` in every environment

- `System.getProperty("os.arch")` is the value the JVM provides for the **process runtime**.
- `uname -m` is usually a shell tool querying kernel/machine architecture; in virtualized/emulated environments it can differ from what the JVM reports.
- The OS/container image may be a specific architecture while the developer host is another architecture.
- The CPU may support extensions such as AVX, but `os.arch` usually does not indicate all extension flags.
- The strings `amd64` and `x86_64` often denote the same architecture family in many ecosystems, but simple string comparison cannot be used as certification of native library compatibility.

**If deploying JNI/JNA**, you must choose the native binary matching **OS + instruction set + process bitness + ABI + C runtime/linker requirements**, not just matching the `os.arch` name.

### 6.2. 32-bit vs 64-bit: three different measurements

1. **Java primitive `long` is always 64-bit**, regardless of whether the JVM is 32-bit or 64-bit. `int` is always 32-bit according to the Java language specification.
2. **Native pointer size** belongs to the process ABI; on a typical 64-bit JVM there are 64-bit pointers, but **Compressed Oops** may use compressed references internally.
3. **`sun.arch.data.model`** usually returns `32` or `64` in **HotSpot-related implementations**, but it is an **implementation-specific property** and must not be treated as a Java SE standard portable API.

```java
System.out.println(Integer.SIZE);  // 32
System.out.println(Long.SIZE);     // 64
```

This is a **snippet**; it proves the width of Java primitive types, **it does not prove** the bitness of the JVM process.

### 6.3. More reliable sources to check native architecture when needed

**Linux:**

```bash
uname -m
file /path/to/java
readelf -h /path/to/java
```

`readelf` requires the binutils package and an ELF executable; `file` can follow symlinks if the appropriate option is added. On macOS:

```bash
uname -m
file /path/to/java
lipo -info /path/to/java
```

`lipo` is only suitable for Mach-O/universal binaries. On Windows, use PowerShell/system tools to check **OS architecture, process architecture, and PE executable architecture**; specific APIs/tools depend on the Windows version and environment.

Do not infer process bitness solely from RAM size, heap `-Xmx`, or Java primitive sizes.

### 6.4. Which JVM decisions does CPU architecture affect?

- Selection of native JNI libraries `.so`/`.dll`/`.dylib`.
- CPU-specific JIT intrinsics/vector instructions and hardware support capabilities.
- Default thread stack size and memory layout by platform.
- HotSpot ports and the set of supported JVM flags.
- Container multi-arch image selection, cross-build.
- Performance baseline: the same Java code may have different speeds on x64/ARM64.
- CDS/custom VM archive compatibility and native-image artifacts.

Architecture does not solely determine GC latency; CPU quota, memory speed, JDK implementation, workload, and compiler policy also have major impacts.

## 7. Java System properties: read accurately but do not absolutize

Java SE 17 has a set of standard/runtime-defined properties via `System.getProperty(...)`. They are very convenient for **information about the running process**, yet have limitations:

- System properties are values **that can be read and in some cases rewritten** via `System.setProperty` or `-Dkey=value`; do not treat a string as tamper-proof certification.
- Not every property mentioned by online tutorials is a Java SE standard.
- Vendor-specific properties may be missing or renamed.
- `java.home` indicates the runtime home, but launching via a wrapper can obscure the executable source outside the JVM.
- `os.arch` describes the JVM environment, not certifying all CPU features/native ABI.
- Collecting the property list must avoid putting secrets/sensitive configuration into logs.

### 7.1. Core identification group

| Property | Used to know | Caution |
| --- | --- | --- |
| `java.version` | Java runtime version | Distinguish feature and full build |
| `java.runtime.version` | Runtime build string if present | May differ from `java.vm.version` |
| `java.vendor` | Java runtime vendor | Do not infer VM implementation |
| `java.vendor.version` | Vendor-specific optional version | May be null |
| `java.home` | Runtime installation location | Not necessarily equal to shell JAVA_HOME |
| `java.vm.name` | VM implementation name | Not a portable enum |
| `java.vm.vendor` | VM vendor | May differ from java.vendor |
| `java.vm.version` | VM implementation version | Compare with same PID |
| `java.vm.info` | Some HotSpot VMs report build/mode info | Not a portable Java SE property |
| `java.specification.version` | Spec feature version | Does not contain patch/security build |
| `java.vm.specification.version` | VM specification version | Differs from implementation version |
| `java.class.version` | Max class-file version the runtime accepts | Java 17 is usually `61.0` |
| `os.name` | OS name | Does not by itself describe distro/kernel |
| `os.arch` | JVM-reported architecture | Does not replace native ABI test |
| `os.version` | OS version property | In containers, host kernel and userspace differ |
| `sun.arch.data.model` | HotSpot-family-specific 32/64 model | Optional/nonportable; may be missing |
| `java.class.path` | Java classpath system property | May not fully describe module layer/custom loader |
| `java.library.path` | Native library search path | Does not guarantee library ABI compatibility |
| `jdk.module.main` | Main module name on some modular launches | May be null; not always present |
| `user.dir` | Current working directory | Does not prove JDK installation |

### 7.2. Do not print all `System.getProperties()` in production logs

`System.getProperties()` may include classpath, user directories, and application-attached system properties containing passwords/tokens/internal endpoints. A diagnostic tool that prints every property to logs will increase the risk of leaking secrets.

Prioritize an **allowlist of identification fields**. When using `-XshowSettings:properties` or `jcmd PID VM.system_properties` in production environments, restrict access permissions and where outputs are stored.

## 8. `java -version`, `-XshowSettings`, and `-XX:+PrintFlagsFinal`

### 8.1. Launcher commands

```bash
java -version
java --version
```

Usually provide the Java release, runtime distribution, and VM banner. **Illustrative** format example, not the exact output in every build:

```text
openjdk version "17.0.x" ...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ... (mixed mode, sharing)
```

“mixed mode” usually relates to interpreter and JIT compiled execution; “sharing” may indicate CDS support/use according to the HotSpot banner. **Do not take the banner as the sole proof** of the flags/GC mode being used, especially on other VM implementations.

### 8.2. Print system properties of the launching JVM

```bash
java -XshowSettings:properties -version
```

You can find:

```text
java.home = ...
java.runtime.version = ...
java.vendor = ...
java.version = ...
java.vm.name = ...
java.vm.vendor = ...
java.vm.version = ...
os.arch = ...
os.name = ...
sun.arch.data.model = ...  (if the build has it)
```

This is an **illustrative display format**, actual values depend on the environment; lines may appear on standard error and follow the launcher's format. Use `-XshowSettings:vm` to view some VM settings; do not infer it is equivalent to dumping all flags.

### 8.3. Effective flags configuration

```bash
java -XX:+PrintFlagsFinal -version
```

On HotSpot, the command can print many flags, including ergonomic defaults chosen automatically by the VM. A flag can be:

- Set via command line.
- Set via environment/wrapper.
- Chosen by ergonomics based on CPU/heap/container settings.
- Have different defaults across JDK versions.
- Not exist on another VM implementation.

Therefore, just looking at a Dockerfile with `-Xmx2g` is not enough to know **all effective JVM flags** of the process. You need to inspect the actual running process and runtime tooling.

**Output caution:** `PrintFlagsFinal` is very long, most of it irrelevant to the problem; filter the exact flags and version instead of dumping it into an issue tracker containing secrets.

### 8.4. Reading container information on Linux

With supported HotSpot Java 17, the launcher has:

```bash
java -XshowSettings:system -version
```

On **Linux**, the `system` category provides host or container configuration information depending on the implementation; on other OSes it may not be supported or may display differently.

Use it to check container-related CPU/memory limits **when it works**. Do not use it to replace all cgroup tools when forensic diagnosis is needed; the VM only reports what it sees and supports according to the JDK update/build.

## 9. Identifying the exact process with `jcmd` on HotSpot

If you need to investigate a running service, **do not open a terminal and just run `java -version`**: that command may run a different binary than the service's JVM process. Query that exact **PID** using the appropriate tool.

On HotSpot JDK 17:

```bash
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
jcmd <pid> VM.flags
jcmd <pid> VM.info
```

`<pid>` is a placeholder that must be replaced with a valid PID. Do not copy the `<`/`>` characters literally into the shell; that is not PID syntax.

- **`VM.version`:** version information of the target JVM.
- **`VM.command_line`:** how the target JVM was launched, helping cross-check options.
- **`VM.system_properties`:** system properties **inside the target JVM** (may contain sensitive data).
- **`VM.flags`:** JVM flags currently in effect according to the VM's capabilities.
- **`VM.info`:** extended VM/environment/status information.
- **`jcmd -l`:** lists JVM processes that the tool can see/attach to appropriately.

Diagnostic commands depend on the runtime implementation/build and execution permissions. You need the same appropriate host/namespace, OS permissions, and attach capability; the process may disallow attach or may have terminated.

### 9.1. PID and container namespaces

When an app runs in a container:

```text
Host PID:            12345 (example)
Container PID:           1 (example)
JVM process namespace:   depends on container runtime
```

`jcmd` running on the host and `jcmd` running inside the container **may see different PIDs**. Do not send `jcmd 1` on the host and think you are definitely talking to PID 1 of the container. Use `docker exec`/`kubectl exec` with the exact target container if permissions/system allow, or map the PID accurately via container/OS tools.

### 9.2. The `jcmd` command is not necessarily in the runtime image

A custom image from `jlink` or a minimal container may only contain `bin/java`, without `jcmd`. You need a tool image of the same runtime family/version and appropriate attach permissions, or log an allowlisted runtime identity at startup. **Do not reinstall the JDK into a production container just to run `jcmd` once if doing so changes the runtime and breaks reproducibility**.

### 9.3. Running tool differs from attached tool

`jcmd` from JDK A may not be completely compatible/authorized with JVM B. The most reliable results come from using tools from the same distribution/build or the toolset supported by the vendor to observe the target process.

### 9.4. VM flags are not the Java language specification

`-XX:+UseG1GC` is a HotSpot option, not a Java source-level feature. `-Xmx` is a common launcher option, but its interpretation and collector choices have implementation-specific dimensions. If `java.vm.name` reports another implementation, consult the exact VM's documentation before using `-XX` flags.

## 10. Java 17 runnable demo: print the “runtime fingerprint” of the process itself

Save the following **`RuntimeFingerprint.java`** file. This is a standalone program that can be compiled with JDK 17. It prints fixed Java 17 fields along with fields **that must be collected from the real machine**, instead of fabricating vendor/CPU/path.

```java
import java.lang.Runtime;
import java.lang.System;
import java.util.LinkedHashMap;
import java.util.Map;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        System.out.println("javaFeature=" + version.feature());
        System.out.println("java17=" + (version.feature() == 17));
        System.out.println("classFormat=" +
                System.getProperty("java.class.version"));

        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("java.version", System.getProperty("java.version"));
        fields.put("java.runtime.version",
                System.getProperty("java.runtime.version"));
        fields.put("java.vendor", System.getProperty("java.vendor"));
        fields.put("java.home", System.getProperty("java.home"));
        fields.put("java.vm.name", System.getProperty("java.vm.name"));
        fields.put("java.vm.vendor", System.getProperty("java.vm.vendor"));
        fields.put("java.vm.version", System.getProperty("java.vm.version"));
        fields.put("os.name", System.getProperty("os.name"));
        fields.put("os.arch", System.getProperty("os.arch"));
        fields.put("os.version", System.getProperty("os.version"));
        fields.put("sun.arch.data.model",
                System.getProperty("sun.arch.data.model", "<absent>"));

        for (Map.Entry<String, String> item : fields.entrySet()) {
            System.out.println(item.getKey() + "=" + item.getValue());
        }

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("logicalProcessors=" +
                Runtime.getRuntime().availableProcessors());
    }
}
```

Compile/run:

```bash
javac --release 17 RuntimeFingerprint.java
java RuntimeFingerprint
```

**Deterministic first part of stdout when running on standard Java 17:**

```text
javaFeature=17
java17=true
classFormat=61.0
```

**The following lines vary by environment**; the example below is an **explanatory form**, not actual measured output:

```text
java.version=<runtime-release>
java.runtime.version=<runtime-build>
java.vendor=<runtime-vendor>
java.home=<runtime-home>
java.vm.name=<vm-implementation-name>
java.vm.vendor=<vm-vendor>
java.vm.version=<vm-build>
os.name=<os-name>
os.arch=<jvm-reported-architecture>
os.version=<os-version>
sun.arch.data.model=<value-or-absent>
pid=<process-id>
logicalProcessors=<count-visible-to-runtime>
```

Strings in angle brackets are placeholders explaining the **variable** lines; they should not be pasted back as evidence. When running it yourself, **read the actual values**.

**Important explanations:**

1. `Runtime.version()` describes the current Java runtime, not `javac` from another build process.
2. `java.vm.name`/`java.vm.vendor` indicate VM implementation metadata, not just the Java specification.
3. `java.home` is the runtime path of the current JVM. It can be a custom `jlink` image and differ from shell `JAVA_HOME`.
4. `os.arch` is the value the runtime reports for architecture, which must be cross-checked against the native binary when selecting JNI/ABI.
5. `sun.arch.data.model` is a **nonportable property**. The default `<absent>` indicates the property is not present; code must not assume every JVM has it.
6. `pid` is the PID according to the process namespace provided by Java/OS, not a stable number across runs.
7. `availableProcessors()` reports the number of logical processors the JVM sees according to the implementation and environment limits; not necessarily equal to the number of physical cores on the host.
8. `classFormat=61.0` is the class-file format version that the Java 17 JVM reports supporting; not the compile version information of all loaded libraries.

### 10.1. Why not print all of `System.getenv()`?

The environment can contain tokens, passwords, internal URLs, or information that should not be put into console/logs. In the demo, only use system properties related to runtime identity. If `JAVA_HOME` is needed, log a **shareable path** after verifying it is not secret/sensitive.

### 10.2. Inspecting patch/build versions in a structured way

Add the following snippet into `main` if you want to see detailed information:

```java
Runtime.Version version = Runtime.version();
System.out.println("feature=" + version.feature());
System.out.println("interim=" + version.interim());
System.out.println("update=" + version.update());
System.out.println("patch=" + version.patch());
System.out.println("build=" + version.build().orElse(-1));
```

This part is a **snippet**, not a standalone file; `-1` is an arbitrary value chosen to represent absent build metadata, **not an actual build number**. Use the API instead of regex to parse the `java.version` string.

## 11. Second Java 17 runnable demo: feature gate with deterministic result

A program should not require a specific vendor if it only needs a Java language/runtime feature. Create the file **`FeatureGate.java`**:

```java
public final class FeatureGate {
    public static void main(String[] args) {
        int required = 17;
        int current = Runtime.version().feature();
        boolean supported = current >= required;

        System.out.println("requiredFeature=" + required);
        System.out.println("runtimeFeature=" + current);
        System.out.println("supported=" + supported);
    }
}
```

Compile/run on JDK 17:

```bash
javac --release 17 FeatureGate.java
java FeatureGate
```

**Exact stdout when the runtime is Java 17:**

```text
requiredFeature=17
runtimeFeature=17
supported=true
```

On Java 21, `supported=true` but `runtimeFeature=21`. This is not a bug: the check requires **Java at least 17**, not “only Java 17 is valid”. If the app is truly only certified on Java 17, change the policy to `current == 17` and document/test it as a separate **compatibility matrix** — do not confuse release policy with API support.

### 11.1. Feature gate does not check JNI architecture

`supported=true` **does not prove** native libraries are compatible. A Java 17 on ARM64 and a Java 17 on x64 both have feature=17, yet JNI `.so` files cannot be considered interchangeable. Native binaries must be checked for OS/arch/ABI independently.

## 12. Third Java 17 runnable demo: reminding the distinction between primitives and VM bitness

Create the file **`PrimitiveVsArchitecture.java`**:

```java
public final class PrimitiveVsArchitecture {
    public static void main(String[] args) {
        System.out.println("intBits=" + Integer.SIZE);
        System.out.println("longBits=" + Long.SIZE);
        System.out.println("charBits=" + Character.SIZE);
        System.out.println("doubleBits=" + Double.SIZE);

        String arch = System.getProperty("os.arch", "unknown");
        System.out.println("architectureReported=" + arch);
    }
}
```

Compile:

```bash
javac --release 17 PrimitiveVsArchitecture.java
java PrimitiveVsArchitecture
```

**The first four stdout lines are invariant according to Java primitive types:**

```text
intBits=32
longBits=64
charBits=16
doubleBits=64
```

The `architectureReported=...` line is the **actual value of the JVM** and varies by platform. It is not sufficient proof of bitness or native library ABI.

**Explanation:** Java `long` is always 64-bit, even if a JVM implementation is in a 32-bit process data model; Java `char` is a 16-bit UTF-16 code unit, which does not mean every Unicode character occupies exactly 16 bits; `double` is IEEE 754 64-bit. Do not infer runtime pointer width from `SIZE` constants.

## 13. Verifying the current JDK from Java code and OS commands

A reliable cross-checking procedure:

```text
A. From outside the process:
   command -v java / Get-Command java
   java -version
   javac -version
   JAVA_HOME

B. From INSIDE the process:
   Runtime.version()
   java.vendor / java.vm.* / java.home
   os.arch / os.name
   availableProcessors()

C. From diagnostics attached to the exact PID:
   jcmd PID VM.version
   jcmd PID VM.command_line
   jcmd PID VM.flags
   jcmd PID VM.system_properties

D. From OS/container:
   executable path / actual ELF/PE/Mach-O architecture
   cgroup CPU & memory limits
   container image digest / architecture
   process namespace mapping

Conclude once the relevant sources have been cross-checked.
```

### 13.1. When results A and B do not match

If the terminal prints `java -version` Java 21 but `RuntimeFingerprint` inside the service gives Java 17:

- You cannot assume the service uses Java 21; the terminal may be prioritizing another executable.
- Inspect `java.home` from the service, process command-line path, and the binary inside the container.
- Check the Windows service/systemd unit, startup shell, and environment when the service started.
- Look for a launcher wrapper/shim or service manager option.
- If the process is in a container, run the check **inside the container itself** instead of the host shell.

**Do not blindly restart production to “fix” the version result** before understanding dependency/compatibility and deployment ownership.

### 13.2. When `java -version` and `javac -version` differ

For example, the compiler reports 21, the launcher reports 17:

1. Record the absolute paths of both.
2. Check IDE/Maven/Gradle Java Toolchains.
3. Use `javac --release 17` when building for a 17 runtime.
4. Test the artifact with the exact Java 17 runtime.
5. If different compiler APIs/toolchains are needed, pin the build JDK in CI.
6. Clean up PATH/JAVA_HOME/configuration from a single clear source, avoiding blind edits.

Do not just rename `JAVA_HOME` and think every running Gradle daemon/service will automatically switch JDKs.

## 14. An installed JDK on the machine does not mean the JDK running in the IDE/build tool

IDEs and build systems have multiple layers:

- **IDE runtime JDK:** Java used to run the IDE.
- **Project SDK:** Java APIs/project language level assigned by the editor.
- **Gradle/Maven daemon JVM:** Java used to run the build process/plugin code.
- **Java compiler toolchain:** JDK performing the compilation.
- **Test JVM:** Process running unit/integration tests.
- **Production runtime JVM:** Final JVM running the service.

For example, compiling a Java 17 class with JDK 21 via `--release 17` and then testing only on JDK 21 **does not prove** the application runs well on JDK 17: the runtime also has different configuration/module/illegal access/native dependencies. Test on the target Java 17.

### 14.1. Class file format and `UnsupportedClassVersionError`

If a class is compiled at a major version higher than the runtime supports, the JVM can throw:

```text
java.lang.UnsupportedClassVersionError: ...
```

The full message depends on the class/JVM. Basically:

| Java feature | Common class major version |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

This is a class format mapping; not a VM vendor version table. Use:

```bash
javap -verbose MyClass
```

and then check `major version`. `javap` must point to the exact deployed class file/artifact, not an old class file of the project in the IDE. If there is a multi-release JAR, the actual class selected also depends on the runtime version and JAR layout.

### 14.2. Use `--release` instead of only `-source/-target`

`javac --release 17` controls syntax, class target, and the public platform API set corresponding to Java 17. In many cases it is safer than `-source 17 -target 17` when a newer compiler has newer APIs and you do not want to accidentally compile a call to a method that only exists on the build machine's JDK.

**Exception:** `--release` does not by itself guarantee compatibility of **JNI libraries**, dynamic linkage dependencies, native crypto providers, or vendor-specific APIs. They must be tested in the target runtime.

## 15. Containers and resources: “a 64-core machine” does not mean the JVM uses 64

This lesson is in the **Resource Configuration** group, so runtime identity must be linked to **effective resources**. HotSpot Java 17 usually detects Linux containers via cgroups and applies container awareness according to the capabilities of the JDK/platform build.

Even so:

- The host may have 64 CPUs, but the container is given a quota equivalent to 2 CPUs.
- `Runtime.getRuntime().availableProcessors()` usually reflects the number of logical processors the JVM sees, **not** the number of physical cores of the host.
- `-XX:ActiveProcessorCount` can override the number of processors HotSpot uses for ergonomics and reports via Java APIs depending on the implementation.
- `-Xmx` can be set directly, inferred from percentages/ergonomics, or from wrapper configuration; it does not depend solely on host RAM.
- Container memory limit differs from “host total memory” and differs from “heap maximum”.
- JNI/native memory, thread stacks, direct buffers, and code cache still need RAM outside the Java heap.
- Architecture affects native dependencies, not the only way to adjust `-Xmx`.

### 15.1. Viewing effective CPUs right inside the Java process

`RuntimeFingerprint` in section 10 has:

```java
Runtime.getRuntime().availableProcessors()
```

The `logicalProcessors=<n>` line reflects the value reported by the runtime **in that run**. If the JVM has the HotSpot option `-XX:ActiveProcessorCount=2`, it can change the CPU count used for ergonomics. Still, this is not certification that “the container has exactly two physical cores”.

### 15.2. How to view JVM heap?

Snippet used in Java 17:

```java
Runtime rt = Runtime.getRuntime();
long maxHeap = rt.maxMemory();
long committedHeap = rt.totalMemory();
long freeInCommitted = rt.freeMemory();
```

This is a **snippet**, not a standalone file. `maxMemory()` is the maximum amount the JVM will try to reserve for the heap, not the container's memory limit; `totalMemory()`/`freeMemory()` reflect heap memory according to the API rather than total RSS/process memory.

Do not calculate “remaining free RAM in container = maxMemory - totalMemory” or “RSS equals -Xmx”; you must account for native allocations, metaspace, JIT code cache, and thread stacks.

### 15.3. `-XshowSettings:system` does not replace cgroup forensics

On HotSpot/Linux Java 17, `-XshowSettings:system` is useful to know which host/container constraints the JVM is receiving. But when CPU throttling/swap/oom-killer is the issue, you need OS/cgroup data, container runtime metrics, and Kubernetes events. A JVM can report an appropriate logical processor count and still be heavily CPU throttled due to competing load.

## 16. Inspecting the real Java process in Docker/Kubernetes

Suggested procedure:

1. Identify the exact deployment/pod/container, image **digest**, and target architecture.
2. Check the entrypoint and actual command line, not just the Dockerfile template.
3. Enter the exact container if permitted: `java -version`, `command -v java`, `$JAVA_HOME`.
4. Log allowlisted runtime identity from the application itself (e.g., `RuntimeFingerprint` or startup telemetry).
5. If tooling and permissions are available, `jcmd <pid> VM.version`/`VM.command_line`.
6. Cross-check `os.arch` and native binary architecture, especially with multi-arch manifests.
7. Check effective CPU/memory limits instead of host totals.
8. Ensure the builder stage JDK/runtime and production stage are not confused.
9. Re-verify after deploy/rollout; do not use logs from an old pod.
10. If using Java agents/CDS/AppCDS/JNI, determine compatibility based on the **runtime process**, not inferred from the build machine.

### 16.1. Multi-stage container build

```text
Stage 1:
  JDK 21 builder
  javac --release 17
  build app.jar

Stage 2:
  Minimal Java 17 runtime image
  java -jar app.jar
```

This is a **conceptually valid** workflow if the app does not accidentally use APIs/native libraries that do not exist on the target and is tested. The two stages may differ in CPU architecture if a multi-platform builder/emulation is used; check the JAR artifact (portable bytecode) separately from **native libraries** (architecture-specific).

### 16.2. Docker `--platform` and host architecture

An image can be built for `linux/arm64` or `linux/amd64`. When running on a host of a different architecture via emulation, performance/ABI behavior and JVM port compatibility may change. `os.arch` from the Java process is a useful signal, but must be paired with the image platform and executable format.

Do not take `docker info` host architecture as the answer in place of the application runtime if emulation/multiarch is present.

## 17. VM options, flags, and versions when diagnosing errors

### 17.1. `Unrecognized VM option`

If a runtime does not recognize `-XX:...`, it could be:

- The flag only exists on HotSpot, but you are running OpenJ9.
- The flag was renamed/removed between versions.
- A diagnostic flag must be unlocked or only exists in a debug build.
- Typo/wrong format/wrong unit.
- The vendor build disabled or modified the option.
- The launch tool is invoking the wrong binary.

Do not just conclude “this JDK 17 is broken”. Record `java.vm.name`, `java.vm.version`, and the absolute launcher path first, then consult the VM documentation for the exact build.

### 17.2. `-XX:+UnlockDiagnosticVMOptions` is not a universal license

Some flags only work when diagnostic options are unlocked, some only exist in non-product builds; and some flags are not supported in a given JVM. Do not copy startup options from a C2/GC tutorial to every VM with the same Java feature.

### 17.3. `-XX:+PrintFlagsFinal` has “effective values” but you must understand the source

For example, `MaxHeapSize` can come from explicit `-Xmx`, ergonomics, or container sizing; `ActiveProcessorCount` can override detected CPUs. When reading flag output, inspect the implementation/build/command line, especially in services managed by scripts/wrappers.

A flag reporting a specific value does not prove the real OS is continuously granting enough CPU/RAM; container cgroups and the scheduler are another layer.

## 18. JNI/native libraries: check OS, arch, and ABI thoroughly

`System.loadLibrary("foo")` usually searches for the native library according to conventions and `java.library.path`. Each platform has a different suffix/loading mechanism:

- Linux: `libfoo.so`.
- macOS: `libfoo.dylib`.
- Windows: `foo.dll`.

The filename **does not prove the content was built for the right architecture**. A `libfoo.so` might be built for x86_64, while the JVM runs on aarch64. Differences also include:

- 32-bit vs 64-bit process ABI.
- Calling conventions, C/C++ standard library, libc variant.
- Exported symbols/JNI mangling, native transitive dependencies.
- CPU instruction extensions and runtime linker path.
- Dynamic loader search policy and permissions.

If you encounter `UnsatisfiedLinkError`, you must distinguish **file not found** from **found but failed to load due to ABI/dependency/symbol**. One method:

1. Verify `os.name`/`os.arch` inside the Java process itself.
2. Verify 32/64-bit VM via startup banner/native binary inspection.
3. Check `java.library.path` if relevant.
4. Check the architecture of `.so/.dll/.dylib` and dependent libraries.
5. Read the native loader error message and OS tool output.
6. Test with the exact container/runtime image, not just the developer laptop.

**Do not set `-Dsun.arch.data.model=64` to “turn a 32-bit JVM into 64-bit”**. That only modifies a string property if the JVM allows it, without changing binary architecture/ABI.

## 19. Reproducible environment manifest: what to save for debugging?

To compare “works locally, fails in production”, you should record in a controlled manner:

```text
Application artifact ID/digest:
  app-version, checksum, dependencies digest

Build toolchain:
  compiler path, javac -version, --release target
  CI image digest, build OS/architecture

Production runtime:
  java.version, Runtime.version(), java.vendor
  java.vm.name, java.vm.vendor, java.vm.version
  java.home, os.name, os.arch, os.version

Execution identity:
  process PID/namespace, executable path
  VM.command_line (redacted), selected VM flags
  container image digest/platform

Resource constraints:
  availableProcessors, container CPU quota/cpuset
  -Xmx/-Xms, observed heap max, cgroup memory
  GC type, native-memory considerations

Native dependencies:
  artifact OS/architecture/ABI, library digests

Observations:
  exceptions, logs, timestamps, diagnostics build
```

**Redaction is mandatory in production runbooks**: do not copy full `VM.system_properties`, launcher arguments, or environments containing passwords/tokens into public systems. If storage is truly needed, apply appropriate access controls and retention.

### 19.1. “Environment fingerprint” should be built with typed fields

Use structured metadata with clear field names, for example:

```text
javaFeature=17
javaRuntimeVersion=<from actual VM>
javaVendor=<from actual VM>
vmName=<from actual VM>
vmVendor=<from actual VM>
vmVersion=<from actual VM>
osArchitecture=<reported value>
runtimeExecutable=<verified executable path>
imageDigest=<release digest>
```

The placeholders are only to illustrate the schema, not actual values. If using it as a cache key for JIT-specific artifacts, follow the **artifact provider's** compatibility contract; do not treat all fields in the table above as sufficient or necessary conditions for every type of cache.

## 20. Real-world scenarios and how to investigate

### 20.1. Case A — Local Java 21, production Java 17

Symptom: runs locally, production has `UnsupportedClassVersionError`.

**Hypothesis:** built class major 65 of Java 21, production runtime only supports major 61.

**Check:** compare `javac -version`/compiler toolchain, `javap -verbose` on the **deployed artifact**, `java -version` of the exact production container, and `Runtime.version()` if the process can start.

**Resolution:** compile targeting `--release 17`, test the artifact on JDK 17, check dependent JARs and plugin-generated classes.

### 20.2. Case B — Set `JAVA_HOME` to JDK 17, yet server still uses JDK 11

Symptom: new shell reports the right JAVA_HOME, but the service still uses the old one.

**Hypothesis:** the service daemon was already running, has an executable absolute path or systemd/Windows service config different from the current shell.

**Check:** service PID, actual executable path, `java.home`/`java.vm.version` from the **process**, startup script, and service manager.

**Resolution:** fix the launcher configuration with the absolute runtime path and perform a controlled redeploy/restart. Do not use shell values to alter data or restart production outside change procedures.

### 20.3. Case C — ARM64 pod fails with JNI error

Symptom: `UnsatisfiedLinkError` when running on ARM64.

**Hypothesis:** the selected image is arm64, but the native dependency is x86_64.

**Check:** pod image architecture, runtime `os.arch`, native library binary headers, and loader error.

**Resolution:** provide the native library with the right ABI/arch or choose the right platform image; recompiling Java source alone cannot fix a native file of a different architecture.

### 20.4. Case D — Host has 32 CPUs, yet JVM only reports 2

Symptom: GC/worker pools operate according to a lower CPU count than expected.

**Hypothesis:** cgroup quota/cpuset or `-XX:ActiveProcessorCount=2`.

**Check:** Java `availableProcessors()` inside the process, `-XshowSettings:system` on HotSpot/Linux, `jcmd PID VM.flags`, and cgroup config.

**Resolution:** adjust CPU quota/active processor policy based on workload and resource budgets; do not assume the host machine gives all CPUs to every container.

### 20.5. Case E — GraalVM/HotSpot vs Native Image

**GraalVM JDK** can have a `java` launcher that runs Java bytecode on a HotSpot-based JVM in some builds, whereas a **native-image executable** is an AOT-built native program and is not equivalent to a JVM `java -jar` process. Do not lump the two artifacts together just because both come from the same vendor/toolchain.

With a native-image executable, `System` properties/VM diagnostics/GC/runtime capabilities may vary by tool/build. You must read the documentation **of the specific artifact and version**.

### 20.6. Case F — Running a newer JDK with old flags

Symptom: VM prints “Unrecognized VM option” or a warning about a deprecated option.

**Check:** vendor, VM implementation, version, and `-XX:+PrintFlagsFinal` output/VM-specific docs; do not use a flag table from another JDK out of habit.

**Resolution:** update flags according to the target JDK/VM and benchmark collector/resource behavior. Do not turn a warning into “JVM 17 must definitely use G1” without identifying the implementation.

## 21. Common misinterpretations

1. **“`java -version` on the host is the runtime of every container.”** False; containers have their own images.
2. **“`JAVA_HOME` definitely determines the `java` file that PATH invokes.”** False; launcher resolution/wrappers differ.
3. **“`javac -version` equals the Java version of the service.”** False; compiler/process are separate.
4. **“Project language level in the IDE determines the production VM.”** False.
5. **“`--release 17` proves a JNI native lib runs on every architecture.”** False.
6. **“As long as it's Java 17, every vendor/VM has the same HotSpot flags.”** False.
7. **“`java.vm.name` tells the full vendor/patch/build.”** False; additional properties are needed.
8. **“`java.vm.specification.vendor` is always the JDK distributor.”** False.
9. **“`java.specification.version` is the complete security patch.”** False.
10. **“`java.class.version` is the compile version of each class in the app.”** False.
11. **“`Runtime.version().feature()==17` proves the VM belongs to the right patch release.”** False.
12. **“`Integer.SIZE` or `Long.SIZE` measures JVM pointer width.”** False.
13. **“`os.arch` is the list of CPU extensions/ISA features.”** False.
14. **“`uname -m` always equals `os.arch` in every container/emulation.”** False.
15. **“As long as `amd64` is in the property, every native `.so` on Linux will run.”** False.
16. **“JDK 17 definitely has `javac` in the production runtime image.”** False if jlink/minimal image.
17. **“Not seeing `jcmd` means the service is not running a JVM.”** False; the runtime image may lack tools.
18. **“`-XX:+PrintFlagsFinal` is a Java SE portable API.”** False; depends on the VM implementation.
19. **“`-XshowSettings:system` always has the same output on Windows/macOS/Linux.”** False.
20. **“`os.name`/`os.version` fully explain the container base distro.”** False; the JVM sees kernel/userspace in the appropriate context.
21. **“`availableProcessors()` equals the number of physical cores guaranteed to be exclusively allocated.”** False.
22. **“Heap max is the entire container RAM limit.”** False; off-heap/native memory also uses RAM.
23. **“Changing `System.setProperty("os.arch", ...)` changes the native binary architecture.”** False.
24. **“Because the machine has JDK 21, class-file major 65 can always run on a Java 17 container.”** False.
25. **“Running successfully on the builder image proves success on the runtime image.”** False.
26. **“`java.home` = `JAVA_HOME` environment of every process.”** False.
27. **“`java.vendor` always indicates an official enum of JVM vendors.”** False, it is a string.
28. **“`java.vm.version` must be identical to `java.version`.”** False.
29. **“Java runtime version >= 17 guarantees no more classpath/module reflection errors.”** False.
30. **“JDK feature/version fingerprint is enough to prove CDS archive binary compatibility.”** False; build/classpath/VM flags also matter.
31. **“`java -version` needs to start every application main class.”** False; only the launcher.
32. **“`jcmd PID VM.version` on any PID on the host always succeeds.”** False; attach permissions/namespaces.
33. **“`-XX:ActiveProcessorCount` must equal the number of physical cores.”** False.
34. **“It is safe to dump all VM.system_properties to public logs.”** False; may contain sensitive data.
35. **“CPU architecture is the only reason two JDKs differ in performance.”** False; VM build/GC/flags/workload/containers.
36. **“‘HotSpot 64-Bit Server VM’ banner means heap is always 64 GiB or larger.”** False; heap is separate and depends on flags/limits.
37. **“Same `java.vendor` value means two JDK binaries have the same checksum.”** False.
38. **“`ProcessHandle.current().pid()` always equals the host PID when running in a container.”** Not guaranteed, PID namespace.
39. **“A JDK supporting Linux x64 supports Linux ARM64 by default.”** False; must choose the correct port/build.
40. **“Java primitive widths change according to CPU architecture.”** False; Java language semantics determine widths.

## 22. Practical exercises

### Exercise 1 — Explore the real environment

Run `RuntimeFingerprint`. Record:

- Java feature/update/build according to `Runtime.Version`.
- Java vendor, VM name/vendor/version.
- `java.home` and absolute launcher path.
- `os.arch`, `os.name`, and (if present) `sun.arch.data.model`.
- `availableProcessors` and container CPU quota (if relevant).

**Question:** Are there any counterintuitive pairs of values (for example, Java 17 from the runtime image but the IDE's `javac` is 21)? Explain using toolchain/runtime separation.

### Exercise 2 — Compare builder and runtime images

Compile `FeatureGate` with JDK 21 using `--release 17`, run on JDK 17. Then try building without `--release` and verify the class-file major with `javap -verbose` before putting it onto the runtime.

**Requirement:** Do not arbitrarily invoke `java` on the host; use absolute paths or pinned container images.

### Exercise 3 — Check resource awareness

In a HotSpot Java 17 Linux test container, measure `availableProcessors()` with different cgroup CPU quotas, and once configure `-XX:ActiveProcessorCount` if the runtime supports it.

**Requirement:** Do not infer the number of physical cores from this API; record kernel/cgroup/runtime versions.

### Exercise 4 — Choose the right JNI artifact

Suppose `libcodec.so` is built for Linux x86_64 and the production image runs Linux aarch64. Present the steps to verify `os.arch`, binary headers, dependencies, and how to build the library for the right architecture.

**Guided answer:** Java bytecode can be portable, native JNI binaries usually are not; you need to build/use a version matching the OS/ABI.

### Exercise 5 — Create an incident report with minimal data

Write a report including Java runtime feature/build, VM vendor/name/version, executable path, container image digest/arch, selected VM flags, symptoms, and exception. Do not send full `System.getProperties()` or tokens.

**Passing criterion:** Another engineer can identify the **exact runtime process and architecture** to reproduce the issue.

## 23. Self-check questions (with answers)

**Question 1.** Which command shows the JVM version running in the exact process PID on HotSpot?

**Answer:** `jcmd <pid> VM.version` when able to attach; cross-check with `VM.command_line` and Java-side properties.

**Question 2.** If `javac -version` is 21 but the runtime Java feature is 17, is this necessarily an error?

**Answer:** No. It may be intentional cross-compiling with `--release 17`. The issue is whether the artifact has the right Java 17 API/class-file/native compatibility and is tested on the target runtime.

**Question 3.** Do `java.vendor` and `java.vm.name` answer the same question?

**Answer:** No. Vendor tells about the distribution, VM name tells about the implementation.

**Question 4.** Is `java.vm.specification.vendor` necessarily Oracle/Temurin/Corretto distributing the binary?

**Answer:** No. The specification vendor differs from the implementation/distribution vendor.

**Question 5.** Why does `-Dsun.arch.data.model=64` not turn a 32-bit JVM into a 64-bit JVM?

**Answer:** Because it is a property string; it does not change the executable ABI/pointer width.

**Question 6.** Can `Runtime.version().feature()` be used to check an API requiring Java 17?

**Answer:** Yes, if the policy is minimum feature 17, but it does not replace dependency/native compatibility tests.

**Question 7.** What is the Java 17 class major version?

**Answer:** **61**; the `java.class.version` property usually returns `61.0`.

**Question 8.** Can `os.arch=amd64` be taken as proof that every CPU extension the JIT can use is present?

**Answer:** No. The architecture family does not list all ISA extensions/hardware features.

**Question 9.** Does `Runtime.getRuntime().availableProcessors()` represent host physical core count or JVM-visible logical processor count?

**Answer:** JVM-visible logical processor count; it can be affected by container quotas/cpuset and VM flags.

**Question 10.** Does `java.home` equal `JAVA_HOME`?

**Answer:** Not necessarily. `java.home` is the runtime location of the process; `JAVA_HOME` is an environment variable that may point to a different JDK.

**Question 11.** Why might `jcmd` not be found in a custom JRE image?

**Answer:** The runtime image may only contain the modules/executables needed to run the app, without diagnostic tools.

**Question 12.** What to do before trying `-XX:+PrintFlagsFinal` on a VM other than HotSpot?

**Answer:** Identify `java.vm.name`/vendor/version and consult VM-specific docs to know supported options.

**Question 13.** Is measuring total JVM RAM with `maxMemory()` accurate?

**Answer:** No. `maxMemory` relates to the Java heap limit; native stacks, metaspace, code cache, and direct buffers are separate.

**Question 14.** Why can host `uname -m` and Java `os.arch` differ?

**Answer:** Container/emulation/VM process bitness/platform reporting differ; you need to check the executable and native ABI of the process.

**Question 15.** Is it safe to share full `jcmd PID VM.system_properties` on a public issue?

**Answer:** No; it may contain paths/configuration information or secrets, and must be filtered/redacted.

**Question 16.** A Java 17 application runs well on local x86_64, gets `UnsatisfiedLinkError` on ARM64. Is that sufficient evidence that the JVM lacks a Java feature?

**Answer:** No; suspect native library architecture/ABI mismatch and check load paths/dependencies.

**Question 17.** Two services both run Java 17 but have different `java.vm.name`. Can HotSpot-only tuning flags be copied between them?

**Answer:** Not by default. You must use documentation/validation for the exact VM implementation.

**Question 18.** If the container image tag does not change but the digest changes, could the runtime identity have changed?

**Answer:** Yes. Pin the digest and verify the new runtime.

**Question 19.** How do `Runtime.Version.update()` and `feature()` differ?

**Answer:** Feature is the Java release family, update is the update release component in the scheme; do not treat update as major feature.

**Question 20.** What is the minimum useful set of information before reporting a GC/container bug?

**Answer:** JDK feature/update/build, vendor, VM name/version, OS/arch, process PID/launch command, effective VM flags, CPU/memory limits, workload, and redacted logs.

## 24. Runtime identification checklist before modifying resource configuration

- [ ] Confirm the **exact service/pod/container/PID**, do not confuse the shell with the target process.
- [ ] Record **`Runtime.version()`** including feature/update/build when available.
- [ ] Record `java.version`, `java.vendor`, `java.vm.name`, `java.vm.vendor`, `java.vm.version`.
- [ ] Record `java.home` and the actual executable path of the service.
- [ ] Compare `java -version`/`javac -version` by absolute paths.
- [ ] Distinguish build JDK, test JDK, production runtime.
- [ ] Check the Java class major version (Java 17 → 61) of the artifact if needed.
- [ ] Record `os.name`/`os.arch` and verify process/native binary ABI when JNI is present.
- [ ] Read `-XshowSettings:system` on HotSpot/Linux if container awareness is needed.
- [ ] Record `availableProcessors` and effective CPU quota/cpuset.
- [ ] Verify heap flags `-Xms/-Xmx`, GC, stack size, and native memory constraints.
- [ ] For HotSpot: try `jcmd PID VM.version`/`VM.command_line`/`VM.flags` when permitted.
- [ ] Handle discrepancies between host/shell/app process explicitly instead of assuming uniformity.
- [ ] In multi-arch images, pin image digest/platform and corresponding JNI artifacts.
- [ ] Only use JVM flags supported by the **actual VM implementation/build**.
- [ ] Redact secrets before saving diagnostic outputs.
- [ ] Test on the runtime/deployment target after changing the JDK or flags.

## 25. Decision map summary

```text
Do you need to optimize or debug a Java service?
                    │
                    ▼
         IDENTIFY THE EXACT PROCESS
          PID + container + executable
                    │
                    ▼
          IDENTIFY THE JAVA VERSION
        Runtime.version(), java.version
         feature / update / patch / build
                    │
                    ▼
         IDENTIFY VM IMPLEMENTATION
        java.vm.name / vendor / version
                    │
                    ▼
           IDENTIFY ARCHITECTURE
        os.arch + process binary + ABI
                    │
                    ▼
         IDENTIFY RESOURCE ENVELOPE
        CPUs/quota, RAM/cgroup, -Xmx, GC
                    │
                    ▼
          CHECK BUILD VS RUNTIME
          javac / --release / class major
                    │
                    ▼
         COLLECT EFFECTIVE VM FLAGS
           jcmd (if present and attachable)
                    │
                    ▼
        APPLY APPROPRIATE TUNING / FIX
        right JDK + right VM + right target
                    │
                    ▼
         VERIFY on production-like runtime
```

**Remember:** Every time you say “the application is using Java 17”, confirm **which process's Java 17, which patch/build, which vendor, which JVM implementation, on which architecture, and with which resource limits**. `java -version` in the shell, `JAVA_HOME`, `javac -version`, `os.arch`, and `jcmd PID VM.version` **provide different perspectives** and cannot replace one another. It is best to cross-check **runtime properties of the process itself**, **toolchain paths**, **native binary/OS/container facts**, and **effective VM flags** before making GC, heap, JIT, or JNI decisions.

### Official documentation

- [Oracle Java SE 17 — System Properties](https://docs.oracle.com/en/java/javase/17/docs/api/system-properties.html): `java.vendor`, `java.version`, `java.vm.name`, and related properties.
- [Java SE 17 — `java.lang.System` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): definition of `getProperty`/`getProperties`, standard list, and caveats.
- [Java SE 17 — `java.lang.Runtime.Version`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): feature/interim/update/patch/build components.
- [Oracle JDK 17 — Version String Format](https://docs.oracle.com/en/java/javase/17/install/version-string-format.html): explanation of release numbering.
- [Oracle JDK 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-version`, `--version`, `-XshowSettings`, `-XX:+PrintFlagsFinal`, and HotSpot options.
- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release 17` and compilation compatibility.
- [Oracle JDK 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-verbose` to read class-file major.
- [Oracle JDK 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.version`, `VM.command_line`, `VM.flags`, `VM.system_properties`.
- [Java SE 17 — `ProcessHandle` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID and process metadata.
- [JVMS SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): bytecode/class major version differs from runtime VM implementation build.
