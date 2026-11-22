# Checking the Return Value Before Reading Error Codes According to the Function's Contract When Calling Native Code with FFM

## 1. Why Must You Check the Return Value First?

With Java's **Foreign Function & Memory API (FFM)**, a native call (*downcall*) is represented by a `MethodHandle` created by `Linker.downcallHandle`. Java can call C functions such as `fopen`, `tmpfile`, `fclose`, `read`, or a Windows API function without writing a JNI wrapper yourself. However, FFM **does not automatically turn all C errors into Java exceptions**.

The error contract of each native function usually has two parts:

1. **The return value** determines whether the call succeeded, failed, reached the end of a data stream, or produced a normal result.
2. **Auxiliary error codes** such as C `errno`, Windows `GetLastError`, or WinSock `WSAGetLastError` are only meaningful in **the cases where the function's contract allows reading them**.

C example:

```c
FILE *f = fopen("missing.txt", "rb");
if (f == NULL) {
    int saved_errno = errno;  /* Error is meaningful according to the fopen contract. */
    /* Handle or report the error based on saved_errno. */
} else {
    /* fopen succeeded: DO NOT treat errno != 0 as a failure. */
    /* Use f and then fclose(f) at the appropriate time. */
}
```

**Most important rule to learn:**

> **Native result → interpret according to the function's own contract → only if the result indicates an error and the API defines an auxiliary error channel should you read the captured error code.** Do not reverse this order.

Direct consequences:

- `errno != 0` is **not** a general indicator that a C function has just failed.
- `GetLastError() != 0` is **not** a general indicator that a Win32 call has just failed.
- `result == 0` is **not** always an error either. For example, `read` returns 0 upon reaching EOF, whereas Win32 `CloseHandle` returns 0 on failure; `getaddrinfo` returns 0 on success.
- `result == -1` is not always an error: some APIs use `-1` as a valid value; you must read the function's documentation carefully and may need an `errno = 0` procedure before the call.
- Even when FFM has **captured** the error state in time, the application must still **decide whether to read/interpret it based on the native result**.

This lesson focuses on FFM in **JDK 22+** (JEP 454, finalized API). The complete Java examples were compiled and run with **JDK 24**. They use `java.lang.foreign`, `java.lang.invoke`, and the `--enable-native-access=ALL-UNNAMED` flag for the restricted downcall API on the classpath. Do not use these examples directly on JDK 17: FFM in JDK 17 has a different incubator API.

## 2. There Is No Single Error-Return Convention for All C Functions

To implement a wrapper accurately, start from **Return value / Errors** in the documentation of **the exact native function being called**, not by guessing about `errno`.

| Function or API family | Indicator per return contract | When to inspect auxiliary error code? |
| --- | --- | --- |
| C `fopen(path, mode)` | Non-NULL `FILE*`: success; `NULL`: failure | When `NULL`, read `errno` of **that call** |
| C `tmpfile()` | Non-NULL `FILE*`: success; `NULL`: failure | When `NULL`, inspect `errno` |
| C `fclose(FILE*)` | `0`: success; `EOF` (usually `-1`): error | When returning an error, inspect `errno` per library contract |
| POSIX `open(path, flags)` | File descriptor `>= 0`: success, `-1`: error | Only when `-1`; **fd = 0 is valid** |
| POSIX `read(fd, buffer, n)` | Byte count `>0`: data; `0`: EOF; `-1`: error | Only when `-1`; reading fewer than `n` bytes is not necessarily an error |
| C `fread(...)` | Number of elements read; fewer than requested may be EOF or error | Distinguish using `ferror`/`feof`; do not infer solely from `errno` |
| POSIX `getaddrinfo(...)` | `0` success; nonzero is an `EAI_*` error code **returned directly** | Use `gai_strerror(result)`; `errno` is only relevant in some cases such as `EAI_SYSTEM` |
| POSIX `pthread_*` (many functions) | `0` success, nonzero is an error code **returned directly** | Do not assume these functions set `errno` |
| Win32 `CloseHandle(h)` | `BOOL != 0` success, `0` failure | `GetLastError` when returning `0` |
| Win32 `GetFileAttributesW(path)` | `INVALID_FILE_ATTRIBUTES` (`0xFFFFFFFF`) is error | `GetLastError` when encountering this sentinel |
| WinSock functions documented to use `WSAGetLastError` | Specific sentinel (`SOCKET_ERROR`, `INVALID_SOCKET`, …) | Only when the status requires it; use **WSAGetLastError**, do not mix with Win32 |
| COM/Win32 `HRESULT` | `SUCCEEDED(hr)` / `FAILED(hr)` based on the sign bit | `HRESULT` itself indicates the status; only read an auxiliary channel if the API states so |

This table is a **guide for reading contracts**, not a replacement for per-function documentation. Types such as `size_t`, `ssize_t`, `long`, `BOOL`, `DWORD`, and pointers must be described with a `FunctionDescriptor` matching the specific ABI. For example, `BOOL` is typically a Win32 32-bit integer, not `ValueLayout.JAVA_BOOLEAN`.

## 3. Why Can errno Be Nonzero Even When a Native Call Succeeds?

### 3.1. errno Is Not a “Success/Failure Flag”

In C/POSIX, `errno` is a **thread-local** contextual error state. Many functions only set `errno` when an error occurs and are **not required to reset it to 0 on success**. Some functions are even allowed to modify `errno` even when they succeed.

Suppose:

```text
Call 1: fopen(missing, "rb") -> NULL, errno = ENOENT
Call 2: tmpfile()            -> non-NULL FILE*
                                errno may still be ENOENT
```

If after Call 2 you write:

```java
// WRONG: turns even a successful call into an error.
if (capturedErrno != 0) {
    throw new IOException("tmpfile failed");
}
```

then it may throw an exception even though `tmpfile` returned a valid `FILE*`. Reading errors must be based on the return contract: `tmpfile` **only fails if it returns NULL**.

In a JDK 24 test on the Windows C runtime, `fopen` for a nonexistent file set `errno = 2`, and then `tmpfile` returned a valid file pointer, yet the captured `errno` value **could still be 2**. That is an **illustrative observation**, not a guarantee that every CRT or OS will preserve this exact number.

### 3.2. Do Not Blindly Reset errno After Every Call

Another misconception: “Before every native call, just reset `errno = 0` to make checking easy.” This **does not fix** the logic bug if you still conclude success or failure solely from `errno`.

- For `fopen`, `tmpfile`, `open`, or `read`, the return contract already specifies the sentinel. **There is no need to reset errno** to determine success.
- Some APIs have a **sentinel value that can indicate either success or an error**. For that special case, the documentation may require setting `errno = 0` **before calling the function** and then classifying both the return value and `errno`.
- The error code may use a separate channel such as `HRESULT` or `EAI_*`, without needing `errno`.

**Do not confuse this:** `capturedState.set(JAVA_INT, ..., 0)` only modifies the **Java buffer allocated for capture**; it **does not reset the actual native thread-local errno**. If an API requires resetting `errno` before a call, it must be done via a native mechanism on the right thread and right CRT according to the function's documentation.

## 4. The Timing Problem: Even When You Know a Call Failed, the Error Code Can Still Be Overwritten

In ordinary C:

```c
FILE *f = fopen(path, "rb");

if (f == NULL) {
    int saved = errno; /* SAVE IMMEDIATELY at the moment the contract reports an error. */
    log_message("open failed");  /* May perform other native calls. */
    report_error(saved);        /* Use the saved code, do not re-read errno. */
}
```

If C code calls `printf`, `malloc`, `strerror`, or another API **before copying `errno`**, the TLS value may change and the cause of `fopen`'s failure is lost. In Java FFM, transitioning from native to Java can involve the runtime/linker; therefore **reading `errno` by calling another function after the downcall has returned is not reliable enough**.

FFM solves *taking a snapshot* with:

```java
Linker.Option.captureCallState("errno")
```

The linker records the state to be captured **immediately after the native call, before the runtime or normal operations have a chance to overwrite it**. Java code can then check the return value and **only if it has failed** read the captured code.

**The two operations have different responsibilities:**

- `captureCallState`: saves the data in time, regardless of success or failure.
- `if (nativeReturn indicates failure)`: chooses the meaningful moment to interpret the saved data.

Capturing state **does not replace checking the return value**; nor does it turn Java exceptions into `errno`.

## 5. Structure of captureCallState in FFM

### 5.1. From SymbolLookup to MethodHandle

A downcall typically starts with:

```java
Linker linker = Linker.nativeLinker();
SymbolLookup c = linker.defaultLookup();

MethodHandle fopen = linker.downcallHandle(
        c.findOrThrow("fopen"),
        FunctionDescriptor.of(
                ValueLayout.ADDRESS,  // FILE * result
                ValueLayout.ADDRESS,  // const char *filename
                ValueLayout.ADDRESS), // const char *mode
        Linker.Option.captureCallState("errno"));
```

**This is an illustrative snippet**, placed inside a class with `import java.lang.foreign.*; import java.lang.invoke.MethodHandle;`. Linking must match the C function's ABI; a wrong descriptor can lead to a crash or memory corruption. The method handle above is **bound** to the specific `fopen` symbol using the `downcallHandle(symbol, descriptor, option)` overload.

### 5.2. The Capture Buffer Is a Separate MemorySegment

`Linker.Option.captureStateLayout()` returns a platform-dependent `StructLayout` containing fields named after the states that can be captured. For example, a Windows environment may support `errno`, `GetLastError`, and `WSAGetLastError`, whereas Unix-like platforms typically use `errno`.

Do not guess offsets or assume the capture layout is identical across machines. Use:

```java
StructLayout stateLayout = Linker.Option.captureStateLayout();
MemorySegment state = arena.allocate(stateLayout);
VarHandle errnoField = stateLayout.varHandle(
        MemoryLayout.PathElement.groupElement("errno"));
```

Read the snapshot with:

```java
int savedErrno = (int) errnoField.get(state, 0L);
```

`0L` is the offset coordinate required by `VarHandle` for the layout path in this usage. Allocating with `arena.allocate(stateLayout)` also guarantees the appropriate size and alignment. **Do not** allocate a buffer of just one `JAVA_INT` and pass it arbitrarily if the platform's state layout is larger or has padding.

### 5.3. A New Parameter Appears in the Downcall's Signature

For a **bound** downcall like the one above, `captureCallState` adds a `MemorySegment` parameter at the beginning of the `MethodHandle`'s Java arguments:

```java
MemorySegment file = (MemorySegment) fopen.invokeExact(
        state,       // Parameter added by FFM to store call state.
        pathCString, // C argument 1.
        modeCString  // C argument 2.
);
```

Do not confuse the `state` parameter with an actual argument of `fopen`. In C, the prototype is still `FILE *fopen(const char *, const char *)`.

With an **unbound downcall handle**, the target function address appears in the Java parameter list before the capture buffer. With the **bound symbol** overload used in this lesson, the function address is already attached to the handle, so the new first parameter is `state`.

`MethodHandle.invokeExact` requires **exact parameter types and return type**; for example, the result of `fopen` must be cast to `MemorySegment`, while `fclose` returns `int`. A `WrongMethodTypeException` is a Java configuration/invocation error, **not** an `errno` from a C function that reported failure.

### 5.4. Getting the List of Supported State Fields on the Platform

`captureCallState` can throw `IllegalArgumentException` if a requested field name is not supported on the current platform. Use:

```java
var supported = Linker.Option.captureStateLayout()
        .memberLayouts().stream()
        .map(MemoryLayout::name)
        .flatMap(java.util.Optional::stream)
        .toList();
System.out.println(supported);
```

This is a snippet placed in a class that imports `java.lang.foreign.*`. The list is **platform-dependent**, so do not hardcode the output. If the native API belongs to Win32, capture `GetLastError`; if it belongs to WinSock and the documentation specifies WinSock errors, capture `WSAGetLastError`; if it belongs to the C runtime/POSIX, consider `errno`.

## 6. Complete Java Program: Checking fopen Before Reading errno

This example uses the **C standard library** through FFM. The program:

1. Creates a temporary directory in Java, ensuring the file `absent-file.txt` does not exist in the new directory.
2. Calls `fopen(path, "rb")`; according to the contract, `NULL` means error.
3. **Only after seeing result == NULL** does it read the `errno` captured by FFM.
4. Calls `tmpfile()`; succeeds if it returns a non-NULL pointer, **without looking at errno to decide success or failure**.
5. Calls `fclose(FILE*)`; succeeds if it returns `0`.
6. Releases the Java resources (the arena) and the temporary directory. `FILE*` is closed explicitly by `fclose`, **not** freed by `Arena.close`.

### 6.1. File NativeReturnFirstDemo.java

```java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class NativeReturnFirstDemo {
    private static final Linker LINKER = Linker.nativeLinker();
    private static final SymbolLookup C = LINKER.defaultLookup();

    private static final Linker.Option CAPTURE =
            Linker.Option.captureCallState("errno");

    private static final StructLayout STATE =
            Linker.Option.captureStateLayout();

    private static final VarHandle ERRNO =
            STATE.varHandle(groupElement("errno"));

    // FILE *fopen(const char *filename, const char *mode)
    private static final MethodHandle FOPEN = LINKER.downcallHandle(
            C.findOrThrow("fopen"),
            FunctionDescriptor.of(ADDRESS, ADDRESS, ADDRESS),
            CAPTURE);

    // FILE *tmpfile(void)
    private static final MethodHandle TMPFILE = LINKER.downcallHandle(
            C.findOrThrow("tmpfile"),
            FunctionDescriptor.of(ADDRESS),
            CAPTURE);

    // int fclose(FILE *stream)
    private static final MethodHandle FCLOSE = LINKER.downcallHandle(
            C.findOrThrow("fclose"),
            FunctionDescriptor.of(JAVA_INT, ADDRESS),
            CAPTURE);

    public static void main(String[] args) throws Throwable {
        Path directory = Files.createTempDirectory("ffm-return-first-");

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment callState = arena.allocate(STATE);
            MemorySegment missing = arena.allocateFrom(
                    directory.resolve("absent-file.txt").toString());
            MemorySegment mode = arena.allocateFrom("rb");

            MemorySegment file = (MemorySegment) FOPEN.invokeExact(
                    callState, missing, mode);

            // 1) Always check the return contract first.
            if (file.address() == 0) {
                // 2) Only because fopen failed is errno meaningful.
                int savedErrno = (int) ERRNO.get(callState, 0L);
                System.out.println("fopen failed: true");
                System.out.println("errno captured on failure: "
                        + (savedErrno != 0));
            } else {
                // Defensive branch: do not leak FILE* in an unexpected environment.
                try {
                    throw new AssertionError("Unexpected existing file");
                } finally {
                    int ignored = (int) FCLOSE.invokeExact(callState, file);
                }
            }

            MemorySegment temporary =
                    (MemorySegment) TMPFILE.invokeExact(callState);

            // Do not inspect tmpfile's errno before checking FILE*.
            if (temporary.address() == 0) {
                int savedErrno = (int) ERRNO.get(callState, 0L);
                throw new IllegalStateException(
                        "tmpfile failed, errno=" + savedErrno);
            }
            System.out.println("tmpfile succeeded: true");

            // After a successful call, ignore errno even if it may be nonzero.
            int closed = (int) FCLOSE.invokeExact(callState, temporary);
            if (closed != 0) {
                int savedErrno = (int) ERRNO.get(callState, 0L);
                throw new IllegalStateException(
                        "fclose failed, errno=" + savedErrno);
            }
            System.out.println("fclose succeeded: true");

        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

**Build/run with JDK 22+ on a platform with the corresponding C runtime exports:**

```bash
javac NativeReturnFirstDemo.java
java --enable-native-access=ALL-UNNAMED NativeReturnFirstDemo
```

**Stdout verified on JDK 24 / Windows (C runtime supporting `fopen`, `tmpfile`, `fclose`):**

```text
fopen failed: true
errno captured on failure: true
tmpfile succeeded: true
fclose succeeded: true
```

**Stability:** the example intentionally does not print a specific `errno` value because numeric codes and error messages depend on the OS/CRT; it only checks that the error code is nonzero after a failure confirmed by `fopen`'s contract. `tmpfile()` requires a temporary directory and OS resources; in an environment that disallows creating temporary files, the function may fail and the program will throw an error with `errno` according to the contract instead of printing success stdout. Some platforms have different export names or library lookups; in that case, you must specify the right native library and ABI.

### 6.2. Why Does the Example Not Rely on errno After Success?

The two key statements are:

```java
MemorySegment temporary =
        (MemorySegment) TMPFILE.invokeExact(callState);

if (temporary.address() == 0) {
    int savedErrno = (int) ERRNO.get(callState, 0L);
    throw new IllegalStateException("tmpfile failed, errno=" + savedErrno);
}
```

Suppose the `callState` buffer after `tmpfile` contains a nonzero error code from a previous operation or from internal CRT work. `temporary.address() != 0` **is still proof of success under `tmpfile`'s contract**. Interpreting `errno` when there is no failure sentinel can produce false positives.

Similarly, `fclose` returns `0` on success; Java must not read the error state just to look for a nonzero number.

### 6.3. Why Not Pass the File Pointer to Java's Arena.close?

The `MemorySegment` returned from `fopen`/`tmpfile` only wraps the native `FILE*` address; the Java object does not own the stream-closing mechanism. `arena.close()` frees the memory regions **allocated by the arena** (such as C strings and the capture-state buffer), and **does not automatically call `fclose` on the FILE*** allocated by the C runtime. You must call `fclose` according to the contract, and if a workflow can abort midway through steps, you should protect the stream with `try/finally` or an `AutoCloseable` wrapper.

### 6.4. What Was Actually Tested?

The `NativeReturnFirstDemo.java` code was compiled and run with JDK 24, using `--enable-native-access=ALL-UNNAMED`. On the test machine, `fopen` returned NULL and `errno` was captured; `tmpfile` returned nonnull; `fclose` returned 0. The lesson **does not require installing a C compiler** because it uses C runtime functions already present in the process.

## 7. Windows Has Its Own Channel: GetLastError Is Not Equivalent to errno

### 7.1. Win32 Contracts

Some Win32 APIs use the error code returned by `GetLastError()`. This is Windows per-thread state, **not** the C runtime's `errno` variable. Nor is it the same as WinSock `WSAGetLastError()`.

Examples:

- `BOOL CloseHandle(HANDLE h)`: a **nonzero result is success**; `0 is an error`, read `GetLastError` to understand why.
- `DWORD GetFileAttributesW(LPCWSTR path)`: returns `INVALID_FILE_ATTRIBUTES` (`0xFFFFFFFF`) on error; other attribute values are successful results, **no need to read GetLastError**.
- WinSock APIs may require `WSAGetLastError`, not `GetLastError`.

Microsoft notes that some APIs set last-error to 0 on success, some **do not reset it**, and some may set a value even on success. Therefore `GetLastError()!=0` **is not a general failure condition**.

### 7.2. Why Is captureCallState("GetLastError") Useful?

The correct sequence:

```text
Java invokes Win32 downcall
  -> C/Win32 function executes
  -> FFM captures GetLastError immediately after the call into MemorySegment
  -> Java receives the int/DWORD/BOOL result
  -> inspect result per API documentation
      |
      +-- failure: read the GetLastError snapshot
      |
      +-- success: ignore the snapshot or only use it when explicitly defined by the API
```

Do not casually make a new `GetLastError()` downcall after Java has moved through other native calls: the error state may already have been changed. The capture option preserves the snapshot at the exact right moment.

### 7.3. Standalone Windows Program: GetFileAttributesW

The following program **runs only on Windows**, using `kernel32.dll`. The temporary directory is created by Java to ensure `absent-file.dat` does not exist. The Win32 function returns the `INVALID_FILE_ATTRIBUTES` sentinel; **only in the sentinel branch** does it read the captured `GetLastError` code.

**File `Win32ReturnFirstDemo.java`:**

```java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.*;
import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class Win32ReturnFirstDemo {
    public static void main(String[] args) throws Throwable {
        Path directory = Files.createTempDirectory("ffm-winerr-");

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();

            SymbolLookup kernel32 = SymbolLookup.libraryLookup(
                    "kernel32.dll", arena);

            StructLayout stateLayout =
                    Linker.Option.captureStateLayout();

            VarHandle errorField = stateLayout.varHandle(
                    groupElement("GetLastError"));

            // DWORD GetFileAttributesW(LPCWSTR lpFileName)
            MethodHandle attributes = linker.downcallHandle(
                    kernel32.findOrThrow("GetFileAttributesW"),
                    FunctionDescriptor.of(JAVA_INT, ADDRESS),
                    Linker.Option.captureCallState("GetLastError"));

            MemorySegment callState = arena.allocate(stateLayout);

            MemorySegment name = arena.allocateFrom(
                    directory.resolve("absent-file.dat").toString(),
                    StandardCharsets.UTF_16LE);

            int result = (int) attributes.invokeExact(callState, name);

            // INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF = int -1.
            if (result == -1) {
                int winError = (int) errorField.get(callState, 0L);
                System.out.println("Win32 call failed: true");
                System.out.println("GetLastError captured on failure: "
                        + (winError != 0));
            } else {
                System.out.println("Win32 call succeeded");
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

**Commands to run on Windows:**

```bat
javac Win32ReturnFirstDemo.java
java --enable-native-access=ALL-UNNAMED Win32ReturnFirstDemo
```

**Stdout verified with JDK 24 on Windows:**

```text
Win32 call failed: true
GetLastError captured on failure: true
```

Analysis:

1. The function name is `GetFileAttributesW`, the wide-character version; `StandardCharsets.UTF_16LE` provides a UTF-16LE string matching `LPCWSTR`, and `allocateFrom` appends the NUL terminator according to the encoding.
2. `JAVA_INT` is used to represent a 32-bit `DWORD` when passing through `MethodHandle`. The unsigned value `0xFFFFFFFF` has the signed `int` representation `-1`. Do not call `GetLastError` just because a flag in the result happens to be nonzero.
3. Only when `result == -1` do we read the `GetLastError` captured by FFM. On the test machine, the code returned `2` (file not found), but the test only requires **nonzero** and does not treat that numeric code as a universal contract across all situations.
4. `GetLastError` is not used in place of C `errno`. If you are calling the CRT's `fopen` on Windows, the failure branch normally inspects **the CRT's errno**, not automatically Win32 last-error.

### 7.4. Notes When Choosing the Win32 Failure Sentinel Type

Do not equate Win32 with “returning 0 is an error”:

| Win32 API / API family | Return status to inspect |
| --- | --- |
| `CloseHandle` | BOOL = 0 is an error |
| `GetFileAttributesW` | DWORD = 0xFFFFFFFF is an error |
| `CreateFileW` | HANDLE = `INVALID_HANDLE_VALUE` is an error, **not always NULL** |
| `HRESULT`-returning API | Use `FAILED(hr)`/`SUCCEEDED(hr)`, do not assume every nonzero value is an error |

If an API has a condition for returning a “success with additional information” value, read `GetLastError` according to that exact section of the function's documentation, rather than applying a single blanket rule.

## 8. APIs That Return Error Codes Directly: Do Not Use errno as the Primary Channel

Some native functions encode the reason for failure **directly in the return value**. POSIX example:

```c
int rc = getaddrinfo(node, service, hints, &result);
if (rc != 0) {
    /* rc is an EAI_* code (not a generic -1 for errno).
       gai_strerror(rc) is normally used to describe the error. */
} else {
    /* result is valid; must call freeaddrinfo(result) after use. */
}
```

According to the `getaddrinfo` documentation, if `rc == EAI_SYSTEM`, then a related system error may be reflected in `errno`. However, for other `EAI_*` error codes, reading `errno` instead of `rc` is **wrong**.

Similarly, many POSIX `pthread_*` functions return `0` or return an **error number** directly without setting `errno`. And for some C++/library-specific APIs, an output parameter or a result struct may hold the status; you must follow the exact API docs.

In FFM, you should translate the result into a clear Java abstraction:

```java
// Pseudocode: rc is the return code of native getaddrinfo.
if (rc != 0) {
    throw new NativeAddressResolutionException(rc);
}
// Do not depend on errno in the success branch.
```

**The snippet above is pseudocode**, because `NativeAddressResolutionException` is an application-defined exception name and does not exist in the JDK. When using FFM in practice, you need the correct `FunctionDescriptor` for `struct addrinfo**`, the correct C layout, and a deallocation policy.

## 9. Success, EOF, and Partial Results Are Not the Same as Errors

### 9.1. POSIX read

```c
ssize_t n = read(fd, buffer, capacity);
if (n < 0) {
    int saved_errno = errno;
    /* Error: use saved_errno. */
} else if (n == 0) {
    /* EOF: usually normal end of stream/file. */
} else {
    /* n bytes were read, even if n < capacity. */
}
```

A `read` call returning **fewer bytes than requested** can be completely normal (pipes, sockets, files near EOF). `n == 0` is EOF in many contexts, not an error for calling `perror`. In FFM, `ssize_t` must be mapped according to the native ABI: on common 64-bit systems it is often 64-bit, but you must not blindly use `JAVA_LONG` on every target. Do not use `captureCallState("errno")` as a substitute for classifying `n<0 / n==0 / n>0`.

### 9.2. fread

`fread(ptr, size, count, stream)` returns **the number of complete elements read**. If the result is less than `count`, it may be due to EOF **or** an I/O error. The contract requires checking `feof(stream)` and `ferror(stream)` to distinguish them. `errno` alone does not express the full stream state.

When `size == 0` or `count == 0`, a result of 0 can be a **valid success**, not an error. Therefore, logic like `if (result == 0) throw ...` is wrong for `fread`.

### 9.3. APIs Returning Valid Pointers or Integer 0

- A POSIX file descriptor equal to `0` can be a valid descriptor. Check `fd == -1` per the `open` contract.
- Functions returning a data count may return `0` when there is no data, which does not mean failure.
- C `NULL` is an error for `fopen`, but for other APIs `NULL` may mean “not found” as a normal outcome, depending on the contract.
- A native callback returning `void` may use a separate error-reporting mechanism and does not inherently have a return value to infer from.

You should design clear Java methods: a “not found” case can be mapped to `Optional.empty()`, while a system error can become an exception — **but only when the C API itself distinguishes those two states in its contract**.

## 10. Special Case: A Sentinel Value Can Also Be a Successful Result

Some functions such as `strtol` or POSIX `getpriority` can return a value that collides with the error sentinel. In that case, **the return value must still be read first**, but the return value alone is not enough to classify the outcome.

Per each API's documentation, the pattern may look like:

```c
errno = 0;                  /* Set BEFORE the native call. */
long value = strtol(s, &end, 10);

if (/* contract says range error based on value AND errno */) {
    /* Check captured/saved errno, e.g. ERANGE. */
}
/* Check end pointer to know whether any digits were converted. */
```

This is a **C sketch**, not a standalone runnable program. `strtol` requires checking `endptr`, `ERANGE`, `LONG_MIN`/`LONG_MAX`, and C runtime locale/range rules; it cannot be decided by a single condition `result == -1`. In particular, on Windows LLP64 C `long` is typically 32-bit, whereas on Linux LP64 it is typically 64-bit; you must map the right ABI into `FunctionDescriptor`.

If FFM needs the “reset errno before call” pattern, prepare a native wrapper that sets `errno` on **the appropriate thread/CRT** and then calls the target function in the same critical sequence; **do not** set 0 into the Java capture-state buffer to simulate it.

Key takeaway: **“check the return value first”** does not mean “never inspect errno if the return value could be valid.” It means **start from the return contract**, then use the combination of return value and error state exactly as the contract specifies.

## 11. Java Exceptions and Native Errors Are Two Different Channels

A native function can return `-1` **without throwing a Java exception**. An FFM downcall usually returns the value directly according to the ABI; it does not automatically know that `-1` means “file not found.”

Conversely, Java code can receive an exception before the native function actually runs:

- `IllegalCallerException` if native access has not been granted for the restricted operation.
- `NoSuchElementException` if `SymbolLookup.findOrThrow("name")` cannot find the symbol.
- `WrongMethodTypeException` if `MethodHandle.invokeExact` has a mismatched signature.
- `IllegalArgumentException` or `IllegalStateException` due to layout/memory scope/misalignment/lifetime.
- Linker errors due to an invalid `FunctionDescriptor` or unsupported ABI.

**These errors do not require looking up `errno` from some C call.** A Java linking or method-handle exception also does not guarantee that the native function was ever invoked. You must distinguish the Java/JVM channel from the error code **returned by the native function according to its API contract**.

The opposite warning also applies: a wrong descriptor that still happens to be callable can cause a JVM crash or memory corruption without necessarily throwing a Java exception. Therefore you must verify the C prototype, pointer size, signedness, calling convention, and struct layout.

## 12. Save the Captured Error Code Before Doing Anything Else

A downcall with a capture buffer provides a snapshot **immediately after the call**. However, if you **reuse that same buffer for the next call**, the field data will be overwritten. Save the code in a primitive Java variable:

```java
MemorySegment pointer =
        (MemorySegment) FOPEN.invokeExact(state, name, mode);

if (pointer.address() == 0) {
    int originalErrno = (int) ERRNO.get(state, 0L);

    // From here on, originalErrno is safe from state overwrites
    // by other downcalls or changes to native TLS errno.
    logFailure(originalErrno); // Application-defined function.
}
```

**This is a snippet**, assuming `FOPEN`/`ERRNO`/`state`/`name`/`mode` and `logFailure` exist in the class.

Do not read `state` after calling another function linked with `captureCallState` using **the same buffer** and assume it is still `FOPEN`'s error code.

### 12.1. Each Call or Each Thread Must Have Appropriate Capture Storage

`errno` and Windows last-error are states associated with a **native thread**. FFM writes the snapshot into the caller-supplied `MemorySegment`. If two Java threads share **one mutable capture segment** without synchronization, the captured result can be overwritten by another call.

Simple pattern: allocate a **separate** `MemorySegment` state **per native call** or per controlled call sequence, for example inside `try (Arena arena = Arena.ofConfined())` on the same thread. Do not pass a confined `MemorySegment` to another thread; do not retain capture state after the arena closes.

If multithreading is needed, use separate state buffers allocated from an appropriate arena or manage synchronization properly. Save the error state into an `int` or Java record immediately after determining failure so the information does not depend on the lifetime of the capture memory.

### 12.2. An Error Code Is Not a Resource Handle

An `errno` is just a number and does not require `free`. However, a successful `fopen` returning `FILE*` must be paired with `fclose`, even if you do not need to read or write. `GetFileAttributesW` does not return a resource handle; `CreateFileW` returns a HANDLE that must be closed with the proper API if it succeeds. Do not confuse cleanup responsibilities with status-reading responsibilities.

## 13. Designing an FFM Wrapper: Return Clear Java Values, Do Not Hide Native Errors

A good wrapper acts as the boundary between the Java application and the C API:

```text
Java service calls wrapper
       |
       v
FFM downcall -> native return + captured state
       |
       v
Check native return contract
       |
       +-- SUCCESS -> produce Java result, manage native resource
       |
       +-- END/EMPTY/NOT_FOUND -> Java EOF/Optional/empty outcome
       |                          (if defined by the contract)
       |
       +-- FAILURE -> read captured error code if needed
                      -> translate/throw/report with context
```

A design example can use a dedicated exception holding three fields:

```java
public final class NativeCallException extends RuntimeException {
    private final String operation;
    private final String errorDomain;
    private final int code;

    public NativeCallException(
            String operation, String errorDomain, int code) {
        super(operation + " failed: " + errorDomain + "=" + code);
        this.operation = operation;
        this.errorDomain = errorDomain;
        this.code = code;
    }

    public String operation() { return operation; }
    public String errorDomain() { return errorDomain; }
    public int code() { return code; }
}
```

This is a **standalone compilable Java class**, though it has no `main` because it is just an application exception model. When throwing:

```java
if (file.address() == 0) {
    int errno = (int) ERRNO.get(state, 0L);
    throw new NativeCallException("fopen", "errno", errno);
}
```

is a **usage snippet**, requiring the defined variables and class. The `errorDomain` field keeps `errno`, `GetLastError`, `WSAGetLastError`, or direct return codes like `EAI_*` distinct; do not lump every integer into a single wrong-platform error message table.

### 13.1. Provide Enough Context Without Exposing Sensitive Data

A useful error message states the native function, status, error domain, error number, and appropriate resource details (such as file type or action). For user paths or sensitive data names, consider logging/redaction before writing everything to logs.

You should not format an error by calling another native function **before saving** the original error code. After saving it as a Java number, you can call `strerror`/`FormatMessage` or perform other handling according to the ownership/lifetime of the returned string. Avoid `reinterpret(Long.MAX_VALUE)` on an arbitrary string pointer just to read a message if you do not know its bounds.

### 13.2. Retry Policy Based on Specific Error Codes

Do not retry every error just because `errno != 0`. POSIX examples:

- `EINTR`: many functions can be interrupted by a signal; retrying may be appropriate depending on the contract and semantics.
- `EAGAIN`/`EWOULDBLOCK`: for nonblocking I/O, a “no data currently available / not ready” condition may need an event loop rather than a busy loop.
- `ENOENT`: a nonexistent file is not necessarily a transient error; blind retries will not fix a wrong path.
- `EACCES`: missing permissions should not be retried indefinitely.

Numeric codes and handling belong to **the native function's contract and platform**, not a single universal policy for all syscalls. Do not hardcode an integer like `2` to represent `ENOENT` across all runtimes; use symbolic constants or conversion functions when available.

## 14. Things to Especially Avoid in Code with Consecutive Downcalls

### Anti-pattern A: Checking errno Before the Return Value

```java
MemorySegment result =
        (MemorySegment) TMPFILE.invokeExact(state);
int errno = (int) ERRNO.get(state, 0L);

if (errno != 0) {
    throw new IllegalStateException("tmpfile failed");
}
// WRONG: may throw even when result is a valid pointer.
```

**Fix:** only read the error and throw when `result.address() == 0`. If the pointer is valid, use it and then `fclose` at the appropriate time.

### Anti-pattern B: Misclassifying the Return Status

```java
int fd = (int) OPEN.invokeExact(state, path, flags);
if (fd == 0) {  // WRONG for POSIX open: fd = 0 can be valid.
    throw new IOException("open failed");
}
```

**Fix:** base the check on `fd == -1` in the `open` contract. This snippet assumes the C prototype/layout is correct and `OPEN` is already linked, not a full program.

### Anti-pattern C: Calling Another Native Function Before Saving the Error Code

```java
MemorySegment result =
        (MemorySegment) FOPEN.invokeExact(state, name, mode);

if (result.address() == 0) {
    // Another downcall using the SAME state can overwrite the snapshot.
    doSomeOtherDowncall(state);
    int wrongErrno = (int) ERRNO.get(state, 0L);
}
```

**Fix:** copy `int originalErrno = ...` **before** any downcall that reuses `state`. This bug is independent of the bug of reading native `errno` directly after return.

### Anti-pattern D: Treating a Java Error as a C Error

```java
try {
    int value = (int) handle.invokeExact(...);
} catch (WrongMethodTypeException e) {
    // WRONG: cannot assume a valid errno from a native call exists.
}
```

The code above is **pseudocode** for an invocation without context. A `MethodHandle` error is a Java type-signature/linking issue. Handle it independently; do not generate reports like “native call errno = ...” when the native function may not have run at all.

### Anti-pattern E: Reading GetLastError for a C Runtime Function

```text
fopen() returns NULL
    -> use C runtime errno, per the fopen contract

GetFileAttributesW() returns INVALID_FILE_ATTRIBUTES
    -> use Win32 GetLastError, per the Win32 contract

WinSock API returns socket sentinel
    -> use WSAGetLastError if documented by the API
```

Mixing error domains easily leads to **unrelated** error codes and wrong diagnoses.

## 15. Code Review Checklist for a Downcall Wrapper

1. **Prototypes:** Does `FunctionDescriptor` match the function name and native ABI? Is the return `ADDRESS`, `JAVA_INT`, `JAVA_LONG`, or a struct?
2. **Native status contract:** Does the API report success/failure via `NULL`, `-1`, `0`, `HRESULT`, `INVALID_HANDLE_VALUE`, `size_t(-1)`, or a direct value?
3. **EOF/partial:** Are 0 or short results normal? Are `feof`/`ferror` needed?
4. **Error domain:** On failure, should you use `errno`, `GetLastError`, `WSAGetLastError`, `EAI_*`, or a separate output parameter?
5. **Capture timing:** Is `captureCallState("...")` present for the required channel to snapshot immediately after the downcall? Or does a C wrapper save it at the right moment?
6. **Capture buffer:** Does `state` have the right `captureStateLayout()`, alignment, and lifetime? Is it shared across threads/calls without synchronization?
7. **Parameter order:** Does the `MethodHandle` add `MemorySegment state` in the right position after the bound/unbound function address?
8. **Decision order:** Does the code **check the result first** and only read the error code if the contract requires it?
9. **Preserve code:** If logging, retrying, or making further native calls is needed, is the error code copied into a Java variable before the snapshot is overwritten?
10. **Success path:** Does the code mistakenly treat `errno != 0` or `GetLastError != 0` as an error even when the result succeeded?
11. **Ownership:** Which API must close/free a handle/pointer returned by a native call, and within what lifetime?
12. **Exceptions:** Does the wrapper distinguish Java linking/memory exceptions from native error codes?
13. **Platforms:** Do error names, codes, library symbols, and native type sizes vary by OS/ABI?
14. **Tests:** Are success, failure, nonzero stale error on success, EOF/partial, invalid arguments, and cleanup all tested?

## 16. Self-Check Exercises

**Question 1.** `fopen` returns a non-NULL `FILE*` but the capture buffer shows `errno = 2`. Should you throw a “file does not exist” exception?

**Answer:** No. According to the `fopen` contract, a non-NULL pointer is success. A nonzero `errno` on success may be stale state or an unrelated change.

**Question 2.** `fopen` returns NULL. What should you read and when?

**Answer:** The native function reported failure, so read the `errno` **captured by FFM immediately after the call**, save it into an `int`, and then report/throw according to policy.

**Question 3.** `read` returns `0` in POSIX I/O. Should you throw an exception because `errno != 0`?

**Answer:** Normally no. `read` returning 0 indicates EOF, not an error. Only `-1` reports an error for which `errno` should be used; handle differently if a specific API has its own constraints.

**Question 4.** A native `open` returns file descriptor `0`. Is it valid?

**Answer:** Yes. FD 0 can be reused; the error condition is `-1` according to the POSIX `open` contract.

**Question 5.** `getaddrinfo` returns `EAI_NONAME`. Should you use `errno` to determine the error?

**Answer:** No. `getaddrinfo` returns `EAI_*` directly. Use the return code and `gai_strerror`; `errno` is only auxiliary for certain codes such as `EAI_SYSTEM`.

**Question 6.** Why does `captureCallState("errno")` add a parameter to `MethodHandle` without adding a parameter to the actual C function?

**Answer:** The new parameter is a `MemorySegment` used by the linker as a **snapshot buffer for execution state**. For a bound handle, it precedes the C arguments; for an unbound handle, it follows the target function address.

**Question 7.** Does calling `state.set(..., 0)` before a call set the native thread's `errno` to 0?

**Answer:** No. That is only the Java buffer for captured data. If the contract requires resetting native `errno`, it must be performed via the actual C/native runtime on the right thread.

**Question 8.** Win32 `GetFileAttributesW` returns `-1` as a Java `int`. Should you use `GetLastError` or `errno`?

**Answer:** `GetLastError` per the Win32 contract, via `captureCallState("GetLastError")`. `-1` represents `INVALID_FILE_ATTRIBUTES == 0xFFFFFFFF` of `DWORD`.

**Question 9.** A WinSock function reports errors via `WSAGetLastError`. Is using `GetLastError` always correct?

**Answer:** No. Windows Sockets has its own `WSAGetLastError` channel; you must check the documentation of the function being called.

**Question 10.** You reuse the same `MemorySegment callState` for two downcalls. After the second call, is the `errno` in the buffer necessarily the error code from the first call?

**Answer:** No. The second downcall with the capture option can overwrite it. Save `int code = ...` from the first call immediately after determining failure.

**Question 11.** `tmpfile()` returns a valid pointer and `errno` is nonzero. What should you do?

**Answer:** Treat `tmpfile` as successful, use the pointer, and call `fclose` on time. Do not turn a stale error code into an exception.

**Question 12.** A `MethodHandle.invokeExact` throws `WrongMethodTypeException`. Can you conclude the native function returned an error and read `errno`?

**Answer:** No. This is a Java signature error, and the native call may not have been executed. You must fix the descriptor/cast/invocation.

**Question 13.** When `strtol` can return a value that collides with an error sentinel, can you rely solely on `result == -1`?

**Answer:** No. You need `strtol`'s contract regarding `errno`/`ERANGE`, `endptr`, and possibly resetting native `errno` before the call; at the same time, you must map C `long` accurately per the ABI.

**Question 14.** Why does an error code captured in time still not automatically become a Java exception?

**Answer:** FFM only brings the native error state number into the buffer. The Java wrapper must read **the result per the contract**, then decide whether to report an error, retry, return `Optional.empty`, or throw an exception.

## 17. End-of-Lesson Summary

- **The return value is the starting point.** Read “Return value / Errors” of the exact native function and identify sentinels, EOF, partial results, or direct error codes.
- **errno/GetLastError is not a boolean failure flag.** It can be nonzero even when a call succeeds; do not use it alone for classification.
- **captureCallState snapshots in time**, but **reading/interpreting it is conditional** on the native result.
- **When a call fails**, save the error code in a Java variable before reusing the capture buffer or calling another native API.
- **Do not mix error domains:** C `errno`, Win32 `GetLastError`, WinSock `WSAGetLastError`, `EAI_*`, `HRESULT`, and Java exceptions belong to different contracts.
- **FFM does not automatically close handles**, does not automatically throw exceptions for every C sentinel, and does not guarantee memory safety if `FunctionDescriptor`/ABI is declared incorrectly.
- **Good testing** must include a success case with a nonzero stale error code, not just a single failure case.

## Reliable References

- [Oracle Java SE 24 — Checking for Native Errors Using errno](https://docs.oracle.com/en/java/javase/24/core/checking-native-errors-using-errno.html)
- [Oracle Java SE 24 — Linker.Option.captureCallState / captureStateLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.Option.html)
- [Oracle Java SE 24 — Linker and downcallHandle](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 24 — FFM API Overview](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html)
- [man7.org — errno(3), when errno is meaningful and errno on success](https://man7.org/linux/man-pages/man3/errno.3.html)
- [man7.org — fopen(3), FILE* or NULL](https://man7.org/linux/man-pages/man3/fopen.3.html)
- [man7.org — getaddrinfo(3), returning EAI_* directly](https://man7.org/linux/man-pages/man3/getaddrinfo.3.html)
- [Microsoft Learn — GetLastError, conditions and timing for reading](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror)
- [Microsoft Learn — GetFileAttributesW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileattributesw)
- [Microsoft Learn — CloseHandle return value](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle)
- [Microsoft Learn — WSAGetLastError](https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-wsagetlasterror)
- [JEP 454 — Foreign Function & Memory API, final from JDK 22](https://openjdk.org/jeps/454)

**Conclusion:** in FFM, **error codes are only meaningful under the conditions set by the native function's own contract**. Check the return value first; only when it reports an error should you read the exact state saved by `captureCallState`, then report the error and perform appropriate cleanup. **Start from the return contract, not from errno.**
