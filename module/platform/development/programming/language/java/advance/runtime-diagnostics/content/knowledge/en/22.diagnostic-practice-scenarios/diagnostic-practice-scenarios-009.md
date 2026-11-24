# 22.9 Reading a Sample Fatal Error Log and Classifying Evidence Still Needed

## Objective

In practice, a Java process suddenly disappearing can result from an unhandled Java exception, a HotSpot **fatal error**, buggy native/JNI code, an OS `SIGKILL`, or a container `OOMKilled`. When you find an `hs_err_pid*.log` file, the question is not just "where is the `Problematic frame`?" but also: **which facts are already confirmed, which hypotheses are under consideration, and what evidence is still missing to prove the root cause?**

This integrated practice lab walks through reading a **simulated fatal error log** in proper sequence, filling out an assessment sheet, and cataloging the artifacts to collect before drawing conclusions.

After this lesson, you will be able to:

1. Read `SIGSEGV`, `pc`, `pid/tid`, `Problematic frame`, `Current thread`, `Native frames`, `Java frames`, `VM Arguments`, and `Dynamic libraries`.
2. Distinguish **`C`/`V`/`v`/`J`/`j`** frame markers; never confuse **running JIT-compiled code** with a **compiler thread actively compiling**.
3. Classify statements into **OBSERVED** (directly seen in evidence), **INFERRED** (plausible hypothesis), and **UNKNOWN** (not yet backed by evidence).
4. Prioritize missing evidence as **P0/P1/P2**, identifying collection sources and verification questions.
5. Formulate a safe triage/reproducer/A-B plan while documenting limitations and access controls, without ever trying to provoke crashes in production.

Scope is **HotSpot/OpenJDK 17+ on Linux**. On Windows, macOS, other JVM vendors, or other JDK updates, headers, signals, frames, or library names may differ. **Logs, PIDs, timestamps, libraries, and all paths in this example are completely simulated**; never cite them as evidence from a real incident.

## 1. Scenario: Image Decoding Service Restarts Abnormally

A service `demo.ImageServer` calls a native image-decoding library over JNI. After a new input request, the process restarts. In the crash directory, a simplified **excerpt** `hs_err_pid7312.log` remains for practicing log reading.

### 1.1. Sample Fatal Error Log

```text
#
# A fatal error has been detected by the Java Runtime Environment:
#
# SIGSEGV (0xb) at pc=0x00007f5a100013d1, pid=7312, tid=7318
#
# JRE version: OpenJDK Runtime Environment (17.x, illustrative build)
# Java VM: OpenJDK 64-Bit Server VM (17.x, mixed mode, linux-amd64)
#
# Problematic frame:
# C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
#
# Core dump will be written. Default location: /var/crash/core.7312
#
---------------  T H R E A D  ---------------
Current thread: JavaThread "decode-io-3" [_thread_in_native, id=7318]

siginfo: si_signo: 11 (SIGSEGV), si_code: 1 (SEGV_MAPERR),
         si_addr: 0x0000000000000000

Native frames: (J=compiled Java code, j=interpreted,
                Vv=VM code, C=native code)
C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
C  [libatlascodec.so+0x1014] codec_unpack+0x24
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0
v  ~StubRoutines::call_stub

Java frames: (J=compiled Java code, j=interpreted, Vv=VM code)
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0

---------------  P R O C E S S  ---------------
VM Arguments:
jvm_args: -Xmx512m -XX:ErrorFile=/var/crash/hs_err_pid%p.log
java_command: demo.ImageServer

Dynamic libraries:
0x00007f5a10000000-0x00007f5a10005000 /opt/app/native/libatlascodec.so
0x00007f5a20000000-0x00007f5a23000000 /opt/jdk/lib/server/libjvm.so

---------------  S Y S T E M  ---------------
OS: Linux x86_64 (illustrative)
CPU: x86_64 (illustrative)
#
```

**How to read this sample:** this is purely a **teaching excerpt** with several sections abbreviated; do not call it a complete `hs_err` file. In the sample, `pc` is set inside the memory mapping starting at `0x00007f5a10000000` plus offset `0x13d1` in `libatlascodec.so`. That address is fictional data, not an identified function/source line in a real binary. The line "Core dump will be written" states intent; **do not claim a core file exists** until verified on the filesystem/core handler.

## 2. Reading the Header: Record Only What Appears

| Signal in Log | What You Can State | What You Cannot State Yet |
| --- | --- | --- |
| `SIGSEGV (0xb)` | Linux reported a segmentation violation at an instruction in the process | Does not automatically prove a Java `NullPointerException` or a JVM bug |
| `pc=0x00007f5a100013d1` | Program counter/instruction pointer when the fault occurred | Not a Java object address or decoded source line |
| `pid=7312` | JVM PID at crash time | Might not match host PID if running inside a PID namespace |
| `tid=7318` | Native thread that encountered the fatal error | Do not use Java's `Thread.getId()` to infer OS TID directly |
| `OpenJDK 17.x` | Runtime family/architecture of the sample | Insufficient exact vendor/JDK patch/build to match known bugs |
| `C [libatlascodec.so+0x13d1]` | Faulting instruction in native frame belongs to a shared library | Does not yet prove the library caused the original corruption |
| `Core dump will be written` | Error reporter intended to write a core at the printed path | Does not confirm the core exists, is readable, or matches this exact crash |

### 2.1. `siginfo` and `si_addr`

`SEGV_MAPERR` typically indicates the program accessed an unmapped address. `si_addr=0x0` suggests a near-null/null address access in native code, yet **does not mean you have located the exact buggy pointer**. To know which address the instruction read or wrote, inspect **registers, disassembly, memory mappings, and the native core**.

`SIGBUS`, `SIGILL`, `SIGFPE`, or `Internal Error` lead down different investigation branches; the signal name only describes the detected fault class. An `Internal Error` from a HotSpot assertion/guarantee can have a different header and need not involve a regular OS signal.

### 2.2. The `-Xmx512m` Line Is Not a Diagnosis

`-Xmx512m` configures the Java heap limit, not total process native memory. A fatal `SIGSEGV` inside a C/C++ library differs from `OutOfMemoryError: Java heap space`. Never propose raising heap without evidence of heap pressure or related conditions.

## 3. `Problematic frame`: Distinguishing the Markers

Read uppercase and lowercase letters accurately:

| Marker | Meaning in HotSpot Fatal Log | Priority Verification Step |
| --- | --- | --- |
| **`C`** | Native code in an application/vendor/JDK/OS library | Verify module, binary/build, JNI callers, native symbols/core |
| **`V`** | HotSpot VM code, such as runtime, GC, or compiler implementation | Inspect current thread, `VM_Operation`, `Current CompileTask`, callers, and memory corruption |
| **`v`** | VM-generated stub/adapter code | Inspect adjacent frames and registers/native transition |
| **`J`** | Compiled Java code, machine code generated by the JIT | Identify method/tier and reproduction conditions; check JNI/agents before blaming a JIT bug |
| **`j`** | Interpreted Java method | Never call `j` JIT-compiled code; read the full stack/transition |

**Strongest rule:** the marker identifies **where the faulting instruction executed**, not necessarily **where state was corrupted**. For example, a JNI buffer overflow can trigger a crash later in `V [libjvm.so]` when GC reads a reference; a VM/JIT bug can also manifest inside compiler runtime. Neither `C`, `V`, nor `J` alone confirms the root cause.

In the sample log, `C` is a sensible starting point for investigating the native library, **not a verdict proving the codec library has a bug**.

## 4. Reading `Current thread` and Stacks to Link Java to Native

In the sample:

```text
Current thread: JavaThread "decode-io-3" [_thread_in_native, id=7318]

Native frames:
C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
C  [libatlascodec.so+0x1014] codec_unpack+0x24
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0
```

These clues point together toward **the Java → native codec decoding path**:

1. `Current thread` is named `decode-io-3` and is in `_thread_in_native`.
2. Two `C` frames lie inside the same native library, including a function named like a JNI entrypoint.
3. The `j` frames show Java callers (in this sample's frame notation).
4. `tid=7318` in the header matches the native thread ID on the current thread.

Yet keep clear boundaries:

- Thread state is a **snapshot at crash time**, not a history of actions.
- Native frame stacks can omit Java inlined methods; `Java frames` help fill in the Java call chain when the log is intact.
- `Error occurred during error reporting` (if present in a real log) indicates the error reporter failed while walking stacks; never treat missing sections as proof of no callers.
- The original corruption may have occurred earlier in another request/thread/library and surfaced only when the codec or VM touched damaged memory.
- Never substitute **Java thread ID** for **native TID** when aligning with OS/core; account for PID namespaces.

### Follow-Up Questions to Ask

- From which commit was `libatlascodec.so` built, and is it the exact version **actually loaded**, or was the file on disk replaced by a later deploy?
- Which buffer/array did JNI entrypoint `Java_demo_codec_Decoder_decode` receive, and does it enforce bounds, lifetime, thread attachment, critical sections, and local/global refs?
- Does it depend on specific input, image dimensions, concurrency, a recent release, or CPU architecture?
- Which instruction (load or store) corresponded to `si_addr=0x0`, with which registers/stack, and where did the null pointer originate?

**Never use a stack snapshot alone to write "JNI null pointer" as a conclusion without instruction and memory evidence.**

## 5. Classifying Three Confidence Levels

This practice lab requires tagging statements **OBSERVED / INFERRED / UNKNOWN** without mixing them:

| Statement | Category | Reason |
| --- | --- | --- |
| `SIGSEGV`, `pc`, `pid`, `tid` appear in header | **OBSERVED** | Directly present in sample log |
| `Problematic frame` is `C` in `libatlascodec.so` | **OBSERVED** per `hs_err` | Log records crash site in native module |
| `Current thread` is in `_thread_in_native` | **OBSERVED** | Thread state line is present |
| Java calls into native codec in printed stack | **OBSERVED** per stack | `j` and `C` frames appear in the same chain |
| Native codec/JNI likely accessed an invalid pointer | **INFERRED** | Consistent with `SIGSEGV` and `si_addr=0`, though lacking core/disassembly |
| Bug definitely lies in native codec source | **UNKNOWN** | Has not ruled out memory corruption from callers, agents, JDK, or OS |
| Core `/var/crash/core.7312` exists and is intact | **UNKNOWN** | Only an intent message to write core exists |
| Exact binary and JDK patch level | **UNKNOWN** | Sample lacks hashes/build IDs/exact vendor |
| Specific decoding input reproduces the fault | **UNKNOWN** | Lacks input/trace/test results |
| GC/JIT is the root cause or completely ruled out | **UNKNOWN** | Excerpt lacks enough evidence to confirm or rule out completely |
| Process was `OOMKilled` instead of `SIGSEGV` | **NOT PROVEN** | Must check OS/pod events and exact incident |

**Good preliminary conclusion template:**

> HotSpot recorded `SIGSEGV` in native code inside `libatlascodec.so` on JavaThread `decode-io-3` in `_thread_in_native`. The Java→native codec call chain and `si_addr=0x0` raise suspicion of a pointer/memory-lifetime bug. **Root cause is unconfirmed**; prioritize preserving logs/core/binaries, retrieving JNI code + input, and reproducing safely.

This template separates **what was observed** from **what is hypothesized**, remaining actionable without overstating claims.

## 6. Designing the "Evidence Still Needed" Sheet

You do not need every conceivable log. Every request must list **priority, collection source, question to answer, and decision criteria**. For an active incident:

- **P0 – preserve immediately:** artifacts at risk of loss from pod recycling, log rotation, deployments, ephemeral volumes, or input expiration.
- **P1 – verify primary hypotheses:** core/symbols/native source, JVM/GC/JIT context, reproducer, and timeline correlation.
- **P2 – deep dive if P1 fails to explain:** controlled A/B across JDK/native releases, sanitizers, and hardware/OS variations.

| Priority | Missing Artifact/Fact | Collection Source | Verification Question |
| --- | --- | --- | --- |
| **P0** | **Complete `hs_err_pid7312.log`**, timestamp + checksum | Crash volume/persistent storage | Was the log truncated, missing stack/process/system sections, or showing error reporting failures? |
| **P0** | **Actual core file** (if generated), path and hash | OS core handler, `systemd-coredump`, volume | Does it contain registers, native stacks, and memory mappings for the exact crash? |
| **P0** | Stderr/stdout, kernel/cgroup/pod termination event | Container runtime, orchestrator, OS journal | Was the restart solely `SIGSEGV`, or were there separate `SIGKILL`/OOM events? |
| **P0** | Image digest, app release, exact JDK vendor/patch/build + flags | Deployment metadata, `hs_err` `VM Arguments` | Are versions exact enough to match binaries and bug databases? |
| **P0** | **Exact loaded `libatlascodec.so`**, checksum/build ID | Archived container image and binary artifacts | Which build produced the native code in the log, and is there an ABI mismatch? |
| **P0** | Request input/trace/operation, within security bounds | Tracing, request IDs, retained test fixtures | Do we have input data and the time window needed to reproduce? |
| **P1** | Native debug symbols, source, and symbolized backtrace | Build artifacts, core + debugger | Which instruction sits at `pc`, and which pointer/register faulted? |
| **P1** | JNI declarations/implementation and memory ownership | Exact-build native/Java source | Are there buffer overflows, use-after-free, invalid refs, races, or ABI mismatches? |
| **P1** | Full `Native frames`/`Java frames`, registers, `siginfo` | Original `hs_err` and core | Are there other JNI callers, stack corruption, or VM transitions? |
| **P1** | GC logs, JFR, compilation logs **if already stored** | Persistent logs/recordings | Did VM/GC/JIT activity before the crash alter hypotheses? |
| **P1** | OS memory/hardware/network and workload/replica pattern | Metrics, host/container events | Does the failure correlate with memory pressure, hardware, or concurrency? |
| **P1** | Safe reproducer with matching binary/input | Staging/sandbox | Does it reproduce? Does changing one variable alter frequency? |
| **P2** | A/B native codec/JDK versions, JVMTI agents | Controlled test matrix | Narrow down library, JVM, agent interaction, or CPU/OS differences? |
| **P2** | Native sanitizers, targeted compiler/GC experiments | Debug test builds | Is there enough evidence to prove memory corruption vs. a JVM bug? |

### Why Prioritize P0 First?

Cores may sit on ephemeral volumes deleted when pods rotate; new binaries overwrite crashed ones; log rotation deletes `hs_err`. Applying an unverified config tweak after losing artifacts makes root-cause analysis far harder.

If **no core exists**, report "core not available"; never claim "the core proved a null pointer". If **no symbols exist**, state findings only at module+offset level without inventing source lines.

## 7. Safe Handling When Reading Crash Files

The commands below **only read copies** of artifacts, never provoking crashes or attaching to production JVMs. Run them on authorized machines/volumes:

### 7.1. Confirm the Exact File and Checksum

```bash
ls -lh hs_err_pid7312.log
sha256sum hs_err_pid7312.log
file hs_err_pid7312.log
```

`sha256sum` detects whether an artifact changed while passed between teams; `file` only checks basic file type, not `hs_err` completeness.

### 7.2. Locate Key Sections

```bash
grep -n -E 'SIGSEGV|SIGBUS|SIGILL|Internal Error|Problematic frame|Current thread|siginfo|Native frames|Java frames|Current CompileTask|VM_Operation|VM Arguments|Dynamic libraries|error occurred during error reporting' hs_err_pid7312.log
```

Next, read **enough surrounding context**, such as header and thread start:

```bash
sed -n '1,150p' hs_err_pid7312.log
```

`grep` is a locator, not a substitute for reading context. Never claim "there was no `Current CompileTask`" just because an excerpt or `grep` missed it; in a full log, that section might simply be absent or truncated. A real `hs_err` can be long with crucial details well past the first 150 lines.

### 7.3. Verify the Exact Native Binary

If you saved the exact binary from the matching image:

```bash
sha256sum libatlascodec.so
file libatlascodec.so
readelf -n libatlascodec.so
```

`readelf -n` can display the GNU build ID if present. Compare against the image/build actually loaded by the process, **not the current file after a newer deploy**.

If a core genuinely exists with matching executables/symbols, inspect it **offline** in a debugger:

```bash
gdb -q /path/to/matching/java /path/to/saved/core
```

Inside the debugger, commands such as `bt`, `info registers`, `info sharedlibrary`, and disassembly around PC verify pointer/mapping hypotheses. `gdb` cannot guarantee accurate backtraces if the core is corrupt or binaries/symbols mismatch. Cores can contain secrets in memory; handle strictly under security policies.

**Never take `libatlascodec.so+0x13d1` and apply it to a different binary build to claim a specific C++ line**: load bias/offsets, ASLR, relocations, stripped symbols, and build IDs all matter.

## 8. Why Must You Separate JVM Crash from OS Kill?

If a pod restarts with exit status 137, that commonly indicates `SIGKILL` yet **does not by itself prove `OOMKilled`**. Cross-check `memory.events` in the **exact cgroup**, kernel logs, and termination reason. A kernel OOM kill can vanish the process without an `hs_err` because the JVM never gets a chance to handle the signal.

If an `hs_err` matches the incident's timestamp, signal, and PID, that is evidence of HotSpot fatal-error handling. You still need orchestrator logs to establish event order (fatal crash first vs. a subsequent restart). Never treat an exit code as complete proof.

Java `OutOfMemoryError: Java heap space` occurs when the JVM fails to allocate an object on the heap; it is **not equivalent** to the native `SIGSEGV` in the sample log. `-Xmx512m` does not prove actual heap usage. Heap dumps help inspect object graphs/OOME, **not replace native cores** when registers and native pointers are needed.

## 9. What If the Log Shows a `V`, `J`, or Compiler Thread Frame?

The primary sample leans toward native `C`. Practice classifying the other cases:

| Sign Pattern | Safe Crash Site Description | Evidence to Add |
| --- | --- | --- |
| `C [libvendor.so]`, `_thread_in_native`, JNI caller | Native library instruction | Library binary/symbols, core, native source, JNI boundary |
| `C [libnet.so]` from JDK | JDK native library instruction | Exact JDK build/OS/native agents, core, caller chain |
| `V [libjvm.so]`, `VMThread`, GC `VM_Operation` | VM/GC-related code at crash time | GC/safepoint logs, JNI/agent corruption, heap state, core |
| `V [jvm.dll]` with `C [App.dll]` right below | VM instruction with native caller | JNI contract/reference validity, native corruption, core |
| `J demo.Foo.work`, `Current thread` is request worker | **Running JIT-compiled Java code** | JDK build, method/tier, native agents, controlled interpreter A/B |
| `V [libjvm.so]`, `C2 CompilerThread`, `Current CompileTask` | **JIT compiler implementation actively compiling** | Compile task, compiler flags/logs, exact JDK, A/B/reproducer |
| `j demo.Foo.work` | Interpreted Java frame | Full stack and top crash PC; `j` is not JIT-compiled |
| `v ~StubRoutines` | VM-generated stub/transition | Adjacent frames, registers, disassembly |
| `Internal Error` / `guarantee(...) failed` | VM self-detected invalid internal state | Exact JDK build/source site, flags, current thread, agents/core |
| No `hs_err`, OS reports OOM kill | OS/container killed the process | Cgroup/kernel events, RSS/memory limits, pod termination evidence |

### 9.1. Two Distinct JIT States

**`Problematic frame: J ...` on an application thread**: PC landed inside JIT-generated machine code **currently executing**. A native library could have corrupted memory earlier; `J` alone does not prove the JIT compiler miscompiled code.

**`Problematic frame: V [libjvm]` on `C2 CompilerThread` with `Current CompileTask`**: the **compiler code itself was running to compile** a method's bytecode. The method in `Current CompileTask` is the **input**, not proof of buggy application logic.

If you only see `V`, inspect **current thread**. If you only see `J`, inspect **native agents, threads, and memory history**. If the log is truncated, never assume unprinted sections did not exist.

### 9.2. Controlled Experiments, Not Panaceas

In authorized test/staging environments:

```bash
java -Xcheck:jni -jar app.jar
java -Xint -jar app.jar
java -XX:CompileCommand=exclude,demo/FastHash.hash -jar app.jar
```

- `-Xcheck:jni` helps catch certain JNI misuses, **not all native C/C++ bugs**; it adds overhead and can halt the VM when severe errors are detected.
- `-Xint` runs Java interpreter-only; if the crash disappears, it could be JIT-related or simply altered timing/scheduling masking a data race.
- `-XX:CompileCommand=exclude,...` excludes only the named method in HotSpot, altering performance, inlining, and timing. Use only with exact method names and supported JDK flags.
- Change **one variable at a time** and repeat enough times; never call a workaround a confirmed root cause without evidence.

## 10. Seven-Step Triage Workflow for the Sample Log

**Step 1 — Preserve P0.** Back up the full fatal log, core if present, stderr, pod/kernel events, and exact image binary/JDK; record timestamps/PID/TID and hashes.

**Step 2 — Write observed facts.** E.g., `SIGSEGV`, `C` frame in `libatlascodec.so`, `decode-io-3` in native, `si_addr=0x0`. Do not auto-assign bug ownership from one frame.

**Step 3 — List data gaps.** Does a real core exist? Do binary/debug symbols match? Which request input? Any native callers/agents? Exact JDK build? Did the error reporter finish cleanly?

**Step 4 — Rank hypotheses.** H1: codec invalid pointer/ownership; H2: JNI caller/agent corruption; H3: ABI/version mismatch; H4: OS/JDK/hardware interaction. Order by proximity to symptoms, **never declaring H1 proven**.

**Step 5 — Collect targeted P1.** Symbolize core, read JNI/native source, check buffer bounds, references, and threading; check metrics/GC/JFR and concurrency at crash time if already recorded.

**Step 6 — Isolated reproducer.** Keep matching input and binary, repeat sufficiently, vary one factor (codec build/agent/JDK patch). Never move customer data outside authorized environments. One non-crashing run does not confirm a fix.

**Step 7 — Write report and owner.** Use `OBSERVED / INFERRED / UNKNOWN / P0 MISSING / P1 NEXT / OWNER / MITIGATION`. Distinguish "stopped crashes via rollback" from "proved root cause in source".

## 11. Java 17 Example: Classifying 4 Frame Samples **Without Crashing**

This program simply parses **simulated log snippets** and prints crash-site category labels; it does not trigger a JVM fatal error and is not a production forensic parser.

Create **`FatalLogClueLab.java`**:

```java
public final class FatalLogClueLab {
    static String classify(String snippet) {
        char frame = '?';
        boolean nextIsFrame = false;
        boolean compilerThread = false;

        for (String raw : snippet.split("\\R")) {
            String line = raw.trim();
            if (line.startsWith("#")) {
                line = line.substring(1).trim();
            }

            if (line.startsWith("Current thread:")
                    && line.contains("CompilerThread")) {
                compilerThread = true;
            }

            if (line.equals("Problematic frame:")) {
                nextIsFrame = true;
                continue;
            }
            if (nextIsFrame && !line.isBlank()) {
                if (line.length() >= 2
                        && Character.isWhitespace(line.charAt(1))) {
                    frame = line.charAt(0);
                }
                nextIsFrame = false;
            }
        }

        if (frame == 'V' && compilerThread) {
            return "JIT_COMPILER_THREAD_SITE";
        }
        return switch (frame) {
            case 'C' -> "NATIVE_LIBRARY_SITE";
            case 'V' -> "HOTSPOT_VM_SITE";
            case 'v' -> "VM_STUB_SITE";
            case 'J' -> "JIT_COMPILED_EXECUTION_SITE";
            case 'j' -> "INTERPRETED_JAVA_FRAME";
            default -> "UNKNOWN_SITE";
        };
    }

    public static void main(String[] args) {
        String[] names = {
            "native", "vm", "jit-execution", "jit-compiler"
        };
        String[] excerpts = {
            """
            # Problematic frame:
            # C  [libatlascodec.so+0x13d1]
            Current thread: JavaThread "decode-io-3" [_thread_in_native]
            """,
            """
            # Problematic frame:
            # V  [libjvm.so+0x1020]
            Current thread: VMThread
            """,
            """
            # Problematic frame:
            # J 1234 c2 demo.FastHash.mix([B)I
            Current thread: JavaThread "request-9" [_thread_in_Java]
            """,
            """
            # Problematic frame:
            # V  [libjvm.so+0xa321]
            Current thread: JavaThread "C2 CompilerThread0" [_thread_in_vm]
            Current CompileTask: demo.FastHash.mix([B)I
            """
        };

        for (int i = 0; i < excerpts.length; i++) {
            System.out.println(names[i] + " -> " + classify(excerpts[i]));
        }
    }
}
```

Compile and run (JDK 17+):

```bash
javac --release 17 FatalLogClueLab.java
java FatalLogClueLab
```

**Deterministic** stdout:

```text
native -> NATIVE_LIBRARY_SITE
vm -> HOTSPOT_VM_SITE
jit-execution -> JIT_COMPILED_EXECUTION_SITE
jit-compiler -> JIT_COMPILER_THREAD_SITE
```

- `NATIVE_LIBRARY_SITE` indicates only a native crash location, **not confirmation of bug cause**.
- `HOTSPOT_VM_SITE` requires checking `VM_Operation`/callers next.
- `JIT_COMPILED_EXECUTION_SITE` is **executing JIT-compiled code**, not proof of miscompilation.
- `JIT_COMPILER_THREAD_SITE` is the compiler implementation running on a compiler thread, needing `Current CompileTask`/JDK build.

This code is **designed strictly for these 4 controlled snippets**. Real `hs_err` logs have varied layouts, error-reporting failures, changing thread states, different debug symbols, or missing frames; never use a toy classifier to auto-determine **root cause** in serious incidents.

## 12. Short Lab Report Template

```text
INCIDENT: demo.ImageServer / PID 7312 / native TID 7318
STATUS: INVESTIGATING
OBSERVED:
- SIGSEGV, pc=0x00007f5a100013d1
- C frame in libatlascodec.so+0x13d1
- current decode-io-3 thread in native state
- si_addr=0x0; Java->native codec frames
INFERRED:
- native/JNI invalid access is plausible
UNKNOWN:
- exact faulting pointer and root cause
- actual core availability, matching symbols, exact binary/JDK build
P0:
- preserve complete hs_err, core, OS events, binary, release and input
P1:
- symbolize core, inspect JNI ownership, isolate reproducer
NEXT:
- confirm artifacts; perform controlled tests in staging
NOT CONFIRMED:
- JNI/vendor bug, JVM bug, JIT bug or a specific source line
```

This is an **illustrative report** for simulated data. In practice, add timeline, request trace, owner, and verified artifacts; never disclose customer data or cores carelessly.

## 13. Common Reasoning Mistakes

1. **"`C` is definitely a vendor library bug."** `C` only marks a native crash site; it could be a JDK/OS library or earlier corruption.
2. **"`V` means the JVM definitely has a bug."** JNI/JVMTI can corrupt memory and cause the VM to crash later.
3. **"`J` means Java source caused a `SIGSEGV`."** It is compiled Java machine code; distinguish miscompilation from memory corruption.
4. **"`j` means JIT."** No: lowercase `j` is an interpreted Java frame.
5. **"CompilerThread crash = compiled Java method executing."** A compiler thread compiles code and usually shows `V`; compiled execution shows `J`.
6. **"`Core dump will be written` guarantees the core was saved."** No: check filesystem, core handler, and permissions.
7. **"`si_addr=0` confirms the source of the null pointer."** It is only a hint; inspect native registers/disassembly/stack.
8. **"No `hs_err` means no crash."** `SIGKILL`, OOM kill, or inability to write logs can leave no fatal log.
9. **"Heap dump replaces native core."** A heap dump describes the Java object graph, not native pointers/registers.
10. **"The `libfoo.so` currently on the host is the one that crashed."** A deploy may have replaced it; verify matching image/binary hash.
11. **"`-Xint` stopped the crash, proving a JIT bug."** Altered timing/scheduling can hide a native race.
12. **"One non-reproducing test means it's fixed."** Rare races and corruptions require many controlled trials.
13. **"It's fine to send the raw core to a vendor."** Cores/`hs_err` contain sensitive data; follow access/redaction policies.
14. **"An investigation must pick one root cause immediately."** Good triage can end in **unconfirmed**, paired with missing evidence and next collection steps.

## 14. Check Questions and Answers

**Question 1.** What are `C [libatlascodec.so]` and `_thread_in_native` evidence of?  
**Answer:** The faulting instruction was in native code and the current thread was in native state. That is **OBSERVED**, not proof the bug is in codec source.

**Question 2.** Is `Core dump will be written` enough to report "core is available"?  
**Answer:** No. Check the actual core file/core handler, size, checksum, and matching PID/time.

**Question 3.** From `si_addr=0`, can you conclude a null pointer was passed directly from Java?  
**Answer:** No. You need registers/instructions, JNI native code, and memory history.

**Question 4.** Which section of the log shows where native libraries were actually loaded?  
**Answer:** `Dynamic libraries`/memory mappings. Follow up by confirming matching image hash/build ID.

**Question 5.** Does `V [libjvm.so]` with `VMThread` running GC confirm a GC bug?  
**Answer:** Not yet. GC may have stumbled on heap/references corrupted by JNI/agents; inspect the core, GC logs, and native evidence.

**Question 6.** How does `J demo.Hash.run` differ from `V` on `C2 CompilerThread`?  
**Answer:** `J` on a request thread is **executing compiled code**; `V` on a compiler thread is **compiling** a method.

**Question 7.** A pod exited with 137 and no `hs_err`; should you conclude OOME?  
**Answer:** No; verify termination event, kernel/cgroup OOM counters, memory pressure, and process signals.

**Question 8.** If a pod is about to be deleted and the core lives on an ephemeral volume, what is top priority?  
**Answer:** Preserve P0: full log, core, image/binary, OS events, and valid input before loss; analyze source/reproducer afterward.

**Question 9.** How do you write the conclusion in an incident ticket when you only have this snippet?  
**Answer:** State **native crash site + pointer/JNI hypothesis + unconfirmed root cause + P0/P1 to collect**, without declaring a vendor/JDK bug confirmed.

## 15. Completion Checklist

- [ ] Captured timestamp, PID/native TID, container/host, and exact app/JDK build.
- [ ] Distinguished JVM fatal error, Java exception, and external OS kill.
- [ ] Read `Problematic frame` and explained `C/V/v/J/j` accurately.
- [ ] Read `Current thread`, native/Java frames, and log excerpt limits.
- [ ] Checked `VM_Operation` or `Current CompileTask` when relevant signs appear.
- [ ] Built an **OBSERVED / INFERRED / UNKNOWN** table.
- [ ] Preserved at-risk P0 artifacts, especially log/core/image/binary/input.
- [ ] Planned targeted P1 verification evidence rather than turning on noisy logs blindly.
- [ ] Avoided symbolizing against mismatched binary/symbol builds.
- [ ] Used controlled tests without provoking crashes in production.
- [ ] Distinguished workarounds from verified root causes.
- [ ] Restricted access and handled sensitive data in `hs_err`/cores properly.

## References

- [Oracle JDK 17 — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-system-crashes.html): native code, compiled code, HotSpot compiler threads, `VMThread`, and diagnostics.
- [Oracle JDK 17 — Fatal Error Log](https://docs.oracle.com/en/java/javase/17/troubleshoot/location-fatal-error-log.html): header/frame markers, thread/process/system sections, file location, and error reporting limits.
- [Oracle JDK 17 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html): collecting cores, `hs_err`, and pre-incident logs.
- [Oracle JDK 17 — Submit a Bug Report](https://docs.oracle.com/en/java/javase/17/troubleshoot/submit-bug-report.html): info/coredumps/logs and reproducers to include when reporting bugs.
- [Oracle JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:ErrorFile`, `-Xcheck:jni`, `-Xint`, and `-XX:CompileCommand`.