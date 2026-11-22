# The MemorySegment, Arena, MemoryLayout, SymbolLookup, and Linker Model

## 1. Goal: assembling the Foreign Function & Memory (FFM) model correctly

When Java needs to read/write native memory or call a function in a C library, the **Foreign Function & Memory API (FFM)** provides the components to represent memory regions, lifetimes, data layouts, symbol names, and calling rules according to the native ABI. This lesson uses the **official API from JDK 22 onward** in the `java.lang.foreign` package. JDK 17 had an *incubator* FFM with a different package and API; JDK 19–21 had different preview versions. Therefore, JDK 22+ sample code is not an example that runs directly on Java 17.

Five components to distinguish:

| Component | Question it answers | Example |
|---|---|---|
| **`MemorySegment`** | Which byte region is being accessed, how long is it, and is it still valid? | `segment.get(JAVA_INT, 0)` |
| **`Arena`** | Who allocates native bytes, how long is the lifetime, and which thread may use it? | `try (Arena a = Arena.ofConfined())` |
| **`MemoryLayout`** | What are the types, field offsets, alignment, and array stride of those bytes? | `MemoryLayout.structLayout(...)` |
| **`SymbolLookup`** | At what address is the native function/variable named X located? | `lookup.find("strlen")` |
| **`Linker`** | Under which ABI does an address + C signature description become a Java callable? | `linker.downcallHandle(address, descriptor)` |

Two important additional concepts: **`FunctionDescriptor`** describes the C signature for `Linker`; **`MethodHandle`** is the Java object used to perform the downcall. Do not put `MemoryLayout` in the wrong place for `MemorySegment`, and do not treat `SymbolLookup` as a mechanism that automatically infers signatures.

After this lesson you will be able to: allocate native memory and use the proper lifecycle; model a C array/struct with padding; look up a native symbol; link the C function `strlen` into a `MethodHandle`; run a Java 22+ program without writing a JNI adapter; and recognize ABI errors, use-after-close, wrong thread, and version differences.

### Interaction overview

~~~text
Java code
  |
  +---- Arena ----------------------> MemorySegment
  |      owner + scope               bytes, address, bounds
  |                                      ^
  +---- MemoryLayout -------------------+|
  |      type/size/alignment/offset      | Java get/set or VarHandle
  |                                      |
  +---- SymbolLookup ----> symbol address (0-byte MemorySegment)
  |                              |
  +---- FunctionDescriptor ------+----> Linker.nativeLinker()
             C signature                      |
                                              v
                                           MethodHandle
                                              |
                                              v
                                     C function (downcall)
~~~

**The lifetime of a native function** and **the lifetime of native memory** are two separate concerns. A `MethodHandle` to an already-unloaded library can be dangerous even if that Java object still exists. A `MemorySegment` from a closed arena also cannot be used just because a Java variable still holds a reference.

## 2. The two halves of FFM and the boundary with JNI

**Foreign memory access**: Java describes, allocates, and accesses memory via `MemorySegment`/`Arena`/`MemoryLayout`. For example, an array of three contiguous `int`s in native memory, written/read by Java using a layout.

**Foreign function access**: `SymbolLookup` finds the address of a C symbol; `FunctionDescriptor` defines the parameters and return according to the C ABI; `Linker` creates a `MethodHandle` for Java to call the native function.

Native C example:

~~~c
/* Native signature used to explain FFM, not a JNI method. */
size_t strlen(const char *text);
~~~

To call it correctly, Java must have a NUL-terminated C string, a pointer that remains alive during the call, the `strlen` symbol, a return layout matching `size_t`, and an argument layout matching `const char*`. The Linker knows the platform's ABI, but **cannot verify a C symbol's type from its name alone**.

Do not confuse FFM with JNI: a JNI native method typically receives `JNIEnv *` and `jobject/jclass`, has a generated C header, and must manage JNI local/global references; an FFM downcall calls a **normal C ABI symbol** without generating JNI glue code. However, FFM cannot replace all JNI APIs for manipulating JVM classes, fields, and exceptions.

## 3. MemorySegment: memory region, bounds, and lifetime

A `MemorySegment` describes a contiguous range of bytes. The view can point to native off-heap memory allocated by an `Arena` or a Java heap region permitted to be represented via `MemorySegment.ofArray(...)`. The Java view knows its size and scope; **it is not a "raw C pointer" to be used arbitrarily**.

Fragment example (needs to be placed inside a Java method):

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slot = arena.allocate(ValueLayout.JAVA_INT);
    slot.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = slot.get(ValueLayout.JAVA_INT, 0);
    System.out.println(answer); // 42
}
~~~

Each `get/set` requires the right type/layout and an offset in **bytes**, not an arbitrary field index. Three levels of safety:

1. **Spatial safety**: Java FFM checks that `offset` and the type's byte count do not exceed `segment.byteSize()`. For example, reading `JAVA_INT` at offset 4 in a 4-byte buffer is a bounds error, rather than silently reading into the adjacent address.
2. **Temporal safety**: after `arena.close()`, segments associated with the arena become invalid. Subsequent Java accesses are blocked (typically `IllegalStateException`).
3. **Thread-confinement safety**: segments of `Arena.ofConfined()` may only be used by the owner thread. Accessing/closing from another thread may throw `WrongThreadException`.

Note: these checks protect **Java FFM accesses**; once Java passes an address to native C, C can read/write out of bounds or perform a use-after-free if the library violates its contract. No Java `try/catch` guarantees saving the JVM from all native memory corruption.

### Non-copying slices

`segment.asSlice(offset, size)` creates a sub-view with the same backing memory and the same lifetime; it does not allocate a copy. Keeping a Java slice after the arena closes **does not** keep the native memory alive. `ValueLayout.ADDRESS` describes a pointer value, but a bit-valid pointer value does not necessarily point to live memory.

### Java heap and native off-heap are different

`MemorySegment.ofArray(byte[])` describes a region on the Java heap; `arena.allocate(...)` normally allocates native off-heap memory. Do not assume that every Java heap segment can be passed as a stable native pointer under every ABI. Choose the right mechanism when a native function needs to hold onto a pointer directly, especially with asynchronous calls.

## 4. Arena: owning native memory and when it is reclaimed

`Arena` is both a `SegmentAllocator` and carries a **scope** to determine lifetime. For closeable arenas, `try-with-resources` is the reliable approach:

~~~java
MemorySegment data;
try (Arena arena = Arena.ofConfined()) {
    data = arena.allocate(64, 8);
    // Use data on the owner thread; minimum alignment 8.
}
// Arena is closed; data can no longer be accessed.
~~~

| Arena | Thread access | Explicit close? | When to use |
|---|---|---|---|
| `Arena.ofConfined()` | Thread that created the arena | Yes, from the owner thread | Short-lived, synchronous buffers |
| `Arena.ofShared()` | Multiple threads | Yes, requires coordination with active users | Shared buffers with explicitly managed lifetime |
| `Arena.ofAuto()` | Multiple threads | No | Data where GC can decide cleanup timing; no exact deadline |
| `Arena.global()` | Multiple threads | No | Data that lives unboundedly for the relevant lifecycle; avoid for unbounded repeated allocations |

**Choose `ofConfined()` by default when sharing is not needed**. `ofShared()` allows cross-thread access, which **does not mean the data is automatically locked**. Two workers writing to the same field still require a synchronization/atomic protocol. Closing a shared arena while native code still holds a pointer is also an ownership problem that cannot be solved merely by switching `ofConfined` to `ofShared`.

`Arena.ofAuto()` is unsuitable if the contract requires destroying the buffer **immediately** when `closeSession()` returns: GC timing is unpredictable. `Arena.global()` does not close automatically, so repeated allocations can retain native memory for a very long time. For a stateful session API, it is better to have an explicit owner, OPEN/CLOSING/CLOSED states, and a cleanup path.

### Library arena and buffer arena

`SymbolLookup.libraryLookup(library, arena)` uses an arena for **the lifetime of the loaded library**. A buffer created in another arena only needs to live until the native function finishes using it. Therefore, there are sometimes two arenas:

~~~text
libraryArena -> load library -> SymbolLookup -> MethodHandle
     |                       do not close before the last downcall
     v
native binding lifetime

callArena -> input/output MemorySegments
     |
     +-- close after native code stops using the buffer
~~~

If a library function saves an input pointer for processing after the call returns, **do not** close `callArena` early. If the library arena closes while a `MethodHandle` is still being called, the function code may have been unloaded; the JVM may crash even though the `MethodHandle` is still a valid Java object.

## 5. MemoryLayout: from a byte region to structured data

`MemoryLayout` does not allocate memory; it describes how to interpret and access bytes.

| Layout | Conceptual equivalent | Example |
|---|---|---|
| `ValueLayout.JAVA_INT` | 32-bit primitive `int` with Java carrier `int` | Integer field |
| `ValueLayout.JAVA_LONG` | 64-bit primitive `long` with Java carrier `long` | Not automatically identical to C `long` |
| `ValueLayout.ADDRESS` | Native pointer | `char*`, `void*`, function pointer |
| `MemoryLayout.sequenceLayout(n, element)` | Native array of `n` elements | `int[3]` |
| `MemoryLayout.structLayout(...)` | C-like struct, sequential fields | `struct Point` |
| `MemoryLayout.unionLayout(...)` | C-like union, overlapping fields | Represents multiple views of the same bytes |
| `MemoryLayout.paddingLayout(n)` | Exact `n` bytes of padding | Fills alignment gaps per the C ABI |

### C struct, alignment, and padding

C source:

~~~c
/* This is an illustrative C declaration, not a complete file. */
struct Tagged {
    char kind;
    int value;
};
~~~

On an ABI with 1-byte `char`, 4-byte `int`, and 4-byte alignment requirement for `int`, the `value` field is at offset **4** and the struct's size is typically **8**. `MemoryLayout.structLayout` **does not automatically insert three padding bytes**:

~~~java
MemoryLayout tagged = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));
long offset = tagged.byteOffset(
        MemoryLayout.PathElement.groupElement("value")); // 4
~~~

Do not assume this struct layout is compatible with every compiler. Actual specifications must be verified against C `sizeof(struct Tagged)`, `_Alignof`/`alignof`, and `offsetof(struct Tagged, value)`, especially if there are packing flags, bitfields, or a different ABI.

### VarHandle and layout path

Two-`int` field struct:

~~~java
MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
VarHandle x = point.varHandle(
        MemoryLayout.PathElement.groupElement("x"));
VarHandle y = point.varHandle(
        MemoryLayout.PathElement.groupElement("y"));
~~~

If `seg` is allocated according to `point`, read/write:

~~~java
// Fragment: seg is an appropriate and live MemorySegment.
x.set(seg, 0L, 7);
y.set(seg, 0L, 35);
int sum = (int) x.get(seg, 0L) + (int) y.get(seg, 0L);
~~~

`0L` is the **base offset** coordinate of a layout-derived `VarHandle`. For a layout path containing an open-path `PathElement.sequenceElement()`, the var handle has an **additional** `long` coordinate for the element index; the API does not guess the index.

### Native arrays

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemoryLayout triple = MemoryLayout.sequenceLayout(
            3, ValueLayout.JAVA_INT);
    MemorySegment numbers = arena.allocate(triple);
    for (int i = 0; i < 3; i++) {
        numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
    }
    int sum = 0;
    for (int i = 0; i < 3; i++) {
        sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
    }
    System.out.println(sum); // 6
}
~~~

`setAtIndex`/`getAtIndex` compute the index based on the `ValueLayout` size and perform bounds checks. Do not treat a native array as a Java `int[]` or assume `JAVA_INT` size always matches C `long`.

## 6. SymbolLookup: finding symbol addresses, not types

`SymbolLookup` looks up a symbol name in one or more native libraries. `lookup.find("name")` returns `Optional<MemorySegment>`; the memory segment of a **symbol address** typically has a size of 0 bytes. It means "address of a function/variable", **not** a data buffer on which you can read `get(JAVA_INT,0)`.

Three options to know:

- `Linker.nativeLinker().defaultLookup()`: finds a set of native symbols that the platform linker chooses to expose (for example `strlen` on many Linux/macOS/Windows runtimes). The symbol list **is not guaranteed to be identical across all OSes/JVMs**.
- `SymbolLookup.libraryLookup(Path, Arena)` or `libraryLookup(String, Arena)`: loads/looks up a specific application-owned library. The lookup and unloading capability are tied to the arena; the arena must be kept alive during native calls.
- `SymbolLookup.loaderLookup()`: finds symbols from native libraries loaded via `System.load` or `System.loadLibrary` in the appropriate class loader; **does not automatically cover libraries loaded via `libraryLookup`**.

How to look up a symbol:

~~~java
Linker linker = Linker.nativeLinker();
SymbolLookup lookup = linker.defaultLookup();
MemorySegment strlenAddress = lookup.find("strlen")
        .orElseThrow(() -> new IllegalStateException(
                "strlen unavailable in default lookup"));
~~~

If `find` fails → report an error or choose an explicit library; do not call a null address. **Finding a symbol also does not verify its C signature**. If a library exports `sum` taking three parameters, `SymbolLookup` does not automatically tell the linker that; you must read the C header and provide the exact `FunctionDescriptor`.

### Scope of a native library

~~~java
// Fragment illustrating libraryLookup for Linux.
try (Arena libraryArena = Arena.ofConfined()) {
    SymbolLookup ownLib = SymbolLookup.libraryLookup(
            Path.of("libffm_math.so").toAbsolutePath(), libraryArena);
    MemorySegment address = ownLib.find("ffi_add").orElseThrow();
    // Only call native within the valid lifetime of libraryArena.
}
~~~

Do not cache a primitive `long` address and reuse it after `libraryArena.close`: the native machine code may have been unloaded. `SymbolLookup.loaderLookup` differs from `libraryLookup` in class loader and loading mechanism; do not use them interchangeably without checking.

## 7. Linker: bridging Java MethodHandle ↔ C ABI

`Linker.nativeLinker()` selects a linker matching the current JVM's ABI: OS, CPU, calling convention, and corresponding native types. It does not compile C source; it turns **a function address + `FunctionDescriptor`** into a callable `MethodHandle`.

Example C `size_t strlen(const char*)`:

~~~text
Return C size_t  -> canonical layout "size_t"
Argument char*   -> ValueLayout.ADDRESS

SymbolLookup      -> strlenAddress
FunctionDescriptor-> (ADDRESS) -> size_t
Linker             -> MethodHandle
MethodHandle       -> calls C function per native ABI
~~~

To avoid assuming `size_t` is always Java `long`:

~~~java
Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
if (sizeT == null) throw new IllegalStateException("size_t unavailable");

FunctionDescriptor signature = FunctionDescriptor.of(
        sizeT, ValueLayout.ADDRESS);
MethodHandle strlen = linker.downcallHandle(
        strlenAddress, signature);
~~~

`canonicalLayouts()` publishes native type mappings per ABI; C `long` on 64-bit Windows is typically 32 bits, whereas on Linux x64 it is typically 64 bits. `size_t` is typically 64 bits wide on 64-bit platforms, but must not be equated with `JAVA_LONG` on every machine.

When invoking, `MethodHandle.invokeExact` requires the Java types at the call-site to match **exactly** the handle's carrier/arity. If the descriptor has a Java `long` return and `MemorySegment` parameter, a matching call on that platform is `long n = (long) strlen.invokeExact(cString)`. Using `invokeWithArguments` is simpler when demonstrating a carrier that varies by ABI, but has overhead and **cannot** fix a wrong C descriptor.

### A wrong native signature can crash the JVM

~~~java
// WRONG fragment, never run:
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
// Wrong: strlen(const char*) is described as int strlen(int).
~~~

Symbol names usually do not contain return/argument types. The Linker cannot check `wrong` against the real C header; if Java passes a garbage pointer, native code may dereference an invalid address. You must verify **count, order, width, alignment, pointers, struct-by-value, and varargs** against the exact ABI.

`Linker.upcallStub(target, descriptor, arena)` is the reverse direction: turning a Java method handle into a native function pointer for C to call back into Java. The stub's lifetime is tied to the arena, and Java callbacks need to handle exceptions in Java before exiting to C. This lesson focuses on **downcalls** to clarify the five core building blocks.

## 8. Complete JDK 22+ Java example: struct, array, lookup, and strlen

The following program needs no JNI `.h` header or C adapter. It accesses native memory, calls the C standard-library `strlen` via the default lookup, and demonstrates that Java FFM access after `Arena.close` is rejected.

**Environment limitation:** `strlen` must be exposed by the linker's default lookup. Actually run on **Windows x64 with JDK 24**, compiled with `--release 22`. On a runtime where the default lookup does not have that symbol, the program reports a clear error and the learner can switch to `libraryLookup` pointing to a specific C library.

### 8.1. File `FfmModelDemo.java` (full source)

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public final class FfmModelDemo {
    public static void main(String[] args) throws Throwable {
        MemoryLayout pointLayout = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("x"),
                ValueLayout.JAVA_INT.withName("y"));

        VarHandle xHandle = pointLayout.varHandle(groupElement("x"));
        VarHandle yHandle = pointLayout.varHandle(groupElement("y"));
        MemorySegment retired;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment point = arena.allocate(pointLayout);
            xHandle.set(point, 0L, 7);
            yHandle.set(point, 0L, 35);

            int x = (int) xHandle.get(point, 0L);
            int y = (int) yHandle.get(point, 0L);
            System.out.println("point=(" + x + "," + y + ")");

            MemoryLayout triple = MemoryLayout.sequenceLayout(
                    3, ValueLayout.JAVA_INT);
            MemorySegment numbers = arena.allocate(triple);
            for (int i = 0; i < 3; ++i) {
                numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
            }

            int sum = 0;
            for (int i = 0; i < 3; ++i) {
                sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
            }
            System.out.println("arraySum=" + sum);

            Linker linker = Linker.nativeLinker();
            MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
            if (sizeT == null) {
                throw new IllegalStateException("size_t unavailable");
            }

            SymbolLookup symbols = linker.defaultLookup();
            MemorySegment strlenAddress = symbols.find("strlen")
                    .orElseThrow(() -> new IllegalStateException(
                            "strlen unavailable in default lookup"));

            FunctionDescriptor signature = FunctionDescriptor.of(
                    sizeT, ValueLayout.ADDRESS);
            MethodHandle strlen = linker.downcallHandle(
                    strlenAddress, signature);

            MemorySegment cString = arena.allocateFrom("hello FFM");
            long length = ((Number) strlen.invokeWithArguments(cString))
                    .longValue();
            System.out.println("strlen=" + length);

            if (x + y != 42 || sum != 6 || length != 9) {
                throw new AssertionError("Unexpected result");
            }

            retired = point;
        }

        try {
            retired.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("Use-after-close accepted");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

Complete file, no package. `VarHandle.set/get(point,0L,...)` uses the base offset coordinate; `Arena.allocateFrom("hello FFM")` creates a UTF-8 C string with a terminating NUL byte. `strlen` returns 9 because the ASCII string has 9 bytes before the terminator, excluding the NUL byte.

### 8.2. Build and run commands

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out FfmModelDemo.java
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

**Windows CMD/PowerShell:** create the `out` directory if it does not exist yet, then:

~~~bat
mkdir out
javac --release 22 -d out FfmModelDemo.java
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

Ignore the "directory already exists" error if `out` remains from a previous run. **No `javac -h`, `jni.h`, C compiler, or `-Djava.library.path` is needed** for this default example. `--enable-native-access=ALL-UNNAMED` grants permission to perform restricted native operations for code on the classpath; see the versioning and security sections below.

### 8.3. Exact stdout when the symbol is present

~~~text
point=(7,35)
arraySum=6
strlen=9
afterClose=IllegalStateException
RESULT: PASS
~~~

Confirmed on JDK 24 Windows x64, compiled with `javac --release 22` and run with `--enable-native-access=ALL-UNNAMED`. If `strlen` is not in the platform's default lookup, you will see `IllegalStateException("strlen unavailable in default lookup")` instead of the PASS output. This is a difference in **symbol exposure**, not evidence that FFM does not work.

### 8.4. Data flow and ownership breakdown

1. `pointLayout` describes two Java `int` fields; `xHandle`/`yHandle` provide access by name. No Java `Point` class is allocated in native memory; only bytes.
2. `Arena.ofConfined` is the owner of `point`, `numbers`, and `cString`. All are used synchronously on the thread that created the arena.
3. `numbers.setAtIndex` writes 1,2,3; `getAtIndex` reads them back as 6, with bounds checking.
4. `Linker.nativeLinker` obtains the running ABI; `size_t` is selected via canonical layouts, avoiding forcing a C type into Java `long` across all ABIs.
5. `SymbolLookup.defaultLookup` finds `strlen`, returning a segment representing the function address. Do not read fields of that zero-length segment.
6. `FunctionDescriptor.of(sizeT, ADDRESS)` declares one pointer parameter and a `size_t` return. `downcallHandle` creates a callable method handle.
7. `Arena.allocateFrom` places the C string in native memory; `strlen.invokeWithArguments` runs **while the arena is alive**. C receives a pointer to terminated UTF-8 data.
8. After leaving `try`, the arena closes; `retired` is a Java object/view that still exists, but its backing memory is invalid. `retired.get(...)` is blocked and the test catches the expected exception.

PASS confirms this scenario; **it does not prove every native function is safe**; C can do dangerous things outside Java's checks.

## 9. Another standalone example: using SymbolLookup.libraryLookup with your own C library

`defaultLookup` is the "platform-provided symbols" model. To understand the "application-owned library" model, you can write your own C function exporting a normal symbol, without JNI glue.

### 9.1. File `native/ffm_math.c`

~~~c
#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

API int ffi_add(int a, int b) {
    return a + b;
}
~~~

On common target platforms, C `int` is 32 bits. When supporting another compiler/ABI, verify this before mapping to `ValueLayout.JAVA_INT`.

Build the native library:

**Linux:**

~~~sh
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libffm_math.so native/ffm_math.c
~~~

**macOS:**

~~~sh
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libffm_math.dylib native/ffm_math.c
~~~

**Windows MSVC Developer Command Prompt:**

~~~bat
cl /nologo /W4 /LD native\ffm_math.c /Fe:ffm_math.dll
~~~

Use a compiler targeting the same architecture as the JVM. Symbol names may be decorated on some ABIs, especially 32-bit Windows; check with `nm` or `dumpbin /EXPORTS` if the lookup does not find it.

### 9.2. File `FfmAddDemo.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmAddDemo {
    public static void main(String[] args) throws Throwable {
        String file = System.mapLibraryName("ffm_math");
        Path library = Path.of(file).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                    SymbolLookup.libraryLookup(library, arena);
            MemorySegment address = lookup.find("ffi_add")
                    .orElseThrow(() -> new IllegalStateException(
                            "ffi_add export not found"));

            Linker linker = Linker.nativeLinker();
            FunctionDescriptor signature = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);
            MethodHandle add =
                    linker.downcallHandle(address, signature);

            int result = (int) add.invokeExact(20, 22);
            System.out.println("ffi_add(20,22)=" + result);
            if (result != 42) {
                throw new AssertionError("Bad native result");
            }
        }
        System.out.println("RESULT: PASS");
    }
}
~~~

Run in the directory containing the built native binary:

~~~sh
javac --release 22 FfmAddDemo.java
java --enable-native-access=ALL-UNNAMED FfmAddDemo
~~~

Expected stdout **if the native library/export/ABI is correct**:

~~~text
ffi_add(20,22)=42
RESULT: PASS
~~~

This is an additional exercise with a C compiler; **this C library has not been run in the current session**, but the Java/C signatures are designed consistently. `System.mapLibraryName` selects the OS-appropriate filename; `Path.of(file).toAbsolutePath()` must actually point to the right file. `SymbolLookup.libraryLookup` can load a library by path without `System.loadLibrary` or `javac -h`.

When `try` ends, the arena owning the library lookup is closed. Do not cache the `MethodHandle` or the `ffi_add` address and call it afterward: the function code may have been unloaded. If multiple Java threads call the library concurrently, use an **owner that keeps the arena alive for the entire binding**, rejects new calls, and waits for in-flight calls to finish before closing.

## 10. C ABI: a wrong descriptor is more dangerous than a Java type error

| C concept | Suggested FFM layout | Notes |
|---|---|---|
| 32-bit `int` | `ValueLayout.JAVA_INT` | Verify ABI, do not guess |
| 64-bit `long long` | Usually `ValueLayout.JAVA_LONG` | Check width in C |
| `long` | Canonical layout per ABI | 64-bit Windows is usually 32-bit; Linux x64 is usually 64-bit |
| `size_t` | `linker.canonicalLayouts().get("size_t")` | Not necessarily always Java `long` |
| `void*`/`char*` | `ValueLayout.ADDRESS` | Size, lifetime, and nullability must have a contract |
| `struct` | `structLayout` + `paddingLayout` | Verify `sizeof`, alignment, `offsetof` |
| `T[n]` | `sequenceLayout(n, typeLayout)` | Stride per element layout |
| C callback pointer | `Linker.upcallStub` | Arena lifetime and exception/thread rules |

A `MemorySegment` pointer may be valid at creation time, yet native code can still write past bounds, or return a pointer to `malloc` and expect the caller to call `free` via the right API. Java FFM does not automatically understand ownership defined by a C library. If C returns a raw pointer without a size, do not blindly `reinterpret`: that operation is restricted and declaring the wrong size can cause a crash or silent corruption.

Native C `char*` and Java `String` also differ: `Arena.allocateFrom(String)` creates a NUL-terminated UTF-8 C string; C `strlen` returns **the number of bytes**, not the number of Java UTF-16 code units or code points. With Vietnamese Unicode, the result usually differs from `String.length()`.

For C variadic functions (such as `printf`), the descriptor must describe the specialized argument list and include `Linker.Option.firstVariadicArg(...)` when needed; do not copy the `FunctionDescriptor.of(return,args...)` recipe from a non-variadic call and guess promotions. Endianness, packed structs, unions, and C calling conventions are also part of the ABI contract.

### Function pointers and data pointers differ in purpose

`SymbolLookup.find("ffi_add")` returns a segment representing **the symbol address**. It does not allocate a data buffer for writing `set(JAVA_INT,0,...)`. For a global native variable, the looked-up address may need to be described/sized with justification; for a native function, pass the address to `Linker.downcallHandle`.

A `MethodHandle` has a `type()` on the Java side, but that is **the Java calling signature generated from the FunctionDescriptor**; it does not prove the native symbol actually has the same C signature. To be safe, you must check the C header/ABI and test on the deployment platform.

## 11. Lifetime and concurrency: Arena.ofShared does not automatically lock data

Many production bugs come not from how the API is called, but from shutdown:

~~~text
Thread A                         Thread B
------------------------------   -----------------------------
Arena.ofShared() allocates buffer
                                 C downcall receives buffer pointer
close arena
                                 C keeps reading old pointer -> dangerous
~~~

Java scope safety cannot force C to stop immediately when Java calls `close`. If a native call/callback is still using a buffer, there must be a **protocol to wait** for completion before freeing. State can be managed as:

~~~text
OPEN
  allow new downcalls; in-flight count++
CLOSING
  reject new calls; wait for count to reach 0
CLOSED
  release native callbacks/buffers; close arena and library scope
~~~

For synchronous `strlen` in this lesson, C does not retain the pointer and the function returns before `arena.close()`, so it is lifetime-safe. For an asynchronous C API, an arena with the **session** lifetime is more appropriate than a call-local arena. Do not pass a pointer from a confined arena to another thread and expect that thread to access it validly just because the address is an integer.

### The library arena must also live long enough

If you used `SymbolLookup.libraryLookup(..., arena)`, the library may unload when the arena closes. Not only must buffers live until the native call finishes, but **the function code** must also remain loaded when the `MethodHandle` is called. The same applies to upcall stubs: the Java stub from `Linker.upcallStub` has the arena's lifetime; C must unregister the callback and must not call the function pointer after the scope closes.

### Arena.ofAuto() and global() are not escapes from design

`ofAuto()` has no specific cleanup deadline; `global()` has an unbounded lifetime. They have valid use cases, but cannot be used as a way to ignore owner design. If a native library requires an explicit `destroy(handle)`, maintain a clear closing contract rather than relying solely on GC.

## 12. Native access, restricted methods, and flags

FFM is finalized as of JDK 22, but has **restricted operations** such as creating a downcall handle, upcall stub, library lookup, or changing the bounds of a raw pointer via `reinterpret`. These operations can crash the JVM if the developer provides the wrong ABI/address.

When running code in an **unnamed module/classpath**:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out FfmModelDemo
~~~

When deploying in a named module, grant native access to **the module that actually contains the FFM code**, for example `--enable-native-access=com.example.binding`. Some JDK releases warn about restricted native access when permission is not granted; policies in newer JDKs may be stricter. Do not guess the behavior when the flag is missing — check the exact JDK docs and runtime logs.

**Distinguishing the flags:**

- `--enable-native-access`: allows code in a module to perform restricted native operations.
- `--enable-preview`: used for Java releases with preview features; **not needed to run finalized FFM on JDK 22+**.
- `--add-modules jdk.incubator.foreign`: belongs to the historical incubator API in JDK 17, does not apply to finalized `java.lang.foreign`.
- `-cp`/`--class-path`: locates Java classes, not native libraries.
- `-Djava.library.path`: relates to certain native library search mechanisms, does not automatically make `Linker.defaultLookup` find arbitrary files on disk.

Native access permission **does not turn unsafe C code into safe code**. Production still needs control over binary sources, signatures, error handling, and lifecycle.

## 13. Java FFM generations: avoid mixing examples from different versions

| JDK | Status | How to read documentation |
|---|---|---|
| 17–18 | Incubator FFM API, historical `jdk.incubator.foreign` package | Do not take this lesson's source verbatim to run on 17; API and flags differ |
| 19–21 | FFM went through preview releases with API adjustments | Need the exact API/Javadoc per release and preview flags where applicable |
| **22** | **Finalized**, JEP 454, `java.lang.foreign` | This lesson's source chooses JDK 22 as the baseline |
| 23+ | Stable API maintained, details and native-access policy may change by release | Cross-check Javadoc/notes of the deployed version |

The `FfmModelDemo` program was **compiled with `--release 22` and run on JDK 24**, without needing preview. Do not simply rename packages in a JDK 17 FFM tutorial and expect compatibility: the design surface of `MemorySession`/`ResourceScope` in older versions differs from the finalized `Arena`.

For projects supporting multiple JDKs, separate source sets or setting a JDK 22+ baseline may be needed. If forced to support Java 17, some integrations make more sense using stable JNI or appropriate separate bindings rather than the inconsistent incubator FFM API.

## 14. FFM and JNI: each mechanism has its own strengths

| Goal | FFM JDK 22+ | JNI |
|---|---|---|
| Calling a C function with a clear ABI | `SymbolLookup` + `Linker` + `MethodHandle`, no JNI adapter needed | `native` method + C/JNI bridge |
| Reading/writing native buffers | `MemorySegment`, `Arena`, `MemoryLayout` | JNI arrays, direct buffers, or C malloc |
| Calling Java from native | FFM `upcallStub` with a function pointer contract | `JNIEnv *`, `Call*Method` |
| Managing Java references/classes | Not a central goal of FFM | JNI has dedicated APIs for local/global refs and Java object operations |
| Running sample source verbatim on Java 17 | No | JNI has long-standing support |
| Risks | ABI descriptor, native pointers, arena/library lifetime | JNI refs, thread attach, C memory misuse |

FFM fits when you need bindings for a specific C ABI, native memory with a clear lifetime, and a JDK 22+ baseline. JNI makes sense when deep interaction with the JVM object model is needed or older JDKs must be supported. **Neither replaces the requirement to test native code**. The `jextract` tool can help generate bindings from C headers, but does not replace the developer checking ownership/ABI.

## 15. Layered troubleshooting

| Observed error | Possible cause | How to check/fix |
|---|---|---|
| `package java.lang.foreign does not exist` | JDK build/target earlier than 22 | Use JDK 22+, set `--release 22` |
| `cannot find symbol allocateFrom` | API from an older/preview JDK | Read Javadoc for the exact release, avoid mixing versions |
| Restricted native API warning | Native access not granted per JDK policy | `--enable-native-access=ALL-UNNAMED` or module name |
| `IllegalCallerException` | Caller module not permitted to call restricted API | Fix launcher/module configuration |
| `strlen unavailable in default lookup` | Runtime does not expose the symbol | Check `find`, choose a custom `libraryLookup` |
| `ffi_add export not found` | Native symbol name/visibility/ABI decoration | `nm`/`dumpbin` and confirm the right library file |
| Library load failure | Wrong path, architecture, dependent libraries | Check absolute `Path`, binary format, dependencies |
| `WrongMethodTypeException` | Java `invokeExact` does not match carrier | Inspect `MethodHandle.type()`, fix call-site signature |
| JVM crash during downcall | Wrong C ABI signature, C writes out of bounds | Read C header, check descriptor, use ASan/native debugger |
| `IndexOutOfBoundsException` | Offset or layout exceeds segment | `byteSize()` and index/field offsets |
| `IllegalStateException` after close | Segment no longer has a valid scope | Move use before `arena.close` or extend lifetime appropriately |
| `WrongThreadException` | Confined segment accessed from another thread | Keep a single owner thread or use shared + synchronization |
| C struct returns wrong values | Wrong padding/alignment/endianness | `sizeof`/`offsetof` and layout tests |
| C `strlen` counts differently from Java length | C counts UTF-8 bytes up to NUL | Confirm encoding and terminator |
| Native memory keeps growing | Global/auto arena mismatching contract, unfreed native malloc | Track allocation/close; profile native heap |
| Cached `MethodHandle` crashes after shutdown | Library already unloaded | Block new downcalls, wait for in-flight, then close library arena |

**Note:** Java-side access exceptions are diagnosable failures, but when a C ABI/implementation writes garbage into native memory, the JVM can die before Java can throw an exception. Do not replace C testing with a `try/catch(Throwable)` wrapping the downcall.

## 16. Self-check questions and answers

**1. Are `Arena` and `MemorySegment` the same?**  
No. `Arena` allocates/holds the scope to manage lifetime; `MemorySegment` is a view of a byte region within that scope. One arena can allocate many segments.

**2. Once you have a `MemoryLayout`, do you still need to allocate?**  
Yes. `MemoryLayout` only describes size/type/offset. `arena.allocate(layout)` actually allocates native memory. A `VarHandle` on a layout is used with a segment allocated with the proper bounds.

**3. Why isn't the `value` field in C struct `{ char kind; int value; }` always at offset 1?**  
Due to ABI alignment/padding. If C places `value` at offset 4, then the Java `structLayout` needs three padding bytes. You must verify C `offsetof` instead of guessing.

**4. Does `SymbolLookup` return the full native function signature?**  
No. It primarily gives the symbol address. `FunctionDescriptor` and the C header/ABI define the return/parameter layouts. A wrong descriptor can crash the JVM.

**5. Why not hardcode Java `long` for C `size_t`?**  
Because C `size_t` is a platform-dependent type; retrieve the canonical layout from the linker for the running ABI. `invokeExact` also requires the exact Java carrier matching that layout.

**6. Does `Arena.ofShared` make segment writes automatically thread-safe?**  
No. A shared arena allows multiple threads to access it, but does not automatically place locks on fields. A synchronization protocol is needed, along with preventing `close` while workers/native functions still use the pointer.

**7. After closing the `libraryLookup` arena, the Java `MethodHandle` is still a Java object. Can it still be called?**  
Do not assume so. The library may have been unloaded; calling through a stale function pointer is dangerous. The binding owner must keep the library arena alive until after the last downcall.

**8. Does `FfmModelDemo` need `--enable-preview`?**  
No. It uses finalized JDK 22+ FFM. Use `--enable-native-access=ALL-UNNAMED` to grant permission for restricted native operations to the classpath.

**9. Does C `strlen("á")` return the same value as Java `"á".length()`?**  
Not necessarily. C counts UTF-8 bytes up to NUL, whereas Java `String.length()` counts UTF-16 code units. The two numbers can differ.

**10. Can FFM completely protect the JVM against buggy C code?**  
No. Java FFM bounds/scope/thread checks protect accesses from Java, but native C given a pointer can violate bounds/lifetime/ABI and corrupt memory.

## 17. Checklist when introducing FFM bindings into a project

- [ ] Clearly choose a JDK 22+ baseline and native-access flags; do not mix incubator/preview sources.
- [ ] Every native buffer has a clear owner arena, close time, and borrowers; never use after close.
- [ ] Thread access of confined/shared arenas is properly understood; synchronization is in place if multiple threads write/read mutable state.
- [ ] Every `MemoryLayout` matches the real C ABI: size, alignment, padding, field offsets, arrays, pointer width, endianness.
- [ ] `SymbolLookup` chooses the right source: default, library, loader; symbol names are verified on the native binary.
- [ ] `FunctionDescriptor` is cross-checked against the real signature in the C header: return, order, carrier, varargs, structs, calling convention.
- [ ] `MethodHandle` Java type and invocation style are tested; do not confuse `WrongMethodTypeException` with an ABI mismatch.
- [ ] Input C strings have proper terminator/encoding; output buffers are large enough so C does not overflow.
- [ ] Upcall stubs, library arenas, and buffers live until all native users have stopped.
- [ ] Shutdown blocks new callers, waits for in-flight work, unregisters callbacks, and only then closes arenas.
- [ ] Native library/version/architecture are managed as dependencies; do not look up raw addresses and cache them indefinitely.
- [ ] Unit tests check struct/array/downcall/after-close; CI tests on the real OS/ABI and uses native tools when errors occur.
- [ ] Do not treat a single PASS run as proof that every native function is safe.

## 18. Summary and official documentation

Remember the short model:

~~~text
Arena              = owner and lifetime
MemorySegment      = memory region and bounds/scope
MemoryLayout       = data types in bytes, alignment/offset
SymbolLookup       = native symbol address
FunctionDescriptor = C ABI signature
Linker             = ABI bridge
MethodHandle       = native call from Java
~~~

A correct FFM program must simultaneously answer: **is the memory still alive, who may access it, does the layout match C, is the symbol from the right library, does the function descriptor match the C ABI, and is the library code still loaded when called?** The five components complement each other; none of them automatically fixes invalid conditions in another.

Official documentation to check versions and semantics:

- [JEP 454 – Foreign Function & Memory API, finalized JDK 22](https://openjdk.org/jeps/454)
- [Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)

For newer JDKs, check the exact Javadoc/release notes of the runtime in use, especially for restricted native access and policy changes; do not infer from an old preview tutorial to the finalized release.