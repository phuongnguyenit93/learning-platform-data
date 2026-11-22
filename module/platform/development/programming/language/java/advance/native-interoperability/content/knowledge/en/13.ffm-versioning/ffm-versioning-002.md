# Distinguishing the Preview FFM API in JDK 21 from the Final API from JDK 22

## 1. Why is it necessary to distinguish JDK 21 and JDK 22?

The **Foreign Function & Memory API (FFM)** allows Java to call native functions according to the C ABI and manipulate memory regions outside the Java heap. Instead of having to write a JNI C layer for every call, Java can obtain the symbol address in a native library, create a `MethodHandle` through `Linker`, and use `MemorySegment`/`Arena` to manage data.

**Key points of the topic:**

- **JDK 21:** FFM belongs to **JEP 442 — Third Preview**. This is an experimental API at the *preview* level, not yet officially stable. Compiling and running programs that use FFM requires enabling `--enable-preview`.
- **JDK 22:** FFM is **finalized under JEP 454** and becomes an official API in Java SE 22. Code using **final FFM** does not need `--enable-preview` just because of FFM.
- **Not just changing runtime flags:** several method names change from 21 to 22, notably `allocateUtf8String` → `allocateFrom`, `allocateArray` → `allocateFrom`, `getUtf8String` → `getString`, `setUtf8String` → `setString`.
- **Do not confuse preview with restricted native access:** after FFM is finalized in 22, native linking/calling operations in the restricted group still require handling the `--enable-native-access` permission policy.

Goal of this lesson: understand the API status by version, identify actual changes in source code, know the exact `javac`/`java` commands, be able to run JDK 21 and JDK 22 examples, and avoid errors caused by native ABI, scope, and preview class files.

## 2. Timeline of FFM from incubator to final

| JDK | JEP | Status | Notable location |
|---|---|---|---|
| **17** | JEP 412 | First incubator | `jdk.incubator.foreign` |
| **18** | JEP 419 | Second incubator | `jdk.incubator.foreign` |
| **19** | JEP 424 | First preview | `java.lang.foreign` |
| **20** | JEP 434 | Second preview | `java.lang.foreign` |
| **21** | **JEP 442** | **Third preview** | `java.lang.foreign`, requires preview flags |
| **22** | **JEP 454** | **Final / standard** | `java.lang.foreign`, no longer preview for FFM |

**Incubator** is the stage where an API is tested in a dedicated module and may undergo major design or naming changes. **Preview** is a step closer to the standard, integrated into the JDK but still **not permanent**; users must explicitly enable the preview flag. **Final** is the standard API status of Java SE.

Do not write that “FFM was officially released in Java 21”: JDK 21 only has the third preview. JDK 22 is the **first** release to finalize FFM as an official API. An application may use JDK 22 while still enabling preview for **another feature**; that does not put FFM back into preview.

In particular, old tutorials containing:

~~~java
import jdk.incubator.foreign.*;
~~~

are from the incubator stage (such as 17/18), and are **not** valid examples for FFM third preview 21 or final 22. In the two versions to learn here, the imports will be `java.lang.foreign`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

The two blocks above are **import snippets**, not standalone Java programs.

## 3. Core concepts retained across both versions

| API Type | Role |
|---|---|
| `Arena` | Allocates native memory and manages its lifetime; supports confined, shared, automatic, and global arenas |
| `MemorySegment` | Represents a memory region and native address; has bounds, scope, and thread checks |
| `MemoryLayout` and `ValueLayout` | Describes size/alignment/layout of native data and Java carrier type |
| `FunctionDescriptor` | Describes the **C function** signature according to the native ABI, not a JNI-style JVM signature |
| `Linker` | Converts a `FunctionDescriptor` and native address into a `MethodHandle`; supports upcalls |
| `SymbolLookup` | Finds native symbols in a library or an appropriate lookup set |
| `MethodHandle` | JVM object representing an invocation with a defined Java signature |

Example downcall diagram:

~~~text
Java program
    |
    | SymbolLookup.libraryLookup(path, arena)
    v
Native library is loaded and has symbol "ffm_add"
    |
    | lookup.find("ffm_add")
    v
MemorySegment representing the native function address
    |
    | Linker.nativeLinker().downcallHandle(symbol, FunctionDescriptor)
    v
MethodHandle in Java
    |
    | invokeExact(7, 5)
    v
C function ffm_add(7, 5)
    |
    v
Java receives 12
~~~

When FFM becomes final, the concepts of `Arena`/`MemorySegment`/`Linker` do not disappear. The main differences are **API status**, several methods having **standardized names and capabilities**, and build/run configurations. One should not assume “same class names” means source code across all versions is completely compatible.

## 4. Comparison table of JDK 21 preview and JDK 22 final

| Item | **JDK 21 (JEP 442)** | **JDK 22 (JEP 454)** |
|---|---|---|
| API status | Third preview | Final |
| Package | `java.lang.foreign` | `java.lang.foreign` |
| Module | `java.base` | `java.base` |
| Compile using FFM | `javac --enable-preview --release 21 ...` | `javac --release 22 ...` |
| Run using FFM | `java --enable-preview ...` | `java ...` |
| Allocate UTF-8 C string | `arena.allocateUtf8String("Hi")` | `arena.allocateFrom("Hi")` |
| Allocate native array with data | `arena.allocateArray(JAVA_INT, 1, 2, 3)` | `arena.allocateFrom(JAVA_INT, 1, 2, 3)` |
| Allocate and initialize a primitive | `arena.allocate(JAVA_INT, 42)` | `arena.allocateFrom(JAVA_INT, 42)` |
| Read UTF-8 C string | `segment.getUtf8String(0)` | `segment.getString(0)` |
| Write UTF-8 C string | `segment.setUtf8String(0, "Hi")` | `segment.setString(0, "Hi")` |
| Specify charset for C string | UTF-8-specific APIs | Has `allocateFrom(String, Charset)` and `getString`/`setString` with `Charset` |
| Canonical layout of C ABI | Does not have `Linker.canonicalLayouts()` | Has `Linker.canonicalLayouts()` |
| Restricted native calls | `--enable-native-access` policy | **Still present**, independent of preview |
| `Arena.ofConfined()`, `FunctionDescriptor.of(...)` | Present (preview) | Present (final) |

**Not the entire API was rewritten:** code using `Linker.nativeLinker`, `SymbolLookup.libraryLookup`, and `FunctionDescriptor.of` for basic cases can look almost identical between the two versions. However, code using the old overloads for creating native strings/arrays may not compile on 22.

Three allocation forms must be distinguished:

~~~text
JDK 22:
arena.allocate(16)                   // Allocate 16 bytes, no source data
arena.allocate(ValueLayout.JAVA_INT) // Allocate region by layout
arena.allocateFrom(JAVA_INT, 42)      // Allocate region then copy one int value
arena.allocateFrom(JAVA_INT, 1,2,3)   // Allocate region then copy int elements
~~~

This is a **syntax comparison**, not a standalone Java file. Do not mechanically replace all `allocate(...)` with `allocateFrom(...)`: only choose `allocateFrom` when there is actually **initial input data**.

## 5. Runnable example on JDK 21: foreign memory preview part

First, practice with memory only to avoid differences in native libraries and C ABI. In the working directory, create a file named **`Ffm21Memory.java`**.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class Ffm21Memory {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers =
                    arena.allocateArray(ValueLayout.JAVA_INT, 2, 4, 6);

            int total =
                    numbers.getAtIndex(ValueLayout.JAVA_INT, 0)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 1)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 2);

            MemorySegment text = arena.allocateUtf8String("FFM");
            System.out.println("sum = " + total);
            System.out.println("text = " + text.getUtf8String(0));
        }
    }
}
~~~

The file above is a **complete Java 21 program**. Check that the terminal is using **JDK 21** before compiling:

~~~bash
java -version
javac -version
javac --enable-preview --release 21 Ffm21Memory.java
java --enable-preview Ffm21Memory
~~~

**Program stdout:**

~~~text
sum = 12
text = FFM
~~~

The compiler/JVM may print additional **preview diagnostics** on stderr; those lines are not application stdout.

Mechanism:

1. `Arena.ofConfined()` creates an arena managing native memory with a clear lifecycle, bound to the current thread.
2. `allocateArray(JAVA_INT, 2, 4, 6)` allocates memory for three integers and copies them into the segment.
3. `getAtIndex(JAVA_INT, i)` reads the `i`-th element in **element** units, not byte offsets. `2 + 4 + 6 = 12`.
4. `allocateUtf8String("FFM")` encodes the Java string into a null-terminated UTF-8 C string.
5. `getUtf8String(0)` reads the string from byte offset 0 up to the first NUL byte.
6. Try-with-resources calls `arena.close()` when exiting. Using a segment belonging to a closed arena violates its lifecycle.

Because this is only **allocating and reading memory**, without creating a native downcall handle or loading a library via restricted lookup, the example does not need `--enable-native-access`. It **still needs `--enable-preview`**, because the FFM API on JDK 21 is not yet finalized.

### 5.1. Old JDK 21 methods to recognize

~~~java
// Snippet in JDK 21 preview, assuming arena/segment are valid.
arena.allocateUtf8String("Hello");
arena.allocateArray(ValueLayout.JAVA_INT, 10, 20, 30);
arena.allocate(ValueLayout.JAVA_INT, 42);

segment.getUtf8String(0);
segment.setUtf8String(0, "OK"); // Segment must have enough bytes.
~~~

This is an **illustrative snippet**, not a complete program. The three `allocate...` lines show three ways of initializing from source data. In 22, those usages are standardized under the name `allocateFrom`. Do not copy the methods above verbatim into a 22 project.

## 6. Equivalent example runnable on JDK 22 final

Create the file **`Ffm22Memory.java`**, without reusing the class name `Ffm21Memory` to avoid artifact confusion.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class Ffm22Memory {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers =
                    arena.allocateFrom(ValueLayout.JAVA_INT, 2, 4, 6);

            int total =
                    numbers.getAtIndex(ValueLayout.JAVA_INT, 0)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 1)
                  + numbers.getAtIndex(ValueLayout.JAVA_INT, 2);

            MemorySegment text = arena.allocateFrom("FFM");
            System.out.println("sum = " + total);
            System.out.println("text = " + text.getString(0));
        }
    }
}
~~~

Using **JDK 22**:

~~~bash
java -version
javac -version
javac --release 22 Ffm22Memory.java
java Ffm22Memory
~~~

**Exact stdout:**

~~~text
sum = 12
text = FFM
~~~

The computation and memory region are equivalent to the 21 example; only the APIs related to **data initialization** and **reading C strings** changed, and the preview flags are removed.

Compare the key lines:

~~~diff
- arena.allocateArray(ValueLayout.JAVA_INT, 2, 4, 6)
+ arena.allocateFrom(ValueLayout.JAVA_INT, 2, 4, 6)

- arena.allocateUtf8String("FFM")
+ arena.allocateFrom("FFM")

- text.getUtf8String(0)
+ text.getString(0)
~~~

The diff only illustrates what needs to change; the full runnable file is above.

### 6.1. Differences in string charset

JDK 22 allows working with **C strings** using a specified charset, for example:

~~~java
// JDK 22, snippet within an open Arena arena scope.
MemorySegment utf8 = arena.allocateFrom(
        "Java", java.nio.charset.StandardCharsets.UTF_8
);
String text = utf8.getString(
        0, java.nio.charset.StandardCharsets.UTF_8
);
~~~

This is not a standalone runnable Java file. If no `Charset` is passed, `allocateFrom(String)` and `getString(long)` use UTF-8 by specification. A C string has a terminating **NUL byte**; if the content contains a NUL in the middle, string reading may terminate early. When using `setString`, you must allocate **enough bytes** for the encoded string and terminator, not just rely on `String.length()`.

Do not assume one Java `char` always corresponds to one UTF-8 byte. For Vietnamese characters or emoji, the UTF-8 byte size often differs from the number of UTF-16 code units. Whenever exchanging data with a C library, check the charset and length rules of that library itself.

## 7. Native downcall example — same C library, two JDK versions

To learn the **foreign function part** of FFM, we use a small C function:

~~~c
int ffm_add(int a, int b);
~~~

It takes two C integers and returns their sum. On common desktop platforms used for examples, C `int` corresponds to the layout type `ValueLayout.JAVA_INT`. For a real native API, **the C ABI must be verified**, because some C types such as `long` or `size_t` vary in width by OS/architecture.

### 7.1. Native file: `ffm_math.c`

~~~c
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

FFM_EXPORT int ffm_add(int a, int b) {
    return a + b;
}
~~~

This is a **complete C file**. Unlike JNI, it does not need `jni.h`, `JNIEnv *`, or an export named `Java_...`. The C symbol `ffm_add` is exported so FFM can obtain its address with `SymbolLookup`.

Compile using one of the following commands, in the directory containing the C file:

**Linux (GCC or Clang):**

~~~bash
cc -fPIC -shared ffm_math.c -o libffm_math.so
~~~

**macOS (Clang):**

~~~bash
cc -fPIC -dynamiclib ffm_math.c -o libffm_math.dylib
~~~

**Windows (MSVC Developer Command Prompt, `cmd.exe`):**

~~~bat
cl /LD ffm_math.c /Fe:ffm_math.dll
~~~

Choose a compiler and binary with the same architecture as the JVM. You cannot load a Windows `.dll` file on Linux or a 32-bit library into a 64-bit JVM process. The native filenames differ, but the C function name `ffm_add` is the same.

### 7.2. JDK 21 preview: `Ffm21Call.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class Ffm21Call {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                System.mapLibraryName("ffm_math")
        ).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    library, arena
            );
            MemorySegment symbol = lookup.find("ffm_add")
                    .orElseThrow();

            MethodHandle add = Linker.nativeLinker()
                    .downcallHandle(
                        symbol,
                        FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT
                        )
                    );

            int value = (int) add.invokeExact(7, 5);
            System.out.println("native = " + value);
        }
    }
}
~~~

This is a **complete program for JDK 21 preview**. `System.mapLibraryName("ffm_math")` generates the OS-specific library name, and `toAbsolutePath()` points to the newly built binary in the current directory. Run the terminal in the exact directory containing the library file.

Compile and run with JDK 21:

~~~bash
javac --enable-preview --release 21 Ffm21Call.java
java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call
~~~

**Application stdout:**

~~~text
native = 12
~~~

Step-by-step explanation: `SymbolLookup.libraryLookup(path, arena)` loads/references the native library; `find("ffm_add")` finds the function address; `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` describes a **C function returning int and taking two ints**; `Linker.nativeLinker().downcallHandle` creates the Java method handle; `invokeExact(7, 5)` calls the native code and receives `12`.

In this example there are two distinct mechanisms:

- `--enable-preview`: required because FFM preview is being used in **JDK 21**.
- `--enable-native-access=ALL-UNNAMED`: grants permission for code on the **classpath** to use restricted FFM operations, such as `libraryLookup` and creating downcall handles.

`ALL-UNNAMED` is a special name referring to code in unnamed modules, not an invented module name. Permission must be granted by actual module name if the application uses named modules.

### 7.3. JDK 22 final: `Ffm22Call.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class Ffm22Call {
    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                System.mapLibraryName("ffm_math")
        ).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    library, arena
            );
            MemorySegment symbol = lookup.find("ffm_add")
                    .orElseThrow();

            MethodHandle add = Linker.nativeLinker()
                    .downcallHandle(
                        symbol,
                        FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT
                        )
                    );

            int value = (int) add.invokeExact(7, 5);
            System.out.println("native = " + value);
        }
    }
}
~~~

Compile and run with **JDK 22**:

~~~bash
javac --release 22 Ffm22Call.java
java --enable-native-access=ALL-UNNAMED Ffm22Call
~~~

**Stdout:**

~~~text
native = 12
~~~

Important notes:

- The downcall code is **very similar to JDK 21** because basic `Linker`, `SymbolLookup`, and `FunctionDescriptor` still have a similar shape. Do not imagine that every FFM API changed when finalized.
- The run command **does not need `--enable-preview`**, because FFM is official in JDK 22.
- The command still specifies **`--enable-native-access=ALL-UNNAMED`** because library lookup and downcalls are restricted operations. Native access policy and final status are **two independent concepts**.
- The lifetime of the symbol lookup depends on the arena. Do not store the method handle for use after the arena closes and the library may be unloaded.
- `invokeExact` requires exact Java carrier types. For the descriptor `(int,int) -> int`, the call passes two `int`s and casts the result to `int`. Using the wrong Java carrier may cause a `WrongMethodTypeException`; declaring the wrong **native C ABI** can have more severe consequences.

**Compared to JNI:** this is a call to the C symbol `ffm_add`, not a Java method declared `native` and without a JNI C implementation like `Java_package_Class_method`.

### 7.4. FFM FunctionDescriptor is not a JNI method descriptor

FFM declares a C function returning `int` and taking two `int`s:

~~~java
FunctionDescriptor.of(
    ValueLayout.JAVA_INT, // return type
    ValueLayout.JAVA_INT, // parameter a
    ValueLayout.JAVA_INT  // parameter b
);
~~~

This is an FFM snippet; in JNI, a Java method taking two ints and returning int has the string descriptor `(II)I`. The two mechanisms are not interchangeable: FFM `FunctionDescriptor` is a **set of MemoryLayout/ValueLayout for the C ABI**, and does not directly accept the JVM string `"(II)I"`.

## 8. Useful new feature in JDK 22: Linker.canonicalLayouts()

When writing FFM native functions, determining the **exact C type layout** is the caller's responsibility. Not all C type names have the same width across platforms:

- C `int` typically corresponds to 32-bit on sample platforms.
- C `long` is usually 64-bit on Linux x64 but 32-bit on Windows x64.
- C `size_t` usually follows pointer width: 32-bit or 64-bit depending on the ABI.

In JDK 21, the FFM library did not have the `Linker.canonicalLayouts()` method. **JDK 22 adds this method** to look up a map of canonical C type layouts for the current native ABI.

Example **JDK 22-only snippet**:

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
System.out.println(sizeT);
~~~

Do not assign a fixed stdout to this snippet: the layout's string value depends on the native linker/JVM/ABI; the map contains keys provided by the platform. You must check that `sizeT` is not `null` and verify the layout type before using it.

`canonicalLayouts()` helps reduce guessing C type sizes, **but it does not automatically infer a native function's prototype**. For `struct`, `union`, callbacks, or C pointers to unknown-sized regions, you still must inspect the real header and C ABI, and manage alignment and lifetime.

## 9. Two independent flag types: preview and native access

### 9.1. Enabling preview in JDK 21

~~~bash
javac --enable-preview --release 21 Ffm21Memory.java
java --enable-preview Ffm21Memory
~~~

JDK 21 requires preview flags for FFM. Omitting compile/run flags can cause errors related to preview APIs or preview class files. To build **FFM JDK 21**, use **JDK 21's `javac`**; do not take JDK 22's `javac` and pass `--enable-preview --release 21` as a way to “cross-compile” preview. Preview features are selected according to the actual compiler version.

### 9.2. Do not enable preview just for FFM in JDK 22

~~~bash
javac --release 22 Ffm22Memory.java
java Ffm22Memory
~~~

The commands above only require JDK 22 and have no native downcall. If an application **also uses another preview feature** of JDK 22, that project may still need preview flags **for that other feature**, not for FFM.

### 9.3. Native access still must be considered in both versions

FFM methods such as `SymbolLookup.libraryLookup` or `Linker.downcallHandle` involve native code that is unsafe at the ABI level and are restricted by the **restricted methods** policy. For programs running on the classpath:

~~~bash
java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call
java --enable-native-access=ALL-UNNAMED Ffm22Call
~~~

These are **two commands for two different versions**, not running the same binary/class on one JVM. The `--enable-native-access` flag grants permission to use restricted methods without warnings or blocking under the corresponding policy.

In **JDK 21/22**, if the native access flag is not specified, some restricted methods may still run while emitting a warning. Conversely, if permission is granted **only to certain modules** and the calling module is not in that list, an `IllegalCallerException` may occur. For responsible deployment, explicitly grant permission to the right modules; do not rely on default warning behavior as a production policy.

Newer JDK releases may change the warning/blocking mode for native access. **Do not apply rules from newer versions backward to JDK 21/22**; always read the JDK documentation for the actual runtime version.

### 9.4. Quick command matrix

| Task | JDK 21 preview | JDK 22 final |
|---|---|---|
| Compile memory sample | `javac --enable-preview --release 21 Ffm21Memory.java` | `javac --release 22 Ffm22Memory.java` |
| Run memory sample | `java --enable-preview Ffm21Memory` | `java Ffm22Memory` |
| Compile native-call sample | `javac --enable-preview --release 21 Ffm21Call.java` | `javac --release 22 Ffm22Call.java` |
| Run native-call sample | `java --enable-preview --enable-native-access=ALL-UNNAMED Ffm21Call` | `java --enable-native-access=ALL-UNNAMED Ffm22Call` |

**Remember:** every command in column 21 must use JDK 21, and every command in column 22 must use JDK 22. The commands for the native-call sample also require the C library file built for the matching OS/CPU.

## 10. Arena lifecycle: final API does not remove safety rules

Both JDK 21 and 22 have the main arena types:

| Arena | Lifecycle | Thread access | Can be closed explicitly? |
|---|---|---|---|
| `Arena.ofConfined()` | Bounded, closed by developer | Thread that created the arena | Yes |
| `Arena.ofShared()` | Bounded, closed by developer | Multiple threads allowed | Yes |
| `Arena.ofAuto()` | Managed by JVM/GC | Multiple threads allowed | No |
| `Arena.global()` | Unbounded lifetime | Multiple threads allowed | No |

Example with `ofConfined`:

~~~text
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);
    ... valid access while arena is alive ...
}
   |
   v
arena.close() makes the scope no longer alive
   |
   v
Accessing segment again -> lifecycle error, must not be used
~~~

The above is a **diagram**, not a valid Java program to copy verbatim.

FFM performs spatial/temporal/thread boundary checks at the `MemorySegment` level, but **does not make every native address safe**. When a native function returns a pointer with an unknown size, manually expanding its scope via a restricted API (such as `reinterpret`) can lead to invalid memory reads/writes or a JVM crash. If an asynchronous callback holds an address belonging to a closed arena, that is also a lifetime bug.

In particular, do not equate **Java GC** with freeing native memory: `Arena.ofConfined()` closes explicitly at the right time; `Arena.ofAuto()` lets the JVM decide when to clean up. A C library that allocates with `malloc` may require calling `free` or a dedicated release function; closing an arena does not mean all foreign resources created by the library are reclaimed.

## 11. Checklist for migrating FFM source 21 → 22

When upgrading a codebase that uses FFM preview, follow this order:

1. **Identify the toolchain**: select JDK 22 and verify `java -version`/`javac -version` locally, in the IDE, and in CI. Do not rely on `JAVA_HOME` if `PATH` points to another JDK.
2. **Find preview APIs**: search for `allocateUtf8String`, `allocateArray`, `getUtf8String`, `setUtf8String`, and the `allocate(layout, value)` overload.
3. **Update by semantics**: data-initializing allocation → `allocateFrom`; reading/writing C strings → `getString`/`setString`. Do not mistakenly replace `allocate(byteSize)` or `allocate(layout)`.
4. **Check charsets**: C strings are bytes with a terminator, not Java UTF-16 Strings; pass an explicit `Charset` if the C API does not accept UTF-8.
5. **Check the C ABI**: `FunctionDescriptor`, return type, parameters, pointers/structs, alignment, `size_t`, signedness, and architecture.
6. **Fix compile/run flags**: remove `--enable-preview` **if only final FFM is needed**; use `javac --release 22` with the 22 compiler.
7. **Keep native access in the right places**: restricted calls still need appropriate grants, especially `libraryLookup`, linking, and certain unsafe operations.
8. **Check the native library**: build for the right OS, bitness, and exported symbols; do not assume the library is loaded via `System.loadLibrary` if the code uses `SymbolLookup.libraryLookup`.
9. **Check resource lifecycle**: Arena closing, segment lifetime, callbacks, threading, native library unloading, and native memory allocated by C itself.
10. **Run actual tests on JDK 22**: test the happy path, abnormal inputs, null pointers, boundaries, encoding, errors, callbacks, and concurrent access; do not rely solely on `javac` succeeding.
11. **Plan binary compatibility**: JDK 21 preview class files are not artifacts to run arbitrarily on JDK 22. Recompile and test on the target runtime; a module that must support both 21 and 22 may need separate source sets/toolchains.
12. **Document the minimum supported Java version** in documentation, build system, and artifact metadata. Final `java.lang.foreign` code requires JDK 22 or later and cannot be deployed directly onto Java 17 just because the package is named `java.lang`.

A project that only reads/writes simple native segments may only change a few lines. However, a project using specific ABIs, complex structs, C++ interop, or callbacks must be tested more thoroughly. **Finalized means API stability**, not a guarantee that every native library's behavior is portable.

## 12. Common errors, causes, and fixes

| Error or misconception | Cause | How to fix |
|---|---|---|
| Using `jdk.incubator.foreign` on JDK 21 | Reading an outdated JDK 17/18 tutorial | Use `java.lang.foreign` and 21 docs |
| `javac` reports FFM is preview | Forgot `--enable-preview` with JDK 21 | Enable preview in the compile command |
| Runtime rejects preview class | Forgot runtime flag or using wrong JVM version | Run with JDK 21 and `--enable-preview` |
| `allocateUtf8String` not found in JDK 22 | API was renamed | `arena.allocateFrom(String)` |
| `allocateArray` not found in JDK 22 | Element-allocation API changed | `arena.allocateFrom(layout, values...)` |
| `getUtf8String` not found in JDK 22 | String-reading method changed | `segment.getString(offset)` |
| `allocateFrom` missing in JDK 21 | Copied JDK 22 code back to 21 | Use the equivalent JDK 21 preview API |
| Preview error when `--release 21` with compiler 22 | Compiler does not compile an older version's preview that way | Use JDK 21's `javac` |
| Restricted native method warning | `--enable-preview` does not grant native access | Pass `--enable-native-access=...` |
| `IllegalCallerException` | Caller module has not been granted native access | Specify the right module or `ALL-UNNAMED` |
| Native library not found | DLL/.so/.dylib wrong path/OS/bitness | Build the right library, run in the right directory |
| `NoSuchElementException` from `find(...).orElseThrow()` | Symbol name not exported properly | Check `ffm_add` in the export table |
| `WrongMethodTypeException` | `invokeExact` does not match Java carriers | Compare `FunctionDescriptor`/argument types |
| JVM crash after downcall | Wrong C ABI signature or expired pointer | Check the real C header, verify lifetime and architecture |
| `WrongThreadException` | Confined segment accessed from another thread | Use the owner thread or design a shared arena |
| `IllegalStateException` when accessing segment | Arena has already been closed | Do not use segment after close |
| `size_t`/`long` wrong on Windows | Assumed C types have the same width as on Linux | Use the actual ABI, check `canonicalLayouts()` in 22 |

### 12.1. Inspection tools

~~~bash
java -version
javac -version
~~~

This step verifies the actual compiler/runtime, especially when multiple JDKs are installed on the machine. On Linux/macOS/Windows, checking exported native symbols can use:

~~~text
Linux:   nm -D libffm_math.so
macOS:   nm -g libffm_math.dylib
Windows: dumpbin /EXPORTS ffm_math.dll
~~~

These are **OS-specific suggested commands**, not a shared script. The `nm` tool on macOS may show a leading underscore on Mach-O symbol names; `SymbolLookup` handles names according to the OS and loader rules.

## 13. Which version to choose in a real project?

If you must support **JDK 21 LTS**, note that FFM on it **is still preview**, so you must accept preview flags, lock the version/toolchain, and test compiler/runtime updates as well.

If the project can require **JDK 22+**, prefer writing new code against **FFM final (JEP 454)**: official `allocateFrom`/`getString` APIs, no preview needed for FFM itself, and suitable as a clear baseline. However, this **does not remove the responsibility** of granting native access, designing the ABI, closing Arenas, and securing native libraries.

If the application must run across multiple major JDKs, do not just copy a `.class` file compiled with JDK 21 preview and treat it as a portable binary for JDK 22. Separate builds/tests for each release, or consider JNI for older runtimes if product requirements mean final FFM is not yet available.

FFM is a powerful tool for binding to a C ABI without writing JNI glue for every function, but **it is not a complete replacement for JNI**. JNI remains important when C/C++ code needs to manipulate Java objects directly, handle JNI-level callbacks, or in systems with long-established native bindings.

## 14. Review questions

1. Which JEP does JDK 21 belong to and which preview is it? Which JEP does JDK 22 belong to?
2. Is JDK 21 FFM in `jdk.incubator.foreign` or `java.lang.foreign`? Why does confusing this often cause import errors?
3. Why does JDK 22 not require `--enable-preview` for FFM itself, yet may still require `--enable-native-access`?
4. Convert the three calls `allocateUtf8String`, `allocateArray`, and `getUtf8String` to JDK 22.
5. When should you keep `arena.allocate(layout)` instead of changing it to `allocateFrom`?
6. Why do the two memory examples using JDK 21 and 22 produce the same stdout `sum = 12` and `text = FFM`?
7. Write the correct `javac` and `java` commands for `Ffm21Call.java` and `Ffm22Call.java`.
8. Which code does the `ALL-UNNAMED` flag apply to? What must be done if using a named module?
9. What does `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` describe? Is it equivalent to passing the JNI string `(II)I` to the API?
10. Why is declaring `size_t` with `JAVA_LONG` for all OSes unsafe?
11. Which JDK introduced `Linker.canonicalLayouts()`, and what kind of problem does it solve?
12. What happens when code attempts to access a `MemorySegment` from a closed confined Arena?
13. Why should you not keep a native function pointer or method handle longer than the time the library is loaded?
14. If all FFM 21 code builds successfully but fails when running on JDK 22, in what order would you check **renamed APIs, preview class files, toolchain, native access, and ABI**?

**Conclusion:** **JDK 21 = FFM third preview (JEP 442)**, requiring preview flags; **JDK 22 = FFM final (JEP 454)**, requiring no preview for FFM. Upgrading is not just dropping flags: you must migrate native data creation APIs from `allocateUtf8String`/`allocateArray`/`allocate(layout,value)` to `allocateFrom` and from `getUtf8String`/`setUtf8String` to `getString`/`setString`. On the other hand, `Arena`, `Linker`, `SymbolLookup`, and `FunctionDescriptor` retain the core model; **native access, C ABI, memory lifetime, and thread safety** still must be managed explicitly.

### Official documentation by version

- [JEP 442 — Foreign Function & Memory API (Third Preview), JDK 21](https://openjdk.org/jeps/442)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [Java 21 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 21 — SegmentAllocator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) and [MemorySegment](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/MemorySegment.html): `allocateUtf8String`, `allocateArray`, `getUtf8String`.
- [Java 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) and [MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `allocateFrom`, `getString`/`setString`.
- [Java 22 — Linker API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): canonical C layouts, downcalls, and restricted methods.
- [Oracle JDK 21 — FFM overview](https://docs.oracle.com/en/java/javase/21/core/foreign-function-and-memory-api.html) and [Oracle Java 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html).
