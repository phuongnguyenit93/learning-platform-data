# Capturing errno or Platform Errors with captureCallState

## Objectives

When Java calls a C function through the **Foreign Function & Memory API (FFM)**, many native functions report errors via a **return value** while simultaneously setting an error state on the **current thread**, rather than throwing a Java exception themselves. On C/POSIX systems, the typical state is **errno**. On Windows, many Win32 APIs use **GetLastError**, while Winsock has **WSAGetLastError**. You cannot read all of these errors by looking only at the return value, nor can you assume the Java runtime will preserve the thread-local error state after the native function finishes.

Starting in JDK 22 (standardized FFM API, JEP 454), **Linker.Option.captureCallState(...)** allows attaching an operation that **captures the error state immediately after the downcall** to the **MethodHandle** calling the native function itself. The result is written into an application-provided **MemorySegment** whose structure is described by **Linker.Option.captureStateLayout()**.

This lesson focuses on:

1. Reading the native function's error contract correctly: return value, errno, Win32 last error, and Winsock error.
2. Creating a downcall with **captureCallState("errno")** or a supported platform state name.
3. Allocating the capture-state segment with the proper size/alignment and reading it with a **VarHandle**.
4. Understanding the position of the additional **MemorySegment** parameter in the **MethodHandle**, as distinct from the actual C parameters.
5. Running a C + Java example that verifies errno without hard-coding the EINVAL number for every system.
6. Avoiding reading stale errors, reading from the wrong thread, reusing a buffer across multiple threads, or miscombining the **critical** option.

**Version:** The full Java example uses standard **java.lang.foreign** in **JDK 22+**. JDK 21 used preview APIs and JDK 17 incubator APIs differ from the example. Some later JDKs may add features, but the descriptions and main code snippets below target the **JDK 22 contract**, so you only need normal **javac/java** commands with **--enable-native-access=ALL-UNNAMED** when performing restricted native operations.

## 1. Why Do We Need to Capture Errors Immediately After a Foreign Call?

Consider a C function:

~~~c
#include <errno.h>

int parse_native_input(void) {
    errno = EINVAL;
    return -1;
}
~~~

If Java calls that function via an FFM downcall, there are two meaningful components:

- **return = -1**: according to the function's own contract, this is the failure signal.
- **errno = EINVAL**: additional information about the error type on the native thread that executed the call.

That is **a C fragment**, not a standalone program, and it does not assert that every C function returns -1 on error. Some functions return **NULL**, **EOF**, another negative value, a direct error code, or a struct. Some functions **do not use errno**, or only set errno in specific cases. **You must read the native function documentation before choosing how to analyze errors.**

A common design mistake:

~~~text
Java calls C function -> C sets errno -> FFM returns to Java
                                           |
                                    Java calls another function
                                           |
                                    tries to read errno late
                                           |
                                    may have already been modified
~~~

**errno is thread-local state**, usually represented by a macro in the C library, not an immutable global integer that Java can arbitrarily read at any time. Java/the VM or a subsequent native call can affect that state. Looking up the address of **errno** as a global variable symbol is also not portable.

**captureCallState** solves the *capture timing* problem: when the downcall finishes, the linker retrieves the requested values directly within the native call mechanism and writes them into a snapshot segment, before subsequent operations can overwrite the value you need to read.

Diagram:

~~~text
          Java application
               |
               | MethodHandle with captureCallState("errno")
               v
       +--------------------+
       | native C function  |
       | return result      |
       | set thread errno   |
       +--------------------+
               |
               v
      Linker captures errno
               |
               +--> capture-state MemorySegment
               |
               v
         Java continues running
               |
               +--> check return value
               +--> if failed, read errno from snapshot
~~~

**Capturing state does not automatically turn a native failure into an exception.** Java still has to check the return code or API contract and decide whether to throw an exception, retry, log, or handle a fallback.

## 2. captureCallState Is a Linker.Option, Not an errno-Reading Function

Core APIs in JDK 22:

~~~java
Linker.Option option =
        Linker.Option.captureCallState("errno");

StructLayout stateLayout =
        Linker.Option.captureStateLayout();
~~~

**captureCallState(String... capturedState)** creates a **linker option** defining which state names to capture. Supported names are platform-dependent and case-sensitive according to their exact names.

**captureStateLayout()** returns a **StructLayout** representing the storage area for states supported by the platform. This layout may contain **named ValueLayouts** and **padding**. Never assume errno is at byte offset 0, that the layout is exactly 4 bytes, or that Windows has the same fields as Linux.

Some states commonly described in the JDK documentation:

| Capture name | Ecosystem | Meaning source |
| --- | --- | --- |
| **"errno"** | C runtime / POSIX and supported environments | C runtime **errno**-style error of the current thread |
| **"GetLastError"** | Windows Win32, when supported by the platform | Last error code of Windows API per each function's contract |
| **"WSAGetLastError"** | Windows Winsock, when supported by the platform | Winsock error code for socket APIs |

The names **GetLastError/WSAGetLastError** are not expected to exist on Linux or macOS. Do not convert Winsock errors to errno yourself; these are different error domains with different meanings and code tables.

**If you choose a name not supported by the platform, captureCallState may throw IllegalArgumentException immediately when creating the option.** Before linking, check the list of names using the actual layout.

### Listing Supported State Names

**File CaptureNames.java:**

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.util.List;
import java.util.Optional;

public class CaptureNames {
    public static void main(String[] args) {
        StructLayout layout = Linker.Option.captureStateLayout();

        List<String> names = layout.memberLayouts().stream()
                .map(MemoryLayout::name)
                .flatMap(Optional::stream)
                .sorted()
                .toList();

        System.out.println("capture layout bytes = "
                + layout.byteSize());
        System.out.println("supported states: " + names);
    }
}
~~~

Run on JDK 22+:

~~~bash
javac CaptureNames.java
java CaptureNames
~~~

**Output is platform-dependent.** A typical Linux JDK build might list **errno**; a Windows JDK build might list **errno**, **GetLastError**, **WSAGetLastError**. Do not expect a fixed stdout for this program because the number of fields and padding depend on the JDK/ABI. The value of **layout.byteSize()** is also not a constant that can be hard-coded for all platforms.

**Note:** **captureStateLayout()** describes the states *potentially supported*, whereas **captureCallState(...)** specifies the states actually requested to be saved. If you only capture **errno**, do not treat other fields present in the layout as a valid snapshot of that same call.

## 3. Linking a Downcall with captureCallState

Suppose native C has the signature:

~~~c
int fail_with_einval(void);
~~~

Describe the **native signature**:

~~~java
FunctionDescriptor descriptor =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);
~~~

The native function **takes no C parameters** and returns an int. Once you obtain the symbol **target**, link it:

~~~java
MethodHandle fail = Linker.nativeLinker().downcallHandle(
        target,
        FunctionDescriptor.of(ValueLayout.JAVA_INT),
        Linker.Option.captureCallState("errno"));
~~~

**This is a fragment**; **target** must be a valid MemorySegment symbol. A common point of confusion is that the **MethodHandle** in Java has an extra parameter to pass the capture-state segment, even though the C function **does not** have that parameter:

~~~text
C function:            int fail_with_einval(void)

Java MethodHandle:     (MemorySegment capturedState) -> int

Calling from Java:     int result =
                           (int) fail.invokeExact(capturedState);
~~~

**The capture-state segment is a parameter used by the linker**, not passed as an argument to the actual C function. Adding it to **FunctionDescriptor** as a C ADDRESS parameter is a **wrong native signature**, which can lead to a crash/undefined behavior.

### Bound versus unbound downcall handle

There are two common ways to link:

- **Bound handle:** **downcallHandle(target, descriptor, option)** already binds the function address, so Java code passes **capturedState** followed by the normal native arguments.
- **Unbound handle:** **downcallHandle(descriptor, option)** leaves the function address to be supplied at invoke time; Java code passes **targetAddress** first, followed by **capturedState** and the native arguments.

For a C function **int add_and_set_error(int x)**, for example:

~~~text
C:                      int f(int x)

Bound Java handle:      (MemorySegment capturedState, int x) -> int

Unbound Java handle:    (MemorySegment targetAddress,
                         MemorySegment capturedState, int x) -> int
~~~

This is the diagram for a function returning a scalar. If the native function **returns a struct by value**, the linker may also require a **SegmentAllocator** and a special parameter order; always check **MethodHandle.type()** and the JDK javadoc for the actual descriptor/options instead of guessing.

A common mistake is trying to invoke a bound handle as usual while forgetting the state:

~~~java
// Wrong if the handle was linked with captureCallState:
int value = (int) fail.invokeExact();
~~~

This statement will encounter **WrongMethodTypeException** or a mismatch at invoke time, because the downcall handle already has the capture-state parameter.

## 4. Allocating the Capture-State Segment Properly and Reading Fields

To read errno:

~~~java
StructLayout stateLayout =
        Linker.Option.captureStateLayout();

VarHandle errnoField = stateLayout.varHandle(
        MemoryLayout.PathElement.groupElement("errno"));
~~~

**VarHandle** accesses the field named **errno** in the StructLayout. It obtains the offset and alignment from the layout, without needing to hard-code positions.

Allocate a **native MemorySegment** with the exact layout:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment captured = arena.allocate(stateLayout);

    int result = (int) fail.invokeExact(captured);
    int errnoValue = (int) errnoField.get(captured, 0L);

    // Analyze result and errnoValue according to the function's contract.
}
~~~

This is a **fragment** of a method declared **throws Throwable** that already has **fail**, **stateLayout**, and **errnoField**. **0L** is the base offset in the VarHandle usage from **MemoryLayout.varHandle** in JDK 22; the **get** method has coordinates **(MemorySegment, long)**.

**Why use arena.allocate(stateLayout)?**

- The segment is allocated according to the **byteSize** and **byteAlignment** returned by the JDK.
- The capture-state is stored in native memory, within the thread's access scope.
- Inside **try-with-resources**, the segment is not freed before the code reads it.
- There is no need to guess the individual size/alignment of errno or the platform's number of fields.

Do not use an arbitrary small **MemorySegment.ofArray(byte[])** or put the state in a Java object and expect the linker to accept it as a native capture-state buffer. **captureCallState** requires a native segment whose size/alignment is compatible with **captureStateLayout()**.

**Reading the state after the downcall** is sufficient; you do not need to call another native function to read errno. Reading after the arena has been closed violates lifetime. If the state resides in a shared arena and is used from multiple threads, do not let threads write to the same capture-state region concurrently.

### Should errno Be Reset to 0 Before the Call?

There are native functions documented to require the caller to clear errno before calling, because the return value may be valid even if it equals a sentinel value. In that case, resetting must follow the specific native contract, performed directly on the **thread used for the downcall**, in a portable/ABI-compliant way (for example, through a C helper).

**Do not confuse writing 0 into the capture-state segment with clearing the actual thread-local errno.** In **JDK 22**, captureCallState is a **post-call capture** mechanism. It is not a promise that calling **errnoField.set(captured, 0L, 0)** will actually set the C runtime's errno=0. If you need to reset errno, do so using an appropriate native mechanism before calling the target function; the capture-state segment is where the linker writes the snapshot after the downcall.

## 5. End-to-End Linux Demo: Generating a Controlled errno Error

To avoid relying on whether a file exists or what value **EINVAL** has on a given machine, we build a small C library with two functions:

1. **fail_with_einval()** sets errno=EINVAL and returns -1.
2. **native_einval()** returns the EINVAL constant of the very C runtime used to build the library.

The Java program captures errno from the first call and compares it with the constant returned by the second call. The check outputs **true** if capture works, regardless of whether EINVAL is 22, 22 on another common platform, or a different number on a supported ABI.

### 5.1. Native File: probe_errno.c

~~~c
#include <errno.h>

/*
 * On Linux, the visibility attribute makes symbols easy to find in the .so.
 * This is C11 code for the Linux GCC/Clang example.
 */
#if defined(__GNUC__)
#define EXPORT __attribute__((visibility("default")))
#else
#define EXPORT
#endif

EXPORT int fail_with_einval(void) {
    errno = EINVAL;
    return -1;
}

EXPORT int native_einval(void) {
    return EINVAL;
}
~~~

**Explanation:** **errno** is a macro accessing the C thread's error state. **EINVAL** is the error code for invalid argument in C/POSIX, though its numeric value is platform-dependent. The native function always returns **-1** and always sets **errno=EINVAL** before returning. The **native_einval** function provides the reference constant without forcing Java code to hard-code the error code.

The functions take no parameters and return a **C int**. On Linux/x86-64 and many common ABIs, C int corresponds to Java **ValueLayout.JAVA_INT** (4 bytes). This is an ABI assumption of the example; for real libraries, check the canonical C int layout and the proper calling convention.

### 5.2. Java File: CaptureErrnoDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.nio.file.Path;

public class CaptureErrnoDemo {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        StructLayout capturedLayout =
                Linker.Option.captureStateLayout();

        VarHandle errnoField = capturedLayout.varHandle(
                MemoryLayout.PathElement.groupElement("errno"));

        try (Arena arena = Arena.ofConfined()) {
            // The .so file is built in the project's "build" directory.
            Path library = Path.of(
                    "build", "liberrno_probe.so").toAbsolutePath();

            SymbolLookup nativeLib =
                    SymbolLookup.libraryLookup(library, arena);

            MemorySegment failSymbol = nativeLib
                    .find("fail_with_einval").orElseThrow();
            MemorySegment expectedSymbol = nativeLib
                    .find("native_einval").orElseThrow();

            FunctionDescriptor noArgInt =
                    FunctionDescriptor.of(ValueLayout.JAVA_INT);

            // Bound handle: capture segment is the first parameter.
            MethodHandle fail = linker.downcallHandle(
                    failSymbol,
                    noArgInt,
                    Linker.Option.captureCallState("errno"));

            // Normal handle: native_einval(void) returns an int.
            MethodHandle expectedHandle = linker.downcallHandle(
                    expectedSymbol,
                    noArgInt);

            MemorySegment captured = arena.allocate(capturedLayout);

            // Linker captures errno into captured immediately after the native call.
            int result = (int) fail.invokeExact(captured);
            int errnoValue = (int) errnoField.get(captured, 0L);

            // Another downcall cannot alter the saved snapshot.
            int expected = (int) expectedHandle.invokeExact();

            System.out.println("return = " + result);
            System.out.println("errno matches EINVAL = "
                    + (errnoValue == expected));
            System.out.println("errno is nonzero = "
                    + (errnoValue != 0));

            if (result != -1 || errnoValue != expected) {
                throw new AssertionError(
                        "native error/capture mismatch");
            }
        }
    }
}
~~~

**A very important point to learn:** The program **reads errno from the capture segment before** calling **native_einval()**. Even if the helper is called afterward, the value in the segment remains the snapshot written from the **fail_with_einval()** call. You do not need to rely on the thread's errno variable after other native calls have run.

**SymbolLookup.libraryLookup(path, arena)** keeps the library alive for the lifetime of the arena. Do not retain the symbol or MethodHandle to call after closing the arena; the downcall target address may no longer be valid if the native library is unloaded.

### 5.3. Compiling and Running on Linux

Requires **JDK 22+** and a C compiler compatible with the OS/JVM architecture:

~~~bash
mkdir -p build

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  probe_errno.c -o build/liberrno_probe.so

javac -d build CaptureErrnoDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build CaptureErrnoDemo
~~~

The **--enable-native-access=ALL-UNNAMED** flag grants permission to use restricted FFM functions for classpath code not belonging to a named module. On JDK22, **--enable-preview** is not needed for the standardized FFM APIs. If you move the class into a named module, you must grant native access to the corresponding module name.

### 5.4. Verifiable Stdout

If the library loads and the example runs properly:

~~~text
return = -1
errno matches EINVAL = true
errno is nonzero = true
~~~

**Do not print a fixed errno value** because the standard does not require EINVAL to equal the same number on every OS. The C helper itself provides the reference value. Each downcall is a real native operation, not Java simulating errno.

If the **java** command reports that the library cannot be found, check the absolute path from the current working directory and confirm that **liberrno_probe.so** was built. If symbol names are missing, check that the .so file actually exports **fail_with_einval** and **native_einval**, as well as architecture and ABI compatibility. If running on Windows/macOS, use the corresponding shared library name and toolchain; the GCC command and .so name above are specific to Linux.

## 6. Illustrating with Standard C APIs like fopen: Errors Only Have Meaning When the Result Fails

On Linux/POSIX, **fopen** has the signature:

~~~c
FILE *fopen(const char *filename, const char *mode);
~~~

With mode **"r"**, if the file does not exist or cannot be read, **fopen** returns **NULL** and sets errno to indicate the cause. However, if **fopen** succeeds, **errno** *is not guaranteed to be 0*. It may still hold a value from a previous operation, because many C functions do not reset errno on success.

Correct Java flow:

~~~text
fopen(path, "r") via captureCallState("errno")
          |
          v
    Is result NULL?
        /       \
      Yes        No
      |           |
  read errno    keep FILE*
  from snapshot call fclose after use
      |
  handle error
~~~

If using the standard C library through **Linker.nativeLinker().defaultLookup()**, you can link **fopen** with:

~~~java
// Fragment for environments where the fopen symbol is in defaultLookup.
Linker linker = Linker.nativeLinker();
MemorySegment fopenSymbol =
        linker.defaultLookup().find("fopen").orElseThrow();

MethodHandle fopen = linker.downcallHandle(
        fopenSymbol,
        FunctionDescriptor.of(
                ValueLayout.ADDRESS,
                ValueLayout.ADDRESS,
                ValueLayout.ADDRESS),
        Linker.Option.captureCallState("errno"));
~~~

The native descriptor contains return **FILE*** (address) and two C parameters of type **char***. The resulting **bound** MethodHandle has the shape:

~~~text
(MemorySegment capturedState,
 MemorySegment filename,
 MemorySegment mode) -> MemorySegment
~~~

Example invocation fragment (inside an active **Arena**, with **fopen** already linked):

~~~java
MemorySegment captured = arena.allocate(
        Linker.Option.captureStateLayout());
MemorySegment filename = arena.allocateFrom(
        "file-that-should-not-exist.txt");
MemorySegment mode = arena.allocateFrom("r");

MemorySegment file = (MemorySegment) fopen.invokeExact(
        captured, filename, mode);

if (file.equals(MemorySegment.NULL)) {
    int code = (int) errnoField.get(captured, 0L);
    System.out.println("native fopen error code = " + code);
}
~~~

This is a **fragment**, not a standalone program: it needs imports, **arena** and **errnoField**, an exception declaration, and **fclose** cleanup if the file opens successfully. The filename only illustrates the scenario; do not assume it does not exist in every working directory. Do not print a fixed stdout for errno because the error could be **ENOENT, EACCES**, or another error depending on the OS/filesystem.

**FILE* is not a Java object and must not be freed directly by an Arena.** If **fopen** returns a valid pointer, you must call **fclose** per the C library contract. Capturing errno does not replace resource cleanup.

### strerrror/strerror and Error Messages

A native **strerror(errno)** can return the message for a C errno code, but:

- Message text depends on the OS, locale, and C library;
- **strerror** may use a static buffer or have thread-safety constraints depending on the runtime;
- If calling another C function to format the error message, **capture and read errno first**;
- The returned C pointer has a lifetime/bounds that must be understood before reading via Java FFM.

Only log messages in environments where the API is verified, and do not rely on fixed English strings for testing.

## 7. Windows: GetLastError and WSAGetLastError Differ from errno

Windows has multiple error namespaces. **captureCallState** lets you select the appropriate platform state if supported by the JDK platform.

| Native API | Typical failure signal | Appropriate state |
| --- | --- | --- |
| C runtime functions (e.g., some file/string APIs) | Per C runtime contract | **errno** |
| Win32 APIs such as **CreateFileW** | **INVALID_HANDLE_VALUE** | **GetLastError** |
| Win32 BOOL-returning APIs | **FALSE** | **GetLastError** per function contract |
| Winsock **socket/recv/send** | **INVALID_SOCKET / SOCKET_ERROR** depending on function | **WSAGetLastError** |
| APIs that return the error directly in the return value | Return code may already be the error | May **not need** captureCallState |

Do not use **GetLastError** to interpret a C runtime function that only specifies errno. Do not use **WSAGetLastError** for Win32 file APIs. Do not assume that identical numeric codes across different error domains share the same meaning.

### Checking Support Before Choosing the Option

~~~java
StructLayout stateLayout =
        Linker.Option.captureStateLayout();

boolean win32Supported = stateLayout.memberLayouts().stream()
        .flatMap(member -> member.name().stream())
        .anyMatch("GetLastError"::equals);

if (win32Supported) {
    Linker.Option win32Option =
            Linker.Option.captureCallState("GetLastError");
    VarHandle win32Field = stateLayout.varHandle(
            MemoryLayout.PathElement.groupElement("GetLastError"));
    // Link the appropriate Win32 downcall with win32Option.
}
~~~

This is a **fragment**; it does not call a Windows function itself. It checks specifically whether **GetLastError** is present in the current capture-state layout. Check **WSAGetLastError** similarly by its own name—do not infer support just from seeing GetLastError.

### Sequence for Calling a Win32 Function

~~~text
1. Link native Win32 function with FunctionDescriptor matching the Win32 ABI.
2. Attach captureCallState("GetLastError") when supported by the platform.
3. Allocate capture segment using captureStateLayout().
4. Invoke downcall, passing capture segment in the right position.
5. Check the return sentinel of the Win32 function itself.
6. Only when the contract confirms failure, read GetLastError
   from the capture-state segment.
7. Translate/log the error code using appropriate means, e.g., FormatMessageW.
~~~

Some Windows APIs allow **GetLastError** to hold information even on success or require special checking logic; always read each function's documentation. **Do not read GetLastError from an earlier native call** after running several other Win32 calls and expect the state to still be accurate.

**Windows error codes are system values and can use unsigned interpretation** when displaying a DWORD. If the carrier is a Java int, **Integer.toUnsignedLong(code)** helps print the 32-bit unsigned range; this does not alter the underlying error. For Winsock, choose the name **WSAGetLastError** instead of the Win32 name, then look up the corresponding **WSA...** code table.

### Conceptual Windows Native Example (Not a Complete Java Program)

~~~c
/* Windows C fragment illustrating Win32 state. */
#include <windows.h>

int fail_win32_demo(void) {
    SetLastError(ERROR_INVALID_PARAMETER);
    return 0;
}
~~~

If you use the linker option **captureCallState("GetLastError")** with that function, the corresponding snapshot is expected to contain the Win32 code **ERROR_INVALID_PARAMETER**. However, exporting the function from a DLL, compiling, linking, ABI handling, and using Windows-specific tooling must be done separately; do not treat this fragment as code that runs on Linux.

**Do not manually map ERROR_INVALID_PARAMETER to EINVAL**. Those are two domains that may have similar meanings, but their mechanisms and encodings are different.

## 8. Why Can't We Just Call errno() from Java Afterward?

**errno** in C is usually a macro that expands to accessing thread-local state via a C runtime-specific function/variable. The exact implementation name varies by platform, such as the thread-local storage mechanism; you should not hard-code addresses or guess symbols.

If Java calls native function A, and then links a function B to query errno:

~~~text
Java
  |
  +-- downcall A (sets errno)
  |
  +-- Java/JVM does other work
  |
  +-- downcall B ("get errno")
~~~

B may read **a modified state**, or a different C runtime/thread-local variable if you linked through a different runtime. The core issue is **timing** and **runtime/thread context**, not merely looking up the right symbol. **captureCallState** folds reading the state into A's linker-orchestrated sequence, avoiding a separate downcall B just to capture the error.

**Limitations:** captureCallState captures only the states supported by the linker. It does not automatically know custom error structures defined by a C library, does not capture arbitrary TLS variables, does not read the errno of another OS thread, and does not keep an error history across multiple calls. For custom error protocols, you must define an appropriate FunctionDescriptor/return struct or helper.

## 9. Do Not Read errno on Success Unless the API Promises to Reset It

An important C rule: **not every native success sets errno to 0**.

Example of buggy logic:

~~~c
int operation(void) {
    if (/* success */ 1) {
        return 42;
    }
    errno = EIO;
    return -1;
}
~~~

This is **C pseudocode** to explain the contract; do not use it directly as a production function. If previous native code set errno=EINVAL and the next operation returns 42 without touching errno, the next capture may still contain a non-zero errno code. This **does not turn returning 42 into an error**.

When Java handles it:

~~~java
int result = (int) call.invokeExact(captured);

if (result == -1) {
    int errno = (int) errnoHandle.get(captured, 0L);
    throw new IllegalStateException(
            "native function failed, errno=" + errno);
}

System.out.println("success = " + result);
~~~

This is a **fragment** assuming the native function has sentinel **-1**, **call** is linked with captureCallState, **captured** and **errnoHandle** are valid, and the code allows throws Throwable. Do not apply **result == -1** to all C/Windows APIs. **The return code determines when errno is meaningful**, unless the function's documentation specifies another rule.

For functions like **strtol**, there are cases where returning **LONG_MAX/LONG_MIN/0** requires distinguishing a valid value from overflow; the C documentation specifies resetting errno before calling and checking afterward. Capturing after the call alone is insufficient if the contract-required reset step is omitted.

## 10. One Call — One Capture Snapshot: Do Not Share Carelessly

For multiple sequential calls, you can reuse one capture-state segment **if you read/copy the needed data before the next invoke**. However, each downcall with captureCallState can overwrite fields in that segment.

~~~text
call A -> captured errno A
             |
             +-- Java reads / saves errno A into a local int
             |
call B -> captured errno B (overwrites the same region)
             |
             +-- Java reads errno B
~~~

Illustrative Java snippet:

~~~java
int resultA = (int) first.invokeExact(state);
int errorA = (int) errnoHandle.get(state, 0L);

int resultB = (int) second.invokeExact(state);
int errorB = (int) errnoHandle.get(state, 0L);

// errorA was saved separately, unchanged when state is overwritten.
~~~

This is a **fragment**; both handles have captureCallState attached and have a FunctionDescriptor returning int with no native parameters. If you want to retain a snapshot longer or compare multiple errors, allocate **two state segments**, or copy the needed fields into Java values/records.

### Multithreading

- A **MethodHandle** linked once can be used from multiple Java threads if the native arguments/objects used all satisfy their contracts.
- **errno** is thread-local: the captured result is tied to the **thread executing the native downcall**, not a process-wide global errno.
- Each thread/invocation should use its **own capture-state segment**, or design synchronization if reuse is needed.
- With **Arena.ofConfined()**, the segment can only be accessed by the thread owning the arena; using it on another thread can cause **WrongThreadException**.
- Using **Arena.ofShared()** does not automatically make multiple threads writing to the same segment safe. Do not let two calls write to the same capture segment without synchronization.

How long a capture-state segment stays alive depends on the arena; closing it and then reading violates MemorySegment lifetime. In particular, **do not keep a reference to a segment from a closed arena** and pass it to a logging thread to read later.

## 11. Relation to Linker.Option.critical(boolean)

FFM has a linker option **critical(boolean allowHeapAccess)** intended for very short native functions that meet strict constraints on JVM interaction. It enables certain optimizations for critical downcalls.

**In JDK 22, captureCallState cannot be combined with critical(boolean).** If a native call needs to capture errno/GetLastError, use a normal downcall with the capture option, and do not force critical just to optimize speed. This is an explicit rule in the JDK 22 API.

Wrong:

~~~java
// Intentionally wrong fragment: invalid option combination on JDK 22.
linker.downcallHandle(
        symbol,
        FunctionDescriptor.of(ValueLayout.JAVA_INT),
        Linker.Option.captureCallState("errno"),
        Linker.Option.critical(false));
~~~

**Do not use critical to call a function that may block, call back into Java, or behave in ways that violate the critical contract**. An invalid option combination may be rejected immediately when the linker creates the MethodHandle. Keep error diagnostics separate from the critical performance concept.

## 12. Native Signatures and ABI Always Matter More Than Plausible-Looking Java Code

**captureCallState only captures state; it does not check whether FunctionDescriptor matches the actual C function.** If you link:

~~~c
int foo(const char *name, size_t length);
~~~

with a descriptor having only one int parameter, you are calling the wrong ABI. At the native level, a mismatch can crash the JVM or corrupt memory, not merely throw a Java exception.

With FFM:

- C **int** typically maps to Java **ValueLayout.JAVA_INT** on common ABIs.
- **char*** is usually **ValueLayout.ADDRESS** and passes a MemorySegment containing a C string with the right encoding/NUL terminator.
- **size_t** has an ABI-dependent size; use **Linker.nativeLinker().canonicalLayouts().get("size_t")** to confirm the mapping instead of assuming long.
- **C long** is 8 bytes on Linux/x64 LP64 but may be 4 bytes on Windows/x64 LLP64.
- A returned pointer may be a zero-length segment; do not dereference out of bounds or past the native object's lifetime.

Capturing error state does not make FunctionDescriptor, Arena, and SymbolLookup automatically safe. The native library must remain alive, memory arguments must remain valid, the thread must have access rights, and native code must adhere to the API contract.

## 13. Practical Operations: Converting Native Errors into Java Exceptions

A Java application should standardize error information into an object with at least three components:

1. **Operation**: the native function or operation that just failed.
2. **Error domain**: **errno**, **GetLastError**, **WSAGetLastError**, or a library-specific code.
3. **Error code + optional text**: the raw integer value and an interpretation based on the corresponding OS/runtime.

Example of FFM-independent Java code to model a result:

~~~java
record NativeFailure(String operation, String domain, int code) {
    String summary() {
        return operation + " failed: "
                + domain + "=" + Integer.toUnsignedString(code);
    }
}
~~~

**This fragment is not a standalone runnable program**. POSIX errno is usually a non-negative int so it can be printed with **Integer.toString(code)**; **Integer.toUnsignedString** illustrates the need to consider Win32 DWORD when interpreting unsigned values. To display messages, use an OS-appropriate translation mechanism; do not hard-code English messages into business logic.

A JDK22 wrapper should look like:

~~~text
request
   |
   v
allocate per-call capturedState
   |
   v
invoke bound MethodHandle
   |
   v
check return according to native API
   |
   +-- success -> use native result, release resources
   |
   +-- failure -> read named field from capturedState
                    |
                    v
              NativeFailure(domain, code)
                    |
                    v
              map to Java exception / retry / status
~~~

**Do not automatically retry every errno**. For example, **EINTR**, **EAGAIN**, **EACCES**, **EINVAL**, and **ENOMEM** have different meanings, retryability, and side effects depending on the API. A call may have partially modified state before returning an error; retry decisions must respect idempotency and the contract.

### Safe Logging

Avoid logging raw paths, credentials, pointer addresses, or user-provided native strings. Always log the **error domain** together with the numeric code because the same number can have different names between POSIX and Windows. For diagnostics when needed, you can log the JDK version, OS/architecture, native library version, and native function name.

## 14. Common Mistakes Table

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Returning a native error code and assuming the JVM will auto-throw | Java continues with wrong results | Check return sentinel, then read capture |
| Reading errno after other native calls | State of the inspected call is lost/swapped | Attach captureCallState to the downcall being tracked |
| Treating errno as a process-global variable | Mixing up codes across threads | Remember errno is thread-local |
| Treating non-zero errno as always a failure | Misclassifying a native success | Check the return contract first |
| Using "GetLastError" on Linux | IllegalArgumentException or unsupported option | List names from captureStateLayout() |
| Using errno for Winsock failures | Wrong error domain | Use WSAGetLastError if supported |
| Hard-coding offset 0 for errno | Reading the wrong field on another layout | VarHandle groupElement("errno") |
| Manually allocating 4 bytes for the snapshot | Fails to meet full layout size/alignment | arena.allocate(captureStateLayout()) |
| Forgetting to pass the capture segment when invoking | WrongMethodTypeException | Follow MethodHandle.type() |
| Putting capturedState into FunctionDescriptor as a C parameter | Wrong ABI, possible crash | Capture is a parameter added by the linker |
| Reading capture only after the arena has closed | Lifetime violation | Read before closing |
| Using the same segment for concurrent calls | Race and overwritten snapshot | Separate state per call/thread |
| Combining captureCallState with critical on JDK22 | Invalid linker option combination | Use a normal downcall |
| Hard-coding EINVAL=22 as a portable test | Test fails on another ABI | Compare against native code returned from the same toolchain |
| Reading fields not selected for capture | Mistaking bytes for captured values | Only trust fields listed in the option |
| Assuming capture replaces fclose/free/CloseHandle | Native resource leak | Manage cleanup per native contract |
| Throwing a Java exception when C returns success with stale errno | False positive | Rely on return sentinel and API contract |
| Calling with the wrong FunctionDescriptor | ABI/memory safety error | Match the C signature and calling convention exactly |

## 15. Implementation Checklist for Each Native Downcall

Before shipping an FFM captureCallState helper to production, verify:

1. Which API does the **native function** belong to? Does it signal failure via NULL, -1, FALSE, INVALID_HANDLE_VALUE, or a direct return error code?
2. Is the **appropriate state** errno, GetLastError, WSAGetLastError, or a custom error object? Some APIs do not need capture.
3. Does the **field name** exist in **captureStateLayout()** on the running JDK/runtime?
4. Does **FunctionDescriptor** match the C signature, scalar widths, calling convention, and pointers?
5. Does the **MethodHandle** have the right additional capture-state parameter? Do bound/unbound handles differ?
6. Is the **capture-state segment** allocated with **arena.allocate(captureStateLayout())** and still alive when read?
7. Does **exception handling** check the return sentinel before interpreting errno?
8. Does the **native API require clearing errno beforehand** or another setup step? If so, perform it properly on the native thread.
9. Does **concurrency** have a separate state segment per call? Does it avoid using a confined segment on the wrong thread?
10. Does **cleanup** close FILE*, socket, HANDLE, Arena, or native resources across all success/failure branches?
11. Does **testing** verify actual errors, including success with stale errno, and at least two platforms if the application is portable?
12. Does **logging** record the error domain and numerical code without assuming fixed messages?

## 16. Self-Check Questions

**Question 1.** A C function returns -1 and sets errno, but Java calls another native function before reading errno. What is the potential bug?

**Answer:** Thread-local errno may have already been modified. Attach **captureCallState("errno")** to the downcall of the function being checked to save the snapshot as soon as the call finishes.

**Question 2.** Having used **captureCallState("errno")**, does the FunctionDescriptor of **int fail(void)** gain an extra C parameter of type ADDRESS?

**Answer:** No. FunctionDescriptor remains **FunctionDescriptor.of(ValueLayout.JAVA_INT)**. The linker adds a **MemorySegment** parameter to the **Java MethodHandle**, while the native C signature does not change.

**Question 3.** Using a bound handle for **int fail(void)** with the capture option, what must the **invokeExact** call pass?

**Answer:** One **capture-state MemorySegment**, followed by no native arguments. For example, **(int) handle.invokeExact(captured)**.

**Question 4.** Should we allocate a 4-byte capture buffer just because errno is usually a 4-byte C int?

**Answer:** No. The capture-state layout is a platform-dependent struct that may contain additional fields/padding and alignment. Use **arena.allocate(Linker.Option.captureStateLayout())**.

**Question 5.** Why can a function returning success with a non-zero captured errno still be valid?

**Answer:** Many C functions do not reset errno on success; it may still hold an error from a prior operation. You must read the documentation and check the return sentinel first.

**Question 6.** Can **captureCallState("GetLastError")** be used verbatim on Linux?

**Answer:** No. This state is Windows-specific and may not be supported. List the names in captureStateLayout() first.

**Question 7.** A Win32 function fails due to the file system; should **WSAGetLastError** or **GetLastError** be used?

**Answer:** If the native function is a Win32 file API and the documentation uses GetLastError, choose **GetLastError**. **WSAGetLastError** is for Winsock.

**Question 8.** Downcall A finishes and captures errno into segment S, then downcall B also captures into S. Reading S at the end will yield A's or B's errno?

**Answer:** Normally the state from call B, which wrote last to the same field. You must save A's errno to a Java local before B runs, or allocate another snapshot.

**Question 9.** Can **captureCallState** be combined with **Linker.Option.critical(false)** on JDK22?

**Answer:** No. The JDK22 documentation explicitly states that this option cannot be combined with critical(boolean).

**Question 10.** Why does the sample program call **native_einval()** instead of comparing the captured errno against the number 22?

**Answer:** EINVAL is a C macro whose value is defined by the C runtime/ABI. Obtaining the reference code from the same toolchain makes the test more portable than hard-coding a numeric value.

### Advanced Exercises

**Exercise A:** In the demo, change **errno=EINVAL** to **errno=EACCES**, and also change the function returning the reference code. Predict that stdout will still have two **true** checks, because the compared code comes from the C runtime.

**Exercise B:** Link an additional C function **int succeed_without_clearing(void) { return 42; }**, attach captureCallState, and call it after fail. Explain why **you must not throw an exception based solely on non-zero errno** if the success contract is returning 42.

**Exercise C:** Create **two capture-state segments** to store the errors of two calls separately. Read both after calling; compare with sharing one segment that gets overwritten.

**Exercise D:** Write the **CaptureNames** program for two machines, Windows and Linux. Print and compare the names, size/alignment of captureStateLayout; explain why code should not hard-code layout offsets.

**Exercise E:** For a Win32 API with documented GetLastError, design a wrapper that stores the operation name, return sentinel, and error code together. Describe where resource cleanup is handled and how a DWORD is converted to an unsigned long when logging.

## Official References

- Java SE 22 API — **Linker.Option.captureCallState / captureStateLayout**, capture parameter order and critical restrictions: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html
- Java SE 22 API — **Linker.downcallHandle**, FunctionDescriptor and native ABI: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Java SE 22 API — **MemoryLayout.varHandle** and groupElement path: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html
- Java SE 22 API — **SymbolLookup.libraryLookup** and lifetime: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- Oracle Java 22 Core Libraries — **Checking for Native Errors Using errno**: https://docs.oracle.com/en/java/javase/22/core/checking-native-errors-using-errno.html
- OpenJDK — **JEP 454: Foreign Function & Memory API**: https://openjdk.org/jeps/454
- Microsoft Win32 — **GetLastError**: https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror
- Microsoft Winsock — **WSAGetLastError**: https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-wsagetlasterror

**Remember:** **captureCallState** is a **Linker.Option attached to a downcall** to save platform error states **immediately after the native call** into a MemorySegment whose layout is provided by the JDK. It **does not replace checking the return value**, does not automatically turn errno into a Java error, does not add parameters to the C signature, does not clear errno by modifying the capture buffer, and does not guarantee that the error domains of POSIX/Win32/Winsock are equivalent.