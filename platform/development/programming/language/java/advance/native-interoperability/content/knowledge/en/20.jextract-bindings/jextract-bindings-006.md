# Separating Generated Code from the Resource-Managing and Data-Validating Wrapper

## 1. Problem Statement and Design Principles

**jextract** is an OpenJDK tool that reads C headers and generates Java bindings based on the **Foreign Function & Memory API (FFM)**. Generated bindings know a great deal about *native signatures*: C function names, C types, `MemoryLayout`, how to look up symbols, and how to create downcall handles. However, they **cannot infer** business rules, trust boundaries, and ownership of a native pointer.

Therefore, there are two Java layers that should be kept separate:

- **Low-level generated binding:** mechanical output of jextract, close to the C ABI, regenerable. Do not inject validation or resource policies into auto-generated source.
- **Handwritten facade (safe wrapper):** stable handwritten class for the application. It accepts Java objects/primitives, validates data, determines who owns the native handle, allocates buffers via `Arena`, checks C status codes, copies output into Java values, closes resources, and prevents calls after close.

You should not let every controller/service import the generated class and call C functions directly. That scatters ownership and causes a single C header change to require edits in many places. The facade consolidates FFM complexity at one boundary that is easy to review/test.

~~~text
Application / Controller / Business service
          |
          | public Java API: int[], exceptions, AutoCloseable
          v
demo.api.CheckedCalc                    [HANDWRITTEN]
  - validate null / max length / value ranges
  - create/close native session exactly once
  - per-call Arena.ofConfined
  - C status -> Java exception
  - copy result into int[] before Arena closes
          |
          | raw C signatures represented as FFM carriers
          v
demo.generated.RawCalc                 [jextract GENERATED]
  - symbols, library loading, downcall handles
  - C int -> Java int; C pointer -> MemorySegment
          |
          v
libsecurecalc.so / .dylib / .dll        [NATIVE LIBRARY]
  - sc_open / sc_scale / sc_close
  - malloc/free; C ABI
~~~

**Key thesis:** jextract generates **bindings**, not a **safe application API**. The name “safe wrapper” does not mean native code has become harmless: wrong ABI, native memory corruption, and use-after-free can still crash the JVM. The goal is to reduce controllable mistakes from the Java side and clarify the native contract.

The main programs are designed for **JDK 22+**, the final FFM release under JEP 454. JDK 21 uses FFM third preview under JEP 442, requires `--enable-preview`, and has API differences. **jextract is not guaranteed to be bundled with the JDK**; choose a jextract version that generates code matching the target JDK.

## 2. Why Can't Generated Code Replace the Wrapper by Itself?

| Question | Generated jextract binding | Handwritten facade |
|---|---|---|
| What is the C function name? Which C types does it accept/return? | Reads from header and generates accordingly | Uses the generated methods |
| How is the C library found/loaded? | According to jextract options | Runtime configuration and error handling at the boundary |
| Is `void *` owned or borrowed? | Cannot know automatically | Needs a clear contract and a single owner |
| Is `const char*` UTF-8 or another encoding? | Does not know business semantics | Chooses charset, checks NUL/byte count |
| How many elements does `int count` allow? | Does not know policy | Checks size, limits, overflow |
| What does `-3` from the native function mean? | Returns `int -3` | Translates to Java exception/domain status |
| Does the native function retain the pointer after returning? | Cannot conclude automatically | Designs Arena lifetime according to C contract |
| When should the native session be freed? | Does not know | `AutoCloseable.close()` + the right C deallocator |
| Is the C function thread-safe? | Does not know | Appropriate lock/owner-thread/executor |
| Does the C struct layout match the actual ABI? | Depends on header/tool/target | Integration tests per OS/CPU/compiler |
| Should `MemorySegment` be returned to the business layer? | May return raw carrier | Usually should copy to a Java array/record |

For example, a generated method can have the carrier `MemorySegment` for both an owned C session and a borrowed `int*` input, even though **the two pointers have completely different owners and lifetimes**. The Java compiler does not distinguish them by the `MemorySegment` type alone. The facade provides appropriate types/usage contracts so API users do not have to guess.

### 2.1. Three Lifetimes to Track Independently

1. **Generated library/class-loader lifetime:** the native binary is loaded according to the binding's options, depending on the loader/JVM. It is not the native session itself.
2. **Native session lifetime:** C `sc_open` allocates `sc_session*` via the C allocator; C `sc_close` frees it. The wrapper is responsible for calling it **once**.
3. **Temporary call buffers:** Java allocates native input/output memory using `Arena.ofConfined()`; it lives for a single call and is reclaimed by the arena when closed.

`Arena.close()` **does not automatically free** a pointer allocated by C `malloc` just because Java holds a `MemorySegment` containing that address. Conversely, `sc_close(session)` does not free buffers allocated by a Java Arena. That is why two kinds of cleanup are needed in the facade.

## 3. Source Structure and Unidirectional Dependencies

~~~text
checked-jextract/
├── native/
│   ├── securecalc.h
│   └── securecalc.c
├── generated/
│   └── src/demo/generated/...
├── src/main/java/
│   └── demo/
│       ├── api/CheckedCalc.java
│       └── app/Main.java
├── build/classes/
└── libsecurecalc.so      (Linux; Windows/macOS have different names)
~~~

**Directories with clear ownership:**

- `native/securecalc.h`: C ABI header, **the input source for jextract**.
- `native/securecalc.c`: C implementation and native session management logic.
- `generated/src`: **written only by jextract**. Generated sources may be committed or regenerated in CI, but choose one consistent strategy.
- `src/main/java/demo/api`: handwritten code, holding validation/ownership/error handling.
- `src/main/java/demo/app`: application depends only on the `CheckedCalc` facade.
- `build/classes`: javac output; do not edit as source.

Import diagram:

~~~text
Allowed:
    demo.app -> demo.api -> demo.generated -> native library

Discouraged:
    demo.app -> demo.generated
    service  -> raw MemorySegment
    generated -> demo.api
    another caller -> sc_close(session) using borrowed pointer
~~~

These packages are **architectural boundaries**, not security mechanisms. When you need to block use of the raw generated API, you can consider Java modules and export only the facade package, with the module graph/native-access properly configured. Do not confuse “should not import” with “cannot import”.

## 4. Defining the Native Contract Before Generating Code

The example uses a C library `securecalc` with 3 functions: create a session with a factor limit, multiply each array element by a factor, and close the session.

**C contract:**

- `sc_open(int max_factor)` accepts `0..10`. On success returns `sc_session*`, the caller **owns** the session and must call `sc_close` exactly **once**. On failure returns `NULL`.
- `sc_scale(session,input,count,factor,output)` requires a live session, `count` from 1 to 64, both input/output have at least `count` `int` values, factor from 0 to `session->max_factor`, each input from 0 to 10000.
- The C function does not retain input/output pointers after returning. Therefore, those buffers can live in a **call-scoped arena**.
- `sc_scale` returns `0` on success, a negative code on failure. **Only read output when status equals 0**.
- `sc_close(session)` calls the matching deallocator for `sc_open`. Do not call again on the same pointer; the C code in the demo does not support double-free.
- The sample ABI targets common platforms with 32-bit C `int`; for unusual ABIs, you must verify type width/layout or replace the header with fixed-width types.

**Do not infer ownership from method names or C pointer types.** A `char*` might point to static memory, an allocation that must be freed, a temporary buffer, or an internal library string. Only the C API documentation/contract decides.

### 4.1. Complete Header — `native/securecalc.h`

~~~c
#ifndef SECURECALC_H
#define SECURECALC_H

#if defined(_WIN32)
#  define SC_EXPORT __declspec(dllexport)
#else
#  define SC_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Opaque native handle: only use through the functions below. */
typedef struct sc_session sc_session;

/* max_factor 0..10, returns NULL on creation failure. */
SC_EXPORT sc_session *sc_open(int max_factor);

/* 0=OK, -1=session NULL, -2=bad pointers/count,
   -3=invalid factor, -4=invalid input value.
   On failure: do not use output contents. */
SC_EXPORT int sc_scale(
    sc_session *session,
    const int *input,
    int count,
    int factor,
    int *output
);

/* Free a live session exactly once; NULL is accepted. */
SC_EXPORT void sc_close(sc_session *session);

#ifdef __cplusplus
}
#endif

#endif
~~~

This is the **complete header file**. `extern "C"` prevents C++ name mangling if a C++ caller includes the header; the example implementation is C. The exports allow the native loader to find symbols. jextract reads **declarations in the header**, without requiring you to write JNI `Java_package_Class_method` names.

### 4.2. Complete Implementation — `native/securecalc.c`

~~~c
#include "securecalc.h"
#include <stddef.h>
#include <stdlib.h>

struct sc_session {
    int max_factor;
};

sc_session *sc_open(int max_factor) {
    if (max_factor < 0 || max_factor > 10) {
        return NULL;
    }

    sc_session *session = (sc_session *)malloc(sizeof(*session));
    if (session == NULL) {
        return NULL;
    }

    session->max_factor = max_factor;
    return session;
}

int sc_scale(
        sc_session *session,
        const int *input,
        int count,
        int factor,
        int *output) {
    if (session == NULL) {
        return -1;
    }
    if (count <= 0 || count > 64 || input == NULL || output == NULL) {
        return -2;
    }
    if (factor < 0 || factor > session->max_factor) {
        return -3;
    }

    /* Validate everything before writing output. */
    for (int i = 0; i < count; i++) {
        if (input[i] < 0 || input[i] > 10000) {
            return -4;
        }
    }

    for (int i = 0; i < count; i++) {
        output[i] = input[i] * factor;
    }
    return 0;
}

void sc_close(sc_session *session) {
    free(session);
}
~~~

This is the **complete C file**. Native C still validates count, pointers, and value ranges itself, because callers outside the wrapper can call it directly. However, the C function only receives an `int*`, **without byte length metadata** of the memory the pointer actually points to: if a caller says `count=64` but only allocates 2 elements, C cannot verify the capacity on its own. The wrapper must keep `count` consistent with the allocated buffer.

The two validation rounds have their own reasons:

- **Java wrapper:** fail early with an exception appropriate for the Java API, avoiding unnecessary allocations/FFM calls.
- **C native:** defensive against other callers and re-checking the C boundary.

In the C demo, maximum `10000 * 10 = 100000`, avoiding signed overflow on 32-bit `int`. For arbitrary inputs, you must design a clear arithmetic bounds/saturation/error policy, never letting C signed overflow become undefined behavior.

## 5. Generating Code with the Right Toolchain and Not Modifying Generated Source

`jextract` is a separate tool from the OpenJDK project, not installed by default with every JDK. Generated code uses FFM APIs so the **jextract version must match the target JDK**. This guide targets **JDK 22+**, preferring a jextract release/branch built for JDK 22 final FFM. Newer jextract versions may require a newer JDK; you cannot assume the latest release generates code usable on JDK 22.

First check:

~~~bash
java -version
javac -version
jextract --version
jextract --help
~~~

Once a compatible tool pair is chosen, run from the project root:

~~~bash
jextract \
  --output generated/src \
  --target-package demo.generated \
  --header-class-name RawCalc \
  --library securecalc \
  --use-system-load-library \
  native/securecalc.h
~~~

**Option meanings:**

| Option | Meaning |
|---|---|
| `--output generated/src` | Places all generated Java sources in a separate root |
| `--target-package demo.generated` | Package of the bindings |
| `--header-class-name RawCalc` | Main class name kept stable when code fits |
| `--library securecalc` | Logical name of the native binary to load |
| `--use-system-load-library` | Uses `System.loadLibrary` so `java.library.path` can be configured |
| `native/securecalc.h` | Exact C header to parse |

On Windows cmd.exe, use **a single line** to avoid line-continuation syntax differences:

~~~bat
jextract --output generated/src --target-package demo.generated --header-class-name RawCalc --library securecalc --use-system-load-library native\securecalc.h
~~~

The **actual** generated source (do not create this class manually) is expected to have static wrapper methods with carriers:

~~~text
demo.generated.RawCalc

sc_open(int)                       -> MemorySegment
sc_scale(MemorySegment session,
         MemorySegment input,
         int count,
         int factor,
         MemorySegment output)     -> int
sc_close(MemorySegment session)    -> void
~~~

This is a **descriptive signature table**, not Java source. Method names/carriers must be verified against the **actual files generated by jextract**, because generator version, typedefs, and target ABI can change the output. If they differ, check the jextract version/header first; adjust the **handwritten adapter** if needed, do not edit generated code.

The generated output may also provide `sc_scale$address()`, `sc_scale$descriptor()`, `sc_scale$handle()`, or helper classes. The app does not need to know these details. Raw C pointers, including opaque `sc_session*`, are typically represented by `MemorySegment` but **carry no ownership** or reliable byte size from the carrier alone.

### 5.1. Why Is --use-system-load-library Chosen?

According to jextract documentation, if using `--library securecalc` by default, bindings may use `SymbolLookup.libraryLookup` and the OS loader search path. With `--use-system-load-library`, jextract generates loading logic via `System.loadLibrary`; Java can then specify `-Djava.library.path=.` to find `libsecurecalc.so`, `libsecurecalc.dylib`, or `securecalc.dll` in the current working directory.

**Do not confuse** `java.library.path` with the search path for native *dependencies* loaded transitively by the OS. If the library depends on other files, you may still need to configure the OS loader. If your jextract version does not have `--use-system-load-library`, read `jextract --help` and pick one consistent loading strategy rather than copying flags from another tool.

### 5.2. Do Not Edit Generated Java After Generation

If you want to add `if (len > 64) throw ...`, write it in `CheckedCalc`. If you want to change the package name, change `--target-package` and regenerate. If you want to restrict declarations, use jextract include filters rather than manually deleting methods in generated files on every build.

When the C header or jextract changes:

~~~text
C header / toolchain update
       |
       v
Regenerate ONLY generated/src
       |
       v
Compile generated + handwritten Java
       |
       v
Run unit tests and native integration tests
       |
       v
Review generated diff + wrapper contract
~~~

Separating directories makes it easy to review machine-generated changes without mixing them with business logic edits.

## 6. Java Facade Class: Owning the Session, Validating Data, and Cleanup

Public API of the example:

~~~text
new CheckedCalc(4)         -> create native session, validate max factor
calc.scale(int[], factor)   -> validate, allocate, call C, copy result
calc.close()                -> sc_close exactly once, mark closed
calc.scale(...) after close -> Java IllegalStateException, DO NOT call C
~~~

Callers do not see `MemorySegment`, `Arena`, raw C status codes, or the `sc_session*` pointer.

### 6.1. Complete File — `src/main/java/demo/api/CheckedCalc.java`

~~~java
package demo.api;

import demo.generated.RawCalc;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Objects;

public final class CheckedCalc implements AutoCloseable {
    private static final int MAX_ITEMS = 64;
    private static final int MAX_VALUE = 10000;
    private static final int MAX_FACTOR = 10;

    private final MemorySegment session;
    private final int maxFactor;
    private boolean closed;

    public CheckedCalc(int maxFactor) {
        if (maxFactor < 0 || maxFactor > MAX_FACTOR) {
            throw new IllegalArgumentException("maxFactor must be 0..10");
        }

        MemorySegment ptr = RawCalc.sc_open(maxFactor);
        if (ptr.address() == 0L) {
            throw new IllegalStateException("native sc_open returned NULL");
        }

        session = ptr;
        this.maxFactor = maxFactor;
    }

    public synchronized int[] scale(int[] values, int factor) {
        ensureOpen();
        Objects.requireNonNull(values, "values");

        if (values.length > MAX_ITEMS) {
            throw new IllegalArgumentException("too many items");
        }
        if (factor < 0 || factor > maxFactor) {
            throw new IllegalArgumentException("factor out of range");
        }
        for (int value : values) {
            if (value < 0 || value > MAX_VALUE) {
                throw new IllegalArgumentException("value out of range");
            }
        }

        // Java API allows empty arrays; C contract requires count >= 1.
        if (values.length == 0) {
            return new int[0];
        }

        try (Arena callArena = Arena.ofConfined()) {
            MemorySegment input =
                    callArena.allocateFrom(ValueLayout.JAVA_INT, values);
            MemorySegment output =
                    callArena.allocate(ValueLayout.JAVA_INT, values.length);

            int status = RawCalc.sc_scale(
                    session, input, values.length, factor, output
            );
            if (status != 0) {
                // Do not read output when C reports an error.
                throw new IllegalStateException(
                        "native sc_scale failed: " + status
                );
            }

            int[] result = new int[values.length];
            for (int i = 0; i < result.length; i++) {
                result[i] = output.getAtIndex(
                        ValueLayout.JAVA_INT, i
                );
            }
            return result;
        }
    }

    private void ensureOpen() {
        if (closed) {
            throw new IllegalStateException("CheckedCalc is closed");
        }
    }

    @Override
    public synchronized void close() {
        if (!closed) {
            closed = true;
            RawCalc.sc_close(session);
        }
    }
}
~~~

This is the **complete Java file** owned by the developer. It relies on the method carriers generated from the exact `native/securecalc.h`. If the generated signature differs, check the tool/header; do not change the C ABI by guessing.

### 6.2. Why Is Each Step Important?

1. **The constructor validates factor before native allocation**, so invalid input does not create a session.
2. `RawCalc.sc_open` returns a `MemorySegment` wrapping an opaque pointer. `ptr.address() == 0L` represents C NULL; the wrapper refuses to create an object without a resource.
3. Session is `private final`, **with no public getter for the raw pointer**, preventing callers from calling `sc_close` themselves and causing a double-free.
4. `scale` checks state before every native call. After `close`, the freed pointer must not be used.
5. `Objects.requireNonNull` gives a clear Java error; never pass null or an invalid count down to C.
6. Validates maximum 64 and values 0..10000 before allocating. The `values.length == 0` case is handled by the wrapper returning `[]`, without calling C with count=0.
7. `callArena.allocateFrom(JAVA_INT, values)` copies Java data into native memory, while `callArena.allocate(JAVA_INT, count)` allocates an appropriately sized output buffer.
8. C receives two `int*`, with count equal to the number of elements. **C does not know `MemorySegment.byteSize()`; Java is responsible for keeping count/byte size consistent.**
9. `status != 0` becomes an exception. Do not copy output from a failed native call.
10. Copy result into `int[]` **before** the arena closes. The output remains valid after the method returns even though the native buffer has been reclaimed.
11. `try (Arena ...)` ensures buffers are freed on the happy path, C status error, or Java exception.
12. `close` is idempotent at the facade: the C deallocator is called once. **Do not** assume C `free(session)` is itself idempotent if called twice.

The class can be modified to map native statuses to domain-specific exception types if a real C API has multiple error kinds. For the demo, `IllegalStateException("native sc_scale failed: ...")` signals an unexpected contract violation because Java already validated beforehand.

### 6.3. Concurrency: close and Calls on the Same Instance

Both `scale` and `close` are `synchronized` on `this`. This means:

~~~text
Thread A enters synchronized scale:
    uses session to call sc_scale
    copies output; closes call Arena
    exits monitor

Thread B wants synchronized close:
    waits for Thread A to exit monitor
    closes native session via sc_close
    marks closed

Subsequent scale call:
    sees closed -> IllegalStateException
    does not call C on freed pointer
~~~

If you only have `volatile boolean closed` without synchronizing the native call with close, the following can happen:

~~~text
A: check closed == false
B: close() -> free(session)
A: sc_scale(session, ...) -> use-after-free
~~~

**`synchronized` only protects call paths going through the same facade instance.** It cannot prevent a native library from having an internal thread holding the pointer, or other code intentionally calling the raw binding outside the facade. If C requires all calls on **a specific OS thread**, serializing with synchronized **is still not enough**: you must use an owner-thread executor or design for thread confinement.

## 7. Application Uses the Java API, Unaware of C Bindings

Complete file — `src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.CheckedCalc;
import java.util.Arrays;

public final class Main {
    public static void main(String[] args) {
        CheckedCalc calc = new CheckedCalc(4);

        try (calc) {
            System.out.println("scaled = "
                    + Arrays.toString(
                            calc.scale(new int[] {2, 4, 6}, 3)
                    ));

            System.out.println("empty = "
                    + Arrays.toString(
                            calc.scale(new int[0], 2)
                    ));

            try {
                calc.scale(new int[] {2, -1}, 2);
                throw new AssertionError("invalid input was accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid value = rejected");
            }

            try {
                calc.scale(new int[] {2}, 7);
                throw new AssertionError("invalid factor was accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid factor = rejected");
            }
        }

        calc.close(); // Idempotent at the facade, does not free again.

        try {
            calc.scale(new int[] {1}, 2);
            throw new AssertionError("closed session was reused");
        } catch (IllegalStateException expected) {
            System.out.println("after close = rejected");
        }
    }
}
~~~

This is the **complete Java file**. Because `calc` is assigned exactly once, it is effectively final and can be used in `try (calc)`. The app only imports `demo.api.CheckedCalc`; it does not import `RawCalc`, `Arena`, or `MemorySegment`.

**Application stdout, on the correct native ABI and toolchain:**

~~~text
scaled = [6, 12, 18]
empty = []
invalid value = rejected
invalid factor = rejected
after close = rejected
~~~

The values:

- `[2,4,6] × 3` ⇒ `[6,12,18]`.
- Empty input ⇒ wrapper returns empty output without calling C.
- Value `-1` is rejected by Java validation.
- Factor `7` exceeding `maxFactor=4` is rejected.
- After `try`, the native session is closed; the next `scale` call is rejected by Java without dereferencing the old C pointer.

The standard output above does not include debug lines if you enable tracing/downcall logging. The demo C code is designed not to print to stdout.

## 8. Building C, Generating Bindings, Compiling Java, Running the Application

Commands are run from the `checked-jextract` root directory. Use a native compiler matching the OS/CPU/bitness of the JVM; the code does not need `jni.h`.

### 8.1. Build Native Library

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -fPIC -shared \
  -I native native/securecalc.c -o libsecurecalc.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -fPIC -dynamiclib \
  -I native native/securecalc.c -o libsecurecalc.dylib
~~~

**Windows (Visual Studio Developer Command Prompt, cmd.exe):**

~~~bat
cl /LD /I native native\securecalc.c /Fe:securecalc.dll
~~~

If using Windows MSVC, run Developer Command Prompt so `cl` and the linker are configured. The output must contain native symbols `sc_open`, `sc_scale`, `sc_close`. Verification command per platform:

~~~text
Linux:   nm -D libsecurecalc.so
macOS:   nm -g libsecurecalc.dylib
Windows: dumpbin /EXPORTS securecalc.dll
~~~

If the symbols are not visible or the native DLL/.so does not match the C header version, stop to fix the build; do not change Java descriptors by guessing.

### 8.2. Generate

**Linux/macOS:**

~~~bash
jextract \
  --output generated/src \
  --target-package demo.generated \
  --header-class-name RawCalc \
  --library securecalc \
  --use-system-load-library \
  native/securecalc.h
~~~

**Windows Command Prompt:**

~~~bat
jextract --output generated/src --target-package demo.generated --header-class-name RawCalc --library securecalc --use-system-load-library native\securecalc.h
~~~

These commands are only valid when the jextract version is compatible with the target JDK and has options like `--use-system-load-library`. Check `jextract --help`/`--version`. Do not grab the latest jextract without checking which JDK version it generates code for.

### 8.3. Compile Generated and Handwritten Code

**Linux/macOS:**

~~~bash
mkdir -p build/classes
find generated/src src/main/java -name '*.java' > build/java-sources.txt
javac --release 22 -d build/classes @build/java-sources.txt
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes | Out-Null
$files = @(Get-ChildItem generated/src, src/main/java -Recurse -Filter *.java |
    ForEach-Object { $_.FullName })
javac --release 22 -d build/classes $files
~~~

Compile **all generated sources**, not just `RawCalc.java`, because the generator may produce helpers/struct types used internally. If javac 22 reports missing methods/APIs in generated code, check the jextract version/FFM target before modifying the wrapper.

### 8.4. Run

**Linux/macOS:**

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  -cp build/classes demo.app.Main
~~~

**Windows Command Prompt:**

~~~bat
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. -cp build\classes demo.app.Main
~~~

Because the generated binding was created with `--use-system-load-library`, `-Djava.library.path=.` allows `System.loadLibrary("securecalc")` to find the native binary in the current directory. If the library has other dependencies, the OS loader search path may still need separate configuration.

`--enable-native-access=ALL-UNNAMED` applies to code running on the classpath that uses restricted FFM methods. Named modules should be granted access by module name rather than granting all unnamed modules. JDK 22 FFM is final, so **`--enable-preview` is not needed for FFM itself**.

## 9. Resource Lifecycle and Exception Safety

### 9.1. Native Session

~~~text
CheckedCalc(maxFactor)  -- validate --> sc_open
                                         |
                               non-NULL native pointer
                                         |
                                         v
                                       OPEN
                                         |
                              scale() 0..N times
                                         |
                              close() (once)
                                         |
                              sc_close -> free
                                         |
                                         v
                                       CLOSED
                                         |
                         scale() -> IllegalStateException
                         close() -> no-op
~~~

The C deallocator `sc_close` **does not know on its own** whether Java has already called it. The wrapper keeps `closed` state, serializes close/scale, and does not expose the session pointer; these are three combined measures to reduce double-free/use-after-free.

### 9.2. Temporary Native Buffer

~~~text
scale(values, factor)
   |
   +-- Java validation
   |
   +-- try (Arena callArena = Arena.ofConfined())
         |
         +-- allocateFrom(JAVA_INT, values) -> native input
         +-- allocate(JAVA_INT, count)     -> native output
         +-- RawCalc.sc_scale(...)         -> C uses pointers only in call
         +-- if success: copy native output -> Java int[]
         |
         +-- callArena.close() at block exit
   |
   +-- return Java int[]
~~~

If C reports an error or Java throws an exception inside the try, **try-with-resources still closes the Arena**. Under the demo contract, C does not retain pointers after returning, so closing at that point is correct.

**You must change the design if the native call is asynchronous** (a callback or native worker thread still uses input/output after returning). In that case, you cannot close the call-scoped arena immediately; you need ownership for the async task and must wait for completion. Do not default to moving every buffer to `Arena.global()`, because global allocations are not reclaimed by the arena during the JVM's lifetime.

### 9.3. Exceptions and Partial Failure

- Constructor validation fails: C is not called, no native session needs closing.
- `sc_open` returns `NULL`: object is not created; the application receives an exception.
- `sc_scale` returns status != 0: **do not copy output**; temporary Arena closes automatically.
- Java result-copy fails: temporary Arena also closes.
- `close` is idempotent on the facade side: C `sc_close` is called at most once.
- A native crash/ABI corruption **is not guaranteed by the JVM to turn into a Java exception**. This is why testing the native/library is needed, not just policy.

### 9.4. Why Not Rely on GC?

Java `finalize()` is not a timely mechanism for cleaning up native handles. `Cleaner` can be viewed as a safety net for forgotten resources, but GC timing is nondeterministic and a cleaner state holding the wrong reference can prevent the resource from ever being reclaimed. **`AutoCloseable` + try-with-resources** is the primary contract; if using Cleaner, it must be designed separately and tested for ownership/double-free.

## 10. Validating Data at the Right Layer, in the Right Units

### 10.1. Null, Count, Range

In the facade:

~~~java
Objects.requireNonNull(values, "values");
if (values.length > MAX_ITEMS) {
    throw new IllegalArgumentException("too many items");
}
if (factor < 0 || factor > maxFactor) {
    throw new IllegalArgumentException("factor out of range");
}
~~~

This is an **excerpt** of the wrapper; constants and fields are defined in the complete class. C still validates count/pointers/range because raw bindings or other native callers might bypass the wrapper.

A C `int*` only carries an address, **not an array length**. The Java wrapper must allocate a byte count matching `count`. For large arrays or `long count` from a native API, use `Math.multiplyExact(count, elementBytes)` and quotas to avoid arithmetic overflow before allocating or reinterpreting pointers.

### 10.2. C String vs Java String

If a C function accepts `const char *utf8`, jextract may generate a `MemorySegment` carrier; the wrapper must choose the right charset, check for embedded NULs when the C API forbids them, provide a NUL terminator, and keep the buffer alive while native code still uses it. JDK 22 `arena.allocateFrom(String)` produces a UTF-8 null-terminated C string; do not use `Java String.length()` as the UTF-8 byte count.

If the C API operates on a binary buffer, use pointer + byte length; do not assume a terminator or encoding.

### 10.3. C Struct and Pointer Ownership

For a C struct pointer, jextract can generate accessor/layout helpers. However:

- `MemorySegment` may just be a zero-length pointer, not proving the backing allocation has enough bytes.
- `reinterpret` only changes spatial/temporal metadata; **it does not verify the actual memory region**.
- A native struct returned *by-value* has a different contract from a `struct*` returned pointer.
- A struct containing pointer fields is not **deep-copied** just because the wrapper copies struct bytes.
- The native deallocator of a pointer field is not automatically called by `Arena.close()` on the struct result.

Expose Java values only when possible, or a resource wrapper/borrowed handle with clearly documented ownership.

## 11. Java Error Policy and Native Status Codes

Demo cases:

| C status | C meaning | Java wrapper handling |
|---|---|---|
| `0` | Success | Copy output and return `int[]` |
| `-1` | Session null | Invariant/lifetime failure |
| `-2` | Invalid pointers/count | ABI/contract mismatch |
| `-3` | Invalid factor | Contract/input failure |
| `-4` | Invalid input value | Contract/input failure |

In the complete code, the wrapper validates beforehand so negative statuses are abnormal signals; it throws `IllegalStateException` with the code. Real applications can map by domain:

- Invalid user input → `IllegalArgumentException`.
- Native I/O failure → exception carrying appropriate C error details.
- Native protocol failure → a custom exception containing the error code without leaking pointers/addresses.
- Retrying is possible if the C API docs state the error is retryable and the resource is still valid; **do not** blindly retry on a session/pointer that is already in an undefined state.

Generated code cannot decide this error policy on its own, because the meaning of status codes comes from the **business/native API contract**, not from the `int` signature.

## 12. Two-Tier Testing Strategy

### 12.1. Unit Tests for Wrapper Policy

Not every unit test needs to load the native library. You can extract a handwritten adapter interface to fake:

~~~java
// Design snippet, not part of the runnable demo program.
interface RawOperations {
    MemorySegment open(int maxFactor);
    int scale(
        MemorySegment session,
        MemorySegment input,
        int count,
        int factor,
        MemorySegment output
    );
    void close(MemorySegment session);
}
~~~

The real adapter delegates to `RawCalc`; fake tests verify call counts, status codes, and close semantics. This interface belongs to **handwritten code**, not `generated/src`. A simple project might not need the abstraction yet, but policy unit tests and ABI integration tests remain two distinct concerns.

Unit cases:

1. Constructor rejects maxFactor outside `0..10` **before** opening native.
2. `scale(null,...)` reports a clear error without calling C.
3. Array >64 elements is rejected before allocation.
4. Values outside `0..10000` are rejected.
5. Negative or over-max factor is rejected.
6. Empty array returns `[]` and does not call C.
7. Negative native status does not cause the wrapper to copy output.
8. Calling `close()` multiple times releases the session only once.
9. `scale` after close throws `IllegalStateException`.
10. Concurrent `scale`/`close` through the same facade does not use the session after free.

### 12.2. Mandatory Integration Tests with Real C

Generated code compiling successfully **does not prove the runtime C ABI is correct**. You must test:

- Compatible jextract target JDK/FFM.
- Matching C header and native binary versions.
- Symbols are exported and library/dependencies load on each OS.
- Integer type widths, pointer size/ABI, alignment/struct packing when the API has structs.
- `sc_open`/`sc_scale`/`sc_close` actually run with valid and invalid data.
- Native memory leak/double-free when many sessions are created and closed.
- Call/close races under target concurrency scenarios.
- Callback/async code does not use buffers after the arena closes (if the API has them).
- Java output is independent of the native Arena after returning.

For this lesson, the **sanity test** runs `demo.app.Main` and compares the five stdout lines in section 7; failures may lie outside the Java heap and require appropriate native diagnostics.

### 12.3. Debugging with Generated Tracing

Some jextract versions support:

~~~bash
java -Djextract.trace.downcalls=true \
  --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  -cp build/classes demo.app.Main
~~~

**Enable only when diagnosing**: the tool may print native parameters, pointers, and sensitive information. When matching stdout automatically, do not enable tracing to avoid extra log lines. Diagnostic flags depend on the jextract/JVM version; check the corresponding documentation.

## 13. Controlled Code Regeneration When the Native Header Changes

If you add a field to a C struct, rename a function, or change `int` to `size_t`, handle it in order:

~~~text
C header/native API changes
       |
       +--> Verify C ABI, ownership, and semantic compatibility
       |
       +--> Pin jextract + JDK + compiler/target OS
       |
       +--> Regenerate only into generated/src
       |
       +--> Review generated diff and compile
       |
       +--> Adjust facade adapter (if signature changed)
       |
       +--> Run policy unit tests + native integration tests
       |
       +--> Publish versioned artifacts and contract documentation
~~~

**Do not expose the generated API as the public contract of the business layer.** A change to `sc_scale` from `int count` to `size_t count` may require updating the facade and native tests, while `CheckedCalc.scale(int[], int)` can still preserve the API for callers if the wrapper performs proper validation/casting.

### 13.1. Commit Generated Code or Generate in CI?

| Approach | Advantage | Responsibility |
|---|---|---|
| Commit generated source and regenerate in a controlled way | Reproducible builds, clear diff review | Prevent generated output from going stale relative to header/tool |
| Generate in CI from pinned version | Source of truth is header/toolchain | CI needs compatible jextract/clang/JDK, with diff checks |

Both are valid. Do not let a developer manually edit a generated file only for CI regeneration to overwrite it. For multi-platform C ABIs, you may need to generate/verify per target because C `long`, `size_t`, struct padding, and macros differ.

### 13.2. Version Compatibility

- `jextract --version` identifies the tool and target JDK.
- `java -version`, `javac -version` identify the runtime/compiler.
- C header must match the binary library.
- `--library` and loading strategy must be consistent between generation and run.
- JDK 22 FFM final does not need preview flags; JDK 21 preview cannot be handled simply by lowering `--release` on JDK 22.

Do not assume **jextract latest** is compatible with JDK 22. If jextract targets a newer JDK, pick a build matching the deployment JDK or upgrade the whole toolchain with testing.

## 14. Anti-Patterns and Fixes

| Anti-pattern | Risk | Better approach |
|---|---|---|
| Adding validation by directly editing generated Java | Regeneration overwrites it | Put validation in the facade |
| Business code calling `RawCalc.sc_close` | Ownership is scattered | One AutoCloseable managing the handle |
| Returning native `MemorySegment` of a confined arena | Use after close | Copy to a Java value |
| Using `Arena.global` for every request | Native memory is not reclaimed by the arena | Bounded Arena and close in the right scope |
| Not checking native status codes | Using undefined output | Fail-fast and error mapping |
| Calling C with empty input when C requires count>0 | Native failure | Facade defines clear empty semantics |
| Checking boolean closed without locking with native call | Use-after-free race | Lock/owner-thread/refcount with close |
| Implicitly using Java String.length as UTF-8 bytes | C reads too few or too many bytes | Verify charset/byte length |
| Retaining callback stub pointer after arena close | Native callback to expired region | Manage callback lifetime per C contract |
| Using `MemorySegment.ofAddress` then reinterpreting a guessed size | Unverified backing memory | Pointer+size contract or copy |
| Mapping all C errors to `-1` with no info | Hard to debug | Typed Java exception + status tracking |
| Testing only on Linux then shipping Windows | ABI/loader mismatch | CI native integration per target |
| Generating with jextract different from deployment JDK | API/version mismatch | Pin version pairs |

## 15. Questions and Exercises

1. Why can jextract generate a method accepting `MemorySegment` without knowing whether that pointer belongs to an owned or borrowed contract?
2. What are the three layers in the architecture diagram? Which layer has the authority to modify validation?
3. Why should `src/main/java` not be located inside `generated/src`?
4. Is a native handle allocated by `malloc` freed by `Arena.close()` or `sc_close`?
5. If a C function retains a pointer after returning, is a per-call `Arena.ofConfined()` still appropriate?
6. Why does the facade copy the output into a Java `int[]` before closing the call arena?
7. When is using `synchronized` sufficient to avoid a scale/close race, and when does it fail to satisfy native thread affinity requirements?
8. If `RawCalc.sc_open` returns `NULL`, how does the wrapper handle it?
9. If native `sc_scale` returns a negative status, why must the output not be read?
10. How does the `--use-system-load-library` mechanism differ from the default `SymbolLookup.libraryLookup`?
11. At which step must the jextract and JDK versions be compatible?
12. When a native API changes from `int count` to `size_t count`, what must you verify regarding ABI/overflow?
13. Why is it necessary to test the real native binary even when Java unit tests PASS?
14. How can a handwritten class hide generated classes from the business layer, and what are the limits of package/module boundaries?
15. How can you test close idempotency without causing an actual double-free?
16. Why does a C string with an embedded NUL make reading via `strlen` behave differently from a Java `String`?
17. If native code returns a borrowed pointer to a static region, should Java have `close/free`?
18. What happens if CI regenerates Java code using a jextract targeting a newer JDK while the application deploys on JDK 22?
19. If the requirement changes from factor 0..10 to 0..20, which layers must be checked/updated?
20. Why is the result `scale([]) = []` a wrapper decision rather than coming from jextract?

**Conclusion:** **Code generated by jextract is a low-level ABI boundary**, helping Java call the right native symbols, but it is not a safe application API. Separate generated sources from the handwritten facade, keep the Java API with clear validation and ownership state, use `AutoCloseable` for owned native handles, `Arena.ofConfined()` for temporary buffers, translate C statuses into Java errors, and return Java values independent of native memory. Maintain correctness through a process of **pinning header/binary/jextract/JDK, controlled regeneration, unit tests, and native integration tests**.

### Official References

- [OpenJDK jextract — Guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md): command-line options, generated function wrappers, code organization, and library loading.
- [Dev.java — Generate Java Bindings with jextract](https://dev.java/learn/ffm/jextract/): workflow for generating bindings and integrating C headers.
- [Oracle Java SE 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html): native binding/tool example.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native memory lifetime, confined/shared/global scopes.
- [Oracle Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): `allocate` and `allocateFrom`.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): spatial/temporal bounds, carriers, and native pointers.
- [JEP 454 — FFM Final (JDK22)](https://openjdk.org/jeps/454) and [JEP 442 — FFM Third Preview (JDK21)](https://openjdk.org/jeps/442): version alignment.
