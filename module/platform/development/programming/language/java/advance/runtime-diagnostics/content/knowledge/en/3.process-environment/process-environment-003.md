# 3.3 Collecting Actual JVM Version, JDK Vendor, Architecture, and Arguments

## Learning Objectives

When a Java application fails differently across a developer machine, CI, containers, and production, the first question is not merely “what Java version is installed?”. You need to prove **which JVM the request-serving process is actually running on, which vendor distributed it, on what architecture, and with which arguments/flags**. These facts form the basis for explaining differences in garbage collector, JIT, module access, TLS, native libraries, memory limits, and diagnostic tool behavior.

After this lesson, you will be able to:

- Identify the exact **PID and specific running instance**, even when a machine has multiple JDKs/JVMs, containers, and recently restarted processes.
- Collect runtime version, vendor, VM name and version, Java home, and OS/CPU architecture from **the target JVM itself**.
- Distinguish startup JVM arguments, program arguments, system properties, and **VM flags with effective values at measurement time**.
- Use `jcmd`, the Java Management API, and appropriate OS tools, knowing when `java -version` or the `JAVA_HOME` variable can mislead.
- Record evidence with timestamps, sources, and confidence levels while removing sensitive information from incident reports.

## 1. What Exactly Must Be Collected?

A “runtime fingerprint” can include the fields below. You do not necessarily need all of them for every case, but when investigating compatibility bugs or environment discrepancies, missing one of the key groups can lead to wrong conclusions.

| Group | Data to have | Question answered |
| --- | --- | --- |
| Process identity | PID, host/container/pod, process start time, app name/version | Is this the exact **run** experiencing the error? |
| Java runtime | `java.version`, `java.runtime.version`, `Runtime.version()`, `java.home` | Which feature/patch/build of Java is running, and from which runtime image was it loaded? |
| Vendor/VM build | `java.vendor`, `java.vm.vendor`, `java.vm.name`, `java.vm.version` | What is the actual JDK/runtime distribution and JVM implementation? |
| Architecture/platform | `os.name`, `os.version`, `os.arch`, host/container architecture when needed | Is the target JVM built for x86-64, AArch64, or another architecture? |
| Startup command | Java launcher/executable path, main class/JAR/module, JVM options, app arguments | How was the process initialized? |
| Runtime state | `VM.flags`, `VM.flags -all`, effective system properties | Which heap/GC/flags is the JVM currently using, including default/ergonomic choices? |
| Configuration sources | Service unit, container spec, start script, IDE/CI, `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` | Where did the options come from, and were any overridden? |
| Evidence | UTC timestamp, collection method, secret-redacted record, attach errors if any | When was the evidence gathered, and how reliable is it? |

Key point: **Java version, vendor, and startup flags are properties of a specific process**, not reliably inferred from the current terminal, build machine, expected config file, or another container's output.

## 2. Distinguishing JDK, Java Runtime, Java Launcher, and JVM

- **JDK (Java Development Kit):** a distribution containing development components such as `javac` alongside the runtime; depending on the image it may include `jcmd`, `jfr`, `jlink`, etc. An application may run in a **minimal runtime image** without a compiler or diagnostic tools.
- **Java launcher (`java`):** the program that starts the JVM. Running `java -version` describes **the `java` executable selected by the shell at that moment**. It can be completely different from the executable used to create the running service.
- **JVM implementation:** the virtual machine executing bytecode, such as HotSpot or OpenJ9; exposed via `java.vm.*` properties. Two JDK distributions of the same Java version can have different VM characteristics, builds, or options.
- **Java runtime image:** the execution environment the application is using, usually indicated by `java.home`. It may be a full JDK, a custom image built with `jlink`, or a runtime bundled with an application package.

Example: a host has `JAVA_HOME` pointing to JDK 21, while the service is started via an absolute path to runtime 17 inside a container. Running `java -version` outside the container yields Java 21, which **cannot prove** the service uses Java 21. To know the truth, query the JVM with the exact PID, process-start time, and namespace.

Similarly, `javac -version` tells you the compiler of **the environment invoking the command**; it does not tell you which `--release` classes were built with, let alone confirm which JVM is running those classes. Compiled bytecode version and runtime version are two separate properties to verify when encountering `UnsupportedClassVersionError`.

## 3. Identifying the Right Process Before Reading JVM Info

**Step 1 – Narrow the scope:** record service name, environment, host/container/pod, and incident timestamp. If there are multiple replicas, identify the replica serving the failing requests; data from another replica is insufficient to explain the incident.

**Step 2 – Confirm the PID:** on a JDK with `jcmd`, the command:

```bash
jcmd -l
```

lists visible JVMs with PID and main class/command details. However, per JDK 21 `jcmd` documentation, listing **excludes some processes in separate Docker namespaces**; you may need OS tools and to run commands inside the right container. Never arbitrarily pick the first JVM in the list.

On Linux, if you know the PID from the process manager, inspect its OS details:

```bash
ps -p 12345 -o pid,ppid,lstart,etime,comm,args
```

**12345 is only a hypothetical PID**. The `args` column may contain tokens/passwords; view only in a controlled terminal and **do not paste verbatim** into tickets/chat. PIDs are reused after restarts; pair the PID with **process start time** to avoid reading a new run by mistake.

On Windows/PowerShell, with proper permissions you can inspect:

```powershell
Get-Process -Id 12345
Get-CimInstance Win32_Process -Filter 'ProcessId = 12345' |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Command-line info on Windows can also contain secrets. `Get-Process` confirms a process exists, yet seeing `java`/`javaw` alone does not guarantee it is the right JVM; verify start time, executable, application, and deployment.

**Step 3 – Bind identity to JVM data:** right before diagnosing, cross-check PID and startup time against service/instance ID, application version, startup logs, container ID, or deployment revision. When the JVM self-reports its PID, prefer matching it with process metadata from the same environment.

**Step 4 – Check attachability:** `jcmd` requires a compatible tool, matching permissions, and reachability to the target JVM; attaching may be disabled by a JVM option, blocked by policy/container, in a different namespace, or `jcmd` may be missing from the image. An attach error **does not prove** the application is not running Java.

## 4. Read-Only Commands with JDK 21: Querying the Live JVM Directly

After checking PID and access permissions, use a `jcmd` compatible with the target VM; in a HotSpot/JDK 21 environment, a typical diagnostic session runs:

```bash
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.uptime
```

Meaning of each command:

| Command | What it retrieves | Interpretation limits |
| --- | --- | --- |
| `jcmd 12345 help` | List of diagnostic commands supported by the target JVM | Commands vary by implementation and version; do not assume every JVM has the same ones |
| `VM.version` | Version info of the currently running VM | Not the terminal's `java -version` output |
| `VM.command_line` | Command line used to initialize the VM | May contain secrets, Java/VM options, and app command; does not reflect all post-launch runtime changes |
| `VM.flags` | Effective VM flags/values presented by this command | Not the full set of launcher parameters or application arguments |
| `VM.flags -all` | Supported JVM flags and current values, potentially with VM source/default markers | Long and HotSpot/version-dependent; does not mean every flag was operator-supplied at startup |
| `VM.uptime` | JVM process uptime | Used to cross-check run/PID; does not replace start timestamp and release ID |

According to Oracle JDK 21 documentation, these commands have **low** impact, but “low” does not mean zero; consider operational policies and audit logs. **In particular, `VM.command_line` can contain secrets**; read in a controlled place and publish only filtered versions.

To read current Java/OS properties, `VM.system_properties` is available on HotSpot:

```bash
jcmd 12345 VM.system_properties
```

Do not post the entire stdout publicly. Some applications store `-Dpassword`, `-Dtoken`, URLs with credentials, truststore passwords, or keys in system properties; reading does not mutate the JVM, yet **the output risks data exposure**.

On Linux/macOS, if you only need specific non-sensitive keys, you can filter output locally:

```bash
jcmd 12345 VM.system_properties |
  grep -E '^(java\.(version|runtime\.version|vendor|vm\.(name|vendor|version)|home)|os\.(name|arch|version))='
```

This snippet **only displays** properties matching the regex; values come from the live JVM. For systems with strict output controls, use a tool/program collecting an **allowlist at the source** rather than printing everything and filtering afterward. If a property does not appear, record its absence instead of guessing.

Where supported on HotSpot, `VM.info` provides broader environment/status details, though it is usually unnecessary for basic identity capture and increases the data to handle. Use it only when additional context is needed and review fields before saving.

## 5. Reading Version and Vendor Accurately

### 5.1 Properties That Must Not Be Equated

| Field | Meaning |
| --- | --- |
| `java.version` | Java runtime version, such as the `17.0.x` or `21.0.x` line |
| `java.runtime.version` | More detailed runtime version string if provided by the runtime; often includes build |
| `Runtime.version()` | Java 9+ API for structured runtime version; `feature()` gets the feature release such as 17 or 21 |
| `java.specification.version` | Java SE specification version supported by the runtime; not patch/build/vendor |
| `java.version.date` | Runtime release date if provided by the runtime |
| `java.vendor` | Published **runtime/distribution** vendor |
| `java.vm.name` | VM implementation name |
| `java.vm.vendor` | VM implementation vendor |
| `java.vm.version` | VM version/build string |
| `java.home` | Runtime environment path inside the process, not necessarily the shell's `JAVA_HOME` |

You cannot deduce vendor from `21.0.4` alone; different vendors can ship the same feature/patch release with different builds, CA/certificates, patching policies, and native libraries. The word `OpenJDK` in `java -version` **does not uniquely identify** the distribution publisher. Names like `HotSpot` or `OpenJ9` indicate the VM implementation, not necessarily the package vendor.

When investigating a compatibility issue, record **the full set of version + runtime vendor + VM name/vendor/version**, not just “Java 21”. To verify a specific CVE patch, check release metadata and image/runtime origin from that exact vendor; major version alone is insufficient.

### 5.2 Version Comparison Rules

- `Runtime.version().feature()` gives the **feature release**, useful for API/bytecode checks. `21` and `17` are different feature versions.
- Preserve patch/build strings verbatim from the target JVM; **do not guess** build metadata from the Java feature release. A JDK 21 on a build machine is not necessarily the same as JDK 21.0.x in production.
- `java.vm.version` and `java.runtime.version` can use different formats across vendors; do not concatenate or substitute them arbitrarily.
- An image with a Java 21 runtime can still run class bytecode compiled for Java 17; the reverse is not automatically true. When checking `UnsupportedClassVersionError`, verify both the **class-file major version** of the failing artifact and the target runtime version.

### 5.3 Do Not Rely on the Shell as Sole Proof

The commands:

```bash
command -v java
java -version
javac -version
```

only describe the executables/versions **accessible to the current terminal**. On a machine with `PATH`, `JAVA_HOME`, alternatives, SDK managers, IDEs, Gradle toolchains, `jlink` images, or containers, those results can differ from the running JVM service.

In PowerShell:

```powershell
Get-Command java
java -version
javac -version
$env:JAVA_HOME
```

These commands are useful for checking **your working environment**, but to prove properties of a JVM service you must read from **that process**. Even `java -version` inside a container only reflects a new process spawned by the `java` found in that container, which may not match a service using its own executable.

## 6. Identifying Architecture: JVM, OS, and Host Can Differ

`os.arch` in Java system properties describes the platform architecture name as seen by the Java runtime, typically `amd64`, `x86_64`, `aarch64`, or `x86` depending on JVM/OS. `os.name` and `os.version` provide OS context. When needing proof of bitness or native ABI, also compare **the JVM/native library binary architecture and process architecture** rather than inferring solely from host environment variables.

Distinguish three layers:

1. **Host/hardware:** physical CPU architecture of the machine or node.
2. **OS/container:** OS kernel and execution environment; containers usually share the host kernel yet have their own image/runtime, and may run an emulation layer across platforms.
3. **Target JVM:** the JVM binary and native libraries actually loaded by the process. `os.arch` from the target JVM pinpoints differences from the host.

Hypothetical example: a laptop uses an ARM64 CPU while a container runs a `linux/amd64` image under emulation; `uname -m` on the host may report ARM64 while the JVM inside the image sees `amd64`. Conclusions about JNI, native codecs, agents, or JIT must use the **actual running JVM's** architecture and matching native libraries, not the hostname or `uname` outside the container as sole proof.

On Linux, the following reads the kernel architecture of **the environment running the command**, which does not directly confirm bitness of a JVM in another namespace:

```bash
uname -m
```

Also never confuse `os.arch` with VM **memory** configuration: `-Xmx2g` sets the Java heap ceiling, does not prove CPU architecture, and process RSS can include native memory outside the heap. Container memory/CPU quotas also affect ergonomic heap sizing, thread counts, and performance; when investigating, record resource limits alongside VM flags when relevant.

### Common Signs of Architecture Mismatches

- `UnsatisfiedLinkError`, “wrong ELF class”, “mach-o wrong architecture”, or DLL/`.so`/`.dylib` load failures: inspect `os.arch`, ABI, and bitness of **both the process and native library**.
- Native agent provided as `linux-amd64` while the JVM runs `aarch64`: verify distribution/architecture of both the agent and Java runtime image.
- Performance differs between two nodes on the same Java feature release: compare vendor/build, architecture, container resource limits, effective GC/JIT flags, and workload rather than blaming the major version right away.

## 7. Distinguishing Four Layers of “Actual JVM Arguments”

Consider an illustrative launch line:

```bash
java -Xms256m -Xmx2g -XX:+UseG1GC -Ddiag.region=ap-southeast-1 \
     -jar service.jar --batch-size=100
```

This is an **illustrative** command and does not imply every application understands `--batch-size`. Meaning of the parts:

| Component | Category | How to verify |
| --- | --- | --- |
| `java` | Launcher executable | Process executable/OS metadata, `java.home`, and JVM identity |
| `-Xms256m` | JVM startup heap option | `VM.command_line`, `RuntimeMXBean.getInputArguments()`; related runtime value is `InitialHeapSize` |
| `-Xmx2g` | JVM startup heap limit | Command line; check `MaxHeapSize` via `VM.flags`/`VM.flags -all` |
| `-XX:+UseG1GC` | User-configured VM flag | Command line and effective flags (names/support vary by VM) |
| `-Ddiag.region=...` | Startup system property | `VM.command_line` or VM input args; current property via `System.getProperty` |
| `-jar service.jar` | Launcher artifact selection | Command line/OS metadata; runtime image does not include artifact hashes by default |
| `--batch-size=100` | **Application argument**, placed after `-jar` | `main(String[] args)`, app config, or command line; not in VM input arguments |

**Layer A – JVM input arguments at startup:** `ManagementFactory.getRuntimeMXBean().getInputArguments()` reflects input arguments passed to the VM according to the implementation; typically includes `-X`, `-XX`, `-D`, `--add-opens`, `-javaagent` if passed to the VM. Per the Java API, this list **does not contain `main()` arguments**, and is not guaranteed to contain every option of the `java` launcher itself.

**Layer B – Startup command line:** `jcmd PID VM.command_line` describes the command used to initialize the VM; presentation and exact shell-string reconstruction vary by implementation. Shell quoting/expansion, wrapper scripts, and `@argfile` can make the original order/syntax in deployment files differ from what the VM sees. Command lines can also include app arguments and sensitive info.

**Layer C – Active system properties:** `System.getProperty("key")`/`VM.system_properties` reads **current values**. A property may be set via `-D` at startup and later changed via `System.setProperty` in code. Thus **current values do not prove all sources and values at launch time**.

**Layer D – Effective VM flags:** `jcmd PID VM.flags` and `VM.flags -all` show the state/values reported by the VM. The JVM can auto-select flags via ergonomics, CPU/RAM/container limits; omitting a `-XX` option at startup does not mean the VM has no value for it. Some flags support dynamic updates; **current value** may differ from startup value. `VM.flags` is not equivalent to “the verbatim entire command line”.

### “Expected Config Source” Does Not Equal “Actual Value”

| Source | What it can prove | What it cannot prove |
| --- | --- | --- |
| Dockerfile or Deployment manifest | **Declared** image/config | Which digest the running replica came from, or how the entrypoint transformed it |
| CI/Gradle toolchain | JDK configured for build/compile | Which JDK actually executed the service |
| Shell `JAVA_HOME`, `PATH` | Current terminal's environment | Environment at service launch, or executable chosen by a wrapper |
| Service unit/start script | Options intended for the process | Env vars, options files, overrides, or unexpected restarts |
| `VM.command_line` + `RuntimeMXBean` | Startup input reported by the JVM | Full current app config and all ergonomic VM flags |
| `VM.flags -all` + system properties | VM/property state at read time | Who changed them, and all original command-line parameters |

Two environment variables that are very easy to overlook:

- **`JDK_JAVA_OPTIONS`**: supported by the Java launcher to prepend options before launcher arguments; its value in the service's runtime may differ from your inspection shell.
- **`JAVA_TOOL_OPTIONS`**: can inject VM options from the environment during VM initialization under supported conditions; exact behavior depends on launcher/VM. Do not assume that env string is automatically printed in full by `VM.command_line`.

There are also wrapper scripts, IDE run configurations, orchestrator environment variables, launch arguments from systemd/Windows services, and `@argfile`. When discrepancies appear, cross-check **startup input + runtime flags/properties + actual deployment sources**. Do not assume “every flag in `VM.flags -all` was passed by an operator,” nor think a `-D` option always means the app used that value for every component: some frameworks read a property only once at startup.

## 8. Java 17+ Practice: Printing the Runtime Fingerprint from the JVM Itself

This is a proactive collection approach when attach is unavailable: use built-in Java APIs inside the application to emit a **credential-free property allowlist**. The example runs on JDK 17+; version/vendor/architecture values depend on the machine, so no fixed stdout is assumed for them.

Create the file **`RuntimeFingerprint.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.Instant;
import java.util.List;

public final class RuntimeFingerprint {
    private static String property(String name) {
        return System.getProperty(name, "(khong-co)");
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        // The first two lines are determined by the practice command below.
        System.out.println("diag.mode=" + property("diag.mode"));
        System.out.println("applicationArgs.count=" + args.length);

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("startTimeUtc=" +
                Instant.ofEpochMilli(runtime.getStartTime()));

        for (String name : List.of(
                "java.version",
                "java.runtime.version",
                "java.specification.version",
                "java.vendor",
                "java.vm.name",
                "java.vm.vendor",
                "java.vm.version",
                "java.home",
                "os.name",
                "os.version",
                "os.arch")) {
            System.out.println(name + "=" + property(name));
        }

        System.out.println("runtimeFeature=" + Runtime.version().feature());

        List<String> heapStartupArgs = runtime.getInputArguments().stream()
                .filter(s -> s.startsWith("-Xms") || s.startsWith("-Xmx"))
                .toList();
        System.out.println("selectedHeapInputArgs=" + heapStartupArgs);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac RuntimeFingerprint.java
java -Xms64m -Xmx256m -Ddiag.mode=lab RuntimeFingerprint alpha beta
```

**Exact first two lines of stdout** for the practice command (OS-independent):

```text
diag.mode=lab
applicationArgs.count=2
```

Subsequent lines contain PID, JVM initialization timestamp, version, vendor, runtime home, OS arch, and `selectedHeapInputArgs`; **values depend on the actual runtime**. On standard HotSpot/JDK, the illustrative heap input arguments are usually `-Xms64m` and `-Xmx256m`, though do not assume every implementation must display them identically; inspect the captured output.

Mechanism explanation:

- `ProcessHandle.current().pid()` identifies the PID of **the JVM running this code**, rather than guessing a PID from `java` processes on the machine.
- `RuntimeMXBean.getStartTime()` gives approximate epoch milliseconds when the VM started; convert to `Instant` to record UTC time for correlation with logs and uptime.
- `System.getProperty(...)` reads the **current** value, not guaranteed to be immutable since launch time.
- `Runtime.version().feature()` is only the **feature release**; to retain patch/build, also record the detailed version string.
- `getInputArguments()` filters only `-Xms`/`-Xmx` to illustrate scoping output, avoiding printing all `-D`/agents since many apps carry secrets in JVM arguments.
- `alpha` and `beta` are **application arguments**, so `args.length == 2`; they do not become JVM input arguments.

Note: this is a **newly launched sample program**, so it only describes **that sample process**. To prove which values a failing service uses, run an equivalent collection mechanism **inside that exact service**, or use `jcmd`/JMX against the exact PID. Never run `RuntimeFingerprint` in a fresh container and attribute the results to a production container that has been running for days.

### Extending via JMX/Management API

If the application already exposes a properly secured management endpoint, you can query `RuntimeMXBean` and an **allowlisted** property set from the service itself. The `java.lang:type=Runtime` MBean provides runtime details such as VM vendor, VM version, start time, and input arguments. Do not expose remote JMX unconditionally just for convenience reading versions: management endpoints require authentication, authorization, network restrictions, and disclosure controls. A custom diagnostics endpoint should emit **only approved keys**, avoiding dumping the full environment or system properties.

Remember that `RuntimeMXBean.getInputArguments()` can contain secrets, and `getSystemProperties()` can return many sensitive fields. Even though the API is read-only, **publishing the output** must still follow data-sharing boundaries.

## 9. A Terminal Collection Pass: Sequence Usable During an Incident

Suppose you are investigating a HotSpot/JDK 21 process with PID **12345** on the right host/container. Record the UTC timestamp of the capture session and confirm the PID belongs to the right service **before each new capture** if autoscaling/restarts occur.

```bash
# Check available commands on the target JVM.
jcmd 12345 help

# Actual VM version/build.
jcmd 12345 VM.version

# Startup command; run only in an authorized terminal, redact before sharing.
jcmd 12345 VM.command_line

# Current flag values reported by the VM.
jcmd 12345 VM.flags

# Use when investigating defaults, ergonomics, or detailed origins.
jcmd 12345 VM.flags -all

# Uptime for correlating the specific startup instance.
jcmd 12345 VM.uptime
```

These commands **do not change VM flags**. `jcmd` is not automatically present in every image, and a `jcmd` from a different JDK vendor/version may not fully support diagnostics of the target VM. Use the tool best matched to the runtime/implementation when possible. Do not assert exact ordering or output of `VM.command_line` without observing it directly.

### If Attach Is Refused or PID Is Not Found

Check in order:

1. **Right namespace?** The process may run in another container; PID `1` in a container is not necessarily PID `1` on the host. Host-side `jcmd -l` may not list container JVMs.
2. **Right user/permissions?** Per Oracle JDK 21 documentation, `jcmd` must run on the same machine with matching effective user/group. Service accounts and OS policies can block attach.
3. **Is the tool in the image?** Minimal `jlink`/distroless runtimes may lack `jcmd` or a shell. Do not rush to modify/restart a container just to inject tools mid-incident.
4. **Did the JVM disable attach?** Some configurations disable the attach mechanism, or non-HotSpot runtimes do not support the same command set.
5. **Did the PID restart?** Compare PID, start time, container ID, and deployment revision against when the incident was noted.
6. **Is there an in-app read path?** Use a controlled diagnostics/JMX endpoint to query runtime identity; note the source clearly and avoid assuming another process's data is equivalent.

In Kubernetes, where you collect evidence matters just as much as the command: correlate **pod UID/container ID, image digest, node, restart count, and PID within the namespace**. Multiple pods with the same logical name or same image tag do not necessarily share the same image digest or runtime flags at read time.

### When Only OS Process Metadata Is Available

The OS can provide the executable path and raw command line, yet does not guarantee showing **all VM flags after JVM default selection** or **current system properties**. A `/bin/sh -c ...` script, Windows service wrapper, or process supervisor can also trick readers into mistaking the **wrapper process** for the child JVM. Record the OS source and confidence level; do not stretch `ps`/Task Manager output into claims about active GC or heap.

## 10. Comparing Expected Configuration with Effective Configuration

When a manifest says `-Xmx2g` yet heap/GC behaves unexpectedly, do not stop at grepping `-Xmx2g` in YAML:

1. Confirm **the right process** and runtime/VM version; verify Java executable, vendor, architecture, and startup time.
2. Read **startup input** via `VM.command_line` and/or `RuntimeMXBean.getInputArguments()` once authorized.
3. Read **effective flags** via `VM.flags`/`VM.flags -all`, including `MaxHeapSize`, `InitialHeapSize`, GC options, and related flags; distinguish byte values from `m`/`g` CLI notation.
4. Cross-check config sources: image entrypoint, process manager, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, options files, command-line overrides, container limits, and VM version.
5. If only comparing environments, read **existing** state; never use `VM.set_flag` to “test” config changes in production during identity collection.
6. Explicitly note whether a flag is **explicit**, **ergonomic/default**, or **changed at runtime** when supported by tools/evidence; do not assign an origin when uncertain.

For example, `-Xmx` usually relates to the effective VM flag `MaxHeapSize`, though fields do not necessarily display the same syntax. In container-aware environments, the JVM may compute heap from memory limits when `-Xmx` is omitted. Seeing a `MaxHeapSize` value does not prove an operator typed `-Xmx`; use startup input and deployment sources to conclude.

Running `java -XX:+PrintFlagsFinal -version` (if supported by the VM) also prints flags **of the new JVM spawned by that command**. It can help when building a reproducer, but does not replace `jcmd PID VM.flags -all` for a running process.

## 11. Collecting and Sharing Evidence Safely and Verifiably

**Minimalism principle:** any information sent externally must be **secret-sanitized and contain only relevant fields**. JVM arguments, environment variables, system properties, shell history, URLs, command lines, and config files can all carry private tokens/passwords/paths.

Data requiring special review before saving/sharing:

- `-D...` containing passwords, access tokens, API keys, JDBC URLs with credentials, proxy authentication, or truststore passwords.
- `-javaagent:`, `-agentpath:`, `--module-path`, and `-cp` that may expose internal paths.
- Application arguments after `-jar`/main class that may contain secrets; `jcmd -l`/OS `ps args` can expose them too.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and the full environment can contain sensitive data outside the runtime question's scope.
- JMX or `VM.system_properties` may capture app data added by frameworks/code unrelated to JDK identity.

**Reporting format:** record `java.version`, `java.runtime.version`, `java.vendor`, `java.vm.*`, `os.arch`, PID/process start time, source name, and an **approved** list of options (e.g., reviewed heap/GC flags). For secrets, put `[REDACTED]` in the report **without preserving the value or token character count**. Never store raw `VM.command_line` in broadly shared documents.

An illustrative capture template, with **hypothetical data**:

```yaml
captureTimeUtc: "2026-10-29T08:10:00Z"
scope:
  service: "catalog-api"
  environment: "staging"
  instance: "catalog-api-2"
  processId: 12345
  processStartUtc: "2026-10-29T07:42:00Z"
runtime:
  javaVersion: "21.0.4"
  javaRuntimeVersion: "21.0.4+7"
  javaVendor: "Vendor A"
  vmName: "OpenJDK 64-Bit Server VM"
  vmVendor: "Vendor A"
  vmVersion: "21.0.4+7"
  javaHome: "/opt/java/runtime"
platform:
  osName: "Linux"
  osArch: "amd64"
vm:
  explicitOptionsReviewed: ["-Xms256m", "-Xmx2g", "-XX:+UseG1GC"]
  effectiveMaxHeapSizeBytes: 2147483648
  commandLineShared: "REDACTED"
evidence:
  commands: ["VM.version", "VM.command_line", "VM.flags", "VM.system_properties"]
  source: "Attached to the target JVM using jcmd"
  incompleteFields: []
```

Do not treat the values above as “Java 21 defaults”: this is a **structural template**, not real output from any process. When applying it, replace every value with data from the target JVM and list only commands actually run; if a field could not be read, mark `unavailable` with a reason rather than filling in an approximate number.

To compare two deployments, build a diff table across the **exact same fields**: process start, full Java runtime version, vendor, VM name/build, `os.arch`, effective heap/GC flags, redacted explicit options, and artifact/container hashes/digests if available. Compare at matching timestamps or matching workload phases; avoid confusing restart/deploy changes with runtime flag changes.

## 12. Typical Scenarios

### Scenario A – “Both servers use Java 21” yet only one fails

Servers A and B both report `java -version` as Java 21 over SSH, yet the error occurs only on B. That is only **shell** data. Investigate the exact service PID on both:

1. Record PID, process startup time, container ID, and application build.
2. Collect `VM.version`, `java.runtime.version`, `java.vendor`, `java.vm.name`, `java.vm.version`.
3. Cross-check `os.arch`, `java.home` path, image digest, and architecture.
4. Compare startup args and effective flags after redaction.
5. Only after confirming a difference should you reproduce the error or conclude version/vendor is involved.

Results might reveal service B actually runs Java 17, a different runtime build, a different architecture, or an extra agent/flag despite the terminal defaulting to Java 21. If all fields match, this evidence helps **rule out several configuration hypotheses**, though it does not rule out workload, application state, or network conditions.

### Scenario B – “The manifest declared `-Xmx2g`, why does the JVM use a different heap?”

Start with `VM.command_line` to see what input the VM received, then `VM.flags`/`VM.flags -all` to inspect current `MaxHeapSize`. Check the service wrapper/entrypoint, deployment overrides, container memory limits, and env/options files. Reading only the manifest while ignoring process state can misdiagnose the source of memory pressure. Reading only `MaxHeapSize` without startup options cannot distinguish explicit `-Xmx` from ergonomic values.

### Scenario C – Native library works locally yet fails to load in production

Collect `os.arch` from the JVM in both environments, record `java.vm.name`, version/vendor, and binary type of the JNI/native artifact. Check OS, libc/ABI, and library dependencies. Do not take `uname -m` from the host as the architecture of a container process. One image tag can point to different ARM64 and amd64 variants; compare by **digest + platform** when investigating image distribution.

### Scenario D – Cannot use `jcmd` in a production image

If the runtime is minimal or attach is blocked by policy, use a pre-built telemetry/management endpoint exposing the allowlisted info from Section 1. If no in-process evidence exists, document the limitation; never use `java -version` in a fresh debug container as proof for a running JVM. Any decision to add diagnostics for the next deployment must go through proper processes; identity collection does not grant authority to swap out a running runtime.

## 13. Pitfalls to Avoid

| Misconception | More accurate reality |
| --- | --- |
| “`java -version` in the terminal is the production JVM version.” | The terminal may use a different executable. Query the target process directly and verify PID/start time. |
| “`JAVA_HOME` controls every JVM on the machine.” | Wrappers, service managers, absolute paths, images/containers, and toolchains can choose other runtimes. |
| “`java.version` is enough to know patches/vendor.” | You need full runtime/build, distribution vendor, VM info, and sometimes image digest. |
| “`java.vendor` and `java.vm.vendor` are always identical.” | These two properties have distinct meanings; record verbatim rather than assuming. |
| “Host `os.arch` always equals the JVM's.” | Containers/emulation/native ABIs can differ; read from the live JVM. |
| “`VM.command_line` and `VM.flags -all` are the same thing.” | One is startup input; the other presents current flags, including VM defaults/ergonomics. |
| “Having `MaxHeapSize` means an operator passed `-Xmx`.” | The VM can size heap automatically; verify startup args and config sources. |
| “`RuntimeMXBean.getInputArguments()` includes everything after `-jar`.” | It excludes `main()` args and is not required to include every launcher option. |
| “Current system properties always equal startup `-D`.” | Applications can call `System.setProperty`; current state does not prove history. |
| “Not finding a PID in `jcmd -l` means the app isn't running Java.” | PID namespaces, containers, permissions, and tools can omit processes from listing. |
| “Logging raw command lines is handy for debugging and risk-free.” | Arguments and system properties can contain passwords/tokens; share only sanitized versions. |
| “`-XX:+PrintFlagsFinal -version` describes the running service.” | That reports info for **a new JVM** spawned by that command. |

## 14. Self-Check Questions

**Q1.** The host shell reports JDK 21, but the service's JVM returns `java.version=17.0.x`. Which version should go in the incident report?

**A:** Runtime 17.0.x of **the exact service process**, along with vendor/build and read source. The shell's JDK 21 can be noted as an environment observation, not as a substitute for the service's reality.

**Q2.** `RuntimeMXBean.getInputArguments()` lacks `--batch-size=100`; is the launch command missing an argument?

**A:** No. If `--batch-size=100` appears after the main class or `-jar service.jar`, it is an app argument; the API returns JVM input arguments, not `main(String[] args)`.

**Q3.** `VM.flags -all` reports `MaxHeapSize`, yet `VM.command_line` shows no `-Xmx`. Is that a contradiction?

**A:** No. `MaxHeapSize` always has a VM-determined value, which can come from defaults/ergonomics or environment resource limits without requiring an explicit `-Xmx`.

**Q4.** A container on an ARM64 host reports `os.arch=amd64` from the service itself. Which value should guide native library lookup?

**A:** Investigate the architecture/ABI of **the JVM process and native artifact**. The JVM's `os.arch=amd64` is a critical fact; an ARM64 host does not prove an ARM64 library can be loaded by an amd64 process.

**Q5.** Can raw `VM.command_line` and `VM.system_properties` output be pasted straight into a ticket?

**A:** Only after reviewing and removing sensitive information per policy. Ideally, collect an **allowlist** of needed fields and note that sensitive data was stripped from the shared record.

**Q6.** `jcmd` fails to attach because the service runs under a different UID. Should the investigator run `java -version` in their own shell to determine the JVM version?

**A:** No. Use authorized permissions and collection paths, or an existing in-process endpoint; mark the status **unverified** if data could not be retrieved from the target JVM itself.

## 15. Practical Incident Checklist

- Confirm the exact **service, host/container, PID, and start time**; record application build/deployment digest when possible.
- Collect from the target JVM: **full Java runtime version; `java.vendor`; `java.vm.name`, `java.vm.vendor`, `java.vm.version`; `java.home`; `os.name` and `os.arch`**.
- Collect startup VM options and active flags via supported tools; document **source**, UTC time, command, tool version, and attach limits.
- Separate **VM input arguments**, **app arguments**, **current system properties**, and **effective VM flags**.
- Compare expected sources (manifest/IDE/service script/CI/JDK env) against **actual process info**; watch for container architecture, resource limits, env injection, and runtime image version.
- Inspect/redact secrets before saving files or sending reports; rely only on verifiable facts and mark unreadable fields.

**Conclusion principle:** data from the target JVM at the right point in time outweighs expected configuration. Collecting version, vendor, architecture, and arguments is only useful when **tied to the exact process, exact startup instance, reliable source, and accurate scope interpretation**.

### Official References

- [Oracle JDK 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `jcmd -l`, `VM.version`, `VM.command_line`, `VM.flags`, `VM.system_properties`, user/host requirements.
- [Oracle JDK 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): launcher, `-D`, `-X`, `-XX`, `@argfile`, `JDK_JAVA_OPTIONS`, and distinguishing app arguments.
- [Java SE 21 — `System` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): Java runtime, VM, and OS properties.
- [Java SE 21 — `RuntimeMXBean` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html): input arguments, start time, VM name/vendor/version, and management system.
- [Java SE 21 — `ProcessHandle` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html): PID and info of the current process.