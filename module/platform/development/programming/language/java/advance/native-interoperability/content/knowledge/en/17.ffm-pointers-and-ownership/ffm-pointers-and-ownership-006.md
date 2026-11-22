# Pointers and Ownership — Handling Output Parameters, Double Pointers, and Library-Filled Buffers

## 1. Why can't output parameters be handled like regular Java values?

In Java, when calling a method that returns `int`, the result is usually in the `return` value. Many C libraries instead use **output parameters**: the function returns a status code, while the actual value is written through an address passed in by the caller.

Three very common C patterns:

```c
// [out] Integer value: caller passes the address of an int slot.
int get_answer(int *out);

// [out] Pointer: caller passes the address of a pointer variable.
int create_payload(unsigned char **out_data, size_t *out_count);

// [out] Caller-allocated buffer: library writes into a provided byte range.
int fill_message(char *buffer, size_t capacity, size_t *required);
```

If you only read the **return value** of the functions above, Java will miss the result. With the Foreign Function & Memory (FFM) API, Java must allocate a `MemorySegment` of the right size/alignment, pass the **native address of the segment** to C, invoke the `MethodHandle`, and then read the bytes written by C.

The most important point: **knowing which address C wrote is not enough; you must know who owns the memory that address points to, what the valid size is, and when it must be freed.** Confusing ownership can lead to memory leaks, double-free, use-after-free, or crashing the entire JVM.

This article is based on the **official FFM in JDK 22+** (JEP 454). Examples were tested with **OpenJDK 24**. In JDK 21, FFM is still a preview API (JEP 442), requires `--enable-preview`, and some API names may differ; do not apply the entire JDK 22+ source directly to JDK 21 without cross-checking.

## 2. Distinguishing `T*`, `T**`, and buffers

### 2.1. Parameters of the form `int *out`

```c
int read_value(int *out) {
    if (out == NULL) return -1;
    *out = 42; // Write into the memory slot allocated by the caller.
    return 0;
}
```

When called, C receives an **address of an `int` slot**. The caller still owns the memory slot. In Java FFM:

```java
MemorySegment out = arena.allocate(ValueLayout.JAVA_INT);
int status = (int) readValue.invokeExact(out);
if (status != 0) throw new IllegalStateException("Native call failed");
int value = out.get(ValueLayout.JAVA_INT, 0); // 42
```

This is an illustrative snippet, assuming an `arena` and an ABI-correct `MethodHandle readValue` already exist. `int*` **is described by `ValueLayout.ADDRESS` in the FunctionDescriptor**, because the parameter received is a pointer; separately, the memory slot is allocated with `JAVA_INT`.

### 2.2. Parameters of the form `char **out` or `T **out`

```c
int get_label(const char **out) {
    static const char label[] = "ready";
    if (out == NULL) return -1;
    *out = label; // Write an ADDRESS into the memory slot provided by the caller.
    return 0;
}
```

Here there are **two levels**:

```text
Java/C caller
   │
   └──► slot holding pointer (address of char* variable)
                    │  library writes *out = some_address
                    ▼
              address of a data region
                    │
                    └──► bytes/characters owned or borrowed by the library
```

In Java FFM, allocate **an ADDRESS-typed slot**, and **not** just `JAVA_BYTE`:

```java
MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
pointerSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
int rc = (int) getLabel.invokeExact(pointerSlot);
MemorySegment resultAddress = pointerSlot.get(ValueLayout.ADDRESS, 0);
```

The snippet only explains the mechanism: `getLabel` must be linked with the appropriate C signature before running. `resultAddress` is a pointer pointing to the **target data**, not a copy of the data. That data may be **borrowed/static**, **caller-owned**, or **newly allocated/native-owned**; how to free it depends on the API contract, and cannot be inferred from the two asterisks `**`.

### 2.3. Parameters of the form `char *buf, size_t cap`

```c
int fill_message(char *buf, size_t cap, size_t *required);
```

The library is allowed to write at most `cap` bytes into the memory provided by the caller. `required` may be the number of bytes actually written, or the required size, **depending on the library specification**. You must read the contract carefully: is the size measured in **bytes**, elements, UTF-16 code units, and does it include the trailing NUL byte?

```text
Java allocates 6-byte buf: [_ _ _ _ _ _]
                   │
           fill_message(buf, 6, &required)
                   │
                   ▼
                   ['h' 'e' 'l' 'l' 'o' '\0']
                                         ↑
                               NUL terminating the C string
```

In this pattern, the memory belongs to **Java's Arena**. Native code **only writes**, must not `free(buf)`, and must not retain `buf` after Java closes the arena, unless the API publishes an explicit pointer-retention protocol.

## 3. C ABI ↔ Java FFM Mapping Table

| C declaration | Meaning | Layout or memory on the Java side |
| --- | --- | --- |
| `int` | 32-bit integer on the example ABI | `ValueLayout.JAVA_INT` |
| `int *out` | Address of caller-allocated 32-bit integer slot | Parameter `ValueLayout.ADDRESS`; allocate slot `arena.allocate(JAVA_INT)` |
| `char *dst` | Address of byte sequence | Parameter `ADDRESS`; allocate buffer by **byte capacity** |
| `char **out` | Address of slot holding a pointer | Parameter `ADDRESS`; allocate slot `arena.allocate(ADDRESS)` |
| `void **out` | Address of slot holding an untyped pointer | `ADDRESS` + `ADDRESS` slot; need to know target type/size before dereferencing |
| `size_t` | Unsigned size, ABI-dependent | **X64 in this article:** 64-bit `JAVA_LONG`; verify ABI when porting |
| `size_t *len` | Address of length slot | Parameter `ADDRESS`; allocate `JAVA_LONG` slot on x64 |
| `const char *input` | Input string/bytes, usually borrowed | `arena.allocateFrom("text")` creates a UTF-8 C string on JDK 22+ |
| `wchar_t *output` on Windows | UTF-16 character buffer filled by Windows | `JAVA_CHAR` 2 bytes × number of **UTF-16 code units** |

The two columns “parameter layout” and “layout of pointed-to data” are **different**. For example, `int*` has FFM parameter `ADDRESS`, but the segment it points to must have at least `JAVA_INT.byteSize()` bytes. `T**` is `ADDRESS` in `FunctionDescriptor`, but the **slot** needs `ADDRESS.byteSize()` bytes and proper alignment.

**Regarding platform ABI:** on **Windows x64 (LLP64)**, C `long` is only **32 bits** wide, even though pointers and `size_t` are 64 bits wide. On **Linux x86-64 (LP64)**, `long` and `size_t` are usually both 64 bits. Therefore, you must not mechanically map `C long = Java long` across all OSes. In the Windows `strtol` example below, C `long` is mapped with `JAVA_INT`; whereas `size_t` in the x64 C library in section 8 is mapped with `JAVA_LONG`.

Pointers in FFM are `MemorySegment` carriers when invoking a downcall. `ValueLayout.ADDRESS.byteSize()` indicates the **pointer width of the environment**, not the size of the target data. `MemorySegment.NULL` represents the null address. Do not cast an arbitrary machine address into valid memory on your own.

## 4. Reading `T**`: slots, returned pointers, and zero-length segments

The easiest point to get wrong is:

```java
MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

// Native code receives slot to do *out = pointer;
MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
```

`pointer` is the **address value** written by native code. By the FFM contract, a pointer read from a regular `ADDRESS` slot is represented as a **zero-length memory segment**, i.e., `pointer.byteSize() == 0`. It does not carry built-in information about size or ownership. Calling `pointer.get(JAVA_BYTE, 0)` on a zero-length segment will be blocked as out of bounds.

If the **library has a contract guaranteeing** the pointer points to a valid region of `n` bytes, you can use:

```java
// Only safe once NULL, size, lifetime, and ABI are verified.
MemorySegment view = pointer.reinterpret(n);
```

**`reinterpret` is a dangerous restricted API:** it only changes the size that Java allows accessing; it **does not reallocate**, **cannot verify how many bytes native actually allocated**, **does not extend the lifetime** of the target object, and **does not automatically call free**. Specifying the wrong `n` can read/write out of bounds, corrupt memory, or crash the JVM. When using this API, you must have the appropriate `--enable-native-access`, follow the C contract, and have a separate cleanup mechanism.

If the pointer returned by native is only **borrowed from a live Java-owned region**, a better approach is not to `reinterpret`. For example, `strtol` sets `endptr` to point **inside the input string**; compute the **byte offset**, verify the offset lies within the input segment, and read from the **original segment** still controlled by the Arena. This approach leverages known bounds/lifetime.

## 5. Complete demo running on Windows x64: out-parameter, `char**`, and buffer

This example **does not need a C compiler**, because it calls native functions built into Windows:

1. `msvcrt.dll!strtol(const char*, char**, int)`: takes `char** endptr` and writes a **borrowed pointer** into the input string.
2. `kernel32.dll!MultiByteToWideChar(...)`: takes a **caller-owned wide-character output buffer**; has a size-querying mode first.
3. `kernel32.dll!GetComputerNameW(wchar_t*, DWORD*)`: takes an **output buffer** and an **in/out length slot**.

All use **Java 22+ FFM**, compiled and run on **OpenJDK 24.0.2 / Windows 64-bit**. The example reads addresses and buffers, without depending on the computer name content in the printed output.

### 5.1. File `OutPointerWindowsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class OutPointerWindowsDemo {
    private static MethodHandle link(Linker linker, SymbolLookup library,
                                     String symbol, FunctionDescriptor descriptor) {
        return linker.downcallHandle(library.findOrThrow(symbol), descriptor);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup crt = SymbolLookup.libraryLookup("msvcrt.dll", arena);
            SymbolLookup kernel = SymbolLookup.libraryLookup("kernel32.dll", arena);

            // C: long strtol(const char *s, char **endptr, int base);
            // Windows x64: C long = 32 bit.
            MethodHandle strtol = link(linker, crt, "strtol",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

            MemorySegment text = arena.allocateFrom("123tail");
            MemorySegment endSlot = arena.allocate(ValueLayout.ADDRESS);
            endSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

            int number = (int) strtol.invokeExact(text, endSlot, 10);
            MemorySegment end = endSlot.get(ValueLayout.ADDRESS, 0);

            // end is a borrowed pointer inside text, must not be free()d.
            long offset = end.address() - text.address();
            if (offset < 0 || offset >= text.byteSize()) {
                throw new IllegalStateException("Invalid strtol end pointer");
            }
            System.out.println("parsed: " + number);
            System.out.println("suffix: " + text.getString(offset));

            // Windows: int MultiByteToWideChar(
            //   UINT cp, DWORD flags, LPCCH src, int srcLen,
            //   LPWSTR dst, int dstChars);
            MethodHandle toWide = link(linker, kernel, "MultiByteToWideChar",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

            MemorySegment input = arena.allocateFrom("hello");
            // cbMultiByte = 5 => DOES NOT include trailing NUL byte.
            int needed = (int) toWide.invokeExact(
                65001, 0, input, 5, MemorySegment.NULL, 0);
            if (needed <= 0) {
                throw new IllegalStateException("MultiByteToWideChar sizing failed");
            }

            // WCHAR on Windows = 2-byte UTF-16.
            MemorySegment output = arena.allocate(
                needed * 2L, ValueLayout.JAVA_CHAR.byteAlignment());
            int written = (int) toWide.invokeExact(
                65001, 0, input, 5, output, needed);
            if (written != needed) {
                throw new IllegalStateException("MultiByteToWideChar conversion failed");
            }

            StringBuilder buffer = new StringBuilder();
            for (int i = 0; i < written; i++) {
                buffer.append(output.getAtIndex(ValueLayout.JAVA_CHAR, i));
            }
            System.out.println("buffer: " + buffer);

            // Windows: BOOL GetComputerNameW(LPWSTR buffer, LPDWORD inoutSize);
            MethodHandle getName = link(linker, kernel, "GetComputerNameW",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS));

            MemorySegment name = arena.allocate(
                256L * 2, ValueLayout.JAVA_CHAR.byteAlignment());
            MemorySegment inOutLength = arena.allocate(ValueLayout.JAVA_INT);

            // nSize input is capacity in WCHARs, NOT bytes.
            inOutLength.set(ValueLayout.JAVA_INT, 0, 256);
            int success = (int) getName.invokeExact(name, inOutLength);
            if (success == 0) {
                throw new IllegalStateException("GetComputerNameW failed");
            }

            // On success, nSize output excludes trailing NUL.
            int chars = inOutLength.get(ValueLayout.JAVA_INT, 0);
            System.out.println("inout length valid: " + (chars > 0 && chars <= 256));
        }
    }
}
```

### 5.2. Compile and run

On Windows 64-bit with **JDK 22 or later** (for example, tested on JDK 24):

```powershell
javac -encoding UTF-8 OutPointerWindowsDemo.java
java --enable-native-access=ALL-UNNAMED OutPointerWindowsDemo
```

**Actual verified stdout:**

```text
parsed: 123
suffix: tail
buffer: hello
inout length valid: true
```

Every `linker.downcallHandle`/`SymbolLookup.libraryLookup` call invokes restricted FFM operations inside a program **without a module name** (classpath). `--enable-native-access=ALL-UNNAMED` permits those restricted methods. In JDK 22+, FFM is final, so `--enable-preview` is not needed **just to use FFM**. If using a named Java module, grant native-access to the specific module instead of `ALL-UNNAMED`.

### 5.3. Decoding each ownership pattern in the output

**`strtol` and `endptr`:** `endSlot` is memory **owned by Java's Arena** to hold an address. `strtol` writes into the slot the address of the first `'t'` character in the string `"123tail"`. `end.address() - text.address() == 3` (in bytes). Since bounds were checked on `text`, Java reads the tail `text.getString(3)` which is `tail`.

The pointer `end` is a **borrowed pointer** pointing into `text`'s region. **Do not call `free(end)`**, because it is not a separately `malloc`'d block; it becomes invalid when the arena closes or `text` is no longer valid. In the example, all operations with `end` complete before exiting `try`.

**`MultiByteToWideChar` and buffer:** The call with output as `MemorySegment.NULL` and `dstChars=0` queries the number of **UTF-16 code units** required. Java allocates exactly `needed*2` bytes and lets native write into it. When `cbMultiByte=5`, the output string **does not automatically have a trailing NUL**, because the input length excludes the NUL byte. Therefore, Java reads **exactly `written` characters**, without using `getString` or scanning indefinitely for a terminator. With the string `hello`, the result is `buffer: hello`.

**`GetComputerNameW` and input/output length:** `inOutLength` is a `DWORD*` slot that is **both input and output**. Before the call, Java writes the number of `WCHAR` slots the buffer holds (256), **not 512 bytes**. After success, native writes the actual number of characters **excluding NUL**. The computer name varies by system, so the demo only prints the valid-size condition, avoiding exposing the computer name or depending on the environment. If the buffer is too small, the API reports an error and has a rule for returning the required size; do not read the buffer as if it were filled successfully.

### 5.4. Platform constraints of the demo

- `strtol` is a CRT function; on Windows x64 `long` is **32 bits**, so mapping the return to `JAVA_INT` is correct. On Linux x86-64, C `long` is **64 bits**, requiring mapping `JAVA_LONG` and looking up the function from the corresponding C library.
- `GetComputerNameW` and `MultiByteToWideChar` are **Win32 APIs**, not available on macOS/Linux. Windows `WCHAR` is 2-byte UTF-16, different from `wchar_t` on many POSIX systems.
- `MultiByteToWideChar` requires `cchWideChar` measured in **WCHAR characters**, not bytes. `GetComputerNameW` has its own rules regarding NUL and size; do not apply this function's contract to every other function.
- Before porting, check the **C header**, calling convention, ABI, alignment, C string encoding, and return semantics. Getting a single FFM descriptor wrong can crash the JVM, not just throw a Java exception.

## 6. Case where `T**` returns library-allocated memory

The `strtol` pattern above has `char**` but only returns a **borrowed pointer**. Another API may allocate memory and write the new address into `T**`:

```c
int create_payload(unsigned char **out_bytes, size_t *out_count);
void release_payload(unsigned char *ptr);
```

Example contract:

1. The caller allocates two slots: one to hold the `unsigned char*` address, one to hold the `size_t` length.
2. Native code writes `*out_bytes = malloc(...)` and `*out_count = n` on success.
3. On success, **ownership of the newly malloc'd block transfers to the caller**. Java must call `release_payload(ptr)` exactly once, even if processing the data throws an exception.
4. On error return, the library sets `*out_bytes = NULL` and `*out_count = 0`; the caller must not dereference the pointer.
5. The slot holding the pointer and the slot holding the size remain **Java-owned Arena memory**. They are distinct from the **native-owned block** pointed to by the pointer.

This is why **two types that are both `char**` have completely different cleanup**: `strtol` returns a pointer into the input string (do not free); `create_payload` returns a `malloc`'d block (must be freed using the library's function). Ownership comes from the **documentation/API contract**, not from the `T**` type.

## 7. Standalone sample C library: `int*`, buffer, and `unsigned char**`

Below is a small C library to clearly show the native side actually writing to out parameters. It does not depend on Win32 APIs; it can be built on **Linux x86-64, macOS 64-bit, or Windows x64** with the corresponding compiler.

### 7.1. Source `outdemo.c`

```c
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

// int*: caller owns one int slot.
EXPORT int get_answer(int *out_value) {
    if (out_value == NULL) return -1;
    *out_value = 42;
    return 0;
}

// char* buffer + size_t* required: caller owns the buffer.
// required counts ALL bytes including trailing NUL.
EXPORT int fill_message(char *buffer, size_t capacity, size_t *required) {
    static const char message[] = "hello"; // sizeof == 6
    if (required == NULL) return -1;

    *required = sizeof(message);
    if (buffer == NULL || capacity < sizeof(message)) {
        return 1; // Need more space; no buffer write.
    }

    memcpy(buffer, message, sizeof(message));
    return 0;
}

// unsigned char**: native allocates, then TRANSFERS block ownership.
EXPORT int create_payload(unsigned char **out_bytes, size_t *out_count) {
    if (out_bytes == NULL || out_count == NULL) return -1;
    *out_bytes = NULL;
    *out_count = 0;

    unsigned char *p = (unsigned char *) malloc(4);
    if (p == NULL) return -2;

    p[0] = 10;
    p[1] = 20;
    p[2] = 30;
    p[3] = 40;
    *out_bytes = p;
    *out_count = 4;
    return 0;
}

// Must be called exactly once for each successful create_payload().
EXPORT void release_payload(unsigned char *p) {
    free(p);
}
```

The functions use the **C ABI**, avoiding C++ name mangling; `EXPORT` exports symbols when building a DLL with MSVC. If the source code is compiled as C++ instead of C, you must adjust the declarations with `extern "C"` so symbol names are compatible with `SymbolLookup.find`.

**Error statuses:** `0` is success; `1` from `fill_message` means **insufficient buffer** and `*required` holds the required capacity; negative values mean invalid input or allocation failure. That is the contract **of this example**, not a universal rule for C libraries.

**Regarding strings:** `sizeof(message)` includes the trailing `'\0'` byte, so `required=6`; C only writes when the buffer has at least `6` bytes. Do not call `strcpy` into a buffer of unknown size or forget room for the terminator.

### 7.2. Build the native library

Linux x86-64 with GCC (command from the directory containing `outdemo.c`):

```bash
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -o liboutdemo.so outdemo.c
```

macOS 64-bit with Clang:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -o liboutdemo.dylib outdemo.c
```

Windows x64 in **Visual Studio Developer PowerShell / Developer Command Prompt** with MSVC:

```powershell
cl /LD /W4 outdemo.c /link /OUT:outdemo.dll
```

These three commands are **per-toolchain** choices, not all run on the same machine. The Java application below uses `System.mapLibraryName("outdemo")` to select the library name for the operating system. **The C and Java FFM source of the sample library has been reviewed; the C code has not been built/run in this Windows test environment because there is no C compiler in PATH.** Section 5 is the FFM example that was actually run without a C compiler.

## 8. Java FFM calling the sample C library and cleaning up a native-owned pointer

The following program is standalone, uses **JDK 22+**, and assumes you have built `liboutdemo.so`, `liboutdemo.dylib`, or `outdemo.dll` for your OS and placed it in the **current directory**. For simplicity, the illustration targets only a **64-bit ABI**, where `size_t` is 8 bytes wide. Run `java` with the native-access flag because it uses restricted FFM methods.

### 8.1. Source `OutParamsDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class OutParamsDemo {
    private static MethodHandle bind(Linker linker, SymbolLookup library,
                                     String symbol, FunctionDescriptor desc) {
        return linker.downcallHandle(library.findOrThrow(symbol), desc);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        try (Arena arena = Arena.ofConfined()) {
            Path path = Path.of(System.mapLibraryName("outdemo"))
                            .toAbsolutePath();
            SymbolLookup library = SymbolLookup.libraryLookup(path, arena);

            MethodHandle answer = bind(linker, library, "get_answer",
                FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS));
            MethodHandle fill = bind(linker, library, "fill_message",
                FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS,
                    ValueLayout.JAVA_LONG, ValueLayout.ADDRESS));
            MethodHandle make = bind(linker, library, "create_payload",
                FunctionDescriptor.of(ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS, ValueLayout.ADDRESS));
            MethodHandle release = bind(linker, library, "release_payload",
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            // A) int *out: allocate slot then read the value written by native.
            MemorySegment outInt = arena.allocate(ValueLayout.JAVA_INT);
            int rc = (int) answer.invokeExact(outInt);
            if (rc != 0) {
                throw new IllegalStateException("get_answer status=" + rc);
            }
            System.out.println("answer: "
                + outInt.get(ValueLayout.JAVA_INT, 0));

            // B) char *buffer, size_t capacity, size_t *required:
            //    first call queries size; second call allocates buffer with exact byte count.
            MemorySegment requiredSlot = arena.allocate(ValueLayout.JAVA_LONG);
            requiredSlot.set(ValueLayout.JAVA_LONG, 0, 0L);
            rc = (int) fill.invokeExact(
                MemorySegment.NULL, 0L, requiredSlot);
            if (rc != 1) {
                throw new IllegalStateException("size query status=" + rc);
            }
            long capacity = requiredSlot.get(ValueLayout.JAVA_LONG, 0);
            if (capacity < 1 || capacity > 1024) {
                throw new IllegalStateException("Invalid native buffer size");
            }

            MemorySegment buffer = arena.allocate(capacity);
            rc = (int) fill.invokeExact(buffer, capacity, requiredSlot);
            if (rc != 0) {
                throw new IllegalStateException("fill_message status=" + rc);
            }
            System.out.println("buffer: " + buffer.getString(0));

            // C) T**: slot holding pointer + slot holding length.
            MemorySegment pointerSlot = arena.allocate(ValueLayout.ADDRESS);
            MemorySegment lengthSlot = arena.allocate(ValueLayout.JAVA_LONG);
            pointerSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            lengthSlot.set(ValueLayout.JAVA_LONG, 0, 0L);
            rc = (int) make.invokeExact(pointerSlot, lengthSlot);
            if (rc != 0) {
                throw new IllegalStateException("create_payload status=" + rc);
            }

            MemorySegment nativePointer =
                pointerSlot.get(ValueLayout.ADDRESS, 0);
            long length = lengthSlot.get(ValueLayout.JAVA_LONG, 0);

            // Pointer target is malloc-owned; cleanup is not automatic.
            try {
                if (nativePointer.address() == 0 || length != 4) {
                    throw new IllegalStateException("Invalid native result");
                }

                // Restricted: requires TRUSTED length and native-access.
                MemorySegment view = nativePointer.reinterpret(length);
                System.out.print("payload: ");
                for (long i = 0; i < length; i++) {
                    if (i > 0) System.out.print(",");
                    System.out.print(view.get(ValueLayout.JAVA_BYTE, i) & 0xFF);
                }
                System.out.println();
            } finally {
                // Same library/allocator that created the payload.
                release.invokeExact(nativePointer);
            }
        }
    }
}
```

### 8.2. Compile and run

In the directory containing `OutParamsDemo.java` **and the built shared library**:

```bash
javac -encoding UTF-8 OutParamsDemo.java
java --enable-native-access=ALL-UNNAMED OutParamsDemo
```

**Expected stdout according to the sample C source:**

```text
answer: 42
buffer: hello
payload: 10,20,30,40
```

**Distinguishing verification levels:** the Java code above was **successfully compiled by javac 24**. The current Windows environment has no C compiler in PATH, so **the sample Java/C pair has not been run together**. Stdout is **the result inferred from the presented C code contract**, not an actual run log of this pair. The Windows example in section 5 was actually run on OpenJDK 24.

### 8.3. Ownership analysis of each object

| Variable/segment | Who allocates? | Who owns? | How is it freed? |
| --- | --- | --- | --- |
| `outInt` | `arena.allocate(JAVA_INT)` | Java Arena | Automatically cleaned up when arena closes |
| `requiredSlot` / `lengthSlot` | `arena.allocate(JAVA_LONG)` | Java Arena | Automatically cleaned up when arena closes |
| `buffer` | `arena.allocate(capacity)` | Java Arena | Automatically cleaned up when arena closes; C does not `free` |
| `pointerSlot` | `arena.allocate(ADDRESS)` | Java Arena | Automatically cleaned up when arena closes |
| `nativePointer` (pointer value received from slot) | C writes address into slot | Does not own the address just because there is a Java handle | Do not `free` the “Java handle” itself; must consider the **target block** |
| Block pointed to by `nativePointer` | C `malloc(4)` | **Transferred to caller after successful creation** | `release_payload(nativePointer)` exactly **once** |
| `view` from `reinterpret(length)` | FFM creates an alias pointing to C block | Only a **view**, not a separate allocation | Do not free view; block is released via C API |

Once `create_payload` succeeds, `finally` guarantees calling `release_payload` even if reading/formatting the data throws an exception. Conversely, when `create_payload` returns an error, the sample C code ensures the pointer remains `NULL` and does not transfer ownership; Java throws an error and **must not free a garbage pointer**.

Do not let `nativePointer`/`view` escape the processing scope after calling `release_payload`. Java cannot detect every use-after-free on a segment that was manually `reinterpret`ed with a size. Do not assume `Arena.close()` automatically calls `free` for a separately malloc'd block: to tie a native allocation to an Arena, you need an explicit cleanup mechanism such as a properly designed `reinterpret(size, arena, cleanup)`. **Do not simultaneously register a cleanup on arena close and call free in `finally`**, as that will cause a double-free.

## 9. Two approaches to handling native buffers: pre-allocate and query-size-first

Libraries that use buffers have two common protocols.

### 9.1. Caller knows capacity upfront

```c
int read_data(char *buf, size_t capacity, size_t *bytes_written);
```

Java allocates the exact capacity; native does not write past it; on success, `bytes_written` must be in the range `0..capacity`. Java reads **exactly `bytes_written` bytes**, without assuming NUL or UTF-8 if the API does not say so. If the API reports overflow/truncation, handle it instead of reading uninitialized memory.

**Common pitfall:** capacity is measured in **number of elements** while Java allocates in bytes; with `wchar_t[]` or a C struct with padding, the two numbers are not the same. Check the C header documentation and data representation.

### 9.2. Two-pass / probe-then-fill

Many APIs allow calling first with output `NULL` and capacity `0` to obtain the required size. For example, `fill_message` in section 7 uses `return 1` and `*required=6`, and then Java allocates 6 bytes. Similarly, `MultiByteToWideChar` allows querying the number of UTF-16 code units first.

General pattern:

```text
call(NULL, 0, &required)
        │
        ▼
  validate required (>= 0, within max, no overflow)
        │
        ▼
 allocate exactly required units
        │
        ▼
 call(buffer, capacity, &written)
        │
        ▼
 check status and written <= capacity
        │
        ▼
 decode/copy exact initialized region
```

Do not assume “returning `0` always means success” or “`required` always includes NUL”: each native API has a different return contract.

**Race condition to watch out for:** if the source data changes between the probe call and the fill call, the required size may change. Real-world APIs may require a reallocation loop, bounded retries, or a caller-specified capacity. Do not retry infinitely and do not allocate based on an unchecked native size. With the fixed C example `"hello"`, the size does not change between the two passes.

## 10. Borrowing pointers, transferring ownership, and protecting lifetime

### 10.1. Free/close decision table

| What does the native function return? | Result ownership | Should you free it yourself? |
| --- | --- | --- |
| Pointer to `static const char[]` | Library-owned/static | **No**; may become invalid if the library is unloaded |
| Pointer into a Java-passed input buffer (like `strtol endptr`) | Borrowed view | **No**; only use while input is alive |
| Newly created pointer via `malloc`, contract transfers ownership | Caller-owned/native allocation | **Yes**, using the exact matching `free`/release API |
| Pointer to memory the library holds in an object/session | Library-owned, time-bounded | **No**, call the owner's close/release per contract |
| Caller-allocated output buffer | Java-owned Arena memory | **Do not `free` on C side**; close Arena on Java side |
| OS/API-issued opaque handle, not a memory pointer | Depends on handle type | Use corresponding `CloseHandle`/`Release...`, **do not** use `free` unless API requires it |

Do not confuse pointer-to-pointer `T**` with “allocation is always performed by the library”. Sometimes it is only a borrowed pointer-to-pointer or an output pointer pointing into input. Conversely, a function can return a **pointer directly in the return value** and still transfer ownership. Only the **contract/documentation** determines who frees it.

### 10.2. Do not retain pointers longer than their source

- A `char*` returned by C pointing to a buffer allocated by `Arena.ofConfined()` is only safe before the arena closes, on the corresponding owner thread.
- A pointer to static library memory may remain valid for a long time, but **should not be used after the library is unloaded**.
- A pointer to a C malloc'd block may still exist as an address after `free`, but **that value becomes invalid to dereference**. Set the registry/native state to “freed” and do not reuse it.
- A returned pointer of unknown size must not be `reinterpret(1000000)`ed just to “peek at the data”; there must be an authoritative size and threshold check.

### 10.3. If you want to carry data outside the native lifetime

The safest approach is to **copy the result into Java values** before closing the arena or freeing the C block:

```java
// Local example: view is a still-valid 4-byte MemorySegment.
byte[] copy = view.toArray(ValueLayout.JAVA_BYTE);
// After copying is done, release native block;
// byte[] is independent Java memory, no longer dependent on native pointer.
```

If you need to return a string, decode the exact bytes written, including terminator/encoding rules. Do not return a native `MemorySegment` alias to long-lived Java code without a clear owner and guaranteed cleanup.

## 11. Common errors and how to fix them

| Error | Cause | How to fix |
| --- | --- | --- |
| Java FFM receives `int*` but descriptor uses `JAVA_INT` | Confusing `int` value with `int*` address | Parameter descriptor must be `ADDRESS`; allocate `JAVA_INT` slot |
| Using `arena.allocate(JAVA_BYTE)` for `char**` | Slot is not large enough to hold a 64-bit pointer | Allocate with `arena.allocate(ADDRESS)` with proper alignment |
| Reading `pointer.get(JAVA_BYTE,0)` right after `get(ADDRESS,0)` | Pointer-return segment defaults to size **0** | Use original segment with offset, or `reinterpret` with certain size/lifetime |
| Calling `free` on pointer from `strtol endptr` | Borrowed pointer pointing into input | Do not free; use while input is alive |
| Not freeing pointer from `create_payload` | Native block was malloc'd and ownership transferred | Call `release_payload` properly in `finally` |
| Double free | Both Java and Arena cleanup free the same block | Choose **one** cleanup owner; do not combine double-free |
| Reading buffer when native call reports error | C may not have initialized contents | Check return status and `written` before reading |
| Forgetting NUL or miscalculating length | `size_t` may be byte count; WinAPI uses WCHAR count | Allocate in the right unit, leave room for terminator if API needs it |
| Using `JAVA_LONG` for Windows `strtol` | Windows x64 C `long` is only 32 bits | Map return `JAVA_INT` on Windows LLP64; Linux x64 differs |
| Using `JAVA_INT` for x64 `size_t` | x64 `size_t` is 64 bits | `JAVA_LONG` on 64-bit ABI; check platform |
| Using memory after closing Arena/freeing native | Temporal lifetime violated | Copy first, close/free via proper owner, do not keep dangling alias |
| Java code cannot find symbol | Wrong DLL/.so path or C++ mangled name | Choose right `System.mapLibraryName`, path, exported C symbols |
| Restricted-method warning/`IllegalCallerException` | Missing native access permission | `--enable-native-access=ALL-UNNAMED` for classpath or module name |
| JVM crash on downcall | Wrong ABI, pointer size, calling convention, or lifetime | Cross-check C header, each `FunctionDescriptor`, check size and threading |

If a C API has `errno`/`GetLastError`, do not infer error codes solely from the return value or output length. For example, `strtol` can return 0 when parsing `"0"` correctly **or** when there are no digits; distinguish via `endptr`, and use an `errno`-reading mechanism suitable for handling overflow/underflow. With WinAPI, you may need a mechanism to capture **last-error** on the right thread/call boundary. This article only uses deterministic input data to focus on out-parameters.

## 12. Checklist when integrating a real out-parameter API

1. Read the **C signature**: return type, `const`, pointer depth, C ABI, alignment, argument order.
2. Create a table for each pointer: **[in], [out], [in,out]**, number of bytes/elements allowed to access.
3. Determine **who allocates**, **who owns**, **who frees**, and with which exact allocator/handle-release API.
4. For `T*`, allocate the right slot type (`JAVA_INT`, `JAVA_LONG`...). For `T**`, allocate an **`ADDRESS` slot** and read the pointer after the call.
5. Initialize output slots per contract, usually null/0, before passing to native code.
6. Check **status before dereferencing**; do not treat outputs as valid if the API reports failure.
7. For buffers, check size by unit (byte, UTF-16 code unit, C element), NUL rules, overflow, max capacity.
8. For native pointers, check null, authoritative size, and lifetime before `reinterpret`; understand the restricted API does not make memory safe automatically.
9. Clean up memory via the proper owner in `finally`/`try-with-resources`, do not free borrowed pointers, do not double-free.
10. Copy to Java `byte[]`/`String` if the data needs to outlive the arena or freed native block.
11. Test branches for buffer too small, native allocation failure, null pointer, length 0, invalid length, native error code, and multithreading.
12. Test on **each target ABI**; especially verify `long`, `size_t`, `wchar_t`, and struct layout before release.

## 13. Practice exercises

1. In `int get_answer(int *out)`, why is the FFM parameter `ADDRESS` while the Java slot is allocated with `JAVA_INT`?
2. For `char **out`, how many bytes does Java need to allocate for the slot on Windows x64? Why not use `JAVA_BYTE`?
3. After `endSlot.get(ValueLayout.ADDRESS,0)`, why should you not read bytes directly from the returned pointer segment?
4. Why must `strtol`'s `endptr` pointer **not** be freed, even though it is received via `char**`?
5. When `create_payload` succeeds, do the two memory regions `pointerSlot` and the `malloc`'d block have the same owner? Who frees each region?
6. Suppose a library returns size as the number of `wchar_t` elements; why can't Java assume by default that it is a byte count?
7. If the first probe says 64 bytes are needed but the data changes and the fill call requests 128, how should the application handle it?
8. If you use `reinterpret(n)` with `n` larger than the actual native block, does Java guarantee a bounds check to prevent a crash?
9. Why does `try-with-resources` on an Arena **not automatically free** a pointer that C allocated with `malloc`?
10. What is the difference between a directly returned `char*`, a `char**` output, and a `char*` caller-supplied buffer in terms of ownership?

**Remember:** **`T*`** usually lets C write a value into a slot, **`T**` lets C write **a pointer** into a slot, and a **caller-provided buffer** is Java-allocated memory for native to fill. FFM only gives you handles and memory views; **ownership, size, lifetime, allocator, and error-handling protocol must come from the library's contract**. Do not free borrowed pointers; free ownership-transferred pointers exactly once; do not read data outside capacity or after Arena/free.

### Official documentation

- [Oracle JDK 24 — FFM package overview: MemorySegment, Arena, Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle JDK 22 — MemorySegment API: pointer returns, getString and reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle JDK 22 — SymbolLookup.libraryLookup and native library lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java Core Libraries — Foreign Functions That Return Pointers](https://docs.oracle.com/en/java/javase/23/core/foreign-functions-that-return-pointers.html).
- [Microsoft Learn — GetComputerNameW: out buffer, in/out size](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getcomputernamew).
- [Microsoft Learn — MultiByteToWideChar: sizing and output buffer](https://learn.microsoft.com/en-us/windows/win32/api/stringapiset/nf-stringapiset-multibytetowidechar).
- [Microsoft Learn — Windows x64 LLP64 data model](https://learn.microsoft.com/en-us/windows/win32/winprog64/abstract-data-models).
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — Foreign Function & Memory API (Third Preview)](https://openjdk.org/jeps/442).
