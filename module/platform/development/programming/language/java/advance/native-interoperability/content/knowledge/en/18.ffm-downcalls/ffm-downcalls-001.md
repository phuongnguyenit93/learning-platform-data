# Finding Symbols with defaultLookup, loaderLookup, or libraryLookup in Java FFM

## 1. The Problem: To Call a C Function from Java, You Must Find the Exact Function Address First

Suppose a C library exports the function:

```c
int ffm_demo_answer_2026(int x);
```

To call that function from Java using the **Foreign Function & Memory API (FFM)**, three distinct steps are required:

1. **Symbol lookup**: determine the native address of the name `ffm_demo_answer_2026`.
2. **Describe ABI/signature**: the function takes one C `int` and returns one C `int`, corresponding to `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` on the ABIs supported in the example.
3. **Create and invoke the downcall**: use `Linker.downcallHandle(...)` to create a `MethodHandle`, then call it using `invokeExact(...)`.

In the first step, there are three common lookup sources:

- **`Linker.nativeLinker().defaultLookup()`**: searches in common system libraries provided by default by the JVM's linker.
- **`SymbolLookup.loaderLookup()`**: searches in native libraries loaded via **`System.load`/`System.loadLibrary`** and **associated with the class loader of the code calling `loaderLookup()`**.
- **`SymbolLookup.libraryLookup(...)`**: opens/searches in **a specific library** by name or `Path`, with a lifetime bound to an `Arena` you specify.

Choosing the right lookup is just as important as the symbol name. A function existing in a `.so`/`.dylib`/`.dll` file **does not guarantee all three lookups will see it**. Furthermore, finding the address **does not verify** whether the C signature is compatible with the `FunctionDescriptor` you declare.

### 1.1. Java Version

This article uses the stable API from **JDK 22** (`java.lang.foreign`, JEP 454). Java 17 does not yet have this stable FFM API; some JDK 19–21 releases had preview APIs with different syntax/policies. Do not copy JDK 22 examples verbatim into a JDK 17 project and expect it to compile.

Native call examples require permission to access native code, so use:

```bash
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
```

`ALL-UNNAMED` grants permission to classpath code (the unnamed module). For named modules, replace it with the appropriate module name in the deployment configuration. Depending on the JDK, lacking native access may cause restricted calls to fail or emit a warning; **do not treat this flag as a library name or a symbol lookup option**.

## 2. What is `SymbolLookup`?

In JDK 22, `java.lang.foreign.SymbolLookup` is an interface with the core method:

```java
Optional<MemorySegment> find(String symbolName);
```

It looks up a **symbol name** and returns:

- `Optional.of(MemorySegment)` if found. The segment represents **the address of the symbol**, having `byteSize() == 0` by specification; it is **not** a copy of the entire machine code of the function or a Java object containing data.
- `Optional.empty()` if not found. Do not call `get()` when empty or "guess" a native address as a replacement.

Snippet example (not a standalone program):

```java
SymbolLookup lookup = Linker.nativeLinker().defaultLookup();

Optional<MemorySegment> result = lookup.find("strlen");
if (result.isPresent()) {
    MemorySegment functionAddress = result.get();
    // Pass functionAddress together with an appropriate FunctionDescriptor
    // to Linker.downcallHandle(...) if you actually need to call it.
}
```

`Optional` forces the user to decide the path when a symbol is absent:

- **Required**: `lookup.find(name).orElseThrow(...)`, then report a clear initialization error.
- **Optional feature**: `find(name).ifPresent(...)` or check `isPresent()` to use a fallback.
- **Multiple lookup sources**: use `lookupA.or(lookupB)` (Section 8), controlling the priority order.

### 2.1. Symbol Names Are Not Java Class Names

In native code:

```c
// C symbol (function) exported to the shared library:
int ffm_demo_answer_2026(int x);
```

Java looks up the exact string `"ffm_demo_answer_2026"`. There is no mechanism that turns `"CFunction.add"` into a C symbol, no automatic `Java_` prefixing like when resolving some JNI native methods, and no automatic searching in the classpath.

The actual name depends on the ABI and how the compiler/linker **exports** the symbol:

- C typically exports the C name as declared, if the compiler/linker makes the symbol visible.
- C++ has **name mangling**; when you want a stable C symbol for FFM, use `extern "C"`.
- Some platforms require export/visibility directives; Windows DLLs require attention to `__declspec(dllexport)` or an export definition file.
- Linux/macOS can use visibility to hide non-public symbols.
- Not every symbol in a header is exported in the built shared library.

**C++ example** (not a standalone runnable file):

```cpp
extern "C" int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

If `extern "C"` is missing, the native symbol may have a compiler-mangled name; `find("ffm_demo_answer_2026")` cannot find it even though the C++ code exists.

## 3. Quick Comparison of the Three Lookup Sources

| Criterion | `defaultLookup()` | `loaderLookup()` | `libraryLookup(...)` |
| --- | --- | --- | --- |
| Obtained from? | `Linker.nativeLinker()` | `SymbolLookup` static factory | `SymbolLookup` static factory |
| Scope | **Common libraries chosen by the linker** | Libraries loaded via JNI and associated with the **caller's class loader** | **Specific library** identified by name/path |
| Does it load a new library? | Not the purpose of this API | **No**; searches in the set already loaded via `System.load*` | **Possibly**; if not yet loaded, it will load the library |
| Requires an `Arena` at creation? | No | No | **Yes** |
| Lifetime management | Follows linker/runtime | Tied to class loader lifecycle, automatically keeps the loader reachable while the lookup/symbols remain reachable | **Follows Arena**; must be kept alive until finished using |
| Reasonable use case | `strlen`, `malloc`, common OS/C library functions **if exposed by the linker** | Already have a plugin/JNI library loaded via `System.load` | Want to use functions in an arbitrary `.so`/`.dll` by path |
| Common misconception | Does not look up **every** symbol in the process | Does not see libraries opened only via `libraryLookup` | Does not automatically turn the library into a JNI class-loader library |

**You cannot rely on `defaultLookup` as a global table listing every library in the process.** The set of libraries it exposes is decided by the **OS, architecture, and linker implementation**, not a uniform list across Windows/Linux/macOS.

## 4. `Linker.nativeLinker().defaultLookup()`

### 4.1. How to Obtain and Look Up

```java
Linker linker = Linker.nativeLinker();
SymbolLookup systemSymbols = linker.defaultLookup();

Optional<MemorySegment> strlenAddress = systemSymbols.find("strlen");
```

`defaultLookup()` is an **instance method** of `Linker`. It is not `SymbolLookup.defaultLookup()` and not a static `Linker.defaultLookup()`. First select the linker for the **native ABI of the running platform**.

A linker may expose the standard C library or math library; for example on **Linux/x64**, the `strlen` symbol is typically looked up via default lookup. However, the specification does not mandate that every platform must expose the same symbols or the same ABI.

### 4.2. Linux/x64 Example: Finding and Calling `strlen`

C declaration:

```c
#include <string.h>
size_t strlen(const char* text);
```

On **typical Linux/x64**, `size_t` is 64-bit, so the descriptor is typically:

```java
FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)
```

This approach is **not universal** for 32-bit systems: `size_t` may have the `int` carrier. If cross-platform code is needed, you should look up the canonical layout for `"size_t"` via `linker.canonicalLayouts()` and handle the corresponding Java type.

File **`LinuxStrlenDemo.java`** — standalone program, specifically targeting Linux/x64 with JVM/JDK 22+:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.util.Optional;

public final class LinuxStrlenDemo {
    private LinuxStrlenDemo() {}

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = linker.defaultLookup();

        Optional<MemorySegment> address = symbols.find("strlen");

        if (address.isEmpty()) {
            System.out.println("strlen unavailable in default lookup");
            return;
        }

        MethodHandle strlen = linker.downcallHandle(
                address.orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)
        );

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cString = arena.allocateFrom("Hello FFM");
            long size = (long) strlen.invokeExact(cString);
            System.out.println("strlen=" + size);
        }
    }
}
```

Run commands (Linux/x64, JDK 22+):

```bash
javac LinuxStrlenDemo.java
java --enable-native-access=ALL-UNNAMED LinuxStrlenDemo
```

**Stdout when `strlen` is exposed by default lookup:**

```text
strlen=9
```

If the linker does not expose this symbol, the program **does not crash due to `Optional.get()`**, and instead prints:

```text
strlen unavailable in default lookup
```

`"Hello FFM"` contains 9 ASCII characters; `Arena.allocateFrom(String)` creates a null-terminated UTF-8 C string, while `strlen` counts the number of bytes before the terminating byte. For multi-byte Unicode strings, the byte count and Java `char` count may differ.

**Do not mechanically apply the `JAVA_LONG` descriptor for `size_t` on Windows/other CPUs.** You must choose the right ABI, and can check `linker.canonicalLayouts().get("size_t")` according to the platform documentation.

## 5. `SymbolLookup.loaderLookup()`: Load via JNI, Then Look Up by Class Loader

### 5.1. Important Contract

`SymbolLookup.loaderLookup()` looks up native libraries loaded with:

- `System.load("/absolute/path/to/libdemo.so")`; or
- `System.loadLibrary("demo")`.

The decisive point: the library is **associated with the class loader of the class calling `System.load*`**. `loaderLookup()` then looks up libraries associated with the **class loader of the class calling `loaderLookup()` itself**. Both sides need the same appropriate class loader; if plugin A and plugin B have different class loaders, `loaderLookup` in B is **not** "the catalog of A's native libraries".

### 5.2. Dynamic Lookup Across the Loading Process

A great feature of `loaderLookup` is that it is **dynamic**: hold a lookup beforehand, then load an additional JNI library in the same loader, and use **the exact lookup already created** to see the new symbol.

```java
SymbolLookup lookup = SymbolLookup.loaderLookup();

boolean before = lookup.find("ffm_demo_answer_2026").isPresent();

System.load(absoluteLibraryPath.toString());

boolean after = lookup.find("ffm_demo_answer_2026").isPresent();
```

This snippet is **illustrative**, assuming `absoluteLibraryPath` already points to the right library containing the exported symbol. In the clean test process in Section 10, `before=false`, `after=true`. If the library was already loaded by another `System.load*` call earlier in the same loader, you should not assume `before` is always false.

**Important:** `loaderLookup` is **not** a library-loading function. If you only call `loaderLookup().find("...")` without having called `System.load*` on the corresponding library, the lookup is not required to search for files on disk on its own.

### 5.3. Class Loader Lifetime

The Javadoc states that a loader lookup has an automatic scope that **keeps the caller's class loader reachable** while the lookup or symbol segments returned by it remain reachable. That also keeps the JNI libraries associated with the class loader loaded during that time.

Therefore:

- Do not treat a reference to a lookup/symbol as if it has no effect on class unloading.
- In plugin/reloadable class loader systems, avoid caching lookups/symbols process-wide if you want to unload plugins.
- Do not manually call `Arena.close` for `loaderLookup`: the API does not accept an Arena from the caller, unlike `libraryLookup`.

### 5.4. `System.loadLibrary` vs. `System.load`

`System.loadLibrary("ffmlookupdemo")` takes a **logical name** for the JVM to search its native library path. `System.load(absolutePath)` takes an **absolute path** to the exact file. When writing cross-OS practical examples with the file placed in the current directory, a reliable way is:

```java
String fileName = System.mapLibraryName("ffmlookupdemo");
Path absolutePath = Path.of(fileName).toAbsolutePath().normalize();
System.load(absolutePath.toString());
```

This is a **snippet**, requiring `import java.nio.file.Path` and the file already built in the working directory. `System.mapLibraryName` typically maps:

- Linux: `libffmlookupdemo.so`.
- macOS: `libffmlookupdemo.dylib`.
- Windows: `ffmlookupdemo.dll`.

If building with a specialized toolchain or targeting a different loader, you may need to customize the path. Do not hard-code `.dll` on Linux.

## 6. `SymbolLookup.libraryLookup(String, Arena)`: Library by Name

### 6.1. Using a Name Understood by the Native OS Loader

Linux example:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup libc =
            SymbolLookup.libraryLookup("libc.so.6", arena);

    Optional<MemorySegment> strlen = libc.find("strlen");
    System.out.println(strlen.isPresent());
}
```

This is a **snippet for common Linux/glibc systems**, not a choice guaranteed to run on every Linux distribution (for example, musl systems have different library names). `libc.so.6` is a name handled by the **native dynamic loader**, not the Java classpath or a Maven artifact.

Some commonly seen names that are **not guaranteed to be available on every machine**:

| System | Native library name you may encounter | Notes |
| --- | --- | --- |
| Linux glibc | `libc.so.6`, `libm.so.6` | Distro, linker search path, and ABI |
| macOS | `/usr/lib/libSystem.B.dylib` | System libraries, frameworks, and SIP policy |
| Windows | `ucrtbase.dll`, `kernel32.dll` | Windows DLL search semantics, architecture |

If targeting a specific library in an application, prefer a `Path` to the packaged file rather than relying solely on fixed OS names.

### 6.2. Arena Controls the Lookup's Lifetime

`libraryLookup` requires a mandatory `Arena`:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lib = SymbolLookup.libraryLookup(
            "libc.so.6", arena
    );

    MemorySegment function = lib.find("strlen").orElseThrow();

    // Create downcall/call function while arena is still alive.
}
// After close, do not use the function address/handle from the lookup
// as if the library were still guaranteed to be loaded.
```

The syntax above is a **snippet**, not a standalone Java program. The library is opened if not yet loaded; the lookup's scope is tied to the arena. When a confined arena closes, the native library owned by that arena may be unloaded per contract (unless kept loaded independently through another mechanism).

**Closing the arena does not necessarily make every copy of the same library disappear from the process immediately.** The OS/JVM may still hold other references (for example, if the library was previously loaded with `System.load`). However, your code must still obey the lifetime of the lookup and the addresses obtained from it, and not use native functions after the scope is closed.

### 6.3. Keep the Arena Alive Long Enough

Anti-pattern:

```java
// WRONG: returning a symbol from an arena that will close immediately.
static MemorySegment getSymbol() {
    try (Arena arena = Arena.ofConfined()) {
        return SymbolLookup.libraryLookup(
                "libc.so.6", arena
        ).find("strlen").orElseThrow();
    }
}
```

This function is just an error illustration; the returned address must not be used after the arena closes.

The right approach is to **jointly own the arena, lookup, and downcalls inside a service object**, with a `close` method called after all callers have finished. If calls from multiple Java threads are needed, consider `Arena.ofShared()`, while still synchronizing closing and preventing in-flight calls from using the library after close.

## 7. `SymbolLookup.libraryLookup(Path, Arena)`: Library by Path

The API also has the overload:

```java
SymbolLookup.libraryLookup(path, arena)
```

Where `path` is a `java.nio.file.Path` on the **default file system**, commonly used when the application builds/bundles its own native library alongside the executable. It helps reduce dependence on the OS search path:

```java
Path path = Path.of(
        System.mapLibraryName("ffmlookupdemo")
).toAbsolutePath();

try (Arena arena = Arena.ofConfined()) {
    SymbolLookup library = SymbolLookup.libraryLookup(path, arena);
    MemorySegment address = library
            .find("ffm_demo_answer_2026")
            .orElseThrow();
    // Create downcall and use before closing arena.
}
```

This snippet requires the native file to be properly built at `path`. `libraryLookup(Path, Arena)` does **not** automatically add a `lib` prefix, does **not** automatically extract from Maven/JAR, and does not search `.class` files. It works with an actual native library.

### 7.1. Why Might You Need to Use Name Instead of Path?

- For system libraries like `libc`, the name/soname is normally found by the OS dynamic loader according to standard configuration.
- In some Linux/macOS/Windows environments, hardcoded paths to system libraries are unstable across OS upgrades.
- For **application-managed** libraries, using an absolute path helps control the binary's version and architecture.
- You can combine a fallback: try the application library by Path; if unavailable, look up a system library by String, but there must be a compatible ABI contract—do not pick arbitrarily just because a symbol name matches.

### 7.2. Errors When `libraryLookup` Opens a Library

The JDK 22 Javadoc notes these key errors:

| Condition | Error/symptom |
| --- | --- |
| Name does not identify a valid native library | `IllegalArgumentException` |
| `Path` does not point to a valid library on the default filesystem | `IllegalArgumentException` |
| Arena is already closed | `IllegalStateException` |
| Calling thread is not the owner of a confined arena | `WrongThreadException` |
| Caller does not have native access | `IllegalCallerException` |
| Library does not contain the requested symbol | `find` returns `Optional.empty()` |
| Correct library but wrong CPU/ABI/dependency | Native loader fails, sometimes surfaced through a load-related exception |

**Note:** **library loading** errors and **symbol not found** errors are two separate stages. `libraryLookup` can load the library successfully while `find("wrong_name")` still returns empty.

## 8. `SymbolLookup.or` to Search Multiple Places in Order

FFM supports combining lookups with `or`:

```java
SymbolLookup combined = appLibrary
        .or(SymbolLookup.loaderLookup())
        .or(Linker.nativeLinker().defaultLookup());

Optional<MemorySegment> symbol = combined.find("some_function");
```

This is a **snippet**, assuming `appLibrary` is an already created lookup and its associated arena is still alive.

The `or` mechanism:

1. Searches in the **left-hand lookup** first.
2. If not found, falls back to the right-hand lookup.
3. If neither has it, returns `Optional.empty()`.

The order **is part of the application contract**. If multiple libraries export `init` or `version`, calling a function from the wrong ABI can cause a crash. Therefore, you should:

- Prioritize the lookup of the **explicitly identified library**.
- Only fall back when both implementations truly share the **same C ABI contract**, version, and ownership.
- Use namespaced/prefixed symbol names, avoiding overly generic names like `init`/`open`.
- Manage the arena of each `libraryLookup` in the chain; `or` does not make a lookup immortal after its arena closes.

### 8.1. Do Not Chain Lookups to Arbitrarily "Sweep Every Library"

Combining multiple sources is useful for plugin fallbacks, but does not replace checking **the library and ABI version**. An identical symbol name in two libraries does not prove they accept the same parameter types. You must know the exact `FunctionDescriptor` matching the **actually selected** symbol.

## 9. From Symbol to Callable Function: `Linker.downcallHandle`

`SymbolLookup.find` only retrieves the **address**. It does not automatically create a Java method, does not check the C signature, and does not know whether the library intends to return `int` or `double`.

Example from a C symbol:

```c
int ffm_demo_answer_2026(int x);
```

FFM:

```java
MemorySegment address = lookup.find(
        "ffm_demo_answer_2026"
).orElseThrow();

MethodHandle fn = Linker.nativeLinker().downcallHandle(
        address,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT
        )
);

int answer = (int) fn.invokeExact(21);
```

This is a **snippet** with a valid `lookup` and the enclosing method declaring `throws Throwable`. `FunctionDescriptor.of(returnLayout, parameterLayouts...)` here accurately describes C `int → int`. Note that the **first argument** of `of` is the **return value** layout. For native C `void`, use `FunctionDescriptor.ofVoid(...)`.

`invokeExact` checks Java types **strictly**; `(int)` is required for the return type, and the argument must be passed as a Java `int`. In this case:

```java
int value = (int) fn.invokeExact(21);
```

is correct. If you accidentally write:

```java
// Wrong data type if the MethodHandle expects (int)int.
long value = (long) fn.invokeExact(21L);
```

then the signature `long → long` does not match `int → int` and will throw `WrongMethodTypeException`; this is not a symbol lookup error.

### 9.1. FFM Does Not Verify C Signatures from the Binary

A native symbol address does not carry Java metadata describing the full ABI. A wrong `FunctionDescriptor` can cause **corruption, crashes**, or random results, even though `find` returns present and the Java compiler reports no errors. Always obtain the signature from the **C header of the exact library/version**, and verify the ABI for types like `long`/`size_t`/struct/varargs/pointer.

For example, `size_t` on Linux/x64 is typically 64-bit, whereas Windows x86 or 32-bit CPUs may differ. Do not pick `JAVA_LONG` out of habit without knowing the platform and mapping.

### 9.2. A Function Address Is Not Ordinary Data Memory

The `MemorySegment` returned from `find` has **zero length**. You should not call `symbol.get(JAVA_INT, 0)` to "read machine instructions" or treat it as a data buffer. For a **global variable symbol**, there are cases where `reinterpret` with an appropriate size is needed to access it, but that is a dangerous restricted API requiring an understanding of memory/address ownership; this article focuses on **function symbol lookup** and downcalls.

## 10. Full Hands-On Practice: C Library + Java, Comparing All Three Lookups

We create **our own** C shared library with a symbol name unlikely to collide with system libraries:

```c
int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

Then run Java in **three separate processes**:

- `library`: uses `libraryLookup(Path, Arena)` to open our library and proves `loaderLookup` does **not** automatically pick up a library opened only via library lookup.
- `loader`: creates `loaderLookup` first, then calls `System.load`, and uses the **old** lookup to find the newly loaded symbol.
- `default`: checks `strlen` in `defaultLookup`; the result **depends on the OS/linker**, without assuming it is always present.

**Why run in separate processes?** A native library already loaded in one process can alter the set of libraries associated with the class loader. To prove the difference between `libraryLookup` and `loaderLookup`, the two modes must be run in **two separate JVM launches**, avoiding mixing loaded state from the previous mode.

### 10.1. C File: `FfmLookupDemo.c`

```c
#if defined(_WIN32)
#  define EXPORT __declspec(dllexport)
#else
#  define EXPORT __attribute__((visibility("default")))
#endif

/* Stable C ABI, no JNI_OnLoad or native Java methods needed. */
EXPORT int ffm_demo_answer_2026(int x) {
    return x + 21;
}
```

This is a **standalone C file to compile into a shared library**. There is no need for `#include <jni.h>` or JNI headers because Java calls via **FFM downcall**, not Java `native` declarations.

On Windows, the guide uses **x64 MSVC**, in order to have a simple C symbol name without calling-convention decorations like some x86/32-bit targets. For C++, add `extern "C"` as shown in Section 2.

### 10.2. Java: `FfmSymbolLookupDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmSymbolLookupDemo {
    private static final String LIB = "ffmlookupdemo";
    private static final String SYMBOL = "ffm_demo_answer_2026";

    private FfmSymbolLookupDemo() {}

    private static MethodHandle bind(
            Linker linker, MemorySegment symbol) {

        // C: int ffm_demo_answer_2026(int)
        return linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)
        );
    }

    private static void libraryMode(
            Linker linker, Path path) throws Throwable {

        // Lookup created before libraryLookup loads the library.
        SymbolLookup callerLibraries = SymbolLookup.loaderLookup();
        System.out.println("loader before="
                + callerLibraries.find(SYMBOL).isPresent());

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup direct =
                    SymbolLookup.libraryLookup(path, arena);

            MemorySegment symbol =
                    direct.find(SYMBOL).orElseThrow();

            MethodHandle function = bind(linker, symbol);
            int result = (int) function.invokeExact(21);

            System.out.println("library=" + result);
            System.out.println("loader after libraryLookup="
                    + callerLibraries.find(SYMBOL).isPresent());
        }
    }

    private static void loaderMode(
            Linker linker, Path path) throws Throwable {

        // Loader lookup is dynamic: the same lookup object still
        // sees a JNI library newly loaded by this class loader.
        SymbolLookup callerLibraries = SymbolLookup.loaderLookup();
        System.out.println("loader before="
                + callerLibraries.find(SYMBOL).isPresent());

        System.load(path.toString());

        MemorySegment symbol =
                callerLibraries.find(SYMBOL).orElseThrow();
        int result = (int) bind(linker, symbol).invokeExact(21);

        System.out.println("loader after System.load="
                + callerLibraries.find(SYMBOL).isPresent());
        System.out.println("loader=" + result);

        // libraryLookup can still look up a library already loaded by System.load.
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup direct =
                    SymbolLookup.libraryLookup(path, arena);

            int viaLibrary = (int) bind(
                    linker,
                    direct.find(SYMBOL).orElseThrow()
            ).invokeExact(21);

            System.out.println("library after System.load="
                    + viaLibrary);
        }
    }

    private static void defaultMode(Linker linker) {
        SymbolLookup standard = linker.defaultLookup();

        // Do not assume a custom library is in default lookup.
        // The symbol set is determined by the linker/OS.
        System.out.println("default strlen present="
                + standard.find("strlen").isPresent());
    }

    public static void main(String[] args) throws Throwable {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use: library, loader, or default"
            );
        }

        Linker linker = Linker.nativeLinker();

        Path path = Path.of(
                System.mapLibraryName(LIB)
        ).toAbsolutePath().normalize();

        switch (args[0]) {
            case "library" -> libraryMode(linker, path);
            case "loader"  -> loaderMode(linker, path);
            case "default" -> defaultMode(linker);
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }
}
```

**Key takeaways from the code:**

1. `Linker.nativeLinker()` is the source for creating a linker for the native ABI; it does not automatically decide which custom library to search.
2. `System.mapLibraryName("ffmlookupdemo")` converts the logical name into the appropriate native filename for the OS.
3. `libraryMode` only calls `SymbolLookup.libraryLookup(path, arena)`, **not** `System.load`. The previously created `loaderLookup` continues not to see symbols from a library opened only via library lookup.
4. `loaderMode` calls `System.load` from the same class loader, so `callerLibraries` — even though created **before loading** — can look up the symbol after loading.
5. `libraryLookup` can still look up a library even if it was already loaded via `System.load`; the class loader association does not restrict looking up a specific library.
6. All `MethodHandle` invocations obtained from library lookup occur **inside the try-with-resources block**, while the arena is alive.
7. `defaultMode` checks a system symbol and does **not** hardcode its stdout, because the set of default symbols varies by platform.
8. `Optional.orElseThrow` is used for **required** symbols of the custom library; if not exported, the program fails clearly instead of calling an invalid address.
9. Passing `21` and having the C function add `21` yields `42`; this result is OS-independent as long as an ABI-compatible library is loaded successfully.

### 10.3. Linux — GCC/Clang

Use JDK **22+** and a C compiler matching the JVM architecture, from the directory containing both files. GCC example on Linux x64:

```bash
gcc -std=c11 -O2 -shared -fPIC \
    FfmLookupDemo.c -o libffmlookupdemo.so

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

If the OS cannot find a library dependency or the JNI loader applies restrictions, check the native loader message, full path, and `ldd`/`readelf`. Because the example uses an absolute `Path` pointing to the file in the current directory, you do not need to put the library directory on `java.library.path` to call `System.load(path)`.

### 10.4. macOS — Clang

On macOS with Command Line Tools and JDK 22+:

```bash
clang -std=c11 -O2 -dynamiclib \
    FfmLookupDemo.c -o libffmlookupdemo.dylib

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

For macOS Apple Silicon or Intel, you must use a JDK with the same architecture as the shared library. If the library is signed/has special policies, the native loader also has additional system rules; that is a **loading** issue, not a `find` difference.

### 10.5. Windows — MSVC x64

Open Visual Studio's **x64 Native Tools Command Prompt**, ensuring JDK 22+ x64 is in `PATH`:

```bat
cl /nologo /O2 /LD FfmLookupDemo.c /link /OUT:ffmlookupdemo.dll

javac FfmSymbolLookupDemo.java

java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo library
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo loader
java --enable-native-access=ALL-UNNAMED FfmSymbolLookupDemo default
```

The `ffmlookupdemo.dll` library resides in the current working directory; Java constructs an absolute `Path` to it. The Windows DLL loader must also be able to find any corresponding dependencies, if present.

### 10.6. Exact Stdout for `library`

In a **clean process**, with only the custom library in the current path and no previously loaded library exporting the same unique name:

```text
loader before=false
library=42
loader after libraryLookup=false
```

This proves: opening a library with `libraryLookup` **does not associate it with the caller's class loader like `System.load`**. The fact that a symbol exists in the process does not turn `loaderLookup` into a "process-wide" lookup.

### 10.7. Exact Stdout for `loader`

Run a **new Java process** (separate `java` command):

```text
loader before=false
loader after System.load=true
loader=42
library after System.load=42
```

This proves: a `loaderLookup` created beforehand still updates with new native libraries of the class loader. After `System.load`, both loader lookup and library lookup on that same library find the symbol. You must keep the library name and path accurate for the OS.

### 10.8. Stdout of `default` Depends on OS/Linker

For example, if `strlen` is in the set of system symbols exposed by the linker:

```text
default strlen present=true
```

If not exposed:

```text
default strlen present=false
```

**Both are valid outputs** for the `default` branch: this is a query `find("strlen").isPresent()`, not a hard assertion that the platform must export `strlen`. `defaultLookup` does not require the newly built custom C library to appear.

## 11. Subtle Details About Arena Lifetime

### 11.1. Confined and Shared Arena

`Arena.ofConfined()` fits a single thread creating the lookup and invoking symbols within that scope. Calling restricted `libraryLookup` from a thread other than the owner can encounter `WrongThreadException`. For a library used across multiple Java threads, you can consider:

```java
Arena arena = Arena.ofShared();
SymbolLookup lib = SymbolLookup.libraryLookup(path, arena);

// Workers can access those symbol segments
// under the shared scope, but must coordinate to stop activity
// before closing the arena.
```

This is an **illustrative pattern**, assuming `path` exists and the caller has native access. `Arena.ofShared()` does not make the native library itself thread-safe: a C function may use global state and be non-reentrant. The owner must manage **in-flight calls** and call `arena.close()` only after all calls have completed.

### 11.2. Do Not Cache a MethodHandle Longer Than Its Arena

`downcallHandle` can capture a symbol address from `libraryLookup`. If you cache the `MethodHandle` in a singleton and then close the arena, invoking the handle again violates the lifetime contract. Do not rely on `MethodHandle` to "keep the library file alive forever" once the arena is closed.

A sound service has the lifecycle:

```text
open()
  -> Arena.ofShared()/Arena.ofConfined()
  -> SymbolLookup.libraryLookup(...)
  -> find required symbols
  -> build MethodHandles
RUNNING
  -> invoke handles only while library scope alive
close()
  -> reject new calls
  -> wait for in-flight calls to complete
  -> close arena
CLOSED
  -> never invoke old handles/addresses
```

The `RUNNING/CLOSED` states are **application-designed**, not built-in FFM enums.

### 11.3. `loaderLookup` Can Extend Class Loader Lifetime

Unlike `libraryLookup`, loader lookup has no caller-created Arena. The lookup/symbol segments have an automatic scope tied to the class loader; caching a symbol globally outside a plugin can prevent the plugin from unloading. When designing hot-reloadable plugins, you must control Java references and the class-loader graph.

### 11.4. `defaultLookup` Is Also Not a Stable API Promise Across All Systems

A new JDK version or a different OS ABI may expose a different set of symbols. Use `defaultLookup` for system libraries that **are genuinely part of your platform contract**; for native plugins packaged by your product, `libraryLookup(Path, Arena)` is usually clearer.

## 12. What `find` Returns: Functions and Global Variables

`find` returns a **symbol address** without a step to automatically distinguish whether it is a function or a variable. If a C library exports:

```c
int global_counter = 100;
int ffm_demo_answer_2026(int x) { return x + 21; }
```

then `find("global_counter")` and `find("ffm_demo_answer_2026")` both return native addresses, but their usage is very different:

- **Functions**: use `Linker.downcallHandle` with the exact `FunctionDescriptor`.
- **Global variables**: you must know the layout/size, write state, and lifetime; the symbol segment from lookup has **zero length**. Calling `reinterpret` to read/write a variable is restricted and can be unsafe.

Never pass a variable's address to `downcallHandle` expecting the JVM to detect the mistake automatically. Likewise, do not read int data directly from a function address. This article intentionally demonstrates only **function symbols** to avoid ambiguity.

## 13. Which Name to Look Up on Which Operating System?

### 13.1. Linux

Use `nm -D` or `readelf -Ws` to inspect the dynamic symbol table:

```bash
nm -D libffmlookupdemo.so | grep ffm_demo_answer_2026
readelf -Ws libffmlookupdemo.so | grep ffm_demo_answer_2026
```

C code with `__attribute__((visibility("default")))` makes the symbol exported under normal GCC/Clang configurations. If the symbol is hidden by flags, `find` returns empty even though the function exists in object code.

### 13.2. macOS

Use `nm` (macOS may display a leading `_` prefix at the symbol table level), for example:

```bash
nm -gU libffmlookupdemo.dylib | grep ffm_demo_answer_2026
```

In FFM/JNI symbol resolution, the C name is looked up via the loader's appropriate API, typically using the C source name `ffm_demo_answer_2026`; do not arbitrarily prepend an underscore based solely on how `nm` displays it.

### 13.3. Windows

Use `dumpbin /EXPORTS`:

```bat
dumpbin /EXPORTS ffmlookupdemo.dll
```

Confirm the exact export name to look up. The example uses x64 so C function names are simpler than x86 decoration schemes. In C++, export with `extern "C"` and the appropriate ABI to avoid name mangling.

**Rule:** inspect the **actual binary**, not just the header containing the function. Do not guess by adding or removing characters from the symbol name, especially when libraries use versioned symbols or specialized compilers.

## 14. Common Errors and How to Handle Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `find("foo")` returns empty | Symbol not exported, wrong name, or right library but wrong version | Check `nm`/`dumpbin` and the matching header/library version |
| `loaderLookup` does not see a library opened by `libraryLookup` | Only `System.load*` loads and associates with the class loader | Use `libraryLookup`'s own lookup, or `System.load*` if appropriate |
| `loaderLookup` in plugin B does not see plugin A's JNI lib | Two different caller class loaders | Define clear plugin/loading boundaries |
| `loaderLookup` created before `System.load` and developer thinks it holds a snapshot | Loader lookup is **dynamic** | Reuse the lookup; it will see new libraries in the same loader |
| `defaultLookup` does not see a symbol in a custom file | Default libs set is chosen by the linker | Use `libraryLookup(Path, Arena)` or the right `loaderLookup` |
| `libraryLookup("my.so", arena)` fails to open on another OS | Name/soname/loader search path differs | Use a controlled `Path` and proper packaging |
| `System.loadLibrary("libdemo.so")` fails | Confusing logical name with filename | Use `"demo"` or `System.load(absolutePath)` |
| `libraryLookup` throws `IllegalCallerException` | Missing native access | Grant `--enable-native-access` to the calling module |
| Arena closed but old downcall handle is still invoked | Symbol lifetime is no longer valid | Do not use handles after close; owner manages in-flight calls |
| Symbol found but calling it crashes | Wrong `FunctionDescriptor`, wrong ABI/argument count | Cross-check C header, calling convention, `size_t`/long/struct |
| `WrongMethodTypeException` on `invokeExact` | Java carrier/type does not match handle | Pass `int`/`long` accurately and cast return type accurately |
| DLL/so fails to open despite file existing | Missing dependency, wrong arch/ABI, loader error | Check dependency chain and native loader diagnostics |
| C++ code exports mangled symbol | Missing `extern "C"` | Export a stable C name |
| Lookup in class loader stays alive forever | Caching loader lookup in a singleton outside the plugin | Manage references and plugin unload lifecycle |
| Symbol has same name as another OS function | Lookup chain prioritizes the wrong place | Use clear namespace prefixes or avoid unverified fallbacks |

### 14.1. Distinguishing the Three Error Layers

An FFM issue usually falls into one of three layers:

1. **Load** — unable to open a library with the right format/architecture/dependencies; `libraryLookup` or `System.load` fails.
2. **Lookup** — library opened, but `find` does not see the exported name.
3. **Link/invoke** — `find` succeeded, but `FunctionDescriptor`/carrier/lifetime/native code is wrong.

If you debug by changing `FunctionDescriptor` when the file actually failed to load, you will not solve the root cause. Log the exact library path, symbol name, native ABI, Arena state, and caller class.

## 15. Production Configuration and Security

### 15.1. Do Not Load Native Files from Arbitrary Input

`libraryLookup` can load native libraries into the JVM process. A native binary has full access to manipulate process memory; it is **not** constrained by Java type safety like normal bytecode. Do not build paths to `.dll`/`.so` directly from untrusted data (HTTP parameters, user-provided filenames). You should:

- Only allow signed libraries or libraries belonging to trusted packages with an allowlist.
- Verify canonical path, version, checksum/signature, and matching architecture.
- Avoid DLL/library search-path hijacking by trusting uncontrolled search path order.
- Cross-check the version/ABI contract with the symbol to be called.

### 15.2. Native Access Is a Permission Boundary, Not a Symbol Selection Mechanism

`--enable-native-access` grants permission for the caller module to use restricted FFM methods; it does **not** make `defaultLookup` contain more libraries, does **not** force `loaderLookup` to see files opened by `libraryLookup`, and does **not** fix ABI mismatches.

For classpath code, the example uses `ALL-UNNAMED`. For real modular applications, you can configure native access per module and review the target JDK's runtime rules.

### 15.3. Sharing Lookups Across Multiple Threads

A `SymbolLookup` can be accessed according to its lifetime contract, but a library managed by `Arena.ofConfined()` is bound by thread ownership. Do not cross thread boundaries arbitrarily. If shared native access is needed, use `Arena.ofShared()` with a close procedure that waits for completion, while also ensuring **the C function is thread-safe** if called concurrently.

### 15.4. Practical Test Matrix to Verify

| Test | What to Verify |
| --- | --- |
| Each OS/architecture | Binary format, filename, linker ABI |
| Symbol exists | `find` returns present, correct export |
| Symbol does not exist | Fallback or clear error, no crash |
| Different class loader | `loaderLookup` does not leak scope across plugins |
| `libraryLookup` with closed Arena | No use of symbol/handle after close |
| `libraryLookup` combined with `System.load` | Loader association rules and reference count |
| Correct `FunctionDescriptor` | Return/parameter types, ptr, struct, `size_t` |
| Missing native access | Clear permission error and proper runtime configuration |
| Load from untrusted path | Reject invalid sources |
| Multiple library versions | Avoid symbol name collisions with different ABIs |

## 16. Self-Check Q&A

**1. Does `defaultLookup` search all native libraries currently in the process?** No. It exposes **the set of libraries chosen by the linker** for the OS/processor. It does not replace library-specific lookups.

**2. Does `loaderLookup` call `dlopen` or `LoadLibrary` itself?** No. It looks up libraries already loaded via `System.load`/`System.loadLibrary` and associated with the caller's class loader.

**3. Does `libraryLookup(Path, Arena)` create a JNI association with the class loader?** No. A library opened only via library lookup does **not** thereby appear in the class loader's loader lookup.

**4. Will a `loaderLookup` created before `System.load` see a library loaded afterward?** Yes, it is dynamic with respect to the set of JNI libraries associated with the corresponding loader.

**5. Can `libraryLookup` look up a library previously loaded with `System.load`?** Yes, because library lookup targets the library itself, regardless of the class loader association of JNI loading.

**6. Why does `find` return a `MemorySegment` of length 0?** Because it represents **a symbol address**, not a byte region with an automatically known size. To call a function, pass that segment into `Linker.downcallHandle`.

**7. Two libraries both export `calculate`; which lookup is chosen in `a.or(b)`?** `a` has priority; only if `a.find` is empty is `b` queried. You must ensure the ABI of the selected implementation.

**8. Why is passing `ValueLayout.JAVA_LONG` for C `size_t` dangerous when porting?** Because C `size_t` is ABI-dependent; on 32-bit platforms it is typically 32 bits. Use the mapping from the linker and test on the target.

**9. After finishing with `libraryLookup`, can you close the Arena and still call a cached MethodHandle?** No. You must ensure the library and symbol remain alive throughout the call. Close the arena after all in-flight calls complete.

**10. If a `.dll` file has the C function but `find` is empty, what should be checked first?** Correct file/architecture, export table (e.g., `dumpbin /EXPORTS`), exact spelling/calling convention, and visibility.

**11. Do you need `System.loadLibrary` before `libraryLookup(path, arena)`?** No. `libraryLookup` is capable of **loading the library if not yet loaded**. Call both only if your application model genuinely requires it.

**12. If you only look up the `strlen` symbol, do you need a `FunctionDescriptor`?** For `find("strlen")`, **no**; if you want to **call** `strlen` via a downcall, then an ABI-accurate descriptor is required.

## 17. Application Checklist

1. Run JDK 22+ with the stable FFM API, granting native access to the appropriate module when using restricted calls.
2. Distinguish **symbol lookup** (`SymbolLookup.find`), **ABI description** (`FunctionDescriptor`), and **function invocation** (`Linker.downcallHandle`).
3. For common OS symbols: try `linker.defaultLookup()`, but always handle the case where it is absent.
4. For libraries already loaded via JNI from the same class loader: use `SymbolLookup.loaderLookup()`.
5. To target a specific native file: use `SymbolLookup.libraryLookup(Path, Arena)` or the name overload intentionally.
6. Do not assume `libraryLookup` makes a library appear in `loaderLookup`.
7. With loader lookup, understand the **caller class loader** scope and its **dynamic** behavior after `System.load*`.
8. With library lookup, keep the Arena open while using symbols/downcalls; close when no calls are in flight.
9. With `or` fallbacks, keep lookup order and the ABI contract explicit.
10. Before invoking, verify symbol export, native architecture, C carrier types, and the exact `FunctionDescriptor`.
11. On `Optional.empty()`, report a contextual error or choose a safe fallback; never call native code through a fabricated address.
12. In production, manage versions, dependencies, path allowlists, and plugin/class loader lifecycles.

## Official References

- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `find`, `or`, `loaderLookup`, `libraryLookup(String/Path, Arena)`, and class loader / Arena rules.
- [Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `defaultLookup`, `downcallHandle`, and canonical layouts.
- [Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): declaring native function signatures.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): lifetime, confinement, and shared arenas.
- [Java SE 22 — System.load](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#load(java.lang.String)): loading native libraries by absolute path.
- [Java SE 22 — System.loadLibrary](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): loading native libraries by logical name.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): rationale for the FFM API stabilizing in JDK 22, linker concepts, lookup, and native access permissions.
