# The Role of jextract in Generating Java Code from C Library Headers

## 1. The Problem: From C API to Java Without Writing Every Binding Manually

Suppose you have an existing C library:

```c
/* minimath.h */
int add_numbers(int a, int b);
int scale(int value, int factor);
```

From Java, you want to call those two functions without manually writing a bunch of symbol lookup code, `FunctionDescriptor`, `Linker.downcallHandle`, `MethodHandle.invokeExact`, and layout-handling code when the API grows large. **jextract** solves this binding generation problem.

**jextract is a tool that parses C headers (`.h`) and generates Java source code using the Foreign Function & Memory API (FFM API) to interact with a native library.** It reads the C interface *declarations*, models functions/types/constants/structs, and creates the corresponding Java APIs. Java users can then call wrappers whose names are close to the C function names, while the generated code performs the FFM linking underneath.

Pipeline diagram:

```text
           C HEADER                 C IMPLEMENTATION
         minimath.h                   minimath.c
       Function, struct,             Machine code definitions
       typedef, macro                for C functions
       declarations...
             │                            │
             ▼                            ▼
        jextract + clang         C compiler + linker
             │                            │
             ▼                            ▼
    GENERATED JAVA SOURCES          libminimath.so
    demo.bindings.NativeMath             │
    (wrappers, layouts,                  │
     function descriptors,               │
     MethodHandles...)                   │
             │                            │
             ▼                            │
        javac -> .class                  │
             │                            │
             └───────────┬────────────────┘
                         ▼
                  JAVA APPLICATION
              NativeMath.add_numbers(...)
                         │
                         ▼
              FFM downcall -> native C
```

**Key point to remember:** jextract does not convert a C implementation into Java, does not translate a `.c` file into bytecode, does not compile a `.so`, and does not automatically allocate/free every native pointer. It **creates a Java bridge from C declarations**. The actual native binary still needs to be compiled, distributed, and loaded properly.

### 1.1. Different Roles of the FFM API and jextract

| Component | What does it do? | Who provides it? |
| --- | --- | --- |
| `java.lang.foreign` | Standard Java API for managing foreign memory and calling native functions | JDK **22+** (final since JEP 454) |
| `Linker` / `FunctionDescriptor` / `MemoryLayout` | Low-level building blocks to create downcalls/upcalls and describe ABI | FFM in the JDK |
| `jextract` | Parses C headers using Clang and **generates Java bindings** based on FFM | Standalone tool from the OpenJDK jextract project |
| C compiler | Compiles C implementation into a native shared library | GCC, Clang, MSVC... |
| Native shared library | Contains the actual machine symbols/functions to execute | Output of the C compiler/linker |
| Generated Java binding | Java wrapper using FFM to find/call native symbols and access layouts | Output of jextract |

**jextract is not the JDK's `javac` command** and is not included by default in every JDK installation. You need to download a jextract build compatible with the JDK you will use, or build the tool yourself following the project instructions. For this exercise, prefer **JDK 22 or later** because `java.lang.foreign` is finalized; the chosen jextract build must also target the runtime JDK's API. If using a newer release, check the actual version before copying commands or generated source.

## 2. What Does jextract Take as Input and What Does It Produce?

A jextract run typically takes:

- **Main header:** the `.h` file containing the library's public interface.
- **Include directories:** paths for Clang to locate headers `#include`d from the main header.
- **Macro definitions and compiler flags:** preprocessor conditions such as `-D FEATURE_X=1`, target ABI, and necessary includes.
- **Code generation target:** output directory `--output` and Java package `--target-package`.
- **Library name:** the `--library` parameter (when you want the generated code to load the library itself).
- **Symbol filtering options:** only generate bindings for the declarations needed when the library is too large.

A typical recipe published in the OpenJDK jextract Guide:

```bash
jextract \
  --include-dir /path/to/native/include \
  --output generated \
  --target-package com.example.nativeapi \
  --library mylib \
  /path/to/native/include/mylib.h
```

The `/path/to/...` paths here are **illustrative placeholders**, not a command to copy and run immediately without a library. The command creates Java files by package, for example `generated/com/example/nativeapi/mylib_h.java` and separate classes for structs/unions/function pointer types if the header has them.

### 2.1. Layers of Generated Artifacts

| Declaration in C header | Java binding typically generated | Meaning |
| --- | --- | --- |
| `int add(int,int);` | A static Java wrapper `add(int,int)`, along with accessors `add$address()`, `add$descriptor()`, `add$handle()` | Call native C and inspect metadata |
| `struct Point { int x; int y; };` | Class `Point`, layout/offset/field getters/setters/allocate helpers | Access and allocate C struct |
| `typedef int MyInt;` | Corresponding layout/typedef metadata | Preserve C type mapping on the ABI |
| `enum Mode { A=1, B=2 };` | Constant accessors; not necessarily a Java `enum` | Correspond to C symbolic constants |
| `#define MAX_SIZE 256` | Accessor for macro constant supported by the tool | Avoid manually copying some constants |
| `typedef int (*callback_t)(int,int);` | Helper class for function pointer/upcall stub | Java callback invoked by native code |
| `extern int count;` | Global-variable layout/segment/getter/setter | Read/write exported C global |
| `union Packet { ... };` | Class/layout corresponding to the union | Compute offsets and field interpretation |
| `int f(int count,...);` | Variadic invoker API specialized by parameter types | Partial support for variadic C ABI |

**Depending on the jextract version and target C header**, specific Java types, class names, overloads, and the number of generated files may vary. When writing production code, **read the actual files just generated** and check `jextract --version`, rather than assuming every version produces source identical to illustrative examples.

### 2.2. jextract Does Not Need the C Function Body

For example, with only the header:

```c
/* math_api.h */
int add(int a, int b);
```

jextract can build a Java wrapper based on the declaration. However, if there is no native library **actually exporting the `add` symbol**, the Java wrapper will fail when linking/calling the symbol. This is similar to `extern` declarations in C: the header describes the API, not the implementation.

Therefore, testing bindings must always include **the header, native binary, and runtime loading**. Merely seeing generated `.java` files does not prove the application calls native code successfully.

## 3. How jextract Reduces Hand-Written FFM Code

Without jextract, a C call typically requires manual FFM logic like this:

```java
// JDK 22+ fragment, assuming linker, lookup, and arena
// have been prepared and kept alive for the appropriate duration.
MemorySegment fn = lookup.find("add_numbers")
        .orElseThrow();

FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

MethodHandle handle = linker.downcallHandle(fn, descriptor);

int result = (int) handle.invokeExact(20, 22);
```

This is a **fragment**, not a standalone Java program. With hundreds of native functions, manually maintaining these descriptions is very error-prone: argument order, ABI `long`, signatures, struct padding, or pointer carriers.

jextract automatically generates a wrapper roughly looking like:

```java
// ILLUSTRATIVE SNIPPET of the generated binding idea,
// not the full file jextract outputs.
public static int add_numbers(int a, int b) {
    // ... invokes the MethodHandle created from the C symbol and descriptor...
    return /* native result */;
}
```

The pseudo-fragment above intentionally omits the concrete MethodHandle body: the generated implementation **depends on the tool version**. What remains conceptually stable is that the Java client calls `add_numbers(20,22)` while the generated code handles `SymbolLookup`/`downcallHandle` and FFM mapping.

In a jextract release that supports metadata accessors, you can also look up:

```java
// Fragment: functions corresponding to the add_numbers symbol.
MemorySegment address = NativeMath.add_numbers$address();
FunctionDescriptor fd = NativeMath.add_numbers$descriptor();
MethodHandle mh = NativeMath.add_numbers$handle();

System.out.println(mh.type()); // On a matching int32 ABI: (int,int)int
```

These metadata accessors are described in the OpenJDK jextract Guide. They help **verify the generated binding**, but do not replace checking against the actual C header and binary ABI.

## 4. Complete Example: From C Header to Java Call

This example follows the easiest-to-observe pipeline: create a small C library, generate bindings with jextract, compile the generated Java sources together with the Java application, and call the function.

**Environment assumptions:** Linux x86-64, GCC/Clang supporting C11, a **JDK 22+**, and a **jextract build compatible with that exact JDK** downloaded and added to `PATH`. The C code uses `int`; on common Linux x86-64, `int` is signed 32-bit so it maps to the Java carrier `int`. For other OS/ABIs, you must re-verify.

### 4.1. Directory Structure

```text
jextract-minimath/
├── native/
│   ├── minimath.h
│   └── minimath.c
├── src/
│   └── MiniMathDemo.java
├── generated/                  # jextract generates Java sources here
└── build/
    ├── classes/                # javac creates .class
    └── libminimath.so          # cc creates native library
```

Do not use `javac -h` in this pipeline. `javac -h` is for JNI header generation in the **Java native declaration → C header** direction; jextract goes in the **C header → Java FFM bindings** direction.

### 4.2. C Header: `native/minimath.h`

```c
#ifndef MINIMATH_H
#define MINIMATH_H

#ifdef __cplusplus
extern "C" {
#endif

int add_numbers(int a, int b);
int scale(int value, int factor);

#ifdef __cplusplus
}
#endif

#endif
```

Both functions are in the public C API. The include guard prevents duplicate declarations. The `extern "C"` section only takes effect when the header is used by a C++ compiler, to provide C linkage; the example source file itself is C. The `extern "C"` braces do not turn jextract into a general-purpose C++ parser.

### 4.3. C Implementation: `native/minimath.c`

```c
#include "minimath.h"

int add_numbers(int a, int b) {
    return a + b;
}

int scale(int value, int factor) {
    return value * factor;
}
```

No JNI-style symbol like `Java_demo_NativeMethod` is needed, nor is there a `JNIEnv *` parameter. They are **ordinary C functions**. They will be called directly via FFM downcall through the Java wrapper generated by jextract.

To keep the example deterministic and avoid signed integer overflow undefined behavior in C, Java will only pass small numbers. This article does not use the demo to claim that C multiplication is always safe for every `int`.

### 4.4. Compiling the C Shared Library on Linux

From the root of the `jextract-minimath` directory:

```bash
mkdir -p build/classes generated

cc -std=c11 -Wall -Wextra -O2 -fPIC -shared \
  native/minimath.c -o build/libminimath.so
```

`-fPIC -shared` creates a Linux shared object. The output `build/libminimath.so` contains the exported symbols `add_numbers` and `scale`. If the compiler attaches hidden visibility or C++ name mangling to the symbols, jextract can still generate code from the header, but Java will fail to resolve the expected symbol names.

You can inspect symbols on Linux:

```bash
nm -D --defined-only build/libminimath.so
```

The actual output also contains addresses/metadata, so the exact stdout of `nm` is not guaranteed. What needs to be confirmed is that **both names `add_numbers` and `scale` are present** in the exported dynamic symbols.

### 4.5. Checking Tools and Generating Java Bindings

Run:

```bash
java -version
jextract --version
```

The `jextract --version` command shows the tool version, target JDK info, and Clang version per release. If the jextract binary was built for a different JDK or is missing native dependencies, **stop and choose the matching toolchain** before generating code.

Generate bindings:

```bash
jextract \
  --output generated \
  --target-package demo.bindings \
  --header-class-name NativeMath \
  --library minimath \
  native/minimath.h
```

Meaning:

- `native/minimath.h`: the main header jextract needs to parse.
- `--output generated`: puts generated sources under the `generated` directory.
- `--target-package demo.bindings`: package of the generated classes.
- `--header-class-name NativeMath`: names the root class `NativeMath` instead of letting jextract infer the name from `minimath.h`.
- `--library minimath`: tells the generated binding to load the native library with logical name `minimath`. On Linux, that name maps to `libminimath.so` via the library loader mechanism.

In the output directory, the example typically has:

```text
generated/
└── demo/
    └── bindings/
        └── NativeMath.java
        (other helper/generated files if needed by the tool)
```

The root class name is fixed by `--header-class-name`; **the exact file structure depends on the jextract version**. If the tool does not recognize an option, check `jextract --help` of your installed version and adjust the command according to the release; do not try to use output generated by a different release.

### 4.6. Java Client: `src/MiniMathDemo.java`

```java
import static demo.bindings.NativeMath.add_numbers;
import static demo.bindings.NativeMath.add_numbers$handle;
import static demo.bindings.NativeMath.scale;

public final class MiniMathDemo {
    private MiniMathDemo() {
    }

    public static void main(String[] args) {
        int sum = add_numbers(20, 22);
        int multiplied = scale(7, 6);

        System.out.println("sum: " + sum);
        System.out.println("scaled: " + multiplied);
        System.out.println(
                "add handle type: " + add_numbers$handle().type());
    }
}
```

**Important point:** the Java client code **does not manually write `FunctionDescriptor` or `Linker.downcallHandle`**. The generated binding handles them from the C declarations. We only import the static wrappers and one metadata accessor to demonstrate the FFM signature.

According to the OpenJDK jextract Guide, a C function `int add_numbers(int,int)` on a 32-bit `int` ABI will have a Java wrapper like:

```text
int add_numbers(int,int)
```

and `add_numbers$handle().type()` is:

```text
(int,int)int
```

It represents the **MethodType of the bound downcall handle**, not C names magically carrying Java signatures. C type mapping is still determined by jextract according to the compiler/ABI when parsing the header.

### 4.7. Compiling and Running Java

From the root directory, on a Linux shell with `find`:

```bash
javac -d build/classes \
  $(find generated -type f -name '*.java') \
  src/MiniMathDemo.java
```

Use the generated Java source files **from the same jextract run**; do not manually create a stub `NativeMath.java` file to pretend a binding exists.

By default `--library minimath` uses native OS library lookup (not automatically `java.library.path`). Configure `LD_LIBRARY_PATH` **before starting the JVM** so the dynamic linker can find `build/libminimath.so`:

```bash
LD_LIBRARY_PATH="$PWD/build" \
  java --enable-native-access=ALL-UNNAMED \
       -cp build/classes MiniMathDemo
```

`--enable-native-access=ALL-UNNAMED` grants permission to use restricted FFM operations for the application running on the unnamed module/classpath, which is suitable for a demo. In modularized systems, grant it only to the required named modules. Do not ignore native access warnings/exceptions if the actual runtime requires additional configuration.

**Expected stdout on the compatible toolchain stated above:**

```text
sum: 42
scaled: 42
add handle type: (int,int)int
```

If the dynamic loader cannot find the library, the JVM will report an error at the load/symbol lookup step, **not** print these three success lines. If the generated code/FFM API is incompatible with the JDK, errors may occur right during Java compilation; check the exact versions and generated source.

### 4.8. Why Is This Example a C→Java Demo and Not JNI?

| Comparison | jextract + FFM | Traditional JNI |
| --- | --- | --- |
| Declaration direction | **C header → generated Java binding** | Usually **Java `native` declaration → native C function** |
| Java calls | Tool-generated wrapper `add_numbers(20,22)` | Java `native int addNumbers(...)` |
| C implementation | `int add_numbers(int,int)` | JNI function like `Java_demo_X_addNumbers(JNIEnv*,jclass,...)` |
| Generation tool | `jextract` | `javac -h` generates C header from Java native method |
| Call mechanism | FFM `Linker`/`MethodHandle` (downcall) | JNI native method entry point |
| Needs native library? | **Yes** | **Yes** |
| Solves ownership automatically? | **No** | **No** |

JNI remains useful when Java must be deeply integrated into C or with legacy native APIs already based on JNI. jextract + FFM is especially convenient when **a public C API already exists** and you want to mechanically generate wrappers, reducing bridge code to maintain.

## 5. Generated Code Details: C Functions and Accessors

Given C:

```c
void foo(int x);
```

The OpenJDK jextract Guide describes a set of APIs of the form:

```java
// ILLUSTRATION of the generated signature form, not a standalone Java file.
public static void foo(int x) { /* native call */ }

public static MemorySegment foo$address() { /*...*/ }
public static FunctionDescriptor foo$descriptor() { /*...*/ }
public static MethodHandle foo$handle() { /*...*/ }
```

The methods serve different roles:

1. `foo(...)`: the API that the Java application uses directly; semantics close to the C function.
2. `foo$address()`: address of the native symbol, represented as a `MemorySegment`.
3. `foo$descriptor()`: `FunctionDescriptor` describing native parameter/return layouts.
4. `foo$handle()`: `MethodHandle` created by the linker and used by the wrapper.

To test a function in a project, you can print these objects or write assertions for `MethodHandle.type()`. However, **the descriptor is inferred from the header**, not a binary ABI verifier. If you use the wrong header version or compile the C library with different macros/struct packing, the generated Java may be wrong even though the source code looks valid.

### 5.1. Generating Code Does Not Mean Providing a Well-Designed Domain Java API

Names like `add_numbers`, `struct Some_Type`, or `foo$handle` intentionally stay close to C declarations. That is convenient for 1-to-1 mapping, but not necessarily a friendly Java API. Production libraries usually have two layers:

```text
Native C library
      ↑
Generated jextract bindings
      ↑
Java façade / domain-level API
      ↑
Java application
```

The façade layer can:

- Rename according to Java conventions (e.g., `add` instead of `add_numbers`).
- Validate inputs and translate native error codes into exceptions.
- Create/close `Arena` in the proper scope, hiding raw pointers from callers.
- Convert a `MemorySegment` containing a UTF-8 C string into a Java `String` using the appropriate API.
- Hide OS-specific constants/layouts behind a stable Java contract.
- Ensure native resources are freed exactly once.

**You should not necessarily edit generated sources directly.** Creating an external wrapper ensures that future regenerations will not wipe out manual changes.

## 6. C Type Mapping: What Does jextract Handle Automatically and What Still Needs Checking?

When parsing headers with Clang, jextract sees C type information, aliases, and platform-specific declarations, then chooses the corresponding FFM layouts. It helps avoid common mistakes made when mapping types by eye.

The table below is a typical model; actual mapping depends on the **ABI and jextract version**:

| C declaration | Commonly used Java carrier / FFM | Notes |
| --- | --- | --- |
| `int` on Linux x86-64 | `int` / `ValueLayout.JAVA_INT` | Check ABI, do not blindly assume for every target |
| 16-bit `short` | `short` / `JAVA_SHORT` | Java is signed; C has unsigned variants |
| 64-bit `long long` | `long` / `JAVA_LONG` | Distinguish from C `long` |
| `float` | `float` / `JAVA_FLOAT` | ABI float arguments/return |
| `double` | `double` / `JAVA_DOUBLE` | ABI double arguments/return |
| `char *` or `void *` | `MemorySegment` / `ADDRESS` | Java `String` cannot be passed directly as a C pointer |
| `struct Point` by value | `MemorySegment` with `GroupLayout` | C ABI padding/return conventions must match |
| `struct Point *` | `MemorySegment` representing a pointer | Does not automatically know lifetime, ownership, or element count |
| `size_t` | 32/64-bit carrier depending on ABI | Do not assert it is always Java `long` on every platform |
| `enum` / numeric macros | Values/constants by inferred C type | Does not automatically become a Java domain enum |

**Especially with `long`:** C `long` on Linux x64 is usually 64-bit, whereas on Windows x64 it is usually 32-bit; Java `long` is always 64-bit. This is why a binding generated on one OS cannot arbitrarily be considered ABI-correct on another OS.

### 6.1. Unsignedness Remains the Java API's Responsibility

If C returns `uint32_t` via a Java `int` carrier, a value with the high bit set to 1 can appear as a negative number in signed Java `int`. jextract does not automatically turn every unsigned type into an arbitrary-precision Java number.

A Java façade can do:

```java
// Fragment: rawUint32 is an int carrying the exact 32 bits of data.
long unsignedValue = Integer.toUnsignedLong(rawUint32);
```

In the reverse direction, you must validate the range before narrowing from Java `long` down to unsigned 32-bit C. jextract helps build *bit width/type* bindings, but does not design all business constraints for you.

### 6.2. Pointers and Strings Are Not the Same Type

C declaration:

```c
int consume_text(const char *utf8);
```

Because it has a C pointer parameter, the generated Java wrapper typically requires a `MemorySegment`. The Java client must prepare a native NUL-terminated string in an arena:

```java
// Fragment assuming the generated function consume_text() already exists.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment text = arena.allocateFrom("hello");
    int rc = consume_text(text);
    // Process rc before the arena closes.
}
```

This is a **fragment**; `Arena`/`MemorySegment` need imports, and `consume_text` is a hypothetical wrapper in bindings generated from a header with that function. `Arena.allocateFrom(String)` encodes UTF-8/NUL-termination per the FFM API and keeps the buffer alive within the block. **If the native API stores the pointer after returning**, you must not close the arena immediately; a different ownership/lifetime design is required.

### 6.3. Struct ABI Is More Complex Than Individual Field Sizes

In C:

```c
struct Mixed {
    char tag;
    int value;
    double weight;
};
```

An ABI layout typically has padding between `tag` and `value`, and requires alignment for `double`. If Java simply adds `1 + 4 + 8` and forces a 13-byte struct, it will very likely violate the ABI. jextract is helpful because Clang has already analyzed offsets/alignment for the target compiler, and generates the `MemoryLayout` along with field accessors for that declaration.

**Even so**, if the native binary is built with `#pragma pack`, a different target, different macros, or a compiler ABI that does not match when jextract ran, the generated layout can still be wrong. The exact header/toolchain is part of the interface.

## 7. Generating Bindings for struct/union: Not Just Function Wrappers

Suppose a C header declares:

```c
struct Point {
    int x;
    int y;
};
```

The OpenJDK jextract Guide describes that the generated `Point` class may contain:

```java
// SCHEMA of generated API — illustrative, does not compile standalone.
public static GroupLayout layout();
public static long sizeof();

public static long x$offset();
public static ValueLayout.OfInt x$layout();
public static int x(MemorySegment point);
public static void x(MemorySegment point, int value);

public static MemorySegment allocate(SegmentAllocator allocator);
public static MemorySegment allocateArray(
        long count, SegmentAllocator allocator);
public static MemorySegment asSlice(
        MemorySegment array, long index);
```

Here this is only a **signature listing**, not Java declarations with bodies. Generated structs/unions may reside in separate files rather than the root header class.

To use it:

```java
// Fragment: Point is the class generated by jextract from struct Point.
// This is the same pattern as the example in the OpenJDK jextract Guide.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment point = Point.allocate(arena);
    Point.x(point, 10);
    Point.y(point, 5);

    System.out.println(Point.x(point)); // 10
    System.out.println(Point.y(point)); // 5
}
```

**Benefit of jextract:** you do not need to manually write `MemoryLayout.structLayout`, compute the `byteOffset` of `x`/`y`, or write every accessor. However, **closing the arena is the caller's responsibility**, and `point` must not be used once the backing memory's lifetime has ended.

### 7.1. Struct Pointer vs. Struct Value

If a C function returns `struct Point *`, the generated Java may receive a `MemorySegment` carrying a pointer. This **does not automatically grant permission to free** or know whether there is one or many `Point`s. Some generated helpers provide `reinterpret` to create a struct-sized view and attach its lifetime to an `Arena`.

Conceptual example per the jextract Guide:

```java
// Fragment illustrating when the C library defines:
// struct Point *create_point(void);
// void delete_point(struct Point *);
//
// Requires corresponding generated wrappers and owner contract.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment raw = create_point();
    MemorySegment point = Point.reinterpret(
            raw, arena, NativeLib::delete_point);

    System.out.println(Point.x(point));
}
// delete_point is registered as cleanup if the generated API/version
// and native ownership contract actually support this pattern.
```

The snippet above **is not a standalone runnable sample**: `NativeLib` is a placeholder representing the actual generated header class in the project, and must be replaced with the generated name. Only use cleanup if the native contract specifies **caller owns** the pointer and must call `delete_point` exactly once. **Do not use with borrowed pointers, static memory, or opaque handles.**

### 7.2. Array-of-structs

For arrays of C records, helpers like `Point.allocateArray(n, arena)` and `Point.asSlice(array, i)` help determine the **stride according to the struct layout** rather than just multiplying by the size of `int`. This is especially important when the struct has padding.

However, the element count **n** must still come from the C contract or validated data; do not infer n from a raw pointer. Seeing only a pointer is not enough to know how long the target region is.

## 8. Callback Functions: jextract Can Generate Classes for Function Pointer Typedefs

A C interface may define:

```c
typedef int (*callback_t)(int a, int b);
int run_callback(callback_t cb);
```

jextract typically generates a `callback_t` class (exact name depends on declaration/tool version) supporting:

- `descriptor()`: describes the callback signature.
- `allocate(Function implementation, Arena arena)`: creates a native-callable upcall stub for a Java callback.
- `invoke(MemorySegment functionPointer, ...)`: invokes a function pointer received from native code.

A fragment per the official guide:

```java
// Fragment: run_callback() is an existing generated wrapper;
// callback_t is the class jextract generates from the typedef.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment callback =
            callback_t.allocate((a, b) -> a + b, arena);

    int result = run_callback(callback);
    System.out.println(result);
}
```

Here `run_callback` in C must actually invoke the callback with the matching signature and **must not retain the callback after the arena is closed**. The generated upcall stub only has a lifetime corresponding to the arena; the Java callback may be invoked on a native thread, so exceptions, synchronization, thread confinement, and FFM upcall restrictions must be considered.

**jextract generates the basic adapter; it does not decide how long a callback is allowed to run.** If the C SDK keeps the callback for asynchronous invocation, Java must keep the stub and arena alive until registration is safely cancelled.

## 9. Constants, Enums, Typedefs, and Global Variables

### 9.1. Numeric Macros and Enum Constants

C header:

```c
#define MY_LIMIT 256
enum Mode { MODE_OFF = 0, MODE_ON = 1 };
```

jextract can generate accessors for numeric constants, such as `MY_LIMIT()`, `MODE_OFF()`, and `MODE_ON()`. They are not necessarily a Java `enum Mode`; this is an intentional choice to reflect how C allows enum values to be used as integers and bitmasks.

**Does not apply to all macros:** function-like macros such as `#define SQUARE(x) ((x)*(x))` are not supported by jextract as a ready-made native function. They are C preprocessor logic, not symbols with an address to downcall.

If a function-like macro is needed in Java, you can:

- Rewrite the operation in Java if the semantics are simple and do not depend on the compiler/platform.
- Create an **exported C shim function** wrapping the macro, then have jextract read the shim's header.
- For complex macros, design a verified manual binding.

### 9.2. Typedefs

`typedef int MyInt;` may be generated as a layout alias; `typedef struct Point MyPoint;` may lead to separate struct-related classes or aliases depending on the tool version. Using typedefs still reflects **ABI types**, not necessarily building rich-logic Java domain classes.

### 9.3. Global Variables

C:

```c
extern int global_count;
```

jextract can provide helpers for the layout, the global's segment address, and the corresponding getter/setter. However, reading/writing C globals may require synchronization when multiple native threads access them concurrently. The generated wrapper **does not automatically provide Java memory-model guarantees for all native shared state**.

Do not treat any C global as thread-safe just because the Java accessor is a static method.

## 10. jextract Command Options You Should Know

Summary table of options commonly found in jextract releases per the OpenJDK Guide; **check `jextract --help` and `jextract --version` of your installed build**:

| Option | Role |
| --- | --- |
| `--output <dir>` | Root directory containing generated Java sources |
| `--target-package <package>` or `-t` | Generated Java package |
| `--header-class-name <name>` | Name of the generated root/header class |
| `--library <name-or-path>` or `-l` | Native shared library the generated binding will look for |
| `--include-dir <dir>` or `-I` | Add include search path for Clang |
| `--define-macro NAME=value` or `-D` | Define a macro for the C preprocessor |
| `--include-function <symbol>` | Only generate binding for the specified function when filtering |
| `--include-struct <symbol>` | Select struct to generate within filtered scope |
| `--include-typedef <symbol>` | Select typedef |
| `--include-var <symbol>` | Select global variable |
| `--dump-includes <file>` | List declarations/tool filters from input headers |
| `--use-system-load-library` | Use `System.loadLibrary`/`System.load` for `--library`, shifting library lookup logic to `java.library.path` |
| `--copy-comments` | Include some header comments near declarations in generated bindings |
| `--version` | Show tool/version/JDK/Clang info |

When a header includes many dependencies:

```c
#include "api_types.h"
#include <stdint.h>

int api_process(struct ApiConfig *config);
```

you may need:

```bash
jextract \
  --include-dir /path/to/sdk/include \
  --target-package com.example.sdk \
  --output generated \
  --library sdk \
  /path/to/sdk/include/api.h
```

**The paths in the snippet above are documentation placeholders, not existing files.** If the header fails to parse, check Clang diagnostics and verify include paths, platform macros, compiler defines, target ABI, and packing; do not rush to edit generated Java by hand.

### 10.1. Filtering Properly When a Header Is Too Broad

For example, a C library has 5,000 declarations, but the app only needs one function:

```bash
jextract \
  --include-function api_version \
  --target-package demo.api \
  --output generated \
  --library api \
  /path/to/sdk/include/api.h
```

If `api_version` depends on a struct/typedef that the filter excluded, jextract may report a dependency error and fail to generate the binding. Therefore, a good workflow is:

1. Run `--dump-includes includes.txt` to see the parsed symbol names.
2. Select the relevant functions/structs/typedefs.
3. Keep sufficient dependencies for each declaration.
4. Generate minimal bindings and compile immediately to catch missing types.
5. Add regression tests for the generated API.

Do not arbitrarily rename macros/functions if the C header is already public; use a Java façade if a cleaner API is needed.

### 10.2. Macros and Compile Conditions Must Match the Native Library

Header:

```c
#ifdef USE_WIDE_VALUES
long long get_value(void);
#else
int get_value(void);
#endif
```

If the native library is built with `USE_WIDE_VALUES` but jextract parses the header **without** that macro, Java will generate a descriptor returning `int` instead of 64-bit `long`. Java compilation may still succeed, but calling C can cause a severe ABI mismatch.

When you must use:

```bash
jextract \
  -D USE_WIDE_VALUES=1 \
  --output generated \
  --target-package demo.api \
  --library api \
  /path/to/sdk/include/api.h
```

ensure both **the C compiler and jextract** use the same set of defines. A good toolchain/CI stores the build configuration as a verifiable artifact rather than separating macro flags in two places where they can easily drift.

## 11. Loading C Libraries: `--library` Does Not Replace the Native Binary

When using:

```bash
jextract --library minimath --output generated \
  --target-package demo.bindings \
  native/minimath.h
```

the generated code typically uses native library lookup to load the logical name `minimath`. On Linux it is `libminimath.so`, on Windows typically `minimath.dll`, and on macOS `libminimath.dylib`. The OS dynamic loader mechanism must also resolve **dependencies** of the shared library itself.

For the default OS lookup on Linux, you can run with:

```bash
LD_LIBRARY_PATH="$PWD/build" \
  java --enable-native-access=ALL-UNNAMED \
  -cp build/classes MiniMathDemo
```

If the generated code is configured with `--use-system-load-library`, the `System.loadLibrary` path will search via `java.library.path` instead of the default OS path for the top-level library. When changing this strategy, **regenerate the bindings** and configure the Java launcher accordingly.

**Do not mechanically mix `LD_LIBRARY_PATH` with `-Djava.library.path`** — they serve different loader paths. A binary may load itself but fail to load a dependency; you must check the specific dynamic linker and packaging mechanism.

### 11.1. Header Version and Library Version Must Be Compatible

A C SDK can change:

- Function names or parameters.
- Enum/typedef sizes.
- Offsets inside a `struct`.
- Calling conventions or symbol visibility.
- Pointer ownership semantics.

The same `libfoo.so` filename does not guarantee the ABI stayed the same. Release processes should pin **header version + native binary version + jextract version + target JDK/OS/arch**. If a library bumps its major version, re-test bindings and regenerate when needed.

### 11.2. Symbol Name Errors

If a header declares `extern "C" int add(int,int);` but the binary is built from C++ without C linkage, the symbol may be mangled to another name. Generated jextract code will look up `add` and fail to find it. The fix lies in the **C ABI/exported name**, not in using a Java cast or forcing `MethodHandle.type()`.

Similarly, a `static` native function in a `.c` file is not an exported public symbol for the dynamic linker, so you cannot just declare it in a header and expect jextract to call it.

## 12. jextract Supports C, Not General C++ Headers

A C++ header with templates, overloads, classes, exceptions, and name mangling is not an input that jextract can convert into a full Java API like Java code. According to the OpenJDK jextract Guide, the primary scope is **C headers**.

To use a C++ library:

1. Create a **C-compatible ABI layer**:
   - `extern "C"` functions exporting C names.
   - `void *`/opaque handles to represent C++ objects.
   - `create/destroy` functions with clear ownership.
   - APIs returning error codes instead of letting C++ exceptions cross the boundary.
2. Write a public C header for that ABI layer.
3. Run jextract on the C header.
4. Call through the generated Java bindings and manage the lifecycle.

Example C wrapper of a C++ engine:

```c
/* engine_c.h: illustrative API only. */
#ifdef __cplusplus
extern "C" {
#endif

typedef struct EngineHandle EngineHandle;
EngineHandle *engine_create(void);
int engine_step(EngineHandle *handle);
void engine_destroy(EngineHandle *handle);

#ifdef __cplusplus
}
#endif
```

Because `EngineHandle` is opaque, jextract cannot infer a private layout. That is **by design**: Java uses the `MemorySegment` handle and C wrappers, without reading internal fields of the C++ object.

**Do not force jextract to parse a C++ template class and expect it to generate an equivalent Java subclass.** The bridge requires a separate C ABI contract.

## 13. Important Limitations of jextract

The OpenJDK Guide notes several areas that jextract **does not support or requires manual handling**, depending on the version:

### 13.1. Function-like Macros

`#define SQUARE(x) ((x)*(x))` has no exported function address. There is no `downcallHandle` for such a macro. Write a Java helper or a C shim.

### 13.2. Struct Bitfields

```c
struct Flags {
    unsigned int ready : 1;
    unsigned int mode : 3;
};
```

Bitfield allocation/order depends on the compiler ABI; jextract may warn and **skip bitfield fields**. Do not manually read adjacent bytes as if the field had a generated accessor. If the ABI requires bitfields, expose a C helper:

```c
/* Fragment illustrating the C helper signature. */
unsigned int flags_get_mode(const struct Flags *flags);
```

so Java calls it via the exported helper's binding.

### 13.3. Opaque Structs

`struct Handle;` only declares an incomplete type, without describing fields. jextract cannot generate a class with accurate field accessors for a struct without a definition. Using an opaque handle via C functions is still possible, but Java must not dereference private fields.

### 13.4. C Types Not Directly Supported by FFM

Some `long double` types wider than 64 bits on Linux, types depending on compiler extensions, or vector ABIs may not map to FFM carriers/layouts. If jextract warns about an unsupported type, common options are:
- Use a C shim to convert the return/argument to `double`/integer or an explicit buffer layout.
- Design the API to return data via `void *` + length.
- Limit platform support and test the ABI.

**Do not silently convert an 80/128-bit `long double` to a Java `double`** if full precision must be preserved.

### 13.5. Linker Options and Call-State Capture

Not every `Linker.Option` is expressible via a jextract option. For example, a C function reporting errors via `errno` may need `Linker.Option.captureCallState("errno")` when creating a downcall manually. If the generated binding does not configure capture, the Java API must use another strategy (e.g., a C shim returning the error code/last error in the same call).

**Do not assume jextract will automatically turn `errno` into a Java exception.**

### 13.6. Non-native Scalar Byte Order

Compiler attributes affecting a field's byte order, such as a packed big-endian format of a special struct, may not be automatically translated by the generator into the correct FFM layout. For file formats, byte order must follow the specification; a generated native struct layout does not guarantee on-disk encoding.

### 13.7. Variadic Functions

`printf(const char *, ...)` is a native variadic function. jextract can generate invoker-specializations for specific arguments, rather than a static Java `printf(Object...)` wrapper that automatically handles every format and C ABI.

Using variadics requires specifying the exact **number and types of C arguments** according to the calling convention; a wrong descriptor can be dangerous. When a more stable API is desired, add a C shim with a non-variadic signature.

## 14. Ownership and Memory Safety Rules Do Not Disappear When Generating Code

jextract only builds **the native call layer**. C pointers can still cause:

- Use-after-free if backing memory has already been freed.
- Double-free if both caller and callee consider themselves the owner.
- Memory leak if forgetting to call the proper destructor/release function.
- Out-of-bounds access if a pointer does not carry its actual length.
- Data race when C and Java/native threads modify data concurrently.
- Invalid pointer when passing a heap segment as raw C memory or using the wrong scope.
- Wrong string encoding/NUL termination.

### 14.1. When Java Owns the Native Buffer

Java can do:

```java
// Fragment: consume_bytes is the generated wrapper of:
// int consume_bytes(const void *bytes, size_t len);
try (Arena arena = Arena.ofConfined()) {
    MemorySegment input = arena.allocate(8);
    input.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

    // The carrier type of len (size_t) depends on the target ABI.
    // On common Linux x64, it may be long.
    int status = consume_bytes(input, 8L);
    // Check status, ensuring C does not retain input after returning.
}
```

Do not treat this as a standalone Java file because `consume_bytes` has no implementation/header in the main demo. It illustrates caller ownership: the arena must stay alive throughout the call, then be closed at the right time.

### 14.2. When C Owns the Returned Pointer

C API:

```c
/* Declaration fragment according to a hypothetical library contract. */
void *buffer_create(size_t bytes);
void buffer_destroy(void *memory);
```

The Java wrapper receives a `MemorySegment` that may only represent an **address value**. To dereference it, you need to know the size, alignment, and lifetime. Reinterpreting (`reinterpret`) an address with the wrong size can lead to a JVM crash, even though the FFM API checks bounds according to the view.

Usually there should be a Java domain wrapper managing:
- The `pointer + length` pair.
- NULL checks.
- The proper deallocator `buffer_destroy` and exactly-once release.
- Not using the pointer after release.
- Not letting callbacks use a freed pointer.

**jextract cannot guess who owns memory from the C type `void *` alone.**

### 14.3. Callback Lifetime

jextract-generated callback helpers may use an `Arena` to allocate an upcall stub. If C stores the function pointer to call later, the callback scope must **last long enough**; do not let C call the stub after the arena closes. If C invokes the callback on a native thread, the Java callback must avoid assumptions about thread-local context, locks, and exceptions crossing the boundary.

### 14.4. Native Access Permissions

Generated bindings use restricted FFM APIs when loading libraries or creating linker/upcall stubs. On JDK 22+ applications typically run with:

```bash
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes MiniMathDemo
```

for classpath demos; for named modules, configure the module name. Native access is a **sensitive permission** because an incorrect descriptor/ownership can cause memory corruption or a crash. Do not enable it broadly for untrusted code in production applications.

## 15. jextract and Controlling C SDK Changes

### 15.1. When Should Generated Code Be Created?

According to the OpenJDK Guide, jextract is typically run **when integrating a native library**, and the generated sources are then added to the project or build output. You only need to regenerate when the header/library or jextract itself changes, rather than running it on every application startup.

A workflow can choose to:
- **Commit generated sources** into version control so building the application does not depend on jextract being available on every machine.
- **Generate in the build pipeline** to ensure reproducibility when the toolchain is pinned.
- **Distribute a binding JAR** alongside native binaries for each platform.

Any approach works as long as versions and binary ABIs are controlled. Do not put the jextract tool on the runtime classpath just because code was generated from it; application users need the generated **classes**, the JDK FFM runtime, and the matching native library version.

### 15.2. Reproducing Output Requires Fixed Inputs

Checklist to pin in CI:

- Version of the **C header** from the SDK.
- Version of the **native binary** (`libfoo.so`/DLL/dylib).
- Version of **jextract** (and target JDK/API).
- JDK used to compile the generated Java.
- OS/arch/ABI or target compiler flags.
- Include directories and macro definitions.
- Output package, filtering flags, and library-loading strategy.

Because Clang preprocesses `#if` and macros, the same header can generate **different APIs between Linux and Windows**. Do not generate on Linux and copy the JAR to Windows without proving ABI compatibility by checking types/layouts.

### 15.3. Generated Files and Manual Code Should Be in Separate Directories

A suggested structure:

```text
project/
├── native/
│   ├── include/
│   └── src/
├── generated-sources/
│   └── demo/bindings/
├── src/main/java/
│   └── demo/api/
│       └── SafeNativeApi.java
└── build/
```

`generated-sources` contains only output managed by jextract. `SafeNativeApi` is a developer-written Java façade holding validation/error handling/lifetime logic. When regenerating, do not overwrite the façade or edit generated source in ways that will be lost when the tool runs again.

### 15.4. Testing After Every Regeneration

A useful test suite:

1. **Build:** generated Java sources compile with the target JDK.
2. **Load:** native library is found on the right path and resolves symbols.
3. **ABI scalar:** `int`/`double` functions return expected test vectors.
4. **Struct layout:** cross-check `sizeof`/field offsets against C `sizeof`/`offsetof`.
5. **Pointer:** check NULL, length, ownership, deallocator.
6. **Callback:** test Java upcall on the right thread and lifetime.
7. **Error codes:** C errors are translated into meaningful Java exceptions/statuses.
8. **Portability:** CI across all OS/architectures the application supports.
9. **Unload/reload:** no remaining workers/callbacks or raw pointers after the library is unloaded.
10. **Regression:** generated public API does not unexpectedly lose constants/functions due to filters/macros.

## 16. Diagnosing Failures When jextract or Generated Bindings Do Not Work

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `jextract: command not found` | Binary not downloaded or not placed on PATH | Install jextract separately, check `jextract --version` |
| JDK and generated source mismatch | jextract binary targets FFM API of a different JDK | Use a compatible jextract release, regenerate |
| Clang reports `file not found` for header | Missing `-I` include dir/SDK headers | Use the correct main header and include paths |
| Parser encounters wrong symbols | Missing/conflicting `-D`, C macro condition | Use compiler defines matching the native build |
| Generated class lacks desired function | Wrong header selected, filter excluded symbol, unsupported macro | `--dump-includes` and inspect generated API |
| `cannot find symbol` / `UnsatisfiedLinkError` | Binary missing export, wrong name, wrong library version | `nm -D`/`objdump`/platform symbol inspection |
| `libminimath.so` fails to load | OS library search path is incorrect | Check `LD_LIBRARY_PATH` or `--use-system-load-library` |
| Native access warning/error | Module lacks restricted FFM permission | `--enable-native-access` for the appropriate module |
| Generated code compile error | Version/tool mismatch, incomplete source, missing generated helper | Pin jextract/JDK and compile all generated Java |
| `WrongMethodTypeException` | Java call site does not match `MethodHandle.type()` | Check accessor `foo$handle().type()` |
| Wrong C scalar value on an OS | Different ABI mapping for C `long`/`size_t` | Generate/test for that OS, check canonical layouts |
| Struct fields read incorrectly | Padding/packing/ABI mismatch | Check C `sizeof`/`offsetof` and Java `layout()` |
| Callback crashes after returning | Upcall stub arena already closed or C retained callback | Design register/unregister lifecycle |
| JVM crash when native function runs | Wrong ABI descriptor/symbol, invalid pointer | Check header/binary/allocator first, not just Java stack trace |
| Memory leak | C pointer must be freed by caller but wrapper does not | Use proper C API deallocator, owner wrapper |
| C++ library cannot find symbol | Name mangling or no C ABI | Create an `extern "C"` exported shim |

### 16.1. Distinguishing Code-Generation Errors from Native Runtime Errors

**Code-generation errors:** jextract fails to parse the header, fails to generate Java source, or the generated Java fails to compile. These usually have clear toolchain diagnostics.

**Runtime linking errors:** Java classes compile, but the native binary is not on the library lookup path, is missing a symbol, or has an ABI signature mismatch. These only surface when loading/calling native code.

**Memory safety errors:** the call runs, but C/Java uses a pointer past its lifetime, out of bounds, or with concurrent access. This is the category that can corrupt the process; do not wait for the JVM to throw a Java exception to detect it.

Dividing errors into three stages helps debug faster:

```text
Header parsing  →  Java compilation  →  Native load/downcall
     │                    │                     │
  Clang/macros          JDK/API          symbols, ABI, lifetime
```

## 17. How to Verify the Quality of Generated Bindings

After generating code, instead of just counting files, check:

- **Root class:** package and header class name match options.
- **Native functions:** names and Java carrier arguments/returns match the C ABI.
- **Metadata accessors:** `foo$descriptor()`, `foo$handle().type()` accurately reflect the intended signature.
- **Structs:** field offsets, `sizeof()`, alignment, and array stride.
- **Enums/macros:** values are correct after preprocessing, no important macros missing.
- **Library load:** correct `-l`/path, shared object and dependencies are found.
- **Error policy:** return codes/`errno` are interpreted properly and wrapped in a Java façade when needed.
- **Ownership:** C allocators/deallocators are paired, borrowed pointers are not treated as owned pointers.
- **Toolchain match:** jextract/JDK/native headers/binaries are consistent.

Do not edit generated classes just to "make errors go away" without tracing the root cause. If the generator parsed a **wrong-version** header, fixing the header/toolchain is the sustainable solution.

## 18. Self-Check Questions (with Answers)

**Q1.** What inputs does jextract take and what outputs does it produce?  
**Answer:** It takes C header(s) along with includes/macros/options, parses them with Clang, and generates **Java source bindings** based on FFM; it does not generate C implementations from Java and does not compile native binaries.

**Q2.** Why does jextract not replace the C compiler?  
**Answer:** Headers only describe declarations. The C implementation still must be compiled into a binary with matching exported symbols; the generated Java wrapper needs that binary to run.

**Q3.** When jextract generates `add_numbers(int,int)`, does the Java developer still have to write `Linker.downcallHandle` manually?  
**Answer:** Usually no. The generated wrapper already uses the FFM linker underneath and provides metadata accessors if verification is needed.

**Q4.** Is jextract a default part of every JDK 17/22/25?  
**Answer:** No. jextract is a separate tool from the OpenJDK project; you must install a compatible release or build from source. FFM is final since JDK 22.

**Q5.** Why can the same C header generate different Java bindings on Linux and Windows?  
**Answer:** The C preprocessor, target macros, `long`/`size_t`, struct packing, calling conventions, and ABI can differ. You must verify on the target platform.

**Q6.** Does `#define SQUARE(x) ((x)*(x))` automatically generate a Java downcall `SQUARE(x)`?  
**Answer:** No. A function-like macro has no native symbol; it requires a Java helper or a C shim.

**Q7.** When a C header declares `struct Point` with x/y, what does jextract help with?  
**Answer:** It generates the layout, field accessors, offsets, and allocation helpers according to the parsed ABI, reducing the need to manually write `MemoryLayout`/`VarHandle` for each field.

**Q8.** If a C function returns `char*`, can Java automatically receive a `String` right away?  
**Answer:** That should not be assumed. The pointer is represented by a `MemorySegment`; you need to know the encoding, NUL/length, lifetime, and free it when appropriate.

**Q9.** A C SDK allocates with `malloc` and requires the caller to free. Does jextract automatically call `free` after each wrapper call?  
**Answer:** No. The caller or Java façade must invoke the deallocator per the contract, without freeing too early or double-freeing.

**Q10.** Why is `--include-dir` needed when the header already has `#include "types.h"`?  
**Answer:** The Clang preprocessor needs to locate dependent headers in order to parse types and declarations accurately.

**Q11.** Does `--library foo` make jextract build `libfoo.so`?  
**Answer:** No. It tells the generated binding to look for a library with the logical name `foo`. `libfoo.so` must already exist from a C compiler or SDK.

**Q12.** Why can a native binary still exist yet the generated binding become wrong after an SDK upgrade?  
**Answer:** Headers, macros, ABIs, structs, or symbols may have changed. You must regenerate and run regression tests with the matching version.

**Q13.** Can jextract directly parse C++ classes/templates?  
**Answer:** Not within the tool's C header scope. Use an appropriate C ABI wrapper/`extern "C"` layer to link C++ libraries.

**Q14.** The tool output shows a struct field has the right type. Do we still need to check ownership?  
**Answer:** Yes. Field/accessors only describe layout; they do not assert that target memory is still alive or who must free it.

**Q15.** How do you prove that the `MethodHandle` generated for the C function `int add(int,int)` is correct?  
**Answer:** Print `add$handle().type()` to check the Java signature, while also cross-checking **header + ABI + actual binary** and running a golden native test. Inspecting `MethodType` alone is not enough to prove the entire ABI.

## 19. Takeaways

- **jextract = C header → Java FFM bindings**. Its purpose is to mechanize writing wrappers, `FunctionDescriptor`, `MethodHandle`, and layouts for C APIs.
- **The FFM API is the runtime foundation**, while jextract is a **standalone source-generation tool**; since JDK 22, FFM is an official API. Choose a jextract release compatible with your JDK.
- **The C implementation and native library must still exist**, with the right symbols and ABI. `--library` does not compile the binary.
- Generated classes typically provide wrapper functions and accessors for `$address`, `$descriptor`, and `$handle`; structs, globals, constants, and function pointers get additional helpers.
- **The Clang preprocessor, include paths, macros, compiler target, and ABI** directly affect the generated output. Regenerate in the right environment, pin versions, and test cross-platform if needed.
- **jextract does not solve all ownership, error handling, encoding, thread-safety, or native safety concerns.** Creating a Java façade that controls lifecycle and domain semantics is good practice.
- **Compared to JNI**, `javac -h` goes from Java native declarations to C headers; **jextract goes the opposite way**, from C headers to Java FFM bindings.
- **Test all three stages:** header parsing succeeds, generated Java compiles, and the actual C binary loads/calls properly.

### Official Documentation

- [OpenJDK jextract — Jextract Guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md): CLI, generated wrappers, structs, callbacks, macros, loader strategy, and unsupported features.
- [OpenJDK jextract source repository](https://github.com/openjdk/jextract): source, build instructions, samples, and tool changes.
- [JDK jextract download page](https://jdk.java.net/jextract/): available jextract binaries; choose a JDK-compatible build.
- [Dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/): official hands-on tutorial with binding generation examples.
- [Oracle Java SE 25 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/25/core/call-native-functions-jextract.html): implementation example from C header to Java FFM.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API finalized in JDK 22.
- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall mechanism that generated bindings rely on.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): mapping native function layouts to Java carriers.
