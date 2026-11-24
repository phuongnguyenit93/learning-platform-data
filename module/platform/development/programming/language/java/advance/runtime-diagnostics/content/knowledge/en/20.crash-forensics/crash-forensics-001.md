# 20.1 Distinguishing Java Exceptions, OutOfMemoryError, StackOverflowError, and Fatal VM Errors

## 1. Goal: Identify the Right Failure Type Before Investigating a Crash

In Java, the word **“error”**, a stack trace on `stderr`, or a service disappearing **does not automatically mean** the JVM crashed. Four groups of phenomena are often conflated:

1. **Java exception**: the application or a library throws a `Throwable` object under the `Exception` branch, such as `IOException`, `SQLException`, `NullPointerException`, or `IllegalArgumentException`. It may be handled, return an HTTP error, terminate a thread, or cause the application to stop depending on logic.
2. **`java.lang.OutOfMemoryError` (OOME)**: the JVM or execution environment cannot satisfy a memory/resource request. This is an **`Error`**, not an `Exception`, and has many distinct causes: heap, metaspace, native thread, native/direct memory regions, array limits, etc.
3. **`java.lang.StackOverflowError` (SOE)**: a thread exceeds its execution stack limit, usually due to unbounded recursion, overly deep recursion, or a cyclic call chain. It is also an **`Error`**, not an ordinary exception.
4. **Fatal VM error**: HotSpot encounters a failure from which it cannot continue, such as a memory access fault in native/JNI/JIT/VM code or an internal VM error. The JVM usually **terminates the process**, attempts to create **`hs_err_pid...log`**, and may generate a core/minidump. This is **not** a Java `Throwable` that `catch` can handle.

There is also a crucial fifth case: **the process is killed by the OS/container**, such as the Linux OOM killer or `SIGKILL`. In that situation, there may be **no** `OutOfMemoryError`, `hs_err_pid`, heap dump, or `finally` execution. Therefore, you must combine evidence from both the JVM side **and** the OS/orchestrator side.

The goal of this lesson is to identify failures by **hierarchy, symptoms, artifacts, impact scope, recovery mechanism, and postmortem workflow**, rather than inferring solely from the exception name.

## 2. `Throwable` Hierarchy Diagram

In Java SE, the relevant class tree is:

```text
java.lang.Object
  └── java.lang.Throwable
        ├── java.lang.Exception
        │     ├── checked exceptions, e.g. IOException
        │     └── java.lang.RuntimeException
        │           ├── NullPointerException
        │           ├── IllegalArgumentException
        │           └── many other runtime exceptions
        └── java.lang.Error
              ├── java.lang.VirtualMachineError
              │     ├── OutOfMemoryError
              │     ├── StackOverflowError
              │     ├── InternalError
              │     └── UnknownError
              ├── AssertionError
              ├── LinkageError
              └── ...
```

**Note:** this is only a simplified branch for the lesson, not all subclasses of `Throwable`.

- **`Throwable`** is the root with `message`, `cause`, `stackTrace`, and `suppressed exceptions`. A `Throwable` that has already been created can be handled by `try/catch` if execution is still running normally.
- **Checked exception**: a subclass of `Exception` that is **not `RuntimeException`**. The Java compiler requires catching it or declaring `throws`; for example, `IOException`.
- **Unchecked exception**: `RuntimeException` and its subclasses. Not required to be declared with `throws`; usually indicates a logic bug, invalid argument, invalid state, or contract violation. Some exceptions may reflect I/O or remote failures wrapped into a runtime exception.
- **`Error`**: also a `Throwable`, but represents serious problems that should not be handled like normal business errors. Java does not require `catch` or declaring it. `OutOfMemoryError` and `StackOverflowError` belong to the `VirtualMachineError` group.
- **Fatal VM error** (such as a native `SIGSEGV`) **is not in the `Throwable` hierarchy**: no Java object is guaranteed to exist, and it is not a Java `Error` thrown via the normal path.

Therefore, claiming that “`OutOfMemoryError` is an exception because its name has Error/stack trace” is wrong regarding **type hierarchy**. Claiming that “every `Error` crashes the VM immediately” is also wrong: `AssertionError`, `StackOverflowError`, or `OutOfMemoryError` can be thrown in Java and the application may continue partially running, even though the state may still be dangerous.

## 3. Quick Comparison Table Before Opening Logs

| Criterion | Java exception | `OutOfMemoryError` | `StackOverflowError` | Fatal VM error |
| --- | --- | --- | --- | --- |
| Failure type | `Exception`/`RuntimeException` | `Error → VirtualMachineError` | `Error → VirtualMachineError` | Runtime/native error **outside `Throwable`** |
| Initial evidence | Exception class, message, stack trace, `Caused by` | `java.lang.OutOfMemoryError: <detail>`, GC/memory metrics | `java.lang.StackOverflowError`, repeated frames, large depth | `A fatal error has been detected...`, `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION`, `hs_err_pid` |
| Most important data | Root cause, stack, input/trace ID, application context | **Detail message**, heap/non-heap/native/container metrics | Repeated stack frames and recursive algorithm, call graph | Signal/exception, **problematic frame**, native stack, JVM build, core |
| Can Java `catch` it? | Yes | Syntactically yes, but safe recovery is hard to guarantee | Syntactically yes, but recovery should not be relied upon | **No**, not with Java `try/catch` |
| Stops the whole JVM automatically? | Not necessarily | Not necessarily; JVM policy or resource pressure may terminate the JVM | Not necessarily; the thread may terminate | Usually **terminates the JVM/process** |
| `hs_err_pid` by default? | No | Usually **no** for pure Java OOME; exceptions exist for native/fatal failures | Usually **no** for pure Java SOE | **May be created** if the fatal reporter is still functional |
| Heap dump when `HeapDumpOnOutOfMemoryError` is enabled? | Not just for ordinary exceptions | Possibly, depending on cause/build and ability to write | Not just for SOE | Cannot be treated as a default artifact |
| Remediation focus | Bug/validation/retry/contract | Specific memory pool, allocation/retention, OS/cgroup limits | Recursion, call cycle, stack depth, algorithm structure | Native/JNI/JIT/VM, build, library, and environment |

The “possibly/may” columns are intentional: a system running out of RAM, a full disk, a killed process, or a corrupted VM may fail to write artifacts in time. **Not seeing `hs_err_pid` does not prove there was no fatal error**; you must check the output location, write permissions, and OS logs.

## 4. Java Exception: Language/Library-Layer Error, Not Equivalent to a JVM Crash

### Checked exception

For example, `java.io.IOException` during I/O operations or `java.sql.SQLException` when handling JDBC. Code must catch or declare it:

```java
import java.io.IOException;

public class CheckedExample {
    static void readConfig() throws IOException {
        throw new IOException("configuration unavailable");
    }

    public static void main(String[] args) {
        try {
            readConfig();
        } catch (IOException ex) {
            System.out.println("handled=" + ex.getClass().getSimpleName());
        }
        System.out.println("still_running");
    }
}
```

Run `javac --release 17 CheckedExample.java` then `java CheckedExample`. Output from `System.out.println`:

```text
handled=IOException
still_running
```

In this example there is a valid `catch` and the process continues. **Do not assume** that catching an exception guarantees business data is safe; a transaction may have partially committed, a file may have been partially written, or a remote operation may have completed even though the client received an error. Proper rollback, idempotency, and retry policies are required.

### Runtime exception

```java
int port = Integer.parseInt("not-a-number");
// java.lang.NumberFormatException (a RuntimeException)
```

This is an **illustrative snippet**, not a standalone Java file. `NumberFormatException` does not require declaring `throws`; if unhandled, the current thread may terminate and print a stack trace. **An uncaught exception in a worker thread does not by itself prove the entire process died**; other threads may remain alive, and an event loop or supervisor may continue. If the main thread dies and no non-daemon threads remain, the process can exit.

### Why not catch every error with `catch (Throwable)`?

```java
try {
    executeRequest();
} catch (Throwable problem) {
    // Do not treat every Throwable as a recoverable HTTP 500 error.
}
```

This is an **illustrative snippet missing the definition of `executeRequest()`**, not a complete runnable program. Overly broad catching swallows `OutOfMemoryError`, `StackOverflowError`, and serious `Error`s. After resource exhaustion, creating a response, logging a stack trace, or allocating a new buffer may continue to fail. Normal application handlers should distinguish business errors, retryable I/O errors, and severe system errors; **do not hide an unhealthy process state**.

## 5. `OutOfMemoryError`: One Class Name, Many Different Causes

**`java.lang.OutOfMemoryError`** usually indicates that an allocation or resource request could not be satisfied. However, **the resource exhaustion condition can belong to many regions**:

| Typical HotSpot/JDK detail message | Resource group / hint | Investigation direction |
| --- | --- | --- |
| `Java heap space` | Cannot allocate an object/array in the Java heap | `-Xmx`, GC logs, heap usage/histogram/dump, retained objects, growing cache/list/map |
| `GC overhead limit exceeded` | JVM spends most of its time in GC with very little memory freed (when this mechanism applies) | GC frequency, heap pressure, allocation rate, retained live set |
| `Metaspace` | Class metadata in native/metaspace region | Classloader retention, dynamic proxy/bytecode generation, `MaxMetaspaceSize` |
| `Compressed class space` | Compressed class pointers/class metadata region (when the related feature is enabled) | Classloading, class metadata, `CompressedClassSpaceSize` |
| `Requested array size exceeds VM limit` | Array request exceeds implementation limit | Input size/length calculation; **cannot** simply be solved by increasing `-Xmx` |
| `unable to create native thread` or similar message | JVM/OS cannot create a native/platform thread | Process/thread count, `ulimit`, cgroup PIDs, native stack memory, memory pressure |
| `Direct buffer memory` or direct buffer reserve failure | Off-heap direct buffer limit / native reservation | Direct buffer usage, `MaxDirectMemorySize` if set, reference retention, RSS |
| `request ... bytes for ... Out of swap space?` or native allocation failure | Native memory/OS allocation, sometimes with fatal VM handling | Native Memory Tracking, OS mapping, swap/cgroup, core/`hs_err_pid` if present |

**Detail strings vary by JDK/vendor/allocation source**; do not treat this table strictly like an API enum. Always read the **exact error line** before changing flags.

### 5.1 Full heap vs. memory leak

`OutOfMemoryError: Java heap space` **does not automatically prove a leak**. There are at least four possibilities:

1. `-Xmx` is set too small for a legitimate live set;
2. increased load, payload size, or concurrency raises allocation/live data with demand;
3. the program holds unnecessary references (unbounded cache, static collection, listener, queue), i.e., a logical leak;
4. the workload has a request creating a very large object/array, or an allocation burst.

How to distinguish them: compare heap **after GC**, allocation rate, request concurrency, object age, and dominator/retained size in a heap dump. If post-GC heap keeps climbing under the same workload, a leak is more likely; if it rises and then stabilizes, it may be a normal cache/working set. **Increasing `-Xmx` merely to mask symptoms** may delay the incident slightly without fixing a retention leak.

### 5.2 Metaspace and classloaders

Metaspace is **native memory managing class metadata**, not the Java object heap in the usual counting sense. If `Metaspace` grows steadily, investigate loaded/unloaded class counts, hot-reload modules, agents, proxy factories, and retained classloaders. You can use `jcmd <PID> VM.classloader_stats`/`VM.metaspace` on supported HotSpot builds together with NMT. `ClassLoader` objects remaining in the heap can keep entire ecosystems of class metadata alive.

### 5.3 Unable to create native thread

The message `unable to create native thread` can occur due to insufficient memory for thread stacks, OS process/thread limits, container `pids.max`, or other resource constraints. **Do not just increase the Java heap**; raising `-Xmx` can sometimes shrink the remaining space for native memory. Check platform thread count, executor creation, `-Xss` (if applicable), RSS, OS ulimits, and cgroup limits. Virtual threads (JDK 21+) do not map each virtual thread 1-to-1 to a fixed kernel thread, but they **do not eliminate** carrier/platform thread limits or other native resources.

### 5.4 Running out of memory does not mean Java reports an OOME

On Linux/Kubernetes, when a cgroup exceeds its limit, **the OOM killer may send `SIGKILL`** to the process before Java can throw `OutOfMemoryError`. In that case, the JVM usually does not write a heap dump and does not run shutdown hooks. The container may report `reason=OOMKilled` and a typical exit status of 137, but **137 by itself only indicates SIGKILL-related termination**, not confirmed cgroup OOM; you must cross-check container events and kernel logs.

## 6. `StackOverflowError`: Call Stack Depth Error, Not a Heap Leak

**`java.lang.StackOverflowError`** occurs when a thread exceeds the stack capacity allocated to it, usually due to excessively deep recursion or an infinite call cycle:

```java
// Bug illustration snippet, DO NOT run directly in production.
static void recurseForever() {
    recurseForever(); // No base case.
}
```

In a typical stack trace, you will see the same method frames repeated many times:

```text
java.lang.StackOverflowError
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    ...
```

This is a **truncated illustrative output**, not fixed stdout; the JDK may limit the number of frames printed in a stack trace. Failures also occur due to **mutual recursion** between two or more methods, or cycles in object structures—for example `toString()` calling a nested object and cycling back, Jackson serialization on a graph with cycles, or a visitor traversing an overly deep tree.

### Preferred fixes

- Identify the **base case** and the condition progressing toward it; detect cycles using a visited/identity set when traversing graphs.
- For user-controlled inputs that can be arbitrarily deep, enforce a **reasonable depth limit** and return a validation error when exceeded rather than using the stack as a business limit.
- Convert extremely deep DFS/recursive traversals to an **iterative algorithm** using a `Deque` or an appropriate streaming/chunking mechanism.
- For `equals()`, `hashCode()`, `toString()`, and serializers/deserializers, check bidirectional object relationships.
- `-Xss` can change the stack size of platform threads on HotSpot, but it is **only an execution parameter** and does not fix infinite recursion. Increasing `-Xss` also raises per-thread stack/reservation cost; benchmark and account for native memory.

With **virtual threads**, stack management differs from platform threads (stacks may be stored as stack chunks on the heap); do not apply a rigid formula like “each virtual thread uses `-Xss` bytes.” Still, overly deep recursion can cause severe failures, and the application must still guard algorithms and inputs.

### Does `StackOverflowError` always kill the JVM?

**No.** It is a Java `Error` thrown in a single thread when its stack overflows. The VM may keep running, though the thread or operation may fail and application/transaction state may be left incomplete. Using `catch (StackOverflowError)` to “continue logic as normal” is not a reliable recovery strategy. Prioritize fixing the recursion/call graph and letting a supervisor restart a corrupted workload when needed.

### StackOverflowError vs. native stack overflow causing a fatal crash

There are cases where a stack failure in JNI/native code or the VM runtime causes a **fatal crash**, not merely a Java `StackOverflowError`. Symptoms include a signal/`hs_err_pid` and native/problematic frames; do not use the phrase “stack overflow” to immediately assume the throwable type. **Artifacts determine the investigation branch.**

## 7. Fatal VM Error: When HotSpot Cannot Continue

A HotSpot VM fatal error usually appears after a failure in **native/JNI code, the JVM runtime, JIT-compiled code, an internal assertion, or unrecoverable native resource failure**. On Linux/macOS you may see `SIGSEGV` (segmentation fault), `SIGBUS`, `SIGILL`, or `SIGABRT`; on Windows you may see `EXCEPTION_ACCESS_VIOLATION`. Typical symptoms:

```text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x..., pid=12345, tid=12346
#
# JRE version: ...
# Java VM: ...
# Problematic frame:
# C  [libexample.so+0x...]
#
# An error report file with more information is saved as:
# /var/log/java/hs_err_pid12345.log
```

This is an **illustrative snippet**, not output from a real crash; exact text, layout, and frames vary by JDK and OS. You may see Java compiled frames `J`, VM frames `V`/`v`, or native frames `C`. `Problematic frame` hints at the fault location, **not necessarily the final root cause**: earlier memory corruption may only manifest when another library dereferences a pointer.

A fatal VM error:

- usually causes the **process to terminate** and cannot be handled by Java `try/catch`;
- may write an **`hs_err_pid<pid>.log`** file, and sometimes a core/minidump depending on OS settings and disk space;
- can occur when using JNI/JNA, FFM/native interop, agents/profilers, native drivers, JVM bugs, or CPU instruction set/memory issues;
- is not always an “Oracle/OpenJDK JVM bug”: you must inspect addresses/libraries/frames and build a reproducer before attributing blame.

**Not every native signal is fatal**; HotSpot uses certain signals for internal purposes. Conclusions must be based on a **fatal report or process termination**, not merely the count of signals in `strace`.

## 8. What Does `hs_err_pid` Contain and in What Order Should You Read It?

HotSpot's fatal error file is typically named `hs_err_pid<PID>.log` in the JVM working directory or the path configured via `-XX:ErrorFile=...`. If writing there fails, the JVM may try a fallback location such as the OS temporary directory, **but file creation is not guaranteed in every crash**.

Once you have `hs_err`, read:

1. **Header**: signal/exception type, program counter (pc), PID/TID, JVM build, and `Problematic frame`.
2. **Current thread / thread state**: name and state of the faulting thread; Java frames, native frames, compiled/interpreted modes.
3. **Native stack and dynamic libraries**: `.so`/`.dll`/`.dylib` names and offsets; compare against the native/JNI/agent library versions in deployment.
4. **VM arguments / environment**: `-Xmx`, `-Xss`, GC, command line, `JAVA_HOME`, library paths, container/OS version, memory/CPU availability.
5. **Heap/GC/metaspace, memory map, and other threads**: whether there is memory pressure or concurrency issues.
6. **Error reporting warnings**: if the log itself notes “error occurred during error reporting” or is missing a section, treat the report as **incomplete** and do not invent missing frames.

A `Problematic frame: C [libmyjni.so+...]` should usually start the investigation at the **native library/JNI**. A `J` or `V` frame requires looking further into the JIT/VM stack and a crash reproducer; **it does not mean the Java source at that frame is definitively the culprit**. Native addresses are only meaningful when matched against the exact **binary build and debug symbols**.

## 9. Preparing Evidence Collection Before an Incident Occurs

The following JVM flags are for **supported HotSpot builds**, placed before `-jar` or the main class. This is a **startup** configuration example for a service, not something you can add to a running process without restarting.

```bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics \
  -XX:ErrorFile=/var/diagnostics/hs_err_pid%p.log \
  -Xlog:gc*:file=/var/diagnostics/gc.log:time,uptime,level,tags \
  -jar application.jar
```

This example uses Unix/Linux shell line continuation syntax; on PowerShell, place the options on **one line** or use PowerShell's line-continuation character. The `/var/diagnostics` directory must exist, the Java process must have write permissions, and there must be sufficient disk space; in containers, mount an appropriate volume if you need to retain artifacts across restarts.

### Distinguishing the options

| Option | When to use | What not to expect |
| --- | --- | --- |
| `-XX:+HeapDumpOnOutOfMemoryError` | Need a heap snapshot when HotSpot reports `OutOfMemoryError` and can write it | Not guaranteed for all native OOM types, container OOM kills, or fatal VM crashes |
| `-XX:HeapDumpPath=<path>` | Set file/directory path for generating a heap dump (HPROF) | Does not trigger a heap dump by itself without the flag above |
| `-XX:ErrorFile=<path>` | Set fatal error report file, supporting the `%p` PID token | Does not create `hs_err` for an ordinary Java exception |
| `-Xlog:gc*...` | Track GC and heap pressure leading up to OOME | Does not directly show the retained object graph |
| `-XX:NativeMemoryTracking=summary` | Need to observe JVM native memory from startup | Does not cover all native allocations from third-party libraries |
| `-XX:+ExitOnOutOfMemoryError` | Operational policy wanting the JVM to exit upon detecting OOME | Does not replace root-cause analysis; requires a supervisor |
| `-XX:+CrashOnOutOfMemoryError` | Special policy wanting the VM to abort/crash on OOME to produce crash artifacts | Can generate huge core files and increase downtime/disk usage; do not enable unconditionally |

`ExitOnOutOfMemoryError` and `CrashOnOutOfMemoryError` are two **different response policies**. Do not enable them blindly or combine them as a “mandatory flag bundle”; verify behavior on the exact JDK, staging environment, and orchestration system. If exit/crash happens too quickly, dumps or logs may not finish writing completely. **Important:** `HeapDumpOnOutOfMemoryError` is for **Java heap evidence**, not a native core dump; `ErrorFile` is for a **fatal VM report**, not an `.hprof` file.

### JFR before a crash

If you need history from the seconds or minutes preceding an incident, you can enable **continuous JFR** from startup:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=1h,maxsize=256m -jar application.jar
```

While the process is alive, use `jcmd <PID> JFR.dump name=ring filename=/var/diagnostics/before-incident.jfr`. When the process is killed or crashes, you will **not by default** get a complete JFR file; you may need to check repository chunks or artifacts previously saved by an observability system. Protect critical data with scheduled dumps or appropriate triggers if policy permits.

## 10. Diagnostic Command Set While the Process Is Still Alive

If the service shows signs of OOM/stack issues while the JVM is still alive, identify the PID and gather evidence in a controlled manner:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print -l
jcmd <PID> JFR.check
```

For a JVM with NMT enabled from startup:

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

These commands require a compatible HotSpot runtime, attach permissions, matching PID namespace, and JDK tools. `VM.native_memory` cannot reconstruct historical numbers if NMT was not enabled. `jcmd <PID> Thread.print` on a JVM with many threads can produce very large output.

### Proactive heap dump

```bash
jcmd <PID> GC.heap_dump /var/diagnostics/heap-before-restart.hprof
```

This is a **high-cost / high-impact command**; it usually requires a pause/safepoint or heavy work and can consume substantial RAM and disk space. Do not run it casually on resource-starved production systems without weighing the risk; choose the right timing, obtain authorization, and ensure sufficient capacity. `.hprof` files often contain sensitive object data.

**You cannot run these commands after the process has died.** Once the JVM is gone, prioritize already-saved logs, `hs_err`, core dumps, generated `.hprof` files, orchestrator/container status, and OS kernel logs.

## 11. Runnable Java 17+: Checking Hierarchy and How Exceptions Are Handled

Save the following program as **`FailureTaxonomyDemo.java`**:

```java
import java.io.IOException;

public class FailureTaxonomyDemo {
    static void failChecked() throws IOException {
        throw new IOException("disk unavailable");
    }

    public static void main(String[] args) {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "runtime_exception=" + ex.getClass().getSimpleName());
        }

        try {
            failChecked();
        } catch (IOException ex) {
            System.out.println(
                    "checked_exception=" + ex.getClass().getSimpleName());
        }

        System.out.println("oome_is_error=" +
                Error.class.isAssignableFrom(OutOfMemoryError.class));
        System.out.println("soe_is_vm_error=" +
                VirtualMachineError.class.isAssignableFrom(
                        StackOverflowError.class));
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 FailureTaxonomyDemo.java
java FailureTaxonomyDemo
```

**Exact stdout of the program:**

```text
runtime_exception=NumberFormatException
checked_exception=IOException
oome_is_error=true
soe_is_vm_error=true
```

This program does **not** trigger an OOME, SOE, or fatal error. It safely verifies type-system relationships:

- `NumberFormatException` is under the `RuntimeException` branch and can be caught specifically.
- `IOException` is a checked exception; `failChecked()` declares `throws`, and the caller must handle or declare it.
- `OutOfMemoryError` is a subclass of `Error`; `StackOverflowError` is a subclass of `VirtualMachineError`.
- The last two lines **do not say** OOME/SOE are “safe to continue from”; they only demonstrate inheritance.

### Why not trigger a real JVM crash in this exercise?

A demo that intentionally allocates infinitely, recurses infinitely, or triggers a JVM `SIGSEGV` can exhaust RAM, slow down the machine, or generate huge dumps. **Do not run such experiments on production or shared machines.** When reproduction is needed, use an isolated environment with cgroup/memory/CPU/disk limits, timeouts, artifact paths, and appropriate permissions. Do not treat a small sandbox OOME test as root-cause proof for a different production OOME.

## 12. Postmortem Workflow: Classify by Initial Evidence

### Step 1 — establish the facts of the process lifecycle

Record absolute timestamps, timezone, PID/container ID, hostname, deployment SHA/JDK build, memory limits, exit code/reason, and final logs. Distinguish:

- **Java stack trace with `Exception`/`Error`** while the process is still alive: start from throwable details, request context, logic bug, or memory pool.
- **`hs_err_pid` present with fatal signal / internal VM error header**: start from the fatal VM report, native frames, and JVM/vendor/library versions.
- **No Java stack trace, process was `OOMKilled` or `SIGKILL`ed**: start from OS/cgroup/kube events, memory graphs, RSS, page cache/native memory, and container limits; do not invent an `OutOfMemoryError`.
- **Application called `System.exit` or supervisor sent SIGTERM**: may be intentional shutdown or health-policy action, not a memory error. Check application logs, deploy events, and shutdown handlers.

### Step 2 — read the **full message**, not just the top-level summary

Examples of abbreviated stack traces:

```text
java.lang.NumberFormatException: For input string: "abc"
    at ...
```

```text
java.lang.OutOfMemoryError: Java heap space
    at ...
```

```text
java.lang.StackOverflowError
    at com.example.Tree.walk(Tree.java:42)
    at com.example.Tree.walk(Tree.java:42)
    ...
```

These are **illustrative samples**, not real logs. A Java exception requires checking `Caused by:`, nested/suppressed exceptions, and request IDs. OOME requires the **detail string** before opening a heap dump; SOE requires repeated frames, recursion-triggering input, and JVM stack configuration. A fatal signal requires `hs_err`/core.

### Step 3 — collect the right artifacts

| Suspect group | Priority artifacts |
| --- | --- |
| Checked/runtime exception | Application logs, trace ID, sanitized payload with sensitive data masked, stack trace/cause, release, transaction status |
| Heap OOME | `.hprof` if available, GC logs, heap metrics/trends, `-Xmx`, load/concurrency, class histogram |
| Metaspace OOME | `VM.metaspace`, `VM.classloader_stats`, class counts, reload patterns, native memory metrics |
| Native/thread/direct OOME | NMT, RSS/cgroup, PID/thread limits, direct buffer pools, OS maps, kernel/container events |
| SOE | Stack trace depth/repeated methods, input graph, recursion base case, `-Xss`, code version |
| Fatal VM error | `hs_err_pid`, core/minidump if available, problematic/native frames, native libraries, JDK/vendor/build, JVM flags, environment |
| OOM kill/SIGKILL | Pod/container exit reason, kernel OOM logs/cgroup events, memory limit/usage, RSS graph; usually **no** Java dump |

### Step 4 — prioritize safety and service recovery

Collect automated evidence if already configured, but **do not delay service recovery indefinitely waiting for a dump**. When you suspect process state is corrupted after a `VirtualMachineError`, apply an appropriate health/restart policy. Do not catch OOME and keep serving requests normally just because the code compiles.

### Step 5 — cross-check and verify

A solid hypothesis must align **error type + message + resource + timing + repro/load conditions**. Fix at the right layer:

- Heap OOME → manage object lifetime / heap sizing / GC / concurrency;
- Native OOME → native allocations, thread/pid limits, off-heap usage, cgroup;
- SOE → base case, cycle detection, iterative algorithm;
- Native fatal → investigate JNI/library/JIT/VM and versions;
- Java exception → input contract, exception handling, transactions/retries.

After the change, verify error rate, post-GC memory trend, RSS, thread counts, latency, and recovery under equivalent load.

## 13. Four Real-World Incidents to Practice Distinguishing

### Scenario A — API returns HTTP 500, service keeps accepting requests

Logs show a `NullPointerException` in a mapper with a request ID, and the process PID remains unchanged. **Handling branch:** runtime exception (application bug). Identify missing input data or uninitialized object, inspect stack/cause, add proper validation, and add a test for that request. Do **not** hunt for `hs_err_pid` as the primary artifact or enable OOME heap dumps to solve an NPE.

**Note:** an unhandled exception can cause a **thread** to terminate. Whether the process continues depends on thread lifecycle and framework behavior; it is not true that “exceptions never kill a service.”

### Scenario B — After 8 hours under load, `OutOfMemoryError: Java heap space`

Logs show post-GC heap climbing steadily, frequent GC, and an `.hprof` file exists because the flag was enabled. **Handling branch:** heap OOME. Analyze the dominator tree/histogram, static caches, retained collections, queue sizes, and the impact of recent releases. `-Xmx` can be adjusted temporarily to ease pressure, but you must prove the memory footprint fits the container limit to avoid an OOM kill from heap + native exceeding the cgroup.

**Do not conclude:** the class with the largest shallow bytes **is not automatically the leak owner**; examine retained references and allocation/lifecycle.

### Scenario C — A batch job crashes with `StackOverflowError` on a data tree

The stack trace repeats `Tree.visit` for thousands of frames, and the input contains a cycle or exceeds the designed depth. **Handling branch:** SOE. Reproduce with anonymized data, add a visited set / depth guard or switch to iterative DFS/BFS; avoid increasing `-Xss` as a “final patch” for unbounded recursion. If `hs_err`/native `SIGSEGV` also appears at the same time, check whether you are hitting a **fatal native stack failure** rather than only a Java SOE.

### Scenario D — Container dies, no Java throwable, exit 137

The orchestrator reports `OOMKilled` and RSS/cgroup memory usage climbed; there is no `.hprof` and no `hs_err`. **Handling branch:** kernel/container OOM kill. Investigate memory limits, off-heap/direct/native buffers, thread stacks, process heap size, shared page cache, and cgroup monitoring. Do **not** conclude the JVM threw `OutOfMemoryError`; the kill may arrive before the JVM detects anything or without passing through the OOME code path.

If you only see exit 137 without an `OOMKilled` reason, check who sent `SIGKILL`, timeouts, deploy/operator actions, and kernel logs before concluding RAM exhaustion.

### Scenario E — `SIGSEGV`, `hs_err_pid` shows `Problematic frame: C [libnative.so...]`

**Handling branch:** fatal VM/native crash. Verify the exact `libnative.so` build, JNI call site, native memory safety, JDK/OS versions, reproduction, core dump, and involved thread. A crash in a native frame **does not by itself prove a bug in that specific library**: memory corruption could have originated elsewhere; traces and core dumps are needed to conclude.

## 14. Reading Crash Artifacts Without Drawing False Conclusions

### `.hprof`

A heap dump is a snapshot of the Java heap's object graph. Use Eclipse MAT, VisualVM, or appropriate JDK tools to inspect the dominator tree, retained sizes, and leak suspects. **Not a native core**: a heap dump does not show every `malloc` in JNI, OS stacks, or all native allocation addresses. Dumps can be huge and contain passwords, sessions, tokens, or PII in the object graph, so they must be encrypted and access-restricted.

### `hs_err_pid*.log`

This is HotSpot's **fatal VM log**: signal, thread, native frames, VM arguments, memory map, and state captured at crash time. It may be absent due to disk, permissions, OS kill, or an error during reporting itself. Do not confuse this file with **Java application logs** written by Logback/Log4j/SLF4J.

### Core dump / minidump

This is an **OS-level** artifact containing process state for a native debugger; it can be very large and sensitive. Whether it is collected depends on `ulimit -c`, `core_pattern`, `systemd-coredump`, Windows WER, container security settings, and disk quota. A `.core` is not an `.hprof` and cannot be opened as a heap dump. Never share production core dumps publicly.

### GC logs

These show heap occupancy and GC pauses prior to OOME; they help distinguish allocation bursts, sustained live-set growth, and collector pressure. They **do not directly identify which Java object holds a reference**; use a corresponding heap dump or tracing for that.

### NMT and OS metrics

Native Memory Tracking uses `-XX:NativeMemoryTracking=summary/detail` from startup; `jcmd VM.native_memory` reports reserved/committed memory by HotSpot category. It is not the total process RSS and does not cover all third-party native libraries. Cross-check against `RSS`/`cgroup memory`, direct buffer pools, OS mappings, and thread counts.

### JFR

JFR reveals what happened before a crash: allocations, GC, thread scheduling, locking, and application events. If enabled only after an incident, it cannot look back retroactively; continuous recording requires retention and dumping while the process is alive. A `.jfr` is a different artifact from `.hprof`/`hs_err`; do not expect one type to completely replace another.

## 15. Common Mistakes When Choosing a Remediation

| Misconception | Why it is wrong | Right approach |
| --- | --- | --- |
| “Any stack trace is a JVM crash” | A Java exception can be caught and the service can continue | Check PID/process lifecycle and throwable type |
| “`Error` means the OS process is dead” | `Error` is a Java `Throwable` and does not necessarily stop the whole JVM | Inspect thread/service state; evaluate restart policy |
| “OOME is always the Java heap” | Metaspace, native threads, direct/native allocations, and other limits exist | Distinguish by **detail message** + metrics |
| “OOME is always a leak” | Could be heap sizing, payload burst, or concurrency | Compare post-GC live set, retained size, and workload |
| “Increasing `-Xmx` fixes every memory issue” | Can reduce native headroom and trigger a cgroup OOM kill | Budget heap + non-heap + native + OS together |
| “Exit 137 proves a Java OOME” | 137 usually reflects SIGKILL and does not prove `OutOfMemoryError` | Check `OOMKilled` reason and kernel/event history |
| “SOE = heap memory is full” | It is a stack/call-depth limit, not the heap | Inspect recursive frames/cycles and code logic |
| “Increasing `-Xss` fixes SOE” | Recursion without a base case stays infinite; larger stacks also consume native memory | Fix the algorithm; tune stack size only if justified |
| “`catch (Throwable)` is robust” | Swallows serious VM errors and may continue in a broken state | Catch recoverable types and surface fatal signals |
| “`finally` always runs before every crash” | `SIGKILL` and fatal aborts can prevent Java cleanup | Use an external supervisor and durable logging |
| “No `hs_err` means it wasn't a VM crash” | The reporter may fail to write; the OS may kill the process | Check stderr, output location, permissions, and OS diagnostics |
| “Having `hs_err` means a Java exception caused it” | Fatal reports belong to the VM/native layer, not ordinary Throwables | Analyze header/problematic frame/native stack |
| “Problematic frame = bug definitely in that library” | Memory corruption may have happened earlier | Use core, symbols, reproducer, and native diagnostics |
| “Heap dump shows few objects so there is no native leak” | Heap dumps do not track all native allocations | Use NMT + RSS/cgroup + native profiling |
| “Trigger OOME directly in production to test flags” | Can impact the entire host/pod and other data | Test with memory/disk/time limits in a sandbox |
| “CrashOnOutOfMemoryError and ExitOnOutOfMemoryError are the same” | One aborts/crashes, the other exits | Choose a policy with testing and artifact requirements |

## 16. Safe Operating Rules After a Failure

**For recoverable Java exceptions:** check transactional safety, idempotency, retry with exponential backoff/jitter, timeouts, and circuit breakers according to business requirements. Do not retry every `RuntimeException`; a `NullPointerException` from a logic bug usually will not improve on retry.

**For OOME:** keep in mind the JVM may lack resources to log, spawn threads, or build responses. Capture evidence proactively and use a fail-fast/restart policy with a supervisor when appropriate. Avoid catching OOME and then allocating large collections, formatting unbounded stack traces, or pushing more load into a resource-exhausted process.

**For SOE:** fix the recursion logic. If the system accepts untrusted input, enforce depth and cycle checks at the boundary; a batch job can mark the job failed and move it to a retry queue **after fixing the data/limits**, rather than repeating the same recursion.

**For fatal VM errors:** treat the process as no longer trustworthy; prioritize recovery via orchestration, preserve logs/cores per policy, and find the root cause with an isolated reproducer. You cannot rely on a Java exception handler to recover from a native segmentation fault.

**For OS kills:** configure appropriate budgets/cgroups/limits, headroom metrics, pod restarts, and readiness/liveness probes as needed; do not expect a Java dump if the kernel sent `SIGKILL`.

## 17. Triage Checklist in the First 60 Seconds of an Incident

- [ ] Is the process alive or dead? Did the PID or container restart count change?
- [ ] Is there a **Java throwable stack trace**, an `hs_err_pid`, or only an exit event?
- [ ] If `OutOfMemoryError`: record the **exact detail message**, without stripping what follows the `:`.
- [ ] If `StackOverflowError`: locate repeated methods, input, cycles, and call depth.
- [ ] If fatal VM: record signal/exception, problematic frame, JDK build, and native library versions.
- [ ] If container exit `137`: check `reason=OOMKilled` and kernel/cgroup events, not just the exit code.
- [ ] Are GC logs, `.hprof`, JFR, NMT, or memory/CPU/thread metrics from before the failure available?
- [ ] Check `-Xmx`/`-Xss`/`MaxMetaspaceSize`/`MaxDirectMemorySize` and container memory/PID limits on the target process.
- [ ] Have artifacts been preserved with timestamp, PID, release, host/container ID, and correct directory?
- [ ] Have filesystem space and permissions been checked for fatal logs and heap/core dumps?
- [ ] Has an appropriate restart/fail-fast policy been chosen instead of swallowing all `Error`s?
- [ ] After remediation, have error rate, memory trend, GC, RSS, and throughput been compared under the same workload?

## 18. Official References to Consult

1. Java SE 21, `Throwable` — exception/error concepts, cause, and stack trace: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html
2. Java SE 21, `Exception` and `Error` — checked/unchecked rules and serious errors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Error.html
3. Java SE 21, `VirtualMachineError` — superclass of `OutOfMemoryError` and `StackOverflowError`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/VirtualMachineError.html
4. Java SE 21, `OutOfMemoryError` — Javadoc: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/OutOfMemoryError.html
5. Java SE 21, `StackOverflowError` — Javadoc: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackOverflowError.html
6. Oracle JDK 21 Troubleshooting Guide, *Troubleshoot Memory Leaks* — OOME detail messages and heap/native classification: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
7. Oracle JDK 24, *Location of Fatal Error Log* — `hs_err_pid` and meaning of header/problematic frame: https://docs.oracle.com/en/java/javase/24/troubleshoot/location-fatal-error-log.html
8. Oracle JDK 22, *Troubleshoot System Crashes* — native/JNI/JIT/VM crash diagnosis: https://docs.oracle.com/en/java/javase/22/troubleshoot/troubleshoot-system-crashes.html
9. Oracle JDK 21 `java` manual — `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath`, `-XX:ErrorFile`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
10. Oracle JDK 21, *Prepare Java for Troubleshooting* — collecting core, fatal logs, GC/JFR, and diagnostic artifacts: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
11. Oracle JDK 21, *Diagnostic Tools* — `jcmd`, heap dump, and postmortem options: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html

**Conclusion:** do not lump every incident together as a “Java crash.” A Java exception is typically **an error represented as a `Throwable`**; `OutOfMemoryError` is **exhaustion of a specific resource, requiring you to read the detail**; `StackOverflowError` is **exceeding stack/call depth**; a fatal VM error is **a breakdown in the JVM/native runtime** that may leave `hs_err_pid`/core; and an OS OOM kill is **an external action outside the JVM**. Pick the right category first so you know whether you need **stack traces, a heap dump, GC/NMT, a core dump, or container/kernel logs** to find the real root cause.
