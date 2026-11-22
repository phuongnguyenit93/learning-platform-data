# Keeping Exceptions, std::string, and C++ Allocators Inside the Wrapper

## Lesson Objectives

When Java integrates a C++ library using the **Foreign Function & Memory API (FFM)** or JNI, the risk does not lie only in calling the right symbol. C++ exceptions, **std::string** objects, class layouts, **new/delete** lifecycles, and internal allocators are not things that should be exposed as-is across the C ABI boundary.

A testable design is to create a **C ABI wrapper** (C-compatible wrapper) as the boundary: the Java side only sees status codes, fixed-width data types, opaque pointers, byte buffers with explicit capacity/length, and a corresponding release function. The C++ side keeps exceptions, STL types, destructors, RAII, and allocators within the same library.

This lesson helps you:

1. Explain why **extern "C" does not automatically turn std::string or exceptions into a stable C ABI**.
2. Catch all C++ exceptions inside a **noexcept** wrapper and convert them into error codes for Java to handle.
3. Keep **std::string** internal; pass across the boundary using **const char* + byte length**, or **char* output + capacity + required length**.
4. Hold C++ objects via an **opaque handle** and call matching **create/release**, without mixing new/delete with malloc/free.
5. Use RAII, **std::unique_ptr**, try/finally, and Arena to preserve proper ownership when exceptions occur.
6. Run a complete example: **C header + C++17 implementation + Java 22+ FFM**, with Linux/macOS/Windows build commands, deterministic error codes, and expected stdout.
7. Analyze common bugs regarding Unicode, ABI, thread safety, lifetime, output buffers, double-free, library unloading, and binary upgrades.

**Version:** The java.lang.foreign API was finalized in **JDK 22 (JEP 454)**, so the Java FFM code here requires JDK 22+. If you must run on Java 17, use an appropriate JNI adapter while still applying the same C++ wrapper principles.

## 1. Separation of Responsibilities at the Boundary

~~~text
              Java application
       String / exceptions / Arena
                     |
          FFM downcall or JNI
                     |
       +--------------------------+
       | Public C ABI             |
       | int32_t status           |
       | char* + byte length      |
       | opaque bridge_handle*    |
       | bridge_release(handle)   |
       +--------------------------+
                     |
          C++ wrapper (noexcept)
          catches all exceptions
          converts status/errors
                     |
        Internal C++ implementation
        std::string / std::vector
        std::unique_ptr / new/delete
        custom allocator / RAII
~~~

**This boundary is a contract, not a name mangling trick.** Java does not need to know whether std::string has small-string optimization, how C++ destructors work, what the vtable/class layout looks like, or which exception unwinding runtime the compiler uses.

### Why Not Export C++ Classes Directly?

C++ standardizes the behavior of classes/STL, but does not standardize the binary layout of std::string, aggregate return types, vtables, and name mangling across compilers/runtimes. The FFM Linker calls native functions according to a **FunctionDescriptor provided by the developer**, rather than automatically discovering all C++ template and object model rules.

The following header is **not pure C ABI** even with extern "C":

~~~cpp
extern "C" std::string make_label(); // DO NOT DO THIS.
extern "C" const std::exception* last_exception(); // DO NOT DO THIS.
~~~

Java would have to guess the layout/lifetime/allocator of those C++ objects to use the result. A better approach is:

~~~c
typedef struct bridge_handle bridge_handle;

int32_t bridge_create(
    const char* bytes,
    int32_t byte_length,
    bridge_handle** out_handle
);
int32_t bridge_render(
    const bridge_handle* handle,
    int32_t repeat,
    char* out_bytes,
    int32_t capacity_bytes,
    int32_t* out_required_bytes
);
void bridge_release(bridge_handle* handle);
~~~

This section **illustrates the API structure**; the full header with export/noexcept macros is in section 6. The struct name is published, while its definition is **not public**.

## 2. C++ Exceptions Must Be Caught Before Leaving the Wrapper

### extern "C" Does Not Catch Exceptions Automatically

~~~cpp
extern "C" int32_t bad_function() {
    throw std::runtime_error("failure"); // INTENTIONALLY WRONG.
}
~~~

extern "C" mainly controls language linkage/symbol names; it does **not** convert a C++ exception into a Java Throwable, and does not guarantee that a Java FFM downcall can catch a C++ exception as a RuntimeException. Letting an exception escape across a foreign boundary can lead to termination, crashes, or undefined behavior.

### noexcept and Status Code Pattern

~~~cpp
extern "C" int32_t safe_function(int32_t value) noexcept {
    try {
        if (value < 0) {
            throw std::invalid_argument("negative input");
        }
        return 0;   // OK
    } catch (const std::invalid_argument&) {
        return 1;   // INVALID_ARGUMENT
    } catch (const std::out_of_range&) {
        return 2;   // OUT_OF_RANGE
    } catch (const std::bad_alloc&) {
        return 3;   // NO_MEMORY
    } catch (...) {
        return 5;   // INTERNAL_ERROR
    }
}
~~~

This is a snippet that requires the corresponding C++ headers; it is not a complete source file. **noexcept** is a commitment that the function does not throw to the caller; if an exception escapes a noexcept function, C++ will call **std::terminate**. Therefore, catching all exceptions in the wrapper is a part of correctness.

### Error Codes Must Have Clear Meaning

| Status | Meaning in the Example API | Java Action |
| ---: | --- | --- |
| **0** | OK | Only then use outputs normally |
| **1** | INVALID_ARGUMENT | Check for NULL, negative length, negative repeat |
| **2** | OUT_OF_RANGE | Exceeds limit or size is too large |
| **3** | NO_MEMORY | Allocator error / insufficient resources |
| **4** | BUFFER_TOO_SMALL | Read required byte length and allocate enough |
| **5** | INTERNAL_ERROR | Unexpected error in library; log for investigation |

**The numbers above are defined by the example itself**, not default Java FFM errors. Do not catch(...) and return OK, do not treat every error as an “empty string”, and do not create complex std::string objects inside catch when memory is running low.

### Exceptions from Destructors

Destructors of C++ resources going through a public release function must not throw. If a destructor throws inside a noexcept release, the program may terminate. For resource closing that can fail, consider a **close** returning a status first, then a non-throwing **release** to free the allocation; the state after an error must be clearly specified, and do not retry blindly.

## 3. std::string Must Be Kept on the C++ Side

**std::string** manages bytes, capacity, and allocator on the C++ side. It is not a C struct with a standard layout. Do not return std::string by value or a pointer to std::string for Java to read with MemoryLayout.

### Input: Byte Pointer + Explicit Length

~~~c
int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
);
~~~

C++ can construct a std::string from **input_bytes** with **input_size_bytes**. Do not use strlen or the std::string(const char*) constructor if the bytes might contain NUL in the middle.

For Java:

- **String.length()** counts UTF-16 code units, not UTF-8 byte count.
- Use **string.getBytes(StandardCharsets.UTF_8)**, then pass **byte[].length**.
- For example, **é** has one UTF-16 code unit but two UTF-8 bytes; supplementary emojis have two UTF-16 code units but four UTF-8 bytes.
- std::string stores bytes; it does not automatically validate that a string is valid UTF-8. If the library requires UTF-8, the wrapper or caller must validate according to the contract.
- Binary data is not necessarily a C string, and does not require a terminating 0 byte.

### Output: Caller-Provided Byte Buffer

Do not return a pointer to local.c_str():

~~~cpp
extern "C" const char* unsafe_name() {
    std::string local = "temporary";
    return local.c_str(); // Dangling after return.
}
~~~

A c_str/data pointer can also be invalidated when std::string is mutated/reallocated or the object is destroyed. A controllable approach is to **copy bytes into a buffer allocated by Java**:

~~~c
int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t capacity_bytes,
    int32_t *out_required_bytes
);
~~~

Rules:

1. When called with **out_bytes=NULL, capacity=0**, C returns the **required bytes** via out_required_bytes.
2. If the output is non-empty and capacity is insufficient, C returns **BUFFER_TOO_SMALL** and **does not write out of bounds**.
3. Java allocates a buffer of the exact required bytes and calls again.
4. C++ copies the **exact** number of bytes; Java decodes using the actual byte count, not strlen.
5. **Required does not include a NUL terminator** in the example contract. If another API outputs a C string, it must explicitly define **whether to add one NUL byte** or not.

**Note on two-pass query/copy:** A snapshot/immutable source or versioning/bounded retry is needed if the string can change between the two calls. In the example, a handle's text is not modified after creation, so the required size is stable.

## 4. C++ Allocators and Ownership Must Stay Inside the Wrapper

### Matching Allocation/Deallocation

| Who Allocates? | Who Frees Properly? |
| --- | --- |
| C++ **new T** | C++ **delete p** via the corresponding owner |
| C++ **new T[n]** | **delete[] p** |
| **malloc** | Matching **free** |
| Custom C++ allocator/pool | That allocator/pool's own release API |
| **std::unique_ptr** | Deleter held by the C++ type |
| **Arena.allocate** from Java FFM | Arena.close() of the owner Arena |
| Opaque object whose ownership is transferred by bridge_create to Java | **bridge_release** in the same C++ library |

Do not call libc free on an object created by C++ new: the destructor may not run, the allocator may differ, and the native heap may be corrupted. On Windows, mixing different C runtime heaps/toolchains must especially be avoided.

### Opaque Handle

The public C header only declares:

~~~c
typedef struct bridge_handle bridge_handle;
~~~

The C++ side defines the actual contents:

~~~cpp
struct bridge_handle {
    std::string text;

    explicit bridge_handle(std::string value)
        : text(std::move(value)) {}
};
~~~

Java only receives **bridge_handle \*** as an ADDRESS; **it must not be reinterpreted into a structLayout to read the C++ class directly**.

### RAII Up to the Exact Point of Ownership Transfer

~~~cpp
std::unique_ptr<bridge_handle> pending(
    new bridge_handle(std::move(text))
);
// If a step can still throw, pending will clean up automatically.
// When all steps succeed:
*out_handle = pending.release();
~~~

This is a snippet; the variables text/out_handle must exist in the full function. If the constructor or processing throws before release(), unique_ptr automatically cleans up the object. When release() succeeds, ownership is transferred to the caller: Java must call **bridge_release** exactly once.

**A MemorySegment alias does not create additional ownership.** Multiple Java modules can hold the same address, but only one owner is allowed to release. For a Java AutoCloseable wrapper, use appropriate state/locking if idempotent close is needed; do not attach both Arena cleanup and manual free for the same handle.

## 5. Designing a Public C ABI Includable by a C Compiler

Key decisions:

- Use **extern "C"** under **#ifdef __cplusplus**, so a C compiler can still read the header.
- Use OS-specific export macros; on Windows building a DLL requires **__declspec(dllexport)**.
- Use **noexcept** on the C++ side in both prototype and definition, since a C compiler does not have that keyword.
- Isolate classes/stdlib types using an **opaque pointer**.
- Prefer **int32_t** for status/length in the example to easily map to **ValueLayout.JAVA_INT**.
- Write comments about **bytes**, **NULL**, **ownership**, error outputs, and ranges.
- Maintain a **bridge_release** corresponding to every successful create.

Do not use C++ std::string, std::vector, std::exception, std::unique_ptr, C++ references, or templates in the public C ABI.

## 6. Runnable Example — File cpp_bridge.h

Create the file **cpp_bridge.h**:

~~~c
#ifndef CPP_BRIDGE_H
#define CPP_BRIDGE_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(BRIDGE_BUILD)
#    define BRIDGE_API __declspec(dllexport)
#  else
#    define BRIDGE_API __declspec(dllimport)
#  endif
#else
#  define BRIDGE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
#  define BRIDGE_NOEXCEPT noexcept
extern "C" {
#else
#  define BRIDGE_NOEXCEPT
#endif

/* Incomplete type, does not export C++ class layout. */
typedef struct bridge_handle bridge_handle;

enum {
    BR_OK = 0,
    BR_INVALID_ARGUMENT = 1,
    BR_OUT_OF_RANGE = 2,
    BR_NO_MEMORY = 3,
    BR_BUFFER_TOO_SMALL = 4,
    BR_INTERNAL_ERROR = 5
};

/*
 * input_size_bytes: byte count, not C string length.
 * input_bytes may be NULL when input_size_bytes == 0.
 * out_handle != NULL; on success transfers ownership to caller.
 * On failure: *out_handle == NULL, caller must not release.
 */
BRIDGE_API int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
) BRIDGE_NOEXCEPT;

/*
 * renders text repeated `repeat` times, separated by '|'.
 * repeat: 0..16. out_required_bytes != NULL.
 * output: exact bytes, NO NUL terminator.
 * Query size: out_bytes=NULL, capacity=0.
 */
BRIDGE_API int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t out_capacity_bytes,
    int32_t *out_required_bytes
) BRIDGE_NOEXCEPT;

/* Exactly one release per live handle. */
BRIDGE_API void bridge_release(
    bridge_handle *handle
) BRIDGE_NOEXCEPT;

/* For example verification only, does not replace synchronization. */
BRIDGE_API int32_t bridge_active_handles(void) BRIDGE_NOEXCEPT;

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CPP_BRIDGE_H */
~~~

**Header analysis:** BRIDGE_BUILD selects export on Windows; the implementation file will define this macro before including the header. BRIDGE_NOEXCEPT keeps the declaration and definition having the same exception specification in C++; when compiling a C file, the macro is empty. bridge_handle is an incomplete type; it is not allocated with malloc from the C caller/Java side.

### C ABI Does Not Mean a Binary Runs on Every Operating System

The shared library must be built for the OS/CPU/ABI of the JVM. The wrapper still has to link C++ dependencies with a compatible runtime/compiler, even though the public header avoids exposing C++ STL ABI. When replacing the C++ implementation, test with the same set of C signatures, status codes, and semantics.

## 7. Runnable Example — File cpp_bridge.cpp

Create the file **cpp_bridge.cpp**:

~~~cpp
#define BRIDGE_BUILD
#include "cpp_bridge.h"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>

struct bridge_handle {
    std::string text;

    explicit bridge_handle(std::string input)
        : text(std::move(input)) {}
};

namespace {
    std::atomic<int32_t> live_handles{0};
    constexpr int32_t MAX_REPEAT = 16;
}

extern "C" BRIDGE_API int32_t bridge_create(
    const char *input_bytes,
    int32_t input_size_bytes,
    bridge_handle **out_handle
) noexcept {
    if (out_handle == nullptr) {
        return BR_INVALID_ARGUMENT;
    }
    *out_handle = nullptr;

    try {
        if (input_size_bytes < 0 ||
            (input_size_bytes > 0 && input_bytes == nullptr)) {
            throw std::invalid_argument("invalid input");
        }

        // Preserve exact byte sequence, including embedded NUL.
        std::string text;
        if (input_size_bytes > 0) {
            text.assign(
                input_bytes,
                static_cast<std::size_t>(input_size_bytes)
            );
        }

        std::unique_ptr<bridge_handle> pending(
            new bridge_handle(std::move(text))
        );
        *out_handle = pending.release();
        live_handles.fetch_add(1, std::memory_order_relaxed);
        return BR_OK;
    } catch (const std::invalid_argument&) {
        return BR_INVALID_ARGUMENT;
    } catch (const std::bad_alloc&) {
        return BR_NO_MEMORY;
    } catch (...) {
        return BR_INTERNAL_ERROR;
    }
}

extern "C" BRIDGE_API int32_t bridge_render(
    const bridge_handle *handle,
    int32_t repeat,
    char *out_bytes,
    int32_t out_capacity_bytes,
    int32_t *out_required_bytes
) noexcept {
    if (out_required_bytes == nullptr) {
        return BR_INVALID_ARGUMENT;
    }
    *out_required_bytes = 0;

    try {
        if (handle == nullptr ||
            repeat < 0 ||
            out_capacity_bytes < 0 ||
            (out_capacity_bytes > 0 && out_bytes == nullptr)) {
            throw std::invalid_argument("invalid arguments");
        }
        if (repeat > MAX_REPEAT) {
            throw std::out_of_range("too many repeats");
        }

        const uint64_t n =
            static_cast<uint64_t>(handle->text.size());
        const uint64_t r = static_cast<uint64_t>(repeat);
        const uint64_t separatorBytes = r > 0 ? r - 1 : 0;
        const uint64_t required64 = n * r + separatorBytes;

        if (required64 >
            static_cast<uint64_t>(
                std::numeric_limits<int32_t>::max()
            )) {
            throw std::out_of_range("too many output bytes");
        }

        const int32_t required =
            static_cast<int32_t>(required64);
        *out_required_bytes = required;

        // Query size: do not write if buffer is insufficient.
        if (out_capacity_bytes < required) {
            return BR_BUFFER_TOO_SMALL;
        }

        std::string output;
        output.reserve(static_cast<std::size_t>(required));
        for (int32_t i = 0; i < repeat; ++i) {
            if (i > 0) {
                output.push_back('|');
            }
            output.append(handle->text);
        }

        if (required > 0) {
            std::memcpy(
                out_bytes, output.data(),
                static_cast<std::size_t>(required)
            );
        }
        return BR_OK;
    } catch (const std::invalid_argument&) {
        return BR_INVALID_ARGUMENT;
    } catch (const std::out_of_range&) {
        return BR_OUT_OF_RANGE;
    } catch (const std::length_error&) {
        return BR_OUT_OF_RANGE;
    } catch (const std::bad_alloc&) {
        return BR_NO_MEMORY;
    } catch (...) {
        return BR_INTERNAL_ERROR;
    }
}

extern "C" BRIDGE_API void bridge_release(
    bridge_handle *handle
) noexcept {
    if (handle == nullptr) {
        return;
    }

    // delete calls the proper C++ destructor and matching allocator.
    // Handle MUST still be alive; double-delete is undefined behavior.
    delete handle;
    live_handles.fetch_sub(1, std::memory_order_relaxed);
}

extern "C" BRIDGE_API int32_t bridge_active_handles(
    void
) noexcept {
    return live_handles.load(std::memory_order_relaxed);
}
~~~

### Key Points in the C++ Code

**bridge_create:** A valid out_handle parameter is set to NULL before creating the object. std::unique_ptr owns the object during the phase that can still throw. When release() happens, the Java caller is transferred ownership exactly once. If an error occurs before that, the destructor/RAII cleans up automatically.

**bridge_render:** Uses std::string internally but only copies **bytes** out to the caller buffer. Computes the size in **uint64_t**, rejects exceeding INT32_MAX, and then checks capacity. When capacity=0 and the output has data, returns **BR_BUFFER_TOO_SMALL** along with required. Output data **has no NUL terminator**.

**bridge_release:** deletes the opaque handle in the exact C++ module, so the std::string destructor runs. The API is not inherently safe against already-freed handles; Java must ensure release is called exactly once.

**bridge_active_handles:** std::atomic only supports diagnostics; it does not protect render and release operations on the **same handle** if called concurrently.

### Where Are Exceptions Converted into Statuses?

| Error/Exception in C++ | C Status |
| --- | --- |
| Null/negative input: std::invalid_argument | **1** |
| repeat > 16 or output too large: std::out_of_range | **2** |
| std::length_error | **2** |
| std::bad_alloc | **3** |
| Insufficient capacity | **4** |
| Unexpected exception | **5** |
| Success | **0** |

No C++ exception is allowed to escape through exported C functions. With a third-party C++ library where you cannot control the destructor or custom allocator, review the contract before declaring noexcept; do not assume native code is always safe just because catch(...) is present.

## 8. Runnable Example — File CppBridgeDemo.java (JDK 22+)

Create the file **CppBridgeDemo.java**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class CppBridgeDemo {
    private static final int OK = 0;
    private static final int OUT_OF_RANGE = 2;
    private static final int BUFFER_TOO_SMALL = 4;

    private CppBridgeDemo() {
    }

    private static void expect(int actual, int expected) {
        if (actual != expected) {
            throw new IllegalStateException(
                "Native status " + actual +
                ", expected " + expected
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Library must outlive every C++ handle.
        try (Arena libraryArena = Arena.ofConfined()) {
            Path lib = Path.of(
                System.mapLibraryName("cppbridge")
            ).toAbsolutePath();

            SymbolLookup symbols =
                SymbolLookup.libraryLookup(lib, libraryArena);

            // int32_t bridge_create(const char*, int32_t, handle**)
            MethodHandle create = linker.downcallHandle(
                symbols.find("bridge_create").orElseThrow(),
                FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
                )
            );

            // int32_t bridge_render(handle*, int32_t,
            //                       char*, int32_t, int32_t*)
            MethodHandle render = linker.downcallHandle(
                symbols.find("bridge_render").orElseThrow(),
                FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
                )
            );

            MethodHandle release = linker.downcallHandle(
                symbols.find("bridge_release").orElseThrow(),
                FunctionDescriptor.ofVoid(
                    ValueLayout.ADDRESS
                )
            );

            MethodHandle active = linker.downcallHandle(
                symbols.find("bridge_active_handles").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            try (Arena arena = Arena.ofConfined()) {
                byte[] bytes = "Native++".getBytes(
                    StandardCharsets.UTF_8
                );

                // C needs a native pointer, does not read heap array directly.
                MemorySegment input = arena.allocate(bytes.length);
                input.copyFrom(MemorySegment.ofArray(bytes));

                // C++ writes bridge_handle* into a slot holding one ADDRESS.
                MemorySegment handleSlot =
                    arena.allocate(ValueLayout.ADDRESS);
                handleSlot.set(
                    ValueLayout.ADDRESS, 0, MemorySegment.NULL
                );

                int created = (int) create.invokeExact(
                    input, bytes.length, handleSlot
                );
                expect(created, OK);

                MemorySegment handle = handleSlot.get(
                    ValueLayout.ADDRESS, 0
                );
                if (handle.address() == 0L) {
                    throw new IllegalStateException("NULL handle");
                }

                // Java only uses opaque ADDRESS: do not reinterpret class.
                try {
                    int live = (int) active.invokeExact();

                    MemorySegment requiredSlot =
                        arena.allocate(ValueLayout.JAVA_INT);
                    requiredSlot.set(ValueLayout.JAVA_INT, 0, 0);

                    // Query actual byte count.
                    int query = (int) render.invokeExact(
                        handle, 2, MemorySegment.NULL,
                        0, requiredSlot
                    );
                    expect(query, BUFFER_TOO_SMALL);

                    int required = requiredSlot.get(
                        ValueLayout.JAVA_INT, 0
                    );
                    if (required <= 0 || required > 1024) {
                        throw new IllegalStateException(
                            "Output size unsupported: " + required
                        );
                    }

                    // Allocate Java-owned buffer; C only borrows during the call.
                    MemorySegment output = arena.allocate(required);
                    int copied = (int) render.invokeExact(
                        handle, 2, output, required, requiredSlot
                    );
                    expect(copied, OK);

                    int written = requiredSlot.get(
                        ValueLayout.JAVA_INT, 0
                    );
                    if (written != required) {
                        throw new IllegalStateException(
                            "Output length changed"
                        );
                    }

                    String result = new String(
                        output.toArray(ValueLayout.JAVA_BYTE),
                        StandardCharsets.UTF_8
                    );

                    // std::out_of_range in C++ -> status 2 in Java.
                    int bad = (int) render.invokeExact(
                        handle, 17, MemorySegment.NULL,
                        0, requiredSlot
                    );
                    expect(bad, OUT_OF_RANGE);

                    System.out.println("activeWhileOpen=" + live);
                    System.out.println("requiredBytes=" + required);
                    System.out.println("output=" + result);
                    System.out.println("outOfRangeStatus=" + bad);
                } finally {
                    // ONE Java owner performs ONE release.
                    release.invokeExact(handle);
                }

                int after = (int) active.invokeExact();
                System.out.println("activeAfterClose=" + after);
            }
        }
    }
}
~~~

**Reading the FunctionDescriptor:** Create takes ADDRESS (input), JAVA_INT (byte length), ADDRESS (pointer-to-pointer); render takes ADDRESS, JAVA_INT, ADDRESS, JAVA_INT, ADDRESS and returns JAVA_INT; release takes ADDRESS and returns void. No descriptor tries to model std::string.

**MemorySegment handle** is just an opaque native pointer; do not dereference it. **handleSlot** and **output/input** are allocated by the Java Arena, whereas **bridge_handle** is allocated by C++ new, so bridge_release is required in finally. The library arena must still be alive when release runs.

### A Detail About JNI

If the same wrapper is called from JNI instead of FFM, the JNI native method receives the right thread's JNIEnv and can convert the error code into a Java exception using JNI **ThrowNew** after the C++ wrapper returns. However, the JNI adapter must also not allow C++ exceptions to escape into the JVM. The bytes/length, opaque handle, and matching destructor contracts remain the same.

## 9. Compiling and Running

Prepare the three files in the same directory: **cpp_bridge.h**, **cpp_bridge.cpp**, **CppBridgeDemo.java**. JDK 22+ and a C++17 toolchain compatible with the OS/CPU/JVM are required.

**Linux:**

~~~bash
g++ -std=c++17 -O2 -fPIC -shared \
  cpp_bridge.cpp -o libcppbridge.so
~~~

**macOS:**

~~~bash
clang++ -std=c++17 -O2 -fPIC -dynamiclib \
  cpp_bridge.cpp -o libcppbridge.dylib
~~~

**Windows, MSVC Developer Command Prompt:**

~~~bat
cl /nologo /EHsc /std:c++17 /LD cpp_bridge.cpp /link /OUT:cppbridge.dll
~~~

Choose **one option** according to your OS. The library must be built for the same architecture as the running JDK. System.mapLibraryName("cppbridge") produces the exact filename for the corresponding OS.

After building:

~~~bash
javac CppBridgeDemo.java
java --enable-native-access=ALL-UNNAMED CppBridgeDemo
~~~

Because FFM uses restricted native calls/library lookup, the classpath demo enables **ALL-UNNAMED**. In a modularized application, grant native access to the specific module when possible.

**Exact expected stdout when building/loading and native calls succeed:**

~~~text
activeWhileOpen=1
requiredBytes=17
output=Native++|Native++
outOfRangeStatus=2
activeAfterClose=0
~~~

Explanation: **Native++** is eight ASCII bytes long; two copies with a **|** separator are 8+1+8=17 bytes. C++ creates one handle (counter=1), Java queries/copies the exact 17 bytes and then decodes them. When repeat=17, the wrapper catches std::out_of_range and returns status 2. Finally calls bridge_release exactly once (counter returns to 0).

**Verification scope:** The sample source and output have been reviewed against the contract, but still need to be built/tested on the target JDK/toolchain; illustrative stdout should not be taken as a result already run on every platform.

## 10. Lifetime and Allocator Bugs That Need Special Attention

### Do Not Free a C++ Object with Java Arena

Closing an Arena frees **input/output/handleSlot** allocated by the Arena; it **does not automatically delete a BridgeHandle** created by C++. The handle requires a matching bridge_release, even though Java only sees a MemorySegment ADDRESS.

### Do Not Call Release Twice

If two Java wrappers both hold a handle, each wrapper calling release can cause a **double-delete**. A single owner must take sole responsibility. Java can use AutoCloseable with state/locking if it wants to guard close, but **do not simultaneously** register a second cleanup action for the same handle.

### Do Not Unload the Library Before Release

A native MethodHandle points into the library's code. When SymbolLookup.libraryLookup ties the library lifetime to an Arena, the library may be unloaded when the arena closes. Therefore **libraryArena** must outlive the **C++ handle** and all bridge_release calls.

### Do Not Use a Handle After Close

An opaque address returned from C can still have the same long value after release, but the memory region has been deleted. **MemorySegment ADDRESS does not automatically know that the C++ object has been freed**; FFM cannot automatically prevent all use-after-free in native code.

### Do Not Release Concurrently with Render

The atomic counter in the demo does not make BridgeHandle thread-safe. If a worker is using the handle and another thread calls release, it can crash. Use an owner lifecycle: stop accepting calls, wait for in-flight calls to finish, and then release. If the C++ implementation is mutable, add mutex/synchronization according to the contract.

## 11. Unicode, Error Messages, and Production ABI

**Encoding:** std::string stores bytes and does not automatically validate UTF-8. Java should use explicit UTF-8; if the C API requires UTF-16 or locale-dependent encoding, create a dedicated adapter and document the contract. Embedded NUL should be tested because strlen loses data after NUL.

**Error messages:** Do not return a pointer to std::exception::what() after the exception object goes out of scope. If error details are needed, copy bytes into a caller-owned buffer or return an opaque error handle with a destroy function. A thread-local last-error message can be overwritten by the next call, so read it immediately and document the thread/overwrite contract.

**C ABI versioning:** When upgrading the library, do not silently change the number/types of parameters of an exported symbol. You can add a **bridge_api_version()** function or a new API for 64-bit sizes. For outputs larger than 2 GiB, int32_t capacity is insufficient: design a separate 64-bit protocol and check unsigned/range limits.

**Compiler and runtime:** A public C ABI reduces dependency on C++ object layout on the Java side, but the library itself and C++ dependencies still require a compatible compiler, standard library, and runtime. Each platform must be built/tested.

**Errors:** Converting a C++ exception into a status does not mean the root cause has been fixed. Java needs to map error codes into contextual exceptions/Results and have a monitoring process. If a custom allocator/driver requires thread-affine destruction, bridge_release must also be called on the appropriate thread.

**C++ callbacks:** If the C++ library invokes Java callbacks from native threads, you must manage the lifetime of the upcall stub/Arena and unregister/drain before closing. A Java upcall callback must not let a Java exception escape across the C ABI; catch and report errors according to the callback contract.

## 12. Common Mistakes Table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Exporting std::string by value in extern "C" | Exposes C++ ABI/allocator | Bytes + length or opaque handle |
| C++ exception crossing FFM/JNI | Crash/terminate/undefined behavior | noexcept + catch/status |
| Catch(...) returning OK | Hides errors | INTERNAL status/diagnostics |
| Creating an error message via allocation in bad_alloc handler | Can throw again | Status constant or pre-existing buffer |
| Returning local.c_str() | Dangling pointer | Copy to caller buffer |
| Keeping text.data() pointer then mutating text | Invalidation | Short borrowed contract or copy |
| Using String.length as UTF-8 byte length | Wrong capacity/overflow | Encode first then take byte[].length |
| Using strlen with data containing NUL | Truncated data | Explicit length |
| C memcpy without checking capacity | Buffer overflow | Query size + bounded copy |
| Java freeing a C++ new object with libc free | Wrong allocator, destructor does not run | Matching bridge_release |
| Attaching two cleanup paths to one handle | Double-free | Single owner |
| Java reading a C++ object via structLayout | Layout is not public/stable | Opaque handle |
| Closing library before handle | Function pointer already unloaded | Release before library close |
| Releasing concurrently with render | Native use-after-free | Stop/drain/lock |
| Query/copy while source changes | Length mismatch | Snapshot/version/bounded retry |
| Skipping OS/ABI build matrix | Load/symbol errors | Compile/test per target |

## 13. Pre-Production Checklist

- [ ] Public header is readable by a C compiler; does not expose STL/C++ classes.
- [ ] extern "C", exported symbols, and ABI are verified on the actual binary.
- [ ] FunctionDescriptor matches the exact C signature/return types.
- [ ] Every C ABI entry point catches C++ exceptions and does not throw across the boundary.
- [ ] Status/error semantics and outputs on error are explicitly documented.
- [ ] Strings crossing the boundary have encoding, byte length, NULL, and terminator policies.
- [ ] No pointer is returned to the buffer of a destroyed or mutable std::string.
- [ ] C++ keeps internal ownership via RAII, transferring only on success.
- [ ] A matching release function exists; Java does not mix allocators and does not double-release.
- [ ] Library outlives all handles/callbacks and cleanup operations.
- [ ] Two-pass query/copy checks capacity, integer overflow, and mutable data.
- [ ] Thread-safety, close races, and affinity are defined by the C++ contract.
- [ ] Tests cover empty input, embedded NUL, UTF-8, negative/out-of-range repeat, insufficient buffer, and allocation failure.
- [ ] Tests cover startup/shutdown, version compatibility, sanitizer/native heap diagnostics on target OS/CPU/JDK.
- [ ] Java exceptions are not used as a mechanism to catch native heap corruption.

## 14. Self-Check Questions

**1. Does extern "C" turn std::string into a standard C struct?**

No. It controls linkage, not the binary layout standardization of an STL type.

**2. Why must C++ exceptions be caught in the wrapper?**

Because C ABI/FFM has no contract to propagate a C++ exception into a Java Throwable; letting it escape can terminate/crash.

**3. If a C++ function creates an object with new, which function should Java call to clean it up?**

The **bridge_release** function published by the same library, not libc free directly.

**4. Why is byte count needed when passing UTF-8?**

Java String.length counts UTF-16 code units, not UTF-8 bytes; byte count also preserves embedded NULs.

**5. Why not return a pointer from a local std::string?**

It is destroyed after the function returns, so the pointer becomes dangling.

**6. What does two-pass query/copy require?**

Required length must be measured in bytes; the buffer must have sufficient capacity; source data must be stable or have an appropriate retry/snapshot mechanism.

**7. How is std::bad_alloc in C++ seen by Java in the example?**

The wrapper catches it and returns code **3 (BR_NO_MEMORY)**, without passing the C++ exception object across FFM.

**8. Why does finally need to release even if Java render throws an exception?**

Because handle ownership was already transferred when create succeeded; a subsequent error does not make C++ automatically delete the allocation.

**9. Does Arena.close automatically destroy a BridgeHandle created with new?**

No. Arena only owns allocations created by Arena; BridgeHandle requires a matching C++ release.

**10. When can a handle used by multiple workers be released?**

When new calls have stopped being accepted and all native consumers/in-flight calls are guaranteed to have completed according to the thread-safety contract.

## Official References

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- [Oracle Java 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle Java 22 — Linker / FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle Java 22 — SymbolLookup and shared library lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java 22 — MemorySegment (copy, scope, access)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [C++ language — Exceptions](https://en.cppreference.com/w/cpp/language/exceptions).
- [C++ basic_string reference](https://en.cppreference.com/w/cpp/string/basic_string).

**Conclusion:** **A C++ wrapper should keep exceptions, std::string, RAII, and allocators internal**, exposing only a C ABI with clear data types, status codes, byte buffers, and matching release. This design helps Java FFM/JNI avoid STL ABI dependencies, prevents C++ exceptions from escaping across the boundary, controls ownership, and reduces the risk of buffer overflow, double-free, leaks, or use-after-free.
