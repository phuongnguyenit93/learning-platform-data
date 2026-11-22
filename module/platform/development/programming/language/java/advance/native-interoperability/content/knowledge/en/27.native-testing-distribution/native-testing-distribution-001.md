# Creating a Small C Library to Demonstrate Data and Ownership Contracts

A native interoperability practice exercise should start with a **data contract** and an **ownership contract**. Java and C have different memory management models: Java has GC/Arena, while C has pointers, allocators, and its own free rules. Calling a C function successfully is not enough; we need to know exactly which bytes cross the boundary, who allocates, and who is allowed to release the memory region.

This article builds a real C library named **tinybridge**, with a public header, source code, native tests, CMake configuration, and a Java program using the **Foreign Function & Memory API (FFM)** from JDK 22. The example is intentionally small, processing only ASCII letters in a byte array; this makes it possible to clearly test behavior with NUL bytes and multi-byte UTF-8.

## 1. The Contract to Be Proven

The library exports three functions with a stable C ABI for a given interface version:

- **tiny_abi_version()** returns the contract version (starting from 1).
- **tiny_ascii_upper_copy(input, input_len, out_data, out_len)** receives a **borrowed byte region**, copies its contents into a **new region owned by C upon allocation**, converts ASCII letters a–z to A–Z, and then hands over the responsibility of freeing the result region to the caller.
- **tiny_free(data)** frees a region that was allocated by the library itself. The function accepts NULL.

Specific definition:

| Element | Contract |
| --- | --- |
| Data type | **uint8_t** array, **uint64_t** length in bytes; does not depend on a string-terminating character |
| Input | **const uint8_t*** pointer is **borrowed**; valid throughout the call; C does not retain it and does not free it |
| Output | **uint8_t*** stored in **out_data**; allocated by C with malloc, **the caller must call tiny_free exactly once** if a non-NULL pointer is received |
| Output length | Written to **out_len**; equals input_len on success |
| Success, empty input | Returns TINY_OK, out_data = NULL and out_len = 0 |
| Error | Returns TINY_EINVAL or TINY_ENOMEM; given two valid output slots, out_data = NULL and out_len = 0 |
| Output lifetime | Valid until tiny_free; after free, all pointers/views pointing to this region are invalid |
| Concurrency | Synchronous functions, retaining no pointers or global mutable state; callers must ensure input/output are not accessed improperly when shared |
| Versioning | Caller checks tiny_abi_version before assuming function signatures |

**Preconditions:** out_data and out_len must point to two **valid, writable, non-overlapping** memory slots; input must be readable for at least input_len bytes if input_len is greater than 0. C cannot check every corrupted pointer supplied by the caller. When output slots are NULL, the function returns an error without being able to initialize the missing slot.

Error code convention: **TINY_OK = 0**, **TINY_EINVAL = 1** (invalid parameter or length), and **TINY_ENOMEM = 2** (allocation failed). Do not throw exceptions across the C ABI boundary.

## 2. Minimal Project Structure

~~~text
tinybridge/
├── CMakeLists.txt
├── include/
│   └── tinybridge.h
├── src/
│   └── tinybridge.c
├── tests/
│   └── test_tinybridge.c
└── examples/
    └── TinyBridgeDemo.java
~~~

The **header + binary library** pair is the contract for Java, C, or other applications to call into. There is no need to expose internal structs, STL/C++ objects, or external allocator addresses.

## 3. Public Header: include/tinybridge.h

~~~c
#ifndef TINYBRIDGE_H
#define TINYBRIDGE_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(TINYBRIDGE_BUILD)
#    define TINY_API __declspec(dllexport)
#  else
#    define TINY_API __declspec(dllimport)
#  endif
#else
#  define TINY_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define TINY_ABI_VERSION 1u
#define TINY_OK      0
#define TINY_EINVAL  1
#define TINY_ENOMEM  2

TINY_API uint32_t tiny_abi_version(void);

/*
 * input: borrowed, readable for input_len bytes, not retained.
 * out_data and out_len: two valid, writable, nonoverlapping slots.
 * On success: output is a separately allocated copy; caller owns it.
 * On error: if both output slots are valid, sets *out_data=NULL,
 *           *out_len=0.
 * input_len==0 accepts input==NULL and returns empty output.
 */
TINY_API int tiny_ascii_upper_copy(
        const uint8_t *input,
        uint64_t input_len,
        uint8_t **out_data,
        uint64_t *out_len);

/* Release only output allocated by tinybridge; NULL is allowed. */
TINY_API void tiny_free(void *data);

#ifdef __cplusplus
}
#endif
#endif
~~~

**Why is it declared this way?**

1. **uint8_t** means byte/octet, **uint64_t** is a 64-bit length. For Java FFM, they correspond to byte contents, **JAVA_LONG** for the uint64_t parameter on common 64-bit ABIs, and **ADDRESS** for pointers. uint64_t values greater than Long.MAX_VALUE require special handling; the Java example below only passes a small array.
2. **const** for input explicitly states that C must not write to the borrowed data. It does not by itself protect the memory from being freed early by the caller.
3. **uint8_t \*\*out_data** and **uint64_t \*out_len** are the addresses of the two output slots; C writes the pointer value and length into them. They are distinct from the output buffer itself.
4. **extern "C"** keeps symbol names following the C ABI when the header is used by a C++ application, avoiding C++ name mangling.
5. **TINY_API** exports symbols from a DLL on Windows and sets visibility on Unix-like systems. The **TINYBRIDGE_BUILD** macro applies only when compiling the library; C/DLL import clients do not define this macro.
6. No Java objects, **std::string**, callbacks, or complex ABI structs are used. A small interface makes it easier to lock versions and test independently.

## 4. Implementation: src/tinybridge.c

~~~c
#include "tinybridge.h"

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

uint32_t tiny_abi_version(void) {
    return TINY_ABI_VERSION;
}

int tiny_ascii_upper_copy(const uint8_t *input, uint64_t input_len,
                          uint8_t **out_data, uint64_t *out_len) {
    if (out_data == NULL || out_len == NULL) {
        return TINY_EINVAL;
    }

    /* Both error and empty input have deterministic output. */
    *out_data = NULL;
    *out_len = 0;

    if (input_len != 0 && input == NULL) {
        return TINY_EINVAL;
    }
    if (input_len > (uint64_t) SIZE_MAX) {
        return TINY_EINVAL; /* Do not overflow when converting to size_t. */
    }
    if (input_len == 0) {
        return TINY_OK;
    }

    size_t n = (size_t) input_len;
    uint8_t *copy = malloc(n);
    if (copy == NULL) {
        return TINY_ENOMEM;
    }

    for (size_t i = 0; i < n; ++i) {
        uint8_t b = input[i];
        copy[i] = (b >= 'a' && b <= 'z')
                ? (uint8_t) (b - ('a' - 'A'))
                : b;
    }

    *out_data = copy;
    *out_len = input_len;
    return TINY_OK;
}

void tiny_free(void *data) {
    free(data);
}
~~~

**Where is the ownership proof?**

- The function only reads **input** while the call is running; it does not store the pointer in a global or an asynchronous request. Therefore, the caller can reclaim input **after the function returns** if there is no other consumer.
- When input_len > 0, **malloc(n)** creates a new region and copies each byte. **copy** does not alias the input region.
- On success, management of the output is transferred via **\*out_data**. C does not free it itself before returning the result; the Java/C caller must call **tiny_free** properly.
- When any valid error occurs, **\*out_data** and **\*out_len** have already been reset, preventing the caller from mistaking error data for real data.
- Empty input produces **NULL + 0**, avoiding dependence on malloc(0) behavior. **free(NULL)** is a valid operation in C.

The function only converts ASCII bytes from 0x61–0x7A to 0x41–0x5A. Non-ASCII UTF-8 (for example, the character é encoded as **C3 A9**) is preserved byte for byte. This is **not** a Unicode uppercasing algorithm; the function name reflects that limitation.

**Warning:** C does not have automatic bounds checking on pointers; a mismatched pointer/length pair can still cause out-of-bounds memory reads. FFM cannot automatically turn an arbitrary native address into a safe memory region.

## 5. Testing the Contract in C Before Calling from Java

**File: tests/test_tinybridge.c**

~~~c
#include "tinybridge.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    if (tiny_abi_version() != TINY_ABI_VERSION) {
        return 1;
    }

    /* Contains a NUL byte in the middle and two UTF-8 bytes for the letter é. */
    const uint8_t input[] = {'h', 'i', 0, 'a', 0xC3, 0xA9};
    const uint8_t want[]  = {'H', 'I', 0, 'A', 0xC3, 0xA9};

    uint8_t *out = NULL;
    uint64_t len = 99;
    int status = tiny_ascii_upper_copy(
            input, sizeof input, &out, &len);

    if (status != TINY_OK || out == NULL || len != sizeof want) {
        return 2;
    }

    int equal = memcmp(out, want, sizeof want) == 0;
    tiny_free(out); /* End the lifetime of the region allocated by the library. */
    if (!equal) {
        return 3;
    }

    /* Error: input is NULL while length > 0; output slots must be reset. */
    uint8_t marker = 42;
    out = &marker;
    len = 99;
    status = tiny_ascii_upper_copy(NULL, 3, &out, &len);
    if (status != TINY_EINVAL || out != NULL || len != 0) {
        return 4;
    }

    /* Valid empty input; return NULL/0 instead of a dummy region. */
    out = &marker;
    len = 99;
    status = tiny_ascii_upper_copy(NULL, 0, &out, &len);
    if (status != TINY_OK || out != NULL || len != 0) {
        return 5;
    }

    tiny_free(out); /* free(NULL) is valid. */
    puts("contract tests: OK");
    return 0;
}
~~~

The test actively checks **embedded NUL** (without using strlen), multi-byte UTF-8, empty input, invalid arguments, output initialization, and the release path. It returns a non-zero code when the contract is violated, so CTest recognizes a test failure. This test does not replace fuzzing, leak detection, or stress testing.

## 6. Building, Running Tests, and Creating a Distribution Package with CMake

**File: CMakeLists.txt**

~~~cmake
cmake_minimum_required(VERSION 3.16)
project(tinybridge VERSION 1.0.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_library(tinybridge SHARED src/tinybridge.c)
target_compile_definitions(tinybridge PRIVATE TINYBRIDGE_BUILD)
target_include_directories(tinybridge PUBLIC include)

add_executable(test_tinybridge tests/test_tinybridge.c)
target_link_libraries(test_tinybridge PRIVATE tinybridge)

enable_testing()
add_test(NAME tinybridge_contract COMMAND test_tinybridge)

install(TARGETS tinybridge
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib)
install(FILES include/tinybridge.h DESTINATION include)
~~~

In the **tinybridge/** root directory, using a machine with **CMake + C compiler**:

~~~bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
cmake --install build --config Debug --prefix stage
~~~

When tests pass, the C program prints:

~~~text
contract tests: OK
~~~

The binary name depends on the operating system and generator:

| System | Typical dynamic library |
| --- | --- |
| Linux | **libtinybridge.so** |
| macOS | **libtinybridge.dylib** |
| Windows | **tinybridge.dll**, usually under **build/Debug/** with Visual Studio |

CMake may place the binary in a different configuration directory; verify the actual path before Java loads it. The **install** step creates the package contents including the header and shared library (Windows may also include an import library **.lib** in **lib/**). When distributing, accompany it with a record of **ABI_VERSION**, operating system, CPU architecture (x86-64/arm64), compiler/runtime dependencies, and artifact version; do not assume a DLL/SO/DYLIB from one platform can be used directly on another.

Inspect symbols when needed: **nm -D** on Linux, **nm -g** or **otool** on macOS, **dumpbin /EXPORTS** on Windows/MSVC. The three names **tiny_abi_version**, **tiny_ascii_upper_copy**, and **tiny_free** must be clearly exported.

## 7. Java 22+: Calling the C Library with FFM and Freeing with the Right Owner

FFM is standardized in **java.lang.foreign** starting in Java 22. The program uses **SymbolLookup** to find symbols, **Linker** to create downcalls, and **Arena** to allocate the input region + two output slots. The actual output region is allocated by **C malloc**, and **does not belong to Java's Arena**.

**File: examples/TinyBridgeDemo.java**

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
import java.util.Arrays;

public class TinyBridgeDemo {
    private static MemorySegment requireSymbol(SymbolLookup lib, String name) {
        return lib.find(name).orElseThrow(
                () -> new IllegalStateException("Symbol missing: " + name));
    }

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass absolute library path");
        }

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup lib = SymbolLookup.libraryLookup(
                    Path.of(args[0]).toAbsolutePath(), arena);

            MethodHandle version = linker.downcallHandle(
                    requireSymbol(lib, "tiny_abi_version"),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));
            MethodHandle copy = linker.downcallHandle(
                    requireSymbol(lib, "tiny_ascii_upper_copy"),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
                            ValueLayout.ADDRESS, ValueLayout.ADDRESS));
            MethodHandle release = linker.downcallHandle(
                    requireSymbol(lib, "tiny_free"),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            int abi = (int) version.invokeExact();
            if (abi != 1) throw new IllegalStateException("Unsupported ABI: " + abi);

            byte[] src = ("hi" + (char) 0 + "aé")
                    .getBytes(StandardCharsets.UTF_8);
            MemorySegment input = arena.allocate(src.length);
            for (int i = 0; i < src.length; i++) {
                input.set(ValueLayout.JAVA_BYTE, i, src[i]);
            }

            MemorySegment outSlot = arena.allocate(ValueLayout.ADDRESS);
            MemorySegment lenSlot = arena.allocate(ValueLayout.JAVA_LONG);
            outSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            lenSlot.set(ValueLayout.JAVA_LONG, 0, 0L);

            int status = (int) copy.invokeExact(
                    input, (long) src.length, outSlot, lenSlot);
            MemorySegment owned = outSlot.get(ValueLayout.ADDRESS, 0);
            long size = lenSlot.get(ValueLayout.JAVA_LONG, 0);

            try {
                if (status != 0) {
                    throw new IllegalStateException("Native status: " + status);
                }
                if (size < 0 || size > Integer.MAX_VALUE
                        || (size > 0 && owned.address() == 0)) {
                    throw new IllegalStateException("Invalid result pointer/length");
                }

                byte[] result = size == 0 ? new byte[0]
                        : owned.reinterpret(size).toArray(ValueLayout.JAVA_BYTE);
                byte[] expected = ("HI" + (char) 0 + "Aé")
                        .getBytes(StandardCharsets.UTF_8);
                if (!Arrays.equals(result, expected)) {
                    throw new AssertionError("Unexpected native output");
                }

                System.out.println("ABI=" + abi);
                System.out.println("input=" + Arrays.toString(src));
                System.out.println("output=" + Arrays.toString(result));
                System.out.println("text=" + new String(result, StandardCharsets.UTF_8)
                        .replace(String.valueOf((char) 0), "<NUL>"));
            } finally {
                release.invokeExact(owned);
            }
        }
    }
}
~~~

After building the library with CMake, compile Java from the project root directory:

~~~bash
javac examples/TinyBridgeDemo.java
~~~

On Linux, when the library has the standard path **build/libtinybridge.so**:

~~~bash
java --enable-native-access=ALL-UNNAMED -cp examples TinyBridgeDemo "$PWD/build/libtinybridge.so"
~~~

On macOS, replace the **.so** extension with **.dylib**. On Windows PowerShell with the Visual Studio generator:

~~~powershell
$lib = (Resolve-Path .\build\Debug\tinybridge.dll).Path
java --enable-native-access=ALL-UNNAMED -cp examples TinyBridgeDemo $lib
~~~

The input data carries a NUL byte in the middle and the character é. With the corresponding build running successfully, stdout should be:

~~~text
ABI=1
input=[104, 105, 0, 97, -61, -87]
output=[72, 73, 0, 65, -61, -87]
text=HI<NUL>Aé
~~~

**Explanation of the key lines:**

- **Arena** keeps the input and output slots alive within the scope of the call. **Arena.ofConfined()** is appropriate because the program calls native synchronously on the same Java thread.
- **ValueLayout.ADDRESS** corresponds to a pointer. The **outSlot** slot holds the address of the output returned by C; the **lenSlot** slot holds the byte count. **JAVA_LONG** corresponds to the **uint64_t** parameter/slot on the chosen 64-bit target.
- The output pointer returned from the downcall has a segment with size 0; only **after checking length/pointer** does Java use **reinterpret(size)** to create a view covering all bytes. Reinterpret is a sensitive operation: if C returns an invalid pointer or length, the JVM can crash.
- **toArray(JAVA_BYTE)** copies bytes into the Java heap. After the copy operation, the Java array has a lifetime independent of the C region. If you want to keep a zero-copy view, you must keep the native output alive until the last access.
- **release.invokeExact(owned)** is placed in **finally**, matching the library's allocator/free pair, even if checking the result or processing the output throws an error. **tiny_free(NULL)** is valid.
- Closing the Java Arena only frees the regions allocated by the Arena; it **does not** replace **tiny_free(owned)** for C malloc. At the same time, you must ensure no symbol is called after the Arena used for library lookup has been closed.

FFM downcalls are restricted native access; use **--enable-native-access=ALL-UNNAMED** for applications on the classpath. Java 22+ requires native access permission rules appropriate for the JVM version; if moving to a named module, grant permission to that module name.

## 8. Ownership Diagram of the Example

~~~text
Java creates input (Arena) ---------- borrowed ----------> C reads input
       |                                                        |
       |                                                malloc(output)
       |                                                        |
       +-- outSlot / lenSlot <--------- pointer + length -------+
                   |
          Java validates data
                   |
            copy to byte[]
                   |
      tiny_free(pointer) ----------> C free(output), exactly once
                   |
             close Arena
~~~

Note that there are **two distinct memory levels**: **outSlot** (which holds the address value, allocated by Java Arena) and **output** (the actual byte region, allocated by C malloc). Do not free the address of **outSlot** with tiny_free; also do not close the Arena and then continue accessing **outSlot**.

Ownership does not transfer automatically by C pointer syntax. The header contract and function documentation are what specify which side is allowed to release.

## 9. Variants That Need Clear Decisions When Extending the Library

| API Type | Who owns the memory? | When can it be released? |
| --- | --- | --- |
| **Borrowed input** | Caller | After the synchronous function returns; if native retains the pointer for async processing, must wait for actual completion |
| **Owned output** as in the example | Caller receives cleanup responsibility; allocator belongs to C | Once reading/copying is done and no views/callbacks are using it |
| **Borrowed output** | Library or owner object | Must not call tiny_free yourself; only use up to the point specified by the library |
| **Caller-allocated output** | Caller allocates and manages | After native finishes writing; API must have capacity, actual length, and error code when insufficient |
| **Opaque native handle** | Specified by the library's create/destroy | Call dedicated destroy after operations using the handle have finished |
| **Transferred input** | Native receives ownership per API | Caller must not free itself after successful transfer; must describe handling when transfer fails |

If adding a function that returns **const char*** pointing to a static string, explicitly document that it is a **borrowed pointer**, read-only for the caller, and must not be freed; include length or NUL termination rules. If adding an API that accepts a string, you must clearly specify **UTF-8/UTF-16/locale**, whether NUL is allowed, whether length is in bytes or code points, who owns the terminator, and whether normalization is performed.

If adding a C struct to the ABI, avoid guessing Java padding/alignment from field order. Use **sizeof**, **offsetof**, and the appropriate MemoryLayout for each platform; test on 64-bit targets as well. Do not expose C++ internals or APIs based on compiler-specific object layouts when aiming for a broad ABI.

## 10. Common Bugs and How to Detect Them

1. **Calling free() from Java/JNA on memory allocated by a DLL**: risk of using the wrong runtime allocator, especially on Windows where there are multiple CRTs/heaps. Use the release function exported by the library.
2. **Closing Arena instead of calling tiny_free**: the C malloc region leaks. The two allocators have independent lifetimes.
3. **tiny_free(input)**: borrowed input is not a C-allocated region, which can cause heap corruption.
4. **Double-freeing output**: the second release leads to undefined behavior. Only one owner is responsible for cleanup; place cleanup in a single finally path.
5. **Keeping a MemorySegment view after tiny_free**: a view pointing to a raw address can become a dangling pointer; copy into the Java heap if the data must live longer.
6. **Using strlen for binary buffers**: a NUL byte in the middle of the array causes data loss. Use an explicit length as in the demo.
7. **Confusing ASCII uppercase with Unicode uppercase**: the letter é is kept unchanged; a Unicode algorithm requires a different library and contract.
8. **Reading output even when status reports an error**: output is invalid; must check status, pointer, and length before reading.
9. **Not stabilizing the ABI**: updating a function signature while Java still uses the old descriptor can corrupt the stack or memory. Check versions, maintain compatibility, or bump the version.
10. **Wrong architecture/library path**: a 64-bit JVM cannot load a native binary for the wrong CPU/OS; the distribution configuration must include the corresponding variant.
11. **Switching to async while still freeing input immediately after submit**: C continues to hold the pointer, leading to use-after-free. Must have a handle/request + completion/quiescence, clarifying owner and release timing from the start.

## 11. Applicable Testing and Distribution Checklist

**Contract tests:** test success, empty length, contract-violating NULL input, NULL output, data containing NUL, non-ASCII bytes, large data, simulated allocation failure, free(NULL), and multiple consecutive calls. Test error paths to ensure no allocated pointers are lost.

**Tooling:** enable compiler warnings (**-Wall -Wextra -Wpedantic** for GCC/Clang, **/W4** for MSVC) and consider AddressSanitizer/UndefinedBehaviorSanitizer in supported builds. Run memory leak checks and multi-threaded stress tests if the API allows concurrent calls. Verify symbol exports and binary dependencies.

**Cross-language tests:** Java tests ABI version mismatch, function lookup failure, UTF-8 Unicode input, embedded NUL, output length, and especially cleanup in finally. Run on every OS/CPU that the package claims to support. A successful Java compilation **does not prove** that the C library builds, loads, or runs correctly on another machine.

**Distribution:** package **tinybridge.h**, the right native binary per platform, document ABI/architecture/dependencies, license, loading instructions, and the ownership table in section 1. Run CTest and Java integration tests on the actual artifact before releasing; avoid testing only a C source build that differs from the packaged binary.

**Extension exercise:** add **tiny_copy_to_buffer(input, len, output, capacity, written)** so the caller owns the output. Define behavior when capacity is insufficient: return an error code, write **written** according to a consistent convention, and never write past capacity. Compare distributing this API with the owned-output **tiny_ascii_upper_copy**.

## 12. Key Takeaways

A small native library must still fully answer four questions: **which bytes cross**, **who allocates**, **who is allowed to release**, and **how long the resource lives**. In the example, Java lends input to C in a synchronous downcall; C creates a separate output and transfers cleanup responsibility to Java; Java copies the result and then asks C itself to free the output via tiny_free. Unit tests, FFM integration tests, and ABI versioning make that contract verifiable during build and distribution.

### References

- Oracle Java SE 22, FFM API: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html
- Dev.java, native memory with Arena/MemorySegment: https://dev.java/learn/api/io/ffm/access-memory/
- CMake, add_library / install / enable_testing: https://cmake.org/cmake/help/latest/
- ISO C, malloc/free and pointer/size contracts: refer to the stdlib.h section in the C11 documentation of the compiler and platform SDK in use.
