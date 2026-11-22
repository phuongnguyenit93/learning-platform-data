# Limitations of JNI or FFM When a Library Only Exports a Complex C++ API

## 1. The Problem: Java Does Not Automatically Understand the C++ Object Model

Suppose an SDK only exposes:

~~~cpp
// Illustrative C++ API, NOT a C interface.
namespace vision {
    template<class Pixel> class Image;

    class Analyzer {
    public:
        explicit Analyzer(std::string modelPath);
        virtual ~Analyzer();
        std::vector<float> infer(const Image<float>& input);
        std::vector<float> infer(const Image<unsigned char>& input);
        void setOptions(const std::map<std::string, std::string>& options);
    };
}
~~~

Having a `.so`/`.dll` and C++ headers is not enough for Java to call these methods. Class layout, constructors, destructors, overloaded function names, template instantiations, virtual dispatch, C++ exceptions, and STL containers have ABI contracts that Java JNI or FFM do not automatically reconstruct.

Two conclusions need to be distinguished:

- **JNI can call C++**: a JNI native method **written in C++**, compiled with an SDK-compatible compiler/linker, can call class methods, instantiate templates, and manipulate `std::string`/`std::vector`. However, native code is required to convert data, manage objects, and handle exceptions. JNI is not a C++ compiler or reflection engine.
- **FFM calls native functions according to the ABI that `Linker` supports**, typically the C ABI on the platform. FFM does not automatically perform C++ overload resolution, constructor invocation, vtable dispatch, or map STL object layouts. To connect a complex C++ library, the common approach is to create a **C-compatible wrapper** written in C++ and have FFM call the `extern "C"` functions.

A valid **function descriptor** in Java does not prove that the actual C++ function has a compatible signature/ABI. Using the wrong layout, function pointer, or object lifetime can crash the JVM rather than merely throwing an exception.

**Lesson objectives:** identify the boundaries of JNI/FFM, understand what `extern "C"` can and cannot do, design an opaque-handle C wrapper, practice C++17 → C ABI → Java 22+ FFM, examine a Java 17+ JNI example, and understand the limitations when only a C++ binary is available without a supported SDK.

## 2. How Does the C ABI Differ from the C++ ABI?

The **ABI (Application Binary Interface)** specifies how symbols are exported, how arguments pass through registers/stack, data sizes and alignment, calling conventions, exceptions/unwinding, and many other platform/compiler details.

| Issue | C-style API | Complex C++ API |
| --- | --- | --- |
| Function name | A single export such as `engine_add` | Namespaces, overloads, **name mangling** |
| Function call | Function pointer per C ABI | Member receiver `this`, virtual calls, constructors |
| Data types | Fixed-width integers, C pointers, C structs | `std::string`, `std::vector<T>`, inheritance, references |
| Object lifetime | Explicit `create/destroy` | RAII, constructors/destructors, copy/move |
| Exceptions | Status/error code | C++ `throw`, exception types, unwinding |
| Templates | None in C API | May be compile-time only/inline, missing exported symbols |
| Binary portability | Clearer if the contract is measured | Requires the same C++ ABI/stdlib/toolchain and flags |

C++:

~~~cpp
// Overload illustration, not a standalone program.
namespace calc {
    int blend(int a, int b);
    double blend(double a, double b);
}
~~~

The compiler needs to distinguish the two overloads at the symbol level. On GCC/Clang Linux, exported names are typically **mangled**; other compilers/ABIs have different rules. `nm -C` displays names **demangled for human readability**, not raw strings that can reliably be passed to FFM `SymbolLookup.find`.

**Do not solve the problem by copying raw mangled symbols.** You might be able to look up a symbol for one specific binary/version, but you still have the issues of member calling convention, type layout, C++ exception ABI, and lifetime. That is not a guaranteed stable interface.

## 3. The True Meaning of `extern "C"`

~~~cpp
extern "C" int32_t engine_add(void *handle, int32_t value);
~~~

`extern "C"` requests C language linkage for the function declared in C++: as a result, the function name and linkage type are described according to the platform's C conventions. It is an essential tool for **exporting a C interface from C++ code**.

However, it **does not turn** every C++ type into a C-compatible type:

~~~cpp
// Should NOT be treated as a portable interface for FFM.
extern "C" std::vector<float> infer(std::string model);
~~~

Such a function still passes/returns `std::vector` and `std::string` according to the C++ object ABI. FFM has no `ValueLayout.STD_VECTOR`. Similarly, `extern "C"` does not automatically catch C++ exceptions, does not call destructors on Java's behalf, and does not make class layouts portable.

A better interface:

~~~c
/* Illustrative C API:
   the C++ implementation handles vector/string internally. */
typedef struct engine_handle engine_handle;

int engine_create(const char *utf8_name,
                  engine_handle **out_handle);
int engine_add(engine_handle *handle, int32_t value);
int engine_sum(const engine_handle *handle,
               int64_t *out_total);
void engine_destroy(engine_handle *handle);
~~~

In the C++ implementation, `engine_handle` can contain `std::vector` and `std::string`. Java only receives an **opaque pointer**: it knows how to hold, pass, and release it through the wrapper, but **does not dereference** the C++ class inside.

## 4. Why Not Describe a C++ Class with `MemoryLayout.structLayout`?

FFM supports `MemoryLayout.structLayout` for C-compatible structs and `unionLayout` for unions, but describing them accurately requires knowing `sizeof`, `alignof`, `offsetof`, padding, and the actual ABI.

A C++ class with virtual methods/inheritance/STL can have:

- Vtable/vptr and dynamic dispatch according to the compiler ABI.
- Multiple/virtual inheritance, base-class subobject offsets, thunks.
- `std::string` containing an internal buffer, capacity, or small-string optimization.
- `std::vector` having an allocator-dependent representation and capacity/size metadata.
- Non-trivial constructors, destructors, copy/move semantics.

~~~cpp
class Base {
public:
    virtual int kind() const = 0;
    virtual ~Base() = default;
};

class Derived : public Base {
public:
    explicit Derived(std::string name);
    int kind() const override;
private:
    std::string name_;
    std::vector<int> values_;
};
~~~

Even if the C++ compiler reports `sizeof(Derived)=N`, calling `arena.allocate(N)` in Java **does not create a Derived object**: the C++ constructor has not run, the vtable/STL internals have not been constructed, and no one will call the destructor.

FFM `MemorySegment.ofAddress(addr)` represents a native address; it **does not** automatically create a C++ dynamic type or perform `dynamic_cast`/RTTI/virtual dispatch. Trying to read a vtable from guessed offsets is compiler-dependent and risks memory corruption.

**Alternative:** only let the C++ adapter create objects via constructor/`new`, destroy them via `delete`/destructor, call member functions, and return results through verifiable C types.

## 5. JNI: C++ Can Be Used on the Native Side, but Glue Is Needed

A JNI entrypoint has a signature dictated by the JVM/JNI, but its body can be written in C++ and linked against a vendor C++ SDK:

~~~cpp
// Pseudocode: not a standalone program.
JNIEXPORT jint JNICALL
Java_App_doWork(JNIEnv *env, jobject self, jlong nativeHandle) {
    // Verify handle and call C++ SDK using the C++ compiler.
    // Convert Java arrays -> std::vector<T> when needed.
    // Catch C++ exceptions before returning to the JVM.
}
~~~

Things JNI **does not automatically** do for you:

1. Resolve and select overloaded C++ methods from Java reflection.
2. Convert Java `String`/`List`/`Map` into `std::string`/`vector`/`map`.
3. Create a valid C++ object from Java `new` or reclaim it via Java GC.
4. Guarantee that a `jlong` holds a live native pointer of the right type.
5. Guarantee that the C++ compiler/plugin ABI matches the vendor library.
6. Automatically map C++ exceptions to Java exceptions.
7. Manage JNI local/global references, worker thread attachment, and pending exceptions.

JNI is useful when you need to manipulate many Java objects and want a C++ native translation unit to call class methods directly. However, **JNI is not a general-purpose C++ ABI translator**. A JNI plugin still must be built, distributed, and tested for each target OS/CPU/toolchain.

### 5.1. JNI References and Thread Ownership

If a native C++ SDK invokes a Java callback from a C++-created thread, it must use the JVM attach/detach APIs per the JNI specification before calling JNI via `JNIEnv*`. `JNIEnv*` is not a pointer that can be used freely across all threads. Java objects retained across calls require a JNI `GlobalRef`, and `DeleteGlobalRef` must be called when registration ends; local references must not be used as long-lived global handles.

When JNI calls Java methods, you must check `ExceptionCheck` or handle pending Java exceptions. Conversely, when C++ code throws an exception, the JNI method must **catch it on the C++ side**, then convert it to a status or call `ThrowNew` per the JNI contract.

## 6. FFM: A C Header Is a Describable Boundary

FFM, finalized in **JDK 22** (JEP 454), provides:

- `Linker.nativeLinker()`: supported native calling conventions.
- `SymbolLookup.libraryLookup(...)` and `find("engine_add")`: looks up symbols by their **actual exported name**.
- `FunctionDescriptor.of(...)` / `ofVoid(...)`: describes the return type and C parameters using `MemoryLayout`.
- `MemorySegment` and `Arena`: buffers/pointers/lifetime in Java.
- `MethodHandle.invokeExact`: calls native functions with matching carrier types.
- `Linker.upcallStub`: creates a callback function pointer when a C API accepts a callback.

For the C signature:

~~~c
int engine_add(engine_handle *handle, int32_t value);
~~~

the descriptor on Linux/x64 is:

~~~java
// Java 22+, excerpt, not standalone.
FunctionDescriptor addSignature = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,   // C return int status
        ValueLayout.ADDRESS,    // engine_handle*
        ValueLayout.JAVA_INT);  // int32_t value
~~~

FFM can perform that call through the exact ABI **without needing to know the C++ class** behind `engine_handle`. The `MemorySegment` received from a pointer is an address value; it does not turn into a Java object containing the class's member methods.

### 6.1. How Far Does `jextract` Help?

According to the OpenJDK guide, `jextract` parses **C headers** and generates Java FFM bindings. It is **not a tool that translates all C++ templates/classes/overloads** into Java classes. For a C++ library with a C wrapper, `jextract` can read the **wrapper header** and generate bindings; you still need to design the ownership and exception protocol yourself.

Diagram:

~~~text
C++ SDK (classes, templates, stdlib)
          |
       .cpp adapter -- SDK-compatible C++ compiler
          |
       C header + C exports
          |
      +---+------------------------+
      |                            |
Java FFM + jextract             JNI glue (if choosing JNI)
      |                            |
      +---------- Java ------------+
~~~

`jextract` does not write `engine_destroy` for you, does not guarantee the C++ object is still alive, does not automatically know if callbacks are running, and does not fix C++ ABI incompatibilities in binaries.

## 7. Designing the C Adapter: A Contract Must Be Clear from the Start

The hands-on exercise uses a C++ class containing:

- `std::string name_` to illustrate a type with a complex allocator/lifetime.
- `std::vector<int32_t> values_` to illustrate a dynamic container.
- A C++ constructor/destructor and an `add` method.
- A `sum` method returning a 64-bit result, with overflow checking.
- A C wrapper returning a status and writing output via an out parameter.

API design:

| C function | Input | C return | Result |
| --- | --- | --- | --- |
| `engine_create` | UTF-8 C string, `engine_handle**` | Status | Opaque handle |
| `engine_add` | Handle, `int32_t` | Status | Push into C++ vector |
| `engine_sum` | Handle, `int64_t*` | Status | Sum |
| `engine_count` | Handle, `int64_t*` | Status | Element count |
| `engine_label_bytes` | Handle, `int64_t*` | Status | Bytes of label |
| `engine_destroy` | Handle | `void` | Destroy C++ object |

**Lifetime contract:**

- `create` allocates the object with C++ `new`; `destroy` uses matching C++ `delete`.
- A successfully created handle must be destroyed **exactly once**; do not use it after destroy.
- The demo wrapper is **not thread-safe for concurrent add/destroy**; the Java application uses a single thread.
- C++ exceptions are caught inside the adapter and never escape across the C function boundary.
- The input label is NUL-terminated UTF-8 and copied during create; output slots are allocated by Java.
- Every status must be checked **before Java reads out parameters**.
- The C++ destructor is called before FFM unloads the library/closes the associated Arena.

## 8. Complete C-Compatible Header File: `engine_bridge.h`

~~~c
#ifndef ENGINE_BRIDGE_H
#define ENGINE_BRIDGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Do not expose the members of this struct to C/Java. */
typedef struct engine_handle engine_handle;

enum {
    ENGINE_OK       = 0,
    ENGINE_EINVAL   = 1,
    ENGINE_ENOMEM   = 2,
    ENGINE_ERANGE   = 3,
    ENGINE_EUNKNOWN = 4
};

int engine_create(const char *label_utf8,
                  engine_handle **out_handle);
int engine_add(engine_handle *handle, int32_t value);
int engine_sum(const engine_handle *handle, int64_t *out_sum);
int engine_count(const engine_handle *handle, int64_t *out_count);
int engine_label_bytes(const engine_handle *handle,
                       int64_t *out_bytes);
void engine_destroy(engine_handle *handle);

#ifdef __cplusplus
}
#endif
#endif
~~~

**Why is this header accepted by a C compiler?** `extern "C"` is wrapped in `#ifdef __cplusplus`; the declared types are standard C; `engine_handle` is only forward-declared, and all functionality is exported through separate C function names.

Do not expose `class Engine`, `std::vector`, or `std::string` in the header. The C++ implementation will define `struct engine_handle` in full.

## 9. C++17 Implementation File: `engine_bridge.cpp`

~~~cpp
#include "engine_bridge.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

class Engine {
public:
    explicit Engine(std::string label)
        : label_(std::move(label)) {}

    void add(std::int32_t value) {
        values_.push_back(value);
    }

    bool trySum(std::int64_t &out) const noexcept {
        std::int64_t total = 0;
        const std::int64_t maximum =
                std::numeric_limits<std::int64_t>::max();
        const std::int64_t minimum =
                std::numeric_limits<std::int64_t>::min();

        for (std::int32_t v : values_) {
            const std::int64_t x = v;
            if ((x > 0 && total > maximum - x) ||
                (x < 0 && total < minimum - x)) {
                return false;
            }
            total += x;
        }

        out = total;
        return true;
    }

    std::size_t count() const noexcept {
        return values_.size();
    }

    std::size_t labelBytes() const noexcept {
        return label_.size();
    }

private:
    std::string label_;
    std::vector<std::int32_t> values_;
};

struct engine_handle {
    explicit engine_handle(std::string label)
        : engine(std::move(label)) {}
    Engine engine;
};

static int writeCount(
        std::size_t n, std::int64_t *out) noexcept {
    if (out == nullptr) {
        return ENGINE_EINVAL;
    }
    const auto limit = static_cast<std::uintmax_t>(
            std::numeric_limits<std::int64_t>::max());
    if (static_cast<std::uintmax_t>(n) > limit) {
        return ENGINE_ERANGE;
    }
    *out = static_cast<std::int64_t>(n);
    return ENGINE_OK;
}

extern "C" int engine_create(
        const char *label_utf8,
        engine_handle **out_handle) {
    if (out_handle == nullptr) {
        return ENGINE_EINVAL;
    }
    *out_handle = nullptr;
    if (label_utf8 == nullptr) {
        return ENGINE_EINVAL;
    }

    try {
        auto owned = std::make_unique<engine_handle>(
                std::string(label_utf8));
        *out_handle = owned.release();
        return ENGINE_OK;
    } catch (const std::bad_alloc &) {
        return ENGINE_ENOMEM;
    } catch (...) {
        return ENGINE_EUNKNOWN;
    }
}

extern "C" int engine_add(
        engine_handle *handle, std::int32_t value) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }

    try {
        handle->engine.add(value);
        return ENGINE_OK;
    } catch (const std::bad_alloc &) {
        return ENGINE_ENOMEM;
    } catch (...) {
        return ENGINE_EUNKNOWN;
    }
}

extern "C" int engine_sum(
        const engine_handle *handle,
        std::int64_t *out_sum) {
    if (handle == nullptr || out_sum == nullptr) {
        return ENGINE_EINVAL;
    }
    std::int64_t sum = 0;
    if (!handle->engine.trySum(sum)) {
        return ENGINE_ERANGE;
    }
    *out_sum = sum;
    return ENGINE_OK;
}

extern "C" int engine_count(
        const engine_handle *handle,
        std::int64_t *out_count) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }
    return writeCount(handle->engine.count(), out_count);
}

extern "C" int engine_label_bytes(
        const engine_handle *handle,
        std::int64_t *out_bytes) {
    if (handle == nullptr) {
        return ENGINE_EINVAL;
    }
    return writeCount(handle->engine.labelBytes(), out_bytes);
}

extern "C" void engine_destroy(engine_handle *handle) {
    delete handle;
}
~~~

### 9.1. What the C++ Code Does on Java's Behalf

- `std::make_unique<engine_handle>` invokes the constructor, creating a valid `Engine` and `std::string`.
- `engine_add` calls `std::vector::push_back`, and the C++ runtime manages allocation and reallocation.
- `engine_sum` reads the vector and checks for signed overflow before adding.
- `engine_label_bytes` counts the number of **bytes** in the C++ string, not the Java UTF-16 length.
- `engine_destroy` invokes the destructor (directly or indirectly) of `Engine` and its members; do not use `free`/Java Arena to destroy them.
- `catch(std::bad_alloc)` and `catch(...)` in functions that allocate prevent C++ exceptions from crossing the C ABI.
- The wrapper returns a status, so the Java side can turn the status into a Java exception **in Java**, after the native call has returned.

`std::size_t` is converted to `int64_t` with a range check. The C wrapper avoids exposing C++ `std::size_t` or `std::string` at the boundary. For production applications, `size_t` can be used in the C API if bound according to the exact ABI, but the compatible size must be described using FFM's canonical layouts.

### 9.2. Limitations of Validation in the Example

The wrapper can detect a null handle, but **cannot verify an arbitrary non-null pointer supplied by the caller actually points to a live object**. If Java calls `engine_add` after `engine_destroy`, that pointer is dangling and C++ dereferencing causes undefined behavior. You must design an owner, state, and concurrency protocol on the application side.

With multiple Java threads, `std::vector` in the demo must not be accessed mutably concurrently. To support concurrency, add a lock in the adapter or confine all calls to a single owner executor; `Arena.ofShared()` **does not automatically make a C++ vector thread-safe**.

## 10. Complete Java 22+ FFM Program: `CppBridgeFfmDemo.java`

In Java, all native method calls use the wrapper's C ABI. An `engine_handle*` read from an out parameter is an **opaque pointer**: Java only passes it back to the wrapper and does not read member offsets.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CppBridgeFfmDemo {
    private static void check(String operation, int status) {
        if (status != 0) {
            throw new IllegalStateException(
                    operation + ": native status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            Path path = Path.of("libenginebridge.so")
                    .toAbsolutePath();

            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle create = linker.downcallHandle(
                    library.find("engine_create").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle add = linker.downcallHandle(
                    library.find("engine_add").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            MethodHandle sum = linker.downcallHandle(
                    library.find("engine_sum").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle count = linker.downcallHandle(
                    library.find("engine_count").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle labelBytes = linker.downcallHandle(
                    library.find("engine_label_bytes").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            MethodHandle destroy = linker.downcallHandle(
                    library.find("engine_destroy").orElseThrow(),
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS));

            MemorySegment label = arena.allocateFrom("demo");
            MemorySegment slot = arena.allocate(
                    ValueLayout.ADDRESS);

            int status = (int) create.invokeExact(label, slot);
            check("engine_create", status);

            MemorySegment handle = slot.get(
                    ValueLayout.ADDRESS, 0);
            if (handle.address() == 0L) {
                throw new IllegalStateException(
                        "engine_create returned NULL");
            }

            try {
                check("add 3",
                        (int) add.invokeExact(handle, 3));
                check("add 5",
                        (int) add.invokeExact(handle, 5));
                check("add 9",
                        (int) add.invokeExact(handle, 9));

                MemorySegment countOut = arena.allocate(
                        ValueLayout.JAVA_LONG);
                MemorySegment sumOut = arena.allocate(
                        ValueLayout.JAVA_LONG);
                MemorySegment nameOut = arena.allocate(
                        ValueLayout.JAVA_LONG);

                check("engine_count",
                        (int) count.invokeExact(handle, countOut));
                check("engine_sum",
                        (int) sum.invokeExact(handle, sumOut));
                check("engine_label_bytes",
                        (int) labelBytes.invokeExact(handle, nameOut));

                System.out.println("count="
                        + countOut.get(ValueLayout.JAVA_LONG, 0));
                System.out.println("sum="
                        + sumOut.get(ValueLayout.JAVA_LONG, 0));
                System.out.println("labelBytes="
                        + nameOut.get(ValueLayout.JAVA_LONG, 0));
            } finally {
                /*
                 * C++ delete RUNS BEFORE Arena.close.
                 * Never use handle after this point.
                 */
                destroy.invokeExact(handle);
                System.out.println("destroyed=true");
            }
        }
    }
}
~~~

### 10.1. Build and Run on Linux x86-64

Use a **C++17 compiler** (GCC/Clang) and **JDK 22+**. Create the three files `engine_bridge.h`, `engine_bridge.cpp`, and `CppBridgeFfmDemo.java` in the same directory, then:

~~~bash
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -o libenginebridge.so engine_bridge.cpp

javac CppBridgeFfmDemo.java

java --enable-native-access=ALL-UNNAMED CppBridgeFfmDemo
~~~

**Expected stdout:**

~~~text
count=3
sum=17
labelBytes=4
destroyed=true
~~~

Explanation:

- C++ `std::vector` receives three values 3, 5, 9 → count 3 and sum 17.
- `std::string("demo")` has 4 UTF-8 bytes → labelBytes 4.
- `engine_destroy` is called exactly once in `finally`, before closing the Arena.
- `--enable-native-access=ALL-UNNAMED` enables restricted FFM operations for classes running on the classpath. In JDK 22 FFM is final, so `--enable-preview` is not used.
- The library is built with the `c++` driver because it needs to link the C++ runtime/stdlib; using `cc` without linking stdlib may produce unresolved symbols.

To inspect the exported C symbols (when `nm` is available):

~~~bash
nm -D --defined-only libenginebridge.so | grep engine_
~~~

Expect `engine_create`, `engine_add`, `engine_sum`, `engine_count`, `engine_label_bytes`, and `engine_destroy`. Additional compiler-generated C++ symbols may exist; Java does not call them directly.

### 10.2. ABI Mapping in Java

| C wrapper parameter | FFM layout | Java carrier |
| --- | --- | --- |
| Return `int` status | `ValueLayout.JAVA_INT` | `int` |
| `engine_handle*` | `ValueLayout.ADDRESS` | `MemorySegment` |
| `engine_handle** out` | `ValueLayout.ADDRESS` | `MemorySegment` of a pointer slot |
| `const char*` | `ValueLayout.ADDRESS` | `MemorySegment` UTF-8 buffer |
| `int32_t` | `ValueLayout.JAVA_INT` | `int` |
| `int64_t*` | `ValueLayout.ADDRESS` | `MemorySegment` of 8-byte output |
| Return `void` | `FunctionDescriptor.ofVoid(...)` | Java `void` callsite |

On Linux x86-64, C `int` is 32 bits and `int64_t` is 64 bits. A C pointer is described by `ADDRESS` rather than the layout of the object it points to.

`slot` is allocated with `arena.allocate(ValueLayout.ADDRESS)`; C writes the handle pointer into it. Java `slot.get(ValueLayout.ADDRESS, 0)` returns a pointer-value segment. **Do not use `handle.get(...)` to guess C++ fields**: `engine_handle` is opaque, the pointer segment may be zero-length, and the object is owned by C++.

### 10.3. Two Different Ownership Domains

~~~text
Java arena open
   |
   +-- label/slot/out buffers     [Arena-owned]
   +-- C library lookup          [Arena-related lifetime]
   |
   +-- engine_create
   |      +-- new engine_handle  [C++-owned]
   |      +-- std::string/vector [C++ internals]
   |
   +-- engine_add, count, sum
   |
   +-- finally: engine_destroy   [C++ delete]
   |
   +-- Arena.close              [FFM buffer/library lifetime]
~~~

**You cannot replace `engine_destroy` with `arena.close()`.** The Arena does not own C++ allocations created with `new`. Conversely, `engine_destroy` does not free the FFM output buffers allocated by the arena.

If `engine_create` fails, the C code sets `*out_handle=nullptr` and Java does not enter the destroy branch. If create succeeds, `finally` always executes destroy even when subsequent Java code throws an exception.

## 11. Standalone JNI Example, Java 17+: C++ Inside a JNI Method

The second example proves that JNI is **not forbidden** from calling C++ code. It does not need a separate C wrapper because a JNI function is already a native entrypoint understood by the JVM.

### 11.1. File `JniCppDemo.java`

~~~java
public final class JniCppDemo {
    static {
        System.loadLibrary("jnicppdemo");
    }

    private static native int calculate();

    public static void main(String[] args) {
        System.out.println("jniResult=" + calculate());
    }
}
~~~

### 11.2. File `jni_cpp_demo.cpp`

~~~cpp
#include "JniCppDemo.h"

#include <exception>
#include <numeric>
#include <vector>

static void throwRuntime(JNIEnv *env, const char *message) {
    jclass klass = env->FindClass(
            "java/lang/RuntimeException");
    if (klass != nullptr) {
        env->ThrowNew(klass, message);
        env->DeleteLocalRef(klass);
    }
}

extern "C" JNIEXPORT jint JNICALL
Java_JniCppDemo_calculate(JNIEnv *env, jclass clazz) {
    (void)clazz;

    try {
        std::vector<int> values{10, 20, 12};
        int result = std::accumulate(
                values.begin(), values.end(), 0);
        return static_cast<jint>(result);
    } catch (const std::exception &error) {
        throwRuntime(env, error.what());
        return 0;
    } catch (...) {
        throwRuntime(env, "Unknown C++ error");
        return 0;
    }
}
~~~

The native code is compiled with a C++ compiler, so it constructs `std::vector` and uses the STL directly. It **catches C++ exceptions** before returning to the JVM. `ThrowNew` puts a Java exception into JNI's pending state; the native code returns a `jint` as required by the signature, but Java will observe the exception if it was successfully set.

### 11.3. JNI Build/Run Commands

Set `JAVA_HOME` to point to the JDK used for compiling/running (JDK 17+ on Linux), then run:

~~~bash
javac -h . JniCppDemo.java

c++ -std=c++17 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicppdemo.so jni_cpp_demo.cpp

java -Djava.library.path=. JniCppDemo
~~~

**Stdout:**

~~~text
jniResult=42
~~~

This is not an example of "JNI automatically understanding `std::vector`": the **C++ compiler** does that; JNI is just the Java → native boundary. With a real vendor library, the C++ JNI translation unit must include the right SDK headers and link against the right vendor binaries/ABI.

## 12. Common Pitfalls When Passing Data

### 12.1. Java `String` Differs from `std::string`

The FFM example uses `arena.allocateFrom("demo")` to create a **NUL-terminated UTF-8 buffer**, which C++ then copies into `std::string`. Java `String` has UTF-16 code units, whereas `std::string::size()` counts bytes; the two lengths can differ, especially for Vietnamese and emoji.

If data contains embedded NULs, a C-string `const char*` will be truncated at the first NUL byte. For arbitrary data, use `const uint8_t* data, size_t length` and specify encoding, bounds, and lifetime clearly.

Do not return a pointer to `std::string::c_str()` of a temporary C++ string that has already been destroyed. If returning a borrowed pointer, document which object keeps the memory alive and which operations can invalidate it.

### 12.2. Java Arrays Differ from `std::vector<T>`

FFM does not allow passing a Java `List<Float>` as a `std::vector<float>` by value. A C wrapper typically uses `float* values, size_t count`, and then the C++ adapter copies/constructs the vector. If you want to avoid copying, you must ensure the buffer is not modified/freed while native code is using it.

`std::vector::data()` can change when the vector reallocates due to `push_back`, `reserve`, or destruction; do not store the pointer and return it to Java for indefinite use. A two-pass API (query size, then caller allocates buffer to copy into) can make sense, but concurrency can change the size between the two calls; there must be a snapshot/version/retry contract.

### 12.3. C Pointers Do Not Carry Bounds

`engine_handle*` is an opaque pointer. You cannot call `MemorySegment.ofAddress(raw).reinterpret(largeSize)` just to "try reading" the C++ structure. Assigning arbitrary wrong bounds is a restricted operation and risks crashing. Only pass the pointer to a C wrapper that understands the exact object type/lifetime.

### 12.4. ABI Pointer/Number Widths and Endianness

In a C API, using `int32_t`/`int64_t` reduces some width differences. However, pointer size, alignment, char encoding, calling convention, C struct layout, and the vendor library's ABI must still be checked per OS/architecture. C `long` on Linux x64 is typically 64 bits, whereas on Windows x64 it is typically 32 bits; do not always map C `long` to Java `JAVA_LONG`.

When a C interface exposes `size_t`, consult `Linker.nativeLinker().canonicalLayouts()` instead of guessing the width. A C ABI wrapper does not make a Linux Java binary run with a Windows DLL.

## 13. C++ Exceptions and Error Handling at the Native Boundary

A C++ native implementation can `throw std::bad_alloc` or `std::runtime_error`. FFM does not automatically convert them to Java exceptions; neither does JNI do so safely on its own.

The approach used by the sample C wrapper:

~~~c
/* Public C protocol. */
enum {
    ENGINE_OK       = 0,
    ENGINE_EINVAL   = 1,
    ENGINE_ENOMEM   = 2,
    ENGINE_ERANGE   = 3,
    ENGINE_EUNKNOWN = 4
};
~~~

On the C++ side:

~~~cpp
// Logic excerpt, not standalone.
try {
    // Call C++ method; may throw.
    return ENGINE_OK;
} catch (const std::bad_alloc &) {
    return ENGINE_ENOMEM;
} catch (...) {
    return ENGINE_EUNKNOWN;
}
~~~

On the Java side, read **status** before reading `out_sum`. Error codes must have a contract: whether output is modified on failure, whether the error is retryable, and whether native state remains usable.

If an error message is needed, use a C API like `get_error(buffer, capacity, written)` or a per-call error buffer with a specific encoding. A global `last_error` can be overwritten by other threads; `thread_local` also requires tracking which thread executes each downcall and native async work.

In JNI, after `env->ThrowNew(...)`, you must follow the pending Java exception rules; most JNI functions must not be called arbitrarily while an exception is pending, and some APIs may return NULL due to OOME. C++ exceptions must be caught **before** the JNI native method returns.

## 14. Native Ownership, Use-After-Free, and Concurrency

There are at least three different kinds of lifetimes:

| Resource | Who allocates | Who frees properly |
| --- | --- | --- |
| C++ object with `new` | C++ library/adapter | C++ `delete` via `engine_destroy` |
| FFM buffer in `Arena.ofConfined` | Java FFM Arena | Java `arena.close()` on owner |
| JNI global reference | JNI `NewGlobalRef` | JNI `DeleteGlobalRef` |
| Native vendor allocation | Vendor API | Vendor-specific disposer |
| FFM upcall stub | `Linker.upcallStub`/Arena | Unregister/drain callbacks before close |
| Java object/array | JVM | Java GC, native only holds valid references |

**Do not mix allocators**: `malloc/free`, C++ `new/delete`, FFM Arena, and vendor memory pools are not interchangeable.

### 14.1. A Non-NULL Pointer Can Still Be Dangling

~~~text
Java thread A                 Java thread B
--------------------          -------------------------
engine_add(handle, 7)
                              engine_destroy(handle)
C++ vector being modified     delete object
=> use-after-free / crash
~~~

The C++ wrapper in the example does not implement locking for concurrent operations. In a real Java application, manage an owner thread/executor, or an `AutoCloseable` class that tracks OPEN/CLOSING/CLOSED state and waits for in-flight calls before destroying.

Checking `handle.address() != 0` does not prevent use-after-free. A pointer can still be non-zero after the object has been deleted.

### 14.2. Async Callbacks Make the Problem Harder

A C++ SDK might accept `std::function<void(Event)>`, retain it, and invoke it on a native worker thread. Java FFM can only interact through a C callback pointer/user-data protocol defined by the adapter. Java must keep the `upcallStub`/Arena alive until native code **unregisters and drains** all callbacks that have started or reserved the right to be called.

In JNI, a C++-created worker needs to attach/detach with the JVM to use JNI, and must not share `JNIEnv*` across threads. Global Java references must also be reclaimed once there are no more callbacks.

A timeout or Java `Future.cancel(true)` does not by itself prove native code has stopped holding the pointer. Do not close the Arena or destroy the native context without a safe acknowledgement.

## 15. When You Cannot Modify the C++ Library

Four scenarios:

| What do you have? | Viable option |
| --- | --- |
| Vendor C++ headers + linkable SDK/toolchain | Write a C++ JNI bridge or a C API adapter |
| Official C wrapper already available | FFM/JNI calls C API, consider `jextract` |
| Only CLI/service API | Use subprocess/IPC/RPC, with clear schema/version/deadline |
| Only opaque binary and no supported interface | Request vendor API/SDK; do not guess vtables/mangled symbols for production |

**A C adapter still depends on the vendor C++ ABI internally.** If the SDK was built with an incompatible compiler/stdlib or differing flags such as `_GLIBCXX_USE_CXX11_ABI`, the adapter may fail to link or run properly. `extern "C"` only makes the **public boundary** easier to control; it does not cure ABI mismatches between C++ libraries.

If you need to prevent an unstable native library from crashing the JVM, process isolation helps: run the native component in a separate process and communicate via RPC/IPC with a data schema, timeouts, and a restart policy. The trade-off is serialization/IPC overhead and not passing raw memory pointers across processes.

### 15.1. Why Not Use JNI/FFM to "Guess the Vtable"?

Vtable layout, virtual base offsets, and destructors/thunks can change across compilers and versions. A production application that reads a vtable address by guessed slot index has no reliable ABI contract. Even if it "works on my machine," flipping a compiler flag can cause the wrong method to be called.

This differs from a C function pointer published by the vendor API with a clear prototype: in that case, FFM can describe `FunctionDescriptor` accurately.

## 16. Testing C++ ↔ Java Bindings

Minimum tests:

1. **Build ABI**: build the adapter with the exact vendor compiler/runtime; load the right architecture and stdlib dependencies.
2. **Symbol exports**: `nm -D` or an equivalent tool verifies actual C exports, not demangled names.
3. **Positive path**: create → add → sum/count → destroy, comparing against C++ expected values.
4. **Error path**: null input/out pointer, invalid status, allocation failure simulation, overflow.
5. **Resource ownership**: no leaks/double-free, closed exactly once, Java use-after-close blocked at the wrapper.
6. **Concurrent access**: if multiple threads are allowed, stress add/read/destroy and verify synchronization.
7. **Strings**: ASCII, Unicode, embedded NUL contract, long strings, invalid UTF-8.
8. **Arrays**: zero-length, huge length, capacity mismatch, signed vs unsigned, overlap, and alignment.
9. **Vendor updates**: C++ class implementation changes while the C ABI remains stable per contract; test regeneration when the C header changes.
10. **Callbacks**: async events, unregister/drain, Arena lifetime, pending exceptions.
11. **Platform matrix**: Linux/Windows/macOS and x86-64/ARM64 only when actually supported; do not copy `.so` files to Windows.
12. **Failure containment**: native crash, compiler sanitizer reports, process restart/IPC if needed.

A good binding must test **both directions**: Java creates input that C++ computes correctly; C++ produces output that Java reads correctly. Java writing and reading its own wrong layout can still look valid, so native-side assertions and testing against the real ABI are necessary.

## 17. Common Anti-Patterns

| Anti-pattern | Problem | Alternative |
| --- | --- | --- |
| `SymbolLookup.find("Class::method")` | Does not resolve overloads/mangled symbols/receiver | C wrapper function |
| Copying symbols from `nm -C` | Demangled name, not an ABI contract | Clearly named C exports |
| `extern "C" std::vector<T> f(...)` | C++ container ABI is still exposed | Buffer + length/status/opaque handle |
| Java doing `arena.allocate(sizeofClass)` | C++ constructor has not run | C++ create wrapper |
| Java calling `free` on object created with C++ `new` | Wrong destructor/allocator | `engine_destroy` |
| Java holding `std::vector::data()` after `push_back` | Reallocation can invalidate pointer | Snapshot/copy/lease |
| C++ exception escaping through FFM/JNI | No automatic Java exception mapping | Catch and convert to status/ThrowNew |
| JNI sharing `JNIEnv*` across native threads | Violates JNI thread association | AttachCurrentThread, local JNIEnv |
| Java `jlong` handle used after destroy | Dangling pointer | Owner lifecycle/state guard |
| Adapter C++ ABI differs from vendor | Link/runtime mismatch | Compatible toolchain/stdlib/flags |
| FFM `FunctionDescriptor` guessing C++ struct by value | Class ABI not fully described | C opaque pointer adapter |
| `--enable-native-access` to fix symbol ABI | Permission flag does not change ABI | C interface and matching toolchain |
| Closing Arena before callbacks are drained | Native calls invalidated upcall stub | Unregister, drain, join, close |
| Skipping native cleanup because of GC | Leaks/non-deterministic timing | Explicit AutoCloseable/native destroy |
| Measuring a few small calls and concluding JNI/FFM is "always faster" | Overhead depends on workload | Real end-to-end benchmark |

## 18. Pre-Merge Checklist

- [ ] Identified the C++ SDK, C++ standard library, toolchain, and target ABI?
- [ ] Have a C-compatible header or C++ JNI glue, not relying on mangled class symbols?
- [ ] C API does not expose `std::string`/`vector`/templates/virtual classes by value?
- [ ] C++ constructors/destructors run properly on the native side?
- [ ] Java only holds opaque handles with controlled lifetimes?
- [ ] All C++ exceptions caught before the native/Java boundary?
- [ ] Error/status codes and output validity clearly specified?
- [ ] There is a `destroy` API and one Java owner calling it exactly once?
- [ ] No unsynchronized concurrent use/destroy?
- [ ] C `long`, `size_t`, fixed-width ints, and pointer layouts match the ABI?
- [ ] Java Strings/arrays converted with correct encoding, length, and ownership?
- [ ] Native borrowed buffers do not expire while Java is using them?
- [ ] JNI local/global refs, pending exceptions, and thread attachment handled properly?
- [ ] FFM `Linker`/`SymbolLookup`/`FunctionDescriptor` match C signatures?
- [ ] FFM native access flags match the JDK/module?
- [ ] Unregister/drain before closing upcall Arena/library if async is used?
- [ ] Native-side tests, sanitizers, or CI in place for actually supported platforms?
- [ ] If no valid SDK is available, considered a vendor C API or IPC instead of reverse-engineering the ABI?

## 19. Self-Check Questions

1. Why cannot a C++ method `Analyzer::infer(std::vector<float>)` be described directly like a normal C function?
2. Does `extern "C"` turn `std::vector` into a portable C struct?
3. Can JNI be written in C++ and call the STL? Why is glue still required?
4. If `SymbolLookup.find("name")` finds a raw C++ symbol, does that mean the ABI descriptor is right?
5. Why is knowing `sizeof(CppClass)` alone not enough for Java to create an instance with an Arena?
6. Why should `engine_handle*` be opaque to Java?
7. What should be used to free an object allocated with `new`?
8. If Java converts `std::string` into a UTF-8 buffer, what factors need to be specified?
9. In what situations can `std::vector::data()` become invalid?
10. How must C++ exceptions be handled in a C wrapper? In JNI?
11. Is `jextract` a general-purpose tool for translating C++ templates/classes?
12. If the vendor's C++ toolchain differs from the adapter's, does `extern "C"` fix every mismatch?
13. When two Java threads use and destroy the same handle, what is the risk?
14. Does an FFM Arena own a C++ object allocated with `new` inside a wrapper?
15. Why does FFM `--enable-native-access` not solve vtable ABI issues?
16. If a vendor provides no header/API but provides a CLI, what is an alternative to native loading?
17. When callbacks run asynchronously, what must be done before closing the Arena?
18. Why is a fixed-width C API + opaque handles usually easier to maintain than exposing C++ class layouts?

**Suggested answers:** (1) member/overload/template/STL ABI; (2) no, only language linkage; (3) yes, but C++ compiler/Java conversions/lifetime must be written; (4) not yet, a symbol does not carry full signature/ownership; (5) constructor/object model has not run; (6) avoids depending on class layout/vtable; (7) C++ destroy/delete of the matching type; (8) UTF-8, NUL, length, ownership, lifetime; (9) reallocation/destructor; (10) catch into status or JNI ThrowNew; (11) no, only C headers; (12) no; (13) use-after-free/race; (14) no; (15) a permission flag does not define the C++ ABI; (16) IPC/subprocess; (17) unregister and drain callbacks; (18) reduces ABI surface and is easier to verify/version.

## 20. Official References

- [Oracle JDK 22 — `Linker`, C ABI, downcall/upcall, and canonical layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `FunctionDescriptor`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle JDK 22 — `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `Arena` and `MemorySegment`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [OpenJDK jextract Guide — C header limitations and C layer for C++](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md)
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle JNI Specification — Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [cppreference — C++ language linkage, `extern "C"`](https://en.cppreference.com/w/cpp/language/language_linkage)
- [GCC libstdc++ ABI](https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html)

**Conclusion:** JNI **can run C++ code** inside native methods, but developers still have to write glue to convert Java objects ↔ C++ objects, manage lifetimes, handle C++ exceptions, and match compiler ABIs. FFM **does not automatically understand complex C++ APIs**; it is suited for a stable C ABI. A C++ adapter exporting **`extern "C"` functions, opaque handles, status/out parameters, and explicit create/destroy** is usually the clearest choice for building testable Java bindings. When compatible C headers/SDKs are unavailable, do not guess mangled symbols/vtables and call them directly in production; request a vendor interface or use an appropriate process/IPC boundary.
