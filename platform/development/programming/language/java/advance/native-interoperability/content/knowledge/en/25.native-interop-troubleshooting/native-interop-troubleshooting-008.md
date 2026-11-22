# Collecting Dump Files, Debug Symbols, and Library Information to Reproduce JNI/Native Incidents

## 1. Why Is It Necessary to Collect All Three Evidence Groups?

Incidents at the Java ↔ native code boundary are often hard to reproduce because many layers are involved: Java bytecode, JIT code, JNI or FFM, C/C++ libraries, system libraries, the operating system's dynamic loader, and the JVM itself. A report that only says "`SIGSEGV` in `libfoo.so`" is usually not enough to find the root cause.

A good evidence bundle must simultaneously answer:

1. **What happened at the time of failure?** → HotSpot fatal-error log, **OS core/minidump**, thread call stacks, signal/exception, registers, memory mappings.
2. **Which function and source line do the machine addresses correspond to?** → **debug symbols** matching the exact binary: DWARF/ELF on Linux, dSYM on macOS, PDB on Windows; if missing, the stack may only show addresses or `??`.
3. **Which exact version of the library was loaded?** → actual deployed binary file, build ID/UUID/GUID, hash, ABI, dependent libraries, JDK and OS, load path, JVM options.

Only **dump + symbols + binaries/metadata from the same build** allow a specialist to translate machine addresses into a stack with function names/source lines and replay the incident in an equivalent environment. A dump file does not contain the full source code on its own, a symbol file does not replace a dump, and two builds of `libfoo.so` with the same name but from different builds **must not be mixed**.

### Distinguish Dump Types From the Start

| Symptom | Priority Evidence | Do Not Confuse With |
| --- | --- | --- |
| JVM dies due to `SIGSEGV`, `SIGABRT`, `EXCEPTION_ACCESS_VIOLATION`, or fatal error | `hs_err_pid<pid>.log` + OS core/dump + native symbols + binary identity | `.hprof` only describes the Java heap, not the entire process |
| `java.lang.OutOfMemoryError` / suspected Java heap leak | `.hprof`, GC logs, JFR, heap histogram, memory metrics | Not every OOME crashes the JVM or produces an OS core |
| Application hangs, deadlock, stuck JNI call | Multiple **thread dumps** spaced over time, JFR, native thread stacks | Thread dumps do not contain full register/stack memory like an OS core |
| Library failed to load: `UnsatisfiedLinkError` | Java stack trace, library name, search paths, ABI/dependency, version | A core dump is not necessarily needed because the process is still running |
| Wrong results / data corruption after JNI | Minimal input, expected/actual results, logs + sanitizers/`-Xcheck:jni` | An address in a core does not immediately identify the earlier invalid write |

**Timing priority:** collect artifacts that are lost when the process exits before restarting or redeploying: `/proc/<pid>/maps`, launch command, library state, and thread dumps; after a crash, collect `hs_err` and OS core/dump. Keep a read-only original copy before creating a sanitized copy with sensitive data redacted for sharing.

## 2. Starting the JVM With Intentional Diagnostic Data

Example on Linux, with a writable path and sufficient disk space:

```bash
mkdir -p /var/tmp/jvm-diag
# Run inside the application's own launcher/service:
java -XX:ErrorFile=/var/tmp/jvm-diag/hs_err_pid%p.log \
     -XX:+CreateCoredumpOnCrash \
     -jar app.jar
```

- `-XX:ErrorFile=...` specifies where to save the **HotSpot fatal error log**; `%p` expands to the PID, avoiding overwrites across incidents. If this flag is not set, HotSpot typically attempts to create `hs_err_pid<pid>.log` in the working directory and falls back to the temporary directory if it cannot write there.
- `-XX:+CreateCoredumpOnCrash` tells HotSpot to allow creating a core/minidump on a fatal error. On many HotSpot builds this flag is already enabled by default; **a JVM flag cannot override** kernel, service manager, container, permission, or disk space limits. Check the actual flags for the JDK build in use.
- `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/jvm-diag` is a configuration **specifically for heap dumps on OOME**. Do not confuse it with an OS core for a `SIGSEGV`.
- `-Xcheck:jni` increases checking for JNI calls that violate the contract (references, `JNIEnv` on the wrong thread, pending exceptions...). It is valuable in a reproduction environment, but adds overhead, changes timing, and does not detect every memory corruption bug.

If running on JDK 24+ and JNI operations have not been granted permission, handle native access warnings separately according to the JDK version's policy. A native access warning **does not mean** a crash and cannot be replaced by collecting a core dump.

### If the Process Is Still Alive

Collect metadata **before stopping/restarting**, using the exact account that can attach to the JVM:

```bash
PID=12345  # Replace with the actual PID of the Java process
jcmd "$PID" VM.command_line > jvm-command-line.txt
jcmd "$PID" VM.flags > jvm-flags.txt
jcmd "$PID" VM.info > jvm-info.txt
jcmd "$PID" Thread.print -l > threads-1.txt
sleep 5
jcmd "$PID" Thread.print -l > threads-2.txt

readlink -f "/proc/$PID/exe" > java-executable.txt
cp "/proc/$PID/maps" proc-maps.txt
cp "/proc/$PID/limits" proc-limits.txt
cat /proc/sys/kernel/core_pattern > core-pattern.txt
```

`jcmd` requires the same host and appropriate permissions for the JVM; container PID namespaces, attach policies, and different users can prevent the tool from finding or attaching to the process. In memory mappings, `/proc/PID/maps` shows which libraries are mapped into the process at the time of reading. Once the process dies, `/proc/PID/...` paths no longer exist. Also collect application logs, timestamps with timezones, time of failure, and deployment ID to correlate by PID.

With JFR already enabled: `jcmd "$PID" JFR.dump filename=/var/tmp/jvm-diag/before-crash.jfr` can capture a recording before restarting. Check commands supported by the target JVM with `jcmd "$PID" help`. If recording was not enabled beforehand, you cannot "retroactively recover" past JFR data.

**Limitation:** a `jcmd` command may fail if the JVM has already crashed, is hung, or has attach disabled. Do not interpret an attach failure as evidence that the Java heap or native code is at fault.

## 3. Linux: Finding, Retrieving, and Verifying an OS Core Dump

### 3.1. Understanding Where the Kernel Writes Core Files

Key check points:

```bash
ulimit -c
cat /proc/sys/kernel/core_pattern
cat /proc/sys/kernel/core_uses_pid
```

- `ulimit -c 0` can prevent file-based core creation; to enable it for **child processes of the reproduction shell**, run `ulimit -c unlimited` before the `java` command. This value does not automatically change the limit of an already running systemd service.
- If `core_pattern` starts with the `|` character, the dump is piped to a **handler** (such as `systemd-coredump`), and does not by default become a `core` file in the current directory.
- For systemd services, check `LimitCORE`, `systemd-coredump` configuration, `Storage` and `ProcessSizeMax`, permissions, and quotas. Do not change host-wide sysctl settings just to test a single application.
- In Docker/Kubernetes, dumps are also subject to host kernel configuration, container runtime, storage mounts, namespaces, and access to the host's handler. A container with `ulimit -c unlimited` may still fail to save a core if the host does not capture it.

If the system uses `systemd-coredump`, check as follows:

```bash
coredumpctl list java
coredumpctl info 12345
coredumpctl dump 12345 --output=core.java.12345
```

Here `12345` is the PID from the fatal-error log/incident (replace with the actual value); if multiple incidents share the same PID due to PID reuse, also cross-check timestamp, executable, and boot ID. `coredumpctl info` can list an entry even if the core file has already been deleted due to retention or lacks read permissions. A `truncated`/`missing`/`error` status does not yield a complete dump for analysis. If not using systemd, look for the file according to `core_pattern` and the host's core collection policy.

After obtaining the file, verify it with:

```bash
file core.java.12345
ls -lh core.java.12345
sha256sum core.java.12345
```

The resulting file must correspond to the crash and architecture to be analyzed; a 0-byte or truncated core cannot be used as a full core. Do not guess the dump location just from the name `core`, because the OS may rename it or route it to a service handler.

### 3.2. Analyzing Native Call Stacks With GDB

You need the `java` executable and shared libraries **matching the build at the time of the crash**. On a diagnostic machine with `gdb` and matching symbols:

```bash
gdb --batch \
  -ex "set pagination off" \
  -ex "info sharedlibrary" \
  -ex "info threads" \
  -ex "thread apply all bt full" \
  /path/to/same-jdk/bin/java /path/to/core.java.12345 \
  > gdb-backtrace.txt
```

From the output, locate the thread that raised the signal, the top of the stack, JNI frames, application library functions, any `??` symbols, and other threads holding mutexes/resources. `info sharedlibrary` shows whether GDB has loaded library information and symbols. You can open interactively with `gdb /path/to/java /path/to/core` and then use `thread <N>`, `bt full`, `frame <N>`, `info locals` when appropriate debug info is available.

Use Serviceability Agent to attempt getting HotSpot's **Java + native** view:

```bash
jhsdb jstack --exe /path/to/same-jdk/bin/java \
             --core /path/to/core.java.12345 --mixed \
  > mixed-stacks.txt
```

`jhsdb` depends on the JVM version, architecture, a complete core, and the relevant native libraries; it is not guaranteed to handle every dump. If the tool reports a JVM mismatch, bring the **exact JDK distribution/build** into the analysis environment rather than decoding the core with another JDK just because it shares the same major version. When `.debug`/`debuginfo` for `libjvm.so` or native libraries is missing, some frames will lack function names/source lines.

## 4. Windows: WER/ProcDump, PDB, and WinDbg

On Windows, OS user-mode crash dumps typically have the `.dmp` extension, unlike Java heap dumps `.hprof`.

**Windows Error Reporting (WER) LocalDumps:** configured per executable, for example via registry key:

```text
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\java.exe
    DumpType   REG_DWORD       2
    DumpCount  REG_DWORD       5
    DumpFolder REG_EXPAND_SZ   C:\jvm-dumps
```

`DumpType=2` requests a full user-mode dump, `1` is a minidump. Create the folder beforehand, grant write ACLs to **the account running the process**, ensure sufficient disk space, and configure with administrator privileges per machine policy. A key under `java.exe` applies to all processes with that executable name, so consider the impact across multiple applications; custom application-server launchers may use a different executable. WER is not enabled by default for every crash, and some crash handlers/postmortem debuggers can affect WER dump collection.

With **Sysinternals ProcDump**, you can attach to a specific PID and request a full dump on an unhandled exception:

```powershell
procdump.exe -accepteula -ma -e 12345 C:\jvm-dumps
```

Here `12345` is the actual PID; `-ma` is a full dump, `-e` monitors for unhandled exceptions; depending on the JVM's exception handling flow, the trigger may not produce the expected file. Also collect `hs_err_pid*.log` when present and verify the dump actually appears. Avoid using the "first-chance" `-e 1` trigger indiscriminately with the JVM, as it can easily produce many very large dumps.

Open the dump in **WinDbg**, configure the Windows symbol server and internal PDB paths matching the build:

```text
.symfix C:\symbol-cache
.sympath+ C:\secure-pdbs
.reload /f
lm
.ecxr
k
!analyze -v
```

The commands above are **commands inside WinDbg**, not typed directly into PowerShell. `lm` lists DLLs; `lmvm <module>` shows details for a module; `.ecxr` switches to the exception context when the dump contains an exception record. The PDB must match the **GUID + Age** of the DLL/EXE, not just have the same filename `foo.pdb`. Keep the exact runtime DLLs, corresponding PDBs, and Windows/JDK versions.

## 5. macOS: Crash Report, Core, and dSYM

On macOS, the system may write **`.ips` crash reports** under `~/Library/Logs/DiagnosticReports/` or a location configured by system administrators. This report typically contains the exception, binary images, UUID, and backtrace, and **is not a full core**. If a core is available and LLDB supports reading it:

```bash
lldb -c /path/to/core /path/to/java
```

Inside LLDB:

```text
(lldb) thread backtrace all
(lldb) image list
(lldb) image lookup --address 0xADDRESS
```

`0xADDRESS` is an actual address in the debug session and must be replaced with the real value from the dump; these commands only illustrate LLDB usage. Collect the matching `.dylib` files along with their `.dSYM` bundles and source code from the same commit. Match by UUID rather than relying on file name:

```bash
dwarfdump --uuid /path/to/libfoo.dylib
dwarfdump --uuid /path/to/libfoo.dylib.dSYM
```

Core dumps on macOS also depend on crash reporting policies, permissions, limits, and OS storage locations. When only `.ips` is available, use the UUID/binary images to symbolicate with the appropriate macOS tools; do not call it a full memory dump.

## 6. Storing Debug Symbols and Identifying the Exact Native Library

### 6.1. What Does "Having Debug Symbols" Mean?

| Platform | Deployed File | Debug Information to Keep | Identification Key |
| --- | --- | --- | --- |
| Linux/ELF | `libfoo.so`, `java`, `libjvm.so` | DWARF inside binary or separate `.debug` file/debuginfo package | ELF **Build ID** and/or `.gnu_debuglink` (CRC); hash of deployed binary |
| Windows/PE | `foo.dll`/`java.exe` | Corresponding **PDB** | PDB **GUID + Age** and DLL/EXE hash |
| macOS/Mach-O | `libfoo.dylib`, executable/framework | **dSYM** bundle or matching DWARF | Mach-O **UUID** for the exact architecture slice |

**It is impossible to reconstruct symbols for a stripped build if you no longer have the unstripped binary, separate debug file, or original CI artifacts.** Even the same semantic version, same commit, or same library name does not guarantee the same build: compiler, flags, link order, and dependencies can change the address layout.

On Linux, when building a JNI library, generate debug information and a build ID; for example:

```bash
gcc -g -O2 -fno-omit-frame-pointer -fPIC -shared \
    -Wl,--build-id -o libfoo.so foo.c

# Keep the debug file before stripping the deployed binary:
objcopy --only-keep-debug libfoo.so libfoo.so.debug
strip --strip-debug libfoo.so
objcopy --add-gnu-debuglink=libfoo.so.debug libfoo.so

readelf -n libfoo.so
sha256sum libfoo.so libfoo.so.debug
```

This is a **build workflow template** for plain C source; real JNI also requires including JDK headers and possibly linking dependent libraries. In CI, store `libfoo.so.debug` separately alongside the **stripped** `libfoo.so` that was actually released. GDB can locate debug files via `.gnu_debuglink`, Build ID, or `debuginfod`; configure the symbol storage location and access restrictions appropriately.

When receiving an incident, collect identity evidence:

```bash
file /opt/app/lib/libfoo.so
readelf -n /opt/app/lib/libfoo.so
readelf -d /opt/app/lib/libfoo.so
nm -D /opt/app/lib/libfoo.so
sha256sum /opt/app/lib/libfoo.so
java -version
uname -a
```

- `readelf -n`: if the toolchain emits a build ID, record that exact value.
- `readelf -d`: `NEEDED` entries show direct dependencies declared by the ELF; they do not confirm which dependency version the dynamic loader selected at runtime.
- `nm -D`: inspects dynamic/exported symbols, which does not mean full line numbers are present.
- `sha256sum`: fingerprint of the **deployed file**; the file hash in a newer image may differ from the one mapped in an older process after a rolling update.
- `java -version`/`uname -a`: a starting point; you must also collect JDK vendor/build, architecture, libc/musl/glibc, and container image version.

You may inspect `ldd` on a **trusted** library to check resolution, but it reflects the **environment where you run the check** and may not match the runtime at the time of the incident; for untrusted binaries, prefer static inspection with `readelf -d`. If the application uses `dlopen`/`System.load`, many libraries **are not listed in `DT_NEEDED`** and only appear in runtime mappings/loader traces.

### 6.2. ASLR and Address Symbolication

A line like `Problematic frame: C [libfoo.so+0x1a2b]` indicates a relative offset of a frame inside the library, but does not prove the bug belongs to that exact function or source line. With ASLR, **absolute runtime PCs** change across runs. The safest approach is to load the **exact core + binary + debug symbols** in GDB/LLDB and run `bt`, `info symbol`/`image lookup`.

If using `addr2line` manually on Linux:

```bash
addr2line -C -f -i -e /path/to/exact/libfoo.so.debug 0x1a2b
```

`0x1a2b` is only an **example**: you must convert a runtime PC into an address/ELF VMA matching the load bias and mapping of the actual binary before looking it up. Do not pass raw absolute addresses from `hs_err` directly to `addr2line` and trust the output; `??:0` usually indicates missing debug symbols or an incorrect address. Compiler optimizations, inlining, tail calls, and memory overwrites can also prevent an exact 1-to-1 match between backtrace and source line.

## 7. Reading `hs_err_pid` to Narrow Down the Root Cause

Start with these fields (field names and presence may vary across JVM versions):

- **Signal/exception**: `SIGSEGV`, `SIGBUS`, `SIGABRT`, `EXCEPTION_ACCESS_VIOLATION`; fault PC, PID, thread ID.
- **Problematic frame**: markers `C` (native C/C++), `V` (JVM code), `J` (JIT-compiled Java), `j` (interpreted Java), along with the library or method name.
- **Current thread / native frames / Java frames**: the JNI transition point, call chain, locks, thread state.
- **Dynamic libraries / memory mappings**: names, load addresses, library paths; used to verify versions and locations.
- **VM Arguments, System, Environment**: JDK build, flags, OS/CPU; these fields may contain sensitive information and may be incomplete if the error handler did not finish writing.

Example **illustrative excerpt**, not the output of the program run below:

```text
# SIGSEGV (0xb) at pc=0x..., pid=12345, tid=...
# Problematic frame:
# C  [libfoo.so+0x1a2b]
```

You can only conclude that the signal was recorded while executing a native frame belonging to `libfoo.so`. **You cannot yet conclude** that this library is the culprit: an out-of-bounds write in library A can corrupt the heap and crash later inside `malloc`/`free` or JVM code. Cross-check multiple cores, thread context, symbols, library versions, and a reproduction model.

You can enable `-Xcheck:jni` to catch certain JNI protocol violations when re-running, or compile the native library with **AddressSanitizer/UndefinedBehaviorSanitizer** in a compatible test build. Sanitizers and debug flags can alter memory layout/timing, so keep both a reproduction on the exact production binary and an instrumented reproduction.

## 8. Hands-On: Building a JNI Library, Collecting Symbols, and Deliberately Reproducing a Crash

This complete example runs on **Linux x86_64 or matching aarch64**, JDK 17+ with `gcc`/`binutils`. It has two modes: default **safe**, or `--crash` to deliberately raise `SIGSEGV`. **Only run crash mode in a lab machine/VM/container where killing the process is permitted; never run it in a production service.** An intentional signal only tests the dump collection pipeline and does not substitute for real memory corruption scenarios.

### Step A — `NativeIncidentLab.java`

```java
public final class NativeIncidentLab {
    static {
        System.loadLibrary("incidentdemo");
    }

    private static native int multiply(int left, int right);
    private static native void simulateSignal();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("result=" + multiply(6, 7));

        if (args.length == 1 && "--pause".equals(args[0])) {
            Thread.sleep(30000);
        } else if (args.length == 1 && "--crash".equals(args[0])) {
            System.out.flush();
            simulateSignal();
        }
    }
}
```

`--pause` keeps the JVM alive for 30 seconds to collect `/proc/PID/maps`/`jcmd`. `--crash` crosses into JNI to raise a signal; the default only computes 6 × 7.

### Step B — `NativeIncidentLab.c`

```c
#include "NativeIncidentLab.h"
#include <signal.h>

JNIEXPORT jint JNICALL Java_NativeIncidentLab_multiply(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void)env;
    (void)clazz;
    return left * right;
}

JNIEXPORT void JNICALL Java_NativeIncidentLab_simulateSignal(
        JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    raise(SIGSEGV);
}
```

`raise(SIGSEGV)` is a deliberate action to test the capture pipeline; the immediate frame raising the signal may be in libc, while `Java_NativeIncidentLab_simulateSignal` sits deeper in the backtrace. Therefore, looking only at `Problematic frame` can mislead you into thinking "libc has a bug".

### Step C — Build With Debug Symbols

```bash
# Run in the directory containing both source files:
javac -h . NativeIncidentLab.java
gcc -g -O0 -fno-omit-frame-pointer -fPIC -shared \
    -Wl,--build-id \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -o libincidentdemo.so NativeIncidentLab.c

file libincidentdemo.so
readelf -n libincidentdemo.so
sha256sum libincidentdemo.so
```

`javac -h` generates `NativeIncidentLab.h` so that C-side JNI signatures match Java. `JAVA_HOME` must point to the JDK containing `include/jni.h`. `-g` generates DWARF, `-O0` makes source lines easy to observe in the lab; `-fno-omit-frame-pointer` assists stack unwinding. The standard GNU linker generates a Build ID with the specified flag.

### Step D — Safe Run, Verify Stdout

```bash
java -Djava.library.path="$PWD" NativeIncidentLab
```

**Exact stdout** (excluding any JVM warnings on stderr):

```text
result=42
```

On JDK 24+, to suppress native access warnings unrelated to this lab, you can add `--enable-native-access=ALL-UNNAMED` to the `java` command because the class is on the classpath. On JDK 17–23 do not use this flag.

### Step E — Proactively Collect Data Before a Crash

```bash
mkdir -p artifacts
java -Djava.library.path="$PWD" NativeIncidentLab --pause &
PID=$!

# Run within 30 seconds before the process exits:
cp "/proc/$PID/maps" artifacts/proc-maps.txt
cp "/proc/$PID/limits" artifacts/proc-limits.txt
jcmd "$PID" VM.command_line > artifacts/jvm-command-line.txt
wait "$PID"
```

The commands may require attach permissions; the PID/namespace must point to the running Java process. When the 30 seconds elapse, Java exits normally; this is the **pre-incident data collection** step and does not create a core yet.

### Step F — Lab Environment Only: Trigger the Crash and Capture the Dump

```bash
ulimit -c unlimited
java -XX:+CreateCoredumpOnCrash \
     -XX:ErrorFile="$PWD/artifacts/hs_err_pid%p.log" \
     -Djava.library.path="$PWD" \
     NativeIncidentLab --crash
```

Stdout before the crash is still:

```text
result=42
```

The process then terminates abnormally; the exit code, stderr, `hs_err` filename, and core existence/location depend on signal handling and OS configuration. **Do not assume a core is always produced.** Check `artifacts/hs_err_pid*.log` and `coredumpctl` or `core_pattern`; if a core exists, copy it into `artifacts/` and use GDB/`jhsdb` as in Section 3. A library compiled with `-g` will allow recognizing `Java_NativeIncidentLab_simulateSignal` in the native stack when the dump has sufficient information.

To prove the symbols pipeline works: read the Build ID of the built `libincidentdemo.so`, store it alongside the core, open the exact Java executable and dump in GDB, and verify that the `simulateSignal` frame is present. Do not rely on the PC addresses, PIDs, or frame numbers in examples because they differ across runs.

## 9. Handoff-Ready Incident Reproduction Package

A useful "incident bundle" should have clear structure and linkage:

```text
incident-12345/
├── repro.md                 # timestamp, how to run, input, expected/actual
├── hs_err_pid12345.log      # protected original copy
├── core.java.12345          # Linux core (or crash.dmp on Windows)
├── native-backtrace.txt     # gdb/lldb/windbg; verified contents
├── java-threads.txt         # jcmd/jhsdb, if collected
├── proc-maps.txt            # pre-crash mappings, if collected
├── jvm-flags.txt
├── os-and-jdk.txt
├── binaries/
│   ├── libfoo.so            # exact deployed build, not a rebuild
│   └── build-info.txt       # SHA-256, Build ID, architecture, dependencies
├── symbols/
│   └── libfoo.so.debug      # matches Build ID or debuglink
└── SHA256SUMS               # hashes of artifacts actually present
```

At a minimum, `repro.md` should record: date/time and timezone; host/container image **digest**; release commit/build pipeline ID; full JDK version (vendor/update/build/architecture); kernel/OS and libc; command line + relevant JVM flags (secrets redacted); minimal input/seed/data shape; thread count; system load and loop conditions; expected/actual results; step-by-step 1–2–3 run instructions; reproduction rate (e.g., 3/10 times); success criteria for reproduction; artifact links and checksums.

Separately record the **reproduction level**:

- *Reproduced*: actually re-ran the same trigger and observed consistent symptoms.
- *Matched signature*: not directly reproduced, but stack/signal/build evidence matches the incident.
- *Not yet reproduced*: only hypotheses exist or symbols do not match yet; must not report root cause found.

To hand off to another team, provide a list of files **actually present**, explicitly stating which files are missing and why (kernel core disabled, truncated dump, different JDK build, attach permissions, lost symbol files). Hashes help detect if the bundle was altered in transit.

## 10. QA Checklist and Very Common Mistakes

| Symptom / Mistake | Why It Is Dangerous | How to Check / Fix |
| --- | --- | --- |
| Keeping only `hs_err`, no core | Lacks registers/memory/state to prove native memory corruption | Set up core capture before a crash, verify `core_pattern`/handler/limits, or state clearly that core is unavailable |
| Only `.hprof` for a `SIGSEGV` | `.hprof` does not contain full native stacks and mapped memory | Collect OS core/dmp; only use heap dump if Java objects also need investigation |
| `gdb` shows `??`, `No debugging symbols found` | Stripped binary or missing DWARF file for the exact build | Verify Build ID, `.gnu_debuglink`, symbol directory/`debuginfod`; retrieve from CI artifacts |
| Stack trace matches names but has wrong addresses | Using a same-named library with a different binary/ABI, or subtracting ASLR load bias incorrectly | Compare hashes, Build ID/UUID/PDB GUID+Age, and exact process mappings |
| `UnsatisfiedLinkError` during reproduction | Missing library, wrong loader path/ABI/transitive dependencies | Check `System.loadLibrary`, `java.library.path`, ELF NEEDED, architecture, container base image |
| `hs_err` points to `libc`/`libjvm` | The crash site is not necessarily where memory was corrupted | Analyze all thread stacks and failure timing; try `-Xcheck:jni`/sanitizers in a lab |
| Changing JVM, GC, compiler flags, and libc all at once | Cannot isolate which variable made the bug disappear/appear | Keep a baseline with the exact original artifacts, changing **one variable at a time** |
| Taking only one thread dump of a hung process | Hard to tell progress/deadlock/blocked JNI | Collect 2–3 samples spaced over time, recording timestamps/stacks together |
| Core file is tiny or reported `missing` | Retention, quota, dump filter, permissions, or truncation | Check `coredumpctl info`, resource limits, storage, and size before analyzing |
| Sharing cores/logs publicly | Dumps can contain tokens, user data, keys, and sensitive memory regions | Keep originals in an ACL-protected store; only send approved copies/channels with proper retention and encryption |

**Acceptance criteria:** a verifiable way to rerun or trigger conditions; recorded JDK/OS/dependency versions; clear hash/build identity of native binaries; symbols matching the build; dump/log artifacts with timestamps tied to PID; symbolicated native + Java stack report when feasible; all gaps listed; sensitive data controlled.

### Self-Check Questions

1. An `.so` and `.debug` have the same name but different Build IDs. Can they be used to find the faulty line? **No**: you must obtain symbols from the same build.
2. `hs_err_pid` reports `C [libbar.so+0x1234]`. Is that enough to prove the bug is in `libbar.so`? **Not yet**: memory corruption may have occurred earlier in another library.
3. `-XX:+CreateCoredumpOnCrash` is enabled, yet there is no `core` file in the working directory. What should you check? **`ulimit`/service limits, `core_pattern`, systemd handler, permissions, quotas, container/host policy**, and `coredumpctl`.
4. A process is hung and you need to observe progress; what should you collect before restarting? **Multiple thread dumps over time**, JFR, and runtime mappings if obtainable.
5. The deployed binary is exact, yet `addr2line` still shows `??`. What causes must be ruled out? **Missing or mismatched symbols, wrong ELF VMA/load bias address, stripped file, compiler optimizations**.

## 11. Standard Reference Documentation by OS and Version

- [Oracle JDK Troubleshooting Guide — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-system-crashes.html) — `hs_err`, fatal frame, JNI native crash.
- [Oracle JDK Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) and [`jcmd` Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — live diagnostics, thread/JFR/heap dump.
- [`jhsdb` Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jhsdb.html) — reading Java/native stacks from a core.
- [Inside Java — Failed to write core dump](https://inside.java/2021/04/30/failed-writing-core-dump/) — `CreateCoredumpOnCrash` and OS barriers.
- [systemd coredumpctl](https://www.freedesktop.org/software/systemd/man/latest/coredumpctl.html) — listing and extracting Linux cores.
- [GNU GDB — Separate Debug Files](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Separate-Debug-Files.html) — Build ID, `debuglink`, and `debuginfod`.
- [Microsoft — Collecting User-Mode Dumps](https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps) and [Sysinternals ProcDump](https://learn.microsoft.com/en-us/sysinternals/downloads/procdump) — Windows `.dmp`/WER.
- [LLDB command map](https://lldb.llvm.org/use/map.html) — threads, images, symbols in LLDB.

When reproducing a JNI/native bug, treat **the running binary**, **matching debug symbols**, and **runtime traces at the time of failure** as three parts of a single piece of evidence. Only when they are linked by build identity, timestamp, PID, and concrete reproduction steps can a crash be reliably analyzed and verified.
