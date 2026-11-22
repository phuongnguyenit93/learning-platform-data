# x86-64, AArch64 Architecture, and Operating System ABIs

## 1. Why Must Java Migration Care About CPUs and ABIs?

One advantage of Java is that bytecode can run across multiple operating systems and CPU architectures when a compatible JVM is available. However, this guarantee **does not automatically apply to native code** loaded via JNI, JNA, the Foreign Function & Memory API, JVMTI agents, or supporting libraries.

In **Java Advance Compatibility Migration**, an application may move from a Linux x86-64 server to Linux AArch64, from Windows to a Linux container, switch its base image from glibc to musl, or use Apple Silicon for development instead of an Intel machine. When that happens:

- JARs containing Java bytecode can still load and run normally.
- The JDK needs a distribution matching the operating system and architecture.
- Native libraries such as .so, .dll, or .dylib must be compiled for the **right architecture and ABI**.
- Native agents, cryptography libraries, compression libraries, JNI bindings, native database drivers, and transitive dependencies can become failure sources.
- Structs, C data types, calling conventions, and dynamic linking behavior can differ across platforms even when all are called "64-bit".

For example, a JNI library built for Linux x86-64 cannot be loaded directly by a Linux AArch64 JVM. Similarly, a Windows x86-64 DLL cannot be loaded by a Linux x86-64 Java process simply because both run on an x86-64 CPU.

This lesson aims to build the ability to:

1. Distinguish instruction set architecture (ISA), operating system, binary format, and ABI.
2. Compare x86-64 with AArch64 from a native Java perspective.
3. Understand calling convention, data model, dynamic linking, libc, and toolchain constraints.
4. Build JNI/native libraries and package artifacts for each OS/architecture combination.
5. Inspect JNA, FFM API, JVMTI agents, native images, and dependencies containing native code.
6. Design CI matrices and test actually loading and running native code on target platforms.
7. Diagnose UnsatisfiedLinkError, wrong-architecture, missing-symbol, and OS-incompatibility errors.

## 2. Four Foundational Concepts That Must Not Be Conflated

### 2.1. ISA: CPU instruction set

ISA (Instruction Set Architecture) defines the instruction set, registers, and architectural characteristics used by machine code.

Two key ISAs when operating modern Java:

- **x86-64**: 64-bit extension of x86; also called AMD64, Intel 64, or x64 in many documents.
- **AArch64**: the 64-bit execution state of the Arm architecture; commonly called arm64.

Being 64-bit CPUs does not mean machine code is shared. A file containing x86-64 instructions does not turn into an AArch64 file merely by changing file extensions, folder names, or Java application compiler flags.

### 2.2. Operating system

The operating system provides process creation, virtual memory, system calls, dynamic loaders, file permissions, signals, and platform APIs.

Examples:

- Linux x86-64.
- Linux AArch64.
- Windows x86-64.
- Windows on Arm64.
- macOS x86-64.
- macOS arm64.

Even on the same ISA, Windows, Linux, and macOS do not share an entire binary interface. A Linux .so is not compatible with macOS merely because both run on x86-64 CPUs.

### 2.3. ABI: binary-level contract

ABI (Application Binary Interface) is the set of rules enabling compiled machine-code components to communicate with one another. Depending on the platform, an ABI covers:

- Calling convention: passing arguments and receiving return values.
- Register and stack usage, stack alignment, and which registers the caller/callee must preserve.
- Sizes, alignment, and layout of data types/structs.
- Symbol names, name mangling, and how symbols are exported/imported.
- Object/shared-library formats and linking mechanisms.
- Exception unwinding, thread-local storage, and parts of runtime conventions.
- Interaction with system libraries such as the C runtime, libstdc++, or Windows runtime libraries.

ABI differs from API. A C function with the same prototype in a header yet compiled for a different ABI may fail to invoke or misread arguments. Conversely, identical public Java methods do not prove the underlying JNI layer is compatible between Linux x86-64 and Windows x64.

### 2.4. Binary formats and loaders

| Platform | Common Native Format | Shared Library | Common Inspection Tools |
|---|---|---|---|
| Linux x86-64/AArch64 | ELF | .so | file, readelf, ldd, objdump |
| Windows x64/Arm64 | PE/COFF | .dll | dumpbin, sigcheck, or appropriate PE tools |
| macOS x86-64/arm64 | Mach-O | .dylib / framework | file, otool, lipo |

File extensions are only an initial hint. The real loader requires matching binary format, architecture, dependencies, and security constraints.

## 3. Comparing x86-64 and AArch64 in a Java Environment

| Characteristic | x86-64 | AArch64 |
|---|---|---|
| Common names | amd64, x86_64, x64 | aarch64, arm64 |
| Machine instruction set | x86-64 family | Arm 64-bit family |
| Registers and calling convention | Defined by OS ABI, typically using x86-64 registers | Defined by OS ABI, commonly using x0–x7 for integer/pointer arguments in many ABIs |
| Vector/SIMD | SSE/AVX and CPU-dependent extensions | NEON/Advanced SIMD; extensions such as SVE depending on CPU |
| JDK distributions | JVM built for OS + x86-64 | JVM built for OS + AArch64 |
| JNI libraries | Must be an x86-64 binary with matching OS ABI | Must be an AArch64 binary with matching OS ABI |
| Java bytecode | Portable across compatible JVMs | Portable across compatible JVMs |

Java primitive types such as int, long, and double have language-specified sizes consistent across both architectures. However, **C long, pointers, struct padding, alignment, and argument passing on the native side** depend on the platform ABI.

Do not convert Java long to C long out of habit without checking the operating system's data model.

### 3.1. CPU architecture is not the Java language level

These combinations can exist simultaneously:

~~~text
JDK 21 / Linux x86-64
JDK 21 / Linux AArch64
JDK 17 / Windows x64
JDK 21 / macOS arm64
~~~

A Java class file targeting Java 17 is not tied to x86-64; a suitable JVM on AArch64 can run that bytecode too. However, if the same JAR packages a JNI library solely for x86-64 without an AArch64 edition, the application can fail when reaching native functionality.

### 3.2. CPU optimizations can be an additional constraint

Even within x86-64 itself, native binaries built with AVX/AVX2/AVX-512 instruction sets or higher x86-64 microarchitecture levels may fail on older CPUs. On AArch64, optional extensions are not always present either.

Thus, compatibility includes:

1. Matching base ISA.
2. Matching OS ABI.
3. Matching baseline CPU features.
4. Matching libc/runtime dependencies.
5. Matching JDK/JNI/agent contract.

A library with a valid x86-64 ELF file that relies on instruction extensions unsupported by the CPU can hit SIGILL/illegal instruction at execution time.

## 4. ABIs Differ Even on the Same x86-64 CPU

An important example is the **System V AMD64 ABI** on Unix-like systems such as Linux compared with the **Microsoft x64 calling convention** on Windows. Even though both run on x86-64 CPUs, native function call rules differ.

### 4.1. Calling convention: passing arguments and results

Common conventions for integer/pointer arguments:

| Environment | First Registers Typically Used for Integer/Pointer Arguments |
|---|---|
| Linux x86-64 under System V AMD64 | rdi, rsi, rdx, rcx, r8, r9 |
| Windows x64 under Microsoft x64 ABI | rcx, rdx, r8, r9 |
| Linux AArch64 under AAPCS64 | x0 through x7 |

This is a **simplified summary**, not a full ABI specification. Floating-point/vector arguments, varargs, struct returns, shadow space, stack alignment, and special cases have their own rules.

Windows x64 also requires callers to prepare home/shadow space per calling convention; System V AMD64 and Windows x64 also differ in stack management. Do not invoke a native function pointer using another ABI's assumptions.

### 4.2. AArch64 also has multiple OS ABIs

Not every OS running on AArch64 shares the exact same ABI. Linux AArch64 generally follows AAPCS64 conventions for user space; Windows Arm64 and Darwin/macOS arm64 have additional or differing ABI/runtime requirements in areas such as varargs, stack layout, symbol handling, and linkage.

Therefore:

> "I compiled the .so for arm64 on Linux" does not mean that binary becomes a .dylib running on Apple Silicon macOS or a DLL running on Windows on Arm.

With JNI/JNA/FFM, use the proper compiler and target triple for **each OS/architecture**, and consult the exact platform's ABI documentation when binding structs, variadic functions, or custom calling conventions.

### 4.3. Do not guess ABI from x64/arm64 names

A native file built for:

~~~text
linux-x86_64
windows-x86_64
macos-x86_64
linux-aarch64
windows-aarch64
macos-aarch64
~~~

must be treated as distinct variants in packaging workflows, even though some platforms use similar architecture labels.

## 5. Data Models: LP64 and LLP64

A very subtle source of native bugs is assuming "on 64-bit, C long is always 64 bits". That is **not true across all operating systems**.

Two common data models:

| C Type | LP64 (common on 64-bit Linux/macOS) | LLP64 (64-bit Windows) |
|---|---:|---:|
| char | 8 bit | 8 bit |
| short | 16 bit | 16 bit |
| int | 32 bit | 32 bit |
| long | 64 bit | 32 bit |
| long long | 64 bit | 64 bit |
| pointer | 64 bit | 64 bit |

The table describes common ABIs and does not replace compiler/platform documentation in special cases. In Java, long is always signed 64-bit regardless of OS.

### 5.1. Java long to C long mapping bug

Java:

~~~java
public static native long countRecords();
~~~

In JNI, the corresponding return type is **jlong**; do not use C long unverified:

~~~c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_com_example_NativeCounter_countRecords(JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return (jlong)1234567890123LL;
}
~~~

JNI defines fixed types such as jint and jlong under the JNI contract. If a library has its own C API using long, verify the actual width and signedness of long on the target ABI before converting to jlong.

### 5.2. C struct layout and padding

Example struct:

~~~c
struct Record {
    int id;
    long timestamp;
    void *payload;
};
~~~

Field sizes and offsets can differ between LP64 and LLP64 due to C long and alignment. If Java uses ByteBuffer/MemorySegment to interpret a struct via hard-coded offsets taken from Linux and then runs on Windows, data can be misread even though both are 64-bit.

Handling guidelines:

- Use fixed-width C types such as int32_t and int64_t when the C interface genuinely requires fixed widths.
- Use size_t and intptr_t when representing sizes, addresses, or pointer-sized values; do not equate size_t with Java int.
- Pay attention to struct padding, packing pragmas, alignment, nested structs, unions, and bit-fields.
- Determine layout using C headers, the target compiler, and appropriate binding methods.
- Do not serialize raw struct memory layouts directly to files/network formats unless a protocol fully specifies layout and byte order.

### 5.3. Endianness should not be hard-coded

x86-64 typically runs little-endian. Many modern AArch64 environments also use little-endian, yet data-exchange code should not implicitly treat host endianness as the wire format.

ByteBuffer example:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.order(ByteOrder.LITTLE_ENDIAN); // Wire format is defined as little-endian.
buffer.putLong(42L);
~~~

If the protocol requires network byte order/big-endian, explicitly set ByteOrder.BIG_ENDIAN. The goal is making the data contract explicit, not guessing from the running architecture.

## 6. JNI Is a Java/Native Bridge, Not an Automatic ABI Translator

JNI (Java Native Interface) standardizes how Java calls native methods and how native code interacts with the JVM. JNI keeps the Java-side interface relatively stable across JVM implementations, yet **the native library still must be compiled for the target OS, CPU, and ABI**.

Example Java file:

~~~java
package com.example;

public final class NativeMath {
    static {
        System.loadLibrary("sample_native");
    }

    private NativeMath() {
    }

    public static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

Java uses the logical name sample_native so the JVM searches for the library according to native library loading rules on the corresponding platform.

C implementation file:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_com_example_NativeMath_add(JNIEnv *env,
                                jclass clazz,
                                jint left,
                                jint right) {
    (void)env;
    (void)clazz;
    return left + right;
}
~~~

Because the method is static, the second argument receives jclass; for an instance native method, the corresponding argument is jobject. Use JNIEXPORT/JNICALL and jni.h properly per the JNI contract; do not guess calling conventions based on Linux or Windows assumptions.

### 6.1. Generating headers with javac -h

With the source above, a JNI header can be generated by the Java compiler:

~~~bash
javac -h native -d classes src/com/example/NativeMath.java
~~~

The path assumes source lives at src/com/example/NativeMath.java. Generated headers prevent miswriting symbol names, JNI types, and special signatures when code grows complex.

### 6.2. Building a Linux native library

Illustrative example on Linux with gcc, a JDK, and architecture-appropriate headers:

~~~bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -o libsample_native.so \
    native/sample_native.c
~~~

This example builds a simple C JNI library. If there are C++ sources or other system libraries, additional compiler/linker flags and dependencies are needed. The compiler used must emit an ELF binary with the exact architecture and ABI of the target Linux system; running the command on an x86-64 host does not automatically produce an AArch64 binary.

### 6.3. Building a macOS native library

Example on macOS with clang:

~~~bash
clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -o libsample_native.dylib \
    native/sample_native.c
~~~

If a specific architecture is needed, pass the target/arch settings supported by Apple's toolchain. For a Universal binary, each slice must be built properly and combined using appropriate tooling; you cannot merely rename an x86-64 file to arm64.

### 6.4. Building a Windows DLL

On Windows, you need a compiler/toolchain producing a PE/COFF DLL for the right target, such as MSVC or a MinGW toolchain compatible with chosen dependencies. Include jni.h and the JDK's win32 platform header, export JNI symbols properly, and verify runtime DLL dependencies.

Do not use Linux gcc to build an .so and rename it to .dll. DLLs rely on the PE/COFF format, Windows ABI, and Windows loader; a filename does not create those properties.

### 6.5. Running Java + the native library

A Linux example after compiling classes and the native library:

~~~bash
java -Djava.library.path=. -cp classes com.example.NativeMath
~~~

With the matching library, the expected result is 5. In real applications, you can use System.load with an absolute path to a verified artifact, or load via the framework's packaging mechanism. Avoid loading arbitrary libraries from untrusted writable paths.

Key point: javac succeeding does not prove a .so/.dll/.dylib library can be loaded; you must execute a native method on a JVM of the exact OS and architecture.

## 7. JNI Function Names, C++, and Binary Linkage

JNI uses convention-based native method resolution or RegisterNatives. With C++, ensure JNI entry points are exported with the right names/calling conventions; using javac-generated headers helps minimize mistakes.

C++ implementation example:

~~~cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL
Java_com_example_NativeMath_add(JNIEnv *env,
                                jclass clazz,
                                jint left,
                                jint right) {
    (void)env;
    (void)clazz;
    return left + right;
}
~~~

extern "C" prevents C++ name mangling on exported JNI symbols. However, in many javac-generated JNI headers, extern "C" is already handled through matching declaration macros; implement consistently with the header.

### 7.1. C++ ABI is more complex than C ABI

Do not treat C++ classes, std::string, std::vector, or exception types as a durable binary contract across:

- Different compiler vendors.
- Different libstdc++ versions.
- MSVC and other Windows toolchains.
- ABI-affecting build flags.
- Different OS/architecture platforms.

A pragmatic solution is exposing a stable **C-compatible API** at the JNI/JNA/FFM boundary, with fixed types and clear ownership, while keeping the C++ implementation behind an adapter.

Example C interface to avoid exporting std::string directly:

~~~c
#include <stdint.h>
#include <stddef.h>

typedef struct native_context native_context;

native_context *native_create(void);
int32_t native_process(native_context *context,
                       const uint8_t *input,
                       size_t input_length);
void native_destroy(native_context *context);
~~~

The interface above still requires specifying ownership, thread safety, error codes, and per-ABI build instructions. It only illustrates keeping C++ implementation classes off the binary boundary.

### 7.2. Native exceptions and errors

Never throw C++ exceptions directly across the JNI ABI boundary into the JVM. Native code should catch errors on the C++ side and translate them into Java errors via JNI, or return error codes for Java code to handle.

If a native method retains pointers for later use:

- Define which side allocates and frees.
- Do not retain JNI local references past their lifetime.
- Use global references per contract when a Java object must outlive a call.
- Never use raw addresses that were already freed.
- Check concurrency and reentrancy.

Mistakes here can crash the JVM or corrupt memory, unlike ordinary Java exceptions.

## 8. JNA and FFM API Are Also Bound by ABIs

### 8.1. JNA

Java Native Access (JNA) lets you invoke native libraries through interface/structure mappings without always writing a custom JNI wrapper for every function. However, JNA does **not** turn a Windows DLL into a Linux .so and does not automatically fix struct layouts.

When using JNA:

- Check that the JNA version supports the target JDK, OS, and CPU.
- Inspect JNA's own native bootstrap dependency.
- Map integer widths, long, size_t, pointers, wchar_t, and struct alignment per platform.
- Identify the C library's calling convention, especially when supporting Windows.
- Be careful with native-to-Java callbacks and memory lifecycles.

### 8.2. Foreign Function & Memory API

In JDK versions with supported Foreign Function & Memory API, applications can use native linkers, memory layouts, and memory segments to access native code without writing traditional JNI bindings in every case.

FFM does not eliminate OS ABIs. Things that still must be verified:

- Whether the native function and symbol exist in that platform's shared library.
- Calling conventions applied by the JDK's native linker and target ABI.
- C structs, unions, arrays, alignment, pointers, and return values.
- Memory segment lifetimes and ownership.
- Thread access, upcalls/downcalls, and callback safety.
- Native access policies and activation flags under the JDK release in use.

For example, a C header using long or a C struct does not have the same layout on LP64 and LLP64; FFM bindings must declare layouts matching the target rather than hard-coding Linux assumptions and running on Windows.

When migrating FFM, check the JDK version because API stability, class names, and native-access restrictions evolved across releases. Do not copy preview/incubator FFM code from an older JDK into a target JDK without updating it.

### 8.3. When to choose JNI, JNA, or FFM?

| Mechanism | Common Strengths | Things Requiring Caution |
|---|---|---|
| JNI | Deep JVM binding support, long-standing interface, tight native wrapper control. | C/C++ bridge, per-platform toolchains, JNI reference management, memory crashes. |
| JNA | Convenient for calling C-ABI native library APIs without writing per-function JNI wrappers. | Auxiliary runtime, ABI/struct/callback mapping, platform support. |
| FFM | Native linker/memory layout model provided by the JDK in supported releases. | JDK version, native-access policy, layout/ownership, ABI portability. |

No option makes native machine code a single portable artifact across x86-64 and AArch64. Whichever mechanism you pick, build and test binaries for each target OS/architecture.

## 9. Native Agents: JVMTI vs. Java Instrumentation Agents

In the **Agents and Native Code** chapter, distinguish:

**Java agent**: typically packaged as a JAR and uses the Java Instrumentation API via options such as -javaagent. The Java bytecode portion is portable across target JDKs, though the agent may pull in native dependencies or bytecode libraries incompatible with newer JDKs.

**Native JVMTI agent**: built as a .so/.dll/.dylib and loaded by the JVM via -agentlib or -agentpath under the JVM Tool Interface mechanism.

For example:

~~~bash
java -agentpath:/opt/agents/libobserver.so -jar app.jar
~~~

The path above illustrates Linux; on Windows/macOS you need a native artifact matching the OS and architecture. If a Linux x86-64 agent build is placed verbatim into a Linux AArch64 image, the JVM cannot load it properly.

### 9.1. Beyond ISA, JVMTI/JDK compatibility is also required

Native agents must verify:

- JVMTI versions/capabilities provided by the target JDK.
- Callbacks, events, and lifecycles tied to the agent.
- JDK startup options and agent-loading policy changes.
- Compatibility with GC, thread models, and virtual threads when used by the application.
- Agent dependencies and libc requirements.
- Correct handling of instrumented class-file versions.
- Safety under dynamic attach, shutdown, and agent unload per contract.

An agent with a proper AArch64 binary can still be incompatible with the target JDK if it uses unsupported JVMTI features/behaviors.

### 9.2. Startup agents and dynamic attach

Do not assume startup agents and dynamic attach share identical conditions across every JDK and security environment. Some runtime/JDK releases have dedicated policies or warnings for dynamic agent loading.

During migration, test:

1. Startup when the agent is loaded from the beginning.
2. Dynamic attach if that is a product-committed feature permitted by the runtime.
3. When the agent is absent or blocked, under what policy does the application fail?
4. Memory leaks, deadlocks, and crashes on profiling/instrumentation threads.
5. Performance impact when running on x86-64 and AArch64.

If the agent is an optional observability tool, define whether the application is permitted to continue running when the agent fails. If the agent is a mandatory security component, fail-open may be inappropriate.

## 10. Linux: ELF, glibc, musl, and Dynamic Loaders

On Linux, having the right CPU architecture still does not guarantee a native library can load. Runtime also depends on:

- ELF machine architecture.
- Matching dynamic loader and interpreter.
- C runtime library (commonly glibc or musl).
- Versioned symbols of glibc/libstdc++ and dynamic dependencies.
- RPATH/RUNPATH, LD_LIBRARY_PATH, and file locations.
- File permissions, mount options, and security policies.

### 10.1. glibc and musl

A common situation is a native library built in a Linux environment using glibc while the production container uses Alpine Linux with musl libc. The two libc implementations are not binary-compatible by default.

For example:

~~~text
Build environment : Linux x86-64 / glibc
Native artifact   : libexample.so (glibc-linked)
Runtime image     : Linux x86-64 / Alpine musl
Result            : May lack the dynamic loader or library/symbols
~~~

Handling approach:

1. Choose the base image and runtime libc per platform policy.
2. Build a musl-compatible native variant if supporting Alpine.
3. Or use a compatible glibc base image if requirements allow.
4. Verify native dependencies directly inside the actual container.

Do not assume "Linux x86-64" is a sufficiently detailed artifact label if the application uses native libraries dynamically linked against libc.

### 10.2. Versioned symbols

A binary built on too new a distro may depend on glibc versioned symbols absent on older distros. Symptom:

~~~text
version 'GLIBC_2.xx' not found
~~~

This is an illustrative message; actual version numbers come from the binary and environment. When needing to run across multiple distros, choose a sufficiently old build baseline per the support matrix or package an appropriate runtime, rather than merely building on the latest distro.

### 10.3. ELF diagnostic tools

On Linux environments, corresponding tools exist:

~~~bash
uname -m
file libexample.so
readelf -h libexample.so
readelf -d libexample.so
readelf -Ws libexample.so
ldd libexample.so
~~~

Meaning:

- uname -m: reported kernel/machine architecture; do not rely on it alone to deduce the Java process architecture when emulation is present.
- file/readelf -h: ELF type and machine target.
- readelf -d: dynamic dependencies and metadata.
- readelf -Ws: exported/imported symbols.
- ldd: dependency resolution in the current environment.

Do not run ldd on untrusted binaries in privileged environments; for unverified artifacts, prefer static inspection with readelf/objdump and verify inside an isolated sandbox.

### 10.4. RPATH/RUNPATH and library locations

An .so may load yet depend on another .so not found by the loader. Search paths are influenced by ELF metadata, loader policies, and environment variables.

Do not fix every error by adding arbitrary directories to LD_LIBRARY_PATH, especially user-writable directories. When designing production images:

- Use controlled paths.
- Package dependencies alongside artifacts per policy.
- Configure RPATH/RUNPATH when needed.
- Reject native binaries from directories writable by untrusted parties.

## 11. Windows: PE/COFF, x64/Arm64, and Runtime DLLs

On Windows, native libraries are usually PE/COFF DLLs. Distinguish:

- Windows x64 process.
- Windows Arm64 process.
- Windows on Arm running an x64 app under emulation where supported by the system.

The native DLL must match the **architecture of the running Java process**, not just the machine's physical CPU. If Windows Arm64 is running an x64 JVM via emulation, the native DLL needs to be x64-compatible with that process; an Arm64 DLL cannot be mixed arbitrarily into the same x64 JVM.

### 11.1. Runtime and toolchain

Check:

- DLL machine type: AMD64, ARM64, or other targets.
- Whether software was built with MSVC or another toolchain and accompanying runtime dependencies.
- Windows C runtime/UCRT and required runtime DLLs.
- Exported symbols, calling conventions, and headers.
- DLL search paths, security policies, and code signing where applicable.

Tools such as dumpbin /headers and dumpbin /dependents help inspect metadata/dependencies when Visual Studio build tools are available.

### 11.2. LP64 and LLP64 apply directly

Windows x64/Arm64 usually uses LLP64: C long is 32-bit, pointers are 64-bit. Any JNI/FFM/JNA code treating C long as 64-bit because it "runs on 64-bit Windows" can read/write corrupted data.

For native interfaces storing 64-bit timestamps, counts, or IDs, use fixed-width types at the C boundary instead of relying on platform-dependent long.

### 11.3. DLL search path is a security issue

An application can accidentally load a malicious DLL of the same name from an untrusted directory if search paths are uncontrolled. Do not prepend arbitrary writable directories to search paths merely to silence UnsatisfiedLinkError.

Better yet, select verified artifacts, specify exact packaging locations, and check dependencies of the DLL itself.

## 12. macOS: Mach-O, Apple Silicon, and Universal Binaries

On macOS, a Java process can run as x86-64 or arm64 depending on the JDK distribution and launch mode. On Apple Silicon, Rosetta 2 can run some Intel x86-64 apps via translation, yet does not allow mixing the two native binary types arbitrarily inside the same process.

### 12.1. Native binaries must match process architecture

For example:

~~~text
Mac Apple Silicon host
  ├─ JDK arm64 process  → load arm64 dylib/slice
  └─ JDK x86-64 under Rosetta → load x86-64 dylib/slice
~~~

If the JDK process is arm64, a .dylib with only an x86-64 slice will not load directly as arm64. Do not use uname -m as sole evidence, because you must confirm the JVM process's own architecture.

### 12.2. Universal 2 / fat Mach-O

A Mach-O Universal binary can contain multiple architecture slices. You can use:

~~~bash
file libexample.dylib
lipo -info libexample.dylib
otool -L libexample.dylib
~~~

These commands display slices and dynamic library dependencies. To build a universal binary, compile/link each architecture with the right toolchain and then combine via corresponding tools. Not every binary or dependency is easy to combine into a universal artifact.

### 12.3. Darwin ABI and deployment target

Beyond arm64/x86-64, macOS binaries also have constraints on:

- macOS minimum deployment target.
- Frameworks and symbols present in the target macOS version.
- Code signing and notarization/hardened runtime policies when distributed applications require them.
- @rpath, @loader_path, and dynamic linker behavior.
- Darwin-specific ABI calling conventions, especially in varargs or C++ interoperability.

Therefore, a .dylib built on a newer macOS may fail to run on an older macOS if it uses symbols/APIs newer than the deployment target.

## 13. Checking the Exact Platform the JVM Is Running On

Java provides useful system properties:

~~~java
public final class PlatformInfo {
    public static void main(String[] args) {
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

The value of os.arch may be reported according to JDK/vendor conventions, such as amd64/x86_64 or aarch64/arm64. Do not hard-code a single string without normalization or a support matrix.

### 13.1. Process architecture matters more than host label

In environments with emulation or translation:

- The host CPU has architecture A.
- The Java runtime process may execute binaries in format B thanks to a translation system.
- JNI/shared libraries must match the **process binary ABI**, unless a separate supporting IPC/emulation boundary exists.

This is especially important on Apple Silicon macOS/Rosetta, Windows on Arm, and CI running QEMU.

### 13.2. When to use platform detection?

Platform detection is useful for:

- Selecting the right OS/arch/libc native artifact from the packaged bundle.
- Enabling/disabling platform-only features.
- Recording diagnostic details.

However, it cannot replace inspecting binary formats or runtime tests. Do not ignore an "unrecognized" architecture and fall back to loading an x86-64 .so on AArch64.

## 14. Designing the Native Artifact Matrix

An application may require multiple binaries:

| OS | ISA/Process Arch | Binary | Additional Constraints |
|---|---|---|---|
| Linux | x86-64 | libnative.so | glibc/musl, symbol baseline, CPU features |
| Linux | AArch64 | libnative.so | glibc/musl, CPU features |
| Windows | x64 | native.dll | PE/COFF AMD64, Windows runtime DLLs |
| Windows | Arm64 | native.dll | PE/COFF ARM64, Windows runtime DLLs |
| macOS | x86-64 | libnative.dylib | Mach-O slice, deployment target, signing |
| macOS | arm64 | libnative.dylib | Mach-O slice, deployment target, signing |

The table illustrates a project aiming to support all six combinations, not a requirement that every project support all of them. Publish a concrete support matrix.

### 14.1. Layout for storing native artifacts

A packaging layout might look like:

~~~text
resources/
  native/
    linux-x86_64-glibc/libsample_native.so
    linux-aarch64-glibc/libsample_native.so
    linux-x86_64-musl/libsample_native.so
    linux-aarch64-musl/libsample_native.so
    windows-x86_64/sample_native.dll
    windows-aarch64/sample_native.dll
    macos-x86_64/libsample_native.dylib
    macos-aarch64/libsample_native.dylib
~~~

This layout is illustrative; folder names depend on product conventions. Provide a selector with clear logic for OS, architecture, libc, and artifact checksums.

### 14.2. Package inside the JAR or distribute separately?

There are three common options:

**One JAR containing multiple native variants:** convenient for users yet increases size, requires extracting and picking the right binary, and requires managing extracted file lifecycles.

**Separate artifacts by classifier:** e.g., packages with classifiers like linux-aarch64 or windows-x86_64; reduces size, though builds/consumers must pick the right artifact.

**Native library installed by the OS/container:** enables independent updates, yet requires deployment to manage system paths, versions, and dependencies.

There is no single right model; choose based on distribution channels and support needs. Whichever option you choose, verify the loaded lib is the exact released build.

### 14.3. Loading libraries from inside a JAR

System.loadLibrary does not directly read a native binary stored inside a JAR resource entry. Some frameworks extract the binary to a filesystem file and then call System.load with a determined path.

If implementing this mechanism yourself:

1. Select the variant by OS, process arch, and libc/runtime.
2. Verify resource integrity (checksum or signature per policy).
3. Extract to an application-controlled directory, avoiding races/collisions and overly broad permissions.
4. Never load arbitrary binaries from untrusted writable locations.
5. Manage file lifetimes and native library loading/classloader behavior.
6. Confirm all transitive shared libraries can be located.

A loader that "tries every DLL/.so in turn until one works" is hard to troubleshoot and can be unsafe. It is better to select the variant by metadata and fail clearly if the platform is unsupported.

## 15. Building and Cross-Compilation

### 15.1. Compiler targets and sysroot

To build native binaries for a platform different from the host, you need a compiler/toolchain capable of targeting the matching architecture and OS, along with headers, libc/sysroot, a linker, and dependencies already built for that target.

For example:

~~~text
Host build machine: Linux x86-64
Target native lib : Linux AArch64 / glibc

Required:
  cross-compiler or target compiler
  AArch64 sysroot/headers
  target-compatible dependencies
  linker matching the target architecture/ELF
  testing on a real AArch64 runtime or verified emulation
~~~

Merely passing an -march flag does not generate binaries for another operating system. CPU target, object format, runtime libraries, and linker must all align.

### 15.2. CMake or native build systems

In a CMake project, you can specify a toolchain file or matching target parameters. Organization:

~~~text
native source
      │
      ├─ Linux x86-64 build
      ├─ Linux AArch64 build
      ├─ Windows x64 build
      ├─ Windows Arm64 build
      ├─ macOS x86-64 build
      └─ macOS arm64 build
      │
      ▼
Platform-specific binaries + metadata/checksums
      │
      ▼
Java packaging/release pipeline
~~~

Depending on the project, you can use CMake, Meson, Make, MSBuild, Gradle native plugins, or scripts. What matters is controlling toolchain versions, targets, and dependencies so builds are reproducible.

### 15.3. Cross-building does not replace runtime testing

An AArch64 cross-compiled binary may build successfully yet:

- The dynamic linker/libc is absent in the target image.
- Symbols are missing at runtime.
- The CPU lacks extensions.
- JNI symbols are not exported properly.
- Native functions have memory alignment, pointer, or concurrency bugs exposed only on AArch64.

Therefore, at minimum run load tests and native smoke tests on the target runtime. Emulation is helpful for some CI checks yet does not fully replace real hardware testing when requirements involve performance, CPU features, or production operability.

## 16. Multi-Architecture Docker Images and Kubernetes

Java containers can be published under a multi-architecture image tag. Registries usually provide an OCI/Docker manifest list or image index with distinct images per architecture.

For example, one tag can point to:

~~~text
image:example
  ├─ linux/amd64
  └─ linux/arm64
~~~

When an AArch64 Kubernetes node pulls the image, the container runtime can select the linux/arm64 variant if the registry provides it and platform policies permit.

However, this does not prove **native libraries inside the image** are compatible if the Dockerfile copied a fixed x86-64 .so for both variants.

### 16.1. Items to inspect

- Does the actual image have manifest entries for linux/amd64 and linux/arm64 as announced?
- Is the JDK base image matching the OS/architecture?
- Are native dependencies and agents built separately per architecture?
- Does the image use glibc or musl, with matching runtime dependencies?
- Does the build pipeline generate/release each variant from the exact right artifact?
- Which architecture do the container entrypoint and JVM process run under?
- Can Kubernetes nodeSelector/affinity and the scheduler place pods onto compatible nodes?

### 16.2. Buildx and multi-platform images

With Docker Buildx, a command like:

~~~bash
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t example/native-java-app:1.0 \
    --push .
~~~

can be used in pipelines with properly configured buildx and builders. However, this command by itself does not endow native libraries with both architectures. The Dockerfile and native build steps must use the right target platform. If emulation is used, evaluate build environment limitations.

### 16.3. Do not confuse the builder's architecture with the target's

In multi-platform builds, tools may provide BUILDPLATFORM/TARGETPLATFORM environment variables. Use the right target when compiling native code instead of running uname -m in the build stage and assuming the final binary matches.

A build stage running on an x86-64 host can produce x86-64 files for both targets if toolchain selection is wrong. Inspect file/readelf in the corresponding image/layer before releasing.

## 17. Testing the Platform Matrix in CI

For projects releasing native components, the test matrix must cover multiple dimensions:

~~~text
JDK version
  × operating system
  × process architecture
  × C runtime / libc (when relevant)
  × native build variant
  × agent/dependency version
~~~

Sample matrix:

| Job | JVM Runtime | Native Binary | Primary Checks |
|---|---|---|---|
| linux-amd64 | Target Linux x86-64 JDK | ELF x86-64/glibc | Load + JNI calls + runtime dependencies |
| linux-arm64 | Target Linux AArch64 JDK | ELF AArch64/glibc | Load + JNI calls + runtime dependencies |
| linux-arm64-musl | Musl-compatible JDK/environment | ELF AArch64/musl | Loader + libc compatibility |
| windows-x64 | Windows x64 JDK | PE DLL AMD64 | DLL load + calling convention + tests |
| windows-arm64 | Windows Arm64 JDK | PE DLL ARM64 | DLL load + function/struct mapping |
| macos-arm64 | macOS arm64 JDK | Mach-O arm64 | Load + code signing/rpath + native tests |

Include a job in the official list only when the platform and runner are available or have a confirmed execution strategy. Do not claim support for a combination merely because the binary compiled.

### 17.1. Required test layers

**Layer 1 — Static artifact inspection**

- Identify ELF/PE/Mach-O and machine type.
- Check exported symbols.
- Inspect dynamic dependencies, libc, and baseline symbols.
- Check checksums/release provenance.

**Layer 2 — Load test**

- Start the JVM with the exact target JDK.
- Load the library via System.load/System.loadLibrary or the real loader.
- Confirm there is no UnsatisfiedLinkError, loader failure, or architecture mismatch.

**Layer 3 — Functional JNI/JNA/FFM tests**

- Invoke native methods with integers, floating-point values, strings, arrays, and buffers.
- Test struct alignment, pointer-sized values, null pointers, and error conditions.
- Test thread safety/callbacks/long-lived handles if applicable.

**Layer 4 — Integration tests**

- Run with the same frameworks, agents, containers, and security settings as deployment.
- Test business APIs crossing the native boundary.
- Check memory/crashes/logging and resource cleanup.

**Layer 5 — Production-like verification**

- Canaries on x86-64/AArch64 nodes per policy.
- Watch for native crashes, SIGILL, JVM fatal error logs, agent startup, and performance.
- Confirm rollback artifacts/images/agents match the architecture.

### 17.2. Testing struct layouts and ABIs

For libraries with C APIs accepting structs, add C-side tests confirming:

~~~c
#include <stddef.h>
#include <stdint.h>

struct Example {
    int32_t code;
    int64_t value;
};

/* Example inspecting offsets against the actual target ABI:
   sizeof(struct Example)
   _Alignof(struct Example)
   offsetof(struct Example, code)
   offsetof(struct Example, value)
*/
~~~

In Java/JNA/FFM, test mappings against the exact same native build. Do not copy offsets from one platform's test output and apply them to every OS without justification.

### 17.3. Deliberate failure tests

Besides positive tests, verify:

- When no native binary exists for a platform, the loader reports unsupported platform clearly.
- When checksums mismatch, do not attempt to load the binary.
- When a JNI symbol is absent, errors log the library name/version and remediation steps.
- When the system lacks libc/runtime DLLs, logs help pinpoint missing dependencies.
- When an optional agent fails to load, fallback behavior matches policy.
- When a required agent fails to load, do not keep running in a state without security controls.

## 18. Diagnosing Common Errors

| Symptom | Possible Cause | Investigation |
|---|---|---|
| UnsatisfiedLinkError: no library in java.library.path | Library not found by name/path. | java.library.path, load location, packaging. |
| UnsatisfiedLinkError with wrong-architecture message | Binary is for another OS/CPU or process arch. | file/readelf/dumpbin/lipo and JVM os.arch. |
| wrong ELF class / invalid ELF header | Binary has wrong bitness/format or invalid file. | ELF header, image build, and artifact origin. |
| undefined symbol | Native library depends on an unsupplied symbol or mismatched ABI/linking. | readelf -Ws, dependency versions, exported symbols. |
| GLIBC version not found | Binary built with newer glibc than runtime supports. | readelf, runtime libc version, build baseline. |
| Native DLL dependency missing | DLL depends on another undistributed runtime DLL. | dumpbin /dependents, loader search path. |
| Mach-O incompatible architecture | No slice matches the JVM process. | file/lipo -info, JDK architecture, Rosetta mode. |
| SIGILL / illegal instruction | CPU lacks instruction extensions used by the compiler. | CPU feature baseline, compiler flags, crash details. |
| SIGSEGV / EXCEPTION_ACCESS_VIOLATION | Native memory, pointer, stack, calling convention, or thread misuse bug. | JVM fatal log, native symbols, debugger/sanitizers in test env. |
| JVM fatal error after loading agent | Incompatible native JVMTI agent or memory/lifecycle bug. | Agent/JDK versions, JVMTI callbacks, native crash logs. |
| Struct values differ between Linux and Windows | LP64/LLP64, padding/alignment, endianness, or wrong binding. | sizeof/offsetof and C headers of each target. |

One error can have multiple causes. For example, UnsatisfiedLinkError can happen because the main library is missing, its symbol was not exported, or a lower-level dependency is missing; do not only tweak java.library.path, inspect the root message and dynamic dependencies.

### 18.1. Workflow for investigating a library load failure

1. Record Java version, vendor, OS, process architecture, and container image.
2. Identify the exact selected native artifact and its checksum.
3. Check format and machine architecture with OS tools.
4. Check libc/C runtime, symbol dependencies, and search paths.
5. Identify required JDK/JNI/JVMTI versions.
6. Create a minimal load test independent of the full application.
7. If loading succeeds yet crashes upon invocation, inspect function signatures, struct layouts, and memory lifetimes.
8. Rebuild/retest for the right target, update the artifact matrix and release notes.

### 18.2. Reading JVM fatal error logs

When native code crashes the JVM, a HotSpot error report may appear with details about signals/exceptions, problematic frames, threads, and involved native libraries.

Do not conclude a JNI method is the culprit solely because the crash appears near it in the log; combine symbols/debug info, native stacks, compiler optimizations, and reproducibility.

Security note: crash dumps and heap/core dumps may contain sensitive data and must be collected and stored per policy, never uploaded automatically to public issues.

## 19. Controlling Memory, Alignment, and Concurrency Across Architectures

Some native bugs surface only when moving from x86-64 to AArch64 because prior assumptions were masked by how memory alignment or memory ordering was handled.

### 19.1. Unaligned memory access

Do not assume every CPU/ABI tolerates all loads/stores from unaligned addresses, or that compilers always handle them identically. C/C++ code casting a byte buffer to a struct pointer can trigger undefined behavior from aliasing/alignment.

Instead of arbitrary casts:

~~~c
/* Do not assume data is aligned and has the right layout */
struct Record *record = (struct Record *)buffer;
~~~

design explicit serialization/deserialization, use memcpy when appropriate, and verify lengths and layouts against the protocol. With FFM/JNA, also declare alignments and sizes per ABI.

### 19.2. Memory ordering and data races

x86-64 and AArch64 have different hardware memory-ordering models. A native C/C++ bug using shared memory without proper synchronization may be very rare on one architecture yet occur frequently on the other.

Do not work around data races by adding sleep or relying on observed instruction ordering. Use:

- C11/C++ atomics or supported mutexes/locks.
- Appropriate memory orders for shared operations.
- Clear JNI synchronization semantics when native and Java threads interact.
- Concurrency tests on both x86-64 and AArch64, paired with sanitizers where toolchains allow.

The Java Memory Model does not automatically make native code using raw pointers and incorrect atomics safe. The JNI/FFM boundary must explicitly establish concurrency rules for both sides.

### 19.3. Size_t, pointers, and handle lifecycles

A 64-bit Java long should not be equated with every kind of native handle or pointer without reviewing semantics. On common 64-bit environments, intptr_t can hold a pointer, yet wrapping pointers as long still requires lifetime management policies and avoiding unnecessary address exposure.

A native handle pattern:

~~~text
Java object holds opaque handle
    │
    ▼
Native context allocated
    │
    ▼
Java calls native operations
    │
    ▼
close() explicitly frees context
~~~

If using handles as long, check null/closed states, double free, use-after-free, multi-threaded access, and cleanup errors. With FFM, arena/lifetime APIs can replace raw longs where design permits.

## 20. Security and Supply Chain of Native Artifacts

Native code executes inside the JVM process with process privileges, so it can access memory and OS APIs outside the normal controls of the Java type system. An untrusted native library can pose severe risks.

Principles:

- Distribute binaries only from approved build pipelines and dependency sources.
- Attach versions/checksums/signatures/provenance to each OS/architecture variant.
- Track CVEs and maintenance policies for native dependencies, not just Java JARs.
- Restrict container/process permissions and native library paths.
- Avoid DLL/.so search paths pointing to directories writable by other parties.
- Manage temporarily extracted native libraries securely.
- Do not disable JDK or OS security policies merely to load legacy binaries.
- Consider code signing/hardened runtime where deployment platforms require them.

**An artifact with the right architecture does not automatically mean it is safe or supported.** Include evidence of provenance, runtime dependencies, and security patching.

## 21. Compatibility Report for Native Dependencies

An inventory table should accompany each native library:

| Attribute | Details to Record |
|---|---|
| Java module/service | Component using the native code. |
| Java wrapper | JNI, JNA, FFM, JVMTI agent, or framework. |
| Native artifact | Filename, version, checksum, classifier. |
| OS target | Linux, Windows, macOS, and minimum versions where relevant. |
| Process architecture | x86-64 or AArch64, using standardized names. |
| Binary format | ELF, PE/COFF, or Mach-O. |
| ABI/data model | System V AMD64, Windows x64, AAPCS64/Darwin conventions; LP64/LLP64. |
| C runtime/dependencies | glibc/musl, UCRT, libstdc++, frameworks, and symbols. |
| CPU baseline | Required extensions or runtime dispatch. |
| JDK/JNI/agent support | Java versions and JVMTI/FFM-specific constraints. |
| Packaging | JAR resource, OS package, container layer, classifier. |
| Verification | Static inspection, load test, functional/native integration tests. |
| Ownership | Team responsible for building, fixing bugs, and applying patches. |

Illustrative support matrix:

~~~text
Component: image-accelerator-native
Version  : 2.x
OS       : Linux
Targets  :
  - linux-x86_64-glibc
  - linux-aarch64-glibc
JDK      : Java versions as announced by the product
Tests    : load + buffer/struct + multithread + feature behavior
Status   : declare SUPPORT only after test evidence exists
~~~

Do not infer support from artifact filenames or from a single passing build; status must be grounded in runtime tests on the exact target.

## 22. Migration Strategy from x86-64 to AArch64

Suppose a Java application runs on Linux x86-64 and needs to deploy additionally on Linux AArch64:

### Step 1 — Inventory all native dependencies

Locate:

- JNI libraries loaded with System.load/LoadLibrary.
- JNA/FFM bindings and dynamically loaded native libraries.
- -agentpath/-agentlib and agents containing native components.
- JNI code packaged by frameworks inside transitive JARs.
- Database drivers with native authentication, crypto/HSM libraries.
- Compression, ML, image/video, and telemetry libraries.

Do not conclude "pure Java project" merely because no .c files appear in source; transitive dependencies can extract .so files at runtime.

### Step 2 — Build the target matrix

Decide target OS versions, libc (glibc/musl), JDK distributions, AArch64 CPU baseline, container images, and agent versions.

### Step 3 — Obtain matching native binaries

For in-house libraries, build using cross-compilers or native runners for the exact target. For third-party libraries, select versions/classifiers with official AArch64 support; if unavailable, consider replacing the library or isolating the capability.

### Step 4 — Review ABI assumptions

Check C long, pointers, size_t, struct padding, alignment, calling conventions, endianness, C++ ABI, CPU-specific intrinsics, and shared-memory synchronization.

### Step 5 — Check packaging

Ensure the JAR or container image selects the linux-aarch64 variant on an AArch64 JVM without mistakenly loading an x86-64 binary. Verify dynamic dependencies inside the target image.

### Step 6 — Run layered tests

- Static binary inspection.
- JVM startup + native load.
- Native functional smoke test.
- Data boundary/struct/callback tests.
- Integration/agent tests.
- Concurrency, performance, and long-running tests.

### Step 7 — Roll out in phases

Deploy staging/canaries on designated AArch64 nodes, monitor JVM fatal errors, agent failures, native memory, and throughput/latency. Have a rollback plan to matching artifacts and node architectures.

### Step 8 — Publish supported scope

Explicitly document product support for:

~~~text
Linux x86-64 + glibc, JDK target
Linux AArch64 + glibc, JDK target
~~~

if those are the two verified combinations. If Alpine/musl, Windows Arm64, or macOS arm64 are not yet supported, do not implicitly advertise all "64-bit" environments as compatible.

## 23. Common False Assumptions

| Assumption | Issue | Proper Practice |
|---|---|---|
| "Java runs everywhere, so JNI does too." | JNI uses OS/ISA-specific binaries. | Build/test native variants for each target. |
| "x64 on Windows equals x86-64 on Linux." | OS ABI, format, loader, and C runtime differ. | Distribute DLL/so per target OS. |
| "AArch64 equals arm64 on every OS." | Same ISA, but ABI and loader differ. | Distinguish Linux/Windows/macOS targets. |
| "64-bit means C long is 64-bit." | 64-bit Windows typically uses LLP64. | Use jlong/fixed-width types and check layout. |
| "Checking os.arch alone is enough." | Emulation and JDK process arch may differ from host CPU. | Inspect the actual process and binary. |
| "Rename .so to .dll and it runs." | ELF and PE/COFF differ in format/ABI. | Build with the proper target toolchain. |
| "Multi-arch images convert JNI libraries automatically." | Multi-arch manifests do not recompile native code. | Build/copy matching variants into each image. |
| "Having an AArch64 .so guarantees Alpine works." | glibc and musl may be incompatible. | Pick the libc variant and inspect dependencies. |
| "Compiling means it is portable." | Runtime may lack symbols, loaders, or CPU features. | Run load/integration tests on target. |
| "A JNI function taking long matches Java long." | C long varies in width by data model. | Use JNI types and fixed interface contracts. |
| "JNA/FFM removes all ABI issues." | Both still map native calling conventions and layouts. | Test bindings by OS/arch and API version. |
| "Java JAR agents have no native dependencies." | Some agents pull JVMTI/JNI or JDK-dependent bytecode tooling. | Inventory agents and runtime dependencies. |
| "AArch64 CPUs are always slower/faster than x86-64." | Performance depends on CPU generation, workload, JIT, SIMD, and native code. | Benchmark on representative hardware. |
| "ldd is safe on any unknown binary." | Inspecting untrusted binaries carries risks in some contexts. | Prefer static inspection and sandboxes. |
| "Same ABI means sharing C++ binaries across all compilers." | C++ ABI, runtimes, and compiler flags can differ. | Use a C boundary and validate toolchains. |

## 24. Native Troubleshooting Workflow After Upgrading the JDK

When an application previously ran well yet fails after changing JDK, OS, or architecture:

1. **Lock down evidence:** JDK version, vendor, process architecture, OS, libc/container image, JVM args, module/library versions.
2. **Isolate the native path:** identify the JNI/JNA/FFM/JVMTI component being loaded.
3. **Capture artifact metadata:** file type, machine architecture, checksum, exported symbols, and dynamic dependencies.
4. **Cross-check ABI:** calling convention, C data model, struct layout, compiler/target, and C runtime.
5. **Reproduce with a minimal load test:** narrow scope from the whole application down to a reproducible method/agent.
6. **Check integration:** JVM ↔ native types, memory lifetimes, concurrency, and lifecycles.
7. **Fix platform mismatches:** rebuild for the right target or select a supported variant; never rename files or bypass security checks.
8. **Test in layers:** static, load, functional, integration, staging/canary.
9. **Record conclusions:** root cause, artifact versions, tested platforms, unsupported combinations, and rollback plan.

If the issue occurs in a third-party native library, consult the vendor's support docs and releases. Do not alter toolchain flags blindly to override ABIs without understanding dependencies and compatibility contracts.

## 25. Conclusion

**x86-64 and AArch64 are two distinct CPU architectures, while an ABI is a binary contract shaped by the operating system, compiler, C runtime, and linked libraries.** Even when both are 64-bit, Linux, Windows, and macOS can use different data models, calling conventions, binary formats, and dynamic loaders. Java code running on a matching JVM can be portable, yet JNI, JNA, FFM bindings, and native JVMTI agents still depend on binaries matching the OS, process architecture, and ABI.

In Java Advance Compatibility Migration, inventory both direct and transitive native dependencies, standardize artifact selection by OS/arch/libc, check LP64/LLP64, struct alignment, native symbols, CPU instruction baselines, and runtime linkers. Multi-architecture builds must be paired with real testing on every target, especially when migrating x86-64 to AArch64, using Alpine/musl, or running JVMs under emulation.

The destination is **an evidence-backed compatibility matrix**: every JDK–OS–architecture–ABI combination has an identified native artifact, clear provenance, load and functional tests, security policies, and a rollout/rollback plan. Only then is Java's portability benefit preserved without overlooking platform-dependent boundaries in native code.
