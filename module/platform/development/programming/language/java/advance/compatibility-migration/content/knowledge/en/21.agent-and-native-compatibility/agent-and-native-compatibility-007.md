# Foreign Function & Memory API and constraints when migrating from legacy solutions

In many long-lived Java systems, business logic runs on the JVM yet still needs to call C/C++ code, use OS native libraries, or access memory outside the Java heap. Projects typically solve this need with **JNI**, wrapper libraries such as **JNA**, `sun.misc.Unsafe`, `ByteBuffer.allocateDirect()`, or a separately packaged agent/native bridge. Those solutions may have worked reliably for years while exposing constraints when upgrading the JDK: having to recompile native code, hitting module access errors, depending on the ABI/OS, or losing access to internal APIs that older library versions relied on.

The **Foreign Function & Memory API (FFM API)** provides a standard Java API for accessing off-heap memory and calling native functions. This approach reduces the need to write JNI glue code for many scenarios, while explicitly modeling memory sizes, lifetimes, and thread ownership. However, FFM does not turn native code into completely safe Java code, does not erase ABI differences across Windows/Linux/macOS, and **does not replace every capability of JNI, JVMTI, or Java agents**.

In Java Advance Compatibility Migration, distinguish two kinds of changes:

- **Upgrading the JDK while keeping current JNI/JNA or native bridges:** prioritize proving compatibility with the new JDK rather than necessarily migrating to FFM immediately.
- **Proactively replacing old native bridges with FFM:** an architectural migration involving changes to APIs, ownership, packaging, callbacks, security, and performance; it requires dedicated design and testing.

This lesson covers FFM history across JDKs, practical APIs and constraints, Java 22+ examples, comparison matrices against JNI/JNA/Unsafe, and a verified migration workflow.

## 1. What problems does the Foreign Function & Memory API solve?

### 1.1. Two needs that commonly go together

A Java program needing native interoperability typically performs two tasks:

1. **Foreign functions:** locating and invoking functions in native libraries, such as `sum_ints`, `sqlite3_open`, or any function with a C ABI.
2. **Foreign memory:** allocating/reading/writing off-heap memory to exchange data with native functions, including buffers, structs, arrays, and pointers.

Calling a C function with two `int` parameters and an `int` return value is relatively straightforward. Yet when functions accept `struct*`, write into output buffers, return pointers requiring deallocation, or retain callbacks past the end of the Java call, migration becomes significantly more complex.

### 1.2. Previous models

JNI declares native methods in Java and implements them in C/C++:

```java
public final class NativeMath {
    static {
        System.loadLibrary("mathbridge");
    }

    public static native int sum(int a, int b);
}
```

The native library must export appropriate JNI entrypoints and manage `JNIEnv*`, handles, references, and exception bridging. This approach is flexible yet adds glue code, resource management burden, and per-platform build requirements.

JNA reduces manual JNI glue code via runtime library mapping of native calls, though projects depend on JNA's runtime/version and must still ensure accurate C ABI mappings.

FFM offers another path: describing function signatures and memory layouts via Java APIs, then producing a `MethodHandle` to call the matching native function.

### 1.3. FFM is not a communication protocol

FFM operates on memory and native functions **in-process or via dynamic libraries loaded into the process**. It does not inherently provide isolation like RPC/gRPC, does not translate C code into Java bytecode, and does not shield the JVM from bugs in native code.

If a native library can crash, write out of bounds, or execute untrusted code, consider running it in a **separate process** over an explicit IPC protocol. FFM does not replace OS security boundaries.

## 2. API history and JDK milestones

FFM underwent multiple incubator/preview rounds before stabilizing. During migration, **do not treat FFM source code on JDK 17, 21, and 22 as equivalent**.

| JDK | Milestone | Status to remember |
|---|---|---|
| JDK 14 | JEP 370 – Foreign-Memory Access API | Incubator for foreign memory access |
| JDK 16 | JEP 393 – Foreign-Memory Access API | Next incubator round |
| JDK 17 | JEP 412 – Foreign Function & Memory API | Incubator; API/packaging not yet the final standard API |
| JDK 19 | JEP 424 – Foreign Function & Memory API | Preview |
| JDK 20 | JEP 434 – Foreign Function & Memory API | Next preview round |
| JDK 21 | JEP 442 – Foreign Function & Memory API | Preview, still subject to change |
| JDK 22 | JEP 454 – Foreign Function & Memory API | API finalized |

### 2.1. JDK 17 does not provide the final JDK 22 API

In incubator releases, APIs lived in separate modules/packages, such as `jdk.incubator.foreign`, requiring corresponding compiler/runtime configuration. You cannot copy code using the final `java.lang.foreign.Arena` or `Linker` APIs and run it directly on Java 17.

If a product still supports JDK 17 runtimes, you may need to:

- Keep JNI/JNA for Java 17 support lines.
- Abstract native implementations behind a shared interface with JDK-specific backends.
- Wait until minimum runtime moves to JDK 22+ before adopting final FFM.
- Use another tested build/distribution approach without assuming preview APIs are backward compatible.

Do not use reflection, module hacks, or arbitrary JAR additions to emulate final `java.lang.foreign` on older JDKs.

### 2.2. JDK 21 is still preview

A program using FFM preview on JDK 21 must compile and run under JDK 21 preview rules, for example:

```bash
javac --enable-preview --release 21 ForeignDemo.java
java --enable-preview --enable-native-access=ALL-UNNAMED ForeignDemo
```

Syntax must be adjusted for actual classpath/module-path and native-access needs. **Do not take final JDK 22 FFM examples and assume every method/signature existed identically in JDK 21.** Preview APIs were permitted to change APIs and behavior before finalization.

Preview features also constrain runtime versions: bytecode using a JDK's preview features generally must execute on that exact release with preview enabled. This differs from ordinary `--release 21` for non-preview sources.

### 2.3. Starting in JDK 22: `java.lang.foreign`

The final API includes types such as:

- `Arena`.
- `MemorySegment`.
- `MemoryLayout` and `ValueLayout`.
- `Linker`.
- `SymbolLookup`.
- `FunctionDescriptor`.

The core types live in Java SE's `java.lang.foreign` package. Starting in JDK 22, enabling preview solely to compile final FFM sources is unnecessary. However, **restricted native operations (restricted methods) may require native-access permission**, and policies toward unauthorized access depend on the JDK release.

### 2.4. Which baseline should you choose?

| Product | Platform choice to consider |
|---|---|
| Must run on JDK 17 | Keep JNI/JNA or compatibility adapters; do not assume final FFM is usable |
| Runs JDK 21 LTS and prioritizes stability | Assess preview risk; continuing the current bridge may be preferable |
| Minimum runtime is already JDK 22+ | Final FFM is viable after verifying OS/ABI/native access |
| Has complex JNI/JVMTI agents | Separate native calls/memory that can migrate from agent callbacks/instrumentation |
| Supports multiple JDKs/OSes | Define a compatibility matrix and backend strategy; test every combination |

Adopting FFM is an architectural decision tied to your **minimum supported JDK**, not merely the JDK on build machines.

## 3. Overall architecture of FFM

A native call flow via FFM can be illustrated as:

```text
Java application
      |
      v
SymbolLookup ----> look up symbol in native library
      |
      v
FunctionDescriptor ----> describe parameters/return value per ABI
      |
      v
Linker.downcallHandle(...)
      |
      v
MethodHandle.invokeExact(...)
      |
      v
Native function in the same process
      |
      v
MemorySegment <---- read/write buffers/structs, managed by Arena
```

Four responsibility groups:

1. **Library/symbol:** which library is loaded, which symbols are looked up, namespace rules, and lookup lifetimes.
2. **ABI mapping:** C types, return types, calling conventions, alignment, padding, and pointer widths.
3. **Memory ownership:** who allocates, who frees, which threads can access, and whether native code retains pointers.
4. **Operational safety:** native access permissions, OS library paths, deployment, crash containment, metrics, and testing.

Omitting any group lets code compile while still failing during actual native calls.

## 4. MemorySegment: bounded, lifetime-managed memory

### 4.1. How does it differ from a raw `long` address?

In legacy code, a pointer might be represented as a `long` or a wrapper library's `Pointer`. With `MemorySegment`, Java provides an abstraction capturing memory region, byte size, lifetime scope, and access bounds checks.

JDK 22+ example:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class SegmentExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocate(16);

            numbers.set(ValueLayout.JAVA_INT, 0, 42);
            numbers.set(ValueLayout.JAVA_INT, 4, 84);

            int first = numbers.get(ValueLayout.JAVA_INT, 0);
            int second = numbers.get(ValueLayout.JAVA_INT, 4);

            System.out.println(first + second); // 126
        }
    }
}
```

Key takeaways:

- `arena.allocate(16)` allocates 16 bytes of native memory owned by the arena.
- `ValueLayout.JAVA_INT` represents a 32-bit `int` layout matched to the API.
- Offsets are measured in bytes, not element indices.
- `MemorySegment.get/set` checks bounds, alignment, and lifetime per contract.
- Exiting `try-with-resources` closes the confined arena and invalidates dependent segments.

Never use a closed `MemorySegment`; any native pointer retained after arena closure becomes a dangling pointer.

### 4.2. Heap segments and native segments differ

FFM can also wrap Java heap arrays as memory views. However, a Java heap segment is not an arbitrarily retainable native pointer for C code.

The JVM garbage collector can relocate heap objects; native linkers and ABIs impose separate constraints. If a C function retains pointers after returning, design an explicitly scoped native allocation or copy data into an appropriate segment.

Never infer that every `MemorySegment` passes as a valid native address in every context. Check segment kind and native function contracts.

### 4.3. Slices and offsets

A segment can represent a subrange of another memory block via slicing, modeling bounds explicitly. Example:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    MemorySegment firstEightBytes = block.asSlice(0, 8);

    firstEightBytes.set(ValueLayout.JAVA_INT, 0, 1234);
    // firstEightBytes.get(..., 8) would exceed the 8-byte bounds
}
```

Where legacy wrappers computed `pointer + offset` with manual arithmetic, switching to slices helps enforce bounds on the Java side. Still, native code receiving a pointer can read or write beyond Java-enforced bounds if C code violates the contract.

## 5. Arena: who owns the memory and which threads access it?

### 5.1. Why lifetime is the central concern

A native function may:

- Read buffers only while the call executes.
- Write data into buffers before returning.
- Return a pointer into the library's static memory.
- Return a pointer requiring a native free function.
- Retain pointers/callbacks for use after the call ends.

A single "close Arena on return" rule cannot cover every scenario. **Actual lifetimes must match the native API contract.**

### 5.2. Arena models

| Arena | Intended use | Risks / check points |
|---|---|---|
| `Arena.ofConfined()` | Memory tied to one owner thread and explicitly closeable | Access from another thread fails confinement checks |
| `Arena.ofShared()` | Memory accessible by multiple threads, explicitly closeable | Needs synchronization and concurrent close control |
| `Arena.ofAuto()` | Lifetime managed by GC | Unsuitable when deterministic timely release is required |
| `Arena.global()` | Lifetime tied to process/runtime | Hard to reclaim long-term resources; avoid overuse |

Depending on JDK version, API details and semantics may vary; this table covers final FFM in JDK 22+. Confined arenas enforce thread ownership, yet do not magically make native library operations thread-safe on their own.

### 5.3. Mistake: returning a segment from a closed Arena

```java
static MemorySegment wrong() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(64);
    }
}
```

The method returns a segment whose lifetime belongs to `arena`. Upon return, `try-with-resources` closes `arena`; the caller receives an invalid view.

An alternative design:

```java
static MemorySegment allocateBuffer(Arena arena) {
    return arena.allocate(64);
}
```

Here the caller controls lifetime and supplies an arena with an explicit ownership contract. If the function must own memory and return data, copy onto the Java heap or return an `AutoCloseable` wrapper owning both arena and segment.

### 5.4. Switching confined to shared does not fix every thread bug

If a worker thread reads a segment owned by another thread's confined arena, Java throws a wrong-thread exception. Switching to a shared arena allows multi-thread access, **yet provides zero synchronization**.

Two threads writing to the same struct or one thread closing an arena during an active native call remains a concurrency bug. You must:

- Document owners, readers, and writers.
- Coordinate shutdown/close sequencing.
- Apply locks, queues, or single-thread executors where needed.
- Verify the native library is thread-safe per documentation.
- Test cancellation, timeouts, and parallel calls happening concurrently.

## 6. Downcalls: calling C functions from Java without JNI glue where appropriate

### 6.1. Example native function

Suppose a custom C library exports:

```c
#include <stdint.h>

int32_t sum_ints(int32_t a, int32_t b) {
    return a + b;
}
```

The function exports with the C ABI and builds as a shared library matching OS and architecture. For C++, ensure C ABI linkage such as `extern "C"` to prevent C++ name mangling when looking up `sum_ints`.

### 6.2. Final Java FFM (JDK 22+)

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmMath {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of("/opt/example/libmathops.so");

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                SymbolLookup.libraryLookup(library, arena);

            MemorySegment function = lookup.find("sum_ints")
                .orElseThrow(() ->
                    new IllegalStateException("Missing sum_ints")
                );

            Linker linker = Linker.nativeLinker();

            FunctionDescriptor descriptor = FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // Return: int32_t
                ValueLayout.JAVA_INT, // Param 1
                ValueLayout.JAVA_INT  // Param 2
            );

            MethodHandle handle =
                linker.downcallHandle(function, descriptor);

            int result = (int) handle.invokeExact(7, 5);
            System.out.println(result); // 12
        }
    }
}
```

The path `/opt/example/libmathops.so` is a Linux example; on Windows/macOS supply matching shared library filenames, exported symbols, and binaries. Executing native calls also requires satisfying the active JDK's native-access policy.

The example uses fixed 32-bit types; ABI mappings must still be verified against the native library's target platform. Since this C function retains no pointers after returning, lifecycle management is relatively simple.

### 6.3. Why is FunctionDescriptor required?

FFM does not parse C headers to infer shared library signatures automatically. `FunctionDescriptor` specifies:

- Return type.
- Parameter ordering and layouts.
- ABI rules required for downcalls.

If the descriptor is wrong, code may compile yet pass corrupted arguments, misread return registers/stacks, or crash. Never treat `FunctionDescriptor` as decorative typing.

### 6.4. MethodHandles must be invoked with exact types

`invokeExact` requires the call-site method type to match the handle exactly. Mismatches in Java primitives or carrier types throw `WrongMethodTypeException`.

The safe pattern is wrapping calls in typed Java methods with dedicated tests, hiding `MethodHandle` from business layers and handling type conversions in one controlled boundary.

Avoid scattering `invokeExact` and layout constants across dozens of domain classes.

## 7. SymbolLookup and packaging native libraries

### 7.1. Finding symbols in the right library

A native library can be loaded via:

- An application-managed path to the shared library.
- Library lookup by name under OS rules.
- The native linker's default lookup for standard symbols.

These choices differ in library provenance, portability, and security. Using relative paths leaves behavior exposed to the app/container working directory.

Production setups should enforce rules:

- Place libraries at predictable locations inside images/packages.
- Use explicit paths; avoid searching untrusted DLL/SO directories.
- Manage binary checksums, versions, and signatures.
- Avoid depending on unmanaged `PATH`/`LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH`.
- Maintain a release manifest pairing Java wrapper versions with native binaries.
- Audit dynamic native dependencies such as libc, OpenSSL, or vendor runtimes.

### 7.2. Symbol names do not always match source function names

In C++, name mangling alters exported symbols. On Windows, export tables and calling conventions affect names; some OSes use versioned symbols. Seeing a function in a header does not guarantee the symbol is exported in the shared library.

When `lookup.find("sum_ints")` returns empty, inspect:

- Actual native file loaded.
- Exported symbol table.
- Compiler/linker flags.
- Architecture matching the JVM.
- Shared library dependencies.
- C vs. C++ symbol mangling.
- Runtime library version.

Tools such as `nm`, `readelf`, `objdump`, `otool`, or `dumpbin` assist depending on OS/toolchain; they are not Java APIs and output formats vary across platforms.

### 7.3. Lifetime of symbol lookups and libraries

When a lookup or library is bound to a closeable Arena, avoid calling function handles after the backing resource closes. Keep arena/library ownership together with method handles inside a managed wrapper, closing only after no calls or callbacks remain active.

Never create a function handle inside a short `try (Arena arena = ...)` block and cache it in a static field for later invocation without verifying its lifetime contract.

## 8. C ABI and native data layouts: the biggest migration risk

### 8.1. Java primitives do not match all C primitives

Java has fixed primitive widths such as 32-bit `int` and 64-bit `long`. In C, several types vary by ABI:

- `long` is 32-bit on 64-bit Windows, yet typically 64-bit on 64-bit Linux.
- `size_t` follows pointer width.
- `char` signedness depends on platform defaults.
- `wchar_t` and Unicode representations vary across OS/compilers.
- `bool`, enums, bitfields, and packed structs carry platform-specific rules.

If an older JNI wrapper handled these conversions in C, migrating to FFM requires porting **that conversion logic too**, not just swapping entrypoints.

### 8.2. Fixed-width types reduce risk

When you own the C API, prefer explicit-width types such as:

```c
#include <stdint.h>

typedef struct {
    int32_t id;
    int64_t timestamp_ms;
} event_record;
```

Even with explicit-width integer fields, structs remain subject to ABI alignment, padding, and byte order. When struct layouts cross native library boundaries, model exact target-platform offsets and sizes.

### 8.3. Struct padding and alignment

Example:

```c
typedef struct {
    uint8_t tag;
    int32_t value;
} packet_header;
```

Never assume `value` starts at byte offset 1. C compilers insert padding to satisfy alignment constraints. FFM `MemoryLayout.structLayout(...)` must declare the real native layout, including explicit padding where required.

Verification steps:

1. Print `sizeof(packet_header)` in a native test helper.
2. Print `offsetof(packet_header, tag)` and `offsetof(packet_header, value)`.
3. Compare against Java `MemoryLayout.byteSize()` and offsets.
4. Test across every supported OS, architecture, and compiler/ABI.

Never copy a Linux x86-64 layout to Windows ARM64 solely because field names look identical.

### 8.4. Canonical C layouts

FFM's `Linker` exposes canonical ABI layouts for standard C types; consider them for `size_t`, `long`, and platform-dependent native types.

Do not hardcode every C `long` as `ValueLayout.JAVA_LONG` without checking the ABI. For pointer parameters, `ValueLayout.ADDRESS` models the address carrier, though pointer validity and lifetimes must still be upheld.

### 8.5. Variadic functions and errno

Variadic C functions such as `printf(const char*, ...)` follow different ABI rules than fixed-arity functions. FFM provides mechanisms to describe variadic arguments per API version; do not build ordinary fixed descriptors for them.

If native APIs report errors via `errno` or platform-specific thread-local last-error state, reading return values alone is insufficient. FFM supports capturing call state per API/JDK; wrappers should capture and translate error state immediately into meaningful exceptions or results before subsequent native calls overwrite `errno`.

For migration, start with simple, non-variadic C functions having explicit ownership contracts before tackling advanced ABI cases with dedicated tests.

## 9. Pointers, ownership, and memory returned from C

### 9.1. Not every pointer can be freed arbitrarily

C functions may return:

- Pointers to static/global memory: **do not free**.
- Pointers to caller-owned objects: valid only while the owner lives.
- Pointers requiring `free`.
- Pointers requiring a **custom release API** (not libc `free`).
- Pointers to scratch buffers valid only until the next call.

Calling the wrong release function crashes the JVM or corrupts the native allocator heap.

Example API:

```c
native_result* result_create(void);
void result_destroy(native_result* result);
```

On the Java side, model `result_destroy` explicitly in the wrapper contract. Never rely on `Arena.close()` directly to free native-allocated memory unless the API transfers that ownership to the Arena.

### 9.2. Pointer sizes and bounds

A pointer returned from native code may carry only an address **without any size metadata**. Guessing byte lengths when reading/writing pointers carries severe risk.

Wrappers should obtain lengths or element counts from native APIs, check for overflow when computing `count * elementSize`, and bound segment views strictly within contracted ranges. Native APIs exposing explicit length parameters are far safer to migrate than naked-pointer APIs.

### 9.3. Null pointers are normal boundary cases to handle

C functions often return `NULL` on failure or empty results. Java FFM represents null addresses, yet wrappers must check for null before dereferencing or reinterpreting segments.

Never convert `NULL` into arbitrary valid Java objects; return `Optional`, throw exceptions, or map error codes according to the actual contract.

### 9.4. UTF-8 and C strings

A typical C string is a null-terminated byte sequence, not a Java `String` or UTF-16 buffer. When passing strings, agree on:

- Encoding, usually UTF-8 if specified by the native API.
- Null termination.
- Whether embedded null bytes are valid.
- Does native code copy the bytes or retain the pointer?
- Who is responsible for freeing the pointer?
- How invalid/malformed encodings are handled.

Never deduce from a function name alone that it expects UTF-8. Windows provides separate ANSI and wide-char API variants; pick bindings matching exact headers and ABIs.

## 10. Upcalls: native code calling back into Java

### 10.1. Callbacks are more complex than downcalls

Native libraries may accept callback function pointers and invoke them later. FFM provides **upcall stubs**, typically created with `Linker.upcallStub(...)` from a Java `MethodHandle` and `FunctionDescriptor`.

Flow:

```text
Java callback method
       |
       v
MethodHandle + FunctionDescriptor
       |
       v
Linker.upcallStub(..., Arena)
       |
       v
Native function pointer
       |
       v
C library invokes callback during or after native operation
```

When migrating JNI/JNA callbacks to FFM, verify:

- Does the native library invoke callbacks synchronously or asynchronously?
- Can callbacks arrive on native threads not created directly by the app?
- Can callbacks fire after the registering Java method returns?
- Does the upcall stub's Arena outlive all possible invocations?
- Does native code cache function pointers in global state?
- What happens under contract if the Java callback throws an exception?
- Can races occur between native unregistration and Arena closure?

### 10.2. Callback lifetime is a strict contract

A common mistake is allocating a callback stub inside a method's local confined Arena and closing it upon return while the C library keeps the pointer for asynchronous calls.

Keep the arena alive until the native library confirms no further callbacks can fire. A safe pattern:

1. Create the callback handle and stub.
2. Register with the native library.
3. Retain strong references/ownership in the wrapper.
4. During shutdown, stop accepting new tasks.
5. Unregister the callback through native APIs if provided.
6. Wait for in-flight callbacks to drain.
7. Only then close the arena and unload resources per contract.

Never assume the garbage collector preserves callbacks or that native libraries clean up every function pointer automatically.

### 10.3. Callbacks differ from Java agents

FFM upcalls allow native code to invoke a Java method via C ABI. They **are not equivalent** to JVMTI callbacks (such as `ClassFileLoadHook`), the Java Instrumentation API, or the Attach API. Native JVMTI agents must still follow JVMTI/JNI lifecycles, agent entrypoints, and attach/load policies.

You may migrate data conversion or library calls to FFM while keeping JNI/JVMTI for agent instrumentation. That separation is usually cleaner than forcing FFM to replace entire agent frameworks.

## 11. Comparing FFM with JNI, JNA, Unsafe, and DirectByteBuffer

| Criterion | JNI | JNA | FFM final | `sun.misc.Unsafe` / direct buffers |
|---|---|---|---|---|
| Project-authored native glue required? | Usually yes | Usually no for standard C calls | Usually no for compatible downcalls | Case-dependent |
| Calling C symbols directly | Yes via JNI bridge | Yes via mapping | Yes via linker/symbol lookup | Not its primary purpose |
| C struct/layout modeling | Inside C/JNI wrappers | JNA mappings | `MemoryLayout`/`ValueLayout` | Mostly manual |
| Off-heap lifetime management | Shared responsibility across C/JNI and Java | JNA Pointer/Memory APIs | `Arena`/`MemorySegment` | Often relies on manual cleanup |
| Native binary requirements | Required when building C bridge | Target library + JNA runtime | Target library | Usage-dependent |
| JDK version dependency | JNI has its own compatibility contract | JNA version must support the JDK | Final API from JDK 22 | High-risk internal API |
| JVMTI/agent instrumentation | Fits native agents | Does not replace JVMTI | Does not replace JVMTI | Does not replace |
| Java-side safety bounds | Wrapper-dependent | JNA API-dependent | Explicit bounds/lifetime/thread checks | Allows unsafe memory access |

No single mechanism fits every case. Decisions depend on native API complexity, minimum JDK, performance, security, legacy ABIs, deployment, and maintainability.

### 11.1. When to keep JNI

Keep JNI when:

- The existing bridge is stable, tested, and poses no compatibility issues.
- The application must support JDKs older than 22.
- Native code interacts deeply with JVM objects, JNI references, or JVMTI.
- The C/C++ layer implements heavy native logic where FFM adds little simplification.
- A library vendor ships only an official JNI binding.
- Rewriting the bridge carries higher risk than expected benefits.

Upgrading the JDK does not mandate deleting JNI. Ensure native libraries and wrappers remain compatible with the new JDK/OS, remove unsupported internal APIs, and test threading, GC/pinning, and deployment.

### 11.2. When to consider FFM

FFM fits when:

- The native API exposes a clear C ABI.
- Many straightforward C calls create high JNI glue maintenance overhead.
- Explicit bounds and lifetime checks on memory access add safety.
- Minimum supported JDK already covers final FFM.
- Platform-specific binaries can be pinned and integration-tested.
- The team accepts managing ABI descriptors and native-access policies.

### 11.3. When not to use FFM to blindly replace `Unsafe`

`sun.misc.Unsafe` spans capabilities beyond direct memory access: field offsets, atomics, fences, object manipulation, and JVM internals. Not every usage maps one-to-one to `MemorySegment`.

Memory access patterns can migrate to FFM; heap concurrency/atomics typically belong on `VarHandle` or standard java.util.concurrent APIs. Logic depending on internal JVM object layouts requires redesign rather than seeking unsupported equivalents.

FFM intentionally forbids reading/writing arbitrary object addresses inside the Java heap the way legacy `Unsafe` codebases often did.

### 11.4. `DirectByteBuffer` still has a role

`ByteBuffer.allocateDirect()` remains valuable for NIO channels and buffer-oriented APIs. Migrating to FFM is not mandatory.

Before migrating, assess:

- Do downstream APIs accept `MemorySegment` or only `ByteBuffer`?
- Are view adapters needed?
- Do memory ownership and cleanup semantics change?
- Are byte order, alignment, and bounds preserved?
- Does conversion introduce unwanted copies?
- Are there double-free or use-after-close hazards?

Avoid converting every direct buffer to segments when existing NIO code runs reliably with no driving requirement.

## 12. Migrating JNI/JNA to FFM: never just a simple import swap

### 12.1. JNI hides many ABI rules

An existing JNI wrapper may silently:

- Encode Java `String` into whatever encoding the C API expects.
- Construct native structs with platform alignment and padding.
- Copy Java arrays into native buffers.
- Translate error codes or `errno` into exceptions.
- Manage Java object references.
- Pin callbacks via JNI global references.
- Lock threads or serialize calls around non-thread-safe libraries.
- Free native buffers inside `finally` blocks.

Replacing `native int call(...)` with `MethodHandle.invokeExact(...)` while omitting those behaviors can corrupt state even if a trivial smoke test returns an integer.

### 12.2. Mapping the wrapper contract

For every JNI/JNA method, record:

| Attribute | Must clarify |
|---|---|
| Symbol/C signature | Exported name, argument/return ABI |
| Java-facing contract | Nullability, exceptions, timeouts, thread safety |
| Encoding | UTF-8, UTF-16, ASCII, OS-specific |
| Memory ownership | Caller, callee, shared, or global |
| Buffer sizes | Supplied by whom; byte-size vs. element-count semantics |
| Struct layout | Size, offsets, alignment, endianness |
| Callbacks | Sync/async, unregistration, and lifetimes |
| Error reporting | Return codes, `errno`, last-error, error strings |
| Library loading | Paths, transitive native deps, classloaders |
| Platform variants | Linux/Windows/macOS, x86-64/ARM64 |
| Security | Input validation, pointer safety, native-access permissions |

Inventory not just the function signature, but **everything the legacy wrapper implicitly enforced**.

### 12.3. Migrate behind adapters instead of big-bang rewrites

A neutral Java interface allows gradual switching:

```java
public interface NativeChecksum {
    int checksum(byte[] payload);
}
```

Both backends can coexist during migration:

```text
NativeChecksum
  ├── JniChecksumAdapter
  └── FfmChecksumAdapter
```

Domain code stays backend-agnostic; integration tests run the same fixtures against both implementations, comparing outputs, exception mappings, and resource behavior.

Select backends strictly by supported artifact/JDK/platform—never fall back silently on ABI errors or try loading untrusted binaries dynamically.

## 13. `jextract`: generating bindings from C headers

### 13.1. Why use a binding generator?

Writing hundreds of `FunctionDescriptor` and `MemoryLayout` declarations manually is error-prone. **jextract** is a standalone tool from OpenJDK Project Panama that generates Java bindings from C headers within the scope supported by that version.

Points to remember:

- `jextract` **does not ship inside every standard JDK distribution**.
- `jextract` versions align with specific FFM API generations.
- Parsing C headers relies on matching native toolchains, typically Clang/libclang.
- Complex macros, C++ constructs, conditional compilation, and platform headers may require special handling.
- Generated code forms part of your application's API/runtime compatibility surface.

### 13.2. Recommended pipeline

```text
Pinned C header + platform defines + toolchain
                  |
                  v
         Pinned jextract version
                  |
                  v
     Generated Java bindings (FFM API target)
                  |
                  v
       Build application/library on JDK target
                  |
                  v
      Integration tests with real native binary
```

Key inputs to track:

- Header version and checksum.
- `-I` include paths, defines, target platform/ABI.
- `jextract` version and required execution JDK.
- Generated package and class names.
- Output directories and source sets.
- Runtime symbol lookup/loading behavior.
- CI environment and Clang/compiler versions.

If headers come from a newer SDK than the production native binary, generated bindings may reference missing symbols or mismatched struct layouts.

### 13.3. Generated source is not an eternal contract

Upgrading `jextract` or changing target JDKs can change generated structure and method names. Avoid letting business logic depend directly on hundreds of generated classes; wrap them in a stable facade/adapter.

When upgrading the generator:

1. Pin input headers.
2. Regenerate in a clean environment.
3. Inspect diffs across generated sources.
4. Compile on the target JDK.
5. Run ABI/layout tests against real native binaries.
6. Run adapter contract tests.
7. Record tool versions and generated outputs in release artifacts.

Never hand-edit generated sources to paper over issues: edits vanish on regeneration or drift irreproducibly.

## 14. Native-access policies and JVM flags

### 14.1. Why restricted methods exist

Certain FFM operations—particularly constructing native linkers, downcalls, upcalls, or unrestricted segments—bypass Java memory safety and can crash the JVM if misused. The JDK gates these via **native access** controls.

For classpath / unnamed-module applications, a common flag is:

```bash
java --enable-native-access=ALL-UNNAMED \
     -cp app.jar com.example.Main
```

For named modules, grant permission only to the module requiring it:

```bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

Module names above are illustrative. Depending on the JDK release, calling restricted methods without permission emits warnings or throws errors; future releases may tighten enforcement. Check exact target-JDK behavior and treat warnings as compatibility signals rather than assuming uniform enforcement across releases.

### 14.2. Native access is not a blanket safety stamp

Enabling `ALL-UNNAMED` grants native access across all unnamed classpath modules. In modular applications, scope permissions strictly to specific modules.

Even when granted, the application remains responsible for:

- Loading trusted native libraries.
- Calling matching ABIs accurately.
- Never retaining dangling pointers.
- Respecting Arena lifetimes.
- Sanitizing untrusted inputs before passing to unsafe C code.
- Preventing leaks of file descriptors, handles, or native memory.

Native-access flags do not validate C logic or turn untrusted shared libraries into safe components.

### 14.3. Module paths, reflection, and native libraries are three distinct mechanisms

Do not confuse:

- `--enable-native-access`: governs FFM/JNI native-access policy in relevant JDKs.
- `--add-opens`: grants deep reflection permissions when justified.
- `--add-exports`: grants compile/runtime access to module packages as needed.
- `java.library.path` or library lookup paths: locates native binaries.
- `--enable-preview`: enables preview APIs on matching JDK releases.

No single flag solves FFM, JNI, and JPMS errors together.

## 15. Agents and native instrumentation: separating scopes accurately

### 15.1. Java agents use the Instrumentation API

A Java agent typically defines `premain` or `agentmain` and uses `java.lang.instrument.Instrumentation` to transform classes. Agents often rely on bytecode libraries such as ASM/Byte Buddy and carry constraints on class-file versions, module access, and attach policies.

FFM does not alter how Java agents load, replace `ClassFileTransformer`, or cure bytecode transformers that fail on new JDK class files.

### 15.2. JVMTI native agents use a distinct interface

JVMTI native agents define entrypoints like `Agent_OnLoad` and JVMTI callbacks to monitor JVM events. They interact with JNI/JVMTI structures, pointers, and memory rules defined by the agent specification.

While FFM can be used inside Java helpers calling C libraries, it cannot replace agent attachment, instrumentation, JVMTI events, or JNI object handles.

### 15.3. Categorizing issues upon JDK upgrades

| Scenario | Likely area involved |
|---|---|
| Agent fails to load after JDK upgrade | Manifest/attach policy, agent runtime, class-file target |
| Agent transform fails with `Unsupported class file major version` | Bytecode library / ASM / Byte Buddy |
| JNI library throws `UnsatisfiedLinkError` | Library path, architecture, exported symbols, native deps |
| FFM downcall denied | Native-access policy/flags |
| Native call crashes JVM | ABI/layout/lifetime mismatch or native bug |
| Callback becomes invalid | Arena/upcall stub lifetime, native unregistration |
| Framework reflection blocked | JPMS opens, framework compatibility |
| Native profiling yields different metrics | JVMTI version, OS tooling, agent implementation |

Native and agent errors can co-occur; categorize carefully to avoid attempting FFM migration when bytecode instrumentation is the real culprit.

## 16. JDK version, ABI, and operating system: three compatibility dimensions

Native bindings never depend on "Java version" alone.

### 16.1. Minimum JDK

- JDK 17: no final FFM.
- JDK 21: FFM preview requiring matching source/runtime flags.
- JDK 22+: final FFM API under JEP 454, while still monitoring native-access policy changes across releases.

If shipping a library supporting Java 17, you cannot expose final JDK 22 `java.lang.foreign.MemorySegment` in public methods and expect Java 17 consumers to compile or run normally.

### 16.2. OS and architecture

Matching native binaries must exist for every supported target:

- Linux x86-64 / ARM64.
- Windows x86-64 / ARM64 if supported.
- macOS x86-64 / Apple Silicon.
- Relevant Linux libc/toolchain variants (e.g., glibc vs. musl).
- Specialized CPU ABIs, calling conventions, and endianness where relevant.

"Write once, run anywhere" Java bytecode does not make native shared libraries cross-platform. Every OS/architecture requires matching native artifacts and tests.

### 16.3. 32-bit, 64-bit, and host endianness

Pointer width, `size_t`, and alignment vary across platforms. Java memory layouts must match the host ABI rather than development-laptop assumptions.

Byte order matters too: native structs often use host endianness, whereas files and network protocols specify fixed byte orders. Never persist raw native struct layouts across platforms without explicit normalization.

### 16.4. Native library ABI versions

Identical symbol names do not guarantee compatible structs or contracts. Vendors may change layouts, insert fields, alter enums, or shift ownership semantics between releases. Manage C header and shared binary versions together just as strictly as Java APIs and implementations.

## 17. Testing lifetimes and concurrency at the FFM boundary

### 17.1. Edge scenarios to test explicitly

- Reading/writing right at 0-byte, 1-byte, and max-capacity boundaries.
- Accessing segments after Arena closure.
- Accessing confined segments from another thread.
- Calling native functions after library lookup lifetimes expire.
- Native functions returning null pointers or error codes.
- C-allocated buffers where Java omits calling custom release APIs.
- Java-allocated buffers where C retains pointers past return.
- Upcalls firing after Java unregistration or arena closure.
- Concurrent closes while downcalls are in flight.
- Multi-threaded virtual/platform thread calls hitting non-thread-safe native libraries.
- Canceling or timing out Java tasks mid-blocking native call.

### 17.2. Java timeouts do not automatically cancel native calls

Interrupting or timing out a Java task does not abort an executing blocking C call. If the native library exposes a cancellation API, integrate it cleanly in wrappers and ensure thread/resource cleanup.

Without a native cancellation contract, consider execution isolation, concurrency limits, watchdogs, or out-of-process execution. Never assume virtual threads make blocking native calls safely cancellable.

### 17.3. Java exceptions cannot freely cross the C ABI

C functions have no concept of Java checked exceptions. Wrappers must translate:

- Return/error codes.
- `errno` or native last-error state.
- Native-owned error messages.
- Null results.
- Callback failures.
- Fatal signals or process crashes.

A native segfault never turns into a catchable `IOException`. If native libraries risk crashing, out-of-process isolation becomes a critical architectural safeguard.

## 18. Performance: do not replace JNI with FFM based on microbenchmarks alone

### 18.1. Boundary overhead is only one piece

End-to-end performance depends on:

- Frequency and granularity of native calls.
- String/array/struct marshaling overhead.
- Buffer allocation and copying.
- Synchronization and lock contention.
- Thread confinement vs. shared arenas.
- Upcall callback rates.
- Work done inside the native library itself.
- GC, off-heap memory, and cleanup costs.
- JIT warmup, CPU/OS/toolchain, and virtualization.

Measuring two integers added in C captures boundary latency, not an image-processing pipeline or native database engine.

### 18.2. Benchmarks must reflect real workloads

Useful benchmark categories:

1. Simple primitive downcalls.
2. Calls passing pointers and small arrays/buffers.
3. Calls processing large buffers.
4. Batched native work inside single downcalls.
5. Native → Java upcall callbacks.
6. Multi-threaded throughput and tail latency.
7. Per-request allocation/cleanup patterns.
8. Real supported platforms and architectures.

Use JMH to control warmup, forking, and measurement across backends. Never compare runs executed with mismatched debug flags, profilers, or JVM options as direct evidence.

### 18.3. Safety and maintainability also count

Even when FFM performs comparably to tightly tuned JNI, clearer memory lifecycles and reduced C glue may justify it. Conversely, if FFM descriptors become overly convoluted for complex C++ APIs, existing JNI bridges may remain more maintainable.

Migration choices must balance **correctness, safety, portability, operations, and performance**—not throughput alone.

## 19. Build and packaging for native integration

### 19.1. Java modules and native artifacts must be versioned together

A repository layout may look like:

```text
native-bridge/
  ├── Java API module
  ├── FFM implementation module
  ├── generated bindings
  ├── C headers
  ├── native libraries per platform
  ├── integration tests
  └── release manifest
```

Native binaries may build via CMake/Meson/Make or come from vendors. Java builds use Maven/Gradle yet cannot verify C toolchains or ABI matches automatically.

### 19.2. Maven/Gradle must pin both tools and runtimes

When using `jextract` or native toolchains:

- Pin generator versions and the JDK executing the generator.
- Pin C compilers/toolchains and native SDK versions.
- Declare explicit input headers, preprocessor defines, and output paths.
- Prevent uncontrolled native binary downloads during build tasks.
- Record OS/architecture metadata.
- Wire generated sources into proper source sets.
- Build packages/launchers selecting matching native binaries.
- Validate on clean checkouts and target containers/VMs.

Do not ship entire build-workstation native SDKs inside production containers when only shared runtime libraries are needed. Conversely, never ship Java bindings without ensuring native binaries are packaged and resolvable at runtime.

### 19.3. Safe library loading mechanisms

Restrict ambiguous search paths; incorrect directory precedence can load spoofed DLL/SO files. Apply artifact integrity verification and repository/packaging policies.

On the classpath/module path, determine where native binaries live inside JARs/distributions. Frameworks that extract native libraries into temporary directories must verify permissions, cleanup, concurrent startup safety, and behavior under read-only container filesystems.

### 19.4. GraalVM Native Image

If building native images with GraalVM, verify FFM API support, dynamic library lookup, reflection/native-access metadata, and platform constraints for your exact GraalVM release. Never assume HotSpot JDK 22 FFM bindings work unchanged inside Native Image.

FFM does not automatically solve AOT compilation, static/shared linking, or runtime symbol visibility.

## 20. Migrating from `Unsafe` or JNI when supporting multiple JDKs

### 20.1. Neutral Java-facing APIs without FFM types

A library supporting both Java 17 and Java 22+ should expose public interfaces free of FFM types:

```java
public interface NativeDigest {
    byte[] digest(byte[] bytes);

    void close();
}
```

Backed by separate implementations:

```text
app-api
  |
  +-- legacy-jni-backend  (Java 17-compatible)
  |
  +-- ffm-backend         (Java 22+)
```

Separate modules or artifacts can target distinct runtimes. If using multi-release JARs, strictly verify runtime class-loading rules; avoid forcing MR-JARs just to save artifacts when public APIs differ.

### 20.2. Do not compile final FFM sources with `--release 17`

Source importing:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
```

cannot be labeled Java 17-compatible via `--release 17`. Those classes do not exist in Java 17 platform APIs, and compilers will rightly reject them.

To support both Java 17 and 22+ from one release line, isolate FFM classes in a source set or module compiled for Java 22+ and ensure Java 17 runtimes never load them during startup or execution.

### 20.3. Rolling deployments require stable boundary contracts

When swapping JNI for FFM, native function outputs must not unexpectedly alter formats:

- Byte layouts and endianness.
- Struct fields and padding.
- Error code translations.
- String encodings.
- Resource ownership rules.
- Ordering and concurrency guarantees.
- Callback/lifecycle semantics.

If the system persists files or transmits network payloads, test compatibility across mixed versions before canary rollouts. Native bridge migrations can alter wire outputs even when Java business code stays untouched.

## 21. Common failures and investigation starting points

| Error or symptom | Possible cause | Check first |
|---|---|---|
| `package java.lang.foreign does not exist` | Compiler/target JDK too old | JDK version, toolchain, and `--release` |
| Preview FFM source fails to compile | Source targets a different preview release | Check JDK 21 vs. 22+ APIs and flags |
| Restricted native-access warning/error | Missing native-access grant | Named/unnamed modules and JDK policy |
| `UnsatisfiedLinkError` | Missing native binary/deps or wrong architecture | Library path, OS/CPU ABI, exported symbols |
| Lookup cannot find symbol | Wrong library version, name mangling, hidden export | Export table and binary checksum |
| `WrongMethodTypeException` | `MethodHandle` call-site signature mismatch | Carrier types and descriptor |
| JVM crashes during downcall | Wrong ABI descriptor, pointer/lifetime bug, native bug | Crash dumps/`hs_err`, C signatures, layouts |
| Segment access fails after close | Arena already closed | Ownership/lifetime and cleanup |
| Confined segment fails from another thread | Thread confinement violation | Thread ownership / shared Arena design |
| Corrupt struct data on Windows | C `long`/alignment/packing differs from Linux | `sizeof`, `offsetof`, and ABI |
| Returned buffer holds garbage data | Invalid pointer or freed by native side | Ownership contract and callback timing |
| Unbounded native memory growth | Missing custom release / destroy calls | Resource lifecycles and leak metrics |
| Crash in callback after shutdown | Native code holds closed upcall stub | Unregistration, in-flight drain, Arena lifetime |
| JNI works while FFM gives wrong result | Legacy wrapper performed implicit conversion/validation | Compare wrapper semantics and fixtures |
| Java agent fails after JDK upgrade | Instrumentation/bytecode API issue, not FFM | ASM/Byte Buddy/JVMTI versions |
| Native Image fails to load library | Missing AOT config/runtime support/packaging | GraalVM support matrix and linker settings |

Never assume "FFM has a bug" just because an error appeared during migration. Capture OS, architecture, JDK vendor/build, native library checksum, C header version, and a minimal reproducer.

## 22. Investigating native crashes

Native crashes can terminate the entire JVM, requiring a different workflow than Java exceptions.

### Step 1: Reproduce in isolation

Use small fixtures outside production with trusted inputs and verified native libraries.

### Step 2: Capture complete environment details

- JVM vendor, version, and build.
- OS, kernel, and architecture.
- Native library path, checksum, and version.
- C compiler, flags, and linked dependencies.
- Function symbol, descriptor, and layouts.
- Thread/concurrency scenario.
- Native-access flags and module configs.
- Crash logs such as `hs_err_pid*.log` emitted by the JVM.

### Step 3: Verify ABI before optimizing

Compare C headers against `FunctionDescriptor`; inspect argument widths, alignments, struct offsets, and calling conventions. For C++ APIs, verify `extern "C"` exports or controlled C ABI wrappers.

### Step 4: Inspect pointers and lifetimes

Verify buffer owners, lengths, thread access, arena closures, and native free calls. Invalid pointer bugs may crash only under concurrency or on a different architecture.

### Step 5: Use native debuggers when needed

Tools such as gdb, lldb, WinDbg, or native sanitizers assist diagnosis. Evaluate native address/undefined-behavior sanitizers per toolchain, mindful of overhead and JVM interaction.

### Step 6: Add regression tests

Do not stop after fixing one crash; add reproducible boundary tests covering inputs, offsets, and lifetimes across all supported platforms.

## 23. Practical migration scenario: JNI bridge to FFM

Suppose an image-management service has:

- Java 17 production runtime.
- JNI bridge calling a C library for image resize/compression.
- C functions taking pointers + length and returning an output pointer.
- Custom `image_result_free` release function.
- Progress notification callback.
- Native binaries for Linux x86-64 and Windows x86-64.
- Long-term target of JDK 22+ and less JNI glue.

### Phase 1: Inventory and baseline

Matrix all function signatures, struct layouts, ownership rules, callback lifecycles, and error mappings. Save native SDK/library versions, C headers, and representative image fixtures.

### Phase 2: Stabilize the public Java API

Extract an `ImageNativeEngine` interface accepting/returning `byte[]` or stable DTOs; keep the JNI implementation as baseline. Avoid leaking `MemorySegment` into public contracts while Java 17 consumers remain.

### Phase 3: Build the FFM backend for downcalls

Start with stateless, fixed-arity functions: reading native version strings, configs, or simple resize calls. Match C ABI descriptors and manage buffers via arenas and native release APIs.

### Phase 4: Migrate ownership carefully

Native functions returning pointers require `image_result_free`. The FFM adapter copies outputs when needed and calls the exact release function inside `finally`. Never use `Arena.close()` as a substitute for custom native free functions.

### Phase 5: Migrate callbacks

Ensure upcall stubs outlive native unregistration and await draining in-flight callbacks. Test shutdown, timeouts, cancellation, and concurrent jobs.

### Phase 6: Compare behavior

Run identical image fixtures through JNI and FFM, checking output bytes/quality within tolerance, error codes, exception mapping, memory usage, latency, and throughput.

### Phase 7: Package and test per platform

Build platform-specific JARs/native packages, run on target JDKs, and validate supported containers, OSes, and CPUs. Verify native-access permissions and library resolution at startup.

### Phase 8: Canary and rollback

Route a slice of traffic to the FFM backend while monitoring crashes, heap/off-heap memory, native handle counts, error rates, and latency. Keep the JNI backend ready for rollback during transition if deployment constraints allow.

Retire JNI only once all contracts are verified and minimum supported JDKs no longer need Java 17 backends.

## 24. Example native memory wrapper with explicit ownership

A Java wrapper around native resources should model lifetimes explicitly instead of returning bare segments:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

public final class NativeBuffer implements AutoCloseable {
    private final Arena arena;
    private final MemorySegment segment;

    public NativeBuffer(long bytes) {
        this.arena = Arena.ofConfined();
        try {
            this.segment = arena.allocate(bytes);
        } catch (RuntimeException | Error failure) {
            arena.close();
            throw failure;
        }
    }

    public MemorySegment segment() {
        return segment;
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

Usage:

```java
try (NativeBuffer buffer = new NativeBuffer(256)) {
    MemorySegment segment = buffer.segment();
    // Invoke synchronous native API without retaining the pointer past this scope.
}
```

This illustrates ownership of **Arena-allocated** memory. It is unsuitable for managing native pointers allocated by external libraries, lacks async callback handling, and is not automatically thread-safe. Production wrappers may need close idempotency guards, ownership transfers, and concurrency protection.

The core lesson is designing APIs that clarify who closes resources rather than scattering `Arena.close()` or custom free calls across business code.

## 25. Standardizing native backend strategies across an organization

When multiple services share a native library, avoid letting every team write inconsistent FFM/JNI wrappers. Publish an internal SDK providing:

1. A neutral Java-facing facade free of ABI types when multiple JDKs are supported.
2. JNI/JNA/FFM backend selection aligned to minimum runtimes and support matrices.
3. OS/CPU native binary metadata and checksums.
4. Version-pinned generated bindings.
5. Centralized native-access flags and module descriptors.
6. Typed error mapping, lifetime, and thread-safety contracts.
7. Cross-platform integration tests.
8. Resource-leak/crash metrics and runbooks.
9. ABI/binary compatibility release notes.
10. Clear rollback/fallback rules that never mask errors silently.

FFM does not need to power every native integration; the SDK can standardize selection criteria and migration assessments. A stable Java API with swappable, controlled backends is far more valuable than leaking `MemorySegment` and `MethodHandle` across domain code.

## 26. Pre-release verification record

Replacing JNI/JNA/Unsafe with FFM requires handing off the following evidence:

| Evidence | Contents |
|---|---|
| Version matrix | Build/runtime JDKs, FFM generation, native library versions |
| C ABI inventory | Function signatures, calling conventions, struct sizes/offsets |
| Memory ownership matrix | Caller/callee allocations, release functions, lifetimes, threading |
| Callback contract | Registration, unregistration, in-flight calls, shutdown |
| Native binary manifest | OS/arch, checksums, compilers, linked dependencies |
| Generated binding record | `jextract`/tool versions, headers, flags, outputs |
| Permissions | Native-access policies by named/unnamed modules |
| Integration report | Contract fixtures, accurate outputs, errors, null pointers |
| Performance report | CPU, latency, throughput, off-heap memory, resource leaks |
| Security review | Input trust, library provenance, native code audit/boundaries |
| Deployment report | Library loading inside artifacts/containers, startup smoke tests |
| Rollback plan | Backend/binary/JDK compatibility and rollback triggers |

If supporting multiple JDKs, track separate columns per runtime: JDK 17/JNI, JDK 21/preview (if intentional), JDK 22+/FFM final. Never lump multiple environments into a single "Java compatible" check.

## 27. Common misconceptions

| Misconception | Reality |
|---|---|
| "FFM became final in JDK 21" | JDK 21 was preview; finalized in JDK 22 per JEP 454 |
| "Final FFM works on Java 17 just by adding a JAR dependency" | Not a Java 17 standard API; requires another backend or raising minimum JDK |
| "FFM replaces all JNI/JVMTI agents" | Does not replace JVM instrumentation, JVMTI callbacks, or all JNI operations |
| "MemorySegment makes native code completely safe" | Java-side bounds/lifetime checks cannot guard every C memory bug |
| "Closing an Arena frees all C pointers" | Native-owned pointers often require custom release APIs |
| "Shared Arenas synchronize multi-thread access automatically" | Shared access is not data-race-free |
| "Java long always equals C long" | C `long` varies by ABI and OS |
| "C struct size equals the sum of field sizes" | Padding and alignment apply |
| "jextract ships inside every JDK" | It is a separate tool; pin versions matching APIs/headers |
| "Passing --enable-native-access fixes every crash" | Flags never fix wrong ABIs, bad pointers, or broken libraries |
| "Legacy JNI bridges must be deleted upon JDK upgrade" | Retaining JNI may remain a lower-risk, supported choice |
| "Native callbacks stay valid after method return" | Depends on stub/Arena lifetime and native unregistration |
| "Linux native binaries run on Windows with the same Java bytecode" | Native binaries are OS- and architecture-dependent |
| "Future timeout cancels executing native functions" | Blocking native calls follow explicit cancellation contracts |
| "FFM running on HotSpot works identically in Native Image" | Verify GraalVM AOT/runtime/toolchain support explicitly |

## 28. FFM migration checklist

### Platform and versions

- [ ] Identified minimum supported JDK and distinguished FFM preview from final.
- [ ] Locked build JDK, runtime JDK, and class-file targets.
- [ ] Confirmed `java.lang.foreign` appears only in modules/artifacts backed by compatible runtimes.
- [ ] Recorded native-access flags and policies per JDK release.
- [ ] Defined any JNI/JVMTI agent responsibilities that must remain.

### ABI and data layouts

- [ ] Cross-checked C headers against `FunctionDescriptor`s.
- [ ] Verified sizes, alignments, padding, and pointer widths per OS.
- [ ] Distinguished C `long`, `size_t`, `wchar_t`, signed/unsigned types.
- [ ] Verified string encodings, null termination, and conversions.
- [ ] Checked null pointers, buffer lengths, and integer overflows.
- [ ] Standardized error/`errno`/native last-error mappings where needed.
- [ ] Recorded binary/library ABI versions and exported symbols.

### Lifetimes and concurrency

- [ ] Every native allocation has an explicit owner and release function.
- [ ] Segments are never accessed after Arena closure.
- [ ] Native pointers are not retained beyond valid lifetimes.
- [ ] Selected confined/shared/automatic arenas per contract.
- [ ] Verified thread safety, concurrent closes, and cancellation.
- [ ] Verified upcall stub lifetimes and callback unregistration.
- [ ] Identified native calls that block non-cancellably.

### Build and deployment

- [ ] Pinned `jextract`/tool versions, headers, and generated bindings.
- [ ] Built/packaged native binaries for every supported OS/architecture.
- [ ] Locked down shared library paths and binary integrity checks.
- [ ] Clean CI builds can regenerate bindings when required.
- [ ] Verified library lookup and symbol resolution on final packaged artifacts.
- [ ] Checked container permissions, native dependencies, and startup.
- [ ] If using Native Image, tested on exact GraalVM versions/runtimes.

### Verification and release

- [ ] Compared outputs and error semantics across legacy and new backends.
- [ ] Executed tests covering nulls, bounds, lifetimes, alignments, and callback races.
- [ ] Tested across every committed JDK/OS/architecture combination.
- [ ] Monitored off-heap memory, native handles, and crash logs.
- [ ] Benchmarked representative workloads rather than microbenchmarks alone.
- [ ] Prepared rollouts, rollbacks, and incident owners for native failures.
- [ ] Archived ABI inventories, ownership matrices, and release manifests.

**Conclusion:** The FFM API establishes a standard path for calling C functions and managing off-heap memory from Java, especially from JDK 22 onward once finalized. Yet moving from JNI, JNA, `Unsafe`, or custom native bridges to FFM is never a mere import change; it is a migration of **ABIs, memory ownership, callback lifecycles, native-access permissions, packaging, and JDK/OS matrices**. Maintain stable Java facades, migrate well-contracted functions incrementally, validate against real native binaries, and retire legacy backends only once full compatibility and rollback readiness are proven.
