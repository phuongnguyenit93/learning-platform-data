# Method Names to Check When Migrating FFM Code Across Java Versions

## 1. Why Does a Foreign Function & Memory (FFM) Snippet That Runs on One JDK Fail to Compile on Another?

**Foreign Function & Memory API (FFM)** provides Java types for working with native memory, C libraries, and native function pointers without having to write a JNI layer by hand for every call. This API went through several redesigns before becoming a permanent API:

| JDK | Stage | Primary module/package | Meaning for source code |
| --- | --- | --- | --- |
| **17** | JEP 412 — incubator | Module `jdk.incubator.foreign`, package `jdk.incubator.foreign` | Uses `CLinker`, `ResourceScope`, `MemoryAddress`, many older names; enable incubator module |
| **18** | JEP 419 — second incubator | `jdk.incubator.foreign` | Do not assume all signatures in JDK 17 remain identical; check JDK 18 Javadoc |
| **19** | JEP 424 — first preview | `java.lang.foreign` in `java.base` | Introduces `Linker`, `MemorySession`; many names and carrier types change |
| **20** | JEP 434 — second preview | `java.lang.foreign` | `Arena`, `SegmentScope`; many `MemoryAddress` roles are unified into `MemorySegment` |
| **21** | JEP 442 — third preview | `java.lang.foreign` | `Arena.ofConfined` and new factories; `VaList` has been removed |
| **22** | JEP 454 — **final/permanent** | `java.lang.foreign` | API stabilizes out of preview status; renames some string/allocation methods, adds C canonical layouts lookup |
| **23+** | Post-final API versions | `java.lang.foreign` | Continues to add convenience methods/changes to native-access policy; do not infer that "final" means the entire API is forever immutable |

This is **not just** changing an `import`. In an FFM call, there are at least four parts to cross-check by version: **class/method names**, **parameter list**, **return type/`MethodHandle` carrier**, and **native access permission at runtime**.

A common error example when copying a tutorial written for JDK 21 into JDK 22:

~~~java
// JDK 21 preview; NOT JDK 22 code:
MemorySegment text = arena.allocateUtf8String("Hello");
String value = text.getUtf8String(0);
~~~

Written for JDK 22:

~~~java
// JDK 22+: two new names:
MemorySegment text = arena.allocateFrom("Hello");
String value = text.getString(0);
~~~

**Same purpose**, but the names changed. Without locking the target JDK, the IDE reports `cannot find symbol` even though the program logic is conceptually correct.

> **Article scope:** a map of **method names to check** when migrating code between JDKs 17–23 and the checks that continue to apply in newer JDKs. Examples labeled as historical are *version-specific illustrations*, not standalone runnable programs. The two programs in the hands-on section use **JDK 22+** and have their own compile/run commands.

## 2. Quick Reference List: Old Names, New Names, and Milestones

| Functionality | Name/usage in older versions | Check/usage in newer versions | Notes |
| --- | --- | --- | --- |
| API package | `jdk.incubator.foreign.*` (JDK 17–18) | `java.lang.foreign.*` (JDK 19+) | JDK 19–21 require preview; JDK 22+ do not |
| Get C linker | `CLinker.getInstance()` (JDK 17) | `Linker.nativeLinker()` (JDK 19+) | JDK 18 is a different incubator: check the exact JDK 18 Javadoc |
| Default C library lookup | `CLinker.systemLookup()` (JDK 17) | `Linker.nativeLinker().defaultLookup()` (JDK 19+) | Available symbols depend on platform; do not confuse with custom library lookup |
| Find symbol in `SymbolLookup` | `lookup("name")` (JDK 17–19) | `find("name")` (JDK 20+) | Both require handling the not-found case |
| Find symbol or throw exception | `find("name").orElseThrow()` (JDK 20–22) | `findOrThrow("name")` available from JDK 23 | Do not use `findOrThrow` when still targeting JDK 22 |
| Manage native memory lifetime | `ResourceScope.newConfinedScope()` (JDK 17) | `MemorySession.openConfined()` (JDK 19), then `Arena` | Not just a class rename; the allocation contract also changed |
| Create confined arena | `Arena.openConfined()` (JDK 20) | `Arena.ofConfined()` (JDK 21+) | Changed `open...` → `of...` at milestone 21 |
| Create shared arena | `Arena.openShared()` (JDK 20) | `Arena.ofShared()` (JDK 21+) | Check ownership/confinement |
| Allocate memory region | `MemorySegment.allocateNative(..., scope/session)` (JDK 19–20) | `arena.allocate(...)` (JDK 21+) | New API is an instance method of allocator/arena |
| Allocate UTF-8 C string | `arena.allocateUtf8String(s)` (JDK 20–21) | `arena.allocateFrom(s)` (JDK 22+) | `allocateFrom` also has other overloads, check argument types |
| Read UTF-8 string from segment | `segment.getUtf8String(offset)` (JDK 20–21) | `segment.getString(offset)` (JDK 22+) | JDK 22 has overload `getString(offset, charset)` |
| Write UTF-8 string into segment | `segment.setUtf8String(offset, s)` (JDK 20–21) | `segment.setString(offset, s)` (JDK 22+) | Do not infer byte capacity from `String.length()` |
| Allocate primitive array | `arena.allocateArray(layout, elements...)` (JDK 20–21) | `arena.allocateFrom(layout, elements...)` (JDK 22+) | Check `SegmentAllocator` overloads |
| Address representation | Separate `MemoryAddress` (JDK 17–19) | `MemorySegment` models pointer/address (JDK 20+) | Many `downcallHandle` and pointer access signatures changed type |
| Numeric address | `MemoryAddress.toRawLongValue()` in older design | `MemorySegment.address()` returns `long` in modern versions | Must not use raw address after memory lifetime ends |
| Get size/bounds and scope | `ResourceScope` / `MemorySession` / `SegmentScope` | `Arena.scope()`, `MemorySegment.scope()` (depending on JDK) | `MemorySegment.Scope` is the type name in JDK 22 |
| Create upcall stub | `upcallStub(handle, descriptor, session)` (JDK 19) | `upcallStub(handle, descriptor, arena)` (JDK 21–22) | Last argument changes according to lifetime management mechanism |
| Downcall method signature | `CLinker.downcallHandle(symbol, MethodType, descriptor)` (JDK 17) | `Linker.downcallHandle(symbol, descriptor, options...)` (JDK 20+) | Method type is inferred; many carrier types changed |
| Canonical C layouts | Must manually match ABI explicitly in preview API | `linker.canonicalLayouts()` (JDK 22+) | Useful for `size_t`, `long`, `wchar_t`... |
| C variadic arguments | `VaList` existed in some preview versions | `Linker.Option.firstVariadicArg(index)` when using variadic downcall in the new API | JDK 21 removed `VaList`; do not blindly map all varargs |

**How to read the table:** The cells are **transition milestones to check**, not assertions that a name exists in every version across a range without checking the Javadoc of the specific version. For example, `CLinker.getInstance()` is stated accurately for JDK 17; do not copy it verbatim to JDK 18 just because both are incubators.

The table uses official documentation per **versioned Javadoc** at the end of the article. It is crucial not to copy Java 25 search results to fix source code that must run on Java 21.

## 3. Package Changes and Feature-Enabling Flags: Before Even Editing Methods

### 3.1. JDK 17–18: incubator

Old-style imports:

~~~java
// JDK 17 (incubator), illustration only:
import jdk.incubator.foreign.CLinker;
import jdk.incubator.foreign.MemorySegment;
import jdk.incubator.foreign.ResourceScope;
~~~

With JDK 17 incubator, you need to add the module and native access when the program uses restricted operations, for example:

~~~bash
# Example syntax for JDK 17; not a command to compile JDK 22 files.
javac --add-modules jdk.incubator.foreign OldFfm17.java
java --add-modules jdk.incubator.foreign \
  --enable-native-access=ALL-UNNAMED OldFfm17
~~~

The filename `OldFfm17.java` here **is a command example placeholder**: the code snippet above does not provide that standalone file. The incubator module printing a warning does not prove that the code is wrong.

### 3.2. JDK 19–21: preview

Imports change to:

~~~java
// JDK 19–21 preview; import illustration only:
import java.lang.foreign.MemorySegment;
import java.lang.foreign.Linker;
~~~

FFM preview must be enabled at both **compile** and **run** time. Replace `21` with the exact target preview JDK version:

~~~bash
# Example command template for JDK 21; Example21.java is a hypothetical name.
javac --enable-preview --release 21 Example21.java
java --enable-preview --enable-native-access=ALL-UNNAMED Example21
~~~

Do not use `--release 22 --enable-preview` for an FFM program that is already final, because preview in a different version does not have an equivalent meaning. Likewise, do not assume class files compiled with JDK 21 preview can run identically on JDK 22.

### 3.3. JDK 22+: final, but still check native access

From JDK 22, FFM is a permanent API in `java.lang.foreign`. For programs that only allocate/read native memory using non-restricted APIs, `--enable-preview` is generally not needed. For programs that create foreign downcall handles or call restricted methods, **grant native access to the appropriate module**:

~~~bash
# Command for a JDK 22+ FFM program on the classpath:
javac FfmMigration22.java
java --enable-native-access=ALL-UNNAMED FfmMigration22
~~~

The filename here corresponds to the runnable program in section 10.

**JDK 24+ changes the native access warning policy:** restricted operations from an ungranted module may emit a warning by default; the `--illegal-native-access=deny` option lets you test strict blocking mode. Do not use "runs with a warning" as proof of long-term compatibility. For named modules, enable native access for the **actual module name** instead of arbitrarily using `ALL-UNNAMED` in production.

**Check first:** `java -version`, `javac -version`, the build tool's target JDK, module/classpath, and flags. If the actual JDK in use differs from the IDE's JDK, `cannot find symbol` errors are very easily misdiagnosed.

## 4. Linker-Related Names: `CLinker`, `Linker`, `downcallHandle`

### 4.1. JDK 17: `CLinker.getInstance()` and manually written method type

Example **illustrating JDK 17 API characteristics only**, not a standalone program:

~~~java
import jdk.incubator.foreign.*;
import java.lang.invoke.*;

MethodHandle strlen = CLinker.getInstance().downcallHandle(
        CLinker.systemLookup().lookup("strlen").orElseThrow(),
        MethodType.methodType(long.class, MemoryAddress.class),
        FunctionDescriptor.of(CLinker.C_LONG, CLinker.C_POINTER)
);
~~~

In JDK 17, the author provides a separate `MethodType`. The signature `CLinker.C_LONG`, `CLinker.C_POINTER` depends on the **ABI**; for example, `strlen` on Linux/x64 has a `size_t` return corresponding to a 64-bit value. Do not infer that Windows/x64 always uses the same layout for `long`.

### 4.2. JDK 19: `Linker.nativeLinker()`, `SymbolLookup.lookup()`

In JDK 19 preview, the call path moved to `Linker`:

~~~java
// JDK 19 preview, illustrating APIs by version only:
Linker linker = Linker.nativeLinker();
SymbolLookup lookup = linker.defaultLookup();
var symbol = lookup.lookup("strlen").orElseThrow();
var descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);
var handle = linker.downcallHandle(symbol, descriptor);
~~~

**What cannot be replaced by simple search-and-replace:** JDK 19 still had the `MemoryAddress` and `Addressable` address abstractions, whereas JDK 20 unified those roles into `MemorySegment`. When encountering type errors on a method handle, carefully check carrier types for the JDK rather than only renaming `downcallHandle`.

### 4.3. JDK 20–22: `SymbolLookup.find()`

Clear rename:

~~~java
// JDK 17–19:
lookup.lookup("strlen").orElseThrow();

// JDK 20–22:
lookup.find("strlen").orElseThrow();
~~~

By JDK 23, `SymbolLookup` provides an additional convenience method:

~~~java
// JDK 23+:
MemorySegment symbol = lookup.findOrThrow("strlen");
~~~

`findOrThrow` **is not an alias to use for JDK 22**. If a library still supports JDK 22, keep `find("name").orElseThrow()`. Also do not reverse `find` → `lookup` when going from 21 to 22: `find` has been used since 20.

### 4.4. Bound and unbound downcall method handles

With the JDK 22 API, the linker has two binding forms:

~~~java
// Illustrating JDK 22+ APIs; linker, symbol, descriptor already exist.
MethodHandle bound = linker.downcallHandle(symbol, descriptor);
MethodHandle unbound = linker.downcallHandle(descriptor);
~~~

- `bound` has a **fixed function address** inside the handle; arguments at invocation time are only the function's C parameters (plus possibly an allocator for struct-return per ABI).
- `unbound` requires an extra **`MemorySegment` symbol address** argument at invocation time. Do not invoke an unbound handle with an argument list meant for a bound handle.
- `MethodHandle.invokeExact` checks the method handle signature strictly; changing types from `MemoryAddress` to `MemorySegment`, from `int` to `long`, or changing the return carrier will cause `WrongMethodTypeException` if the invocation does not match.
- `FunctionDescriptor.ofVoid(...)` is used when the native function returns `void`; `FunctionDescriptor.of(returnLayout, argLayouts...)` for functions with a return value.
- For callbacks/upcalls, `Linker.upcallStub` also has JDK-dependent signature and lifetime rules, see section 9.

## 5. SymbolLookup and Library Loading Names

Distinguish between two tasks:

1. **Finding symbols in default libraries** provided by the ABI/linker (e.g., built-in libc functions): `linker.defaultLookup()`.
2. **Opening a custom library** and finding symbols in it: `SymbolLookup.libraryLookup(..., arena)` in the modern API.

JDK 22 example:

~~~java
// Illustration, not a standalone runnable:
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup custom = SymbolLookup.libraryLookup(
            "mynative", arena);
    MemorySegment symbol = custom.find("my_function").orElseThrow();
}
~~~

The name `"mynative"` in the example is illustrative only; a real library may require a full path or native OS name (`.so`/`.dll`/`.dylib`), depending on what `libraryLookup` expects. **Do not assume** the name for `System.loadLibrary` and the name for `libraryLookup` follow the same search rules. The `Arena` parameter determines the lifetime of the lookup/library loaded via the API, so **do not keep a symbol pointer and use it after the arena is closed**.

Methods to check:

| API | Name to check | Why |
| --- | --- | --- |
| System/default symbols | `CLinker.systemLookup` (17) → `Linker.defaultLookup` (19+) | Responsibility moved from `CLinker` to native linker |
| Loader lookup | `SymbolLookup.loaderLookup()` | Finds symbols in libraries associated with the class loader, not all libraries |
| Find symbol | `lookup(name)` → `find(name)` | JDK 20 milestone |
| Not-found shortcut | `findOrThrow(name)` | Only available from JDK 23; JDK 22 must use `find(...).orElseThrow()` |
| Explicit library | `libraryLookup(name/path, session/scope/arena)` | Lifetime-management argument type changed across FFM versions |
| Load classpath JNI library | `System.loadLibrary(logicalName)` | Legacy Java/JNI API; **do not** mechanically replace with `libraryLookup` |

**Do not treat a `MemorySegment` containing a function address as a readable data memory region.** Native symbol lookup returns a segment representing an address; in the modern design it typically has size 0. Use it with `downcallHandle` instead of reading bytes from it; if you need to dereference external memory, you must know the actual bounds/lifetime and use restricted APIs properly.

## 6. Lifetime Names: `ResourceScope` → `MemorySession` → `Arena`

### 6.1. JDK 17

~~~java
// JDK 17 incubator, illustration: only one lifetime construct.
try (ResourceScope scope = ResourceScope.newConfinedScope()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, scope);
    // use nativeMemory within the valid scope
}
~~~

`ResourceScope` manages when a memory segment becomes invalid. Copying `ResourceScope.newConfinedScope()` into JDK 22 will fail because this class is no longer part of the modern API.

### 6.2. JDK 19

~~~java
// JDK 19 preview, illustration:
try (MemorySession session = MemorySession.openConfined()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, session);
}
~~~

`MemorySession` replaced the older scope model in JDK 19. You cannot assume `session` has all the same methods as `ResourceScope`.

### 6.3. JDK 20

~~~java
// JDK 20 preview, illustration:
try (Arena arena = Arena.openConfined()) {
    MemorySegment nativeMemory =
            MemorySegment.allocateNative(16, arena.scope());
}
~~~

This was the stage where `Arena` and `SegmentScope` were separate in the API, and `Arena.openConfined()` was the factory name. **It is not JDK 21's `Arena.ofConfined()`.**

### 6.4. JDK 21–22+

~~~java
// JDK 21 preview or JDK 22+ final:
try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeMemory = arena.allocate(16);
    nativeMemory.set(ValueLayout.JAVA_INT, 0, 7);
}
~~~

This API style is more concise: `Arena` both allocates and controls lifetime. In JDK 22, `arena.allocate(ValueLayout.JAVA_INT)` also works when you want to allocate exactly one primitive layout.

Factories to distinguish:

| JDK 21+ Factory | Lifetime/characteristics | When to consider |
| --- | --- | --- |
| `Arena.ofConfined()` | Explicit close; accessed on owner thread | Short tasks on a single thread, using try-with-resources |
| `Arena.ofShared()` | Explicit close; accessible from multiple threads | Sharing segments with a synchronization contract |
| `Arena.ofAuto()` | Automatic lifetime managed by GC | No need to release at an exact deterministic time; non-determinism acceptable |
| `Arena.global()` | Unbounded lifetime, never closed | Only when intentionally keeping memory alive until process exit |

**Do not just rename the factory and ignore thread ownership.** `Arena.ofConfined()` does not allow other threads to arbitrarily read the segment; `Arena.ofShared()` allows access but does not automatically make mutable data thread-safe. Once a segment is closed, reading/writing may throw `IllegalStateException`.

## 7. Native String and Array API Names — Notable Changes in JDK 22

### 7.1. C-string: allocation and reading/writing

JDK 20–21 version:

~~~java
// JDK 20–21 preview; does not compile identically on 22:
MemorySegment cString = arena.allocateUtf8String("hello");
String value = cString.getUtf8String(0);
cString.setUtf8String(0, "hi");
~~~

JDK 22+ version:

~~~java
// JDK 22+:
MemorySegment cString = arena.allocateFrom("hello");
String value = cString.getString(0);
cString.setString(0, "hi");
~~~

**Note on size:** After `allocateFrom("hello")`, the buffer is only allocated for the size needed for `"hello"` plus the terminator. Calling `setString(0, ...)` with a string longer than the buffer size can fail bounds checks. A Java String of 10 UTF-16 units does not always take exactly 11 bytes as a UTF-8 C-string: byte count depends on encoding, especially with Vietnamese diacritics and emoji.

JDK 22 provides overloads accepting a `Charset` such as `arena.allocateFrom(text, charset)`, `segment.getString(offset, charset)`, and `segment.setString(offset, text, charset)`. Therefore, renaming does not mean ignoring encoding, byte order, or null-terminator rules.

### 7.2. Native arrays

JDK 21:

~~~java
// JDK 21 preview, illustrating method naming:
MemorySegment values = arena.allocateArray(
        ValueLayout.JAVA_INT, 2, 3, 5);
~~~

JDK 22+:

~~~java
// JDK 22+:
MemorySegment values = arena.allocateFrom(
        ValueLayout.JAVA_INT, 2, 3, 5);
~~~

Reading with the conceptually stable API:

~~~java
// Illustrating JDK 22+ API style:
int first = values.getAtIndex(ValueLayout.JAVA_INT, 0);
int third = values.getAtIndex(ValueLayout.JAVA_INT, 2);
~~~

Check `allocateFrom` overloads with `int[]` arrays, `int...` varargs, and specific layout types. A signature change can cause a call to pick the wrong overload or fail to match generics/carriers, even when the code still "looks similar".

### 7.3. Native data and Java heap are not the same

`arena.allocateFrom` creates a **native memory copy** of the data per the allocator contract; it does not turn a Java array into a zero-copy native array. `MemorySegment.ofArray(int[])` creates a **heap segment** with different native status and alignment; do not pass any heap segment to a C function expecting a native pointer without checking the `Linker` contract.

## 8. `MemoryAddress` and `MemorySegment`: Not Just a Type Rename

In older APIs, `MemoryAddress` was a separate abstraction. From JDK 20 preview onward, pointers/addresses are modeled by `MemorySegment`. This affects:

- Return value of `SymbolLookup.find`: in the modern API it is `Optional<MemorySegment>`.
- Carrier type of a downcall handle for C pointers: `MemorySegment` rather than `MemoryAddress`.
- Reading/writing pointers from memory: use `ValueLayout.ADDRESS` and `MemorySegment.get/set`.
- Creating an address from a `long` in JDK 22: `MemorySegment.ofAddress(address)` creates a zero-length segment.
- `segment.address()` in JDK 22 returns a `long`; this is a **raw address** and does not imply memory ownership.
- `MemorySegment.NULL` is the constant representing a null address in the modern API.

JDK 22 example:

~~~java
// Illustration; symbol and scope declarations are incomplete.
MemorySegment pointer = MemorySegment.ofAddress(0x1000L);
long raw = pointer.address();       // 4096
long size = pointer.byteSize();     // 0
~~~

**Do not dereference** this example: `0x1000L` was chosen only to illustrate the numeric representation, **not** to assert that this address has valid memory. Reading `pointer.get(ValueLayout.JAVA_BYTE, 0)` will hit the bounds of a zero-length segment; calling `reinterpret` with a fabricated length can create unsafe memory access and crash the JVM.

### `reinterpret` and target layout are restricted operations

JDK 22 has `segment.reinterpret(newSize)`, overloads attaching lifetime to an `Arena`, and `AddressLayout.withTargetLayout(...)`. These are **restricted** APIs because assigning bounds/lifetime to a pointer is not verified by the JVM. Use them only when you know for certain where the memory was allocated, its true size, who frees it, and when.

Changing `MemoryAddress.asSegment(...)` in the old design to `MemorySegment.ofAddress(...).reinterpret(...)` is **not** an "automatically safe" rename; you must re-verify native ownership, offset, bounds, scope, and native access policy.

## 9. `upcallStub`, Variadic Functions, and `FunctionDescriptor`

### 9.1. `upcallStub`: check the last argument type

A Java callback invoked by native code via a function pointer (upcall) needs a `MethodHandle` matching the `FunctionDescriptor` and a way to keep the stub alive long enough.

Modern API example:

~~~java
// JDK 22+; illustration, handle/descriptor/linker already exist:
try (Arena arena = Arena.ofConfined()) {
    MemorySegment stub = linker.upcallStub(
            handle, descriptor, arena);
    // Only pass the stub to native code that uses it within the arena's lifetime.
}
~~~

In JDK 19, the last argument of `upcallStub` could be `MemorySession`; in JDK 20 it was `SegmentScope` (typically `arena.scope()`); JDK 21–22 attach it to `Arena`. If you only search-and-replace `MemorySession` → `Arena` while keeping `session`/`scope` as before, the code may have the wrong signature or wrong lifetime.

**Warning:** A native function pointer to a stub must not be retained and called after the arena frees the stub. The callback target method handle must have ABI-correct carrier types and behavior; Java exceptions escaping an upcall do not have arbitrary handling like a Java-to-Java call.

### 9.2. Variadic arguments: `VaList` is not the default option for JDK 21+

Older preview code samples may mention `VaList`. JDK 21 removed `VaList` from the API. For C variadic functions like `printf(const char*, ...)`, the modern API uses a **concrete callsite signature** and marks the variadic argument position:

~~~java
// JDK 22+; illustrative snippet, does not call printf itself:
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

var option = Linker.Option.firstVariadicArg(1);
~~~

Index marking is **0-based according to the descriptor's argument order**. For `printf`, the first argument is the format pointer (index 0), and the first integer at index 1 is variadic. C's default argument promotion rules must be considered; the FFM linker cannot automatically guess every ABI signature. Renaming the API does not guarantee safe variadic function calls.

### 9.3. `FunctionDescriptor` and canonical C types

`FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)` is an example describing `size_t strlen(const char*)` on **Linux/x64**: `size_t` is 64-bit. On a 32-bit system, the return layout may differ. For C `long`, Linux/x64 is typically 64-bit, whereas Windows/x64 is typically 32-bit.

From JDK 22, `linker.canonicalLayouts()` returns a mapping from canonical C ABI type names to `MemoryLayout`:

~~~java
// JDK 22+, example of checking instead of assuming size_t:
MemoryLayout sizeT = Linker.nativeLinker()
        .canonicalLayouts()
        .get("size_t");
~~~

A cross-platform library must build descriptors based on the actual C header and corresponding ABI. Do not use `ValueLayout.JAVA_LONG` to mechanically substitute for every `long`/`size_t` just because the example worked on a development machine.

## 10. Complete Runnable Example, JDK 22+: Allocating and Reading/Writing Native Memory

Create the file **`FfmMigration22.java`** with the following content. This is a **standalone** program requiring only **JDK 22 or later**, needing no custom C library, using no preview APIs, and requiring no restricted methods.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class FfmMigration22 {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {

            MemorySegment number =
                    arena.allocate(ValueLayout.JAVA_INT);
            number.set(ValueLayout.JAVA_INT, 0, 42);

            MemorySegment word =
                    arena.allocateFrom("Java FFM");

            MemorySegment values =
                    arena.allocateFrom(
                            ValueLayout.JAVA_INT, 2, 3, 5);

            System.out.println(
                    "number=" + number.get(
                            ValueLayout.JAVA_INT, 0));
            System.out.println(
                    "word=" + word.getString(0));
            System.out.println(
                    "sum=" + (
                            values.getAtIndex(
                                    ValueLayout.JAVA_INT, 0)
                            + values.getAtIndex(
                                    ValueLayout.JAVA_INT, 1)
                            + values.getAtIndex(
                                    ValueLayout.JAVA_INT, 2)));
        }
    }
}
~~~

Compile and run:

~~~bash
javac FfmMigration22.java
java FfmMigration22
~~~

**Exact stdout**:

~~~text
number=42
word=Java FFM
sum=10
~~~

Why these names are used:

- `Arena.ofConfined()`: JDK 21+ factory, still valid in 22.
- `arena.allocate(ValueLayout.JAVA_INT)`: allocates a region matching the `int` layout.
- `arena.allocateFrom("Java FFM")`: new C string creation API from JDK 22.
- `arena.allocateFrom(ValueLayout.JAVA_INT, 2, 3, 5)`: native int array allocation API from JDK 22.
- `word.getString(0)`: new string reading API from JDK 22; does not use preview-style `getUtf8String`.
- `number.get(...)`, `number.set(...)`, `values.getAtIndex(...)`: accesses the segment with valid layout and offset/index.
- `try (Arena arena = ...)`: when exiting the block, the memory backing the segments allocated via the arena is freed.

The program does not call the native linker, so it does not necessarily need `--enable-native-access` in JDKs where the methods used here are not restricted. If you mix in `Linker.downcallHandle` or `reinterpret`, check the module's native access permission.

## 11. Complete Runnable Example: Calling `strlen` via FFM on Linux/x64, JDK 22+

This example is for the **Linux/x64 platform where libc provides `strlen` via default lookup**. On that ABI, `size_t` is 64 bits long, so the return type can be described with `ValueLayout.JAVA_LONG`. This is an example comparing method names when migrating from JDK 21 to 22.

Create the file **`FfmStrlen22.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class FfmStrlen22 {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        MemorySegment symbol = linker.defaultLookup()
                .find("strlen")
                .orElseThrow();

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment cText = arena.allocateFrom("FFM 22");

            long bytes = (long) strlen.invokeExact(cText);

            System.out.println("bytes=" + bytes);
        }
    }
}
~~~

Compile and run:

~~~bash
javac FfmStrlen22.java
java --enable-native-access=ALL-UNNAMED FfmStrlen22
~~~

**Stdout on Linux/x64 when `strlen` is found and native access is enabled:**

~~~text
bytes=6
~~~

Data flow:

1. `Linker.nativeLinker()` selects the linker for the current JVM's ABI.
2. `linker.defaultLookup().find("strlen").orElseThrow()` retrieves the C function address. The name `find` is correct for JDK 22; `lookup` will not compile.
3. `FunctionDescriptor.of(ValueLayout.JAVA_LONG, ValueLayout.ADDRESS)` describes the `size_t` return and `const char*` parameter according to the Linux/x64 ABI.
4. `downcallHandle(symbol, descriptor)` returns a MethodHandle with the function address already bound, so `invokeExact(cText)` takes **one** `MemorySegment` argument.
5. `arena.allocateFrom("FFM 22")` creates a NUL-terminated UTF-8 buffer. `strlen` counts bytes before NUL and returns `6`.
6. When `try-with-resources` exits, the arena closes and the buffer is no longer allowed to be used. Do not retain the segment for native code after this point.

If deploying on Windows/x64 or another ABI, **do not** keep `ValueLayout.JAVA_LONG` for a C function return without checking the C ABI; also do not assume default lookup always exposes `strlen` on every OS. This program is runnable **for the stated environment**, not an unconditional cross-platform guarantee.

### 11.1. If raising the minimum target to JDK 23

You can replace:

~~~java
// JDK 22:
MemorySegment symbol = linker.defaultLookup()
        .find("strlen").orElseThrow();

// JDK 23+:
MemorySegment symbol = linker.defaultLookup()
        .findOrThrow("strlen");
~~~

If the project is a library that must still run on JDK 22, keep the first variant. `findOrThrow` is a classic example of a **newly added method**, not a breaking rename of `find`.

## 12. How to Verify Method Names Using the Exact Javadoc

When a project migrates from **version A → version B**, apply the following process instead of renaming by intuition.

### Step 1: lock the version and how it is run

~~~bash
java -version
javac -version
~~~

Also cross-check `maven.compiler.release` / `--release` / Gradle Java toolchain / IDE Project SDK and module-path. Knowing only the JDK installed on your local machine is not enough: CI may use a different JDK.

### Step 2: look up **each class in the exact Javadoc of the target version**

The URLs follow a fixed structure:

~~~text
https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/jdk/incubator/foreign/CLinker.html
https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/MemorySession.html
https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/Arena.html
https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html
https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html
https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/lang/foreign/SymbolLookup.html
~~~

In the target Javadoc, look at **Method Summary** and then **Method Details**, especially the `Since`, `Preview`, `Restricted`, `Parameters`, `Returns`, and `Throws` sections. If a name only exists from a later version, do not use it for an earlier binary/source target.

### Step 3: compare the **full signature**, not just the identifier

Example checklist entry to record in a review:

~~~text
Class/interface:
  SymbolLookup            java.lang.foreign.SymbolLookup
Name:
  find                    (JDK 20+)
Parameters:
  String
Return type:
  Optional<MemorySegment>
Error behavior:
  empty optional if symbol is not found
Replacement/API convenience:
  findOrThrow             (JDK 23+)
~~~

Another example: `Linker.downcallHandle` has bound and unbound overloads; changing from `Addressable` to `MemorySegment` changes the parameter type of `MethodHandle`. Seeing the same method name alone **is not enough** to conclude the code is portable.

### Step 4: check factors **outside Java method names**

- ABI: `sizeof(long)`, `sizeof(size_t)`, alignment, and calling convention.
- Native library: filename, platform loading/lookup, symbol visibility.
- Lifetime: is the arena/session/scope still alive when native code uses the pointer?
- Thread confinement: is a confined arena's segment used on the right thread?
- Restricted API: are flags/native access/preview and module configured properly?
- Encoding: UTF-8 bytes, NUL terminator, buffer size.
- Pointer bounds: zero-length segment, `reinterpret`, who allocates/`free`s the returned pointer?

### Step 5: compile and test on **every JDK committed to be supported**

A library intending to support JDK 21 and 22 needs at least two build/test profiles or two source-sets/adapters with the appropriate APIs. Because JDK 21 uses preview, "compile once" does not guarantee jumping to the final 22 API; compilation errors are signals to update the contract, not to tweak flags randomly.

## 13. Common Errors When Migrating FFM and How to Narrow Them Down

| Symptom | Common cause | What to check/fix |
| --- | --- | --- |
| `package jdk.incubator.foreign does not exist` | Using incubator imports on a JDK that removed the module, or missing the old add-modules flag | Cross-check target JDK and package; 19+ uses `java.lang.foreign` |
| `package java.lang.foreign does not exist` | Compiling with JDK 17/18 or wrong actual JDK | Check `javac -version`; you cannot get the API just by adding an import |
| `cannot find symbol: method lookup(String)` | Bringing `SymbolLookup.lookup` from 17–19 to 20+ | Use `find` (or `findOrThrow` on 23+) |
| `cannot find symbol: method findOrThrow` | Using JDK 23 convenience method with a JDK 22 target | Replace with `find(...).orElseThrow()` |
| `cannot find symbol: method openConfined` | Using JDK 20 `Arena.openConfined` on JDK 21/22 | Replace with `Arena.ofConfined` |
| `cannot find symbol: method allocateUtf8String` | Using old JDK 20/21 allocation name on JDK 22 | `arena.allocateFrom(text)` |
| `cannot find symbol: method getUtf8String` | Using JDK 20/21 string read name on JDK 22 | `segment.getString(offset)` |
| `cannot find symbol: method allocateArray` | Using preview `SegmentAllocator.allocateArray` on JDK 22 | `arena.allocateFrom(layout, values...)` |
| `cannot find symbol: method allocateNative` | Using old static `MemorySegment.allocateNative` with the new API | Switch to `arena.allocate(...)` |
| `cannot find symbol: class VaList` | JDK 21 removed the preview `VaList` abstraction | Design the descriptor and `Linker.Option.firstVariadicArg` for the target ABI |
| `method downcallHandle cannot be applied` | Symbol/descriptor/options types or overload differ across versions | Cross-check bound/unbound, `MemorySegment` carrier, and actual signature |
| `WrongMethodTypeException` | `invokeExact` has mismatched Java method handle carrier/arity/return | Check descriptor, argument list, return cast, and `MethodHandle.type()` |
| `IllegalCallerException` | Restricted native-access operation is not granted permission | Enable native access for the right module/flag per JDK |
| Runtime warning about restricted/native access | Newer JDK warns that a module is using native APIs | Enable `--enable-native-access`; test `--illegal-native-access=deny` on supporting JDKs |
| `NoSuchElementException` on symbol lookup | Library/symbol is not exposed on the OS/ABI | Distinguish `defaultLookup` from `libraryLookup`; verify actual symbol |
| `IllegalStateException` when accessing segment | Arena/scope has been closed | Do not retain segment/pointer beyond its lifetime |
| `WrongThreadException` | Confined arena used from the wrong owner thread | Design with a shared arena or move the work to the owner thread |
| Native crash even though Java compiles | Wrong C ABI descriptor, wrong lifetime/pointer/bounds | Check C header, canonical layouts, ownership; do not just fix method names |

**Do not fix a native crash by changing `invokeExact` to `invoke` without understanding the signature.** `invoke` can perform some conversions per MethodHandle rules, but it does not prove the C ABI is right. FFM still allows unsafe native calls and can crash the JVM if the descriptor is wrong.

## 14. Pre-Merge FFM Source Code Verification Checklist

You can use this checklist for every Java upgrade PR:

- [ ] Recorded **source JDK**, **target JDK**, OS/ABI, and API stage (incubator/preview/final)?
- [ ] Replaced `jdk.incubator.foreign` with `java.lang.foreign` if past milestone 19?
- [ ] `CLinker`/`Linker.nativeLinker` used for the right version?
- [ ] `CLinker.systemLookup`/`Linker.defaultLookup` and `SymbolLookup.loaderLookup/libraryLookup` have the right scope?
- [ ] `SymbolLookup.lookup`, `find`, and `findOrThrow` match the version milestone?
- [ ] `ResourceScope`/`MemorySession`/`Arena` along with `scope()` re-checked?
- [ ] `Arena.openConfined` ↔ `Arena.ofConfined` not mixed up?
- [ ] `MemorySegment.allocateNative`/`arena.allocate` updated to the right signature?
- [ ] `allocateUtf8String` ↔ `allocateFrom(String)` and `getUtf8String` ↔ `getString` fixed properly?
- [ ] `allocateArray` ↔ `allocateFrom(layout, values...)` uses the right overload?
- [ ] `MemoryAddress`/`Addressable` → `MemorySegment` and method handle carrier types cross-checked?
- [ ] `upcallStub` has the target's right `session/scope/arena` lifetime argument?
- [ ] If using `VaList` or variadic C calls, checked `Linker.Option.firstVariadicArg` and promotions?
- [ ] `FunctionDescriptor`, C ABI, `canonicalLayouts`, and return/argument widths match the platform?
- [ ] Not calling `reinterpret` or retaining pointers beyond lifetime without permission/ownership?
- [ ] Preview/incubator/native access compiler flags and Maven/Gradle toolchain match the version?
- [ ] Ran **compile + test** on the lowest supported JDK itself, not just the latest version?

## 15. Review Questions

1. Why can't a project using `CLinker.getInstance()` from JDK 17 just change Java compiler flags to run the final JDK 22 FFM API?
2. In JDKs 19, 20, and 22, which method is used to look up a symbol from `SymbolLookup`?
3. When the minimum target is JDK 22, can `findOrThrow("strlen")` be used? Why?
4. How did the factory for creating a confined arena change its name between JDK 20 and 21?
5. When upgrading from JDK 21 preview to 22 final, what should `allocateUtf8String`, `getUtf8String`, and `allocateArray` be changed to?
6. Why can't `MemorySegment.allocateNative` from JDK 19/20 be replaced by an arbitrary `new MemorySegment(...)` in JDK 22?
7. Why can't `MemoryAddress` and `MemorySegment` be swapped in `MethodHandle.invokeExact` without checking the carrier type?
8. How does `Linker.downcallHandle(symbol, descriptor)` differ from `Linker.downcallHandle(descriptor)` in terms of arguments at invocation time?
9. If JDK 22 code calls `strlen` on Linux/x64, which layout does the C `size_t` return typically map to? Can that be applied mechanically to Windows/x64 or 32-bit?
10. When upgrading from JDK 21 to 22, is `--enable-preview` still needed? What about `--enable-native-access` for restricted downcalls?
11. Why is an address created by `MemorySegment.ofAddress(0x1000L)` not automatically safe to dereference?
12. When seeing `IllegalCallerException` or a native-access warning, what should be distinguished from a `cannot find symbol` error?

**Suggested answers:** (1) packages/classes and signatures changed across multiple redesigns; (2) 19 `lookup`, 20 and 22 `find`; (3) no, the convenience API exists from 23, 22 uses `find(...).orElseThrow()`; (4) `openConfined` → `ofConfined`; (5) `allocateFrom`, `getString`, and `allocateFrom(layout, values...)`; (6) allocation goes through `Arena/SegmentAllocator` and manages lifetime; (7) the Java address/handle method type changed, and `invokeExact` requires an exact signature; (8) unbound takes an extra function address argument; (9) `JAVA_LONG` on Linux/x64, must check the ABI on other machines; (10) preview is not needed for the final API, but restricted FFM still requires native access for the appropriate module; (11) bounds, lifetime, and ownership are unknown; (12) native permission errors differ from missing method name/symbol lookup errors.

## 16. Versioned References

**Official JEPs:**

- [JEP 412 — Foreign Function & Memory API (Incubator), JDK 17](https://openjdk.org/jeps/412)
- [JEP 419 — Foreign Function & Memory API (Second Incubator), JDK 18](https://openjdk.org/jeps/419)
- [JEP 424 — Foreign Function & Memory API (Preview), JDK 19](https://openjdk.org/jeps/424)
- [JEP 434 — Foreign Function & Memory API (Second Preview), JDK 20](https://openjdk.org/jeps/434)
- [JEP 442 — Foreign Function & Memory API (Third Preview), JDK 21](https://openjdk.org/jeps/442)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)

**Versioned API/Javadoc:**

- [JDK 17 `CLinker` and `SymbolLookup`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/jdk/incubator/foreign/CLinker.html)
- [JDK 19 `MemorySession`](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/MemorySession.html)
- [JDK 19 `SymbolLookup`](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 20 `Arena`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 20 `SymbolLookup`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 21 `Arena` and factories](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 22 `SegmentAllocator`: `allocateFrom`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
- [JDK 22 `MemorySegment`: `getString`/`setString`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [JDK 22 `Linker`: `canonicalLayouts` and downcalls](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [JDK 23 `SymbolLookup`: `findOrThrow`](https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [JDK 25 — Restricted Methods and Native Access](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)

**Conclusion:** When migrating FFM code, there is no safe "bulk rename" operation. **Lock the target JDK**, cross-check each symbol against the **versioned Javadoc**, verify the **full signature + carrier + lifetime + ABI + flags**, and then compile/run with that exact JDK. Especially easy-to-confuse names include `SymbolLookup.lookup/find/findOrThrow`, `Arena.openConfined/ofConfined`, `MemorySegment.allocateNative/Arena.allocate`, `allocateUtf8String/allocateFrom`, `getUtf8String/getString`, and `CLinker/Linker`.
