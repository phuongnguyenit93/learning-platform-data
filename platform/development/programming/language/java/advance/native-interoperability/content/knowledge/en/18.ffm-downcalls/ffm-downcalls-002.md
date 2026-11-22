# Distinguishing Libraries Loaded via JNI from Libraries Managed by libraryLookup

## 1. Same native libraries, but not the same loading mechanism

A Java program can call C/C++ code in two familiar ways:

- **JNI (Java Native Interface):** declare `native` methods and load the library using `System.loadLibrary(...)` or `System.load(...)`. The JVM manages the relationship between **the library, the class loader, and JNI lifecycle hooks**, then links the Java native methods to C/C++ functions.
- **FFM (Foreign Function & Memory API):** describe the native function signature using `FunctionDescriptor`, obtain the symbol address using `SymbolLookup`, and then use `Linker.downcallHandle(...)`. Specifically, `SymbolLookup.libraryLookup(...)` loads or accesses a native library through the OS library mechanism and ties the **lookup/symbol lifetime** to an `Arena`.

Both approaches can run together in the same JVM and use the same `.so`, `.dylib`, or `.dll` file. However, **you must not treat a library loaded by `libraryLookup` as equivalent to the JVM having loaded and registered that library via JNI**.

An easy-to-remember example:

~~~java
// Mechanism 1: JVM loads a JNI library and associates it with a class loader.
System.loadLibrary("jniowner");

// Mechanism 2: FFM creates a library lookup, tying its lifetime to an Arena.
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup symbols = SymbolLookup.libraryLookup(
            Path.of("/absolute/path/to/library.so"), arena);
}
~~~

This is an **illustrative code snippet**, not compiled standalone. It requires `java.lang.foreign.Arena`, `SymbolLookup`, `java.nio.file.Path`, and an OS-appropriate library path.

**Most important difference:**

> `System.loadLibrary` makes the library a **JNI library associated with a class loader**, which can invoke `JNI_OnLoad`. `SymbolLookup.libraryLookup` manages an **Arena-scoped OS library lookup** and **does not automatically perform the JNI library registration process**.

This lesson uses the standardized API of **JDK 22+** (JEP 454). In JDK 17, FFM was still a different incubator API; the `java.lang.foreign` imports and signatures here are **incompatible**.

### What will you be able to do?

1. Distinguish between a **native library managed by the JVM via JNI** and a **library lookup managed by FFM/Arena**.
2. Understand `JNI_OnLoad`, `JNI_OnUnload`, and the significance of the class loader.
3. Use `SymbolLookup.loaderLookup()` to find symbols in libraries loaded via JNI.
4. Use `SymbolLookup.libraryLookup(String, Arena)` and `libraryLookup(Path, Arena)` with the proper lifetime.
5. Use `Linker.nativeLinker()`, `FunctionDescriptor`, and `MethodHandle.invokeExact` to call C functions.
6. Run an example with **two C libraries + two Java classes** whose stdout distinguishes the two loading paths.
7. Avoid errors such as using symbols after `Arena.close()`, confusing library search paths, and mistakenly assuming `libraryLookup` automatically runs JNI hooks.

## 2. Quick Comparison Table

| Perspective | `System.loadLibrary` / `System.load` (JNI) | `SymbolLookup.libraryLookup` (FFM) |
| --- | --- | --- |
| Primary intent | Load a library for JNI native methods and JNI lifecycle | Load/find **exported native symbols** for use via FFM |
| Calling API | `System.loadLibrary("name")` or `System.load(absolutePath)` | `SymbolLookup.libraryLookup("native-name", arena)` or `libraryLookup(Path, arena)` |
| Who manages loading? | **JVM JNI native-library registry** with class loader | **FFM library lookup** backed by the OS dynamic loader |
| Relationship with class loader | JNI library is associated with the loader of the class calling load | Lookup does not have the same JNI class-loader ownership registration |
| Relationship with Arena | Not managed by an Arena passed by the caller | Library lookup and symbol addresses are tied to the scope of an **Arena** |
| `JNI_OnLoad` | JVM calls it when loading the JNI library if the hook is exported | **Not automatically called** just because `libraryLookup` is created |
| `JNI_OnUnload` | May be called when the class loader owning the JNI library is GC'd | Not automatically called as a JNI lifecycle hook when closing the Arena |
| Finding symbols from a JNI-loaded library | `SymbolLookup.loaderLookup()` from an appropriate class loader | Can create a `libraryLookup` for that library, but it is a separate lookup |
| Finding symbols from an FFM-loaded library | `loaderLookup()` does **not** automatically see them | `libraryLookup(...).find(name)` sees exported symbols |
| End of lifetime | Tied to the class loader and JVM; no corresponding public `unloadLibrary()` | Use `Arena.close()` with confined/shared to end the scope and release lookup ownership |
| Native access | JNI invocation according to the corresponding JNI/JDK rules | JDK 22: `libraryLookup` and creating downcalls are **restricted methods** |
| Common errors | `UnsatisfiedLinkError`, JNI method/linkage/ABI error | `IllegalArgumentException`, `IllegalCallerException`, missing symbol, scope/ABI error |

**Note:** `libraryLookup` can access a library that was already loaded previously; the OS may reuse the handle or maintain a reference count. Closing an Arena **does not guarantee the OS immediately unmaps a file** if other owners or references remain. The differences in the table are **ownership mechanisms and access rights**, not necessarily two different machine copies of the native code.

## 3. JNI load: JVM registers the library with a class loader

Java example:

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    public static native int addOne(int number);
}
~~~

In the `NativeBridge` class, `System.loadLibrary("nativebridge")` asks the JVM to find the OS-appropriate library name: on Linux usually `libnativebridge.so`, on macOS `libnativebridge.dylib`, on Windows `nativebridge.dll`.

When the JNI mechanism loads successfully, the JVM can:

1. Ask the OS loader to load the shared library and its dependencies.
2. Associate the loaded library with the **class loader of the class calling `System.loadLibrary`**.
3. Find and run `JNI_OnLoad(JavaVM*, void*)` if the library exports that symbol.
4. Check the **JNI version** returned by the hook; the hook can perform setup such as `RegisterNatives`.
5. When Java actually calls `native addOne`, the JVM links the method to the C function by traditional JNI naming or registration.

**A library file can export many ordinary C functions**, but the fact that the JVM knows the library via JNI **does not automatically turn every exported C function into Java native methods**. For `native addOne`, the JVM still needs a valid JNI name or `RegisterNatives`.

### 3.1. `JNI_OnLoad` and its return value

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

This is a **complete C JNI hook in terms of signature**, though it has no business-logic methods yet.

- `JNI_OnLoad` is **called by the JVM when the library is loaded via JNI**, not a Java native method that must be called manually.
- The success return value of **`JNI_OnLoad` is a `JNI_VERSION_*` supported by the JVM**, for example `JNI_VERSION_1_6`. Do not confuse `JNI_OK` (the status code of `GetEnv` and many JNI APIs) with the JNI version.
- A library **without** `JNI_OnLoad` can still be a JNI library; according to the specification, the JVM assumes it requires JNI `JNI_VERSION_1_1`.
- If the hook returns an invalid JNI version, the JVM rejects the load as if the library were not loaded.
- The hook runs in the context of the class loader loading the library, so `FindClass` inside the hook has special class-loader rules that are useful when registering native methods.

A library loaded **only** through the OS mechanism of `libraryLookup` does not automatically undergo the JVM process of calling the `JNI_OnLoad` hook. Even if that file *exports* the `JNI_OnLoad` symbol, the existence of the symbol is not enough to create a JNI registration.

### 3.2. `JNI_OnUnload` and class loader lifetime

JNI has the hook:

~~~c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    /* Clean up resources owned by the JNI library. */
}
~~~

The JVM may call this hook when **the class loader containing the JNI library is GC'd**. Do not treat the hook as a guarantee that it "will definitely run when the Java process exits" or "will run every time the user closes a screen".

According to traditional JNI rules:

- A dynamic JNI library **cannot simultaneously be associated with two independent class loaders**. Reloading the same library from another loader may throw `UnsatisfiedLinkError`.
- JNI library lifetime is tied to the reachability of the class loader and other objects/references.
- There is no simple public Java API like `System.unloadLibrary("...")` to close the library on demand.
- Using `SymbolLookup.loaderLookup()` will **keep the associated class loader reachable** as long as the corresponding lookup/symbol segments remain reachable, which can therefore extend the JNI library's lifetime.

**Do not mechanically apply JNI's class loader rules** to `SymbolLookup.libraryLookup`. Although both call the OS loader at a low level, FFM has ownership through Arena and does not create an equivalent JNI class-loader registration.

## 4. FFM `libraryLookup`: libraries managed by Arena

Overloads in JDK 22:

~~~java
SymbolLookup byName =
        SymbolLookup.libraryLookup("some-platform-name", arena);

SymbolLookup byPath =
        SymbolLookup.libraryLookup(
                Path.of("/absolute/path/to/native/library.so"),
                arena);
~~~

These are snippets, with `arena` already created and still alive.

- `libraryLookup(String, Arena)` lets the OS resolver find the library by **native name**. Resolution depends on the OS: POSIX typically relies on `dlopen`; Windows relies on `LoadLibrary`.
- `libraryLookup(Path, Arena)` specifies the exact **path** to the library, which is usually easier to control in examples and when an application packages its own native files.
- `arena` determines the **lifetime** of the lookup and the address segments obtained via `find`.
- `lookup.find("function_name")` returns `Optional<MemorySegment>`: if the symbol exists, it returns an address view (a zero-length memory segment); if not, `Optional.empty()`.
- `Linker.downcallHandle(address, FunctionDescriptor...)` creates a `MethodHandle` to call a **native function** according to the OS/CPU ABI.

Full sequential illustration:

~~~java
try (Arena arena = Arena.ofConfined()) {
    Path library = Path.of(
            System.mapLibraryName("mathdemo")).toAbsolutePath();

    SymbolLookup lookup =
            SymbolLookup.libraryLookup(library, arena);

    MemorySegment address =
            lookup.find("native_square").orElseThrow();

    Linker linker = Linker.nativeLinker();

    MethodHandle square = linker.downcallHandle(
            address,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

    int result = (int) square.invokeExact(7);
    System.out.println(result);  // 49, if C exports native_square.
}
~~~

This snippet is **illustrative**; there is no `mathdemo` source here. Required imports: `Arena`, `SymbolLookup`, `MemorySegment`, `Linker`, `FunctionDescriptor`, `ValueLayout`, `MethodHandle`, `Path`. `main` or the method must handle/declare `Throwable` for `invokeExact`.

**Lifetime limit:** `arena.close()` invalidates the symbol address segments from that lookup. **Do not** retain a downcall handle pointing to a library of a closed Arena and call it again. If native code is still using the library, you must wait for all callers to finish before closing.

### 4.1. Why does `libraryLookup` need an Arena?

Loading a native library creates an **OS-level resource**: a handle to the library, dynamic dependencies, and symbol addresses. The programmer needs a way to explicitly state "until when it may be used". Arena solves this:

~~~text
Native file on disk
       |
       v
SymbolLookup.libraryLookup(path, arena)
       |
       +-- lookup.find("foo") -> symbol address A
       +-- lookup.find("bar") -> symbol address B
       |
       +-- Linker.downcallHandle(A, descriptorA)
       +-- Linker.downcallHandle(B, descriptorB)
       |
       v
Arena alive -> calls may be allowed when ABI/lifetime are valid
       |
       v
Arena.close() -> scope no longer alive, lookup/symbols invalidated
                 FFM releases ownership of the library
~~~

Note that FFM does not guarantee a library is **unloaded from physical memory immediately** if it is still loaded via JNI, referenced by another library, or the OS retains a handle. Closing the Arena **ends the usage contract through this lookup**, which does not mean all references outside the JVM have disappeared.

### 4.2. Types of Arena

| Arena | Access and close permissions | Suitable when |
| --- | --- | --- |
| `Arena.ofConfined()` | Single owner thread; deterministic `close()` | Single-threaded synchronous downcalls, short scope |
| `Arena.ofShared()` | Usable from multiple threads; deterministic `close()` but users must coordinate | Services sharing functions/library across threads |
| `Arena.ofAuto()` | No manual `close`; GC manages non-deterministic termination | Only when deterministic unload/cleanup deadline is not needed |
| `Arena.global()` | Does not support close; lifetime spans virtually the entire process/VM | Native library intentionally kept long-term |

Do not create an `ofConfined()` inside a helper and return a lookup or symbol for the caller to use **after the helper has closed the Arena**. Also do not use `global()` for every request just to avoid lifetime management if the system needs unloading or has native resource pressure.

## 5. `loaderLookup()` and `libraryLookup()` see different symbols

### 5.1. Loader lookup is not library lookup

~~~java
SymbolLookup loaderSymbols = SymbolLookup.loaderLookup();
~~~

`loaderLookup()` searches for symbols in native libraries that **the JVM has loaded via JNI** and **associated with the class loader of the class calling `loaderLookup()`**.

Example:

~~~java
System.loadLibrary("jniowner");

// In a class using the same class loader:
SymbolLookup loader = SymbolLookup.loaderLookup();
boolean found = loader.find("jniowner_hook_count").isPresent();
~~~

If the library exports `jniowner_hook_count` and loads successfully, `found` is `true`. However, `loaderLookup()` **does not open a new library file itself**, and it **does not** search all OS libraries in the process.

Characteristics:

- **Dynamic lookup:** If a new JNI library is later loaded with `System.loadLibrary` from the same loader, a previously created lookup can see the new library's symbols.
- **Caller-sensitive:** "Same class loader" matters. Plugin loader A and application loader B do not necessarily see the same set of JNI library symbols.
- **Lifetime:** Addresses from a loader lookup are associated with an automatic scope that keeps the caller class loader reachable. You **do not** close this lookup like a confined Arena.
- If the call is made in a context lacking a caller frame (for example, a native-attached thread calling directly), the specification states that the **system class loader** is used.

### 5.2. `libraryLookup` does not make `loaderLookup` see the library

If you **only** do:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup ffmSymbols =
            SymbolLookup.libraryLookup(
                    Path.of("/path/to/ffmside.so"), arena);

    boolean byFfm =
            ffmSymbols.find("ffmside_triple").isPresent();

    boolean byJniLoader =
            SymbolLookup.loaderLookup()
                    .find("ffmside_triple").isPresent();
}
~~~

In a demo environment where **ffmside is not JNI-loaded** and no other library in the same class loader exports the same symbol name: `byFfm` is `true`, `byJniLoader` is `false`.

**Do not try to turn `loaderLookup` into a place to find every shared library**. It only exposes symbols in libraries that the **JNI loader registry** associates with the caller class loader.

### 5.3. Can a library already loaded via JNI be looked up again with FFM `libraryLookup`?

**Yes.** `SymbolLookup.libraryLookup(...)` can create a lookup for a library L that already exists in the OS, **even if L was previously loaded via JNI**. That **does not transfer JNI's class loader ownership to the Arena**. OS dynamic-loader implementations may keep the same loaded image or increment the reference count when creating the lookup.

It helps to distinguish:

~~~text
JNI loader registry:         System.loadLibrary("L")
         |                                |
         v                                v
L associated with ClassLoader CL     JNI_OnLoad (if present)
         |
         +--> loaderLookup() finds symbols of L
         |
         +--> libraryLookup("L", arena) can also
              get symbols of L via an FFM handle
              BUT does not transfer L away from CL
~~~

Do not conclude that `arena.close()` will remove JNI's class-loader registration or call `JNI_OnUnload`. If you want separate management by Arena, use a library that is only FFM-loaded within a deterministic lifetime.

## 6. `Linker.defaultLookup()` is the third path

FFM also has:

~~~java
Linker linker = Linker.nativeLinker();
SymbolLookup defaults = linker.defaultLookup();
~~~

`defaultLookup()` provides symbols from common native libraries according to the **ABI/OS** supported by the linker, such as certain libc functions. It is not synonymous with:

- `loaderLookup()` — libraries associated with the caller class loader via JNI.
- `libraryLookup(...)` — the symbol set of a specific library requested by the caller.

Some symbols may happen to appear in multiple lookups due to OS/linker policies, but **you should not rely** on `defaultLookup` seeing every library you just loaded with `System.loadLibrary` or `libraryLookup`. To know clearly where a symbol belongs, choose the right lookup.

You can combine them with `SymbolLookup.or(...)` when you want a fallback:

~~~java
SymbolLookup preferred = SymbolLookup.libraryLookup(
        somePath, arena);
SymbolLookup combined = preferred.or(
        SymbolLookup.loaderLookup());
~~~

This is an **illustrative snippet**, with `somePath`/`arena` provided by the caller. `or` tries `preferred` first, and only checks `loaderLookup` when the symbol is not found. This is useful when there are multiple symbol sources, but you need to avoid **name collisions**: two different libraries with the same exported name will be resolved by lookup order, not by "which function is more appropriate".

## 7. Two lifecycle systems: JNI hooks differ from OS loader hooks

| Event | `System.loadLibrary("jniowner")` | `SymbolLookup.libraryLookup(ffmPath, arena)` |
| --- | --- | --- |
| OS performs dynamic loading if needed | Yes | Yes |
| OS constructors / dynamic-loader initialization may run | Yes | Yes |
| JVM registers JNI library with class loader | Yes | **Does not automatically do this** |
| JVM calls `JNI_OnLoad` exported from JNI library | Yes, upon proper JNI load | **Does not automatically call** |
| JVM may call `JNI_OnUnload` upon class-loader GC | Yes | Not upon Arena close |
| FFM `SymbolLookup.find` finds export | Via `loaderLookup` or a separate library lookup | Via the created library lookup itself |
| End of ownership in the API | Class loader reachability / VM lifecycle | `Arena.close()` for explicit arenas |

**`JNI_OnLoad` is different from a C/C++ library's static constructor.**

In C/C++, there may be static initialization, ELF constructors, Windows `DllMain`, or OS-level loader callbacks. Those parts may run simply because the OS loader opens the library, **even without JNI registration**. `JNI_OnLoad` is a **mechanism actively looked up and called by the JVM**, not a standard `dlopen`/`LoadLibrary` callback.

Therefore, saying "FFM `libraryLookup` does not call `JNI_OnLoad`" **does not mean** "FFM loads the library without executing any native code". Precisely because dynamic loading can run native constructors, `SymbolLookup.libraryLookup` is classified as a **restricted method**.

## 8. Complete example: two C libraries and two Java classes

The goal is to **prove via stdout**:

1. `System.loadLibrary("jniowner")` runs `JNI_OnLoad` of the JNI library; the native method works.
2. `SymbolLookup.loaderLookup()` from the same application class loader finds the exported function of the JNI library.
3. `SymbolLookup.libraryLookup(Path, arena)` opens the `ffmside` library.
4. A pure C function in `ffmside` is called via `Linker.downcallHandle`.
5. `ffmside` *also has* the `JNI_OnLoad` symbol, but because this library is only loaded by FFM, that hook is **not automatically called by the JVM**.
6. `loaderLookup()` does not see `ffmside` because it does not belong to the class loader's list of JNI-loaded libraries.

We use **two separate libraries** so that the OS having already loaded the same file earlier does not make interpretation difficult.

### 8.1. Directory structure

~~~text
jni-ffm-lookup-demo/
├── JniOwner.java
├── NativeLibraryComparison.java
├── jniowner.c
└── ffmside.c
~~~

The build output will add `.class` files and the OS-appropriate shared libraries.

### 8.2. Java: `JniOwner.java`

~~~java
public final class JniOwner {
    static {
        System.loadLibrary("jniowner");
    }

    private JniOwner() {
    }

    public static native int plusOne(int x);
}
~~~

This is the Java class containing the native method linked by the JVM via the JNI mechanism. The static initializer only loads `jniowner` **when the class is initialized**, not "running `JNI_OnLoad` every time `plusOne` is called".

### 8.3. C: `jniowner.c`

~~~c
#include <jni.h>

static jint hook_count = 0;

/* Only the JVM JNI library loader actively calls this hook. */
JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    ++hook_count;
    return JNI_VERSION_1_6;
}

/* Implementation of Java static native int plusOne(int). */
JNIEXPORT jint JNICALL Java_JniOwner_plusOne(
        JNIEnv *env, jclass declaringClass, jint x) {
    (void) env;
    (void) declaringClass;
    return x + 1;
}

/* Pure C symbol exported for FFM to find via loaderLookup. */
JNIEXPORT jint jniowner_hook_count(void) {
    return hook_count;
}
~~~

**Why are all three functions present?**

- `JNI_OnLoad` is the JNI lifecycle hook, incrementing `hook_count` right when the JVM loads the library.
- `Java_JniOwner_plusOne` binds to the name/signature `JniOwner.plusOne(int)` according to JNI name-based resolution.
- `jniowner_hook_count` is a **C function that is not a Java native method**, merely returning the C global value. We call it via FFM to observe that the hook actually ran.

`JNIEXPORT` ensures symbol export on supported JNI toolchains. On **x64/ARM64 architectures**, `jint` has a 32-bit size matching `ValueLayout.JAVA_INT`; on **32-bit** Windows you need to consider calling conventions and decorated symbols, so the demo requires a **64-bit JDK + compiler of the same architecture**.

### 8.4. C: `ffmside.c`

~~~c
#include <jni.h>

static jint hook_count = 0;

/*
 * This file ALSO exports JNI_OnLoad for comparison.
 * However, the example only loads ffmside using SymbolLookup.libraryLookup.
 * Since there is no JNI library load, this hook does not run automatically.
 */
JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    ++hook_count;
    return JNI_VERSION_1_6;
}

/* Pure C function: Java will call via FFM downcall. */
JNIEXPORT jint ffmside_triple(jint value) {
    return value * 3;
}

/* Returns how many times ffmside's JNI_OnLoad was called by the JVM. */
JNIEXPORT jint ffmside_hook_count(void) {
    return hook_count;
}
~~~

**Important:** `ffmside_triple` does not declare `JNIEnv *`, `jobject`, or `jclass` because it is an **ordinary C function**, not a JNI native method. The `FunctionDescriptor` on the Java side must match `int32 -> int32`.

A file loaded by FFM can still contain exports named `JNI_OnLoad`, but `libraryLookup` itself does not perform the "JVM calls the hook" step. The counter remains at `0` until there is an **actual JNI load** under other conditions.

### 8.5. Java: `NativeLibraryComparison.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class NativeLibraryComparison {
    private NativeLibraryComparison() {
    }

    private static int callNoArg(
            Linker linker, SymbolLookup lookup, String name)
            throws Throwable {
        MethodHandle handle = linker.downcallHandle(
                lookup.find(name).orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT));
        return (int) handle.invokeExact();
    }

    private static int callIntArg(
            Linker linker, SymbolLookup lookup, String name,
            int value) throws Throwable {
        MethodHandle handle = linker.downcallHandle(
                lookup.find(name).orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));
        return (int) handle.invokeExact(value);
    }

    public static void main(String[] args) throws Throwable {
        // 1. Trigger JNI library load of JniOwner.
        System.out.println("JNI result=" + JniOwner.plusOne(41));

        // 2. JNI loader lookup of the same application class loader.
        SymbolLookup loader = SymbolLookup.loaderLookup();
        Linker linker = Linker.nativeLinker();

        int jniHookCount = callNoArg(
                linker, loader, "jniowner_hook_count");

        System.out.println("JNI_OnLoad count=" + jniHookCount);
        System.out.println(
                "loader sees JNI symbol="
                        + loader.find("jniowner_hook_count").isPresent());

        // 3. Separately open ffmside via FFM, not through the JNI loader.
        Path ffmPath = Path.of(
                System.mapLibraryName("ffmside")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup ffm =
                    SymbolLookup.libraryLookup(ffmPath, arena);

            int result = callIntArg(
                    linker, ffm, "ffmside_triple", 14);
            int ffmHookCount = callNoArg(
                    linker, ffm, "ffmside_hook_count");

            System.out.println("FFM result=" + result);
            System.out.println(
                    "FFM JNI_OnLoad count=" + ffmHookCount);
            System.out.println(
                    "loader sees FFM symbol="
                            + loader.find("ffmside_triple").isPresent());
        }
        // arena closes here: do not make downcalls from ffm afterward.
    }
}
~~~

**Notes on the APIs:**

- `System.mapLibraryName("ffmside")` creates a filename like `libffmside.so` / `libffmside.dylib` / `ffmside.dll` depending on the OS. `toAbsolutePath()` resolves the file in the current working directory.
- `SymbolLookup.loaderLookup()` is called from `NativeLibraryComparison`; this class and `JniOwner` are loaded by the **same application class loader** in the demo.
- `SymbolLookup.libraryLookup(ffmPath, arena)` uses an **absolute path** instead of relying on OS search paths.
- `FunctionDescriptor.of(ValueLayout.JAVA_INT)` describes a C function returning `int32` with **no parameters**.
- `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)` describes a C function taking **one `int32` and returning `int32`**.
- `MethodHandle.invokeExact` requires exact types; here `(int) handle.invokeExact(value)` with `value` as `int`. Therefore, the helper declares `throws Throwable`.
- `try (Arena arena = Arena.ofConfined())` keeps the `ffmside` library and symbol segments valid during the downcalls; it closes after all calls complete.

**There is no "hidden `JNIEnv *` parameter" in the FFM downcall** to `ffmside_triple`. Meanwhile, the JNI method `Java_JniOwner_plusOne` is called by the JVM with `JNIEnv *` and `jclass` before the `jint x` parameter.

### 8.6. Compiling Java

Use **JDK 22+**:

~~~bash
javac JniOwner.java NativeLibraryComparison.java
~~~

`--enable-preview` is not needed in JDK 22 for standardized APIs. Make sure **JDK 22+ is actually selected for both `javac` and `java`**.

### 8.7. Building on Linux x64 or ARM64

Set `JAVA_HOME` to the root directory of the running JDK; compile C with GCC or Clang of the same architecture as the JVM:

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jniowner.c -o libjniowner.so

cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  ffmside.c -o libffmside.so
~~~

There is no need to link `libjvm.so` directly when a shared JNI library only receives `JavaVM *` and `JNIEnv *` through hook/native entry points. The OS loader and JVM will provide the JNI interface at runtime accordingly.

### 8.8. Building on macOS x64 or ARM64

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jniowner.c -o libjniowner.dylib

cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  ffmside.c -o libffmside.dylib
~~~

### 8.9. Building on Windows x64

Open **x64 Native Tools Command Prompt for Visual Studio** with an x64 JDK:

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniowner.c /link /OUT:jniowner.dll

cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" ffmside.c /link /OUT:ffmside.dll
~~~

Do not run all three command groups; use the one matching your OS. In all cases, place both shared libraries in the **same working directory** as the two `.class` files, because the demo resolves the FFM path relative to the current directory.

### 8.10. Running Java with native access enabled

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  NativeLibraryComparison
~~~

On Windows Command Prompt, run on one line:

~~~bat
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. NativeLibraryComparison
~~~

- `--enable-native-access=ALL-UNNAMED` grants permission to use restricted FFM methods for classes on the classpath. In JDK 22, omitting it may emit a restricted native access warning; explicitly enabling permission lets the program run without warnings and without depending on policies that will change in later JDKs.
- `-Djava.library.path=.` helps `System.loadLibrary("jniowner")` find the JNI library in the current directory.
- The FFM side uses `Path.toAbsolutePath()`, **not relying on `java.library.path`** to locate `ffmside`.
- `--enable-native-access` does not load libraries by itself, does not create JNI registration, and does not replace ABI verification.

### 8.11. Expected stdout

~~~text
JNI result=42
JNI_OnLoad count=1
loader sees JNI symbol=true
FFM result=42
FFM JNI_OnLoad count=0
loader sees FFM symbol=false
~~~

**Line-by-line analysis:**

1. `JNI result=42`: the JNI native method `plusOne(41)` of `JniOwner` returns `42`.
2. `JNI_OnLoad count=1`: the JVM JNI loader called `jniowner`'s `JNI_OnLoad` once during the demo's load.
3. `loader sees JNI symbol=true`: the application class loader's `loaderLookup` sees `jniowner_hook_count` exported from the JNI-loaded library.
4. `FFM result=42`: the FFM downcall to `ffmside_triple(14)` returns `42`.
5. `FFM JNI_OnLoad count=0`: although `ffmside` exports `JNI_OnLoad`, the `libraryLookup` approach **does not automatically call** the JNI hook.
6. `loader sees FFM symbol=false`: `ffmside` has not been loaded via `System.loadLibrary` in the same class loader; `loaderLookup` does not contain it.

**Conditions for meaningful stdout:** run in a **fresh JVM process**, loading the exact two newly compiled libraries, with no other code calling `System.loadLibrary("ffmside")` or exporting colliding demo symbols. If a real application has already loaded or reused the library through another JNI path, the counter values and symbol sets may differ; the example is designed to isolate the two cases.

## 9. Diagram from the JVM and OS loader perspective

~~~text
                  JAVA APPLICATION (same ClassLoader CL)
                                   |
               +-------------------+-------------------+
               |                                       |
               v                                       v
    JniOwner.plusOne(41)                    NativeLibraryComparison
               |                                       |
               v                                       |
    System.loadLibrary("jniowner")                     |
               |                                       |
               v                                       v
      JVM JNI library registry                  Arena.ofConfined()
      manages (CL, jniowner)                           |
               |                                       v
               |                            SymbolLookup.libraryLookup(
               |                                  ffmsidePath, arena)
               v                                       |
          OS loads JNI lib                             v
               |                                  OS loads FFM lib
               v                                       |
         JVM calls JNI_OnLoad                          |
               |                                       |
               v                                       v
     Java_JniOwner_plusOne                   ffmside_triple(14)
               |                                       |
               +---------------+-----------------------+
                               |
                  SymbolLookup.loaderLookup()
                    finds JNI-loaded symbols,
                    does NOT automatically see ffmside
                               |
                     arena.close() only
                     ends FFM lookup
                     does not remove JNI registry
~~~

Both branches can go through the **same OS dynamic loader** and may reference the same native image if it is the same file. Therefore, we must distinguish:

- **OS load state**: which libraries are mapped in the process, number of native references, dependencies.
- **JNI registration state**: which class loader owns a JNI library and which JNI hooks have run.
- **FFM lookup lifetime**: which arena holds the right to use a set of symbol addresses.

These three layers of state **are related**, but **do not replace each other**.

## 10. Scope of symbol address, MethodHandle, and invocation rights

A symbol lookup returns a `MemorySegment` of size `0` containing a **function address**. This is not a data buffer like `arena.allocate(1024)`. Do not use `get(ValueLayout.JAVA_INT, 0L)` to "read an int" from a function symbol; you must pass the address to the linker with the appropriate `FunctionDescriptor`.

### 10.1. Do not call a function after the arena closes

Anti-pattern:

~~~java
// WRONG: keeping a downcall handle pointing to a library of a closed arena.
MethodHandle saved;

try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup =
            SymbolLookup.libraryLookup(libraryPath, arena);

    saved = Linker.nativeLinker().downcallHandle(
            lookup.find("ffmside_triple").orElseThrow(),
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));
}

// Do not call saved.invokeExact(5) here.
// The library lookup is out of scope: the pointer is no longer valid.
~~~

This snippet is **Java pseudocode**; the `libraryPath` variable comes from the caller. Do not try to predict that every platform will throw the same safe exception when calling a stale native function pointer; calling an unloaded native address can cause a **JVM crash or memory corruption**.

**Rule:** a method handle is **not a tool for extending the lifetime of an Arena**. The owner must keep the arena alive until all foreign calls, callbacks, and background jobs using the library have completed.

### 10.2. Sharing function symbols across multiple threads

For a multi-threaded service, `Arena.ofConfined()` may be unsuitable because symbols from the lookup are tied to a confined scope. Consider `Arena.ofShared()` and then:

- Create the lookup/MethodHandle when starting the service.
- Let multiple workers access it according to the C library's ABI contract and thread-safety guarantees.
- Stop accepting new tasks before shutdown.
- Wait for **all downcalls** to complete.
- Close the shared arena **once** after no one is using the function pointers anymore.

`Arena.ofShared()` **does not guarantee that C functions are thread-safe**. If the native library uses global state or requires separate init/teardown, you must follow the library documentation and use appropriate synchronization.

### 10.3. If a native library is loaded in multiple places

A `libX.so` file can simultaneously be referenced by a JNI load, FFM lookups, and native dependencies. When an FFM arena closes, the OS typically decrements the ownership/reference associated with the lookup; the file may **still be kept loaded** because of other users.

Avoid three assumptions:

1. "`libraryLookup` always creates a new copy of the lib in RAM" — the OS may reuse the loaded image.
2. "`arena.close()` definitely makes the DLL/dylib disappear immediately" — other references may remain.
3. "`arena.close()` is equivalent to `JNI_OnUnload`" — **incorrect**. JNI class-loader lifecycle is a separate matter.

## 11. Common errors when mixing JNI and FFM

| Symptom | Possible root cause | How to resolve |
| --- | --- | --- |
| `System.loadLibrary` throws `UnsatisfiedLinkError` | Wrong JNI library name, missing `java.library.path`, wrong ABI/dependency | Check `System.mapLibraryName`, path, CPU architecture, and native deps |
| JNI method throws `UnsatisfiedLinkError` when called | Library loaded but `Java_*` name or `RegisterNatives` is wrong | Compare JNI header (`javac -h`), method descriptor, and exports |
| `JNI_OnLoad` does not run when using `libraryLookup` | No JNI library load occurred | **By design**; if JNI setup is needed, use the JNI mechanism |
| `loaderLookup().find("ffmSymbol")` is empty | Library was only loaded via `libraryLookup` | Use the **FFM lookup itself** returned by `libraryLookup` |
| `libraryLookup` cannot find symbol | Symbol not exported, C++ name mangling, wrong path, dependency, typo | Check exports and use `extern "C"` with C++ |
| `libraryLookup` throws `IllegalArgumentException` | Name/path does not identify a valid library | Use an absolute path to the right `.so/.dll/.dylib` |
| `libraryLookup` throws `IllegalCallerException` | Caller module has not been granted native access | Use `--enable-native-access=ALL-UNNAMED` on classpath or the right module name |
| `lookup.find("foo").orElseThrow()` throws `NoSuchElementException` | `find` returned `Optional.empty()` | Check symbol name, export visibility, and library |
| `MethodHandle.invokeExact` throws `WrongMethodTypeException` | Java argument/return types do not match descriptor | Check `FunctionDescriptor` and `MethodHandle.type()` |
| JVM crashes even though MethodHandle types look right | Actual C ABI differs from descriptor: struct/varargs/pointer/calling convention | Check C signature, linker canonical layouts, native ABI; errors may not be detected by Java |
| `WrongThreadException` when using lookup/symbol | Confined arena used from another thread | Pick the right owner thread or use a shared arena |
| Error after `Arena.close()` | Calling stale symbol/MethodHandle | Ensure the arena is alive during all downcalls; do not call after close |
| Plugin class loader cannot be unloaded | `loaderLookup`/symbol or static references still reachable | Check reachability and owners; do not retain unintentionally |
| Arena closed but `JNI_OnUnload` has not run | Closing Arena does not remove JNI registration | Manage JNI class loader separately; do not conflate lifecycles |
| Same JNI library loaded from another loader is rejected | JNI has a policy that one library cannot attach to two independent loaders | Design a stable native bridge loader or separate deployments |

### 11.1. Native symbol diagnostic tools

Linux:

~~~bash
nm -D libjniowner.so
nm -D libffmside.so
~~~

macOS:

~~~bash
nm -gU libjniowner.dylib
nm -gU libffmside.dylib
~~~

Windows Developer Command Prompt:

~~~bat
dumpbin /exports jniowner.dll
dumpbin /exports ffmside.dll
~~~

You should see the corresponding exported symbols (on some platforms `nm` shows an underscore prefix depending on the binary format). With C++ code, you must export using `extern "C"` to avoid C++ name mangling for functions used by FFM (and export `JNI_OnLoad` with proper JNI C linkage).

Do not assume that if `System.loadLibrary("jniowner")` succeeds, every C symbol can be looked up via `loaderLookup`: the symbol must actually be exported/visible. A native internal `static` function in C is not exported just because the library was loaded by JNI.

## 12. Be careful with `FunctionDescriptor` and JNI signatures

The following two functions both take one integer and return one integer, but their **calling interfaces differ**:

~~~c
/* Native implementation of a Java JNI method. */
JNIEXPORT jint JNICALL Java_JniOwner_plusOne(
        JNIEnv *env, jclass clazz, jint x);

/* Pure C function for an FFM direct downcall. */
JNIEXPORT jint ffmside_triple(jint x);
~~~

For the JNI method, the JVM automatically passes `JNIEnv *` and `jclass`; the Java application **does not** construct a `FunctionDescriptor` for that native method itself. For `ffmside_triple`, FFM's `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` accurately describes **one int argument** and **an int return value**.

**Do not take the address of `Java_JniOwner_plusOne` and call it with a one-int-argument descriptor**. That function requires two additional ABI parameters. A wrong descriptor can cause a crash or read garbage data rather than just throwing `WrongMethodTypeException`.

A foreign function can also:

- Return `void`: `FunctionDescriptor.ofVoid(...)`.
- Accept a pointer: use `ValueLayout.ADDRESS` and `MemorySegment` carrier.
- Accept/return C `long`: check the ABI; on Windows x64, C `long` is usually 32-bit, whereas on Linux/x64 it is usually 64-bit.
- Accept a `struct`: must describe `MemoryLayout` and ABI-correct padding/alignment.
- Be a variadic function: must use the appropriate FFM linker option for variadic arguments, not mistakenly assign a fixed descriptor.

**FFM does not know what types a C function name carries.** `lookup.find(...)` only provides the address; `FunctionDescriptor` is the programmer's commitment that the ABI signature has been verified.

### 12.1. Native access is capability control, not a sandbox

In JDK 22, `SymbolLookup.libraryLookup(...)` and `Linker.downcallHandle(...)` are **restricted methods**. Use:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeLibraryComparison
~~~

In projects using Java modules, you should grant native access **only to the module that needs FFM** rather than `ALL-UNNAMED` for the entire classpath. This flag **does not verify the quality or trustworthiness of the DLL**; a malicious or ABI-buggy library can still corrupt the process. Only load libraries from trusted paths and control deployment.

**Version differences:** starting in JDKs after 22, the warning/rejection policy for restricted native access continues to evolve. Running commands with explicit native access permissions keeps examples independent of per-version default policies.

## 13. Calling the same library via both JNI and FFM: when does it make sense?

Some applications gradually migrate from JNI to FFM, or have a library exporting **both a JNI bridge and C ABI functions**. In that case:

- The library can continue to be loaded via `System.loadLibrary` to perform JNI registration and use `JNI_OnLoad`.
- FFM can look up pure C symbols from that same JNI-loaded library via **`SymbolLookup.loaderLookup()`**, provided the caller class loader matches.
- There is no need to open an additional `libraryLookup` just to look up a symbol already in the loader lookup, if JNI ownership meets the requirements and the export is visible.
- If you must use a separate `libraryLookup` for the same file, treat it as **an OS-level reference/lookup with its own Arena lifetime**, not a request for the JVM to perform a second JNI load.
- Do not call JNI functions with an FFM descriptor missing `JNIEnv *`/`jclass`; instead, export a separate **pure C ABI wrapper** for FFM.

### 13.1. Architecture pattern for gradual migration

~~~text
Java app / service
      |
      +-- JNI bridge (legacy)
      |     System.loadLibrary("legacy")
      |     native methods -> Java_... / RegisterNatives
      |     JNI_OnLoad for JNI setup
      |
      +-- FFM bridge (new)
            SymbolLookup.loaderLookup() if using C symbols
            in the already loaded JNI library
            or
            SymbolLookup.libraryLookup(newLibPath, arena)
            if the library is managed separately by FFM
            |
            FunctionDescriptor + Linker
            |
            MethodHandle.invokeExact(...)
~~~

Factors to decide **before** writing code:

1. Does the native library have a **public/stable C ABI**, or only JNI entrypoints?
2. Who owns init/teardown? JNI hooks, an explicit native API, or the library's RAII?
3. Which class loader owns the JNI library? Is there plugin/reloading?
4. How long do data and function pointers need to exist; which Arena manages them?
5. Are there native background threads holding pointers? When can it be closed/unloaded?
6. Is there a situation where `libraryLookup` and JNI load the same file, causing ABI/static global state to be shared unintentionally?

A good init/teardown contract usually has explicit C functions such as `library_init()`/`library_shutdown()` if the library needs to be used from multiple runtimes. **Do not assume `JNI_OnLoad` is a universal init API for all consumers**, because the OS loader/FFM does not automatically run the JNI hook.

## 14. Why should you not call `JNI_OnLoad` manually via FFM?

Suppose `libraryLookup` finds the exported symbol `JNI_OnLoad`. Someone might think: "I'll downcall that hook directly to initialize the FFM library". This is **not a replacement** for JNI library loading because:

- `JNI_OnLoad` takes `JavaVM *` and a reserved pointer according to the JNI contract; a Java FFM app has no valid reason to simulate the JVM loader handshake.
- `JNI_OnLoad` may call `FindClass` and `RegisterNatives` relying on the **class loader context** created by the JNI loader. Calling it directly from FFM does not fully recreate that context.
- The JVM does not register the library in the JNI registry just because a native function named `JNI_OnLoad` was called via a downcall.
- It can initialize state multiple times, in the wrong order, or cause errors if the JNI loader later actually runs the hook.
- When the arena closes, `JNI_OnUnload` will not automatically pair with the forged call.

**The right way:** use `System.loadLibrary` if you need a JNI library/lifecycle; use `libraryLookup` if you need C symbols via FFM and the native library has an appropriate init/cleanup mechanism for FFM.

## 15. Practical lifetime scenarios

### 15.1. Confined library lookup for a synchronous operation

~~~java
void runOnce() throws Throwable {
    try (Arena arena = Arena.ofConfined()) {
        SymbolLookup lookup = SymbolLookup.libraryLookup(
                Path.of("/trusted/lib/tool.so"), arena);

        var fn = Linker.nativeLinker().downcallHandle(
                lookup.find("run_tool").orElseThrow(),
                FunctionDescriptor.of(ValueLayout.JAVA_INT));

        int rc = (int) fn.invokeExact();
        // Read result, check rc before closing.
    }
}
~~~

The snippet above is a **non-standalone illustration**: the C path and symbol name are just examples; declare imports/ABI according to your project. For libraries loaded/unloaded very frequently, `dlopen/dlclose` overhead can be significant; consider keeping a lookup longer to match the service lifetime if that fits the requirements.

### 15.2. Shared library tied to service lifecycle

~~~java
// Java pseudocode describing architecture, not runnable standalone.
final class NativeService implements AutoCloseable {
    private final Arena arena = Arena.ofShared();
    private final SymbolLookup symbols =
            SymbolLookup.libraryLookup(verifiedPath, arena);

    void runTask() {
        // Use symbols + linker handle from the library while arena is alive.
        // Synchronize native global state if the library is not thread-safe.
    }

    @Override
    public void close() {
        // Stop accepting new work.
        // Wait for all running workers/downcalls to complete.
        arena.close();
    }
}
~~~

This is **pseudocode**; `verifiedPath` and worker coordination code are not defined. It is intentionally not presented as runnable source because properly closing a shared library requires project-specific lifecycle, task tracking, and error handling.

### 15.3. JNI-loaded library in a plugin class loader

If a plugin loads a JNI library with `System.loadLibrary`, do not let a global singleton accidentally hold onto the plugin's `SymbolLookup.loaderLookup()` or symbol segments forever. According to the javadoc, a loader lookup has a scope that keeps the caller class loader reachable; therefore, caching it in a long-lived class loader can **prevent the JNI library from unloading** even after the plugin logic has been removed.

When you want to unload a plugin properly:

- Stop related native calls/callbacks and native threads.
- Clear references to plugin classes, class loaders, and JNI global references where appropriate.
- Do not keep loader lookups/symbols in a permanent cache outside the plugin owner.
- Do not expect `JNI_OnUnload` to run immediately just because you dropped a Java reference.
- Consider separating the native bridge into a stable loader if the library does not support reloading.

## 16. Self-check questions and answers

**1.** After using `SymbolLookup.libraryLookup(path, arena)`, does `SymbolLookup.loaderLookup()` of the same app class loader automatically see that library's symbols?

**Answer:** No. `loaderLookup` is only for libraries loaded via JNI and associated with the caller class loader; an FFM lookup does not automatically register a JNI library.

**2.** The `ffmside` library exports `JNI_OnLoad`. Why does the example return a hook count of 0?

**Answer:** Because the library was loaded **only** via `libraryLookup`. OS dynamic loading does not mean the JVM calls the JNI lifecycle hook. There is no JNI load for `ffmside` in the demo.

**3.** Can a library already loaded with `System.loadLibrary` use FFM to find its own C symbols?

**Answer:** Yes. `SymbolLookup.loaderLookup()` finds symbols of JNI-loaded libraries associated with the caller loader. `libraryLookup` can also look them up from that library through a separate lookup, though without transferring class-loader ownership.

**4.** Can a method handle pointing to a `libraryLookup` symbol be called after the arena has closed?

**Answer:** No. The symbol address is tied to the arena's scope. Calling an invalidated pointer can cause severe errors, including a crash. Only close after all foreign calls have completed.

**5.** Is `JNI_OnUnload` automatically called when `Arena.close()` runs?

**Answer:** No. That is a **JNI class-loader lifecycle hook**, not a callback for closing an FFM library lookup.

**6.** Why can both `JNI_OnLoad` and a C++ constructor be called at different times?

**Answer:** C++/OS constructors belong to **OS dynamic loader initialization**. `JNI_OnLoad` is actively called by the **JVM JNI loader** after loading via the JNI mechanism. FFM can trigger the OS constructor without calling `JNI_OnLoad`.

**7.** `ffi_process` cannot be found using `loaderLookup`. Does that mean the native file is definitely not in RAM?

**Answer:** No. It may have been loaded via FFM, an OS dependency, or another loader. `loaderLookup` only considers JNI libraries associated with the caller class loader, not the entire process.

**8.** In FFM, if C declares `int triple(int)`, what `FunctionDescriptor` should be chosen?

**Answer:** On the demo x64 ABI, `FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT)`: returns `int` and takes one `int`. Java invocation uses `(int) methodHandle.invokeExact(intValue)`.

**9.** Why is `--enable-native-access=ALL-UNNAMED` needed when running the JDK 22 example?

**Answer:** `libraryLookup` and `downcallHandle` belong to restricted FFM APIs. Granting native access explicitly to classpath code avoids warnings and JVM policy restrictions; it does not turn the native library into a safe sandbox.

**10.** Why should you not directly call the exported `JNI_OnLoad` via FFM?

**Answer:** It does not perform JNI library registration, does not create the proper class-loader loading context, and can cause JNI setup to run in the wrong order or repeatedly. To use JNI, you need `System.loadLibrary`.

**11.** If two FFM lookups or one JNI load and one FFM lookup point to the same file, does closing one Arena guarantee the file unloads immediately?

**Answer:** No. The OS may keep the library loaded due to other references. Closing an Arena ends that Arena's **lookup ownership**, without removing all OS/JNI references.

**12.** When should you use `Linker.defaultLookup()` instead of `libraryLookup`?

**Answer:** When you need symbols in the default native libraries supported by the linker/OS (e.g., libc). When you want a specific custom library, use `libraryLookup`; when you want a JNI library belonging to the class loader, use `loaderLookup`.

## 17. Checklist when choosing a loading mechanism

- Does the library need **JNI native methods**, `JNI_OnLoad`, or `RegisterNatives`? → Choose the JNI mechanism.
- Does the library mainly have **C ABI functions** and need to be called with `FunctionDescriptor`? → Choose FFM library lookup.
- Was the library already loaded via JNI by the **same class loader**? → Try `loaderLookup` before opening a separate FFM lookup.
- Do you need to control when the FFM library is released yourself? → Choose a confined/shared Arena and organize ownership clearly.
- Are multiple threads/downcalls running concurrently? → Use a shared arena when appropriate, coordinate stop/join/close, and ensure C thread-safety.
- Does the library have a JNI hook but is loaded via FFM? → **Do not** expect the hook to be called.
- Have you verified exported symbols with `nm`/`dumpbin`, native dependencies, and the correct CPU architecture?
- Does `FunctionDescriptor` have the exact **C ABI signature**, without mixing in JNI's two implicit parameters?
- Has native access been granted to the module/classpath using restricted FFM APIs?
- Is there a clear shutdown path with no remaining downcalls/native callbacks when closing?
- Are there plugin class loaders? → Beware of `loaderLookup` keeping the class loader reachable and preventing the JNI library from unloading.
- Are you inadvertently relying on one OS's refcount/`dlopen` behavior to infer Java behavior on another OS?

## 18. Official reading sources

- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup`, `loaderLookup`, `defaultLookup`, dynamic visibility, and scope rules.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `downcallHandle`, C ABI mapping, and restricted access.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): specifying native parameter/return types.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): lifetime, confined/shared/automatic/global scopes.
- [Oracle Java SE 22 — Restricted Methods](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html): `--enable-native-access` and restricted APIs.
- [Oracle Java SE 22 — JNI Invocation API](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/invocation.html): JNI library management mechanism and `JNI_OnLoad`/`JNI_OnUnload` lifecycle.
- [Oracle Java SE 22 — System.loadLibrary](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): library naming rules and JNI load.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): official FFM API as of JDK 22.

**Key takeaway:** `System.loadLibrary` → **JVM JNI registry + class loader + JNI lifecycle**. `SymbolLookup.libraryLookup` → **OS library lookup + Arena lifetime + FFM symbols**. `SymbolLookup.loaderLookup` is the bridge for looking up symbols from **already-loaded JNI libraries**, not a command to load a new library or a list of all native code in the process.
