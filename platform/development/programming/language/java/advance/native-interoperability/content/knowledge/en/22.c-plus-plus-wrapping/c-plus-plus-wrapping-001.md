# Why C++ Classes, Overloading, and ABI Must Be Considered Before Linking

## Learning Objectives

A C++ library does not just contain named functions. It has **classes**, **constructors/destructors**, **method overloading**, **virtual dispatch**, **templates**, **STL containers**, **exceptions**, and ABI conventions determined by the compiler/toolchain. When Java wants to call native code through the **Foreign Function & Memory API (FFM)** or **JNI**, those details directly affect symbol names, calling conventions, how data is passed, object lifetimes, and compatibility across builds.

Central question: **Why can't you just look at a method name in C++ and have Java look up the symbol and call it like a C function?**

After this lesson you will be able to:

1. Understand **name mangling** and why C++ overloads require distinct symbols at the binary level.
2. Explain the risks of **C++ class layout, implicit `this`, virtual tables, multiple inheritance**, and RTTI.
3. Distinguish **C linkage** created by **extern "C"** from a **truly safe C ABI contract**.
4. Explain why C++ **exceptions, STL, allocators, and constructors/destructors** must be managed at the native boundary.
5. Design a **C-compatible façade**: opaque handles, distinct C function names, status codes, out parameters, and balanced create/destroy.
6. Compile a C++17 library yourself, inspect exported symbols with native tools, and call the library via **Java 22+ FFM**.
7. Know when to choose **FFM, JNI, or jextract**, and how to check for mismatches between Linux/GCC, Windows/MSVC, and other ABIs.

**Example environment:** C++17 on Linux x64, JDK 22+ (FFM became a final API in JDK 22, per JEP 454). With JDK 17, a C façade can still be used via JNI, but the **java.lang.foreign** package example will not compile verbatim on JDK 17; JDK 21 uses a different FFM preview.

## 1. Three Boundaries You Must Understand Clearly

~~~text
Java code
   |
   | FFM SymbolLookup / Linker / FunctionDescriptor
   | or JNI native method
   v
C-compatible exported functions           ← Stable ABI by contract
   |
   | calls C++ object/method using the exact native compiler
   v
C++ implementation (classes, overloads, STL, exceptions)
   |
   v
Native library .so / .dll / .dylib
~~~

A real-world Java application might need to call **Counter::add(int)**, but FFM's Linker does not automatically know that **Counter** is a C++ class, does not automatically generate a C++ constructor call, does not automatically resolve overloaded methods, and does not automatically interpret a vtable. It needs a **function address** with a **native signature compatible with `FunctionDescriptor`**.

Break the problem into three layers:

| Layer | What to verify | If wrong |
| --- | --- | --- |
| **Naming and exports** | What symbol does the function have, and is it in the dynamic export table? | SymbolLookup cannot find it |
| **ABI and data types** | Are arguments, return values, memory layout, and calling convention correct? | Data corruption, crashes, memory corruption |
| **Ownership and semantics** | Who creates/destroys the object? How are exceptions, threads, callbacks, and resources managed? | Leaks, use-after-free, double-free, race conditions |

Success at the first layer (lookup finds an address) does not prove the other two layers are correct.

## 2. Name Mangling: Why a C++ Function Does Not Necessarily Export Under the Same Name

C++ supports overloading:

~~~cpp
int transform(int input);
double transform(double input);
~~~

In C++ source code, the compiler distinguishes the two functions by their parameter types. At the linker level, it typically **decorates/mangles** the names to encode enough information to select the right overload.

For example, a toolchain using the **Itanium C++ ABI** on Linux might produce illustrative symbols like:

~~~text
_Z9transformi
_Z9transformd
~~~

These are examples of mangled names for the two parameter types, **not a universal contract across all compilers**. Microsoft MSVC uses a different **decorated names** scheme, often starting with a question mark for C++ functions. Namespaces, classes, qualifiers, parameter types, and calling conventions can all affect the encoded name.

You can see these different names when inspecting a shared library:

~~~bash
nm -D --defined-only libsample.so
nm -D --defined-only libsample.so | c++filt
~~~

**nm** displays symbols; **c++filt** demangles names into human-readable descriptions. However, demangling is only for diagnostics; **it does not turn a C++ ABI into a C ABI**.

### Why Not Hard-Code Mangled Names in Java?

Suppose Java tries to look up **_Z9transformi**. A different compiler version, namespace, or signature can change the symbol name. More importantly, **C++ member methods also have receiver and calling convention rules**, so finding the right name does not guarantee a correct call.

A public API should not force Java to depend on implementation-specific mangled names unless the project intentionally locks down the entire compiler/ABI and tests it rigorously.

## 3. What `extern "C"` Can and Cannot Do

In C++:

~~~cpp
extern "C" int c_transform_i32(int input) {
    return input * 2;
}
~~~

**extern "C"** requests **C language linkage**, allowing the public function to use C-compatible naming/linkage conventions on that toolchain. On Linux x64, the exported symbol can typically be looked up as **c_transform_i32**, without needing to know a name mangled by the C++ compiler.

### C Linkage Does Not Support Overloading Under the Same C Name

The following two declarations are **intentionally invalid** and are not meant to build:

~~~cpp
extern "C" int c_convert(int value);
extern "C" double c_convert(double value);
~~~

A C name does not encode an overload signature like a C++ decorated name; you cannot export two overloaded functions with the same C linkage identifier and expect dynamic lookup to pick the right one. They must be separated:

~~~cpp
extern "C" int c_convert_i32(int value);
extern "C" double c_convert_f64(double value);
~~~

The new C names describe the exposed types. The C++ implementation can still use overloads behind the wrapper.

### `extern "C"` Does Not Automatically Solve the Remaining Problems

- It does not turn **std::string/std::vector/std::map** into C structs with a portable layout.
- It does not eliminate vptrs, C++ object layout, multiple inheritance, or RTTI.
- It does not make constructors/destructors ordinary C functions that Java can call.
- It does not automatically turn C++ exceptions into Java exceptions.
- It does not guarantee the caller can use **free** on a C++ object allocated with **new**.
- It does not automatically give types like **long, size_t, pointer, wchar_t** the same size across all ABIs.
- It does not automatically export a Windows DLL function without **__declspec(dllexport)** or an export configuration.
- It does not prevent certain symbol decoration rules caused by Windows x86 calling conventions.

**Section takeaway:** `extern "C"` helps establish the public symbol boundary, but the entire **function signature + layout + lifetime** still has to be designed as a complete C ABI contract.

## 4. A C++ Class Is Not a Record You Can Send Directly to Java

Consider:

~~~cpp
class Calculator {
public:
    explicit Calculator(int seed);
    int add(int delta) const;
    double add(double delta) const;
    virtual ~Calculator();
private:
    int seed_;
};
~~~

There are at least five factors that require separate consideration.

**Constructor:** It is not just a C function taking `seed` and returning `Calculator*`. The C++ compiler is responsible for fully initializing the object, which may include base classes and a vptr. A C façade should provide **calculator_create(int)**, using **new Calculator(seed)** internally and returning a handle.

**Destructor:** A virtual or non-virtual destructor must be invoked through the proper native mechanism, which may trigger cleanup of members. Java should not simply `free` the object's address and expect the destructor to run. The C façade needs **calculator_destroy(handle)**.

**Member functions and `this`:** **Calculator::add(int)** takes an implicit receiver according to C++ ABI rules. You cannot just prepend a **ValueLayout.ADDRESS** to an FFM `FunctionDescriptor` and assume every compiler will call it like a regular C function.

**Overloads:** The two methods **add(int)** and **add(double)** can have distinct mangled names. The C side should expose **calculator_add_i32** and **calculator_add_f64**.

**Virtual dispatch, vtables, and inheritance:** vptr/vtable layout, base subobject offsets, and pointer adjustments are toolchain-dependent. Java should not read a raw vtable pointer to call virtual functions directly without ABI-specific bindings.

C++ multiple inheritance example:

~~~cpp
struct BaseA {
    virtual int valueA() const;
};

struct BaseB {
    virtual int valueB() const;
};

struct Derived : BaseA, BaseB {
    int state;
};
~~~

This snippet only **illustrates a class hierarchy**; the virtual methods have no implementation. The **Derived*** and **BaseB*** pointers may require address adjustment when casting to a base subobject. This is why an opaque handle and wrapper methods are far safer than computing class field offsets manually in Java.

## 5. C++ ABI Is Broader Than Symbol Names

**ABI — Application Binary Interface** specifies both how machine code calls functions and how data is represented in binary: register/stack arguments, return values, alignment, exception unwinding, RTTI, and binary object layout.

### GCC/Clang and MSVC

On many platforms using GCC/Clang, C++ mangling and layout follow conventions related to the **Itanium C++ ABI**; that name does not mean it is only used on Itanium CPUs. **MSVC** on Windows has its own C++ ABI rules. A C++ library built by compiler A is not automatically binary-compatible with every binary built by compiler B.

Even within a single compiler family, factors that can affect the ABI include:

- compiler version and target architecture;
- C++ standard library version, libstdc++/libc++/MSVC STL;
- **_GLIBCXX_USE_CXX11_ABI** on certain GNU libstdc++ builds;
- packing/alignment flags, compiler attributes, exception/RTTI options;
- calling convention and export visibility;
- static vs. dynamic C runtime, allocator boundaries;
- debug/release build configuration and specific STL settings.

**Do not use identical type names as proof of identical ABIs.** A function accepting **std::string** on one C++ side does not necessarily understand a `std::string` object created by a different compiler/STL.

### The C ABI Is Also Platform-Dependent

A C façade does not make the ABI identical across all systems. C **long** is typically 8 bytes on LP64 Linux x64 and 4 bytes on LLP64 Windows x64. **size_t**, pointer width, alignment, struct packing, and boolean/enum conventions also need to be checked.

When defining public C functions, prefer fixed-width types like **int32_t, uint64_t** for numeric data of known width, while still verifying **double representation**, calling convention, alignment, pointer ownership, and the actual compiler/platform.

## 6. C++ Exceptions, STL, and Allocators Must Stop at the Native Boundary

### C++ Exception Boundary

A C++ method may throw **std::overflow_error**, **std::bad_alloc**, or other exceptions. An FFM downcall **provides no mechanism to automatically catch a C++ exception across Java frames**. Letting a C++ exception escape a C-compatible function called by FFM/JNI is dangerous: unwinding across the boundary may be unsupported, leading to termination, crashes, or uncontrolled errors.

Solution:

~~~text
C++ operation
     |
   try/catch (...), inside the native wrapper
     |
     +-- success -> status = 0, write output
     |
     +-- failure -> status != 0, output must not be trusted
     |
Java checks status
     |
     +-- create an appropriate Java exception if needed
~~~

**Catching exceptions is only the first step.** If a function mutates state and then throws, returning a status code from the wrapper does not automatically roll back all changes; the API needs to document exception-safety/transactional guarantees.

### STL and Strings

Do not expose **std::string**, **std::vector**, or C++ references directly in a header that Java FFM treats as a C ABI. More controllable approaches:

- **const char* + length** for strings with a defined encoding (usually UTF-8);
- **const uint8_t* + size_t** for binary data;
- **caller-owned buffer** to receive data copied back to Java;
- **opaque handle** for complex C++ collections/objects;
- explicit **create/destroy** or **buffer_release** for native-managed allocations.

A **char*** pointer could be a NUL-terminated string or a raw buffer; there must be a clear contract, especially when embedded 0 bytes or encodings other than UTF-8 are possible.

### Do Not Arbitrarily Replace `new/delete` with `malloc/free`

An object allocated with **new** must be handled with the matching native **delete** so its destructor runs. Calling C **free** on that object's address is wrong. Especially on Windows, different DLL/CRT heaps make freeing resources across runtimes even more dangerous.

Java FFM's **Arena** manages native `MemorySegment`s allocated through the Arena; **it does not automatically manage the lifetime of a C++ object allocated by the library with `new`**. Therefore, the C-compatible wrapper must provide a destroy function, and Java must call it at the right time.

## 7. Designing a C Façade: An API Containing Only C-Compatible Types

The goal is to **hide the C++ implementation** and expose a small set of C functions that Java can link to accurately.

Principles:

1. Each C++ overload gets its **own C export name**.
2. Use **extern "C"** in the header when compiled as C++.
3. Ensure proper export visibility on Linux/macOS/Windows.
4. Keep the class implementation inside `.cpp`; the public C header uses only **opaque struct pointers**.
5. Use **int32_t, double, pointers** with a verified ABI.
6. The C wrapper **catches exceptions** and returns status codes; never throw across the boundary.
7. Define **output valid only when status==0**.
8. Use symmetric **create/destroy** with a consistent allocator.
9. Explicitly state whether the caller may share handles across threads.
10. Use the native compiler to verify exported symbol names and run Java integration tests.

The core C API will look like this:

~~~c
typedef struct CounterHandle CounterHandle;
CounterHandle* counter_create(int32_t initial);
int counter_add_i32(const CounterHandle *h, int32_t delta, int32_t *out);
int counter_add_f64(const CounterHandle *h, double delta, double *out);
void counter_destroy(CounterHandle *h);
~~~

This is a condensed **fragment**; the full code below includes header guards, export macros, and `noexcept`. Java does not need to know how many fields `CounterHandle` has or whether it has a vtable; Java simply passes the handle back to C functions of the same library.

## 8. End-to-End Example: Two C++ Overloads, One C Façade, Java FFM

**Target platform:** Linux x64, GCC/Clang supporting C++17, JDK 22+ with standard FFM. The example intentionally uses simple addition to verify the right overloaded method and ABI.

### 8.1. File `counter_c.h` — C-Compatible Interface

~~~c
#ifndef COUNTER_C_H
#define COUNTER_C_H

#include <stdint.h>

/* Platform-specific export macro. */
#if defined(_WIN32)
    #if defined(COUNTER_BUILD)
        #define COUNTER_API __declspec(dllexport)
    #else
        #define COUNTER_API __declspec(dllimport)
    #endif
#else
    #define COUNTER_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
    #define COUNTER_NOEXCEPT noexcept
    extern "C" {
#else
    #define COUNTER_NOEXCEPT
#endif

/* Incomplete type: C/Java must not access object internals. */
typedef struct CounterHandle CounterHandle;

enum {
    COUNTER_OK = 0,
    COUNTER_INVALID_ARG = 1,
    COUNTER_ARITHMETIC_ERROR = 2
};

/* Returns NULL when native object creation fails. */
COUNTER_API CounterHandle *counter_create(
        int32_t initial) COUNTER_NOEXCEPT;

/* Only writes *out when return status == COUNTER_OK. */
COUNTER_API int counter_add_i32(
        const CounterHandle *handle,
        int32_t delta,
        int32_t *out) COUNTER_NOEXCEPT;

COUNTER_API int counter_add_f64(
        const CounterHandle *handle,
        double delta,
        double *out) COUNTER_NOEXCEPT;

/* Caller destroys only once, after no more calls use the handle. */
COUNTER_API void counter_destroy(
        CounterHandle *handle) COUNTER_NOEXCEPT;

#ifdef __cplusplus
}
#endif

#endif
~~~

**Key points:**

- When compiled under C++, **extern "C"** applies C linkage and **COUNTER_NOEXCEPT** expands to **noexcept**; when compiled under C, both C++ elements are omitted.
- On Windows, **COUNTER_API** exports the symbol if building the DLL with **COUNTER_BUILD**, while importing C code can use `dllimport`. On Linux/macOS GCC/Clang, default visibility allows public functions to be found by the loader.
- **CounterHandle** is an opaque/incomplete struct: callers cannot allocate it with **sizeof(CounterHandle)**, read its fields, or `delete` it directly.
- Statuses **0, 1, 2** are this example's contract, not standard C++ error codes.
- **COUNTER_NOEXCEPT** on declarations helps express the ABI wrapper as a boundary that will not let exceptions escape.

### 8.2. File `counter.cpp` — C++ Class and C Wrappers

~~~cpp
#include "counter_c.h"

#include <cstdint>
#include <limits>
#include <stdexcept>

class Counter {
public:
    explicit Counter(std::int32_t initial)
            : base_(initial) {}

    std::int32_t add(std::int32_t delta) const {
        const std::int64_t sum =
                static_cast<std::int64_t>(base_) +
                static_cast<std::int64_t>(delta);

        if (sum < std::numeric_limits<std::int32_t>::min() ||
            sum > std::numeric_limits<std::int32_t>::max()) {
            throw std::overflow_error("int32 overflow");
        }

        return static_cast<std::int32_t>(sum);
    }

    double add(double delta) const {
        return static_cast<double>(base_) + delta;
    }

private:
    std::int32_t base_;
};

struct CounterHandle {
    explicit CounterHandle(std::int32_t initial)
            : object(initial) {}

    Counter object;
};

extern "C" COUNTER_API CounterHandle *counter_create(
        int32_t initial) noexcept {
    try {
        return new CounterHandle(initial);
    } catch (...) {
        return nullptr;
    }
}

extern "C" COUNTER_API int counter_add_i32(
        const CounterHandle *handle,
        int32_t delta,
        int32_t *out) noexcept {
    if (handle == nullptr || out == nullptr) {
        return COUNTER_INVALID_ARG;
    }

    try {
        const std::int32_t answer = handle->object.add(delta);
        *out = answer;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_ARITHMETIC_ERROR;
    }
}

extern "C" COUNTER_API int counter_add_f64(
        const CounterHandle *handle,
        double delta,
        double *out) noexcept {
    if (handle == nullptr || out == nullptr) {
        return COUNTER_INVALID_ARG;
    }

    try {
        const double answer = handle->object.add(delta);
        *out = answer;
        return COUNTER_OK;
    } catch (...) {
        return COUNTER_ARITHMETIC_ERROR;
    }
}

extern "C" COUNTER_API void counter_destroy(
        CounterHandle *handle) noexcept {
    delete handle;
}
~~~

**Explanation:**

- C++ has two methods both named **add**, taking **std::int32_t** and **double**; the compiler selects the right overload inside each wrapper.
- **counter_add_i32** and **counter_add_f64** are two distinct exported C names, without requiring Java to understand mangled method names.
- **int64_t** adds two `int32` values without intermediate overflow, then checks the `int32` range. When base 10 is added to **Integer.MAX_VALUE**, the C++ method throws **std::overflow_error**.
- The C wrapper catches the exception and returns **COUNTER_ARITHMETIC_ERROR = 2**. **out** is only written after the calculation succeeds.
- **counter_create** allocates with **new**, and **counter_destroy** deallocates with **delete** in the same library.
- There are no STL types or class definitions in the public C header. This is a **shared library implementation**, with no `main`.

**Limitation:** Catch-all is used to demonstrate preventing exceptions from crossing the boundary, whereas a production API usually needs finer error classification rather than hiding all causes behind a single status.

### 8.3. Building on Linux

Create the two files **counter_c.h** and **counter.cpp** in the same directory, then run:

~~~bash
mkdir -p build

g++ -std=c++17 -Wall -Wextra -Wpedantic \
    -O2 -fPIC -shared -fvisibility=hidden \
    -DCOUNTER_BUILD counter.cpp \
    -o build/libcounter_c.so
~~~

**g++** (or a properly configured `clang++`) compiles and links the C++ runtime. **-fPIC -shared** builds an ELF shared library on Linux; **-fvisibility=hidden** hides non-public symbols, while **COUNTER_API** explicitly exports the C façade. **-DCOUNTER_BUILD** only affects the import/export macro in the Windows branch and does not break the Linux demo.

Check exported C symbols:

~~~bash
nm -D --defined-only build/libcounter_c.so \
  | grep 'counter_'
~~~

The goal is to see four names:

~~~text
counter_create
counter_add_i32
counter_add_f64
counter_destroy
~~~

This is the **list of symbol names you should see**, not the raw stdout of **nm**, since `nm` also prints addresses and symbol types. You can use **nm -D ... | c++filt** to read C++ mangled names, but do not use them as Java's public ABI.

### 8.4. File `CppFacadeDemo.java` — Java 22+ Using FFM Downcalls

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class CppFacadeDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        Path library = Path.of("build", "libcounter_c.so")
                .toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // CounterHandle* counter_create(int32_t)
            MethodHandle create = linker.downcallHandle(
                    symbols.find("counter_create").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            // int counter_add_i32(CounterHandle*, int32_t, int32_t*)
            MethodHandle addI32 = linker.downcallHandle(
                    symbols.find("counter_add_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            // int counter_add_f64(CounterHandle*, double, double*)
            MethodHandle addF64 = linker.downcallHandle(
                    symbols.find("counter_add_f64").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.ADDRESS));

            // void counter_destroy(CounterHandle*)
            MethodHandle destroy = linker.downcallHandle(
                    symbols.find("counter_destroy").orElseThrow(),
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS));

            MemorySegment handle =
                    (MemorySegment) create.invokeExact(10);

            if (handle.equals(MemorySegment.NULL)) {
                throw new IllegalStateException(
                        "native constructor returned NULL");
            }

            System.out.println("created = true");

            try {
                MemorySegment intOut =
                        arena.allocate(ValueLayout.JAVA_INT);

                int intStatus =
                        (int) addI32.invokeExact(handle, 32, intOut);
                if (intStatus != 0) {
                    throw new IllegalStateException(
                            "int status=" + intStatus);
                }
                System.out.println("int result = " +
                        intOut.get(ValueLayout.JAVA_INT, 0));

                MemorySegment doubleOut =
                        arena.allocate(ValueLayout.JAVA_DOUBLE);

                int doubleStatus =
                        (int) addF64.invokeExact(handle, 2.5, doubleOut);
                if (doubleStatus != 0) {
                    throw new IllegalStateException(
                            "double status=" + doubleStatus);
                }
                System.out.println("double result = " +
                        doubleOut.get(ValueLayout.JAVA_DOUBLE, 0));

                // 10 + Integer.MAX_VALUE does not fit in int32.
                int overflowStatus = (int) addI32.invokeExact(
                        handle, Integer.MAX_VALUE, intOut);
                System.out.println("overflow status = " +
                        overflowStatus);

            } finally {
                destroy.invokeExact(handle);
                System.out.println("destroyed = true");
            }
        }
    }
}
~~~

**Observe the mappings:**

| C façade signature | Java FFM descriptor |
| --- | --- |
| **CounterHandle* create(int32_t)** | Return **ADDRESS**, argument **JAVA_INT** |
| **int add_i32(CounterHandle*, int32_t, int32_t*)** | Return **JAVA_INT**, args **ADDRESS, JAVA_INT, ADDRESS** |
| **int add_f64(CounterHandle*, double, double*)** | Return **JAVA_INT**, args **ADDRESS, JAVA_DOUBLE, ADDRESS** |
| **void destroy(CounterHandle*)** | **ofVoid(ADDRESS)** |

The **MemorySegment handle** from **ValueLayout.ADDRESS** represents a pointer token; it does not mean Java may read the bytes of the `Counter` object. Java only passes it to functions of the same library.

**Output buffers:** **intOut** and **doubleOut** are allocated by the Java `Arena` in the appropriate scope, passed as pointers to native code, and read after status 0. On overflow, **intOut** must not be treated as a new result, regardless of any value remaining from a previous call.

**finally** ensures `destroy` is called if the handle was successfully created, even if Java code throws an exception afterward. The library lookup and output segments stay alive in the `Arena` until the end of the **try-with-resources** block. Do not call `destroy` twice.

### 8.5. Running Java

~~~bash
javac CppFacadeDemo.java

java --enable-native-access=ALL-UNNAMED CppFacadeDemo
~~~

With JDK 22+ FFM and a properly built Linux native library, stdout:

~~~text
created = true
int result = 42
double result = 12.5
overflow status = 2
destroyed = true
~~~

**Why is this right?** The C++ `Counter` receives `base=10`. The `int` overload computes **10+32=42**. The `double` overload computes **10.0+2.5=12.5**. Calling the `int` overload with **Integer.MAX_VALUE** exceeds the `int32` range, C++ throws `overflow_error`, and the wrapper catches it and returns status 2. Finally, Java calls **counter_destroy** to match the native lifetime.

**--enable-native-access=ALL-UNNAMED** grants restricted method access to classpath code; **--enable-preview** is not needed since FFM is final in JDK 22. When using a named module, native access must be configured for the actual module.

**No guarantees about stderr:** Depending on the JVM and environment configuration, diagnostics may print additional messages; the five lines above are the stdout explicitly printed by the program.

## 9. Why Didn't This Demo Link Directly to `Counter::add`?

From Java's perspective, it is clear:

~~~text
Java knows:
  "counter_create"
  "counter_add_i32"
  "counter_add_f64"
  "counter_destroy"

Java does not need to know:
  C++ mangled names
  byte layout of Counter
  vtable / hidden this
  constructor/destructor ABI
  C++ exception implementation
  std::allocator
~~~

The two overloaded C++ **add** methods are resolved directly in the native source code by the appropriate C++ compiler. The C façade guarantees a set of symbols and primitive signatures that are straightforward to express with FFM.

If Java were to look up the mangled name of **Counter::add(double)** directly, it would also need to know the receiver pointer, how the compiler passes member arguments, const/cv-qualification, the actual ABI, and pointer adjustments when inheritance is involved. Using a C façade eliminates many fragile assumptions about the native toolchain.

## 10. Interacting with JNI and jextract

### FFM (Java 22+)

**SymbolLookup.libraryLookup**, **Linker.downcallHandle**, **FunctionDescriptor**, and **MemorySegment** let you call a C-compatible native function. The advantage is that you do not need to declare Java `native` methods or write JNI stubs once the public interface is a C ABI.

~~~text
Java FFM -> native C ABI façade -> C++ methods
~~~

FFM restricted native calls require native access under the appropriate module/runtime policy. FFM has no mechanism to automatically understand C++ class objects.

### JNI (When JVM-Specific Integration or an Older JDK Is Needed)

JNI goes through a Java `native` method and an exported function matching JNI naming/ABI rules:

~~~cpp
// C++ fragment: requires jni.h and the corresponding Java class demo.Bridge.
extern "C" JNIEXPORT jint JNICALL
Java_demo_Bridge_add(JNIEnv *env,
                     jclass cls,
                     jint left,
                     jint right) {
    (void)env;
    (void)cls;
    return left + right;
}
~~~

`JNIEXPORT`/`JNICALL` specify JNI export/calling conventions, while **extern "C"** prevents C++ name mangling beyond the JNI naming rules. This fragment is not standalone: it requires a Java `native` declaration, building a library, and `System.loadLibrary`. When a bridge actually calls C++ objects, it still needs to address constructors, exceptions, ownership, and ABI just like FFM.

### jextract (Generating Bindings for C Headers)

`jextract` can generate Java bindings from **counter_c.h** because it is a C-compatible header that does not expose C++ templates or classes. You must choose a `jextract` version matching the FFM API and target JDK, inspect the generated methods, and compile/run on the target native ABI. Do not feed `jextract` a C++ STL-heavy header and expect every overload/vtable to be generated as Java methods.

**You can combine them:** C++ implementation + C façade + `jextract`-generated Java FFM bindings. This combination is convenient when an interface has many functions/structs and you want to avoid writing many `FunctionDescriptor`s by hand.

## 11. Library Loading Paths and Symbol Checks

### Linux

~~~bash
nm -D --defined-only build/libcounter_c.so
nm -D --defined-only build/libcounter_c.so | c++filt
readelf -d build/libcounter_c.so
ldd build/libcounter_c.so
~~~

- **nm -D** inspects dynamic exported symbols.
- **c++filt** helps read mangled C++ names during diagnostics.
- **readelf -d** shows dynamic dependencies and loader metadata.
- **ldd** checks shared library dependencies on trusted binaries.

**Successful symbol lookup ≠ correct ABI.** If you call with the wrong `FunctionDescriptor`, pointer lifetime, or calling convention, the app can still crash after lookup.

### Windows

You can use the MSVC Developer Command Prompt (illustrative, not a Linux demo command):

~~~bat
cl /nologo /std:c++17 /EHsc /LD /DCOUNTER_BUILD ^
  counter.cpp /Fe:counter_c.dll

dumpbin /exports counter_c.dll
~~~

Windows requires the **__declspec(dllexport)** macro or an appropriate export declaration, the right MSVC toolset, and CRT setup. Under some Windows x86 calling conventions, C symbols still get name decoration, so you should verify the actual names in the DLL export table. On Windows x64, common C-style exports are less likely to be decorated, but you must not infer this solely from filenames.

### macOS

Typically uses **.dylib** and `dyld` library loading. The `nm` tool may display C symbols with a leading underscore, which does not mean Java always looks them up with the underscore: verify symbol lookup on the actual runtime. Do not automatically carry Linux `.so` or C++ ABI assumptions over to macOS.

## 12. Thread Safety, Callbacks, and Ownership

A C façade does not make a C++ class thread-safe. When Java holds a **CounterHandle***, you must specify:

- Can multiple Java threads call methods on the same handle concurrently?
- Do the C++ methods mutate fields or call external code?
- Are there internal locks and a reentrancy policy?
- Can `destroy` be called while another thread is still using the handle in a downcall?
- How long is a native→Java callback registered, which thread invokes it, and when is it unregistered?
- Is there native thread affinity, such as COM/GUI/event loops?

The `Counter` demo only reads `base_` after construction and does not mutate internal state in `add`. However, **`destroy` must still wait for all in-flight operations to finish**. Java's **finally** only manages the scope of the calling thread; it does not synchronize the entire system.

**Memory note:** A returned pointer can be represented by a Java **MemorySegment** without Java automatically knowing the object has been `delete`d. Never dereference or pass a handle after `destroy`. For a production Java wrapper, you can wrap the handle in an **AutoCloseable** that tracks closed state, while still guarding against double-close and concurrent use-after-close.

**Callbacks/upcalls:** If C++ stores a function pointer created via Java FFM **Linker.upcallStub**, the arena owning the stub must remain alive until native code unregisters it. The Java exception/callback policy must also have compatible boundaries; do not let exceptions cross native frames arbitrarily.

## 13. String, Buffer, and Opaque Data Design

A C-facing header for a native library might look like:

~~~c
/* Fragment: names are illustrative, without implementation yet. */
typedef struct QueryHandle QueryHandle;

int query_create(QueryHandle **out);
int query_add_filter(QueryHandle *handle,
                     const char *key,
                     const char *value);
int query_copy_result(QueryHandle *handle,
                      char *buffer,
                      size_t capacity,
                      size_t *written);
void query_destroy(QueryHandle *handle);
~~~

You must specify:

1. **Encoding**: Are `key`/`value` UTF-8 or another encoding?
2. **Termination**: NUL-terminated or pointer+length? Binary data can contain NUL bytes.
3. **Ownership**: Does `query_add_filter` copy the strings or retain the pointers after returning?
4. **Buffer capacity**: If it is too small, what code is returned, and is `written` the bytes written or the bytes required?
5. **Threading**: Can a shared handle be used concurrently?
6. **Allocator**: If the library allocates a buffer, who calls `release` and in which runtime?
7. **size_t**: The Java mapping must match the native ABI (x86 vs. x64/Windows vs. Linux).
8. **Versioning**: Changing a signature must bump the API version, not silently keep the old name.

**Do not have Java receive `std::string` by value over FFM** just because the object holds UTF-8 data internally. The STL's layout/allocator is not a long-term C ABI protocol.

## 14. C API Versioning and Binary Compatibility

A stable C façade is easier to version than a direct C++ class ABI, but you must still avoid silently changing signatures.

Example:

~~~c
/* Fragment, without implementations yet. */
int counter_v1_get(const CounterHandle *h, int32_t *result);
int counter_v2_get(const CounterHandle *h,
                   int32_t *result,
                   uint32_t flags);
~~~

If an older Java program linked **counter_v1_get** with two arguments, but a newer native library changed the actual signature under the same name to three arguments, the old `FunctionDescriptor` can cause undefined native behavior. Keep the old symbol with its old contract, or introduce a versioned name with an explicit migration.

**The C ABI is still platform-dependent**: C `int`/`long` sizes, pointer width, calling convention, struct packing, endianness, and library dependencies must be verified in every native build. A façade is not a promise that a Windows DLL can be loaded into a Linux JVM.

## 15. Troubleshooting Table

| Symptom | Primary cause | How to verify |
| --- | --- | --- |
| **SymbolLookup.find** cannot find function | C++ mangled name, hidden visibility, not exported | `nm`/`dumpbin`, `extern "C"`, export macros |
| **libcounter_c.so** fails to load | Wrong path/architecture/dependency | Absolute path, `ldd`, target OS/CPU |
| **WrongMethodTypeException** | Wrong `invokeExact` carrier/argument count | Compare `FunctionDescriptor` and `MethodHandle.type` |
| **IllegalCallerException** on downcall | Restricted FFM native access not granted | `--enable-native-access` for the right module/classpath |
| Immediate crash on invoke | Wrong C ABI/`FunctionDescriptor`/calling convention | Check native signature, ABI, pointers |
| Wrong result without crashing | C type sizes, alignment, endianness, or prototype mismatch | C header/`sizeof`/`offsetof`/toolchain |
| Double-free/use-after-free | Incorrect ownership and destroy contract | Java state management, native resource tests |
| C++ exception causes terminate | Wrapper did not catch exception before FFM | Catch in native code, return status |
| Works on Linux but fails on Windows | MSVC ABI, DLL export, LLP64, CRT | Build/test per platform, `dumpbin` |
| Linking C++ object files misses STL runtime | Used C linker instead of C++ linker | `g++`/`clang++`, native runtime dependencies |
| `JNIEXPORT` function not found by Java | Wrong JNI name/signature/`extern "C"` | `javap`, `nm`, generated header, `JNICALL` |
| Java memory `Arena` closes before native finishes using pointer | Incorrect lifetime | Keep `Arena` alive, verify callback/store semantics |

**Important:** Do not troubleshoot by guessing a new mangled symbol while ignoring the native signature, runtime, and ownership. When testing, build a minimal C façade and prove it end-to-end first.

## 16. Pre-Linking Checklist for C++ Libraries

**Designing the native boundary**

- [ ] Public symbols are C-compatible functions, not relying on mangled C++ method names.
- [ ] Each overload has a distinct C export name.
- [ ] Header uses **extern "C"** for C++ compilation and appropriate export visibility.
- [ ] Opaque handles replace public C++ class layouts.
- [ ] **create/destroy** exist, the caller knows resource ownership, and there is a one-destroy policy.
- [ ] C++ exceptions are caught and translated into a status/error protocol.
- [ ] Scalars, pointers, buffers, encodings, and byte lengths have clear contracts.
- [ ] No STL types, templates, or C++ references are exposed in the C ABI.
- [ ] Threading/reentrancy/async callbacks/lifetimes are documented.
- [ ] Compiler/OS/CPU/C++ runtime are compatible with the native binary being wrapped.

**Java linking**

- [ ] Java JDK/FFM or JNI version is correct.
- [ ] Actual native library loads and symbols have been verified.
- [ ] `FunctionDescriptor` matches all input/output C types.
- [ ] Java does not dereference opaque pointers directly.
- [ ] Native status is checked before reading out parameters.
- [ ] `finally`/`AutoCloseable` and library-specific `destroy` are called appropriately.
- [ ] Handle is never used after `destroy` or after library unload.
- [ ] Native integration tests exist for success, invalid arguments, exceptions, and concurrency.
- [ ] With `jextract`, the input is a C-compatible header and the generated source matches the target JDK.

## 17. Self-Check Questions

**Question 1.** Why shouldn't Java use **SymbolLookup.find("add")** to call `Counter::add(int)` directly?

**Answer:** A C++ member function has a mangled name and an implicit **this** receiver following the toolchain's calling convention. The symbol `"add"` does not describe all of those elements; use a public C façade instead.

**Question 2.** Can **extern "C"** export the same name **convert** for both `int` and `double` overloads?

**Answer:** No. C linkage does not provide overloaded symbol names. Use **convert_i32** and **convert_f64** or other independent C names.

**Question 3.** Why is **std::string** not a portable type to pass directly to Java FFM?

**Answer:** Its C++ object layout, allocator, ABI, and lifetime depend on the runtime/compiler. Convert it to a C-compatible encoding + buffer/length or an opaque handle.

**Question 4.** When a native `Counter` is created with `new`, can Java call `free(handle)`?

**Answer:** No. Java must call **counter_destroy(handle)** provided by the same native library so that `delete` and the destructor run properly.

**Question 5.** If C++ throws an exception in `add`, does Java FFM automatically turn it into a Java exception?

**Answer:** No. The native wrapper catches exceptions inside C++ and returns a status code; Java handles the error based on that status.

**Question 6.** If the exported symbol has the right name, is a Java downcall guaranteed to be safe?

**Answer:** Not yet. `FunctionDescriptor`, ABI, calling convention, pointer lifetime, and ownership still need to be verified.

**Question 7.** On the same JDK 22+, is a C++ library built by MSVC automatically object-layout compatible with a library built by GCC?

**Answer:** No. The JDK does not determine the C++ ABI of native toolchains.

**Question 8.** Why does a façade still need a threading contract even when all functions are `extern "C"`?

**Answer:** C linkage only affects naming and calling conventions; it does not make a C++ object thread-safe, and calling `destroy` while another downcall is using the handle is still dangerous.

**Question 9.** What happens if a C function returns status 2 and Java still reads `intOut`?

**Answer:** `intOut` is not a valid new result; it may still hold an old value. Only read data when the contract reports success.

**Question 10.** Does `jextract` directly parse C++ classes and virtual methods into standard Java APIs for every compiler?

**Answer:** No. `jextract` primarily generates FFM bindings from C headers; you need a C-compatible façade or a specialized tool with a verified ABI.

### Practice Exercises

**A.** Add a C++ **add(int64_t)** overload and a **counter_add_i64** C façade using the appropriate `ValueLayout` for `int64_t`; explain how to avoid overflow during addition.

**B.** Remove `extern "C"` from one export in a sandbox copy, rebuild the library, and use `nm` to compare the symbols. Note why FFM lookup by the C name fails.

**C.** Try passing **MemorySegment.NULL** as the out parameter to **counter_add_i32** and check for status 1 without dereferencing a null pointer. Do not do this on a library that lacks validation.

**D.** Write an **AutoCloseable** Java wrapper around `CounterHandle`; prevent double-close, forbid using the handle after close, and manage synchronization if multiple threads may call it concurrently.

**E.** Design an API accepting a UTF-8 string: let Java allocate the buffer pointer+length; ensure native code does not retain the pointer after the Java `Arena` closes.

## Official References

- Microsoft Learn — **Name Decoration**: https://learn.microsoft.com/en-us/cpp/error-messages/tool-errors/name-decoration
- Microsoft Learn — **Decorated names**: https://learn.microsoft.com/en-us/cpp/build/reference/decorated-names
- Microsoft Learn — **Exporting C++ Functions for C-Language Executables**: https://learn.microsoft.com/en-us/cpp/build/exporting-cpp-functions-for-use-in-c-language-executables
- GCC libstdc++ — **ABI and binary compatibility**: https://gcc.gnu.org/onlinedocs/libstdc++/manual/abi.html
- Itanium C++ ABI Specification: https://itanium-cxx-abi.github.io/cxx-abi/abi.html
- Java SE 22 — **Foreign Function & Memory API**: https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html
- Java SE 22 — **Call a C Library Function via FFM**: https://docs.oracle.com/en/java/javase/22/core/calling-c-library-function-foreign-function-and-memory-api.html
- Java SE 22 — **Linker**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Java SE 22 — **SymbolLookup**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- OpenJDK — **JEP 454: FFM API final**: https://openjdk.org/jeps/454
- OpenJDK — **jextract repository**: https://github.com/openjdk/jextract

**Summary:** When Java needs to use C++, **C++ classes, overloading, and ABI must be considered before linking**, because the symbol name is only the tip of the binary contract. A **C façade with `extern "C"`**, explicit C names for overloads, **opaque handles**, **status/out parameters**, an exception boundary, and **create/destroy** allow Java FFM/JNI to call C++ through a simpler interface, while still requiring verification of the native ABI, calling convention, loader, lifetime, and thread safety.
