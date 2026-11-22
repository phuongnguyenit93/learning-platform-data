# JNI, JNA, and native library compatibility

When upgrading a Java application to a new JDK, pure Java code may compile and pass tests cleanly while the program still fails immediately upon loading a native library, initializing an agent, invoking a C/C++ function, or receiving a callback from outside the JVM. Errors such as UnsatisfiedLinkError, memory access violations, JVM crashes, corrupted return values, or hangs during shutdown frequently originate at the **Java–native boundary**.

A native library does not depend only on the Java version. It also depends on the operating system, CPU architecture, ABI, calling conventions, C/C++ compilers, runtime libraries, dynamic library loading mechanisms, and pointer, thread, and memory management. That is why the exact same JAR can run fine on Linux x86-64 yet fail on Linux ARM64, Windows, macOS, or a container using a different libc.

In **Java Advance Compatibility Migration**, the **Agent and Native Code** chapter, this lesson explains two key mechanisms — **JNI (Java Native Interface)** and **JNA (Java Native Access)** — the compatibility layers to assess when changing JDKs and runtimes, how to diagnose failures, and how to design a safe migration workflow.

The goal is not merely getting the JVM to find a `.so`, `.dll`, or `.dylib` file. The goal is ensuring **Java and native code completely agree on data representations, memory ownership, calling mechanics, exceptions, threading, resource cleanup, and supported platforms**.

## 1. Where does native code live inside a Java application?

A Java application can cross multiple kinds of boundaries:

~~~text
Java application
       |
       +--> Java framework / dependency JAR
       |         |
       |         +--> JNI wrapper
       |         |       |
       |         |       v
       |         |   C/C++ native library
       |         |
       |         +--> JNA / libffi invocation
       |                 |
       |                 v
       |             OS native library
       |
       +--> Java agent (-javaagent)
       |         |
       |         +--> Bytecode instrumentation
       |         +--> May use its own JNI/JVMTI
       |
       +--> Native agent (-agentlib/-agentpath)
                 |
                 v
               JVMTI
~~~

Libraries commonly involving native code include:

- JDBC drivers relying on native client libraries.
- Compression, image/video, OCR, audio, or computer vision libraries.
- Cryptography, HSM, PKCS#11, and security libraries.
- Embedded databases or storage engines.
- Machine-learning inference runtimes.
- Hardware access, serial ports, USB, and GPUs.
- Operating-system integration.
- Monitoring, profilers, debuggers, and tracing agents.
- Libraries written in Rust/C/C++ packaged as native binaries.

Just because an artifact ends in JAR does not mean it contains only Java bytecode. Many JARs embed native binaries, extract them to a temporary directory, and load them via System.load, JNI, or JNA.

## 2. Distinguishing JNI, JNA, FFM, and JVMTI

| Mechanism | Invocation model | Characteristics | Primary concerns |
|---|---|---|---|
| JNI | Java declares native methods; native library implements per JNI protocol | Long-standing standard API for Java–native integration | JNI signatures, JNIEnv, exceptions, references |
| JNA | Java uses interfaces/mappings to call native functions via JNA runtime | Reduces manual JNI glue code in many cases | C ABI, types, struct layouts, JNA/libffi |
| FFM API | Java uses the JDK's Foreign Function & Memory API where applicable | Modern standard API for foreign calls and off-heap memory | Descriptors, memory layouts, lifetimes, native access |
| JVMTI | Native agents interact with the JVM via the tooling interface | Built for profilers, debuggers, monitoring, and agents | Event/capability lifecycles, JVMTI/JVM compatibility |
| Java Instrumentation API | Java agents transform bytecode via java.lang.instrument | Not pure JNI | Bytecode, module openness, agent bootstrap |

**JNI and JNA are not identical.** JNI is the low-level interface between Java and native code. JNA is a library supplying mapping/invocation mechanisms over native functions via a support runtime; JNA's own implementation contains native components and does not turn an arbitrary C++ API into a stable ABI.

**JVMTI differs from JNI.** A JVMTI agent may use JNI to manipulate Java objects, yet JVMTI defines a distinct API set for JVM instrumentation and observation. Never lump every agent error into "JNI library missing".

## 3. Compatibility layers to evaluate

A Java upgrade can break multiple layers invisible to the Java compiler.

| Layer | Question | Potential symptoms |
|---|---|---|
| Java source | Are native method declarations and wrapper APIs still right? | Compile errors |
| Java binary | Do native method names/descriptors still match? | UnsatisfiedLinkError on invocation |
| JNI contract | Are JNI function signatures and JNIEnv usage still valid? | Crashes, exceptions, corrupted data |
| C ABI | Do calling conventions, symbols, struct layouts, and integer sizes match? | Crashes, corrupted arguments/returns |
| Platform | Do OS, CPU, bitness, and libc match the target? | Library fails to load |
| Dependencies | Are all native library dependencies/linker symbols present? | Linker errors |
| JDK policy | Did native access permissions, modules, or agent loading change? | Warnings or runtime rejection depending on JDK |
| Memory | Do pointers, buffers, and references live long enough? | Use-after-free, JVM crash |
| Threading | Do native threads calling into the JVM attach/detach properly? | Crashes, leaks, hangs |
| Error handling | Are native error codes, Java exceptions, and errno handled right? | Silent corruption |
| Operations | How are libraries extracted, loaded, and cleaned up? | Failures in containers, permissions, shutdown |

A program can succeed at library loading and simple calls yet still fail under concurrency, during GC cycles, or during shutdown/redeploy.

## 4. The JNI model: Java calling C via specified names and types

JNI allows a Java class to declare native methods:

~~~java
package com.example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("nativecalc");
    }

    private NativeMath() {
    }

    public static native long sum(long a, long b);
}
~~~

Call site:

~~~java
long result = NativeMath.sum(10L, 20L);
System.out.println(result);
~~~

Java declares only the native method signature without a Java method body. When the class initializes, System.loadLibrary tells the JVM to load the native library with logical name `nativecalc` from appropriate search paths.

The native implementation must follow the matching JNI ABI.

### 4.1. Typical C header form

~~~c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_com_example_nativebridge_NativeMath_sum(
        JNIEnv *env,
        jclass clazz,
        jlong a,
        jlong b) {
    (void)env;
    (void)clazz;
    return a + b;
}
~~~

In this example:

- JNIEXPORT handles platform-specific symbol exporting.
- JNICALL represents the JNI-specified calling convention.
- `JNIEnv*` exposes JNI functions for the executing thread.
- For **static native methods**, the second parameter is jclass.
- For **instance native methods**, the second parameter is jobject.
- jlong is the JNI type sized for 64-bit Java long.

The long function name follows JNI naming conventions for the class and method. With overloaded native methods, native names include signature-encoding suffixes. Never hand-guess symbol names when `javac` can generate headers.

### 4.2. Generating headers with javac -h

On supporting JDKs:

~~~bash
javac -h native-headers -d classes src/com/example/nativebridge/NativeMath.java
~~~

The compiler generates headers declaring JNI functions with the necessary names, types, and macros.

Safe mindset:

1. Java native declarations are the source contract.
2. Generate headers from declarations.
3. C/C++ implementations include those headers.
4. Build native libraries using the platform-matched toolchain.
5. Load from the matching Java runtime.
6. Run integration tests on every supported platform.

Never hand-write all JNI function prototypes assuming they still match after changing packages, method names, or parameters.

### 4.3. Static vs. instance native methods

Instance method:

~~~java
public final class NativeCounter {
    public native int increment(int delta);
}
~~~

The C implementation receives a jobject receiver instead of jclass:

~~~c
JNIEXPORT jint JNICALL
Java_com_example_nativebridge_NativeCounter_increment(
        JNIEnv *env,
        jobject self,
        jint delta) {
    (void)env;
    (void)self;
    return delta + 1;
}
~~~

This illustrates signature shape; the C function's package/class portion must match the actual Java package. Changing jclass to jobject or modifying Java methods without rebuilding the native library creates linkage risks.

## 5. JNI_OnLoad and native library lifecycle

A JNI library can define JNI_OnLoad to receive the JavaVM pointer when loaded by the JVM.

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}
~~~

JNI_OnLoad can validate or initialize lightweight state. Avoid heavy initialization that could deadlock or call unsuitable APIs during load.

To bind Java native methods without relying on exported symbol naming conventions, use RegisterNatives with exact class and method signatures. That demands explicit mapping management and must never be misunderstood as bypassing JNI type checks or constraints.

### 5.1. Do not rely on automatic unloading for business cleanup

JNI_OnUnload may run when a library unloads under JVM-permitted conditions. However, unload timing depends on classloaders and native-reference lifetimes rather than acting as a reliable shutdown hook for every app.

Design explicit close/shutdown APIs for native contexts and handles, releasing resources at application or service shutdown per clear contracts.

### 5.2. Java objects and native handles need clear ownership

A Java object may store a `jlong` holding a native pointer or handle ID. Clarify:

- Does the Java object own the handle?
- Is the native handle still valid when methods execute?
- Is closing multiple times idempotent/permitted?
- Can multiple Java objects share one handle?
- Can one thread close while another calls into the handle?
- On partial initialization errors, who frees allocated resources?

Never treat a `jlong` holding a memory address as an ordinary number to store, copy, or mutate arbitrarily.

## 6. JNI types and data mapping

JNI defines explicit types that must not be replaced casually with lookalike C/C++ types by intuition.

| Java | JNI type | Notes |
|---|---|---|
| boolean | jboolean | JNI representation; never assume equivalent to C++ bool across all ABIs |
| byte | jbyte | Signed 8-bit integer |
| char | jchar | Unsigned 16-bit UTF-16 code unit |
| short | jshort | 16-bit integer |
| int | jint | 32-bit integer |
| long | jlong | 64-bit integer |
| float | jfloat | 32-bit floating point |
| double | jdouble | 64-bit floating point |
| Object | jobject | JNI reference |
| String | jstring | JNI reference to String |
| Class | jclass | JNI class reference |
| Array | jarray / typed variants | JNI array reference |

Platforms differ in C `long`, `size_t`, pointer sizes, and alignment. When C code needs a 64-bit integer from Java `long`, use `jlong` or an appropriate fixed-width C type with range-checked conversion.

### 6.1. Pitfall: C long is not Java long

On many 64-bit Linux environments, C `long` is 64-bit. On 64-bit Windows, C `long` is typically 32-bit per the platform ABI. Java `long` is always 64-bit.

Converting `jlong` to C `long` without checking ranges and ABI sizes can silently truncate data on some platforms.

### 6.2. Char and Unicode

Java `char` is a UTF-16 code unit, not a full Unicode scalar value and not a C `char` byte.

JNI provides APIs operating on `jstring` as UTF-16 or modified UTF-8. **JNI modified UTF-8 must not be equated with standard UTF-8.** When integrating with C libraries expecting standard UTF-8, perform explicit encoding conversion and test non-BMP characters, embedded nulls, emojis, and multilingual strings.

### 6.3. Boolean differs from an ordinary byte

When mapping Java `boolean` to a native API, confirm whether the native side expects `_Bool`, `BOOL`, `bool`, `uint8_t`, or `int`. These types can differ in size, alignment, and calling conventions.

Never pass `jboolean` straight into an OS library interface expecting a 32-bit `BOOL` assuming equivalence.

## 7. JNA: calling the C ABI without hand-written JNI glue

JNA lets you declare Java interfaces representing exported C functions in a native library. C example:

~~~c
/* nativecalc.c */
int add(int a, int b) {
    return a + b;
}
~~~

When building the shared library, export the `add` symbol per toolchain/platform rules. Windows may require `__declspec(dllexport)`; C++ requires `extern "C"` to avoid name mangling.

Java JNA interface:

~~~java
package com.example.jnademo;

import com.sun.jna.Library;
import com.sun.jna.Native;

public interface NativeCalc extends Library {
    NativeCalc INSTANCE = Native.load(
        "nativecalc",
        NativeCalc.class
    );

    int add(int a, int b);
}
~~~

Usage:

~~~java
int result = NativeCalc.INSTANCE.add(2, 3);
System.out.println(result);
~~~

Here, JNA handles most of the work mapping the call to the exported native function. No `JNIEXPORT Java_package_Class_method` boilerplate like hand-written JNI is needed.

### 7.1. Preconditions for the JNA example

The example works only when:

- The native library is built for the matching OS/CPU.
- The `add` symbol is actually exported.
- The Java signature `int, int → int` matches C `int` on the target ABI.
- The JNA runtime and native support library match the JDK/OS.
- The library and its native dependencies are visible to the loader.
- Calling conventions match.

If C++ exports mangled symbols or uses a different calling convention, ordinary JNA interface bindings may fail to find or mis-call the symbol.

### 7.2. JNA does not eliminate ABI requirements

JNA reduces manual JNI glue code, yet the C ABI must still align precisely:

- Integer widths and signedness.
- Pointer widths.
- Struct packing and alignment.
- Callback signatures.
- Memory ownership.
- Calling conventions.
- String encodings.
- C++ symbol names and layouts.
- Function pointer lifetimes.

An ABI mismatch under JNA still causes crashes, memory corruption, or wrong results invisible to the Java compiler.

## 8. How to choose between JNI and JNA?

| Criterion | JNI | JNA |
|---|---|---|
| Need to write a native bridge | Typically yes | Often minimal when library exports a clean C ABI |
| Need C/C++ compiler for wrapper | Typically yes | No wrapper needed for many simple cases |
| Accessing Java objects | Directly via JNI APIs | Callback/mapping support, yet cannot replace full JNI |
| Optimizing hot call paths | Full bridge control | Extra mapping/FFI overhead |
| ABI mismatches | High risk | Still high risk |
| Integrating C-style OS APIs | Possible | Often convenient |
| Callbacks and threading | Must obey JNI rules | Must obey callback lifetime and native rules |
| Native runtime dependencies | Self-built library and wrapper | JNA runtime/libffi plus target library |
| JDK migration focus | Check JNI contracts and native builds | Check JNA version, loader, and library ABI |

Neither option is universally best. For native libraries already exposing a clean C ABI, JNA can cut boilerplate. For complex callbacks, deep JVM interactions, or tightly tuned call paths, JNI may fit better. For greenfield projects on a supporting JDK, the Foreign Function & Memory API is another option to evaluate.

### 8.1. Do not decide from naive microbenchmarks alone

Performance depends on boundary crossing frequency, marshalling cost, payload sizes, calling conventions, JIT behavior, library implementation, and workload.

Millions of tiny native calls can be dominated by boundary overhead. Conversely, processing large images or heavy cryptography makes native computation dominate boundary overhead.

Before optimizing, analyze batching sizes, feasible zero-copy paths, data flows, and allocation/conversion costs.

## 9. OS, CPU architecture, and bitness

Native binaries follow platform-specific formats:

| Operating system | Example extension | Common format |
|---|---|---|
| Windows | `.dll` | PE/COFF |
| Linux | `.so` | ELF |
| macOS | `.dylib` or legacy `.jnilib` | Mach-O |

You cannot load a Linux `.so` directly on Windows, or an x86-64 binary inside an ARM64 process without explicit out-of-band compatibility layers.

Differences to record:

- x86-64 vs. aarch64/arm64.
- Windows, Linux, macOS.
- 32-bit vs. 64-bit.
- glibc vs. musl on Linux.
- Minimum supported OS version.
- CPU instruction sets such as AVX/NEON.
- Native dependencies (OpenSSL, libstdc++, libgcc, CUDA, etc.).
- C++ compiler and runtime ABI versions.

### 9.1. What does an architecture mismatch look like?

Suppose a Linux ARM64 container loads an `.so` compiled for x86-64. The JVM may throw `UnsatisfiedLinkError` wrapping dynamic loader messages about wrong ELF class, machine type, or format.

The fix is supplying binaries for the right architecture or compiling the native component for the target platform. Tweaking `java.library.path` will not turn an x86-64 file into ARM64.

### 9.2. Container base images changing libc

An application on an Ubuntu/Debian-based image typically uses native libraries linked against glibc. Moving to Alpine Linux introduces musl. Even on the exact same CPU architecture, `.so` files and dependencies may fail to load.

This makes upgrading the JDK simultaneously with swapping container base images a dual change. Validate native compatibility against the final image.

### 9.3. macOS universal binaries and codesigning

macOS enforces architecture matching, code signing, hardened runtime rules, and dynamic library loading entitlements depending on environment. A native library running smoothly on a developer workstation can be blocked once packaged inside a desktop app or different distribution.

Inspect signatures, quarantine flags, architecture slices, and platform packaging rules instead of adjusting only Java classpaths.

## 10. Dynamic linker, symbols, and native dependencies

`System.loadLibrary` only requests loading the named library. The operating system must also resolve every native dependency of that library.

Example:

~~~text
Java:
  System.loadLibrary("nativecalc")
       |
       v
nativecalc.so
       |
       +--> libstdc++.so
       +--> libcrypto.so
       +--> libc.so
~~~

If `nativecalc.so` exists yet ABI-compatible `libcrypto.so` is absent, the JVM still throws `UnsatisfiedLinkError` due to an unresolved transitive dependency.

Questions to check:

1. Can the library file be found?
2. Does it match OS/CPU/bitness?
3. Are all transitive native dependencies available?
4. Are needed symbols exported?
5. Does the runtime linker pick the intended dependency version?
6. Are there ABI conflicts across versions?
7. Do OS policies block loading?

### 10.1. Java logical names vs. filenames

~~~java
System.loadLibrary("nativecalc");
~~~

uses a logical name. The JVM maps it to platform conventions, such as `libnativecalc.so` on Linux or `nativecalc.dll` on Windows.

~~~java
System.load("/opt/app/native/libnativecalc.so");
~~~

takes an absolute path to a specific file. That path is illustrative; cross-OS applications must never hardcode Linux paths across environments.

### 10.2. java.library.path differs from classpath

Classpath locates Java classes and resources. `java.library.path` feeds the JVM's native library search mechanism where applicable.

Dropping an `.so` beside JAR files does not automatically guarantee `System.loadLibrary` finds it. Nor should code mutate `java.library.path` **after the JVM has booted** expecting the loader to refresh search paths; actual behavior depends on JVM and loader specifics.

### 10.3. JNA has its own library lookup mechanism

JNA exposes search/config options such as `jna.library.path` depending on usage. Yet JNA still relies on the OS dynamic loader and underlying native dependencies.

Inside containers, check where JNA extracts its native support library, whether the temp filesystem allows execution, and whether libraries can load from that directory.

## 11. ABI: why matching-looking method signatures can still be wrong

An **ABI (Application Binary Interface)** defines how compiled binaries exchange data and calls at machine level: registers/stack, parameter layouts, return values, symbol naming, alignment, and conventions.

### 11.1. C primitive sizes vary across platforms

Commonly confused types:

| C/C++ type | Size or pitfall | Handling guidance |
|---|---|---|
| `int` | Often 32-bit on common platforms, though ABI-defined | Verify via headers and platform ABI |
| `long` | Can be 32-bit or 64-bit | Never equate with Java `long` |
| `size_t` | Matches platform address width | Map with pointer-sized widths |
| `void*` | 32/64-bit or platform-specific | Never cast blindly to Java `int` |
| `bool` / `_Bool` | Compiler/ABI-specific layout | Never assume identical to Java `boolean` |
| `wchar_t` | Varies in width across platforms | Never equate with Java `char` |
| `long double` | Varies in format and width | Never map arbitrarily to `double` |

When designing a stable C API for JNA/JNI, prefer fixed-width types like `int32_t`, `int64_t`, and `uint32_t` from `stdint.h` where appropriate, paired with explicit contracts for pointer-sized types.

### 11.2. Calling conventions

Depending on platform and ABI, `cdecl`, `stdcall`, `fastcall`, or platform conventions differ in argument passing and stack cleanup.

JNA interfaces must declare matching calling conventions, such as `StdCallLibrary` for applicable Windows APIs. Mismatched conventions produce hard-to-diagnose corruption or crashes.

In JNI, using proper `JNIEXPORT`/`JNICALL` macros and `javac`-generated headers helps prevent calling-convention errors.

### 11.3. The C++ ABI is not a universally stable C ABI

C++ introduces name mangling, overloading, class layouts, vtables, exceptions, and standard-library ABIs tied to compiler, platform, and version.

To expose a C++ library cleanly to JNA or multiple runtimes, consider publishing a **C ABI facade**:

~~~cpp
extern "C" {
    int nativecalc_add(int a, int b) {
        return a + b;
    }
}
~~~

On Windows DLLs, exporting symbols in the dynamic export table may also require export annotations or `.def` files. `extern "C"` governs C linkage rather than automatically guaranteeing symbol exports or full ABI compatibility.

## 12. Structure layout, alignment, and packing

A C struct:

~~~c
#include <stdint.h>

struct SensorReading {
    uint8_t status;
    double value;
    uint32_t sequence;
};
~~~

does not have a naive "sum of field sizes" layout. Compilers insert padding bytes to align `double` and subsequent members.

When JNA maps this to a `Structure`, field order and layout/packing rules must match the native ABI. Mismatched alignment silently reads garbage in `value` or `sequence` without immediate crashes.

### 12.1. Inspect sizeof and offsetof

A reliable way to document the native ABI is writing a small C probe:

~~~c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("sizeof=%zu\n", sizeof(struct SensorReading));
    printf("value_offset=%zu\n",
           offsetof(struct SensorReading, value));
    printf("sequence_offset=%zu\n",
           offsetof(struct SensorReading, sequence));
    return 0;
}
~~~

In a complete probe, include the struct definition above, then compare actual sizes and offsets against Java mappings on every supported platform.

### 12.2. JNA Structure and field order

A JNA mapping can use `Structure` and `@FieldOrder`:

~~~java
import com.sun.jna.Structure;

@Structure.FieldOrder({
    "status", "value", "sequence"
})
public class SensorReading extends Structure {
    public byte status;
    public double value;
    public int sequence;
}
~~~

This illustrates field ordering and basic types. **It is not enough on its own to guarantee ABI alignment across platforms**: verify padding, packed attributes, unsigned semantics, and platform-specific layouts.

Structs containing pointers, unions, arrays, bit-fields, or nested structs are even trickier; test directly against the native binary.

### 12.3. Changing compiler flags can break the ABI

Changing `-fpack-struct`, `#pragma pack`, compiler flags, C++ standard library versions, or alignment rules can shift struct layouts even while struct and field names remain untouched.

Upgrading C/C++ compilers alongside a JDK upgrade must therefore be treated as an independent ABI change.

## 13. Pointers, buffers, and memory ownership

Java GC manages Java object lifetimes, yet does not automatically free allocations created by native code.

Native example:

~~~c
void* native_alloc(size_t size);
void native_free(void* ptr);
~~~

If Java receives pointers from `native_alloc`, contracts must specify **who calls `native_free`** and when.

### 13.1. Critical ownership questions

- Does the caller or callee allocate?
- Who frees?
- Can pointers outlive the call?
- Are pointers invalidated when an object/context closes?
- Can multiple threads use the pointer concurrently?
- Does the function point to static, stack, or heap memory?
- Must a paired free function from the exact same native library be called?
- Can a pointer returned by one instance be freed by another?

Never free memory allocated by allocator A using allocator B unless the API explicitly guarantees compatibility. On Windows, mismatched CRT heaps are especially dangerous; across all platforms, ownership rules must hold strictly.

### 13.2. JNA Memory and Pointer

JNA provides abstractions such as `Pointer` and `Memory` for native regions. `Memory` tracks JNA-allocated/managed regions; `Pointer` is merely a reference and does not imply authority to free arbitrary native allocations.

If a callback passes Java a temporary `Pointer` valid only during that callback, never cache that `Pointer` for reading after native code frees it.

### 13.3. DirectByteBuffer and JNI

JNI can create or access direct buffers to avoid copying in data pipelines. However:

- Buffers have distinct lifetimes and ownership.
- Native backing pointers must remain valid while Java accesses them.
- Never read/write after native free.
- Thread safety must be preserved explicitly.
- Byte order may need explicit configuration.
- Never assume zero-copy is always fastest or safest.

A direct buffer pointing to freed memory can crash the JVM outside normal Java exception handling.

## 14. JNI references: local, global, and weak global

JNI forbids native code from holding onto Java object references arbitrarily.

### 14.1. Local references

Local references stay valid within the active native call/thread scope per JNI rules. Never cache a local `jobject` in a global C variable and reuse it after the native call returns.

### 14.2. Global references

When native code must retain a Java object across calls or callbacks, create a global reference via `NewGlobalRef` and free it via `DeleteGlobalRef` once unneeded.

~~~c
jobject globalRef = (*env)->NewGlobalRef(env, someObject);

/* Use within valid lifetime. */

(*env)->DeleteGlobalRef(env, globalRef);
~~~

The example assumes valid `env` and `someObject`. Handle `NewGlobalRef` failure and pending exceptions per JNI rules.

Global references keep Java objects alive across GC; forgetting `DeleteGlobalRef` leaks Java heap memory even if native RSS barely grows.

### 14.3. Weak global references

Weak global references carry different semantics from strong global references. Native code must never assume the referent stays alive; check/promote using proper JNI APIs before accessing it.

Native caches must never treat weak references as permanently valid raw pointers.

### 14.4. Local references inside large loops

When native code allocates numerous Java object references inside a tight loop without returning to Java, local references accumulate. Use `DeleteLocalRef` or `PushLocalFrame`/`PopLocalFrame` appropriately.

This failure often appears only under large batches or stress tests rather than single native calls.

## 15. JNI and the Garbage Collector

GC can relocate Java objects in memory. Native code must never assume a Java object's address stays fixed simply because it holds a `jobject`.

JNI defines explicit APIs for accessing arrays, strings, and regions. Calls like `GetByteArrayElements` may return either a direct pinned pointer or a copy depending on JVM/conditions; always pair with `ReleaseByteArrayElements` per API rules.

### 15.1. GetPrimitiveArrayCritical

Critical APIs carry strict rules. While holding critical array access, native code must avoid long operations, blocking calls, or arbitrary JNI calls violating the contract, as doing so stalls GC and causes latency spikes.

Never use Critical APIs as a clever zero-copy shortcut around multi-second I/O.

### 15.2. Native code and safepoints

Long-running native calls, long-held resources, or uncooperative native loops can impact JVM latency and observability. Never expect native code to respond automatically to `Thread.interrupt`, shutdown hooks, or GC pauses like blocking Java APIs.

When migrating JDKs or GCs, measure pause times, throughput, and native-thread interactions under realistic workloads.

## 16. Native threads calling back into the JVM

Native libraries may spawn threads via pthreads, Windows threads, or similar APIs. Those threads do not automatically possess a valid `JNIEnv` to call Java APIs.

### 16.1. JNIEnv is thread-local

`JNIEnv*` belongs strictly to one thread context. Never cache a `JNIEnv*` from Thread A and use it on Thread B.

To call Java from a native-created thread, attach it via `JavaVM`:

~~~c
JavaVM *vm = /* Validly supplied JavaVM */;
JNIEnv *env = NULL;

/* Conceptual example; check return code and version. */
jint rc = (*vm)->AttachCurrentThread(vm, (void**)&env, NULL);

if (rc == JNI_OK) {
    /* Call JNI APIs using the current thread's env. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

This illustrates API shape rather than complete production C code. Real implementations must track whether the thread was already attached, handle errors and pending exceptions, and avoid detaching JVM-owned threads improperly.

### 16.2. Callback guidelines

- Define clear ownership of native threads.
- Attach native-created threads before invoking JNI.
- Use each thread's own `JNIEnv`.
- Never pass invalid local references across threads.
- Use lifetime-managed global references where needed.
- Catch/handle Java exceptions crossing callbacks.
- Detach threads when attach scope ends.
- Never hold native locks across Java callbacks that may re-enter native code if deadlocks can occur.

A callback passing single-threaded tests can deadlock in production when a Java callback acquires a lock while native code already holds one.

## 17. Java exceptions and native errors

Java exceptions and native error codes do not translate automatically in either direction.

### 17.1. JNI pending exceptions

When native code invokes a Java method via JNI and that method throws, native code must handle the pending exception properly. Most JNI operations must not continue arbitrarily while an exception is pending.

Use `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, and related APIs per JNI contracts. **Never call `ExceptionClear` just to swallow errors and "keep code running" without a recovery contract.**

### 17.2. Native errors

C APIs typically report errors through:

- Return codes.
- `errno`.
- `GetLastError` on Windows.
- Error objects/structs.
- Thread-local last-error state.
- Internal C++ exceptions.

Java wrappers must map them into meaningful result types or exceptions.

Example:

~~~java
public final class NativeResult {
    public final boolean success;
    public final int errorCode;

    public NativeResult(boolean success, int errorCode) {
        this.success = success;
        this.errorCode = errorCode;
    }
}
~~~

This illustrates a simple DTO. In production, verify which error space codes come from, when they are read, and whether subsequent native calls overwrite them.

### 17.3. Never let C++ exceptions cross a C/JNI boundary

C++ exceptions must never unwind uncontrollably out of C/JNI ABI functions. Catch them inside the native wrapper boundary, release resources, and translate into Java exceptions or return codes per contract.

Likewise, JNI code must never assume the JVM automatically cleans up native allocations if an exception occurs mid-operation.

### 17.4. Protect data against native crashes

A native segmentation fault or access violation can terminate the entire JVM process, unlike a catchable Java `NullPointerException`. For untrusted native work or unstable third-party libraries, consider isolating them in a **separate OS process** communicating via IPC/gRPC/messages instead of running in-process with the main JVM.

## 18. JNA callbacks and lifetime

JNA can map Java callbacks onto C function pointers when appropriate, yet callbacks carry lifecycle requirements too:

- Does the native library retain the function pointer after registration returns?
- Is the Java callback object kept strongly referenced long enough?
- Are callbacks invoked from native-created threads?
- Do calling conventions match?
- May callbacks throw Java exceptions, and how does the wrapper handle them?
- Can callbacks be unregistered/cancelled cleanly during shutdown?

If Java GC collects the callback object while native code still holds its pointer, later invocations fail catastrophically. Closing a native context while a callback runs also risks use-after-free.

A robust design provides explicit register/unregister APIs, strong references while active, and synchronization between callback execution and context shutdown.

## 19. Classloaders and native library reloadability

Enterprise Java apps can use multiple classloaders:

~~~text
Bootstrap / Platform
        |
        v
Application loader
        |
      +-+-----------------+
      |                   |
      v                   v
Plugin loader A      Plugin loader B
      |                   |
      v                   v
JNI wrapper A        JNI wrapper B
~~~

If two classloaders attempt to load the same native library in ways the JVM disallows, failures occur such as:

~~~text
Native Library ... already loaded in another classloader
~~~

Copying `.so` files to two different paths is rarely a general fix. Native libraries may hold global state, singleton handles, native threads, or static caches unsafe for duplicate instances.

### 19.1. Problems when redeploying WARs or plugins

When a web application undeploys:

- The Java classloader can become eligible for collection if unreferenced.
- Native code may still retain global JNI references.
- Native threads may still be running.
- Callbacks may still target classes from the old classloader.
- The native library may not unload when expected.

This produces classloader leaks or failures on the next redeploy.

Manage explicit lifecycles, native thread shutdown, and global references. If a library cannot unload/reload cleanly, isolating deployments into separate processes/containers fits better.

## 20. Native agents, Java agents, and JVMTI

Because this chapter covers **Agent and Native Code**, investigating any JNI/JNA app should also inventory agents attached to the JVM.

### 20.1. Java agents

Java Instrumentation uses:

~~~bash
java -javaagent:/opt/agents/monitor.jar -jar app.jar
~~~

Java agents may transform bytecode, append to bootstrap search paths, or rely on module-access options depending on implementation. They need not contain native code, yet still depend on JDK internals or bytecode-instrumentation compatibility.

### 20.2. Native JVMTI agents

Native agents can be configured with:

~~~bash
java -agentpath:/opt/agents/libprofiler.so -jar app.jar
~~~

or `-agentlib` with a logical library name where appropriate.

JVMTI agents rely on JVMTI entry points and capability/event mechanisms, differing from JNI libraries exporting native methods. Agents must support the target JDK, architecture, OS, and JVM implementation.

### 20.3. Changes that can break agents

- JVMTI capability/event behaviors no longer matching agent expectations.
- New JVM instrumentation semantics or class-file versions.
- Wrong native dependencies or ABIs.
- Java module encapsulation blocking agent reflective access.
- Agents attached at different lifecycle stages or via dynamic attach.
- JDK changes to warning or native/dynamic-agent-loading policies.
- Agents lacking support for virtual threads or newer runtime features.
- Version mismatches between the agent and framework/monitoring backend.

Upgrading application JARs while overlooking profiler/APM/security agents is a common Java migration mistake.

### 20.4. Agent startup needs a rollback plan

If an agent causes JVM crashes or slow startup, prepare config paths to disable the agent and start the service in fallback mode when operational policy permits.

Never disable mandatory security agents without proper controls and approval.

## 21. Native access restrictions and modern JDKs

Modern JDKs are evolving warnings and restrictions around native access to clarify which modules rely on JNI or the Foreign Function & Memory API.

For example, recent releases introduce `--enable-native-access` to grant specific modules permission for restricted native operations, alongside release-specific warnings, diagnostics, or policies governing illegal native access.

Key considerations:

- Exact flag behaviors and scopes **depend on the JDK version**.
- Not every JDK release enforces identical default policies.
- JNA or JNI libraries may need version upgrades to stay compatible.
- A warning does not mean execution was blocked; conversely, zero warnings does not prove complete compatibility.
- Never suppress all warnings or grant overly broad permissions blindly to hide bugs.

When targeting a new JDK, consult release notes for **that exact JDK release** plus your native library/agent documentation. Supporting JDK 17 does not guarantee a library works on JDK 25 or later.

### 21.1. --enable-native-access does not fix ABI bugs

If `nativecalc.so` is an ARM64 binary while the JVM runs on x86-64, native access flags will not help.

If a C struct layout is wrong, granting native access will not prevent memory corruption.

If Java cannot locate a JNI symbol, fix the library name, symbol, or native signature.

Separate native access permissions cleanly from binary and runtime compatibility.

## 22. Where is the Foreign Function & Memory API a modern choice?

The Foreign Function & Memory (FFM) API became standard in Java 22. It offers an integrated Java API to describe memory segments, layouts, and foreign function invocations.

Unlike JNI, FFM lets many use cases invoke C ABIs without writing traditional JNI glue code. Key design benefits include:

- Explicit native memory layout descriptions.
- Scoped lifetime management via dedicated abstractions.
- Method-handle-based downcalls to native functions.
- Upcall stubs for callbacks when needed.
- Controlled lifetimes for memory segments.

However:

- APIs and support depend on the JDK version.
- Native access restrictions and policies still apply.
- C ABIs, struct alignment, pointer semantics, and concurrency remain critical.
- Migrating from JNA/JNI to FFM can be a major refactor.
- Apps running on Java 17 cannot use Java 22's final FFM API directly.

### 22.1. Do not force JNI/JNA-to-FFM rewrites in the same step

If your immediate objective is moving Java 11 to 17 or supporting multiple JDKs, rewriting every native binding to FFM exceeds scope. Split the work:

1. Verify existing JNI/JNA runs safely on the target JDK.
2. Upgrade wrapper dependencies and native artifacts.
3. Stabilize contract tests.
4. Evaluate FFM as a separate architectural choice once your Java baseline allows.

JNI remains valuable for integrations interacting deeply with Java objects and JVM internals, and JNA remains practical for straightforward C ABIs; FFM is an option, not an immediate mandate to rewrite legacy code.

## 23. Distributing native binaries by platform

Applications targeting multiple environments need a reliable mechanism to select the right binary.

Example packaging layout:

~~~text
native/
  linux-x86_64/
    libnativecalc.so
  linux-aarch64/
    libnativecalc.so
  windows-x86_64/
    nativecalc.dll
  macos-aarch64/
    libnativecalc.dylib
~~~

This illustrates one structure rather than a mandatory standard.

Some Maven artifacts use classifiers:

~~~text
nativecalc-1.2.0-linux-x86_64.jar
nativecalc-1.2.0-linux-aarch64.jar
nativecalc-1.2.0-windows-x86_64.jar
~~~

Distribution logic must detect OS/architecture accurately, extract into properly permissioned paths, check file integrity, and avoid races when multiple processes start concurrently.

### 23.1. Do not rely solely on os.name

`os.name` and `os.arch` provide hints yet sometimes return unexpected strings or fail to distinguish libc/ABI variants. Inspect packaging policies and real runtime environments too.

### 23.2. Native resources inside JARs must be extracted

`System.loadLibrary` cannot open arbitrary `.so` entries directly from inside a JAR as dynamic libraries. Many libraries extract files onto the local filesystem and invoke `System.load` with the absolute path.

Failure points include:

- Temp directory mounted `noexec`.
- Insufficient read/write permissions.
- Antivirus or OS security policies blocking execution.
- Extracted files cleaned prematurely.
- Two processes racing to extract the exact same filename.
- Missing checksum/signature checks.
- Symlink or path-traversal flaws in extraction logic.
- Missing cleanup on shutdown.

In containers with read-only root filesystems, mount a writable/executable directory or install native libraries directly into the image cleanly.

## 24. Building native libraries with a separate toolchain

Maven and Gradle can orchestrate C/C++ builds, yet `maven-compiler-plugin` and `JavaCompile` do not compile C code themselves. Native layers require toolchains such as gcc/clang/MSVC, CMake, or equivalent build systems.

Example workflow:

~~~text
Java source
     |
     v
javac -h -> JNI header
     |
     v
C/C++ source + generated header
     |
     v
Native compiler/linker
     |
     v
.dll / .so / .dylib
     |
     v
Package per OS/architecture
     |
     v
Integration tests on target JDK
~~~

A project can drive native builds via CMake while matching compiler, output library name, and flags per platform. Never assume a Linux build command suffices for Windows or macOS binaries.

### 24.1. JDK-specific JNI headers

`jni.h` and platform-specific headers ship with each JDK. Native compilers must point include paths to the appropriate JDK target/build headers.

You can compile against one JDK's headers and run across other JDKs when sticking strictly to supported JNI APIs and preserving ABIs, provided you test both lowest and highest supported versions. Never depend on private JVM headers or HotSpot internal structs as stable APIs.

### 24.2. Compiler and linker versions must also be pinned

An `.so` compiled against a newer `libstdc++` than production may demand unavailable symbol versions. Keep build images and runtime images on compatible baselines.

Never pin only the Java JDK while overlooking:

- gcc/clang/MSVC versions.
- glibc/musl baselines.
- C++ standard libraries.
- OpenSSL/native dependencies.
- Linker flags, visibility, and rpath/runpath.
- Target CPU instruction sets.
- Minimum OS deployment targets.

## 25. Diagnostic tools for native libraries

The tools below aid troubleshooting; availability varies by OS.

### 25.1. Java and runtime

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Inspect Java home, architecture, `java.library.path`, and system properties. Never dump full environments containing secrets into public logs.

### 25.2. Inspecting files on Linux

~~~bash
file libnativecalc.so
~~~

Inspect ELF architecture/header metadata:

~~~bash
readelf -h libnativecalc.so
~~~

Inspect dynamic dependencies:

~~~bash
readelf -d libnativecalc.so
~~~

Inspect exported symbols:

~~~bash
nm -D libnativecalc.so
~~~

or:

~~~bash
objdump -T libnativecalc.so
~~~

These commands pinpoint missing JNI or C API symbols. Available tools and flags differ by platform.

### 25.3. Checking runtime dependencies

~~~bash
ldd libnativecalc.so
~~~

On Linux, `ldd` reports dependency resolution, though exercise caution with untrusted binaries and `ldd` behavior. For untrusted artifacts, inspect statically via `readelf`/`objdump` or appropriate isolated tooling.

On macOS use `otool`; on Windows use `dumpbin` or equivalent PE tools.

### 25.4. JVM fatal error logs

When native code crashes the JVM, it typically writes a log such as:

~~~text
hs_err_pid12345.log
~~~

Such logs often capture:

- The failing native frame.
- JVM/JDK version and build.
- Crashing thread.
- Loaded native libraries.
- Stack and CPU registers.
- OS signal or exception.

Never post raw crash logs to public channels, as they can leak file paths, arguments, hostnames, or sensitive memory/env data. Analyze them alongside native symbols/debug info and crash repros.

### 25.5. Do not confuse core dumps with Java stack traces

A native SIGSEGV generally cannot be caught via Java `catch (RuntimeException)`. Investigating it can require core dumps, minidumps, native debuggers, AddressSanitizer, or suitable memory-checking tools.

In production, enabling core dumps requires security reviews and disk-space limits.

## 26. Common JNI/JNA errors

### 26.1. UnsatisfiedLinkError: no ... in java.library.path

Example:

~~~text
java.lang.UnsatisfiedLinkError:
no nativecalc in java.library.path
~~~

Possible causes:

- Native library not distributed.
- Wrong logical library name.
- Wrong search path.
- Extraction failed.
- Missing file inside deployment container.
- Faulty classloader/loading logic.

Resolution: confirm the file exists for the exact platform and trace actual load paths. Avoid broadening global `PATH`/`LD_LIBRARY_PATH` blindly when targeted config works.

### 26.2. UnsatisfiedLinkError: native method implementation not found

~~~text
java.lang.UnsatisfiedLinkError:
'long com.example.nativebridge.NativeMath.sum(long, long)'
~~~

Possible causes:

- No matching JNI symbol exists.
- Native method renamed, moved packages, or changed signature.
- Wrapper passed invalid `RegisterNatives` mappings.
- Older native library loaded instead of updated one.
- Overloaded method name mapping mismatch.

Inspect generated headers and exported symbols.

### 26.3. Wrong ELF class, invalid image, bad CPU type

Almost always wrong bitness, CPU architecture, or binary format. Build/package binaries for the exact target platform.

### 26.4. Symbol lookup error or missing native dependency

The top-level library exists yet a transitive dependency fails to resolve or clashes on ABI version. Inspect shared library dependencies, `rpath`/`runpath`, and native runtime images.

### 26.5. JNA Function not found

JNA located the library, yet the target function is unexported or differs in mangling/calling convention. Check exported symbols in the native binary and your JNA interface bindings.

### 26.6. Crash after invoking a function

Potential causes:

- Invalid pointer or expired memory lifetime.
- Mismatched struct alignment.
- Wrong calling convention.
- Wrong Java `int`/`long` mapping.
- Use-after-free or double free.
- Garbage-collected callback object.
- Data race or thread-unsafe native library.
- Native exception escaping across the ABI boundary.

Never treat successful library loading as proof that the ABI matches.

### 26.7. JVM crashes only during GC or shutdown

Commonly caused by misused local/global references, stale native pointers to Java objects, callbacks firing after context teardown, critical array misuse, or un-detached native threads.

### 26.8. Agents break only on newer JDKs

Commonly caused by JVMTI capabilities, bytecode instrumentation, module access rules, native access policies, or vendor/JDK incompatibilities. Check both agent and target JDK release notes.

## 27. How to test libraries accurately against the target JDK

Do not call one simple native function and declare the whole integration safe. Test suites should cover critical boundaries.

### 27.1. Loading tests

- Matching OS/CPU/bitness.
- All native dependencies present.
- Correct file permissions and execution policies.
- Proper container load paths.
- Multi-classloader isolation without conflicts.
- No accidental loading of older system-installed libraries.

### 27.2. Data tests

- Java `int`/`long` boundary values.
- Signed/unsigned native integer conversions.
- Null pointers and null Java references.
- Unicode, emojis, and non-BMP characters.
- Strings with embedded null characters or special bytes.
- Struct layouts and packing.
- Long and empty arrays/buffers.
- Negative error codes.
- Unsupported argument combinations rejected gracefully.

### 27.3. Memory tests

- Repeated allocate/free cycles.
- Double-close or close idempotency.
- Post-close calls fail cleanly.
- Native context stays valid throughout callbacks.
- GC stress tests verifying reference lifetimes.
- Direct buffer lifetimes.
- Native RSS growth over long runs.
- Error paths freeing allocated resources.

### 27.4. Concurrency tests

- Multiple Java threads calling shared native contexts.
- Concurrent native callbacks.
- Attaching/detaching native-spawned threads.
- Shutdown while callbacks are active.
- Cancelling/interrupting blocked native calls.
- Plugin redeploys and classloader cleanup.
- Thread safety of upgraded native libraries.

### 27.5. Operational tests

- Containers with read-only root filesystems.
- `noexec` temporary directories.
- Varying OS/CPU platforms.
- Running alongside debug/monitoring agents.
- Security providers/FIPS modes where required.
- Graceful shutdowns and restarts.
- Upgrading and rolling back library artifacts.

## 28. Native compatibility matrix

Sample test matrix:

| Java runtime | OS / architecture | Native artifact | Expectation |
|---|---|---|---|
| JDK 17 | Linux x86-64 glibc | `linux-x86_64` `.so` | Baseline |
| JDK 21 | Linux x86-64 glibc | `linux-x86_64` `.so` | Migration target |
| JDK 21 | Linux ARM64 | `linux-aarch64` `.so` | Architecture support |
| JDK 21 | Windows x86-64 | `windows-x86_64` `.dll` | ABI/calling convention |
| JDK 21 | macOS ARM64 | `macos-aarch64` `.dylib` | Packaging/security |
| Target JDK | Linux musl | musl-compatible `.so` | If Alpine is supported |
| Target JDK | JVM with native agent | Compatible agent release | Observability/instrumentation |

This matrix is illustrative. Select Java versions and platforms matching your product support policy, and never claim support for combinations lacking built native binaries and test runs.

### 28.1. When supporting only a single platform

If a product deploys solely on Linux x86-64 with glibc, Windows/macOS binaries may be unnecessary. Even then, verify changes such as:

- Newer container base images.
- Newer CPU instance types.
- Updated glibc and native dependency versions.
- JDK vendor differences.
- Kernel/OS policies.
- Dynamic loader search paths.
- Debug/monitoring agents.

Having no "cross-platform" requirement does not eliminate ABI risk.

## 29. Phased migration strategy

### Phase 1 — Inventory the native surface

List:

- Java `native` methods.
- JNA interfaces and loaded library names.
- Native libraries embedded in JARs.
- `System.load`/`System.loadLibrary` call sites.
- Java agent and native agent flags.
- `JNI_OnLoad` and `RegisterNatives`.
- Java→native and native→Java callbacks.
- Native dependency graphs.
- Actual production platforms.

Sample inventory table:

| Component | Mechanism | Native file | Owner | JDK/platform support |
|---|---|---|---|---|
| `image-engine` | JNI | `libimage.so` | Vendor A | Needs verification |
| `win-device` | JNA | `device.dll` | Team B | Windows x86-64 |
| `APM profiler` | JVMTI agent | `libprofiler.so` | Vendor C | Needs verification |
| `crypto-provider` | JNI/PKCS#11 | `provider.so` | Security team | Separate policy |

### Phase 2 — Capture baseline and artifacts

Record:

- Old JDK and target JDK.
- JVM vendor/implementation.
- OS, architecture, and libc.
- C/C++ compiler/linker versions.
- Native dependencies.
- Library hashes/versions.
- Java wrapper/JNA versions.
- Container base image.
- Native access and agent flags.

### Phase 3 — Upgrade to vendor-supported releases

Prefer JNI/JNA/native agent versions officially documented by vendors to support the new JDK and OS. Avoid hand-patching closed-source binaries when official releases exist.

If a library lacks ARM64 builds or new-JDK support, plan replacement or process isolation prior to rollout instead of discovering it in production.

### Phase 4 — Keep Java/native contracts stable

Avoid changing Java native declarations, native ABIs, package names, and serialization contracts simultaneously unless strictly necessary. When an ABI change is unavoidable, version wrappers and libraries together and protect older consumers through planned releases.

### Phase 5 — Build and package native binaries

Compile for each target OS/CPU/libc using appropriate toolchains; verify symbol exports and dependency graphs; record checksums and artifact provenance.

### Phase 6 — Run integration and stress tests

Run against the exact final JDK and container. Exercise concurrent access, GC, callbacks, memory lifetimes, shutdowns, and error paths. On native crashes, collect fatal error logs and core dumps per security policy.

### Phase 7 — Canary and observe

Monitor:

- Startup library load failures.
- Native crashes.
- RSS memory and native allocations.
- Thread counts.
- Boundary-call latency.
- JNI/JNA error rates.
- GC pause times.
- Agent overhead.
- Resource cleanup.
- Business error rates.

### Phase 8 — Realistic rollback

Rollback may require reverting the Java JARs, native `.so`/`.dll` binaries, container base images, and agent versions together. If a native library wrote newer file or database formats, check whether older versions can read them.

Never assume rollback means swapping only the JDK image. When ABIs or state formats change, versions may not share state cleanly.

## 30. End-to-end example: migrating a JNI library from an older JDK to a newer JDK

Suppose a system has:

~~~text
Java application: Java 11
JNI wrapper: native-image-bridge.jar
Native library: libimagebridge.so
OS: Linux x86-64
Container: glibc-based
Agent: native APM profiler
~~~

Goal: JDK 21, with potential future deployment on Linux ARM64.

### Step 1 — Inventory APIs and ABIs

Locate native methods in JARs; inspect headers/signatures, `JNI_OnLoad`, callbacks, `jlong` handles, and memory ownership.

### Step 2 — Inspect native binaries

Use `file`/`readelf`/`nm` or equivalent tools to verify ELF architecture, exported JNI symbols, C++ dependencies, and glibc baselines.

### Step 3 — Verify vendor support

Upgrade the JNI wrapper and profiler to JDK-21-supported versions. If `libimagebridge.so` relies strictly on stable public JNI APIs, it may run without rebuilding, yet must still be verified on the new JDK.

### Step 4 — Build and package by architecture

For ARM64, compile an ARM64 native library; never reuse an x86-64 `.so`. Audit transitive native dependencies, especially image-processing libraries and CPU instruction requirements.

### Step 5 — Test logic and data

Test small/large images, boundary types, Unicode filenames, allocations, error paths, and Java/native callbacks.

### Step 6 — Stress test

Exercise multi-threaded loads and active GC; watch native RSS, thread counts, leaks, and crash logs.

### Step 7 — Test the production image

Validate the exact container base image, any read-only/`noexec` policies, deployment permissions, agent flags, and toolchain runtime dependencies.

### Step 8 — Canary and rollback

Route partial traffic via canary while monitoring crashes, errors, and memory. Prepare coordinated rollback covering the Java wrapper, native library, and agents — not the JDK alone.

Throughout the process, no step can be skipped merely because Maven or Gradle reports a green build.

## 31. Common misconceptions

### "JNI is a standard API, so every old native library runs on every new JDK"

False. While JNI defines a stable interface contract, binaries may still rely on private JVM internals, changed security policies, ABIs, native dependencies, or runtime behaviors.

### "JNA uses no native code"

False. JNA's runtime includes native components to invoke native libraries; it only reduces hand-written JNI glue in many cases.

### "Java long equals C long on every OS"

False. C `long` varies by ABI; Java `long` is always 64-bit.

### "Successful library loading proves ABI compatibility"

False. Struct layout bugs, pointer lifetime flaws, or calling convention mismatches may crash only when specific functions run.

### "Changing java.library.path fixes every UnsatisfiedLinkError"

False. Wrong CPU/OS binaries, missing transitive native libraries, or missing JNI symbols are not solved by search paths.

### "JNIEnv works from any thread"

False. `JNIEnv` is bound to one thread context. Native-spawned threads must attach properly.

### "GC cleans up native memory too"

False. Native allocations and handles normally require explicit cleanup via native APIs. Global JNI references also require timely deletion.

### "A JNA Pointer owns its backing memory"

Not always. A `Pointer` may reference memory owned by the library, caller, callback, or another object.

### "Two versions of a native library can mix freely across classloaders"

Never assume this. JVM load rules, global native state, and thread/reference lifetimes readily cause conflicts or leaks.

### "The agent is a Java JAR, so native compatibility doesn't apply"

Not every agent is pure Java. APMs, debuggers, and profilers may rely on JVMTI/JNI or bundled native components.

### "--enable-native-access fixes missing .so errors"

False. Native access policies and OS dynamic linking/ABIs operate at completely different layers.

### "FFM replaces all JNI code with no contract changes"

False. FFM has its own APIs, JDK baseline, and memory lifetime model; certain JVM-level use cases still need JNI/JVMTI.

### "No Java exception means the native call succeeded"

False. Native code can corrupt memory, leak resources, or fail silently before crashing later. Inspect error codes, invariants, and resource state.

## 32. Compatibility check record template

~~~text
JAVA APPLICATION
  App/module:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  Framework:
  Java agent(s):
  Native agent(s):
  Java runtime options:

NATIVE DEPENDENCY
  Library name:
  JNI / JNA / FFM / JVMTI:
  Java wrapper version:
  Native binary version/hash:
  Native build toolchain:
  Required OS:
  Required architecture:
  32/64-bit:
  libc / C++ runtime dependencies:
  External native dependencies:

BINDING CONTRACT
  Java method/interface:
  Native symbol:
  Calling convention:
  Parameter and return types:
  Struct layout/alignment:
  String encoding:
  Error mapping:
  Callback contract:

MEMORY AND THREADING
  Allocation owner:
  Release/free API:
  Native handle lifetime:
  Local/global JNI references:
  Native thread attach/detach:
  Callback lifetime:
  Concurrent use allowed?:
  Shutdown/cleanup path:

LOADING AND PACKAGING
  loadLibrary/load path:
  java.library.path / JNA path:
  Extracted native artifacts:
  Filesystem permissions:
  Classloader behavior:
  Container/base image:
  Code signing/security policy:

VALIDATION
  JVM load:
  Symbol resolution:
  Dependency resolution:
  Boundary numeric values:
  Unicode/string data:
  Struct layout:
  Null/error cases:
  GC/memory stress:
  Concurrent callbacks:
  Shutdown/redeploy:
  Agent compatibility:
  Multi-platform matrix:
  Canary metrics:
  Rollback:

DECISION
  Compatible:
  Vendor upgrade required:
  Rebuild required:
  Platform-specific exception:
  Owner:
  Deadline:
~~~

A strong record specifies **which exact artifact was verified against which JDK, OS, architecture, and native dependency versions**, rather than writing a vague "JNI supported".

## 33. Summary

Native compatibility in a Java application is a multi-layer contract. Even when the JVM keeps the JNI API unchanged, applications still fail due to wrong binary architectures, shifted C ABIs, missing native dependencies, use-after-free pointers, or agents incompatible with the new JDK.

Core principles:

1. **Identify the exact mechanism:** JNI, JNA, FFM, Java agents, and JVMTI have distinct scopes.
2. **Never confuse Java binary compatibility with native ABI compatibility:** valid `.class` files do not guarantee valid `.so`/`.dll` binaries.
3. **Verify types and layouts carefully:** `jlong`, C `long`, pointer widths, struct packing, calling conventions, and encodings must all align.
4. **Define clear ownership:** memory, handles, JNI references, callbacks, and threads need explicit lifecycles.
5. **Audit the full load chain:** file presence, OS/CPU, libc, transitive native libraries, symbols, classloaders, and permissions.
6. **Upgrade agents and wrappers together:** not just app JARs, but also JNA runtimes, JNI libraries, and APM/JVMTI agents.
7. **Test real packaged artifacts on real runtimes:** use the target JDK, container, OS/architecture, and concurrency/GC/shutdown suites.
8. **Deploy with coordinated rollback:** Java bytecode, native binaries, base images, and agent versions may all have to roll back together.

A thorough migration is not merely getting the JVM to load a native library without throwing immediately. It must prove the application exchanges data accurately, honors ABIs, avoids leaks, survives heavy concurrency without crashing, and runs safely across every committed production environment.
