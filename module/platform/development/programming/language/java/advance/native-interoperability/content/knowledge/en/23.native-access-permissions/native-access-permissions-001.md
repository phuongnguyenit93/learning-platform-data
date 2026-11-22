# Restricted Methods and Why Explicit Native Access Permission Is Required

In Java, APIs that allow running code outside the JVM can **break the safety guarantees of the Java platform** even though the call itself originates from a valid `.java` file. The Foreign Function & Memory API (FFM) since **JDK 22** marks certain methods as **restricted methods**: they are still public APIs, but they can load native libraries, create function pointers, misassign C ABI signatures, or expand a `MemorySegment` to bytes that the JVM cannot prove are valid. If used incorrectly, the result is not just a Java exception; native code can cause a **JVM crash or silent memory corruption**.

So that the application deployer truly knows and **consents to crossing outside the JVM's safety boundary**, Java provides a **native-access permission mechanism for modules**. For example, a program running on the classpath requires `--enable-native-access=ALL-UNNAMED`; a named module `com.example.bridge` can be granted access individually with `--enable-native-access=com.example.bridge`. This is a **runtime decision**, not just an import line or an annotation in source code.

Starting in **JDK 24**, JEP 472 extends this policy to unify **JNI load/bind** operations with FFM: a program without granted permission may receive a warning by default; the `--illegal-native-access=deny` mode causes violating operations to throw `IllegalCallerException`. The default mode may become stricter in future JDKs; do not write code that relies on warnings always being sufficient.

This article belongs to the **Native access permissions** group, progressing from the meaning of "restricted", the specific list of methods, differences between JDK 22–23 and 24+, how to grant permission for classpath/named modules, a **runnable Java 22+ + C11** example performing `libraryLookup`, `downcallHandle`, `upcallStub`, and `reinterpret`, to diagnosing policy errors, operations, and principles for protecting the native boundary.

## 1. What Does “Restricted” Mean and What Does It Not Mean?

A **restricted** method can be called using valid Java source code and typically has an official return type, parameter types, and Javadoc. However, the nature of its work can **go beyond what the JVM can verify on its own**. The JVM requires **the module containing the calling code** to be granted native access permission if it wants to use that method without violating policy.

~~~text
Java code (module M)
       |
       | calls Linker.downcallHandle, libraryLookup,
       | reinterpret, or another restricted API
       v
Does JVM check that M has native access permission?
       |
       +--- YES --> continue operation
       |             (still must ensure ABI/bounds/ownership yourself)
       |
       +--- NO  --> "illegal native access"
                    |-- warn: warn and continue
                    |-- deny: IllegalCallerException
                    |-- allow: continue without warning
                    (mode availability depends on JDK version)
~~~

**Restricted does not mean deprecated.** For example, `Linker.downcallHandle` is an official part of standard FFM in JDK 22, not an API scheduled for removal; it is restricted because the linker **cannot prove** that the `FunctionDescriptor` you describe matches the C code at a native address.

**Restricted does not mean every FFM API is restricted.** You can create a `MemoryLayout`, use an `Arena` to allocate bounded memory, and perform `MemorySegment.get/set` within a valid scope without necessarily needing native access permission. When calling dangerous points such as creating a downcall handle or using `reinterpret` to expand a memory region, native access permission becomes a policy requirement.

**Permission does not make native code safe.** Once `--enable-native-access` is granted, the JVM **allows** crossing the boundary; it **does not verify** the correct ABI, buffer size, lifetime, thread safety, or whether the C library is trustworthy. Native code can still crash the process or affect data in the same process.

### 1.1. Java's Safety Boundary and Platform Integrity

Java normally performs bytecode verification, array bounds checking, memory type safety, reference/lifetime management, and many runtime checks. Native code is loaded into the **same JVM process**, can read/write memory through pointers, call OS APIs, run library initializers, or introduce asynchronous threads/callbacks. When a function pointer or memory size is wrong, there is no JVM proof that prevents all consequences.

Therefore, the policy requires **making the choice "I consent to this code having native access" explicit**. It aids operations, auditing, and discovering unreviewed dependencies; it is not a security sandbox to isolate a native library from JVM data. To isolate processes or defend against malicious binaries, other isolation mechanisms such as process boundaries, OS permissions, or appropriate sandboxes are required.

## 2. Which FFM Methods Are Marked Restricted?

Table according to Oracle JDK 22/24/25 documentation:

| API | Why is it restricted? | Design mistakes to avoid |
| --- | --- | --- |
| `SymbolLookup.libraryLookup(String, Arena)` and `libraryLookup(Path, Arena)` | Loading a native library can trigger initializers and execute code immediately upon loading, such as dynamic loader hooks | Loading files from untrusted paths; not controlling dependencies and ABI |
| `Linker.downcallHandle(...)` (both symbol-binding and descriptor-only forms) | The linker does not know the actual C signature of the symbol address and cannot prove the descriptor matches the ABI | Wrong return type, argument count, alignment, or variadic convention |
| `Linker.upcallStub(MethodHandle, FunctionDescriptor, Arena, ...)` | Cannot verify that the C callback function pointer will be invoked according to the declared descriptor | C storing the callback after the arena closes; wrong signature |
| `MemorySegment.reinterpret(long)` and overloads with `Arena`/cleanup | Creates an alias with **spatial/temporal bounds** asserted by the caller; can misstate size or lifetime | Reinterpreting 100 bytes when C only allocated 8 bytes, then dereferencing |
| `AddressLayout.withTargetLayout(MemoryLayout)` | Attaches a layout for the data region behind a pointer to dereference according to the size declared by the caller | Target layout larger than actual allocation, NULL/dangling pointer |
| `ModuleLayer.Controller.enableNativeAccess(Module)` | Allows conditionally propagating native-access permission to another module in a layer | Creating a mechanism that grants permission indiscriminately without verifying trusted modules |

This list may change between releases. Before deploying, check the **Javadoc for the exact JVM version**, as restricted behaviors/parameters evolved through incubator, preview, and finalization of FFM.

### 2.1. Why Is `libraryLookup` a Dangerous Action Even Before Calling Any C Function?

On many operating systems, **loading a shared library by itself can execute native code**: static constructors, dynamic-loader initialization, dependency loading, or hooks provided by the binary/OS. Therefore, a `.dll/.so/.dylib` file is not inert data. `SymbolLookup.libraryLookup(path,arena)` can cause side effects as soon as the lookup is created.

~~~java
// JDK 22+ snippet: only illustrates restricted load; does not include full imports.
SymbolLookup symbols =
        SymbolLookup.libraryLookup(pathToTrustedLibrary, arena);
~~~

Do not use **arbitrary user-supplied paths** as the library file to load. You must verify provenance, architecture, dependencies, trustworthy signatures/distribution, and check how the OS locates auxiliary shared libraries. The native access flag is not a digital signature verifying the file.

### 2.2. Why Is `downcallHandle` Restricted?

A C symbol `sum_i32` is usually just a **function address**, carrying insufficient metadata for the JVM to know that the actual C prototype is:

~~~c
#include <stdint.h>
int32_t sum_i32(int32_t a, int32_t b);
~~~

If Java declares the wrong descriptor such as `FunctionDescriptor.of(JAVA_LONG, ADDRESS)`, the linker cannot always determine the mismatch from the symbol. When invoking the handle, registers/stack may be read differently from the ABI, leading to undefined behavior. Even though `MethodHandle.invokeExact` checks the **Java carrier types against the descriptor**, it does not prove that the descriptor is the exact contract of the native function.

### 2.3. Why Is `upcallStub` Restricted?

`Linker.upcallStub` creates a C function pointer for C to call back into a Java `MethodHandle`. If C expects the pointer to have signature `int (*)(int)` but Java creates a stub describing `double (*)(double)`, the ABI mismatches. If C **stores the callback** and continues calling it after the `Arena` owning the stub has closed, native code may jump to an invalidated address.

Native access permission allows creating the stub; the author must still ensure the callback type, exception handling, thread model, unregister/stop, and lifetime.

### 2.4. Why Are `reinterpret`/`withTargetLayout` Restricted?

A returned C pointer usually has a `MemorySegment` representation of size 0 because the JVM **does not know the number of bytes underneath**. `reinterpret(1024)` creates a view claiming "1024 valid bytes", without asking the C allocator whether the actual allocation is large enough. Similarly, `ADDRESS.withTargetLayout(sequenceLayout(256,JAVA_INT))` relies on the assumption that the pointer points to 256 integers; if wrong, it can dereference out of bounds.

These APIs are in the public JDK, but the risk lies in the **caller-supplied assertion about C memory**. Only use them when there is a reliable contract for size, ownership, alignment, nullability, and lifetime.

## 3. Distinguishing Restricted From Normal FFM Operations

Practical table for JDK 22+:

| Operation | Is it restricted solely because of this operation? | Explanation |
| --- | --- | --- |
| `MemoryLayout.structLayout(...)`, `sequenceLayout(...)` | **No** | Creates data descriptions, does not execute native code |
| `ValueLayout.JAVA_INT`, `withOrder(...)` | **No** | Metadata about carrier, size, alignment, endianness |
| `Arena.ofConfined()` and `arena.allocate(...)` | **No** | Allocates memory with scope/size managed by Java |
| `MemorySegment.get/set(...)` within valid bounds | **No** | Checked for bounds/lifetime/thread on the Java side |
| `FileChannel.map(..., Arena)` | **Not in the FFM restricted list above** | File mapping still has I/O/backing-file risks, but is not native linking |
| `Linker.nativeLinker()` | Not in the JDK 22 restricted list | Obtains linker metadata/ABI, does not create a downcall handle yet |
| `Linker.canonicalLayouts()` | No | Looks up C ABI layouts, does not execute a foreign function |
| `SymbolLookup.libraryLookup(...)` | **Yes** | Loads a binary and may execute initialization code |
| `Linker.downcallHandle(...)` | **Yes** | Actual C prototype is unknown |
| `Linker.upcallStub(...)` | **Yes** | Creates a callback pointer outside the Java type system |
| `MemorySegment.reinterpret(...)` | **Yes** | Changes asserted bounds/scope |
| `AddressLayout.withTargetLayout(...)` | **Yes** | Allows dereferencing a pointer according to a caller-committed target size |

Not every `IllegalArgumentException` or `IndexOutOfBoundsException` in `MemorySegment.get/set` is a **native access permission** error. Separate **permission to call restricted APIs** from **data/scope correctness**. For example, using `JAVA_INT` at byte offset 1 on an aligned segment can cause an alignment exception even if the module has been granted all native permissions.

## 4. JDK Versions: What Changes?

| Version | FFM Status | Related Native-Access Policy |
| --- | --- | --- |
| Java 17 | FFM incubator `jdk.incubator.foreign` (JEP 412) | Does not use the final `java.lang.foreign` API; native access/options follow the incubator release, do not infer from JDK 22 |
| Java 19–21 | FFM preview (JEP 424/434/442) | Preview APIs/flags depend on the release, not fully identical to the final API |
| **Java 22–23** | FFM is **final** since JDK 22 (JEP 454) | Restricted FFM methods require permission; behavior when permission is missing differs depending on whether modules are listed via `--enable-native-access` |
| **Java 24** | FFM final; JNI under **JEP 472** brought into the same mechanism | Both **JNI load/bind** and restricted FFM are governed by `--enable-native-access`; `--illegal-native-access=allow/warn/deny` is available, default **warn** |
| Java 25 and later releases | FFM/JNI continue to be governed by native-access rules; check the current release | Per Oracle JDK 25, default is **warn**, `deny` is expected to become the default in a future release, without committing to an unannounced year/version |

**Important detail for JDK 22–23:** If no native-access grants are specified at all, a restricted FFM call can run and **warn**. If permission has been granted to some modules via `--enable-native-access=M1,...`, another unlisted module can receive an **`IllegalCallerException`** when calling a restricted API. JDK 24 changed the behavior to **unify** the warning/deny rules for JNI and FFM; therefore, do not take Java 22 warning results and assume Java 24 behaves identically.

**Do not say "JNI is removed" or "FFM must replace JNI".** JEP 472 does not deprecate JNI; it requires applications to **explicitly acknowledge** native permission when loading/linking code that can cross safety boundaries. JNI remains essential when native C needs `JNIEnv`, `jobject`, Java fields/methods, and class loaders.

### 4.1. `--illegal-native-access` Modes on JDK 24+

| Mode | When a module has not been granted native access | Purpose |
| --- | --- | --- |
| `allow` | Allows execution, no warning | Temporary compatibility; **not** a long-term solution |
| `warn` | Allows execution, warns on the first violation per module | **Default in JDK 24/25**, to identify code that needs permission |
| `deny` | Throws **`IllegalCallerException`** on each restricted/illegal access | Auditing before the default policy becomes stricter |

`--illegal-native-access` must not be used as an equivalent flag for older runtimes that do not support it. On JDK 24/25, you should test-run the application with **`--illegal-native-access=deny`** to uncover gaps; for production applications, **grant permission properly to the modules that actually need native access**.

When native access is missing, warnings are usually written to **stderr**, not stdout printed by the program. The count/order/wording of warnings depend on the JDK and code path. Do not assert the **exact wording** of warnings in unit tests; check the meaning and the reported module.

## 5. Permission Is Granted to a **Module**, Not to Individual C Functions

### 5.1. Classpath / Unnamed Module

A Java class compiled and run with:

~~~sh
javac -d build/classes src/NativeAccessDemo.java
java -cp build/classes NativeAccessDemo
~~~

belongs to an **unnamed module**. To grant restricted FFM methods permission to code on the classpath:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

`ALL-UNNAMED` is a special name applying to **all unnamed modules**, not a user-named module. This mode is convenient for demos/tests but grants relatively broad access: many libraries on the classpath gain the ability to call restricted operations. When an app grows larger, consider placing native bindings into a separate **named module** for narrower grants.

### 5.2. Named Module and the Principle of Least Privilege

Suppose module `com.example.nativebridge` contains the FFM calls. Run command on Java 22+:

~~~sh
java --module-path mods \
  --enable-native-access=com.example.nativebridge \
  --module com.example.nativebridge/com.example.nativebridge.Main
~~~

This is a **deployment command pattern**, not a command to directly run the source in the example section (the example source is in the default package on the classpath). It assumes you have built a named module with `module-info.java`, a main class, and files in `mods`. Do not run this command verbatim against the default `NativeAccessDemo.java`.

If module `com.example.app` only calls the Java API of `com.example.nativebridge`, while the **restricted calls actually reside in `com.example.nativebridge`**, you should grant permission to the **bridge module**, not necessarily the app module. Which module is checked depends on the **caller of the restricted operation**, not just the main class or the module containing business logic.

If both M1 and M2 directly need native access, the JVM flag is:

~~~sh
java --enable-native-access=com.example.nativebridge,com.vendor.codec \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

The module list is comma-separated, with **no** spaces added. Do not use `ALL-UNNAMED` in place of a named module's name; the two module types are different.

### 5.3. Checking Permission in Code

JDK 22 provides:

~~~java
// Java 22+ snippet, code inside a class
boolean enabled =
        NativeAccessDemo.class.getModule().isNativeAccessEnabled();
System.out.println("nativeAccess=" + enabled);
~~~

`Module.isNativeAccessEnabled()` is a **query** for module permission, not a self-grant. For a classpath demo run with `--enable-native-access=ALL-UNNAMED`, the printed value is `true`. For a module without a grant, it is `false`, even though warn mode may temporarily allow the restricted operation to proceed. Do not confuse "allowed to run due to warn" with "module has native access enabled".

A strict application can check permission and refuse to initialize bindings with a clear error message before loading libraries, but that is **application design**, and does not change the JVM's actual `IllegalCallerException` behavior when mode=deny.

### 5.4. Ways to Provide Grants in Deployment

For code on the classpath, besides the command line:

- `JDK_JAVA_OPTIONS` for the launcher if operations manage the environment.
- Java launcher argument files such as `@java-args.txt` to standardize flags.
- The manifest of an **executable JAR** with the attribute `Enable-Native-Access: ALL-UNNAMED`. Per JDK docs, do **not** put a named module name as the value of this manifest attribute.
- A runtime image created by `jlink` can embed launcher flags using the appropriate `--add-options` mechanism.
- For dynamic module layers, `ModuleLayer.Controller.enableNativeAccess(...)` is a conditional restricted API, **not** a license for code to routinely self-elevate privileges at will.

How permission is granted should be a **decision of the application deployer**, reviewed alongside binary artifacts, checksums, supply chain, and permissions. Do not let a third-party library force every JVM on a host to open `ALL-UNNAMED` if it can be isolated into a separate module.

### 5.5. What Does **Not Replace** Native-Access Permission?

- `--add-opens` opens reflection access to a package; it does not grant permission to call restricted FFM/native methods.
- `--add-exports` opens access to internal/exported packages; it does not grant native access.
- `--enable-preview` enables preview features of that release; **final FFM in JDK 22** does not need it, and it does not grant native access.
- `-Djava.library.path=...` helps JNI locate libraries by name; it does not grant permission for `System.loadLibrary` when JDK 24+ enforces policy.
- `System.loadLibrary("example")` by itself is not a declaration that "I allow this module to call native" and may produce a warning.
- `--illegal-native-access=allow` makes warnings disappear during a compatibility phase, but does not mark the module as granted; it is a way to **bypass the policy**, not narrow privilege delegation.

## 6. Runnable Example: C Library and Java FFM Using Four Groups of Restricted APIs

We create a C11 library logically named `nativegate` with three exported functions:

1. `add_i32(int32_t a,int32_t b)`: returns the sum of two integers; Java uses `Linker.downcallHandle`.
2. `invoke_callback(int32_t value,int32_t(*callback)(int32_t))`: C calls a function pointer created by `Linker.upcallStub` and returns the value; example of a synchronous callback.
3. `get_fixed_pair(void)`: C returns the address of `static const int32_t[2]={9,12}`. Java knows **exactly 2×4 bytes per the C contract**, so it uses `MemorySegment.reinterpret(8,arena,null)` to read it.

`SymbolLookup.libraryLookup(path,arena)` is the restricted action when loading the library. The Java part also prints `Module.isNativeAccessEnabled()` to distinguish running with a grant from running in warn-only mode. **There is no JNI entry point** because all three functions are pure C ABI.

Layout:

~~~text
native-permission-demo/
├── native/
│   └── nativegate.c
├── src/
│   └── NativeAccessDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

### 6.1. Full C11 — `native/nativegate.c`

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

_Static_assert(sizeof(int32_t) == 4,
               "demo requires int32_t to be 4 bytes");

EXPORT int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}

typedef int32_t (*unary_callback)(int32_t);

EXPORT int32_t invoke_callback(
        int32_t value, unary_callback callback) {
    if (callback == NULL) {
        return 0;
    }
    /* Call synchronously and do not store the pointer for use after the call. */
    return callback(value);
}

EXPORT const int32_t *get_fixed_pair(void) {
    static const int32_t pair[2] = {9, 12};
    return pair;  /* Borrowed, static, read-only, do not free. */
}
~~~

Library contract:

- `int32_t` has a 32-bit width; `ValueLayout.JAVA_INT` has Java carrier `int` and size 4. The C compiler and JVM must share the same target ABI; if porting to another target, verify alignment/calling convention.
- `add_i32(20,22)` returns 42, with no overflow for the demo values.
- `invoke_callback(21,twice)` calls the callback **exactly once, synchronously**; does not retain the function pointer beyond return. Java can close the arena after the call completes.
- `get_fixed_pair()` returns a **non-NULL** pointer to at least two valid `int32_t` values, **which Java must not free or modify**. The pointer lives as long as the binary library remains loaded and C static data remains valid.
- No `malloc` is used, and there is no native heap owner requiring `free` in this example. If an API returns a malloc pointer in practice, you must call the proper destroy/free and coordinate lifetime with the arena.

### 6.2. Full Java 22+ — `src/NativeAccessDemo.java`

~~~java
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

public final class NativeAccessDemo {
    private NativeAccessDemo() {
    }

    // Java callback that C receives as a function pointer int(*)(int).
    private static int twice(int x) {
        return x * 2;
    }

    public static void main(String[] args) throws Throwable {
        Module module = NativeAccessDemo.class.getModule();
        System.out.println("nativeAccess=" +
                module.isNativeAccessEnabled());

        Path library = Path.of("build", "lib",
                System.mapLibraryName("nativegate")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();

            // RESTRICTED #1: loading a native library.
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // int32_t add_i32(int32_t,int32_t)
            // RESTRICTED #2: downcall handle.
            MethodHandle add = linker.downcallHandle(
                    symbols.find("add_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            int sum = (int) add.invokeExact(20, 22);
            System.out.println("add=" + sum);

            // C signature: int32_t invoke_callback(
            //     int32_t, int32_t (*)(int32_t))
            MethodHandle invokeCallback = linker.downcallHandle(
                    symbols.find("invoke_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle javaCallback = MethodHandles.lookup()
                    .findStatic(
                            NativeAccessDemo.class,
                            "twice",
                            MethodType.methodType(
                                    int.class, int.class));

            // RESTRICTED #3: create upcall function pointer.
            MemorySegment callback = linker.upcallStub(
                    javaCallback,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    arena);

            int callbackResult = (int)
                    invokeCallback.invokeExact(21, callback);
            System.out.println("callback=" + callbackResult);

            // C returns const int32_t pair[2] as pointer.
            MethodHandle getPair = linker.downcallHandle(
                    symbols.find("get_fixed_pair").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.ADDRESS));

            MemorySegment raw =
                    (MemorySegment) getPair.invokeExact();
            if (raw.address() == 0L) {
                throw new IllegalStateException(
                        "get_fixed_pair returned NULL");
            }
            System.out.println("rawSize=" + raw.byteSize());

            // RESTRICTED #4: reinterpret zero-length pointer.
            // Contract C guarantees exactly two int32_t values.
            long bytes = 2L * ValueLayout.JAVA_INT.byteSize();
            MemorySegment pair =
                    raw.reinterpret(bytes, arena, null);

            int first = pair.getAtIndex(ValueLayout.JAVA_INT, 0);
            int second = pair.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("pair=" + first + "," + second);
        }
    }
}
~~~

This is a **complete runnable Java file** with JDK 22+ and the native library above. `NativeAccessDemo.class.getModule().isNativeAccessEnabled()` is introspection; it does not grant permission itself. When run with `--enable-native-access=ALL-UNNAMED`, the first line will print `nativeAccess=true`.

### 6.3. Why Does the Program Still Have Areas That Can Cause Danger?

- `libraryLookup` is loading a **native binary**; only choose trusted files and target-matching dependencies.
- `downcallHandle` uses a descriptor chosen by Java; it is correct here because we control the C source/prototype. If the C prototype changes without updating the Java descriptor, the program can break.
- `upcallStub` only lives within the `Arena`; C does not store the callback after returning. If C works asynchronously, you must unregister the callback and wait for all invocations to finish **before arena.close()**.
- `reinterpret(bytes,arena,null)` does not verify that the actual C allocation is 8 bytes. The example is correct because the static C contract provides `int32_t[2]`; for pointers returned by APIs of unknown length, do not guess and reinterpret.
- `pair` is a borrowed view into static C data and must not be freed or mutated. The `arena` scope bounds Java accesses, but the C library must remain loaded while reading.
- The Java callback `twice` throws no exceptions and yields 21×2=42. For production callbacks, there must be an error-conversion strategy; do not let Java exceptions propagate arbitrarily across the C ABI.

**Being granted native access does not mean being granted permission to modify all native data.** Java can create a writable alias to `const` C memory; writing to it can cause undefined behavior or an OS protection fault. Always obey the C const/ownership contract even when there is no Java-side read-only flag.

## 7. Building/Running the Example on Linux, macOS, and Windows

Run from the root directory `native-permission-demo`. Requires **JDK 22 or later** and a C compiler matching the CPU/OS ABI. The Java source uses final `java.lang.foreign`, does not need `--enable-preview`, and does not use JNI `javac -h` because the library exports a regular C ABI.

### 7.1. Linux, GCC or Clang

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/nativegate.c -o build/lib/libnativegate.so

javac -d build/classes src/NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

### 7.2. macOS, Clang

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/nativegate.c -o build/lib/libnativegate.dylib

javac -d build/classes src/NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

### 7.3. Windows x64, MSVC Developer Command Prompt

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /LD native\nativegate.c ^
  /link /OUT:build\lib\nativegate.dll

javac -d build\classes src\NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes NativeAccessDemo
~~~

On Windows, the line-continuation `^` is **Command Prompt** syntax. On Apple Silicon macOS, use an arm64 binary for an arm64 JVM; Windows x64 requires an x64-configured compiler, not an x86 DLL by mistake. `System.mapLibraryName("nativegate")` returns the logical mapped filename per OS; the library does not need to reside in `java.library.path` because `SymbolLookup.libraryLookup` is given an **absolute Path**.

If the OS reports missing dynamic dependencies, check the platform's dependency search path. Renaming a DLL extension to SO cannot fix an ABI mismatch.

### 7.4. Exact Stdout in Full-Permission Mode

~~~text
nativeAccess=true
add=42
callback=42
rawSize=0
pair=9,12
~~~

Explanation: the classpath module is granted native access, so introspection returns `true`. C `add_i32(20,22)` returns 42; Java callback `twice(21)` is called once by C and returns 42; the raw pointer returned via `ValueLayout.ADDRESS` has `byteSize()==0` because there is no target layout; Java opens an 8-byte view per the C contract `pair[2]={9,12}` and reads the 2 integers accurately.

These lines are **output derived from the source with the right ABI/build/runtime**; you must actually run on the target JDK and OS to verify the executable end-to-end. No native addresses or warning logs are printed, as they vary by process/JDK version.

## 8. Native-Access Permission Experiments (Especially JDK 24+)

Assume the library is built and Java is compiled. **No recompilation is needed** to switch between policy flags.

### 8.1. Running With Permission (Standard Path)

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

Line `nativeAccess=true` and the remaining 4 lines match `Stdout` in section 7.4. There are no warnings because the module performing restricted operations has been granted permission.

### 8.2. Running Without Permission, JDK 24/25 Default `warn`

~~~sh
java -cp build/classes NativeAccessDemo
~~~

The first line is usually `nativeAccess=false`. The JVM may continue restricted operations while writing a **warning to stderr** about illegal native access in the unnamed module. **Do not assert** the interleaving order of warnings with stdout because stdout/stderr buffering differs; do not copy a specific JDK's warning text as fixed output.

The purpose of `warn` mode is to give projects an opportunity to upgrade, not to prove the binding is safe. Do not ship these logs to production and claim the program is authorized. On future JDKs with stricter policies, the same command may fail to run.

### 8.3. Running Without Permission With `deny` (JDK 24+)

~~~sh
java --illegal-native-access=deny \
  -cp build/classes NativeAccessDemo
~~~

The program may print `nativeAccess=false` and then throw **`IllegalCallerException` on the first restricted API call** (`SymbolLookup.libraryLookup`). Do not strictly predict stack trace line numbers, messages, or Java stderr formatting. This is a **policy error**, not evidence that `nativegate.so/dylib/dll` is missing symbols.

### 8.4. Granting Properly and Testing With `deny`

~~~sh
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -cp build/classes NativeAccessDemo
~~~

On JDK 24/25, this is a good deployment check: the code runs normally and produces the **exact stdout** from section 7.4. If another module in the application also directly loads/binds native code **without a grant**, its operations will still be denied; this helps you discover dependencies that need review.

### 8.5. What About JDK 22–23?

FFM is final since 22; `--enable-native-access=ALL-UNNAMED` is the transparent, compatible way to run. However, **do not** copy JDK 24's `--illegal-native-access=deny` to a 22/23 launcher assuming the flag is always available. JDK 22/23 has its own rules: when native access is configured for some modules, restricted calls from other modules may be rejected; when no grants are specified, the runtime may warn. Test on the actual target runtime, and do not mix warning expectations across major releases.

## 9. JNI Also Needs Native Access Permission Starting in JDK 24

JEP 472 applies the policy to **two JNI steps** that can bypass JVM guarantees:

1. **Loading a native library**, e.g., `System.loadLibrary("legacy")`, `System.load(path)`, and corresponding overloads on `Runtime`. Loading can execute OS loader initializers and `JNI_OnLoad`.
2. **Binding/linking native methods** when the JVM first links a `native` method to a function in a binary (`Java_package_Class_method` or `RegisterNatives`). JNI can call Java objects/methods, but the JVM cannot guarantee that the actual native function matches the ABI from the method declaration alone.

Java JNI example **for policy illustration only**, not a standalone runnable program:

~~~java
package demo;

public final class LegacyApi {
    static {
        System.loadLibrary("legacy");
    }

    public static native int calculate(int value);
}
~~~

This snippet only shows the points that can trigger warn/deny when the module is not granted; running it requires a **native C/JNI implementation** and corresponding exported symbols. Do not use it to replace the C ABI/FFM demo program above.

On JDK 24+, if `LegacyApi` is in a **named module** `com.example.legacyjni`, deployment can grant:

~~~sh
java --enable-native-access=com.example.legacyjni \
  --illegal-native-access=deny \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

This is a **launcher pattern** assuming named modules are already built, not for running `LegacyApi.java` directly. Having a JNI library loaded by one module and a `native` method declared in another module may require evaluating **both modules**; do not grant permission to the main module out of habit when the restricted operations actually live in another library/module.

### 9.1. JNI and FFM Still Serve Different Purposes

- **JNI**: `JNIEnv`, `jobject`, Java arrays, fields, methods, Java exceptions, class loader integration, Invocation API. A bridge into the **JVM object model**.
- **FFM**: C ABI downcalls, upcall function pointers, native memory, `MemorySegment`/`Arena`/`MemoryLayout`. Useful for C libraries **that do not depend on Java objects**.
- **Common policy point:** both can execute native code and break JVM integrity if misused, so the JVM requires explicit deployer consent.
- **Not a mutually exclusive choice:** an application can use JNI for native→Java objects and FFM for pure C ABI, granting permission to the right modules and managing resources separately.

## 10. Why Shouldn't You Grant Permission as Broadly as Possible?

Suppose a server has 50 libraries on the classpath. When running with `ALL-UNNAMED`, any library in unnamed modules can directly call restricted FFM/JNI operations whenever its code path executes; that is a **broad trust choice**. If a dependency is compromised or has a vulnerability, native access permission can make the consequences more severe.

However, **named module permission also does not sandbox** code within the granted module itself. It only reduces the surface area of modules allowed to cross the boundary. A loaded native binary is also in the **same OS process**, potentially having the same file/network/process privileges as the JVM host. You must combine:

- Dependency provenance, binary review, checksums/signatures, and update controls.
- Proper module ownership; small native binding modules, typed Java APIs, validated input data.
- Management of `Arena`, native allocations, callback registrations, worker threads, and error handling.
- Multi-OS/architecture ABI CI builds; pay special attention on Windows to C `long` width and CRT/allocator family.
- Preventing C function pointers from outliving the library or owning Arena.
- Managing OS permissions and process isolation for untrusted native code.

**FFM MemorySegment bounds checks only protect Java-side accesses within declared bounds.** A C function called via downcall can still read/write past a buffer. Similarly, `reinterpret` expanding bounds incorrectly can cause Java-side checks to accept invalid operations. Granting permission is a **risk-acceptance decision**, not an allocation verification.

## 11. Discovery and Auditing Tools Before Upgrading JDK

### 11.1. Combining Warnings, Deny, and Runtime Tests

Practical workflow when upgrading an application from JDK 21 to JDK 24+:

1. Run integration tests on the target JDK in default `warn` mode, collect **stderr**, and identify modules that load/bind JNI or call restricted FFM methods.
2. Also run with `--illegal-native-access=deny` to find code paths that genuinely **need permission**; operations blocked with `IllegalCallerException` pinpoint missing grants.
3. Grant `--enable-native-access=M1,M2,...` to **the modules that actually call restricted operations**, without rushing to grant the entire app.
4. Re-run with **both `--enable-native-access` and `--illegal-native-access=deny`** to verify no hidden ungranted callers remain.
5. Test error paths and rarely executed branches: lazy JNI method binding can occur when a method is first called, not only at application startup.
6. Verify ABI and native library paths, allocators/lifetimes/callbacks. Having zero warnings **does not** mean the native integration is memory-safe.

### 11.2. `jnativescan` on JDK 24+

JDK 24 introduces the `jnativescan` tool to **statically scan Java code** for JNI usage that may need permission, such as `native` declarations and restricted calls. View exact options with:

~~~sh
jnativescan --help
~~~

For projects with many JARs/modules, use command-line syntax supported by the **deployed JDK version**, as options and ways to pass module path/class path should be checked against `jnativescan --help` on the machine. Do not assume a static scan covers all reflective calls, generated code, dynamic loading, or native libraries loaded only at runtime. Combine static scans with integration tests.

### 11.3. JFR Events and Logs

On supported runtimes, JDK Flight Recorder provides `jdk.NativeLibraryLoad` and `jdk.NativeLibraryUnload` events to help observe when the JVM loads/unloads native libraries. JFR events are **diagnostics**, not proof that C code matches the ABI or that all native methods are tested.

Monitor warnings from **stderr**, the module name in the message, JDK version, launcher flags, and the dependency causing the load. Do not troubleshoot by silencing warnings everywhere with `--illegal-native-access=allow`; that hides the evidence needed to fix deployment.

## 12. Classifying Errors to Avoid Fixing the Wrong Thing

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `IllegalCallerException` at `libraryLookup`/`downcallHandle` | Module lacks native access in deny mode or JDK 22/23 restricted configuration | Grant `--enable-native-access` to the right **caller module** |
| Restricted FFM warning on stderr | Native access not yet granted to the module | Verify the module is listed in the flag; do not treat a warning as full success |
| `System.loadLibrary`/native method binding warning on JDK 24+ | JNI native access not yet granted | Grant to the corresponding loading/binding module |
| `UnsatisfiedLinkError` when loading JNI | Binary/dependency/symbol not found, wrong OS/architecture | Check path, library name, native exports, linker dependencies |
| `NoSuchElementException` on `symbols.find(...).orElseThrow()` | C symbol not exported/name mismatch | Use `nm`, `dumpbin`, check C++ name mangling |
| `WrongMethodTypeException` on `invokeExact` | Java carrier arity/return types do not match the created MethodHandle | Check `FunctionDescriptor` and explicit Java casts |
| JVM crash when calling C | Possible wrong ABI/descriptor, pointer, lifetime, or callback | Review C header, target ABI, native diagnostics/sanitizers |
| `IndexOutOfBoundsException` with `MemorySegment.get` | Declared Java spatial bounds are insufficient | Verify offset + layout size, do not blindly expand with reinterpret |
| `IllegalStateException` when using a segment | Arena scope is already closed | Fix ownership/lifetime, do not keep calling |
| `WrongThreadException` | Confined Arena accessed from another thread | Use the owner thread or a shared arena with synchronization |
| C library loads but callback crashes after close | UpcallStub address lifetime expired | Unregister/stop/join before closing the Arena |
| Added `--add-opens` but still getting IllegalCallerException | Reflection flags do not grant native-access | Use `--enable-native-access`, do not mix the two mechanisms |
| Demo runs with grant but output is wrong | Not a native permission error | Check C logic, ABI, format, endianness, data race |
| JDK 22 runs, but adding `--illegal-native-access=deny` reports unknown option | Unified JNI/FFM management option starts in JDK 24 | Use the right flags for the JDK release |
| Granted permission to main module but not binding module | Caller of the restricted method is in another module | Grant the module name **that defines the code performing the operation** |

Do not write unit tests that intentionally create an invalid C function descriptor and expect Java to always throw a safe exception. Failure paths caused by native memory corruption can bring down the entire test JVM process; for untrusted APIs, use process isolation and C sanitizers.

## 13. Four Architectural Scenarios

### 13.1. CLI Tool Only Computing With a C ABI

A classpath application uses a small C SDK, and operations staff control the binary. Using FFM (JDK 22+) and `--enable-native-access=ALL-UNNAMED` is simple and clear. If deploying on JDK 24/25, add `--illegal-native-access=deny` in integration tests to catch ungranted native calls in other modules.

### 13.2. Server With Many Dependencies Containing Native Code

If 50 JAR files share the classpath, `ALL-UNNAMED` grants broad permission to all of them. Layer it: move the native bridge separately onto the module path, name it `com.example.nativebridge`, grant `--enable-native-access=com.example.nativebridge`, and expose only a safe Java interface to the rest. **Do not** assume Java modules become a sandbox; control the binary supply chain.

### 13.3. Plugin System With Dynamic ClassLoader/ModuleLayer

A plugin can call JNI/FFM after loading, while native callbacks/global refs can keep class loaders alive. Do not let arbitrary plugins self-escalate native access; review and grant per host policy, knowing exactly which modules perform restricted calls. Stop/unregister callbacks, free native resources, close Arenas, and release loader dependencies **before** unloading. `ModuleLayer.Controller.enableNativeAccess` is a restricted API and does not replace policy auditing.

### 13.4. Upgrading a Java 21 JNI Framework to JDK 24+

Previously, JNI `System.loadLibrary` might not have generated native-access warnings under the new policy. When running on JDK 24, library loads and native method bindings can produce warnings even though business logic did not change. You do not necessarily have to rewrite JNI to FFM; instead, identify modules using JNI, add appropriate grants, and test under `deny`. Read JEP 472 and the JDK migration guide for the exact version to understand module attribution of native methods.

## 14. Exercises and Answers

1. **Is restricted the same as deprecated?** No. `Linker.downcallHandle` is an official API, but it requires consent because a wrong signature can break memory safety.
2. **Do you need a grant to call `MemoryLayout.sequenceLayout(10,JAVA_INT)`?** Not solely for that operation; creating a safe layout is not equivalent to executing native code.
3. **Who checks the permission?** The JVM checks the module of the caller of the restricted API; it is not the OS validating C headers.
4. **How is permission granted on the classpath?** `--enable-native-access=ALL-UNNAMED`.
5. **Named module `com.acme.ffi`?** `--enable-native-access=com.acme.ffi`.
6. **Is `--add-opens` equivalent to native access?** No, it is for reflective package access.
7. **Is `--enable-preview` needed for JDK 22 FFM?** No, FFM is final; preview and native access are two different mechanisms.
8. **Which phase does `--illegal-native-access=deny` belong to?** JDK 24+; the runtime responds with `IllegalCallerException` on illegal native access.
9. **What is the default mode in JDK 24?** `warn` per JEP 472.
10. **Why is `libraryLookup` restricted before calling C?** Native library initializers can run immediately upon loading.
11. **Why is `reinterpret` restricted?** The caller can overstate size/lifetime, leading to out-of-bounds or dangling accesses.
12. **Once permission is granted, does the JVM automatically verify the ABI?** No. Permission does not replace checking C prototypes/memory lifetimes.
13. **What happens to an FFM upcall stub stored by C after Arena.close?** Dangling function pointer, potentially causing crash/corruption.
14. **Why can JNI `System.loadLibrary` warn on JDK 24?** Loading a native library is a restricted operation under JEP 472 when the module is not granted.
15. **Should `--illegal-native-access=allow` be used long-term in production?** No; it hides warnings and does not grant permission to specific modules.
16. **App runs with a grant but still gets `UnsatisfiedLinkError`?** That is a binary/path/dependencies/symbol issue, not a native-access grant issue.
17. **How to audit dependencies?** Combine stderr warnings, `jnativescan`, native library load events, `deny` mode, and integration tests.
18. **Why should the FFM bridge module be separate?** Reduces the scope of granted modules per least privilege, even though it is not a sandbox.

## 15. Production Checklist for Native Access

- [ ] **JDK:** Confirmed actual runtime version, FFM final since JDK 22, JNI native access policy in JDK 24+?
- [ ] **Inventory:** Identified which code calls `SymbolLookup.libraryLookup`, `Linker.downcallHandle`, `upcallStub`, `reinterpret`, `AddressLayout.withTargetLayout`, or delegates permission via `ModuleLayer.Controller`?
- [ ] **JNI:** On JDK 24+, accounted for both `System/Runtime.load*` and native method linking?
- [ ] **Module:** Identified which module (named or unnamed) holds the code performing the restricted operation, and granted **the exact caller module name**?
- [ ] **Least privilege:** Can native bindings be placed in a separate module instead of using `ALL-UNNAMED` for all dependencies?
- [ ] **Flags:** Production launcher has `--enable-native-access=...`, and environment/jlink/manifest options are managed consistently?
- [ ] **Tests:** On JDK 24+, ran CI with `--illegal-native-access=deny` and inspected stderr/warnings for lazy branches?
- [ ] **ABI:** FunctionDescriptor/MethodHandle matches C header/ABI per OS/CPU; no guessing `long`, `size_t`, or variadic types?
- [ ] **Memory:** `MemorySegment` has correct size, alignment, scope, and ownership; `reinterpret` used only after verifying the C length contract?
- [ ] **Callbacks:** Upcall target/stub lives long enough, native unregisters callbacks, and workers stop/join before Arena.close?
- [ ] **Binary:** Library path/dependencies, provenance, signatures/hashes, and JVM/compiler architecture reviewed?
- [ ] **Errors:** Distinguished policy `IllegalCallerException` from `UnsatisfiedLinkError`, `WrongMethodTypeException`, scope/bounds errors, and OS crashes?
- [ ] **Security:** Not treating native access grants as a sandbox or proof that a native library is safe; OS isolation in place if binaries are untrusted?
- [ ] **Maintenance:** Tracking JDK release notes because `warn` is expected to become `deny` by default in a future release; not relying on warning behavior permanently.

**Conclusion:** Java places points **that can execute code or interpret memory beyond the JVM's verification** into the restricted category. `--enable-native-access` does not "turn on a missing feature"; it explicitly records the decision **to allow a specific module to cross the safety boundary**. This consent should come from the deployment owner, be tested with `deny` on JDK 24+, and be accompanied by accurate C ABI, library binary control, ownership, and cleanup. If a JNI or FFM call is wrong, a granted module can still crash the entire JVM.

### Official References

- Oracle, [JDK 22 Restricted Methods](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html): FFM restricted list, reasons, `--enable-native-access`.
- Oracle, [JDK 25 Restricted Methods](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html): named/unnamed grants, `Module.isNativeAccessEnabled`, `--illegal-native-access` modes.
- Oracle, [JDK 22 Linker API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall and ABI risks.
- Oracle, [JDK 22 Module.isNativeAccessEnabled](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/Module.html#isNativeAccessEnabled()): Java-side permission inspection.
- Oracle, [JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): JNI load/binding, JEP 472, `jnativescan`, deployment flags, and diagnostics.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): FFM API final in JDK 22.
- OpenJDK, [JEP 472](https://openjdk.org/jeps/472): preparing to restrict the use of JNI and unifying JDK 24 native access policy.
- Dev.java, [Troubleshoot FFM Calls — Restricted Methods](https://dev.java/learn/api/io/ffm/troubleshoot/): reasons for restriction and option examples.