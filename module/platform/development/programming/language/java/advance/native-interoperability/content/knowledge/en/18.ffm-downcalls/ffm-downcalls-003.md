# Choosing an Arena for Library Lifetime and Symbol Addresses

## 1. The problem: once you have a native function address, when does that address become invalid?

In **Java Advance – native-interoperability**, under the topic **Calling Functions with FFM**, Java can load a native library using `SymbolLookup.libraryLookup(...)`, find a symbol such as `abs` or `strlen`, and create a `MethodHandle` via `Linker.nativeLinker()`. The danger is that **a `MethodHandle` still existing in Java does not prove the function code it points to is still loaded**, and a symbol address of type `MemorySegment` does not mean it is permitted to be used outside its scope.

This lesson answers the exact question: **which kind of `Arena` should you choose to manage the lifetime of a native library and the symbol addresses obtained from that library?** Specifically:

- The `Arena` passed to `SymbolLookup.libraryLookup(nameOrPath, arena)` controls the **lifetime of the library lookup**, which relates to **loading / potentially unloading the library** and the validity of symbol addresses.
- A `MemorySegment` representing a **symbol address** typically has `byteSize() == 0`. It is used as a function address for the linker, **not a 0-byte data buffer that can be read arbitrarily**.
- `Arena.ofConfined()` is suitable if **one single thread** performs the downcalls and closes the owner; `Arena.ofShared()` is suitable for a **library binding shared by multiple threads** with a clear shutdown protocol.
- `Arena.ofAuto()` and `Arena.global()` do not have an **explicit close point** to reflect a session that needs to unload at the right time; use them only when there is truly an appropriate lifetime contract.
- **The library's arena** and **the arena allocating strings/arrays/native buffers for each call** do not have to be the same. An input buffer can end after a synchronous downcall, while the symbol and library must live across multiple calls.
- Once Java closes the arena, do not call the `MethodHandle`/function pointer tied to that library again; **do not test use-after-unload** because it can crash the JVM instead of throwing an easy-to-catch exception.

The two complete Java programs below were compiled with `javac --release 22` and run on **JDK 24 / Windows x64**. They use **official FFM from JDK 22**, without needing JNI glue code. The main example calls C runtime functions through library lookup; the second example manages a library used concurrently by two worker threads with explicit close.

### Learning Objectives

After this lesson, you can:

1. Distinguish `SymbolLookup.libraryLookup` from `linker.defaultLookup()` and `SymbolLookup.loaderLookup()` regarding symbol source and lifetime.
2. Explain which `Arena` keeps the library alive, which `MemorySegment` is only a symbol address, and which `MethodHandle` is used to call it.
3. Choose `ofConfined` or `ofShared` according to single-thread/multi-thread needs; avoid using `global/auto` to dodge designing shutdown.
4. Separate the lifetimes of **library / symbol address / downcall handle / call arguments / callback stub**.
5. Design `OPEN → CLOSING → CLOSED` so there are no in-flight foreign calls during unload.
6. Handle errors for missing library, missing symbol, native access permission, wrong ABI, wrong thread, using an expired address, and closing an arena twice.
7. Write and run a Java 22+ program that accurately checks scope state **before/after close** without **calling a native function after close**.

## 2. The ownership picture: library vs. argument memory

Look at the path from Java to C:

~~~text
                 Java application
                         |
                +--------+-----------+
                |                    |
         BINDING / LIBRARY        ONE CALL
                |                    |
       Arena libraryArena      Arena callArena
         (long lifetime)        (short lifetime)
                |                    |
         SymbolLookup              allocateFrom("...")
         .libraryLookup              |
                |                 MemorySegment (C char*)
         find("strlen")              |
                |                    |
        MemorySegment symbol         |
     (function addr, size 0)         |
                |                    |
      Linker.downcallHandle          |
                |                    |
            MethodHandle ----------> C strlen(char*)
                |                    |
           returns result <----------+
                |
         Continue using other functions,
         or call again with a new buffer

     STOP new calls -> wait for in-flight -> close libraryArena
     => symbol addresses belonging to that scope are no longer valid
~~~

**The tricky point:** `callArena.close()` can happen **between two downcalls** with no reason to close the library; conversely, `libraryArena.close()` can make future calls using a cached handle invalid, even when the Java `MethodHandle` object has not yet been garbage-collected.

An example contract:
- **Library owner** is responsible for loading the library once and keeping `Arena libraryArena` alive while any caller has the right to perform a downcall.
- **Call owner** is responsible for creating/releasing temporary buffers (`Arena callArena`) after the foreign function **has truly stopped using the pointer**.
- **Callers of the library owner** must not take a raw function address and store it beyond the lifecycle; if access from multiple threads is needed, go through the owner performing a gate/lease.

In a real library, there may be **native-created workers** and C callbacks holding pointers to Java. In that case, the lifetime must extend until native code stops, not just until the Java method returns.

## 3. How does `SymbolLookup.libraryLookup` bind a library to an arena?

JDK 22+ FFM provides two factories for a specific native library:

~~~java
// Fragment inside a Java method, requires import java.lang.foreign.*.
SymbolLookup byName =
        SymbolLookup.libraryLookup("libExample.so", libraryArena);

SymbolLookup byPath =
        SymbolLookup.libraryLookup(
                Path.of("/absolute/path/libExample.so"),
                libraryArena);
~~~

This is **illustrative syntax**, not a standalone runnable file, and the name/path are just Linux examples. `Path` requires `import java.nio.file.Path;`. Use **one of the two**, do not load twice by default.

Both methods are **restricted native access**. They:
1. Locate the library by a **name** understood by the OS loader, or by a **path** in the file system.
2. Load the library if it is not already in the process according to OS semantics.
3. Return a lookup that only finds symbols exported in that library.
4. Bind the **scope of the lookup and symbol addresses** to the passed `arena`.
5. When the arena closes, the library lookup's lifetime ends; the library may be unloaded from the process, depending on reference counting / the loader / whether another component is also holding the library.

Syntax to run from a regular classpath:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

Without native access permission, the application may receive a warning or `IllegalCallerException` depending on the JDK release and policy in use. **Do not confuse the native access flag with granting more memory**: this is a mechanism declaring that a module is allowed to perform risky FFM operations, not something that makes a native function safe if the ABI is wrong.

### Closing the arena: do not equate scope with the physical state of the DLL/SO

If `try (Arena arena = Arena.ofConfined())` finishes normally, `arena.scope().isAlive()` turns `false`. That is what **Java FFM can verify**. Whether the operating system has actually unloaded the SO/DLL file from the process can depend on:
- the library already being loaded by the JVM or another module;
- the dynamic loader's reference count;
- dependencies between native libraries;
- the OS's policy for retaining system runtime libraries.

Therefore, the accurate phrasing is **the library lookup and symbol addresses of the owner arena have expired; do not call anymore**. Avoid claiming "the DLL is definitely removed from memory immediately" or relying on whether the file remains open to decide safety.

### A `SymbolLookup` does not tell you the ABI signature on its own

~~~java
MemorySegment address = byName.find("ffi_calculate")
        .orElseThrow(() -> new IllegalStateException("symbol missing"));
~~~

`address` only represents the location of the native symbol. `find` does not read C headers or know `int`/`size_t`/pointer arguments. The developer must have the appropriate `FunctionDescriptor` for `Linker` to create the handle. A wrong native signature can crash the JVM; there is no compile-time Java type checker comparing the symbol against the real C function declaration.

## 4. A symbol address is a special `MemorySegment`

The FFM Javadoc describes a symbol's address as a **zero-length memory segment**:

~~~java
MemorySegment functionAddress =
        lookup.find("abs").orElseThrow();
long bytes = functionAddress.byteSize(); // 0 in this lesson's lookup.
~~~

This is not a buffer:

~~~java
// WRONG – cannot read an int value from a zero-length "function address".
int data = functionAddress.get(ValueLayout.JAVA_INT, 0);
~~~

You can use it as a function address for `linker.downcallHandle(address, descriptor)`. If the symbol is a **native global variable**, to manipulate data located at that address you must know the size, alignment, and ownership, and then use the appropriate API; expanding bounds with `reinterpret` is a **restricted operation** and can be dangerous if you guess the size.

### Checking scope without dereferencing

From a symbol of `libraryLookup(..., arena)`:

~~~java
MemorySegment address = lookup.find("abs").orElseThrow();
boolean active = address.scope().isAlive();
~~~

In the demo: while `libraryArena` is open, `active` is `true`; after `close`, it is `false`. **Do not print raw addresses** because addresses depend on ASLR/OS/run session and are not useful for proving lifetime.

A Java `MemorySegment` can still exist after its scope has closed, but it is an **expired view**. Keeping a `MemorySegment` in a Java field, converting it to `long` and reconstructing a pointer, or keeping a `MethodHandle` are different ways of holding **address information**; they do not replace valid usage permission according to lifetime.

### Symbol scope and input buffer scope are different

`functionAddress.scope()` is bound to the lookup's **libraryArena**; `inputCString.scope()` is bound to the **callArena** that allocated it. Two objects can have the same Java type `MemorySegment` yet have different owners and must be closed at different times.

This is why you should name `libraryArena` and `callArena` clearly in source code, instead of using just one long-lived `arena` variable where nobody knows who is responsible.

## 5. Choosing an Arena type for a library: confined, shared, auto, or global?

| Arena type | Can it be used with `libraryLookup`? | Main limitation | Suitable case |
|---|---|---|---|
| `Arena.ofConfined()` | Yes | Symbol segments/thread access belong to **the thread that created the arena**; closed by owner thread | Binding used synchronously on a single thread; tests/demos or dedicated thread |
| `Arena.ofShared()` | Yes | Allows multiple threads to use symbols; **does not automatically prevent races between close and calls** | Binding shared by a server/worker pool; requires owner/gate/stop protocol |
| `Arena.ofAuto()` | Yes if native-access policy allows | No explicit close; cleanup by reachability/GC, **no deadline** | Only when automatic lifetime truly fits the contract |
| `Arena.global()` | Yes if policy allows | Scope never closes; native resources can live until process end | Library intentionally used for the entire JVM lifetime, bounded in count and needing no unload |

### 5.1. Choose `ofConfined` when all operations belong to one thread

~~~java
// Fragment, requires Java 22+ and native access.
try (Arena libraryArena = Arena.ofConfined()) {
    SymbolLookup lookup =
            SymbolLookup.libraryLookup(libraryName, libraryArena);

    MemorySegment address = lookup.find("abs").orElseThrow();
    MethodHandle abs = linker.downcallHandle(
            address,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

    int result = (int) abs.invokeExact(-17);
    // result == 17.
} // Symbol scope and library owner end here.
~~~

Pros: short lifetime, closed at the right place, simple, low scope overhead. Cons: **do not** pass a symbol/handle bound to a confined arena to a thread pool and arbitrarily call it on other threads. In particular, if another Java thread calls `close` on a confined arena, you will typically encounter `WrongThreadException`.

### 5.2. Choose `ofShared` for a multi-threaded library-wide owner

~~~java
// Conceptual fragment: operations must reside in an owner class with a gate.
Arena libraryArena = Arena.ofShared();
SymbolLookup lookup = SymbolLookup.libraryLookup(
        libraryName, libraryArena);
MethodHandle mh = linker.downcallHandle(
        lookup.find("abs").orElseThrow(), signature);

// Multiple worker threads may use the shared-scope symbol.
// Owner must block new calls and wait for all old calls to finish before:
libraryArena.close();
~~~

**Shared does not mean "safe to close anywhere/anytime"**. The arena may refuse to close while a segment is being accessed concurrently (for example, a downcall is running), but an exception is not a substitute for a lock/gate/state machine. For deterministic shutdown, **do not allow a race and just catch `IllegalStateException` to retry arbitrarily**.

### 5.3. When to avoid `ofAuto` or `global`?

If the code has an explicit `closeSession()`, needs to guarantee native calls are no longer possible after the method returns, and wants to release the library at the right time, **`ofAuto` gives no deadline**, while `global` **cannot be closed**. If you create hundreds of independent classloaders/plugins and each plugin uses `Arena.global()`, native code/resources may never be released per session.

Both still have valid use cases: a system dependency that must live for the entire process can use global lifetime; an API purely based on reachability can consider auto. Explicitly document this choice as an **ownership decision**, not a choice made "to avoid having to close".

### 5.4. Quick decision table

| Problem | Recommended arena for **library** | Recommended arena for **arguments** |
|---|---|---|
| One thread calls a few synchronous functions in a block | `ofConfined`, using `try-with-resources` | `ofConfined` per call or the same arena if lifetimes match |
| One service with multiple request threads using the same library | `ofShared` held by the service/binding owner | `ofConfined` **per request/call thread** for short buffers |
| Native async callback holds a pointer after return | `ofShared` or an appropriate long-lived owner | Session arena living until after callback/unregister, not call-local |
| Plugin needing explicit unload/reload | `ofShared`/`ofConfined` depending on threads, with explicit `close` | Scope of each operation |
| Library used for the entire process lifecycle, no unload needed | `global` may be suitable if there is a real contract | Still **should not** default every request buffer to global |

Different arena choices are normal: **the lifetime of function code** and **the lifetime of bytes passed into the function** are two independent contracts.

## 6. `libraryLookup`, `defaultLookup`, `loaderLookup`: do not mix up ownership

| API | Where do symbols come from? | Lifetime / owner |
|---|---|---|
| `SymbolLookup.libraryLookup(name/path, arena)` | A specific native library, loaded if not already present | **The passed arena** controls lookup/library lifetime |
| `Linker.nativeLinker().defaultLookup()` | Native libraries the underlying linker/JVM chooses to expose | Does not take a caller-owned arena; does not close on its own like library lookup |
| `SymbolLookup.loaderLookup()` | Libraries loaded via `System.load`/`System.loadLibrary` in the caller's class loader | Has classloader reachability semantics; does not depend on an arbitrary call-local arena |

A common misconception: "I already used `SymbolLookup.libraryLookup("foo", arena)`, so `SymbolLookup.loaderLookup().find("foo")` must find the symbols in foo". **Incorrect**: JDK 22 specifies that loader lookup only includes libraries loaded via the JNI loader, and does not automatically include libraries loaded by library lookup. Therefore, **keep the exact lookup you received** from `libraryLookup` when you want to access symbols in the same scope.

Another misconception: "`defaultLookup` searches every library installed on my machine". There is no such guarantee; the symbol set of default lookup depends on the native linker/JDK/OS. For a specific plugin, use `libraryLookup` with a name/path and manage the arena.

### `SymbolLookup.or(...)` and each source's lifetime

`lookupA.or(lookupB)` creates a combined lookup: try A first, and if not found, try B. However, **it does not merge two library arenas into a single owner**. A symbol found from A belongs to A's lifetime; one found from B belongs to B's lifetime. You must not close A early just because you still hold the composite lookup and B is still alive.

Example (fragment):

~~~java
SymbolLookup combined = SymbolLookup.libraryLookup("foo", arenaFoo)
        .or(SymbolLookup.libraryLookup("bar", arenaBar));
MemorySegment address = combined.find("some_function").orElseThrow();
// Must know whether the symbol came from foo or bar to choose the right lifetime.
~~~

If two libraries have a symbol with the same name, lookup order also matters: A takes precedence. In large bindings, manage each library/ABI separately to avoid accidentally calling a symbol from the wrong library.

### Name vs. path

`libraryLookup(String, Arena)` resolves the name via the **OS native loader** (Windows `LoadLibrary`, Linux `dlopen`, etc.); names like `libc.so.6`, `msvcrt.dll`, `libSystem.B.dylib` are **platform-specific**, not portable JVM names. `libraryLookup(Path, Arena)` is for a specific file, usually suitable for libraries packaged with the application. Using `Path.of(...).toAbsolutePath()` does not make a binary compatible if the CPU architecture or dependencies are wrong.

## 7. Linker and MethodHandle do not "pin" all native code lifetimes

To perform a downcall:

~~~java
Linker linker = Linker.nativeLinker();
MemorySegment symbol = lookup.find("abs").orElseThrow();

FunctionDescriptor signature = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

MethodHandle abs = linker.downcallHandle(symbol, signature);
int result = (int) abs.invokeExact(-42);
~~~

C equivalent: `int abs(int);`. On common ABIs `int` is 32-bit; production applications must verify C headers and the ABI instead of assuming every `int`/`long` has the same size. `ValueLayout.JAVA_INT` uses the Java `int` carrier.

`MethodHandle` is a callable Java object, but **it has no authority to extend the library's lifetime indefinitely**. It can only be invoked while the function address/lookup is still valid. If the library arena is closed, calling `abs.invokeExact(-42)` with the old handle is not permitted — **do not try it**, because in wrong-lifetime cases it can lead to a severe JVM error, not just a Java exception.

### Java code running successfully does not mean the ABI is right

`SymbolLookup.find("abs")` only confirms a symbol with that name exists. `FunctionDescriptor` must be constructed based on the **real C signature**. Wrong example:

~~~java
// Wrong: abs(int) but described as taking a pointer address.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.ADDRESS);
~~~

If you try to call C `abs` with this descriptor, you have told the linker an ABI different from reality. Some situations may produce garbage results or crash. Do not use Java exception handling as a substitute for checking signatures.

### Function addresses can change on reload

The OS loader may assign a different location when a native library is unloaded/reloaded (ASLR or process state). Do not store a raw `long functionAddress` in a database/cache and reuse it after a restart/reload. Always create a **new lookup/handle in a new owner** if reloading is needed. Java references to the old symbol must not be carried over to the new binding instance.

## 8. Program 1: two arenas, one library, and two C function calls

This example demonstrates **`Arena.ofConfined()`** managing a library used in the **same thread**, while a second `Arena.ofConfined()` manages a C string for a single call. We use two common C functions:

~~~c
/* Two C declarations to specify the ABI, not JNI glue code. */
int abs(int value);
size_t strlen(const char *text);
~~~

`abs` takes/returns `int`; `strlen` returns `size_t` (ABI-specific) and takes a pointer to a NUL-terminated C string. Operating systems have different C runtime names; the code has typical choices for Windows, Linux, and macOS. Tested on **Windows x64/JDK 24**; there is no guarantee every Linux/macOS distribution exposes both symbols under those exact names in the chosen library.

### 8.1. Complete Java file: `LibraryArenaLesson.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.util.Locale;

public final class LibraryArenaLesson {
    private static String nativeLibraryName() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        if (os.contains("win")) return "msvcrt.dll";
        if (os.contains("mac")) return "libSystem.B.dylib";
        if (os.contains("linux")) return "libc.so.6";
        throw new UnsupportedOperationException(
                "No example libc name for " + os);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment escapedAddress;

        try (Arena libraryArena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                    nativeLibraryName(), libraryArena);

            MemorySegment absAddress = library.find("abs")
                    .orElseThrow(() -> new IllegalStateException(
                            "abs not exported"));
            escapedAddress = absAddress;

            System.out.println("symbolBytes=" + absAddress.byteSize());
            System.out.println(
                    "libraryAlive=" + libraryArena.scope().isAlive());

            FunctionDescriptor absSignature = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
            MethodHandle abs = linker.downcallHandle(
                    absAddress, absSignature);

            int first = (int) abs.invokeExact(-7);
            System.out.println("abs(-7)=" + first);

            MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");
            if (sizeT == null) {
                throw new AssertionError("missing size_t");
            }
            MemorySegment strlenAddress = library.find("strlen")
                    .orElseThrow(() -> new IllegalStateException(
                            "strlen not exported"));
            MethodHandle strlen = linker.downcallHandle(
                    strlenAddress, FunctionDescriptor.of(
                            sizeT, ValueLayout.ADDRESS));

            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment cstr =
                        callArena.allocateFrom("library");
                long n = ((Number) strlen.invokeWithArguments(cstr))
                        .longValue();

                System.out.println("strlen=" + n);
                if (n != 7) {
                    throw new AssertionError("bad strlen");
                }
            } // cstr buffer lifetime ends here.

            // C library is still alive even though callArena is closed.
            int second = (int) abs.invokeExact(-42);
            System.out.println("afterCallArenaAbs=" + second);

            if (first != 7 || second != 42) {
                throw new AssertionError("bad abs");
            }
        } // Close libraryArena; downcall permission ends.

        // Only observe scope state, DO NOT call abs/strlen again.
        System.out.println("symbolAliveAfterClose="
                + escapedAddress.scope().isAlive());
        if (escapedAddress.scope().isAlive()) {
            throw new AssertionError("library scope alive");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

No `package`; the file name must be `LibraryArenaLesson.java`. `import java.lang.foreign.*` keeps the example concise in Java 22+. The runtime names `msvcrt.dll`/`libc.so.6`/`libSystem.B.dylib` are **illustrative for common platforms**, not a substitute for checking the real installation.

### 8.2. Build/run for your version

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED \
  -cp out LibraryArenaLesson
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

**Windows CMD** (if `out` does not exist yet):

~~~bat
mkdir out
javac --release 22 -d out LibraryArenaLesson.java
java --enable-native-access=ALL-UNNAMED -cp out LibraryArenaLesson
~~~

With JDK 22+ where FFM is finalized, **`--enable-preview` is not needed**. Neither `javac -h` nor `jni.h` is needed, because the code uses **SymbolLookup/Linker** rather than creating a JNI native method.

### 8.3. Verified stdout

~~~text
symbolBytes=0
libraryAlive=true
abs(-7)=7
strlen=7
afterCallArenaAbs=42
symbolAliveAfterClose=false
RESULT: PASS
~~~

This output was actually run on **JDK 24, Windows x64**, compiled with `javac --release 22` and run with `--enable-native-access=ALL-UNNAMED`.

The lines illustrate **each distinct lifetime**:
- `symbolBytes=0`: the function address is a **zero-length segment**; do not read it as a buffer.
- `libraryAlive=true`: the library is still in the FFM scope owned by `libraryArena`.
- `abs(-7)=7`: the linker uses the C runtime ABI, calling the function while the library is alive.
- `strlen=7`: `callArena`'s buffer holds `"library"` consisting of seven ASCII bytes before NUL and lives through the synchronous `strlen` call.
- `afterCallArenaAbs=42`: closing the input arena does not affect the library scope.
- `symbolAliveAfterClose=false`: the function address's scope has expired after `libraryArena.close()`. **Do not try calling abs after this line**.
- `RESULT: PASS`: assertions and scope checks passed.

If the platform cannot find libc by name, `IllegalArgumentException` will be thrown at `libraryLookup`; if the library name is right but does not export `abs`/`strlen`, `orElseThrow` produces a specific `IllegalStateException`. Do not fix it by fabricating an arbitrary raw function address; choose the right native runtime library/path for your environment or use the custom library example in a later section.

## 9. Why choose a separate callArena? Timeline analysis

A synchronous `strlen` call has this lifecycle:

~~~text
t0   libraryArena opens, lookup("strlen"), create MethodHandle strlen
t1   callArena opens, allocate C string ("library\0")
t2   Java calls strlen(cstr), C reads buffer while callArena is alive
t3   strlen returns long/int per ABI, Java gets value 7
t4   callArena.close() -> cstr becomes invalid
t5   Java calls abs(-42) using another symbol in libraryArena
t6   libraryArena.close() -> symbol scope becomes invalid
t7   Do not use any function address/handle belonging to the closed owner
~~~

If the C API stores the pointer for **asynchronous use**, step t4 **is no longer valid** just because the Java method returned. In that case, you need a **session arena** longer than the call arena, a callback/unregister API, or a mechanism confirming native code is no longer using the buffer before closing.

### Not just one Arena for "everything"

Sometimes a single arena is used for both library and buffers to keep code short:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lib = SymbolLookup.libraryLookup(name, arena);
    MemorySegment input = arena.allocateFrom("example");
    // Call synchronous native function, then close everything.
}
~~~

This pattern is valid if **all resources truly share the same lifetime**. However, if a service loads the library once and handles millions of requests, you should not keep every input buffer in the library arena until server shutdown: doing so retains each call's memory for too long. Separate the **binding owner** and the **request buffer owner**.

### Do not close the library inside a helper that returns a handle

~~~java
// WRONG lifetime: do not write a helper like this.
static MethodHandle badHandle() {
    try (Arena arena = Arena.ofConfined()) {
        var lookup = SymbolLookup.libraryLookup("myLibrary", arena);
        var symbol = lookup.find("my_function").orElseThrow();
        return Linker.nativeLinker().downcallHandle(
                symbol, someKnownDescriptor);
    } // Arena closes BEFORE the caller uses the handle.
}
~~~

`someKnownDescriptor` in the fragment merely represents a descriptor that must be defined from the C header. The bug is not in Java syntax but in API design: the helper returns a **handle outliving its owner's lifetime**. Fix it by returning a **binding owner object** holding `Arena`, `MethodHandle`, and `close()`, and only allowing calls through the owner while it is still OPEN. Full example below.

## 10. Program 2: using `Arena.ofShared()` with a library-closing gate

A library can be shared by multiple Java threads. If you create `libraryArena = Arena.ofConfined()` in the main thread and hand a `MethodHandle` with a confined-scoped symbol to workers, calling it from other threads **is not the right choice**. `Arena.ofShared()` allows the segment scope to be used across multiple threads, but needs a **gate** to ensure the arena is not closed while a downcall is still running.

The program uses `ReentrantReadWriteLock`:
- Each `absolute(int)` holds the **read lock** throughout the native downcall.
- `close()` acquires the **write lock**, thus waiting for all read locks to be released before closing.
- `closed` is checked **under the same gate**, not merely via a boolean read outside the lock.
- After close, subsequent calls receive `IllegalStateException` **from the Java wrapper**, without attempting to execute a stale native handle.
- The closable arena is kept **inside the owner**; callers do not receive the raw address/`MethodHandle` outside.

### 10.1. Complete file `SharedLibraryLesson.java`

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.util.Locale;
import java.util.concurrent.*;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class SharedLibraryLesson {
    private static String nativeLibraryName() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        if (os.contains("win")) return "msvcrt.dll";
        if (os.contains("mac")) return "libSystem.B.dylib";
        if (os.contains("linux")) return "libc.so.6";
        throw new UnsupportedOperationException(os);
    }

    static final class LibrarySession implements AutoCloseable {
        private final Arena libraryArena;
        private final MethodHandle absolute;
        private final ReentrantReadWriteLock lifecycle =
                new ReentrantReadWriteLock();
        private boolean closed;

        LibrarySession(String name) {
            Arena fresh = Arena.ofShared();
            try {
                SymbolLookup library =
                        SymbolLookup.libraryLookup(name, fresh);
                MemorySegment symbol =
                        library.find("abs").orElseThrow();

                this.absolute =
                        Linker.nativeLinker().downcallHandle(
                                symbol,
                                FunctionDescriptor.of(
                                        ValueLayout.JAVA_INT,
                                        ValueLayout.JAVA_INT));
                this.libraryArena = fresh;
            } catch (RuntimeException | Error ex) {
                fresh.close(); // Cleanup when init fails.
                throw ex;
            }
        }

        int absolute(int value) {
            lifecycle.readLock().lock();
            try {
                if (closed) {
                    throw new IllegalStateException("library closed");
                }
                try {
                    return (int) absolute.invokeExact(value);
                } catch (Throwable failure) {
                    throw new IllegalStateException(
                            "foreign call failed", failure);
                }
            } finally {
                lifecycle.readLock().unlock();
            }
        }

        boolean scopeAlive() {
            lifecycle.readLock().lock();
            try {
                return libraryArena.scope().isAlive();
            } finally {
                lifecycle.readLock().unlock();
            }
        }

        @Override
        public void close() {
            lifecycle.writeLock().lock();
            try {
                if (!closed) {
                    libraryArena.close();
                    closed = true;
                }
            } finally {
                lifecycle.writeLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        LibrarySession owner =
                new LibrarySession(nativeLibraryName());
        try {
            ExecutorService workers = Executors.newFixedThreadPool(2);
            try {
                Future<Integer> first =
                        workers.submit(() -> owner.absolute(-7));
                Future<Integer> second =
                        workers.submit(() -> owner.absolute(-42));

                int a = first.get();
                int b = second.get();
                if (a != 7 || b != 42) {
                    throw new AssertionError();
                }
                System.out.println("parallelAbs=" + a + "," + b);
            } finally {
                workers.shutdown();
                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "workers not finished");
                }
            }
            System.out.println("libraryAliveBeforeClose="
                    + owner.scopeAlive());
        } finally {
            owner.close();
        }

        System.out.println("libraryAliveAfterClose="
                + owner.scopeAlive());
        try {
            owner.absolute(-9);
            throw new AssertionError(
                    "closed owner accepted a call");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "callAfterClose=IllegalStateException");
        }
        System.out.println("RESULT: PASS");
    }
}
~~~

This is a **separate file** from the previous program; do not copy two `public class` definitions into the same file. `LibrarySession` is the owner of the library and handle; callers only use `absolute(...)` and `close()`. The `nativeLibraryName()` helper uses the OS runtime name for the demo and must be replaced when deploying with another custom library.

### 10.2. Build commands and stdout

~~~sh
mkdir -p out
javac --release 22 -d out SharedLibraryLesson.java
java --enable-native-access=ALL-UNNAMED \
  -cp out SharedLibraryLesson
~~~

On Windows PowerShell, replace `mkdir` with `New-Item -ItemType Directory -Force out | Out-Null` if you want the script not to complain when the directory already exists; the `javac/java` commands remain unchanged.

Verified output:

~~~text
parallelAbs=7,42
libraryAliveBeforeClose=true
libraryAliveAfterClose=false
callAfterClose=IllegalStateException
RESULT: PASS
~~~

**Why is the output deterministic?** The two workers can execute in different orders, but Java collects results using `Future.get()` on `first` and `second`, then prints in a deterministic order. The native `abs` function does not depend on mutable session state, and both downcalls are permitted to run on the shared-scope symbol.

### 10.3. Analyzing the gate in the code

~~~text
Thread worker A                       Thread worker B
   readLock                                readLock
   check closed=false                     check closed=false
   native abs(-7)                         native abs(-42)
   readUnlock                              readUnlock
        \                                   /
         \                                 /
          Owner close: writeLock waits until
          NO readLocks are held
              |
              v
         libraryArena.close()
         closed=true
              |
         unlock writeLock
              |
         new absolute(...):
         readLock, sees closed=true -> Java IllegalStateException
         NO downcall to stale function address
~~~

This is the principle of **preventing close vs. in-flight calls**. If there were only a `volatile boolean closed` without a gate, one thread could check `closed == false` and get preempted, another thread could close the arena, and then the first thread would call native using an expired handle. Checking a flag before calling **is not enough** if you do not prevent shutdown from interleaving.

### Limitations of the multi-threaded example

- `ReentrantReadWriteLock` only protects the owner's lifecycle and **does not make an inherently non-thread-safe native C library thread-safe**. If the C API has global mutable state, add synchronization according to the C API contract.
- Do not call `owner.close()` **from a callback/call path that is already holding the read lock** in an attempt to upgrade read → write lock: `ReentrantReadWriteLock` does not support safe lock upgrading and can self-deadlock. Request close from a coordinator thread after callbacks finish.
- The code simulates two short-lived futures that complete before close. In a real server, manage **shutdown / request admission / timeout / interrupt / executor drain**; do not close if a foreign call may still be running on the native side.
- `close()` is designed to be **idempotent at the wrapper** via the `closed` check, because **`Arena.close()` itself is not idempotent**: calling it again on an already-closed arena throws an exception.
- If `Arena.close()` throws an exception because a resource is currently accessed or cleanup fails, the wrapper must not claim it closed successfully. Production code needs an error policy and a dedicated failure state to avoid leaving the owner in an unknown state; the demo only illustrates the normal path.

## 11. `Arena.close()` and race risks: do not just catch an exception to "retry"

The Javadoc for `Arena.close()` states it can:
- throw `WrongThreadException` if a confined arena is closed by a non-owner thread;
- throw `IllegalStateException` if the arena is already closed;
- throw `IllegalStateException` in some cases when a segment is being accessed concurrently, such as during a downcall;
- throw `UnsupportedOperationException` if the arena does not support explicit close (auto/global);
- throw an error from a cleanup action registered by a custom/native resource attached to the arena.

Some people design:

~~~java
// WRONG shutdown protocol.
try {
    libraryArena.close();
} catch (IllegalStateException ignored) {
    // "a call is running, try again later" but does not block new calls!
}
~~~

This snippet creates no **barrier** preventing new downcalls. Even if you retry shortly after, other threads can still start new calls, causing starvation or an unload race. Design an admission gate first:
1. Mark `CLOSING` and reject new requests.
2. Wait for all in-flight Java/native calls and callbacks to reach a safe point.
3. Only when nobody is using the symbols anymore, close the library arena.
4. Mark `CLOSED` after cleanup succeeds.

Do not put `close()` in a destructor/GC callback as the sole way to satisfy a requirement to "unload immediately when the session ends". With `Arena.ofAuto()`, there is no deadline for when GC runs; with `Arena.global()`, the scope never closes on its own.

### State machine example

~~~text
           construct + load + lookup success
                         |
                         v
                       OPEN
                   /           \
         begin call             request close
             |                      |
        inFlight++              CLOSING
             |                reject new calls
        execute native               |
             |                  inFlight > 0?
        inFlight--                 /     \
                                yes      no
                                |         |
                              wait   arena.close()
                                            |
                                            v
                                          CLOSED
~~~

In multithreading, consistency must be maintained between `OPEN/CLOSING` and the counter/`inFlight`. A **read-write lifecycle lock** like in the demo simplifies this, but if a foreign call triggers a reentrant callback or requests close inside the callback itself, you must evaluate deadlock/lock-order or design a separate shutdown queue.

## 12. Production protocol for a session: who creates, who borrows, who destroys?

To avoid *use-after-unload*, every object in the binding must have a role:

| Resource | Owner | "Borrower" | End of usage right |
|---|---|---|---|
| `Arena libraryArena` | `LibrarySession/Binding` | Methods calling native, through gate | After in-flight calls/callbacks stop |
| `SymbolLookup library` | Binding | Symbol-resolving code | Not used outside `libraryArena` scope |
| `MemorySegment symbol` | Lookup/arena | `Linker` or downcall handle | Ends when `libraryArena` scope closes |
| `MethodHandle` bound to symbol | Binding | Callers through binding's API | Do not invoke after owner close |
| `Arena callArena` | Each call/request | Synchronous native function | After C is no longer using the buffer |
| `MemorySegment input/output` | Call/session arena | Native function taking pointer | Not after close/async use |
| `upcallStub` pointer (if any) | Callback/session arena | Native library registering callback | Unregister + wait for last callback before arena close |

A good pattern: **do not expose raw addresses/handles** from the public API. Use business-level methods like `binding.calculate(a,b)`, where the owner can:
- check that it is still OPEN;
- hold a lease/read lock throughout the call;
- allocate input buffers in the call arena;
- invoke the method handle;
- check native results/errors;
- release buffers and the lease;
- allow close only when no leases remain.

### Failure-atomic constructor

Loading the library may succeed and then `find("symbol")` fails, or `downcallHandle` reports an unsupported descriptor. If the constructor does not clean up the newly created arena, you can leave an unintended library load behind. Therefore, in the multi-threaded example's constructor:

~~~java
Arena fresh = Arena.ofShared();
try {
    SymbolLookup library = SymbolLookup.libraryLookup(name, fresh);
    // Find symbol, create descriptor, linker/downcall handle.
    // On success, transfer ownership to the libraryArena field.
} catch (RuntimeException | Error ex) {
    fresh.close(); // Cleanup if init is incomplete.
    throw ex;
}
~~~

This is a fragment showing the idea; the full program in section 10 implements it properly. If more complex handling is needed, guard exceptions thrown during cleanup as well and preserve the original exception via `addSuppressed`. Do not leave a new resource behind just because part of initialization failed.

### Do not reuse a closed owner

If you want to reload a plugin:

~~~text
Owner #1 OPEN -> CLOSING -> CLOSED
        |
        +-- symbols/handles belonging to Owner #1: no longer valid
Owner #2 NEW -> OPEN
        |
        +-- NEW lookup/symbols/handles belonging to Owner #2
~~~

Do not "resurrect" an old Java `MethodHandle` by creating a new arena, even for a library with the same name. Code addresses can change across unload/reload. All callers of the old owner must be prevented from making further calls, and the reload API should issue **a new binding instance**.

## 13. Application's custom library: using `libraryLookup(Path, Arena)`

The main lesson uses the OS C runtime so no C compiler is required. When you need to package your own library, know the **Path overload**. The example below provides a C symbol `ffi_square` and platform-specific build commands. This is an **additional exercise**; this Java/C part was not run on every toolchain in the main verification session, so build and check the exported symbol yourself.

### 13.1. Native file `native/ffm_arena.c`

~~~c
#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

/* Simple example, call only with small values to avoid int overflow. */
FFM_EXPORT int ffi_square(int x) {
    return x * x;
}
~~~

This is an **ordinary C ABI symbol**: no `JNIEnv *` or JNI method name. The compiler needs to export a symbol with the exact name `ffi_square`.

**Linux**:

~~~sh
mkdir -p native
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libffm_arena.so native/ffm_arena.c
~~~

**macOS**:

~~~sh
mkdir -p native
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libffm_arena.dylib native/ffm_arena.c
~~~

**Windows MSVC Developer Command Prompt**:

~~~bat
mkdir native
cl /nologo /W4 /LD native\ffm_arena.c /Fe:ffm_arena.dll
~~~

Create the source `native/ffm_arena.c` before building; `mkdir native` is only needed if the directory does not exist yet. The native binary and the JVM must have the same CPU architecture. Check exports with `nm -D --defined-only` (Linux), `nm -gU` (macOS), or `dumpbin /EXPORTS` (Windows). On some 32-bit Windows ABIs, symbol names may be decorated and require adjusting the export convention/lookup.

### 13.2. Java calling the exact symbol and keeping the library arena alive

Create `CustomLibraryArenaDemo.java`:

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class CustomLibraryArenaDemo {
    public static void main(String[] args) throws Throwable {
        // JVM maps logical name to .so/.dylib/.dll per OS.
        String filename = System.mapLibraryName("ffm_arena");
        Path libraryPath = Path.of(filename).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            SymbolLookup lookup = SymbolLookup.libraryLookup(
                    libraryPath, libraryArena);
            MemorySegment function = lookup.find("ffi_square")
                    .orElseThrow(() -> new IllegalStateException(
                            "ffi_square not found"));

            Linker linker = Linker.nativeLinker();
            FunctionDescriptor desc = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

            MethodHandle square =
                    linker.downcallHandle(function, desc);

            int answer = (int) square.invokeExact(6);
            System.out.println("square(6)=" + answer);
            if (answer != 36) {
                throw new AssertionError("wrong C result");
            }
        } // Close library owner here, after the last downcall.

        System.out.println("RESULT: PASS");
    }
}
~~~

Run **in the directory containing the native binary** (and Java source):

~~~sh
javac --release 22 CustomLibraryArenaDemo.java
java --enable-native-access=ALL-UNNAMED CustomLibraryArenaDemo
~~~

Expected when the C binary is right:

~~~text
square(6)=36
RESULT: PASS
~~~

`libraryLookup(Path, Arena)` loads the library by file `Path` for the current JVM; this differs from `System.loadLibrary` via the JNI loader. This Java source does not need `javac -h` or JNI C headers. To use from multiple request threads, replace `Arena.ofConfined` with an `Arena.ofShared` owner plus a gate equivalent to example 2; **do not just change one arena keyword and consider the lifecycle finished**.

## 14. Libraries, symbols, and callbacks: lifetime dependencies can cause deadlocks

A native library can store a function pointer to call back into Java using `Linker.upcallStub`. In that case:

~~~text
Library owner arena ----- function code of C library
        |
        +-- C callback registry holds upcall function pointer
                      |
                      v
Callback arena ------ upcallStub -> Java MethodHandle target
        |
        +-- must remain alive while callback is being invoked by native
~~~

During shutdown:
1. **Block new callback registrations** and new downcalls.
2. **Unregister the callback** from the native library, while the library is still live to call the unregister function.
3. **Wait for in-flight callbacks/native work to complete**.
4. Close callback/session arenas and call buffers that are no longer used.
5. Only when there are no more function calls into the library, **close the library owner arena**.

If you close the library arena before calling the native unregister API, you have lost the code needed for the shutdown process. If you close the callback arena while C still holds the upcall pointer, C may call an expired pointer, causing a crash.

**Deadlocks can also occur:** one thread holds the write lock requesting to close the binding and waits for a callback, while the callback tries to acquire the read lock of the same binding to finish. You must design *quiescing* and lock ordering. Do not hold the write lock across a blocking native unregister function if the callback itself needs that read lock; you may need to transition to `CLOSING` state, release the lock, wait for activity to end, and then close when quiescent. The `ReentrantReadWriteLock` example in this lesson only applies to short downcalls **without reentrant callbacks**.

## 15. Mistakes that easily cause hard-to-find bugs

| Mistake | Consequence | Fix |
|---|---|---|
| Creating `libraryLookup` with try-with-resources in a helper, returning `MethodHandle` | MethodHandle outlives owner scope, risk of use-after-unload | Return an `AutoCloseable` owner holding arena/handle and gating calls |
| Using `Arena.ofConfined` and calling the handle from a worker pool | Wrong thread access, possible `WrongThreadException` | Use `ofShared` and a gate if cross-thread access is needed |
| Using `Arena.ofShared` and closing while another request is calling native | Close/in-flight race, error or crash | Block new calls, wait for all calls/callbacks to finish, then close |
| Keeping input buffers in the same library arena for the entire service lifetime | Native memory grows unnecessarily | Separate `callArena` for synchronous buffers |
| Using `Arena.ofAuto` when immediate unload at `closeSession` is needed | No deadline for GC cleanup | Choose an explicit arena + close protocol |
| Using `Arena.global` for every plugin reload | No explicit unload; resources can accumulate | Use only for intentionally process-lifetime libraries |
| Calling the handle again after close to "see if it errors" | Use-after-unload can crash the JVM | Only check `scope().isAlive()` or owner state, **do not call native** |
| Casting a size=0 symbol address into an arbitrary readable data segment | Wrong bounds/ABI/lifetime access | Function symbols are for linker; global data needs a size contract |
| Looking up a symbol in `loaderLookup` even though loaded via `libraryLookup` | Not found, different loader semantics | Keep the lookup from the right source and its arena |
| Assuming `defaultLookup` has every symbol installed on the machine | `Optional.empty` | Use explicit native library lookup/path |
| Omitting `--enable-native-access` | Warning or `IllegalCallerException` depending on JDK version | Grant permission to the right module |
| Guessing Java `long` for C `long`/`size_t` | ABI mismatch on other OSes | Use `linker.canonicalLayouts()` and C headers |
| Catching every `Throwable` from a native call and continuing to call | Hides corruption/native errors | Apply an error policy; a C crash is not a normal Java exception |
| Closing an arena twice without owner state | `Arena.close()` is not idempotent | Wrapper with flag/state, idempotent public close when contract requires |

### Do not store `MemorySegment.address()` in a long-term cache

A function address can be printed as a `long`, but that raw number **carries no scope** once converted to a number. Converting a handle/address to an integer does not extend the DLL/SO lifetime. After unload/reload, the new symbol may be at a different location, and using the old raw address bypasses FFM's safeguards.

### Do not call `close` during a pending downcall/callback

Some Java resources have explicit cleanup, yet a native function may still be using a buffer pointer or callback pointer. `Arena.close()` reporting concurrent access **does not mean native code has stopped**, and seeing no error **is not** proof that all C threads have stopped either. Have native-level acknowledgements/joins when needed.

## 16. Diagnosing in order

### A. Java does not compile

- `package java.lang.foreign does not exist`: using a JDK below 22 or a different compile target; use JDK 22+ for finalized source.
- `cannot find symbol libraryLookup`: mixing FFM incubator/preview APIs, or source/Javadoc from another release. Check `java -version` and `javac -version`.
- `WrongMethodTypeException` on `invokeExact`: method handle carrier/argument types do not match the Java call site, inspect `handle.type()`; specifically `strlen` uses `invokeWithArguments` and `Number.longValue()` to avoid hardcoding the `size_t` Java carrier across all pointer widths.

### B. Library loading fails

- `IllegalArgumentException` at `SymbolLookup.libraryLookup(name, arena)`: invalid library name / OS loader cannot find the file or its dependencies cannot be loaded. Use the exact name on the OS, or `libraryLookup(Path, Arena)` with an explicit file.
- Loads fine but `find("foo")` is empty: symbol is not exported / has a different name, C++ name mangling / calling convention, or wrong binary version. Check `nm`/`dumpbin`, C headers, and linker export tables.
- `UnsatisfiedLinkError` in JNI `System.loadLibrary` is a **different** loading path; it does not mean FFM library lookup uses the Java library path the exact same way as JNI.

### C. Native access and ABI errors

- `IllegalCallerException`: caller/module is not permitted to call restricted `libraryLookup`/`downcallHandle`; pass `--enable-native-access=ALL-UNNAMED` for classpath or the actual module name.
- Native code crashes or produces garbage data: `FunctionDescriptor` does not match the C header (carrier, pointer, return, packing, varargs); always check OS/arch/ABI first.
- `WrongThreadException`: library lookup address bound to a confined arena was accessed from another thread, or a confined arena was closed from the wrong thread.
- `IllegalStateException` on close: arena is already closed, or there is concurrent access. Stop/admit gate, wait for in-flight work, log the error; do not retry infinitely.

### D. Observing lifetime safely

Reasonable checks:

~~~java
boolean scopeAlive = libraryArena.scope().isAlive();
boolean symbolAlive = functionAddress.scope().isAlive();
int symbolBytes = (int) functionAddress.byteSize(); // usually 0.
~~~

When the scope expires, only observe status/owner state; **do not invoke a downcall** as a "test". Do not infer actual OS unload from the fact that the PID still has a DLL/SO mapped, because the loader may still hold other references.

### E. Bugs that only appear under multi-threaded load

If the single-threaded demo PASSES but production crashes at shutdown:
- Who closes the arena? Was it closed before the worker pool drained?
- Are native threads holding C pointers beyond Java method return?
- Are callbacks currently running or about to be triggered by native code?
- Did the owner return `MethodHandle`/`MemorySegment` outside the gate, allowing uncontrolled code to call when CLOSED?
- Is there a deadlock where close waits for a callback and the callback waits for the owner's lock?
- Does the library have non-thread-safe global state even though the Java gate allows multiple read locks?
- Distinguish scope/lifetime errors from ABI or C allocator errors.

## 17. Testing strategy for a library with unload/reload

A practical test suite includes:
1. **Load the right library**: `libraryLookup` by confirmed name/path; `find` required symbols.
2. **Downcall within scope**: ABI-correct descriptor; simple function `abs(-7)=7` or custom `ffi_square(6)=36`.
3. **Input arena shorter than library arena**: close call arena, continue another downcall with the library still alive.
4. **Scope after close**: `symbol.scope().isAlive()==false`; **do not invoke stale handle**.
5. **Multi-threaded calls**: `ofShared` owner, run futures and ensure all complete before close.
6. **Post-close rejection**: calling the wrapper API throws `IllegalStateException` **before the native call**, via owner state/gate.
7. **Initialization failures**: missing library/symbol; arena is closed when constructor fails.
8. **Shutdown contention**: stress tests where thread A is calling, thread B requests close, thread C starts a new call; no path calls after CLOSED.
9. **Callback contracts**: if C has callbacks, unregister and let in-flight callbacks quiesce before close.
10. **Cross-OS builds**: verify Windows/Linux/macOS file names, exports, dependencies, ABI, and native loader behavior.

A test that asserts **the native library was physically unloaded** by calling a stale function pointer is **unsafe**. If you need to investigate physical unload at the OS level, use a profiler/native loader events in an isolated environment; do not turn it into a crash-based unit test.

## 18. Self-check questions

**Question 1.** Why does `MemorySegment symbol` from `lookup.find("abs")` have `byteSize()==0` yet still allow calling the function?  
**Answer:** It represents a **function address**, not a data buffer. The linker uses that address together with `FunctionDescriptor` to create a downcall handle. Do not call `get(JAVA_INT,0)` to read "function contents".

**Question 2.** `MethodHandle abs` is cached in a singleton; the library arena is closed. Can it still be called because the singleton is alive?  
**Answer:** No. Java reachability of the handle does not extend the library scope contract. Calls must be blocked and a new binding created on reload.

**Question 3.** Is `Arena.ofConfined()` suitable for a binding called concurrently by 8 threads?  
**Answer:** Not a suitable choice. Confined scope is tied to the owner thread. Use `ofShared()` and an admission/close protocol; check whether the native function itself is thread-safe.

**Question 4.** Why not use `Arena.global()` to avoid all use-after-close bugs?  
**Answer:** It avoids explicit close but creates a virtually infinite lifetime, unsuitable for plugins/sessions that need to release native resources on time and can cause resource retention.

**Question 5.** Is it valid to close `callArena` after `strlen` and then call `abs` next?  
**Answer:** Yes, because synchronous `strlen` has stopped using the C string, and `abs` only uses the library symbol still alive in its separate `libraryArena`.

**Question 6.** Does `SymbolLookup.loaderLookup()` see every symbol from `libraryLookup(path,arena)`?  
**Answer:** No. Loader lookup focuses on native libraries loaded via the caller class loader's JNI loading APIs. Keep the right library lookup for this binding.

**Question 7.** Closing a shared arena can throw `IllegalStateException` during an active downcall, so is catching and retrying enough?  
**Answer:** No. You must **block new downcalls**, wait for current calls/callbacks to finish, and only then close. Catching an exception does not replace an ownership protocol.

**Question 8.** Does `SymbolLookup.libraryLookup("mylib", Arena.ofAuto())` guarantee unload at `closeSession`?  
**Answer:** No. An auto arena relies on GC/reachability; there is no deterministic cleanup deadline or explicit close. An `ofConfined`/`ofShared` owner is needed when there is a close contract.

**Question 9.** If the library is already held elsewhere by the JVM or OS, does `libraryArena.close()` always remove the file from the process?  
**Answer:** Cannot be guaranteed. The lookup's scope has expired; actual unload depends on the loader/reference counting and other owners. You must not continue using the old function address.

**Question 10.** When a native API registers an upcall stub and invokes the callback later, which arena is closed first?  
**Answer:** After **unregistering** and waiting for in-flight callbacks to finish, the callback/session arena can be closed; the library arena must remain alive while using the native unregister API and any final calls, and only then be closed.

## 19. Checklist before merging an FFM binding with a custom library

- [ ] Use the right **JDK 22+ finalized** FFM version; native access enabled for module/classpath if needed.
- [ ] Verify exact library file/name, platform, CPU arch, and C ABI.
- [ ] `SymbolLookup.libraryLookup(name/path, arena)` has a clear owner; arena does not close prematurely.
- [ ] `MemorySegment` representing a symbol address is used as a function pointer, not confused with a readable buffer.
- [ ] `FunctionDescriptor` matches the native C function signature; `MethodHandle` has the right Java method type.
- [ ] Choose `ofConfined` if all calls/close come from one thread, `ofShared` if multiple threads; do not treat shared as synchronization.
- [ ] `Arena.ofAuto/global` used only when lifetime needs no explicit close or is process-long by contract.
- [ ] Have a **binding owner** holding arena, symbols/handles, and `close`; do not expose raw handles to be called outside the gate.
- [ ] Separate `callArena`/session buffer arenas if lifetimes differ from the library; manage pointers held asynchronously by C.
- [ ] Shutdown blocks new calls, waits for in-flight downcalls/upcalls/unregister, and only then closes the library arena.
- [ ] If callbacks exist, avoid deadlock between shutdown's write lock and callbacks needing the read lock.
- [ ] Never call a stale method handle or dereference a stale symbol after close, even in tests.
- [ ] Verify `scope().isAlive()` and owner state; public API rejects calls after close **before the native call**.
- [ ] Clean up the arena on partial initialization failure, do not hold the library indefinitely.
- [ ] Ensure wrapper close is idempotent if the API contract requires it; remember `Arena.close()` itself is not idempotent.
- [ ] Test on real OS/ABI; do not infer from one Windows PASS that all Linux/macOS symbols are identical.

## 20. Summary and official references

An easy-to-remember formula:

~~~text
libraryArena     -> holds permission to use the library
libraryLookup    -> finds symbol addresses belonging to libraryArena
symbol address   -> zero-length MemorySegment, with scope
FunctionDescriptor + Linker -> downcall MethodHandle
callArena        -> allocates native bytes for each call
close libraryArena -> do not call that owner's symbols/handles again
~~~

**The right Arena decision is not just choosing `ofConfined` or `ofShared`: it is designing who opens the library, who is allowed to call, who waits for calls to finish, and who closes last.** When you separate library lifetime from input-buffer lifetime, manage symbols as scoped resources rather than permanent raw pointers, and have a clear shutdown gate, FFM applications become much easier to reason about.

Official documentation:

- [OpenJDK JEP 454 – Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)
- [Java SE 22 – SymbolLookup: libraryLookup, loaderLookup, default lookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 – Arena: arena types, scope, close, and thread confinement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 – Linker: downcall method handle and native ABI](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 22 – MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [Java SE 22 – FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)

For newer JDK versions, check the Javadoc of the **target JDK** to verify native-access restrictions, as policies may evolve even though the ownership model stays the same. Do not test use-after-unload by deliberately crashing the JVM: the owner API design should **prevent** that dangerous action before the native call ever happens.