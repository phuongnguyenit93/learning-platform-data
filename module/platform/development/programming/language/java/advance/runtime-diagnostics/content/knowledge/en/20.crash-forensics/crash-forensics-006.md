# 20.6. Core Dumps, Executables, and JDK or Architecture Compatibility Requirements During Analysis

## Objectives

After this lesson, you will be able to:

- Distinguish a **process core dump / crash dump** from `hs_err_pid*.log`, a Java heap dump `.hprof`, a thread dump, and a JFR `.jfr` file.
- Explain why post-crash analysis requires **the core + the actual executable that ran + matching native/JDK libraries**, rather than just a `core` file alone.
- Verify compatibility across **OS, dump format, CPU architecture, 32/64-bit, JDK vendor/version/build, `libjvm`, native libraries, and debug symbols**.
- Execute a Linux workflow with `file`, `readelf`, `sha256sum`, `coredumpctl`, `jhsdb`, and `gdb`; understand what differs on Windows and macOS.
- Recognize cases of **missing cores, truncated cores/missing mappings, and mismatched binaries**, along with security risks when storing or sharing dumps.

**Scope:** HotSpot/OpenJDK during **postmortem analysis**. Examples focus on Linux ELF cores; Windows and macOS have different dump formats, tools, and debuggers. Illustrative commands do not trigger crashes on live systems. A process core dump can contain highly sensitive data; every step must follow security policy.

## 1. First: What Kind of Artifact Do You Have?

When a Java application fails, not every file with *dump* in its name works with the same tools.

| Artifact | Primary contents | Typical tools | What not to confuse it with |
|---|---|---|---|
| **Linux core file (ELF core)** | Snapshot of **part or many parts** of address space, thread states, and registers when the process died or was dumped | `gdb`, `jhsdb` with matching executable and libs | Not a guaranteed snapshot of all RAM; mappings may be omitted |
| **Windows process dump `.dmp`** | Process dump by full/minidump type and collection policy | WinDbg / compatible Windows debuggers | Not by default an ELF core usable with Linux `gdb`/`jhsdb` |
| **macOS core/crash report** | Core with its own format/scope; crash report has stack/metadata | `lldb` and Apple tools | Not Linux ELF; a crash report does not automatically equal a full core |
| **`hs_err_pid*.log`** | Fatal error report HotSpot may generate: signal/exception, problematic frame, JVM, OS, native libraries, registers/stack when available | Text viewer, manual analysis | Not a file containing full process memory |
| **Java heap dump `.hprof`** | Java object graph / heap at capture time | Eclipse MAT, VisualVM / heap analyzers | Does not replace native frames/registers from a core |
| **Thread dump** | Thread stacks and states at capture time | `jcmd`, JFR/JMC, text tools | Does not contain a full memory image or registers |
| **JFR `.jfr`** | Time-ordered event stream: GC, CPU samples, allocations, threads, I/O, etc., if enabled | `jfr` CLI, JDK Mission Control | Not a post-crash core snapshot |

A **core dump** is most useful when the JVM/process **dies from a native fault** such as `SIGSEGV`, `SIGBUS`, `SIGILL`, or `SIGABRT` on Linux (depending on OS/signal/config). It lets you ask: which thread faulted, where was the instruction pointer, what were the registers, what did the Java/native stacks look like, and which binary/library owned the code and data at that address.

**Note:** ordinary Java exceptions (`NullPointerException` in Java code, for instance) **do not automatically produce an OS core dump**. A Java `OutOfMemoryError` also does not generate a core by default; container/kernel OOM killers typically terminate with `SIGKILL`, which **does not generate a core via the signal-crash mechanism**. If you only have `ExitCode=137` in a container, prioritize checking cgroup/OOM events before looking for a core.

## 2. Why Is a Core Alone Not Enough? You Need the Exact Executable and Libraries

In Linux ELF, a core primarily preserves process state and the memory regions the OS chose to write. Code segments, symbol tables, debug info, and certain mapped pages may **not be fully included inside the core**. A native debugger needs the corresponding **executable** and **shared libraries** to map addresses in the core back to machine code, functions, and stacks.

Suppose Java crashes in native code:

```text
Core:   PC = 0x7f...; TID = ...; registers; mappings; memory pages
          |
          +--- executable that ran: /opt/runtime/bin/java
          |
          +--- JVM library: /opt/runtime/lib/server/libjvm.so
          |
          +--- native/JNI libraries: libfoo.so, libbar.so, libc.so...
          |
          +--- debug symbols (if available): debuginfo, build-id, symbol files
          v
GDB: native backtrace, registers, instruction/symbol near fault
jhsdb: attempts to decode Java threads/HotSpot VM structures/heap
```

If you use a **different executable** or a `libjvm.so` from after an upgrade:

- The debugger may still open the core, yet resolve **wrong** symbols or offsets.
- The stack may show `??`, nonsensical frames, wrong addresses, or fail while reading JVM data.
- The Serviceability Agent in `jhsdb` may fail to recognize HotSpot's internal layout/structures, even if both JDKs say “Java 21.”
- Simply being able to open the file **does not prove** every frame or object was decoded accurately.

**Key concepts:**

- **JDK version** is a version label (`21.0.x`, `24.0.x`), **not a complete fingerprint**.
- **JDK vendor/distribution/build** identifies the specific product and build; even within the same major version, patches, native layouts, compiler flags, or native binaries can differ.
- **Executable** is *the binary that actually started the process*: usually `bin/java`, though JNI Invocation API or a custom launcher can make the executable another binary. Never assume `app.jar` itself is the executable `jhsdb --exe` expects.
- **`libjvm`** is the HotSpot native library; identical filenames alone do not prove identical hashes or builds.
- **Native/JNI/shared libraries** and libc/loader also affect native backtrace reconstruction; symbol packages must match the exact build.

### A practical rule

To minimize errors, prioritize **reconstructing the exact runtime image from the crash**: the same OS ABI, CPU architecture, JDK binaries, and libraries used, plus debug symbols matching the **build ID** if available. Save a hash-verified copy from the deployment artifact or container image rather than grabbing a random “same major” JDK after the incident occurs.

Not every preliminary check requires an exact byte-for-byte build: GDB can still inspect some registers, threads, or file metadata even when symbols are missing. However, for **deep conclusions about HotSpot objects, heap, or Java stacks**, build consistency is exceptionally valuable; never trust data from a mismatched build without verification.

## 3. Compatibility Checklist Before Opening a Core

| Comparison layer | What to verify | What happens if wrong? |
|---|---|---|
| **Format** | Linux ELF core, Windows dump, macOS Mach-O core/crash report | Tools fail to open or misparse the format |
| **Machine architecture** | `x86_64/amd64`, `aarch64/arm64`, 32-bit ARM, etc. | Native debugger / SA does not support cross-target; registers and ISA differ |
| **Word size & ABI** | 32/64-bit, endianness, matching ABI and OS | Pointer/stack/register layouts are incompatible |
| **Executable build** | Byte-for-byte binary or build ID/hash matching the core's time | Symbol addresses and stack mappings can shift |
| **JDK vendor/build/patch** | Matching Java runtime/VM version, vendor, HotSpot implementation, build | HotSpot SA may misdecode internal structures |
| **`libjvm` and JDK libraries** | The exact ones loaded at crash time, matching path/build ID | Native frames and HotSpot offsets may not match |
| **JNI/native libraries and libc** | Exact versions, symbols, loader, and mapping paths | Missing frames or symbols in the crashing library |
| **Debug symbols** | Symbols for executable/`libjvm`/native libs must share the same build ID | Backtrace may still show addresses, but few function names or file:line info |
| **Core integrity** | Complete file, hash, not truncated, essential mappings dumped | Memory/stack queries fail or data is missing |
| **Analysis toolset** | `gdb`/`jhsdb` version compatible with the OS/JDK/format | Parser errors, Unsupported OS/CPU, symbol mismatch |

**Do not conflate these layers:** having the same `os.arch=amd64` does not guarantee the same CPU feature set, libc, or binary. Being the same Java `21` does not guarantee the same `21.0.x+build`. And a binary with the right hash **does not make a core file missing pages complete**.

For x86-64 vs. AArch64, use `file`/`readelf` on both the executable and core (on Linux) to check `Machine`, `Class`, and `Data`. Cross-architecture analysis is only feasible when the debugger truly supports the target and all corresponding files/runtimes are present; with `jhsdb`, do not assume arbitrary cross-architecture analysis works.

## 4. Collecting Artifacts at the Right Time: Before a Rollout Replaces the JDK/Image

An incident can lose investigability if the team saves only the `core` file while CI/CD replaces the runtime after a restart. While authorized metadata access is still available, prioritize keeping:

1. **The core file or Windows dump** and its checksum.
2. **`hs_err_pid*.log`** associated with the same PID/incident (if HotSpot generated it).
3. **The original executable** and the entire JDK/runtime image used, especially `lib/server/libjvm.so` on Linux HotSpot.
4. **Application/JNI native shared libraries**, relevant libc/loader, OS/container image version, and matching debug symbols.
5. **Application JAR/config/flags/command line** from the crashed deployment version; logs and JFR if captured.
6. **Correlation metadata:** UTC timestamp, PID/TID (mindful of container namespaces), host/pod/container ID, image **digest** rather than just tag, architecture, and crash signal/exit code.

If the application runs in a container, save the **image digest** or an immutable artifact. A tag like `latest` or `release-2026` can later point to a new image; pulling that tag again does not guarantee the exact libraries mapped at crash time.

### On Linux, while the process is still alive

The following commands are **read-only**. Replace `12345` with the real PID:

```bash
PID=12345

readlink -f "/proc/$PID/exe"
cat "/proc/$PID/cmdline" | tr '\0' ' '
grep -E 'libjvm|libc\.so|libjli|\.so' "/proc/$PID/maps"
cat "/proc/$PID/limits" | grep -i 'core file'
```

`/proc/$PID/exe` tells you which binary is **actually running**, but once the process crashes and vanishes, that link disappears. `/proc/$PID/maps` shows the **mappings at observation time**; if a library is later replaced or deleted, the path alone cannot recover the original byte-for-byte version. These commands may require privileges to inspect another process; `cmdline` can also contain sensitive arguments, so do not share it carelessly.

If the process is already dead, rely on `hs_err`, `systemd-coredump` metadata, deployment inventory, container image digests, OS package databases, and pre-saved artifacts. Never claim the JDK on the **current host** is the one that crashed if a deployment replaced it.

## 5. Why Is the Core Sometimes Missing? Checking Linux Policies

### 5.1. Limits and write mechanisms

Before running workloads in an environment **where you are authorized to configure settings**, check:

```bash
ulimit -c
cat /proc/sys/kernel/core_pattern
```

`ulimit -c` is the soft core-file-size limit of the **current shell**, not necessarily the limit of a previously running service. `ulimit -c unlimited` in a shell affects only that shell and its child processes; for systemd services you typically configure `LimitCORE=` or the relevant service/container policy. A `core_pattern` starting with `|` means cores are piped to a **user-space handler**, such as `systemd-coredump`, rather than written as a `core` file in the working directory.

Other reasons a file may not appear:

- The crash did not raise a signal whose default action dumps core; e.g., `SIGKILL` from the OOM killer.
- Dumpable flags, file/directory permissions, container permissions, security policies, or quotas blocked writing.
- Filesystem full, core too large, collector pipeline limits, or retention deleted it.
- Mappings excluded via `coredump_filter` or `MADV_DONTDUMP`, leaving **core contents partially missing**.
- In some cases HotSpot writes an error log yet the OS creates no core; there is no basis to assume both always appear together.

### 5.2. If the host uses systemd-coredump

Once you confirm the host uses `systemd-coredump`, with appropriate permissions:

```bash
coredumpctl list
coredumpctl info 12345
coredumpctl dump 12345 -o core.12345
```

Replace `12345` with the incident PID. `coredumpctl` may not be installed, data may be restricted by permissions/capacity, or retention may have expired; `PID`s can repeat over time, so cross-check **timestamp, executable, and unit/host** in the metadata. Extracted files must be stored securely.

Do not run `kill -SEGV`, `kill -ABRT`, or force crashes in production just to test core collection. If policy testing is needed, use a dedicated test process in an approved, isolated environment.

### 5.3. `hs_err` and output location

When HotSpot encounters a fatal error, it usually tries to write `hs_err_pid*.log`, though success depends on process state and filesystem permissions. You can set a target path via the HotSpot option:

```bash
java -XX:ErrorFile=/secure/java-crashes/hs_err_pid%p.log -jar app.jar
```

This example only works if `/secure/java-crashes` already exists and the process has write permission; HotSpot does not create missing directories. Paths and filenames depend on deployment. In the log, check **JRE/VM version, problematic frame, signal/exception, current thread, native frames, dynamic libraries, and memory map** when present, as well as the core dump location message. This log file is **corroborating evidence**, not an executable or a core dump.

## 6. Verifying Files and Architecture on Linux

Suppose you placed artifacts in a restricted investigation directory containing `core.12345` and the saved executable. Replace illustrative paths with your actual paths.

```bash
file /secure/incident/core.12345
file /secure/incident/jdk/bin/java

readelf -h /secure/incident/core.12345
readelf -h /secure/incident/jdk/bin/java

readelf -n /secure/incident/jdk/bin/java
readelf -n /secure/incident/jdk/lib/server/libjvm.so

sha256sum /secure/incident/core.12345 \
          /secure/incident/jdk/bin/java \
          /secure/incident/jdk/lib/server/libjvm.so

uname -m
```

Meaning:

- `file` quickly identifies ELF cores, ELF binaries, architecture, and 32/64-bit class from metadata; it does not guarantee the core contains **all pages**.
- `readelf -h` reads the ELF header: `Class`, `Data`, `Machine`, `Type`; detects 32/64-bit or x86-64/AArch64 mismatches.
- `readelf -n` displays ELF notes, sometimes including a `Build ID` to match binaries with debug symbols; not every build includes a build-id.
- `sha256sum` verifies byte integrity between stored and transferred copies, **without proving by itself** that the files came from the same process unless you have trusted checksums/inventory from crash time.
- `uname -m` reports the architecture of **the analysis machine**, not the machine that produced the core. If you move a core to another host, architecture conclusions must come from the **core/executable**, not the local `uname`.

`libjvm.so` may reside at a different path or be absent if the VM is not standard Linux HotSpot. Use the original image/runtime; never assume identical layout across different JDK distributions.

### 6.1. Not all levels of matching are equal

| Result | Interpretation |
|---|---|
| Both core and executable are ELF64 x86-64 | **Only passed format/architecture checks so far** |
| Same Java major `21` but different vendor or patch | Not reliable enough for deep HotSpot SA analysis; exact build needed |
| Executable hash matches, yet `libjvm.so` was replaced after deployment | Native symbols and HotSpot memory layout may still be wrong |
| `libjvm.so` Build ID matches debug symbols | Much better chance of resolving native function names and file:line |
| Core opens, yet a critical mapping is missing | Some memory/stack/heap queries will fail even with the right executable |
| Analyzing on a different OS/arch host | Requires matching debugger and target support; do not assume `jhsdb`/`gdb` supports every combination |

## 7. Analyzing Java/HotSpot Cores with `jhsdb` (Serviceability Agent)

**`jhsdb`** is a JDK tool using the **Serviceability Agent (SA)** to inspect VM/Java structures from a live process or core dump. It is **experimental and unsupported** per Oracle Java SE 21 documentation. Because it depends heavily on HotSpot internals, **matching the exact JDK build is critical**. The examples below show documented syntax, not output from a real core here.

### 7.1. Basic commands with core and executable

```bash
jhsdb jstack \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345

jhsdb jstack --mixed \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345

jhsdb jinfo \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345
```

- `jhsdb jstack` attempts to reconstruct **Java threads and stack traces** from the core.
- `--mixed` attempts to include native frames when supported by the platform/tool; it is not guaranteed to unwind every frame.
- `jhsdb jinfo` can retrieve VM flags and properties.
- You can also use `jhsdb jmap --heap` or `--histo` with `--exe`/`--core` when supported by the tool and core; analyzing large heaps can consume substantial resources.

If interactive exploration of HotSpot structures is needed:

```bash
jhsdb clhsdb \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345
```

This opens an interactive **CLI debugger**. `jhsdb hsdb` provides a GUI when an appropriate environment is available. Never run these commands on unauthorized production cores; cores contain process data and tools may parse untrusted files, so prefer an isolated diagnostic sandbox.

**`--exe` must be the binary that actually produced the core**, not an arbitrary Java bytecode/JAR file. If the application embeds the JVM via the JNI Invocation API, the executable may be a native launcher rather than `bin/java`. Never swap `--exe` to a newly installed `java` just to make the command run.

### 7.2. Critical warning about live attach

According to Oracle documentation, **attaching `jhsdb` directly via `--pid` to a running JVM can hang the process and risks crashing it when the debugger detaches**. This lesson focuses on **postmortem `--exe` + `--core`**. Do not make live attach a routine production practice, especially when an incident already produced a core for offline analysis.

### 7.3. Interpreting Serviceability Agent errors

Symptoms such as “unrecognized VM layout,” address read errors, missing symbols, or malformed stacks can be caused by:

- Wrong `--exe` or files from a **different JDK build/vendor/version**.
- `libjvm`/runtime libraries that do not match the core.
- Different CPU architecture/OS ABI, or an SA version that does not support that combination.
- Core missing mappings, truncated/corrupted, or missing critical pages.
- Core created by a **native launcher** rather than the specified `bin/java`.
- Real memory corruption in the VM at crash time: some structures were overwritten even though all artifacts match.

**Distinguish “the tool could not parse it” from “found an application bug.”** Verify artifact compatibility and completeness before concluding that corrupted memory was caused by an application bug.

## 8. Analyzing Native Crashes with GDB and Matching Symbols

**GDB** reads an ELF core alongside its executable to inspect **native frames, registers, and thread states**. It does not natively understand HotSpot's object graph the way `jhsdb` does; when the JVM runs JIT-compiled Java, GDB may show only native entry/VM frames or code-cache addresses without reconstructing full Java stacks.

### 8.1. Opening the core

```bash
gdb -q /secure/incident/jdk/bin/java /secure/incident/core.12345
```

Inside a GDB session (the following lines are **interactive commands**, not stdout):

```text
info files
info sharedlibrary
info threads
thread apply all bt
bt full
info registers
```

- `info files`: inspect executable, sections, and file details of the debug session.
- `info sharedlibrary`: check shared libraries known to GDB and their symbol status.
- `info threads`: list OS threads in the core.
- `thread apply all bt`: generate native backtraces for all threads, helping inspect the crashing thread, JNI frames, and libc/VM internals.
- `bt full`: details of locals in the **currently selected thread** if symbols/debug info allow.
- `info registers`: register values (for the selected thread) showing PC/SP, pointers, and fault state.

These commands do **not** “re-run” the core; they read a post-crash snapshot. Without debug symbols, you can still read addresses and some exported symbols, though many frames will appear as `??` without file/line/locals.

### 8.2. When GDB picks up the analysis machine's libraries by mistake

If the core came from a container or another host, paths in the mappings may look identical while **the file contents on the analysis machine differ**. GDB may report missing shared libraries or load an incompatible host library.

The solution is to supply **copies of the original libraries** in an appropriate directory tree and configure `sysroot`/`solib-search-path` per GDB documentation, for example:

```text
(gdb) set sysroot /secure/incident/rootfs
(gdb) set solib-search-path /secure/incident/native-libs
(gdb) info sharedlibrary
```

These are **interactive GDB commands**; you must obtain the real rootfs/native libs from the original container/image rather than creating them by installing a similarly named package yourself. Depending on how GDB already loaded libraries, you may need to **restart the GDB session or reload symbols** after updating search paths.

**Debug symbols must also match the exact build**: a symbol package with the right name but a different build ID can yield wrong stacks or missing line numbers. When build IDs exist, verify with `readelf -n` and your debuginfo distribution system. Even from the **same source code**, binaries can differ due to compiler flags or linkers; “same commit” does not guarantee the same native address layout.

### 8.3. Tracing root cause from “problematic frame”

If `hs_err_pid*.log` says:

```text
# SIGSEGV ... 
# Problematic frame:
# C  [libexample.so+0x1234]  example_call+0x...
```

This is **illustrative format only**, not a log from a specific crash. Analysis steps:

1. Obtain `libexample.so` from the **crashed image/deployment**, not the newest version.
2. Correlate the core thread/PC and GDB's native backtrace.
3. Check JNI arguments, buffer/pointer lifetimes, concurrency, memory corruption, or bugs in the library.
4. Distinguish the **faulting instruction** from the **root cause**: a memory overwrite may have occurred earlier and crashed in a different function.
5. Add sanitizers, native reproduction tests, and vendor bug reports when appropriate.

Never conclude “JVM bug” merely because the frame is inside `libjvm.so`: an earlier JNI error or memory corruption can cause the VM to crash. Conversely, if a real JVM bug is present, preserve the exact build and incident evidence to check release notes and vendor support.

## 9. Runnable Java 17+: Recording an Environment Manifest Before a Crash

**Purpose:** practice collecting runtime metadata to later correlate a core with its executable/JDK—**without** triggering a crash and without pretending a real core exists. Java APIs cannot by themselves confirm all native library mappings and checksums; therefore, this example provides **reference** data that must be paired with OS tools and deployment inventory.

Create **`CrashArtifactManifest.java`**:

```java
import java.nio.file.Path;
import java.util.Locale;

public class CrashArtifactManifest {
    private static void show(String name, String value) {
        System.out.println(name + "=" + value);
    }

    public static void main(String[] args) {
        String javaHome = System.getProperty("java.home");
        boolean windows = System.getProperty("os.name").toLowerCase(Locale.ROOT)
                .contains("windows");
        Path candidateJava = Path.of(javaHome, "bin",
                windows ? "java.exe" : "java");

        show("java.version", System.getProperty("java.version"));
        show("java.runtime.version", System.getProperty("java.runtime.version"));
        show("java.vm.name", System.getProperty("java.vm.name"));
        show("java.vm.version", System.getProperty("java.vm.version"));
        show("java.vm.vendor", System.getProperty("java.vm.vendor"));
        show("os.name", System.getProperty("os.name"));
        show("os.arch", System.getProperty("os.arch"));
        show("os.version", System.getProperty("os.version"));
        show("java.home", javaHome);
        show("candidate.java", candidateJava.toString());
        show("actual.command", ProcessHandle.current().info().command()
                .orElse("(unavailable)"));
        show("pid", Long.toString(ProcessHandle.current().pid()));
        System.out.println("Inventory complete");
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 CrashArtifactManifest.java
java CrashArtifactManifest
```

The program prints **keys with machine-dependent values**. Example abbreviated output on a Java 24 machine (**illustrative only, not fixed stdout**):

```text
java.version=24.0.2
java.runtime.version=24.0.2+12
java.vm.name=OpenJDK 64-Bit Server VM
java.vm.version=24.0.2+12
java.vm.vendor=...
os.name=...
os.arch=amd64
os.version=...
java.home=...
candidate.java=...
actual.command=...
pid=...
Inventory complete
```

The final line **`Inventory complete`** is fixed; PID, paths, and OS/vendor/version **are not fixed**. The example was compiled with `javac --release 17` and verified on OpenJDK 24.

**How to read the output:**

- `java.vm.version` and `java.runtime.version` help identify the build; when multiple runtimes exist on a host, do not rely solely on `java -version` from the current shell.
- `java.home` and `candidate.java` are **candidates**, not guarantees of the actual launching binary. In embedded JVMs, `jlink` runtime images, custom launchers, or symlinks, the location and executable may differ.
- `actual.command` from `ProcessHandle` may be withheld by the OS/JVM, printing `(unavailable)`; nor does it replace hash/build ID verification.
- `os.arch` describes the JVM/OS architecture per Java properties, not an ELF header check of a future core.
- `pid` helps link logs and dumps, though PIDs can be reused and differ across host/container namespaces.

In production, rather than printing `java.home`/command lines casually to public logs, capture manifests under operational permissions, protect the data, and store alongside deployment ID/image digest. Gather `hs_err`, the JDK image, and native libs together after an incident.

## 10. When Analyzing on Windows or macOS

### 10.1. Windows

On Windows, process dumps typically have a `.dmp` extension and are opened with **WinDbg / Windows Debugger** alongside the matching executable/DLLs and **PDB symbols**. Crash reports can lead to a minidump or a full dump; a **minidump contains only a subset** of memory/information configured by the collector, so many variables and heap pages may be unavailable.

Items to verify include **x64/ARM64/32-bit**, exception code, module versions, DLLs, PDB GUID/age, and dump completeness. Do not use a Linux ELF analysis host and assume it can open every `.dmp` file. `.dll` paths and PDB loading work differently from Linux `.so`/debuginfo. Whether `jhsdb` works with a particular Windows dump depends on the JDK/platform/format and must be verified in practice.

### 10.2. macOS

On macOS, **Mach-O/dSYM** and **LLDB** are standard formats/tools for reconstructing native stacks. Check Apple Silicon `arm64` vs. Intel `x86_64`, executable/framework/dylib versions, and matching dSYM UUIDs. A **macOS crash report** typically provides metadata/stacks without full memory like a core dump. Never rename `.crash`/`.ips` to `core` and apply Linux commands.

**General lesson:** a core/dump must be read with a debugger that understands the matching **format + CPU architecture + OS ABI**, using binaries/symbols from the crashed build. Cross-architecture or cross-machine analysis is a **capability that must be verified**, not assumed by default.

## 11. Six Common Diagnostic Scenarios

| Symptom | Hypothesis to check | Verification steps |
|---|---|---|
| Have `core`, yet `jhsdb` fails to read VM | Wrong JDK/SA vendor/build, different `libjvm`, or core missing pages | Compare JDK build ID/hash, library mappings, format, and completeness |
| GDB opens core, yet native stack has many `??` | Missing debug symbols, mismatched library version, optimized code, or corrupted stack | `info sharedlibrary`, right rootfs/libs, build IDs/debuginfo, and `hs_err` |
| Core is ELF64 AArch64, tools run on x86-64 | Incompatible target architecture/tool | `readelf -h`, cross-target support; use an appropriate environment |
| Same `libjvm.so` name, yet stack jumps to nonsensical offsets | JDK binary was replaced by a newer deployment | Retrieve runtime image by **crash-time digest/hash**, not the new version |
| Process exited 137 in Kubernetes, no core | Cgroup/kernel OOM kill via `SIGKILL` | Pod last state, node logs, memory events, RSS/cgroup; do not wait for a core |
| `hs_err` exists, yet no core | Limits/policy, disk/permissions, systemd collector, or undumpable crash | `core_pattern`, `coredumpctl`, `ulimit/LimitCORE`, quota, dumpable flag |
| Core has data, yet `jhsdb jmap` misses a heap region | Mappings excluded from dump, truncated core, or corrupted VM memory | `coredump_filter`, check file size/collector, native maps |

**Scenario A — Same JDK major, different build.** The service ran `21.0.5+...`, and after the incident the team upgraded to `21.0.6+...`. Downloading `21.0.6` to analyze the old core can prevent SA from reading the layout. The right approach is to retrieve the `21.0.5` runtime **exact distribution/build and libraries** from the release artifact or container digest. If impossible, native GDB on the core may still yield some signals/threads, but you must clearly report the confidence limits.

**Scenario B — Embedded JVM.** The process is `/opt/app/native-launcher` calling the JNI Invocation API to create a JVM. `jhsdb --exe /opt/jdk/bin/java` can fail because that was not the executable that created the core. Use the matching `native-launcher` and the loaded JDK libraries.

**Scenario C — Core from a container.** The team copied only `core.1234` to the host, and GDB accidentally loaded the host's `/usr/lib/libc.so`. Native frames look bizarre. Fix: preserve the **original image/rootfs**, point GDB search paths to the right libs, and verify build IDs. Never assert a root cause while library mappings remain mismatched.

**Scenario D — Core after a native fault, yet Java heap histogram fails to build.** This does not necessarily mean “Java heap is empty”: SA may be incompatible, the dump may lack memory regions, or VM structures themselves may be corrupted. Prioritize `hs_err`, native backtrace, registers, artifacts, and an appropriate reproducer.

**Scenario E — Crash appears only on ARM.** Inspect the ARM64 image, JNI/native libraries, optimized intrinsic/JIT paths, and kernel/OS ABI. Never take an x86-64 binary built from the same source to analyze an ARM64 core and draw conclusions about the instruction pointer.

**Scenario F — Suspected native crash turns out to be an OOM kill.** Exit 137, no `hs_err`, no core. Check cgroup/OS events and OOM pressure first; if no core-producing signal occurred, there is no reason to ask `jhsdb` to read a nonexistent core file.

## 12. Security and Integrity of Core Dumps

Cores can contain **passwords, tokens, TLS keys, customer data, heap objects, URLs, session information, request payloads**, and anything currently in process memory. Before collecting or transferring:

1. Identify who is **authorized** to collect dumps and for what investigative purpose; follow incident/security procedures.
2. Use tightly restricted directories, encryption at rest and in transit, and bounded retention.
3. Record **SHA-256 hashes** and metadata to detect tampering; never edit or truncate a core and still treat it as original.
4. Avoid posting cores or `hs_err` files on public issue trackers or tickets; error logs can also contain command lines, environments, and paths.
5. Analyze in an isolated, authorized environment, working on a **copy**; never open arbitrary debugger ports on production.
6. Keep the artifact bundle in a reproducible form only as long as policy permits; destroy securely once no longer needed.

Core files can be huge. Before enabling bulk collection, budget disk space, storage quotas, and retention; repeated crashes can fill filesystems if left unchecked.

## 13. Concise, Repeatable Postmortem Workflow

**Phase A — Verify the incident**

1. Determine whether it was a **fatal JVM/native crash** vs. a Java exception, normal shutdown, or `SIGKILL`/OOMKill.
2. Collect `hs_err`/OS signal/exit code, timestamp, PID/TID, host/pod, JDK build, image digest, and application logs/JFR.
3. Confirm whether a core/dump was actually created, which collector holds it, and whether you have access permissions.

**Phase B — Lock down artifact accuracy**

4. Back up the core, **real executable**, JDK runtime (including `libjvm`), native libraries, and matching debug symbols.
5. Record checksums; verify core format/architecture; cross-check version/vendor/build/OS ABI and library build IDs.
6. Check for signs of truncated cores, missing files, or permission/sparse/filtered mappings.

**Phase C — Choose tools at the right layer**

7. Use `hs_err` to identify the problematic frame/signal/VM and suspect libraries.
8. On Linux, use **GDB** with matching binaries/libs to inspect native crashes; use **`jhsdb` with `--exe --core`** to try reconstructing Java/HotSpot state when tool versions support it.
9. If symbols or SA mismatch, fix **artifact/tool compatibility** before drawing conclusions from stacks or heap.

**Phase D — Find root cause and verify**

10. Distinguish the faulting site from where memory corruption or an invariant violation happened earlier.
11. Build a reproducer test case in an isolated environment; check JNI/library/JVM patch release notes if a native bug is suspected.
12. Write **conclusions with confidence levels**, verified files/symbols, and core limitations; never say “root cause confirmed” from a single frame alone.

### Mistakes to avoid

- **“A core alone is enough; the executable isn't needed.”** Wrong: debuggers generally need the binary and libraries to map memory/addresses back to code.
- **“Same Java 21 guarantees compatibility.”** Wrong: vendor, patch, build, architecture, and HotSpot layout can still differ.
- **“Using the newest `java` to debug an old core is better.”** Not necessarily, and it can cause severe SA mismatches.
- **“`file core` recognizes ELF64 so the core is complete.”** Wrong: the header does not prove every page was saved.
- **“`hs_err` and `core` hold the same contents.”** Wrong: one is a text fatal-error report; the other is a memory/process snapshot.
- **“GDB prints `??` so the JVM had no stack.”** Wrong: usually caused by symbol/library mismatch or missing debug info, or sometimes corruption.
- **“No core means no crash.”** Wrong: limits, handlers, dumpable flags, disk, signal type, or retention can all prevent a core.
- **“Analyze an `.hprof` heap dump like an ELF core.”** Wrong: different format, scope, and tools.
- **“Native `gdb` alone is enough to understand all Java objects.”** Wrong: GDB does not natively understand the HotSpot object model; a compatible SA is needed.
- **“Cores can be shared freely because they only contain stack traces.”** Wrong: cores can contain secrets and personal data.
- **“Seeing `libjvm.so` in the fault frame proves a HotSpot bug.”** Wrong: earlier JNI errors or memory corruption can trigger a fault inside the VM.

### Self-check

1. If a process running JDK `21.0.5` crashed, yet the server just upgraded to JDK `21.0.6`, which files/versions must you recover before running `jhsdb`?
2. Why might `gdb` open a core yet fail to print full names of native frames?
3. Why might `jhsdb`'s `--exe` not be `bin/java` for an application using the JNI Invocation API?
4. Given an x86-64 ELF core and an ARM64 executable, which tool detects the mismatch?
5. Why do exit code 137 or a Java `OutOfMemoryError` not automatically guarantee a core dump?
6. How do `hs_err_pid*.log`, `.hprof`, `.jfr`, and `core` answer different questions?
7. If a core was extracted from a container, why can the analysis host's libc/native libraries lead to wrong conclusions?
8. When transferring a core to an external support team, which steps protect both data integrity and confidentiality?

## References

- [Oracle Java SE 21 — `jhsdb` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html): `--exe`/`--core`, `jstack`/`jmap`/`jinfo` modes, and experimental status.
- [Oracle Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jhsdb` with cores, mixed Java/native stacks, and postmortem tools.
- [Oracle Java SE 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): collecting cores, fatal error logs, and artifacts to retain.
- [Linux `core(5)` — man-pages](https://man7.org/linux/man-pages/man5/core.5.html): core limits, `core_pattern`, filtered mappings, and `systemd-coredump`.
- [GDB Manual — Executable and Core Files](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Files.html): how GDB uses binaries, cores, symbols, and sysroot/shared-library search paths.
- [GDB Manual — Core File Generation](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Core-File-Generation.html): cores as memory/process status snapshots and `gcore` in authorized contexts.
