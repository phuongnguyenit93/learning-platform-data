# Choosing FFM or JNI Based on Java Version and Dependency on JVM Objects

**Foreign Function & Memory API (FFM)** and **Java Native Interface (JNI)** both enable Java to interoperate with native code, but they solve problems that are not entirely identical. For C libraries with a clear ABI that mainly exchange numbers, pointers, structs, and off-heap memory, standard FFM from **JDK 22** often allows writing most bindings in Java. Conversely, when native code must directly manipulate **`jobject`, `jclass`, `JNIEnv`, Java fields/methods, exceptions, class loaders**, or use the Invocation API to create/embed a JVM, JNI remains the right interface.

The decision also depends on the **actual Java version used to compile/run**. An example using the standard JDK 22 `java.lang.foreign.*` **does not automatically run** on Java 17 or Java 21; nor does FFM replace all capabilities of JNI just because it supports "upcalls". This article provides a version matrix, technical criteria, ABI and lifetime risks, two complete examples sharing the same C library, and a decision/migration process applicable in projects.

## 1. Two Different Boundaries: C ABI and JVM Object Model

~~~text
                                JAVA PROGRAM
                                     |
                +--------------------+--------------------+
                |                                         |
          FFM / java.lang.foreign                    JNI / native methods
                |                                         |
     Linker + SymbolLookup +                     javac -h + JNIEXPORT
     FunctionDescriptor + Arena                  + JNIEnv / jobject
                |                                         |
        Native C ABI function                     JNI entry point
   (int, double, pointer, struct...)        (JNIEnv*, jclass/jobject, ...)
                |                                         |
        Native memory / C library          JVM object graph, fields, methods,
                                          exceptions, arrays, class loaders
~~~

**FFM** uses `Linker.nativeLinker()` to create a Java `MethodHandle` for a function following the **native ABI**, describes the signature with `FunctionDescriptor`, resolves symbol addresses with `SymbolLookup`, and works with off-heap data using `MemorySegment`/`Arena`. It does not require writing a `Java_package_Class_method` function to call a regular C function.

**JNI** defines the protocol between the JVM and native code. Java declares `native`, and C/C++ implements the JNI function with `JNIEnv *` and `jobject` or `jclass`, from which it can read/write fields, create Strings/arrays, invoke Java methods, manage local/global refs, throw exceptions, and interact deeply with the object model.

Both ultimately execute **native code that is not fully protected by Java memory-safety**. FFM checks bounds/lifetime of `MemorySegment` instances managed by Java, but C can still dereference an invalid pointer, write past a buffer, or violate the ABI. JNI does not automatically make all C accesses safe either.

### 1.1. "Native Calling Back Into Java" Has Two Meanings

A C API with a callback like:

~~~c
/* C ABI callback: C receives a function pointer, unaware of jobject. */
int32_t run_callback(int32_t x, int32_t (*callback)(int32_t));
~~~

FFM creates an **upcall stub** from a Java `MethodHandle`, passes the stub as a function pointer to C, and C calls back into Java via the ABI callback. This is an **FFM upcall**, not arbitrary access into the JVM heap. The callback target can be a Java method (including a method handle bound to an object), but native code only sees a function pointer and ABI data.

Conversely, C code that needs:

~~~c
/* JNI illustrative snippet, not a standalone C function. */
jmethodID mid = (*env)->GetMethodID(env, clazz, "onEvent", "(I)V");
(*env)->CallVoidMethod(env, object, mid, (jint)42);
~~~

requires **JNI** to have `JNIEnv`, `jobject`, method IDs, and Java exception semantics. FFM `upcallStub` does not directly replace `GetMethodID`/`CallVoidMethod`. If you want to use FFM with a library that depends on JNI, you must design a **C ABI wrapper layer** or keep JNI for the JVM-related part.

## 2. Version Matrix: FFM Was Not a Stable API Before Java 22

| JDK Version | FFM Status | Practical Choice |
| --- | --- | --- |
| **Java 8–15** | No unified and stable FFM like JDK 22 | JNI is the available standard API for writing custom native bridges; project-appropriate binding libraries may be considered |
| **Java 16** | Foreign Linker/Memory APIs in incubator stage (different from JDK 22 standard API) | Do not assume FFM 22 source runs; JNI fits when a standard Java API across versions is needed |
| **Java 17** | `jdk.incubator.foreign`, **incubator** (JEP 412), API differs from final `java.lang.foreign` | With a Java 17 baseline, **prefer JNI** for system/application bindings needing stability; incubator FFM only when accepting experimental dependencies |
| **Java 18** | Next FFM incubator round (JEP 419) | Same note: not yet a final API |
| **Java 19** | FFM **first preview** (JEP 424) | Can be evaluated, but API/flags are tied to that exact release |
| **Java 20** | FFM **second preview** (JEP 434) | Not yet a final Java SE API |
| **Java 21 (LTS)** | FFM **third preview** (JEP 442), package `java.lang.foreign` but still preview | If production code must not rely on preview, prefer JNI or defer FFM bindings until baseline 22+; preview requires `--enable-preview` and version-specific builds |
| **Java 22+** | FFM **final/standard** (JEP 454), `java.lang.foreign` | FFM is the first choice worth trying for C ABI + foreign memory; JNI is still needed when native must manipulate JVM objects |
| **Java 24+** | FFM remains a standard API; JEP 472 unifies **native access** warnings for JNI and FFM | Grant native access via `--enable-native-access`; do not rely on default warning behavior forever |

**Three distinctions:**

1. **Incubator ≠ preview ≠ final.** Java 17 having `jdk.incubator.foreign` does not make Java 22's `import java.lang.foreign.*;` compile. Java 21 has a nearly similar package, but it is **still preview**; code/behavior may differ from the final version.
2. **FFM becoming standard in JDK 22** does not mean "Java 22 is the minimum version for JNI"; JNI has long existed and remains the standard for supporting native methods.
3. **JDK version is a real build/runtime constraint**, not just syntax. An artifact compiled against JDK 22 APIs and bytecode cannot be deployed as-is onto JRE 17 or 21.

Java 17 and 21 are common LTS baselines in enterprise projects. On Java 21 LTS, if the system has a policy prohibiting preview features, do not choose preview FFM just because the import looks valid. You can keep the existing JNI native wrapper, isolate the C ABI for easier future transition, and plan a JDK baseline upgrade before migrating to FFM.

### 2.1. When Are Flags Needed?

- **Java 17 incubator:** requires `--add-modules jdk.incubator.foreign` to access the incubator module, along with version-specific conditions; the `java.lang.foreign` examples in this article **cannot be used**.
- **Java 21 preview:** compiling/running preview features requires `--enable-preview` with the matching release, and code must match the JDK 21 API. Do not apply Java 22 commands verbatim to JDK 21.
- **Java 22 and later:** FFM is final, **no `--enable-preview` needed**; restricted/dangerous FFM operations such as `SymbolLookup.libraryLookup`, `Linker.downcallHandle`, and `Linker.upcallStub` require **native access** permission for the calling module.
- **Java 24+ with JNI:** JEP 472 standardizes native access rules. JNI loading/linking by an unauthorized module may emit a warning by default; depending on `--illegal-native-access`, it may be denied. This is not an announcement that JNI is removed or deprecated.

For code on the **classpath** (unnamed module), the common form is:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

For a **named module**, replace `ALL-UNNAMED` with the module name containing the code that calls restricted native APIs, for example `--enable-native-access=com.example.nativebridge`. Prefer granting the minimum required permission instead of enabling it for all modules. Depending on the JVM version, `--illegal-native-access=deny` is a proactive way to check where permissions are missing.

Do not ignore native access warnings just because the program still runs: warnings are signals about **runtime policy**, completely different from symbol or ABI errors.

## 3. JVM Objects Are the Most Important Branching Point

Look at the **contract of the C library**, not the technology name:

### 3.1. Cases Suited for FFM

- C functions taking integers/floats, pointers, C strings, native arrays, structs/unions, opaque handles.
- Outputs are primitive values, structs, caller- or callee-owned buffers, native error codes, or handles.
- Native callbacks follow a **C ABI function pointer**; Java provides a `MethodHandle` via `Linker.upcallStub` and ensures the callback does not outlive the stub's lifetime.
- The C library is inherently JVM-independent: cryptography, compression, math, device drivers, core database drivers, native SDKs with C headers.
- Java can express the ABI accurately with `FunctionDescriptor`, `ValueLayout`, `MemoryLayout`; the caller can manage memory and ownership via `Arena`.

Example of a suitable header:

~~~c
#include <stdint.h>

int64_t sum_i32(const int32_t *data, int32_t count);
int32_t call_unary(int32_t x, int32_t (*callback)(int32_t));
~~~

Neither function references `JNIEnv`, `jobject`, or class loaders. Java 22+ can create downcalls directly without a JNI wrapper.

### 3.2. Cases Suited for JNI

- Native methods receive `String`, Java object instances, Java arrays, `Class<?>`, `Throwable` and must operate on them **as Java objects**.
- C/C++ needs `GetObjectClass`, `GetFieldID`, `CallObjectMethod`, `NewString`, `NewObject`, `GetArrayLength`, or manages `NewGlobalRef`/`DeleteGlobalRef`.
- Native code must call Java methods on a given `jobject`, retain Java callback refs, look up classes by class loader, attach threads, and handle pending Java exceptions.
- The native library integrates with existing JNI code, or long-term bindings must run on JDK 17/21 without preview.
- A native host **embeds a JVM** and calls the Invocation API such as `JNI_CreateJavaVM`/`DestroyJavaVM`; FFM from Java does not replace the native API for creating a JVM.

Example of JNI receiving a Java array:

~~~c
/* Illustrative snippet: env belongs to the current JNI thread. */
JNIEXPORT jlong JNICALL Java_demo_JniCalc_sum(
    JNIEnv *env, jclass owner, jintArray values);
~~~

JNI knows this is a `jintArray` and can use `GetIntArrayElements`. When FFM sees a C pointer, it **cannot automatically recognize it as a `jintArray`** or call `GetObjectArrayElement`. Do not cast a `MemorySegment` to `jobject` or confuse `MemorySegment.NULL` with Java `null`.

### 3.3. Both Can Be Used in One Application

A sensible design is often:

~~~text
Java services / domain classes
            |
            +-- JNI bridge -> Java objects, lifecycle, exceptions
            |
            +-- FFM bridge -> C ABI native engine
                                     |
                                 buffers/structs
~~~

JNI can manage a few tight integration points with the JVM, while FFM calls many C ABI functions of a pure native engine. If both share native state, you must clearly design who creates/destroys handles, synchronization, classloader, and library loading; **never have two layers free the same pointer**.

A common transition architecture: extract the native algorithm into a **JVM-independent C ABI**, keep a thin JNI wrapper for Java 17 callers, and add an FFM wrapper for Java 22+. Both wrappers can call the same core, while the Java API matches the runtime version.

## 4. How Does FFM Work?

Standard FFM has the following main components:

| Component | Responsibility |
| --- | --- |
| `Linker.nativeLinker()` | Understands the native ABI on the current OS/CPU, creates downcalls/upcalls |
| `SymbolLookup` | Finds the address of an exported C symbol in a library, not a Java method |
| `FunctionDescriptor` | Declares the ABI return type and each argument type |
| `ValueLayout`/`MemoryLayout` | Describes primitives, addresses, structs, sequences, alignment/padding |
| `MethodHandle` | Represents the native function call from Java; carrier signatures must match |
| `MemorySegment` | Memory view, with size/scope and Java-side bounds checks |
| `Arena` | Manages the lifetime of native memory, and can also manage the lifetime of library lookups/upcall stubs |
| `Linker.upcallStub` | Creates a C ABI function pointer that calls a Java method handle |

Simple call path:

~~~text
Path to native library
  -> SymbolLookup.libraryLookup(path, arena)
  -> find("sum_i32") -> MemorySegment holding symbol address
  -> Linker.downcallHandle(symbol, FunctionDescriptor...)
  -> MethodHandle.invokeExact(...)
  -> C ABI function -> Java primitive/MemorySegment result
~~~

**Lifetime:** `Arena.ofConfined()` is an arena owned by a single thread; `close()` invalidates segments/stubs attached to its scope. `Arena.ofShared()` is for multi-threaded access when coordination is required; `Arena.global()` never closes automatically and is unsuitable if per-request deallocation is needed. `Arena.ofAuto()` relies on GC and has no deterministic deallocation time.

**Bounds and lifetime are not ABI correctness.** If you describe a 32-bit C `long` on Windows using Java's 64-bit `JAVA_LONG`, or omit padding in a C struct, the call can fail or misbehave even though Java's `MemorySegment` has bounds checks. For platform-dependent types like `size_t`, `long`, `wchar_t`, use canonical layouts, headers, and the target ABI to determine them accurately; do not hard-code "every pointer is a long" or "C long is always 64-bit".

**Upcall:** a method handle can call Java, but native C is given a C function pointer matching the described signature, not direct permission to read the object heap. If C stores the callback function pointer after the arena is closed, that is a lifetime bug; stop callbacks before closing and handle callback threads/exceptions explicitly.

## 5. How Does JNI Work?

Typical JNI call path:

~~~text
Java: private static native long sum(int[] values);
  -> javac -h generates demo_JniCalc.h
  -> C exports Java_demo_JniCalc_sum(JNIEnv*, jclass, jintArray)
  -> native calls GetArrayLength / GetIntArrayElements
  -> native computes and calls ReleaseIntArrayElements
  -> native returns jlong to Java
~~~

`JNIEnv *` is a JNI function table tied to a thread and must not be cached across threads. `jobject` and `jclass` are JNI references, not raw Java object addresses. `jmethodID` and `jfieldID` are opaque IDs valid for the lifetime of the defining class; do not turn them into arbitrary FFM pointers. Native code must release borrowed array/string memory, handle pending Java exceptions, and delete JNI global refs when no longer needed.

`JNIEXPORT`, `JNICALL`, and the header generated by `javac -h` help keep the ABI accurate. JNI does not use FFM's `Linker`; both use OS shared libraries (`.so`, `.dylib`, `.dll`), but how **functions/arguments are resolved** differs. A C ABI function such as `sum_i32` does not automatically become a JNI native method just by sharing the same name as a Java method.

JNI fits when object access is the bridge's purpose. If you only pass millions of numeric values to C, JNI can still do it, but it may require more glue code; FFM and batching data via `MemorySegment` is an option to benchmark rather than claiming one technology is always faster.

## 6. Complete Example: One Native Library, Two Java Clients, Two JDK Baselines

The example illustrates the **same integer summation task** through two interfaces:

- **JNI client — Java 17+:** passes `int[]`, JNI retrieves elements via `JNIEnv`, returns `long`. This is the **Java array object** boundary.
- **FFM client — Java 22+:** allocates an off-heap int buffer, calls C ABI `sum_i32` via `Linker`, and also tests C callback `call_unary` via `upcallStub`. This is the **pointer + C ABI** boundary, not `jintArray` access.

The output is designed to be deterministic, independent of benchmarks or GC output. Run each main class in a **separate Java process** to avoid confusing library lifecycle/ownership during testing.

~~~text
native-choice/
├── src/
│   └── demo/
│       ├── JniCalc.java          (Java 17+)
│       └── FfmCalc.java          (Java 22+)
├── native/
│   └── calcbridge.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 6.1. C11 Library — `native/calcbridge.c`

~~~c
#include "demo_JniCalc.h"
#include <stdint.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* Pure C ABI, used for FFM. */
EXPORT int64_t sum_i32(const int32_t *data, int32_t count) {
    if (count <= 0 || data == NULL) {
        return 0;
    }
    int64_t total = 0;
    for (int32_t i = 0; i < count; ++i) {
        total += (int64_t)data[i];
    }
    return total;
}

typedef int32_t (*unary_callback)(int32_t);

/* Pure C ABI: callback takes/returns int32_t. */
EXPORT int32_t call_unary(int32_t value, unary_callback callback) {
    if (callback == NULL) {
        return 0;
    }
    return callback(value);
}

/* JNI entry point specifically for Java int[]. */
JNIEXPORT jlong JNICALL Java_demo_JniCalc_sum(
        JNIEnv *env, jclass owner, jintArray values) {
    (void)owner;

    if (values == NULL) {
        jclass ex = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (ex != NULL) {
            (*env)->ThrowNew(env, ex, "values");
            (*env)->DeleteLocalRef(env, ex);
        }
        return 0;
    }

    jsize count = (*env)->GetArrayLength(env, values);
    if (count == 0) {
        return 0;
    }

    jint *data = (*env)->GetIntArrayElements(env, values, NULL);
    if (data == NULL) {
        return 0; /* Usually there is a pending exception from JNI. */
    }

    jlong total = 0;
    for (jsize i = 0; i < count; ++i) {
        total += (jlong)data[i];
    }

    (*env)->ReleaseIntArrayElements(env, values, data, JNI_ABORT);
    return total;
}
~~~

**The three exported functions have different meanings:**

- `sum_i32(const int32_t *, int32_t)`: C ABI. Java FFM passes a `MemorySegment` address of the memory region along with the element count; C cannot verify the validity of an arbitrary pointer provided by the caller. Caller rule: `data` must contain at least `count` valid `int32_t` elements if `count>0`; here `count<=0` or null returns 0. That is this example's contract, not a rule for every C library.
- `call_unary(int32_t, unary_callback)`: receives a C ABI function pointer and calls it **synchronously once**, without retaining the pointer after returning. This makes the FFM stub lifetime easy to control.
- `Java_demo_JniCalc_sum`: JNI protocol, receives a Java `jintArray`, checks null/empty, borrows a pointer with `GetIntArrayElements`, and releases with `JNI_ABORT` (since it is read-only). Accumulates in `jlong` to avoid 32-bit signed overflow.

A single library can export both JNI entry points and C ABI functions. **FFM only looks up `sum_i32` and `call_unary`**, without needing `JNIEnv*`; **the JNI client calls `Java_demo_JniCalc_sum`** via JNI rules. FFM using `SymbolLookup.libraryLookup` does not mean the JVM automatically calls the library's `JNI_OnLoad` (if present); the two loading/linking mechanisms should not be conflated.

The `#include "demo_JniCalc.h"` line requires running `javac -h` on `JniCalc.java` before building C; it helps the compiler verify against the generated prototype. C uses `int32_t`/`int64_t` from `<stdint.h>`, avoiding ambiguity in the size of C's `long` on Windows/Linux.

### 6.2. Java 17+ — `src/demo/JniCalc.java`

~~~java
package demo;

public final class JniCalc {
    private JniCalc() {
    }

    static {
        System.loadLibrary("calcbridge");
    }

    private static native long sum(int[] values);

    public static void main(String[] args) {
        System.out.println("JNI sum=" +
                sum(new int[] {7, -2, 9}));
        System.out.println("JNI empty=" + sum(new int[0]));
    }
}
~~~

The Java method `sum` takes a **Java array**, not a pointer. JNI sees `jintArray` and knows the length via `GetArrayLength`; Java does not have to manually copy to off-heap memory. C must release the borrowed pointer and must not retain `jint *` for use after the JNI call.

**Exact stdout** when the native library loads successfully:

~~~text
JNI sum=14
JNI empty=0
~~~

On Java 17 and later, the Java code above requires no FFM, incubator, or preview flags. JDK 24+ may require native access configuration to avoid warnings or comply with deny mode, as shown in the run section.

### 6.3. Java 22+ — `src/demo/FfmCalc.java`

~~~java
package demo;

import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;

public final class FfmCalc {
    private FfmCalc() {
    }

    // Java callback: C sees a function pointer (int32_t) -> int32_t.
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                "build", "lib",
                System.mapLibraryName("calcbridge")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // int64_t sum_i32(const int32_t*, int32_t);
            MethodHandle sum = linker.downcallHandle(
                    symbols.find("sum_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            MemorySegment data = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 7, -2, 9);
            long total = (long) sum.invokeExact(data, 3);
            long empty = (long) sum.invokeExact(
                    MemorySegment.NULL, 0);

            System.out.println("FFM sum=" + total);
            System.out.println("FFM empty=" + empty);

            // int32_t call_unary(int32_t, int32_t (*)(int32_t));
            MethodHandle callUnary = linker.downcallHandle(
                    symbols.find("call_unary").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle javaTarget = MethodHandles.lookup()
                    .findStatic(
                            FfmCalc.class,
                            "twice",
                            MethodType.methodType(int.class, int.class));

            FunctionDescriptor callbackType =
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT);

            MemorySegment callback =
                    linker.upcallStub(javaTarget, callbackType, arena);

            int result = (int) callUnary.invokeExact(21, callback);
            System.out.println("FFM callback=" + result);
        }
    }
}
~~~

**Exact stdout** when built and granted native access properly:

~~~text
FFM sum=14
FFM empty=0
FFM callback=42
~~~

This code uses the standard **JDK 22** API (`java.lang.foreign`, `Arena.allocateFrom`, `Linker.downcallHandle`, `Linker.upcallStub`). **It does not compile on JDK 17 or JDK 21**; the demo code is not written for the incubator/preview APIs of those releases.

ABI and lifetime explanation:

1. `SymbolLookup.libraryLookup(path, arena)` loads/finds symbols at the **actual native file path**. `System.mapLibraryName` produces the appropriate platform name: typically `libcalcbridge.so` (Linux), `libcalcbridge.dylib` (macOS), `calcbridge.dll` (Windows).
2. `FunctionDescriptor.of(JAVA_LONG, ADDRESS, JAVA_INT)` describes a C return `int64_t`, pointer `const int32_t *`, and `int32_t count` on common ABIs. `ADDRESS` has the Java carrier type `MemorySegment`. `MethodHandle.invokeExact` requires exact argument/return signatures.
3. `arena.allocateFrom(JAVA_INT, 7, -2, 9)` allocates native memory (not a Java `int[]` object), copies the three numbers into it, and ties access lifetime to `arena`. C only reads the memory while `arena` is alive.
4. `MemorySegment.NULL` combined with `count=0` is valid under **the C function's contract in the example**; do not infer that every C function accepting a null pointer is safe.
5. `upcallStub` creates a C ABI function pointer calling Java's `twice`. C calls the callback **synchronously before returning**; it does not retain the stub after the arena closes. Native code cannot pass a `jobject` or use `JNIEnv` in this call.
6. Closing the arena at the end of `try` frees the memory segments allocated by the arena, invalidates the stub, and manages the corresponding library lookup lifetime. Do not store a MethodHandle/segment/stub beyond its scope and invoke it later.
7. The Java method `twice` does not throw exceptions in this test. For production callbacks, handle Java exceptions explicitly: never let an exception arbitrarily cross a C function pointer boundary.

The same C function `sum_i32` can be called from another C application if the ABI is followed; the JNI function depends on the VM. This illustrates why FFM fits **native APIs that are inherently JVM-independent**.

## 7. Compile the C Library Once, Run Both Java Paths

In the `native-choice` directory, always run `javac -h` first to generate `build/include/demo_JniCalc.h`. Whenever you change the package or native method signature, you must regenerate the header and rebuild C. For Java 17+ JNI, you can use JDK 17 alone; to run FFM as well, use **JDK 22+**.

### 7.1. Linux (GCC/Clang, C11)

~~~sh
mkdir -p build/classes build/include build/lib

javac -h build/include -d build/classes src/demo/JniCalc.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/calcbridge.c -o build/lib/libcalcbridge.so

java -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

Then, with **JDK 22+**:

~~~sh
javac -d build/classes src/demo/FfmCalc.java
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

On **JDK 24+**, if you want to enable native access explicitly for the JNI client:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

FFM `SymbolLookup.libraryLookup` uses an absolute file path constructed in Java, so `-Djava.library.path` is not needed in the FFM command; JNI `System.loadLibrary` searches for the logical library name via the Java native library search path.

### 7.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib

javac -h build/include -d build/classes src/demo/JniCalc.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/calcbridge.c -o build/lib/libcalcbridge.dylib

java -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

FFM client (JDK 22+):

~~~sh
javac -d build/classes src/demo/FfmCalc.java
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

If the JVM is Apple Silicon, the native library must match the JVM's architecture/ABI; renaming the file extension does not convert x86_64 to arm64.

### 7.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib

javac -h build\include -d build\classes src\demo\JniCalc.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\calcbridge.c ^
  /link /OUT:build\lib\calcbridge.dll

java -Djava.library.path=build\lib -cp build\classes demo.JniCalc
~~~

FFM client with JDK 22+:

~~~bat
javac -d build\classes src\demo\FfmCalc.java
java --enable-native-access=ALL-UNNAMED -cp build\classes demo.FfmCalc
~~~

Windows commands use **Command Prompt**, where `^` is cmd.exe's line continuation character. Use `cl` in the Developer Command Prompt and a JDK with matching x64 architecture. If the compiler or JNI headers belong to a different toolchain, verify the ABI and dependencies before mixing them.

### 7.4. Checking Exported Symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libcalcbridge.so
~~~

The output should include these symbol names (addresses and order are not fixed):

~~~text
sum_i32
call_unary
Java_demo_JniCalc_sum
~~~

macOS: `nm -gU build/lib/libcalcbridge.dylib` (the tool may prepend `_` to symbols). Windows: `dumpbin /exports build\lib\calcbridge.dll`. **FFM requires exported C ABI symbols such as `sum_i32`**, not `Java_demo_JniCalc_sum` unless you intentionally design a call to a JNI entry point (not recommended). JNI relies on the exported JNI name from `javac -h` and does not automatically resolve `sum_i32`.

**Note:** this is the same binary library exposing two APIs, but each demo runs in a **separate JVM process**. If a single JVM needs both JNI `System.loadLibrary` and FFM `libraryLookup` for the same library, check loader ownership, lifetime, synchronization, and multi-classloader rules; never call `dlclose`/`FreeLibrary` directly to interfere with a handle managed by the VM.

## 8. Comparing Ownership, Threading, and Boundary Errors

| Concern | JNI | FFM |
| --- | --- | --- |
| Java objects | `jobject`/`jclass`/`jarray`; JNI API knows the object model | C ABI only sees primitives/pointers, no direct knowledge of `jobject` |
| Java heap arrays | Has `Get<Type>ArrayElements`/`Get<Type>ArrayRegion` | Usually copies/marshals data to a native `MemorySegment`; do not assume Java `int[]` is a stable C pointer |
| Native memory | C `malloc/free`, native handles, or JNI borrowed pointers | `Arena` can own allocated segments; must still obey C-side `malloc/free` contracts |
| Threads | `JNIEnv *` is thread-bound; attach native threads if needed | Confined/shared arenas and scope checks; native worker threads/callbacks need clear policies |
| Callbacks | C uses `Call<Type>Method` on `jobject`/`jclass` | `upcallStub` turns a MethodHandle into a C function pointer |
| Exceptions | Pending Java exception on `JNIEnv`; `ThrowNew`/`ExceptionCheck` | Native C error codes/errno/return conventions decoded by wrapper; callback exceptions need deliberate handling |
| Method binding | `javac -h`, exported JNI name, or `RegisterNatives` | `SymbolLookup` + C ABI symbol + `FunctionDescriptor` |
| Cleanup | `DeleteLocalRef`/`DeleteGlobalRef`, release arrays/strings, native destroy | `Arena.close` for owned scopes; native APIs still need explicit free/close if memory was allocated in C |
| Safety | C can crash the JVM on pointer/prototype violations | MemorySegment checks Java-side bounds/lifetime; wrong native ABI/callback still crashes or corrupts |

### 8.1. FFM Does Not Automatically Free C Resources Just Because of Arena

If a native library returns a pointer from `malloc` and requires calling `free_buffer`, **Arena does not know the internal ownership of the library** unless you attach an appropriate cleanup policy. You must clearly define:

- Who allocates the memory? Java `Arena.allocate` or C `malloc`?
- Who frees it? `Arena.close`, `free_buffer(ptr)`, or another native destroy API?
- Is the pointer retained after the downcall returns?
- How long does native code keep the callback? Is there an `unregister_callback`/`stop` function that runs **before** closing the arena?
- Which functions allow null, empty data, large lengths, or special error codes?

Do not call `free` twice, do not close the arena while C still uses the pointer, and do not read a `MemorySegment` after closing. FFM reduces glue code, but it does not eliminate C ABI ownership agreements.

### 8.2. JNI Must Not Treat Every Handle as a Plain C Pointer

`jobject` may be an indirect handle managed by the JVM, not a stable address of a Java object. A C function taking `void *` has no right to use `jobject` as a raw struct; Java GC can move objects, and references have their own scopes. If a C library needs to process data, copy it to a native buffer or use JNI accessors with the proper lifetime, rather than arbitrarily forcing `jobject` through `MemorySegment`.

`jmethodID` is not like `jobject`; caching IDs must account for the defining class's lifetime and not keep them across classloader reloads. If a native library needs to manipulate Java ClassLoaders, exceptions, and real arrays/objects, keeping JNI for that integration layer is the right technical choice.

### 8.3. Native Callbacks Require Careful Design

JNI callbacks:

- Store `JavaVM *` if needed, attach/detach threads properly; **do not cache another thread's `JNIEnv *`**.
- If storing a Java object across calls, use `NewGlobalRef`/`DeleteGlobalRef` according to its lifecycle, do not retain a local ref.
- `Call<Type>Method` can cause Java to throw an exception; native code must stop/clear/propagate deliberately.

FFM callbacks:

- `Linker.upcallStub` binds a `MethodHandle` to a C ABI function pointer address and an arena scope.
- The stub must stay alive **for the entire duration** C might invoke it; if C stores the callback, you must unregister/stop and wait for in-flight calls to finish before closing the arena.
- The callback is invoked on whichever thread native code chooses; thread confinement, thread attachment, and exception handling may need consideration depending on the runtime and native API contract.
- **Do not let Java exceptions escape unchecked across a C ABI**; translate errors into error codes/results or handle them at the callback layer before returning to C.

In the demo, `call_unary` invokes immediately on the same thread and does not retain the pointer. For C functions that register an asynchronous event handler, do not copy the example and close `Arena.ofConfined()` right after calling `register_callback`: that creates a dangling callback.

## 9. Making the Decision With Two Questions in Order

**Question 1: What is the actual Java baseline?**

- **Must run on Java 17**: do not use final FFM 22 code. If a bridge is needed in current Java SE, JNI is the stable path; if third-party libraries are acceptable, also evaluate JNA/JNR based on maintenance, overhead, native-access requirements, and project policy.
- **Must run on Java 21 LTS and preview is not allowed**: use JNI for production bridges or wait for a baseline upgrade; do not treat Java 21's preview `java.lang.foreign` as a final API.
- **Java 22+ baseline**: standard FFM can be used; proceed to ask whether the C API is sufficiently JVM-independent.
- **Multiple baselines simultaneously**: keep a stable Java interface layer, package separate implementations (JNI for older, FFM for newer) via dependency/version selection; avoid forcing an older JVM to load classes referencing APIs that only exist in newer JDKs.

**Question 2: What access to the JVM does the native code need?**

- **Only C ABI/foreign memory/function pointer callbacks**: usually start with FFM if the JDK allows it.
- **Needs to read/write fields, call Java methods, create Java objects, pass Java arrays as Java objects, manage ClassLoaders or exceptions**: choose JNI for this part.
- **Needs both**: separate a JVM-independent C core; use a small JNI wrapper where required and an FFM wrapper for pure ABI APIs.
- **Embedding a JVM from a C/C++ application**: consider the JNI Invocation API (FFM from Java does not initialize a JVM for a host).
- **Native SDK only has a complex C++ ABI**: usually create a **C ABI wrapper** (`extern "C"`, opaque handles, exported functions) first; C++ name mangling, exceptions, and compiler ABIs do not automatically become FFM/JNI-friendly.

## 10. Scenario and Recommendation Table

| Scenario | Preferred Decision | Why |
| --- | --- | --- |
| Java 17 service calling a C library for computation | **JNI** or a 17-compatible binding library | Cannot use FFM final API when the runtime is 17 |
| Java 21 LTS, no-preview policy, C ABI native SDK | **JNI now**, plan FFM when upgrading JDK | FFM 21 is still preview |
| Java 22+ calling a C SDK with primitives, pointers, and structs | **FFM** | Has standard downcalls, MemoryLayout, Arena, SymbolLookup |
| Java 22+ needing an `int (*)(int)` callback, not stored long-term | **FFM upcallStub** | Callback is a C function pointer with a clear ABI contract |
| C needs to hold `jobject` and call Java instance methods | **JNI** | Only JNI provides the object model and `JNIEnv` |
| Native thread must call a Java method on a specific class loader | **JNI** for the JVM access part | Needs JavaVM/attach, refs, lookup, exceptions |
| Inherited legacy JNI library working well | **No mandatory rewrite** | Migration carries cost/risk; only change when measurable benefits exist |
| Native engine shared across Java, Python, Node | **Stable C ABI + FFM wrapper** (Java 22+) | Avoids coupling the engine to Java |
| Java 22+ calling a C++ SDK lacking a C ABI | **C ABI adapter first**, then FFM or JNI | FFM does not understand vtables/unstable C++ ABIs |
| Embedded JVM started by a C host | **JNI Invocation API** | Needs `JNI_CreateJavaVM` and VM management from native |
| Plugin module needing frequent unload/reload | **Design lifetime first**, then choose JNI/FFM per bridge | Global jclass refs, Arenas, and callbacks can all pin or cause use-after-free |
| Application not allowed to enable native access | **Do not use restricted JNI/FFM operations** for that part | Runtime/policy permissions matter more than how the binding is written |

Remember: **JNI is not an "old technology that must always be abandoned"; FFM is not a "new technology that is automatically faster".** The right decision comes from the JDK baseline, ABI, object-dependency, ownership, and native access permissions.

## 11. Migrating From JNI to FFM: Not a Search/Replace API Swap

A controlled migration should follow these steps:

1. **Current inventory:** list native declarations, generated headers, function calls, `JNIEnv` operations, global refs, arrays/Strings, exception mapping, callbacks, and native threads.
2. **Categorize and separate:** mark functions that truly handle **pure C ABI**, functions dependent on JVM objects, and hybrid functions. Only pure functions are candidates for direct FFM downcalls.
3. **Stabilize the C contract:** export clear API function names, fix `int32_t`/`int64_t` types or ABI mappings, and document ownership, nullability, error status, alignment, struct packing, and callback lifetime.
4. **Upgrade Java baseline if needed:** JDK 17/21 will not run final 22 code; do not assume deployed services are upgraded just because local dev runs 22+.
5. **Create the FFM wrapper:** `SymbolLookup`, `FunctionDescriptor`, `MemoryLayout`, `Arena`; consider using **jextract** (a tool that generates bindings from C headers, not a built-in `javac` option) for complex native headers.
6. **Keep JNI where needed:** Java object callbacks, ClassLoader, Java exceptions, native methods operating on `jobject`; do not cast them to raw C pointers.
7. **Design error handling:** translate C error codes, errno, or error objects into Java exceptions in the Java wrapper; in JNI, preserve pending exception semantics. Do not let C++ exceptions cross the C ABI.
8. **Manage lifetimes:** close arenas at the right time, free C allocations via native APIs, unregister callbacks and stop worker threads, delete JNI refs according to their owner.
9. **Check native access policy:** classpath/unnamed modules or module names; on JDK 24+, test with `--illegal-native-access=deny` to catch unauthorized code.
10. **Compare results and performance:** test parity, binary compatibility, OS/architecture matrix, cold start, throughput/latency, allocation/GC. Use JMH/benchmarks with proper warmup and batching; do not draw conclusions from a single microbenchmark.

### 11.1. Plan for Splitting a Legacy JNI Wrapper

If currently:

~~~text
Java -> nativeCompute(jintArray) -> C algorithm
~~~

then splitting can proceed in two phases:

~~~text
PHASE 1 (unchanged Java API):
Java 17 -> JNI wrapper -> C ABI core

PHASE 2 (after baseline >=22):
Java 22+ -> FFM downcall -> same C ABI core
                    |
             JNI wrapper still exists for JVM-object-dependent calls
~~~

This avoids removing JNI across the entire system. Ensure **only one owner** for a native context if both bridges can access it concurrently; each wrapper must respect the same locking and free protocol. If an API must return a Java object, switching to FFM does not magically provide object representation; you must return data as bytes/structs/handles and perform the mapping in Java or keep JNI.

## 12. Common Mistakes When Choosing a Technology

**Mistake 1 — "Java 17 has FFM so JDK 22 `java.lang.foreign` code will run".** False: Java 17 has a different incubator API, not the final `java.lang.foreign`.

**Mistake 2 — "Java 21 LTS means FFM is final".** False: Java 21's FFM is the third preview. Production policies may prohibit preview code.

**Mistake 3 — "FFM upcall replaces all JNI calls".** An upcall stub is a C function pointer to a Java MethodHandle; it **does not** let C directly manipulate `jobject`, Java fields, class loaders, or pending Java exceptions via `JNIEnv`.

**Mistake 4 — "JNI is always slower than FFM" or vice versa.** Overhead depends on how data is copied, call count, pin/copy, JIT, critical calls, struct marshalling, callbacks, and workload. Benchmark under real deployment conditions before deciding.

**Mistake 5 — "Arena.close() automatically calls C free for every pointer".** Only memory owned by the arena or configured with matching cleanup follows that lifecycle. Allocations via `malloc` from a C SDK need matching free/destroy calls.

**Mistake 6 — "`MemorySegment` makes C as safe as Java".** FFM checks Java-side accesses within the segment's scope/bounds, but a C function can still read the wrong number of elements, follow a garbage pointer, or write out of bounds.

**Mistake 7 — "Native access warnings are compile errors".** From JDK 24, warnings for restricted JNI/FFM operations may appear at runtime; policy can turn them into denials. Fix this by configuring modules properly and understanding the deployer's permissions, not by renaming JNI functions.

**Mistake 8 — "C `long` and Java `long` are both 64-bit on every OS".** False; C `long` is usually 32-bit on Windows x64 but 64-bit on Linux x64. Use fixed-width types or canonical layouts and verify the ABI.

**Mistake 9 — "An exported C++ method has a name similar to a Java method so FFM can find it".** C++ name mangling/ABI is unstable across toolchains. Create a C ABI wrapper with `extern "C"` and explicit exports before using FFM.

**Mistake 10 — "You can close the arena right after registering an asynchronous callback".** False: C may retain the function pointer and call it after the stub is invalidated; you must unregister, stop, wait for in-flight calls, and only then close.

**Mistake 11 — "Use the same native pointer in both FFM and JNI and either side can close first".** No: ownership/synchronization must be unified, otherwise double-free/use-after-free is likely.

**Mistake 12 — "Every Java array can be passed straight as a C pointer".** The Java heap belongs to the JVM/GC; JNI has borrowed accessors, while FFM usually uses off-heap buffers/marshalling. Do not arbitrarily turn `int[]` into a C buffer address.

## 13. Self-Check Questions

1. A service forced to run on **JDK 17** uses a C SDK that only takes `int*` and returns `double`. Why won't JDK 22's final FFM code compile on that service? Without changing the Java baseline, which approach should you choose?
2. A **JDK 21** app allows preview features, but the operations team does not want `--enable-preview` in production. Should you write production FFM 21 bindings?
3. Native C has `void notify(JNIEnv*, jobject)` and needs to call a Java method on the object. Can FFM `upcallStub` directly perform `JNIEnv`'s work?
4. A C library has `int square(int)` and callback `int (*)(int)` on **JDK 22**. When is FFM suitable, and when do you need to keep the callback stub/arena alive longer?
5. A native function returns a buffer allocated with `malloc`. Is `Arena.ofConfined().close()` alone enough to free that buffer if the buffer was not allocated by the arena?
6. You see a warning from `System.loadLibrary` on JDK 24. Is this an `UnsatisfiedLinkError` or a native access policy? What flag do you need for code in the unnamed module?
7. A legacy JNI library has hundreds of `GetFieldID`/`CallObjectMethod` calls but only a few C computations. Should you rewrite everything to FFM or separate the C ABI core and keep JNI for JVM objects?
8. On Windows x64, a C header uses `long`. Can you always use `ValueLayout.JAVA_LONG` for it?
9. An FFM upcall callback is kept by C to be called a minute later, but the arena closes right after registration. What lifetime bug occurs?
10. Two bindings share ownership of a native handle. What design prevents them from double-freeing?

### Short Answer Hints

1. Java 17's incubator API differs from final FFM 22; keep JNI/a 17-compatible binding library or upgrade the JDK.
2. No: preview does not meet policy; use JNI or wait for a baseline upgrade.
3. No: FFM upcall only presents a function pointer according to the C ABI; JNI is required for the object model.
4. FFM fits when the ABI is pure; the stub must live at least until the final callback; unregister before closing.
5. No: you must call the corresponding free/destroy API or attach a valid cleanup.
6. Native access policy if the library loads with a warning; use `--enable-native-access=ALL-UNNAMED` (or the module name).
7. Separate the C ABI core, keep JNI for JVM-dependent tasks, and evaluate FFM on JDK 22+.
8. No; check canonical ABI layouts, especially Windows LLP64 vs Linux LP64.
9. C may call an invalidated function pointer; use-after-scope/crash.
10. Single owner, close/reference-counting protocol, synchronization, and double-free protection.

## 14. Final Decision Checklist

- **JDK:** Is the production minimum 17, 21, or 22+? Are incubator/preview features allowed? Do build and runtime use the same API release?
- **JVM objects:** Does native code need direct access to `jobject/jclass/jarray`, Java fields, methods, exceptions, class loaders, or the Invocation API?
- **C ABI:** Are there JVM-independent headers/exported symbols? Are signatures/memory layouts, alignment, `size_t/long`, and C++ name mangling understood?
- **Lifetime:** Do MemorySegment/Arena, JNI refs, native pointers, async callbacks, worker threads, and close/unregister have clear owners?
- **Errors:** Are Java exceptions and native error codes/errno translated properly, without letting C++ exceptions cross boundaries or ignoring pending JNI exceptions?
- **Native access:** Is permission enabled on the right named/unnamed module and tested for warnings/denials on the target JDK?
- **Portability:** Are shared libraries built for the exact OS/CPU/ABI and tested against the actual Java runtime?
- **Performance:** Have you measured batching, copy-vs-view, callback overhead, memory allocation, and GC instead of guessing?
- **Migration:** If currently using JNI, which parts can genuinely be split into a C ABI for FFM to call? Do multiple Java versions need support?
- **Testing:** Are there tests for correctness, null/empty, overflow, errors, ownership, wrong-thread, out-of-scope, and callback shutdown?

**Conclusion:** Choose along **two priority axes**: (1) whether the JDK version provides **stable** FFM, and (2) whether native code must manipulate the **JVM object model** or only needs the **C ABI/foreign memory**. With Java 22+ and a pure C API, FFM is usually a reasonable starting point; with JDK 17/21 without preview, or when native code needs `JNIEnv/jobject`, JNI remains the appropriate tool. A system can use both without conflict, provided the ABI, native access, and ownership are clearly defined.

### Official Documentation

- Oracle, [JDK 17 `jdk.incubator.foreign`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/module-summary.html): incubator, differs from the final API.
- Oracle, [JDK 21 Preview List](https://docs.oracle.com/en/java/javase/21/docs/api/preview-list.html): `java.lang.foreign` is still FFM third preview (JEP 442).
- Oracle, [JDK 22 Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FFM final, downcall, upcall, Arena, and native memory.
- Oracle, [JDK 22 `Linker`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): FunctionDescriptor, ABI, downcall/upcall.
- Oracle, [JDK 22 `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): native symbol lookup, library lifetime.
- Oracle, [JDK 22 `Arena`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocation, scope, thread confinement.
- Oracle, [JDK 17 JNI Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): object model, native methods, references, Invocation API.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): finalizing FFM in JDK 22.
- OpenJDK, [JEP 472](https://openjdk.org/jeps/472): native access restrictions and JNI/FFM warnings from JDK 24.