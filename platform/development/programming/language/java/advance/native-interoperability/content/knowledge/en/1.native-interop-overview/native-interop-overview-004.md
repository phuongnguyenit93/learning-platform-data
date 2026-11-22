# Comparing JNI, Foreign Function & Memory API, and Interprocess Communication

> **Context:** Java Advance / Native Interoperability / Interoperability Overview. This article compares three ways for a Java application to use code or services outside the JVM, focusing on execution boundaries, memory control, reliability, and selection criteria.

## 1. Three Approaches Solving Three Different Types of Boundaries

Suppose a Java program needs to call a function provided by a C library, use a codec written in C++, or run an existing computation program:

- **JNI (Java Native Interface):** Java declares a `native` method; a dynamic library containing C/C++ code implements that method and uses the JNI interface to interact with the JVM, Java objects, exceptions, and callbacks.
- **FFM API (Foreign Function & Memory API):** Java uses `java.lang.foreign` to look up C ABI function symbols, describe function signatures, create a `MethodHandle` to call native code, and manage off-heap memory regions with `MemorySegment`/`Arena`. For compatible C ABI functions, the JNI glue layer written in C can be omitted.
- **Interprocess communication (IPC):** Java and a helper program run in **two different processes**, exchanging messages via stdin/stdout, pipes, Unix-domain sockets, TCP, HTTP, gRPC, or other IPC mechanisms. The helper program can be written in Java, C, C++, Rust, Python, etc.

```text
JNI:   [Java + JVM, PID A] -> [JNI wrapper C/C++] -> [native library, PID A]
FFM:   [Java + JVM, PID A] -> [Linker / MethodHandle] -> [C ABI library, PID A]
IPC:   [Java + JVM, PID A] -> [bytes + protocol] -> [helper process, PID B]
                                                         -> [native library, PID B]
```

**Decision point:** JNI and FFM call native code **within the same address space** as the JVM; IPC creates a process boundary. Replacing JNI with FFM does not automatically isolate the JVM from a buggy native library. Conversely, IPC does not necessarily involve native code: Java can communicate with another Java process.

FFM was finalized in **JDK 22 (JEP 454)**. JNI has existed for a long time and is still usable on Java 17+. IPC with `ProcessBuilder` is also usable on Java 17+. The FFM examples below require **JDK 22 or later**; the JNI/IPC examples run on Java 17+.

## 2. Comparison Table by Technical Criteria

| Criterion | JNI | FFM API | IPC across processes |
|---|---|---|---|
| Boundary | Java ↔ native **same process** | Java ↔ native **same process** | Two processes, possibly on two machines |
| Java entry point | `native`, `System.loadLibrary`, `JNIEnv*` | `Linker`, `SymbolLookup`, `FunctionDescriptor`, `MethodHandle`; `MemorySegment`/`Arena` when using memory | `ProcessBuilder`, pipe, socket, HTTP/gRPC client |
| Separate C glue code needed? | Usually **yes**: wrapper following JNI conventions | Usually **no** when the library exports a compatible C ABI | Not needed in the JVM; helper handles the protocol and library itself |
| Reusable Java API | Java 17+ and older versions | Stable since Java 22 | Java 17+; language-independent protocol |
| Object/GC interaction | JNI provides access to objects, arrays, classes, exceptions, global/local refs | FFM favors ABI data, layouts, and addresses; passing complex Java objects requires custom conversion | Serialized into messages, no shared Java objects/pointers |
| Memory | Native pointers, `JNIEnv`, JNI pin/copy array APIs; careful manual management | `MemorySegment` has bounds/lifetime checks when accessed from Java; `Arena` controls ownership | No shared address space by default; buffers managed on each side |
| Per-call overhead | JNI transition, object/array mapping, and marshaling | Foreign downcall, ABI adaptation, data allocation/transfer if needed | Serialize/deserialize, IPC I/O, scheduling; process startup if called one-shot |
| Native crash/UB | Can **crash the entire JVM** | Can still **crash the entire JVM** | Usually only the helper process crashes; Java receives EOF/exit/error and handles it |
| Debugging | Java stack + native debugger, symbols, core dump | Java stack + native debugger, layout/ABI | Logs, traces, request IDs, and per-process debugging |
| Distribution | JVM + OS/CPU-specific library + JNI wrapper | JVM 22+ + OS/CPU-specific library and compatible ABI | JVM + executable/container/helper + protocol and lifecycle |
| Calling back into Java | JNI calls Java methods via `JNIEnv` | FFM has `upcallStub` for native code to call a Java target via a method handle | Helper sends messages/callbacks according to the protocol |
| Notable use cases | Existing JNI libraries; deep manipulation of Java objects/JVM needed | Clear C ABI; calling native functions/structs/pointers without wanting to maintain JNI glue | Isolating fault-prone code, CLI tools, separate services, different languages/privileges/machines |

The table shows **design characteristics**, not a speed ranking. An optimized JNI wrapper may be faster or slower than FFM under a given workload; a long-lived IPC worker processing batches may be more efficient than calling native code per element. Always measure with realistic data volumes and call patterns.

## 3. JNI: Java Calling a Method Implemented in C

JNI is a binary interface and set of functions for native code to work with the JVM. When Java calls a `native` method, the JVM transitions to the corresponding native function; for a C wrapper, the `JNIEnv*` parameter provides operations for Java objects, strings, arrays, and exceptions. `JNIEnv*` is bound to the calling thread; **do not store this pointer and use it from another thread**. Java references created via JNI also have lifetime rules: a local reference must not be treated as a global reference.

The following example demonstrates a standalone JNI wrapper performing small integer addition (assuming no `int` overflow). The build commands use **Linux, GCC, and a JDK with `JAVA_HOME` configured**.

**File `JniAdd.java`:**

```java
public class JniAdd {
    static {
        System.loadLibrary("jniadd");
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println("JNI: " + add(20, 22));
    }
}
```

Generate the header using the JDK compiler:

```bash
javac -h . JniAdd.java
```

This command generates `JniAdd.class` and `JniAdd.h`. The native function name must match the header generated by `javac -h`.

**File `JniAdd.c`:**

```c
#include <jni.h>
#include "JniAdd.h"

JNIEXPORT jint JNICALL Java_JniAdd_add(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return a + b;
}
```

Build the shared library and run (Linux):

```bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjniadd.so JniAdd.c

java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniAdd
```

**stdout (JDK 24+, native access granted):**

```text
JNI: 42
```

On Java 17, you can run `java -Djava.library.path=. JniAdd`. On macOS, the corresponding library is typically `libjniadd.dylib` and the compile command uses `-dynamiclib` and the `include/darwin` header; Windows requires a DLL, toolchain, and the appropriate `include/win32` header. All three must build the library for the exact OS/CPU/JDK ABI. `System.loadLibrary("jniadd")` uses the logical name `jniadd`, without adding the `lib` prefix or file extension.

**When is JNI useful?** When a library already provides a JNI wrapper, or when native code needs to retrieve/call Java objects, handle Java exceptions, callbacks, classes, and deep JVM lifecycle. In return, you must maintain C/C++ glue, reference ownership, `jstring`/`jarray` type conversions, thread attachment, and native build tooling.

## 4. FFM API: Calling a C ABI Without Writing a JNI Wrapper

FFM has two complementary parts:

1. **Foreign function:** `SymbolLookup` finds the function address, `FunctionDescriptor` describes the return type and parameters, and `Linker.nativeLinker()` creates a `MethodHandle` to call the function according to the platform ABI. A Java → C call is a **downcall**; in the C → Java direction, an **upcall stub** can be created.
2. **Foreign memory:** `MemorySegment` represents a contiguous memory region; `MemoryLayout` describes size/alignment/structs; `Arena` allocates and determines the memory region's lifetime. `Arena.ofConfined()` restricts operations to the owning thread and is closed via `try-with-resources`; `Arena.ofShared()` supports access from multiple threads but requires data synchronization.

Reusing the same addition in a C library exporting the `add` function. Example on **Linux x86-64 / standard C ABI**; `C int` matches `ValueLayout.JAVA_INT` (32-bit) on this platform.

**File `nativecalc.c`:**

```c
int add(int a, int b) {
    return a + b;
}
```

Build the C library:

```bash
gcc -fPIC -shared -o libnativecalc.so nativecalc.c
```

**File `FfmAdd.java` (JDK 22+):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class FfmAdd {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup symbols = SymbolLookup.libraryLookup(
                    Path.of("libnativecalc.so").toAbsolutePath(), arena);

            MethodHandle add = Linker.nativeLinker().downcallHandle(
                    symbols.find("add").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

            int result = (int) add.invokeExact(20, 22);
            System.out.println("FFM: " + result);
        }
    }
}
```

Build and run:

```bash
javac FfmAdd.java
java --enable-native-access=ALL-UNNAMED FfmAdd
```

**stdout:**

```text
FFM: 42
```

`SymbolLookup.libraryLookup(Path, Arena)` retrieves symbols directly from the library and ties the lookup's lifetime to the arena. `symbols.find("add").orElseThrow()` works on JDK 22 as well; the convenience method `findOrThrow` was only added in a later JDK release. When `arena` closes, segments/lookups belonging to that scope can no longer be used; do not keep method handles or pointers to call after the library/memory region's lifetime has ended.

**Points to check when doing real FFM work:**

- The C ABI must match **exactly**: number/types of parameters, return type, calling convention, alignment, struct/union layout, and `long`/`size_t` size per OS/architecture. Do not assume C `long` is always Java `long`; 64-bit Windows and 64-bit Linux have different data models.
- Native pointers are addresses, not Java objects. You must clarify who owns the memory, which side allocates/frees it, and whether native code retains the pointer after Java closes the `Arena`.
- Bounds/lifetime checks when Java accesses a `MemorySegment` help prevent one class of bugs; they **do not guarantee** that the called C/C++ function is safe. Native code can still write out of bounds, cause use-after-free, or crash the JVM.
- If a library only exports C++ APIs with name mangling, class methods, templates, or C++ exceptions, a stable **C ABI facade** is usually needed first before calling it with FFM; FFM does not automatically turn every C++ API into a callable ABI.

For C libraries with a simple ABI, FFM reduces dedicated JNI code and makes data/pointers explicit on the Java side. For libraries heavily using complex Java objects/callbacks and an existing JNI ecosystem, migrating to FFM may not be worth the cost.

## 5. IPC: Java Communicating with a Helper Process

IPC separates Java from the helper along an operating system boundary. The helper can load native libraries without the main JVM needing to load them. A **protocol** must be agreed upon: request/response format (text lines, JSON, Protobuf), encoding, framing, error status, versioning, timeouts, correlation IDs, and size limits.

The Java 17+ example below uses **one request and one response over a pipe**. The helper is written in Java so the demo is easy to run; in a native system, you can replace the helper with a C/C++ executable using the same protocol.

**File `ChildAdd.java`:**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ChildAdd {
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line = input.readLine();
        if (line == null) {
            throw new IllegalArgumentException("Missing request");
        }

        String[] fields = line.trim().split("\\s+");
        if (fields.length != 2) {
            throw new IllegalArgumentException("Expected: a b");
        }

        int a = Integer.parseInt(fields[0]);
        int b = Integer.parseInt(fields[1]);
        System.out.println(Math.addExact(a, b));
    }
}
```

**File `ParentAdd.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ParentAdd {
    public static void main(String[] args) throws Exception {
        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String javaBin = Path.of(
                System.getProperty("java.home"), "bin", executable).toString();

        Process child = new ProcessBuilder(
                javaBin, "-cp", System.getProperty("java.class.path"), "ChildAdd")
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();

        try (var writer = new BufferedWriter(
                new OutputStreamWriter(
                        child.getOutputStream(), StandardCharsets.UTF_8))) {
            writer.write("20 22\n");
        }

        String reply;
        try (var reader = new BufferedReader(
                new InputStreamReader(
                        child.getInputStream(), StandardCharsets.UTF_8))) {
            reply = reader.readLine();
        }

        int exit = child.waitFor();
        if (exit != 0 || reply == null) {
            throw new IllegalStateException(
                    "Helper failed: exit=" + exit + ", reply=" + reply);
        }
        System.out.println("IPC: " + Integer.parseInt(reply));
    }
}
```

Run on Windows, Linux, or macOS with JDK 17+:

```bash
javac ChildAdd.java ParentAdd.java
java ParentAdd
```

**stdout:**

```text
IPC: 42
```

`ParentAdd` sends the request via the child's stdin, the child returns the response via stdout, and stderr is redirected straight to the console to avoid mixing logs with machine-readable data. `waitFor()` checks the exit code. This is a **small, synchronous, single-request example**: `readLine()` can still hang forever if the helper does not output a line. In a real environment, you need a timeout mechanism covering I/O, consumption of both stdout/stderr (or redirecting stderr to logs), message size limits, stream closing, process cancellation handling, and appropriate restarts.

For long-running helpers, maintain a connection/worker pool instead of starting a process for every call. If you need to exchange multiple requests or support multiple clients, choose a framed protocol, request identifiers, and backpressure control; sockets or RPC are usually clearer than a simple pipe.

## 6. Reliability, Failures, and Isolation

**JNI and FFM:** Both bring the native library into the same JVM process. A segmentation fault, out-of-bounds memory write, stack corruption, or undefined behavior in C/C++ can terminate the entire JVM. Java `try/catch` is not a shield against native-level crashes. Ordinary logic errors can still be turned into error results: JNI uses APIs to throw Java exceptions or return error codes; FFM typically reads return codes/`errno`/result structs according to the C ABI contract.

**IPC:** The helper process has its own address space and state. If the helper dies due to a native crash, Java usually sees a closed pipe, EOF, a non-zero exit code, or a connection reset; Java can log, retry when safe, restart the helper, or return an error for the request. However, IPC **does not automatically** guarantee timeouts, recovery, exactly-once semantics, security, or resilience: your protocol and supervisor design must provide those properties.

Distinguish between:

- **Crash isolation:** a faulty helper does not directly corrupt the parent process's JVM heap; processes still share machine resources (CPU, RAM, files, network), so resource limits must be enforced.
- **Fault handling:** in-process native calls require native code to check pointers/return codes; IPC requires managing timeouts, connections, exit codes, and lifecycles.
- **Retry:** a timed-out IPC call may have already executed in the helper; only retry blindly when the operation is truly idempotent or has request IDs/deduplication.
- **Trust boundary:** a helper running under the same user can still read files/secrets with the same permissions; for strong isolation, you need reduced OS privileges, an appropriate container/sandbox, filesystem/network policies, and input validation.

## 7. Performance: Looking at the Entire Data Path

A qualitative model:

```text
JNI call ≈ JNI transition + data conversion + native work
FFM call ≈ downcall/ABI adaptation + data conversion + native work
IPC call ≈ encode + data transfer + scheduling + decode + helper work
           (+ process startup if spawning a new helper per request)
```

- For millions of tiny operations, repeated boundary-crossing costs can dominate the work; try **batching multiple elements** into a single native/IPC call.
- For heavy tasks like video processing, ML inference, or file compression, IPC overhead may be small compared to the computation; isolation and operations may matter more than a few microseconds.
- For large arrays/structs, measure bytes copied, pinning, alignment, memory allocation, serialization, and buffer reuse. `MemorySegment` does not automatically mean end-to-end "zero copy".
- Distinguish **throughput**, **p50/p95/p99 latency**, CPU, native memory, startup time, and stability under failure. Benchmark with JIT warm-up, realistic data, and the same environment/hardware; do not treat a single microbenchmark as a universal rule.

There is no general guarantee that "FFM is always faster than JNI" or "JNI is always faster than IPC": the workload, library, data transfer method, and implementation determine the result.

## 8. Choosing Technology Based on Requirements

| Scenario | Reasonable initial choice | Why |
|---|---|---|
| A stable JNI binding already exists for the library in use | **JNI** | Leverage tested bindings, callbacks, and code; no need to migrate just because FFM exists |
| Need to call many simple C ABI functions, running JDK 22+, don't want to write JNI glue | **FFM** | Link symbols directly, describe C ABI types, and manage memory on the Java side |
| Need deep interaction with JVM objects from C/C++ | **JNI** | `JNIEnv`, refs, and Java callbacks are core parts of JNI |
| Untrusted or crash-prone native library (third-party codec/plugin) | **IPC helper** | Limits crash impact and allows restarting the helper |
| Existing CLI tool with simple input/output protocol | **IPC via ProcessBuilder** | Reuses the executable without forcing native bindings inside the JVM |
| Component needs independent upgrades, multiple clients, potential remote execution | **IPC/RPC service** | Has separate deployment, versioning, and operational boundaries |
| Need both C ABI calls and JVM isolation | **FFM or JNI in a helper process + IPC to main Java** | Two independent axes: how the helper calls native code and how Java talks to the helper |

**Quick decision flow:** (1) Must it run in the **same process**? If crash/privilege/deployment isolation is required, prefer IPC. (2) If in-process, is there an existing JNI wrapper or deep Java object/JVM manipulation needed? Consider JNI. (3) If primarily calling a C ABI, on JDK 22+, and wanting to reduce C glue, try FFM. (4) Measure performance and evaluate operations before finalizing.

Approaches can be **combined**: the main Java process talks via IPC to a C++ worker; the worker uses a C ABI or JNI/FFM in its own JVM (if the worker is also Java). This is often the solution when both native functionality and fault isolation are needed.

## 9. Safety, Compatibility, and Deployment

**JVM integrity and native access.** Starting in **JDK 24**, JEP 472 prepares to restrict JNI and FFM uniformly: many native operations are considered restricted and emit warnings by default when permission is not granted. When code is on the classpath, run with `--enable-native-access=ALL-UNNAMED`; modularized applications should grant `--enable-native-access=module.name` precisely. In production environments, test with `--illegal-native-access=deny` (JDK 24+) to catch code missing permissions early. This is a mechanism to control a module's permission *to use native access*; it does not make C/C++ memory-safe. On JDK 22–23, FFM restricted operations require native-access enablement; on JDK 17, there is no stable FFM API yet.

**ABI and distribution.** Native artifacts are OS/architecture-specific: Linux `.so`, macOS `.dylib`, Windows `.dll`. Having the right file format is not enough: you need matching architecture, calling convention, compiler/runtime dependencies, symbol exports, layouts, and dependent libraries. C++ ABIs are not uniform across compilers; a C facade is usually more stable. Docker images, artifact classifiers, or installers should package the right binaries. IPC also needs to distribute the right executable and protocol version, even though the main JVM does not load the binary into its address space.

**Memory ownership.** With JNI, acquire/release pairs for arrays/strings and local/global references must be balanced; never use another thread's `JNIEnv*`. With FFM, choose a confined/shared arena according to your threading policy; do not let pointers escape scope, and do not let native code hold pointers after memory is freed. With IPC, do not send raw pointers/addresses as reusable data to another process: pass values, OS-protocol-shared file descriptors/handles, or shared memory with explicit permissions and synchronization.

**Security.** Validate data from Java before passing it down to native code or sending it to a helper; enforce length, encoding, path, and resource limits. With `ProcessBuilder`, pass commands/arguments as separate elements rather than concatenating arbitrary shell strings; only use a shell when truly necessary and with controlled quoting. Keep stdout clean for the protocol and stderr separate for logs; control execution permissions on libraries/executables, IPC connection addresses, and secrets.

## 10. Common Pitfalls When Comparing or Implementing

1. **"FFM is the new JNI and completely replaces JNI."** False: FFM is stable since JDK 22 and fits C ABI/memory very well, but JNI still fits APIs working deeply with the JVM and existing binding ecosystems.
2. **"FFM avoids native crashes."** False: native code still runs inside the JVM process and can corrupt memory.
3. **"IPC is always slow, so don't use it for computation."** False if native work is large, well-batched, or high isolation is required. Measure p95/p99 and end-to-end cost.
4. **"Returning normally means all errors were handled properly."** False: JNI must handle pending Java exceptions, FFM must check return codes/errno, and IPC must check exit codes, EOF, protocol errors, and timeouts.
5. **"`int`/`long`/structs have the same layout on every platform."** False: check the specific C ABI, alignment, and field offsets; especially `long` and `size_t`.
6. **"Native pointers can be passed over IPC as shared addresses."** False: each process has its own address space; use serialization or OS-supported shared memory/handle mechanisms.
7. **"Closing the `Arena` ends all responsibilities."** False if native code still holds pointers, uses buffers after closing, or violates the ownership contract.
8. **"`readLine()` followed by `waitFor()` is enough to prevent hangs."** False: timeouts must cover the read/write phases, bounded buffers, and uncooperative processes.
9. **"Switching from JNI to FFM will automatically speed things up."** There is no guarantee; comparisons must keep the workload, native implementation, and marshaling strategy identical.

## 11. Practice Exercises for Self-Verification

- Run the three examples with `20` and `22`; all three return `42`. Then replace them with negative and boundary numbers, clarifying that overflow is the responsibility of the native implementation/protocol.
- In the FFM example, try changing `FunctionDescriptor` to a wrong one (only in a practice environment) to see how **an ABI mismatch can cause serious errors**; do not do this on a JVM holding important data.
- With IPC, make the helper exit with a non-zero exit code or print nothing to stdout; observe how the parent handles EOF/exit status. Add a real timeout covering I/O and test a hanging helper.
- With JNI/FFM, check what errors occur when loading a library for the wrong OS/CPU or a non-existent symbol. With IPC, check a missing executable or mismatched protocol version.
- If measuring performance, compare **one million individual adds** against **one batch call of one million elements**, with the same data and work, to see how boundary crossing and marshaling can become the bottleneck.

**Practical conclusion:** Choose **JNI** when you need deep JVM bindings or want to keep existing JNI integrations; choose **FFM** when you want to use C ABIs and native memory directly on JDK 22+; choose **IPC** when you prioritize isolation, independent deployment, or using a separate executable/service. A system can combine IPC with JNI/FFM on the worker side.

## Official References

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Java SE 25: `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java SE 25: `SymbolLookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 25: `Arena` and thread confinement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
- [Java SE 25: `ProcessBuilder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/index.html)
