# Source-Level API and Binary-Level ABI in Java–C Interoperability

## 1. Two Different Contracts

When a Java program uses a C library, at least two questions must be answered: **what interface can the source code use?** and **does the compiled machine code call the loaded binary library correctly?** The first question belongs to the API; the second question belongs to the ABI.

- **API (Application Programming Interface)** is the contract at the programmer level: function/method names, parameter types and return types, constants, public data types, calling usage, preconditions, postconditions, errors, and the meaning of the operation. For C, the API is typically described by header files (`.h`) and documentation; for Java, by class/method declarations along with behavioral documentation.
- **ABI (Application Binary Interface)** is the contract for *compiled* components to link and exchange data at the machine level: exported symbol names, how parameters are passed and return values are received, data size/alignment/layout, function calling conventions, library linking and loading mechanisms, as well as conventions specific to the operating system, architecture, and toolchain.
- **Behavioral contract** also needs to be considered separately when evaluating upgradability: a library may preserve its ABI yet return different results or change the meaning of a parameter, causing the application to malfunction even though linking succeeds.

| Question | Source-Level API | Binary-Level ABI |
| --- | --- | --- |
| Who uses it directly? | Programmers and the compiler when reading/compiling source code | Compiler, linker, loader, runtime, and generated machine code |
| Examples of the contract | `int32_t sum(int32_t a, int32_t b)`; input requirements; meaning of the result | Symbol `sum`; register/stack locations for the two arguments; return rules for `int32_t` |
| Typical verification | Compiling client code against the new header/API; testing behavior | Running the **old binary** against the new library; checking symbols, layout, calling convention |
| Typical failure | Compiler reports missing name/type or invalid call | Symbol not found, calling with wrong binary signature, reading wrong offset, crash, or data corruption |
| Changing platforms | Source-level calls may remain unchanged | May require a different binary library for the new OS/CPU/ABI |

**Key takeaway:** source code that still compiles **does not prove** that an old binary still runs correctly; a library that loads successfully **does not prove** that calls match the ABI or preserve behavior. Source compatibility, binary compatibility, and behavioral compatibility are three related but distinct checks.

## 2. A C Declaration Does Not Describe the Entire ABI

Suppose a library publishes the following header:

```c
/* calc.h */
#ifndef CALC_H
#define CALC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns the sum of two 32-bit signed integers. */
int32_t add_i32(int32_t left, int32_t right);

#ifdef __cplusplus
}
#endif

#endif
```

From the API perspective, client code knows the name `add_i32`, two `int32_t` inputs, the `int32_t` return type, and the meaning of addition. C code can write `int32_t result = add_i32(7, 5);` once the header is included and the appropriate library is linked.

From the ABI perspective, agreements must still be reached on things that cannot be fully determined by looking at the declaration line alone:

1. **Symbols and linking:** machine code must find the exact symbol name exported from the dynamic/static library. `extern "C"` when compiled with C++ requests C language linkage, which usually avoids C++ name mangling for the C interface; it **does not** automatically guarantee compatibility of all types, layouts, or calling conventions.
2. **Calling convention:** which argument goes in which register, which argument goes on the stack, how the stack is aligned and cleaned up, and where the return value is placed. Actual rules depend on the target ABI.
3. **Data representation:** bit width, alignment, signedness; for `struct`, also field order, padding, offsets, and how structs are passed/returned across function boundaries. `int32_t` has an exact width of 32 bits when provided, but it does not determine the entire parameter-passing mechanism.
4. **Binary format and environment:** object format such as ELF/PE/Mach-O, library format, CPU architecture, pointer width, loader rules, and versions of dependent libraries.
5. **Resource management rules at the boundary:** who allocates/frees, how long a pointer remains valid, which thread callbacks run on, and who owns the memory. This part is often published as part of the API contract, but getting it wrong can cause severe native errors.

ABI is not a single C standard applicable to every machine. For example, on many x86-64 systems, Linux uses the LP64 model (`long` and pointers are typically 64-bit), whereas Windows x64 uses LLP64 (`long` is 32-bit, pointers are 64-bit). Both can accept the same C syntax but require platform-appropriate binaries and data mappings.

## 3. Distinguishing API Changes from ABI Changes Through Scenarios

### Scenario A — Preserving API, Preserving ABI

The library changes the internal algorithm inside `add_i32` while still exporting the old symbol, keeping the exact binary signature and promised results. Client source code still compiles; old client binaries can still link/run in the same ABI environment. Internal optimizations, when they do not alter the public contract, are usually compatible changes.

### Scenario B — Renaming the API and Dropping the Old Symbol

Header v1 declares `add_i32`; v2 only has `sum_i32`. Old source code calling `add_i32` no longer compiles against header v2; old binaries requiring the symbol `add_i32` also cannot link if library v2 removed that symbol. This is a breaking change at both layers.

Binary compatibility can be preserved by **continuing to export `add_i32` as a wrapper** that calls `sum_i32`, while publishing the new name for new source code. Renaming in the header does not necessarily require removing the entry point for old binaries.

### Scenario C — Source Code Remains Valid, but Binary Layout Has Changed

Consider a public type exchanged directly between the library and client code:

```c
/* ABI v1 */
typedef struct {
    uint32_t id;
    uint8_t enabled;
} Record;

/* ABI v2: keeps both field names but swaps their order */
typedef struct {
    uint8_t enabled;
    uint32_t id;
} Record;
```

C code using `record.id` and `record.enabled` may still compile after updating the header. However, machine code compiled against v1 has already baked in the offset of each field; if it receives a pointer to an object with the v2 layout, it will read/write at the wrong locations. On a common ABI that aligns `uint32_t` to 4 bytes, v1 typically places `id` at offset 0 and `enabled` at 4; v2 typically places `enabled` at 0 and `id` at 4. **Do not assume these offsets on every platform**: verify using `offsetof`/`sizeof` with the exact compiler, target, and flags.

```c
#include <stddef.h>
#include <stdio.h>
#include <stdint.h>

typedef struct {
    uint32_t id;
    uint8_t enabled;
} Record;

int main(void) {
    printf("id=%zu enabled=%zu size=%zu\n",
           offsetof(Record, id),
           offsetof(Record, enabled),
           sizeof(Record));
}
```

Compile/run, for example on Linux with C11: `cc -std=c11 record.c -o record && ./record`. The program **prints the actual offsets and size of the running environment**; there is no single fixed stdout string guaranteed across all ABIs. If the struct changes, compare the results between the two versions on the same target.

### Scenario D — Linker Finds the Symbol, but Machine Signatures Do Not Match

Suppose an old binary was compiled against `int32_t get_total(void)`, while the new library implements an exported function with the **same name** that returns `int64_t`. In C, ordinary symbol names do not fully encode parameter types or return types. The linker can therefore find the symbol, yet the old caller and the new function no longer agree on how to read the return value; calling across an incompatible interface can lead to undefined behavior. Do not use “loaded successfully” as a criterion to conclude ABI safety.

Changing the calling convention, changing a parameter from by-value to a pointer, or changing the allocation mechanism can also break the binary contract. Depending on the type of change, the error may manifest immediately upon call or only surface under real load.

### Scenario E — ABI Preserved, but Behavior Is Wrong

The function `read_data(void *buf, size_t size)` still has the same symbol and calling convention, but the new version implicitly interprets `size` as “number of elements” instead of “number of bytes”. The binary still loads and can be called; data may be written past the buffer. This is **breaking the behavioral contract of the API** even though the ABI shape is unchanged.

A change that only adds comments, renames parameters in a C declaration, or adds a `static inline` utility function to a header usually does not require changing the library's exported ABI. However, already-compiled code does not automatically pick up new inline logic until it is recompiled.

## 4. The Java ↔ C Boundary: Both Layers Must Match Simultaneously

Java runs bytecode according to the JVM's type system; C uses the platform's binary conventions. JNI (Java Native Interface) bridges them with specific rules for native method names, type mappings, hidden parameters, and object lifetimes. The public Java API may look simple, but the C library must conform to the JNI ABI.

Minimal runnable example with JDK 17 or later, GCC/Clang, and Linux.

**File `demo/NativeMath.java`:**

```java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println(add(7, 5));
    }
}
```

**Generate the JNI declaration and implement the native code** from the directory containing `demo`:

```bash
javac -h . demo/NativeMath.java
```

This command generates the class file along with the JNI header `demo_NativeMath.h`. In the case above, the header declares a function named `Java_demo_NativeMath_add`, with return type `jint` and parameters `JNIEnv *`, `jclass`, `jint`, `jint`.

**File `native_math.c`:**

```c
#include "demo_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_NativeMath_add(
        JNIEnv *env, jclass type, jint a, jint b) {
    (void)env;
    (void)type;
    return a + b;
}
```

**Compile and run on Linux** (set `JAVA_HOME` to the JDK in use):

```bash
cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native_math.c -o libnative_math.so

java -Djava.library.path=. demo.NativeMath
```

Expected output on **stdout**:

```text
12
```

Depending on the JDK version and native access permission configuration, additional warnings may appear on **stderr**. On Windows/macOS, the library file extension, build command, and OS-specific JNI include directory will differ.

Here, three layers must be clearly distinguished:

- **Java API:** `NativeMath.add(int, int)` returns `int`, and the caller understands the meaning of addition. Bytecode carries the method descriptor `(II)I` (two `int` inputs, one `int` output).
- **JNI bridge:** entry point name `Java_demo_NativeMath_add` (for the non-overloaded method in the example), hidden parameters `JNIEnv *` and `jclass` because the method is `static`, `jint` for Java `int`; the `JNIEXPORT`/`JNICALL` macros handle the required export and calling convention.
- **Native platform ABI:** `libnative_math.so` must be built for the OS/CPU/ABI on which the JVM actually runs; the library must export the right symbol, follow the target's calling rules, and adhere to JNI rules.

If Java `int add(int,int)` is changed to `long add(long,long)`, the JVM descriptor changes from `(II)I` to `(JJ)J` and the native code must be updated accordingly to `jlong`. You must not keep the old C function taking `jint` and assume that having the same symbol name is enough. When there are overloaded `native` methods, long JNI names encode the descriptor to disambiguate them; always use the header generated by `javac -h` or register accurately with `RegisterNatives`.

**Distinguishing errors:** `NoSuchMethodError` may occur when old Java bytecode calls a Java method that no longer has the expected name/descriptor; `UnsatisfiedLinkError` is usually related to failing to load the library or find the native implementation. Both are signals to investigate, not automatic confirmation of a specific root cause. A case where the C/JNI signature is wrong yet the symbol is still found can be more dangerous: the JVM may crash or corrupt data without a helpful Java exception.

### When Using the Foreign Function & Memory API (FFM)

Since **JDK 22**, the FFM API (`java.lang.foreign`) has been finalized, allowing C functions to be called via `Linker` and signatures to be described using `FunctionDescriptor`. For example, a signature “returns `int`, takes two `int`s” can be described by the following Java fragment (not a standalone program):

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
Linker linker = Linker.nativeLinker();
```

`Linker.nativeLinker()` uses the ABI of the running native platform; the descriptor must **accurately** reflect the signature of the C function that the symbol points to. FFM changes how the bridge is declared, **not the responsibility to ensure ABI compatibility**: choosing the wrong layout, pointer type, access permissions, or memory segment lifetime can still make the program incorrect or cause severe errors. Calls to restricted APIs are subject to native access rules depending on the JDK version and module configuration.

## 5. Checklist When Upgrading a Native Library Version

Evaluate changes along **two separate tracks**: rebuilding clients from source and running already-compiled clients.

1. **Public API definition:** compare function names, prototypes, public structs/enums, constants, error descriptions, parameter semantics, and ownership rules. If behavior changes, explicitly document it as a breaking change even if the ABI is unchanged.
2. **ABI comparison on each target:** verify exported symbols, library name, parameter count/sizes, calling convention, size/alignment/offsets of public structs, pointer width, allocation conventions, and system runtime dependencies.
3. **Keep old client binaries to test upgrades:** run executables/JNI wrappers built against version N-1 with library N; simultaneously recompile source code against header N. Running only one of these two tests is insufficient.
4. **Verify the right library is loaded:** on Linux, `nm -D libnative_math.so` or `readelf -Ws libnative_math.so` to inspect symbols, `ldd` to inspect dynamic dependencies; on Windows, `dumpbin /exports` is typically used; on the Java side, `javap -s demo.NativeMath` to inspect descriptors. Tools vary by OS and binary format.
5. **Test hard edge cases:** integer boundary values, null pointers, structs on both sides, lifetime after release, callbacks, multithreading, error handling, and buffer lengths. Layout/ownership bugs often do not show up in a “hello world” test.

### Designing C APIs for a More Durable ABI

- Prefer **opaque handles** instead of letting clients directly access internal struct layouts, for example publishing `typedef struct Context Context;` and providing `context_create`/`context_destroy` along with operation functions. Changing internal fields does not break old clients that depend on offsets.
- Use explicit-width types (`int32_t`, `uint64_t`) when exact representation is needed; do not assume `long` or pointers have the same size across all OSes. Document endianness, encoding, alignment, and how buffers are passed.
- Expose C linkage at C++ boundaries with `extern "C"`; avoid passing C++ classes, STL containers, exceptions, or compiler-dependent layouts directly across an ABI intended for multiple toolchains.
- Do not silently change a signature or reuse an old symbol with a new meaning. When a breaking change is necessary, create a new versioned symbol/entry point and maintain the old wrapper during a transition period if possible.
- If passing a public struct is unavoidable, consider a `size`/`version` field and a well-defined reserved area; establish rules for versioning, initialization, and buffer size before adding fields. Do not assume that appending a field to the end of a struct is always safe when passing the struct **by value**.
- Clearly specify “whoever creates it, frees it”, which allocator is used, whether a pointer remains valid after the call, and how errors are returned. Ensure the same runtime/allocator when the API requires it, especially across module boundaries or different platforms.

## 6. Self-Check

**Question 1.** A new header only renames parameter `left` to `x`, while the prototype, symbol, and behavior remain unchanged. Do all old applications need to be rebuilt? **Not for this ABI reason**: C parameter names do not participate in the calling convention or the function symbol.

**Question 2.** The `process` symbol still exists, but the field order in a public struct passed by pointer was swapped. New client source code still compiles. Can the library binary be replaced immediately without rebuilding clients? **It cannot be assumed safe**: old binaries use offsets from the old layout; you must preserve the old layout or provide an appropriate conversion/versioning mechanism.

**Question 3.** A JNI library loads, but a Java method changed `int` to `long`. Is renaming the library file properly enough? **No**: you must synchronize the Java descriptor, type mapping (`jint`/`jlong`), native registration or entry point, C signature, and the compiled binary.

**Question 4.** Do the same header and the same ABI guarantee that the application runs correctly? **No**: you also need the behavioral contract, memory management, execution environment, and cross-boundary Java/C assumptions to match.

## 7. Key Takeaways

- **API** answers “what is source code allowed to call and what does the operation mean?”.
- **ABI** answers “by what convention does a built binary transfer control and exchange data with another binary?”.
- **Source compatibility ≠ binary compatibility ≠ behavioral compatibility.** Across the Java–C boundary, you must check both the Java method descriptor/JNI or FFM mapping **and** the actual ABI of the OS/CPU/compiler.
- For library upgrades, the strongest evidence is **building old source code against the new interface while also running old binaries against the new library**, then verifying results and memory safety against the contract.

### References

- [GCC — Binary Compatibility](https://gcc.sourceware.org/onlinedocs/gcc/Compatibility.html): calling convention, layout, binary compatibility.
- [Oracle — JNI Design Overview](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html): JNI method name mapping and linking rules.
- [Oracle — Foreign Function and Memory API (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): calling native functions and managing foreign memory.
