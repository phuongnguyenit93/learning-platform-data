# Creating a downcall MethodHandle and verifying the actual MethodType in Java FFM

## 1. Goal: knowing the exact Java type needed when calling a native function

With the Foreign Function & Memory API (FFM), Java can call a C function using a **downcall `MethodHandle`** without writing a JNI wrapper for each function. However, the C signature, `FunctionDescriptor`, and `MethodType` are not three identical representations.

For example, suppose a native library has the function:

```c
int32_t add_i32(int32_t left, int32_t right);
```

On a platform where C `int32_t` follows the ABI of a matching 32-bit scalar, Java describes the function with:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

After creating a **downcall handle with a bound function address**, the actual type is:

```text
(int,int)int
```

But an **unbound downcall handle** has the type:

```text
(MemorySegment,int,int)int
```

Because when invoked, the second case also requires the **function pointer address** (represented as a `MemorySegment`) as the first Java parameter.

This issue often surfaces when using:

```java
MethodHandle handle = linker.downcallHandle(...);
System.out.println(handle.type());
```

and seeing a signature that differs from what was expected. **Read `handle.type()` before choosing `invokeExact` or writing a wrapper**, rather than guessing that FFM accepts the exact types in the C declaration as read in ordinary Java.

**Version used:** this article applies the official `java.lang.foreign` API from **JDK 22+** (JEP 454). On JDK 17, the equivalent package and API do not have the same stable version. The runnable example below requires JDK 22+, a C compiler, and a **Linux x86-64** environment so that the ABI/library path conventions are well-defined. Do not try to force these commands onto Java 17.

## 2. Four concepts to keep separate

### 2.1. Native function signature

The signature declared in C expresses the types that the **native ABI** uses to receive parameters and return results:

```c
double mul_f64(double a, double b);
void write_sum(int32_t *output, int32_t a, int32_t b);
```

C types such as `int`, `long`, `size_t`, `void *`, or `struct` have ABI-level passing rules that depend on the platform and do not necessarily correspond one-to-one with Java keywords of the same name.

### 2.2. `FunctionDescriptor`: the layout contract at the C/Java boundary

A `FunctionDescriptor` lists the **layout of the result** (if any) and the **layouts of the native parameters**:

```java
// int32_t add_i32(int32_t, int32_t)
FunctionDescriptor addDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

// void write_sum(int32_t*, int32_t, int32_t)
FunctionDescriptor writeDescriptor = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

These are fragments, placed inside a method with imports from `java.lang.foreign`.

- `FunctionDescriptor.of(returnLayout, arguments...)`: the **first** layout parameter is the **return layout**, and the subsequent layouts are the arguments.
- `FunctionDescriptor.ofVoid(arguments...)`: a function with no return value, equivalent to C `void`. Do **not** use `FunctionDescriptor.of(ValueLayout.JAVA_VOID, ...)` because there is no corresponding `JAVA_VOID` layout.
- `ValueLayout.ADDRESS`: a native pointer; its Java carrier is `MemorySegment`, not `long` or `String`.
- `ValueLayout.JAVA_INT`: its carrier is Java `int`, not boxed `Integer`.
- `GroupLayout` such as a C `struct`: its Java carrier is `MemorySegment`, but a **function returning a group layout** requires an additional allocator at call time.

**Important:** `FunctionDescriptor` does not execute the function and does not automatically verify the C ABI of the looked-up symbol. An incorrect descriptor can create a handle that looks valid on the surface but calls into C with the wrong convention, leading to a **JVM crash or memory corruption**.

### 2.3. `MethodType`: the actual Java signature

`java.lang.invoke.MethodType` describes the **Java parameter classes** and **Java return class** of a `MethodHandle`.

For example:

```java
import java.lang.invoke.MethodType;

MethodType t = MethodType.methodType(
        int.class, int.class, int.class);

System.out.println(t); // (int,int)int
```

This is a fragment. `MethodType` says nothing about the C calling convention or physical struct layout; it states which **Java** arguments must be passed to the `MethodHandle`. Two identical `MethodType` instances can represent native functions with different ABIs if their descriptors or linker options differ.

### 2.4. `Linker`: turning a descriptor into a downcall handle

`Linker.nativeLinker()` uses the ABI of the **current JVM platform**. There are two main overloads:

```java
// Bind the function address IMMEDIATELY when creating the handle.
MethodHandle bound = linker.downcallHandle(
        functionAddress, descriptor);

// Unbound address: pass functionAddress when invoking.
MethodHandle unbound = linker.downcallHandle(
        descriptor);
```

Both are **restricted methods**; the application must enable native access for the module calling FFM, for example by running the program on the classpath with `--enable-native-access=ALL-UNNAMED`.

The first form is semantically equivalent in linking to:

```java
MethodHandle unbound = linker.downcallHandle(descriptor);
MethodHandle bound = unbound.bindTo(functionAddress);
```

When **binding** the address, the leading `MemorySegment` parameter representing the function pointer no longer needs to be passed on each call.

## 3. Formula for the actual MethodType

For a `FunctionDescriptor` with return `R` and native arguments `A1, A2, ..., An`, if all are scalar/address values:

```text
descriptor.toMethodType() = (A1, A2, ..., An)R

bound downcall handle     = (A1, A2, ..., An)R

unbound downcall handle   = (MemorySegment, A1, A2, ..., An)R
                             └── target function address
```

`R` and `Ai` here are the **Java carrier types** of the layouts, not C type names. For a `void` return, `R=void`.

For example, with the function `int32_t add_i32(int32_t,int32_t)`:

| Operation | Result in `MethodType.toString()` format |
| --- | --- |
| `addDesc.toMethodType()` | `(int,int)int` |
| `linker.downcallHandle(address, addDesc).type()` | `(int,int)int` |
| `linker.downcallHandle(addDesc).type()` | `(MemorySegment,int,int)int` |

If Java code calls an unbound handle as if it were a bound handle, the program will be missing the **function address** and will fail to match the Java MethodType.

### 3.1. `FunctionDescriptor.toMethodType()` is not always `handle.type()`

`FunctionDescriptor.toMethodType()` infers carrier types from the descriptor. It **cannot know on its own** whether you will call the bound or unbound overload, or whether additional parameters are added by linker/runtime options.

Therefore, the proper verification workflow is:

```java
System.out.println("FD carrier type: " +
        descriptor.toMethodType());
System.out.println("actual handle type: " +
        handle.type());
```

Do not write `descriptor.toMethodType().equals(handle.type())` as a general rule. That comparison may hold for a **bound** scalar downcall with no synthetic parameters, but it is **false** for an unbound handle or group-return/capture-state cases.

### 3.2. Type mapping: from layout to Java carrier

| Native ABI type (e.g., Linux/x64) | FFM Layout | Java carrier in MethodType |
| --- | --- | --- |
| C `int` / `int32_t` on matching ABI | `ValueLayout.JAVA_INT` | `int` |
| C 16-bit `short` | `ValueLayout.JAVA_SHORT` | `short` |
| C 64-bit `long long` | `ValueLayout.JAVA_LONG` | `long` |
| C `float` | `ValueLayout.JAVA_FLOAT` | `float` |
| C `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| C `bool` when canonical mapping supports it | `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| C `char *` / `void *` | `ValueLayout.ADDRESS` | `MemorySegment` |
| C `struct Pair` (by value) | ABI-matching `GroupLayout`/`StructLayout` | `MemorySegment` |
| Native `void` return | `FunctionDescriptor.ofVoid(...)` | `void` |

**Do not equate `MemorySegment` with Java `String`:** `char*` is a C address (usually pointing to a NUL-terminated string), not a Java object. To call C `strlen(const char*)`, you must allocate and encode the string into native memory before passing a `MemorySegment`.

For C `unsigned int`/`size_t`, the Java carrier does not automatically express signedness. If retrieving large unsigned values, you need to handle bit patterns or convert to a wider type according to the ABI. **Having the right MethodType does not guarantee the right data semantics**.

## 4. Bound and unbound: same native function, different Java signature

Suppose `address` is the result of:

```java
MemorySegment address =
        symbols.find("add_i32").orElseThrow();
```

It represents the **C function address**, not a Java method object. With the descriptor:

```java
FunctionDescriptor addDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

Create two handles:

```java
MethodHandle bound =
        linker.downcallHandle(address, addDesc);

MethodHandle unbound =
        linker.downcallHandle(addDesc);
```

Invoke them:

```java
int a = (int) bound.invokeExact(20, 22);

int b = (int) unbound.invokeExact(
        address, 20, 22);
```

In a context with all imports present, both calls can return `42` if the C function actually has the signature matching the descriptor. What to check in Java:

```java
MethodType expectedBound =
        MethodType.methodType(
                int.class, int.class, int.class);

MethodType expectedUnbound =
        MethodType.methodType(
                int.class,
                MemorySegment.class, int.class, int.class);

System.out.println(bound.type().equals(expectedBound));
System.out.println(unbound.type().equals(expectedUnbound));
```

Both comparisons are expected to be `true` in this case. **This is a fragment**, because `linker`, `symbols`, and `address` are not initialized here; the complete program below will create them.

### 4.1. When to choose each kind?

A **bound handle** is suitable when:

- A Java wrapper always calls the same native symbol.
- The library is loaded and kept with a clear lifetime.
- You want the Java call to have fewer parameters, closer to the native function.

An **unbound handle** is suitable when:

- One native function signature applies to **multiple different function pointers**.
- The function address is chosen at call time (vtable, plugin resolver, dynamic dispatch).
- You need per-use control over the symbol/lifetime.

Drawback: API users easily forget the function pointer and fail to realize that the first `MemorySegment` parameter is the **function address** rather than `char*`/`int*` data from the C signature.

### 4.2. Two `MemorySegment` parameters do not mean the same thing

A C function:

```c
void write_sum(int32_t *out, int32_t a, int32_t b);
```

has the descriptor:

```java
FunctionDescriptor writeDesc = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

- Bound handle: `(MemorySegment,int,int)void`. The first `MemorySegment` is the **out buffer pointer** received by C.
- Unbound handle: `(MemorySegment,MemorySegment,int,int)void`. The **first** `MemorySegment` is the **function address**; the **second** `MemorySegment` is the **out buffer pointer**.

Even though the Java types may be the same, **the role of each parameter is different**. `MethodType` only knows the class; the source code must name `functionAddress` and `outBuffer` clearly to avoid swapping them.

## 5. Complete example: compiling a C library and checking MethodType at runtime

The main example demonstrates four signature styles:

1. `int32_t add_i32(int32_t,int32_t)`: returns `int`.
2. `double mul_f64(double,double)`: returns `double`.
3. `void write_sum(int32_t*,int32_t,int32_t)`: returns `void`, takes a native pointer.
4. `struct Pair make_pair(int32_t,int32_t)`: returns a **struct by value**, causing the downcall handle to have an additional `SegmentAllocator`.

To avoid confusion with OS-dependent `size_t`/`long`, the example is scoped to **Linux x86-64, System V C ABI, JDK 22+** and uses explicit `int32_t`. The program includes checks of `handle.type()` against `MethodType` instead of assuming correctness.

### 5.1. Directory structure

```text
ffm-method-types/
├── native/
│   └── ffm_types.c
├── src/
│   └── FFMMethodTypes.java
└── build/
    └── libffm_types.so          # built from C
```

### 5.2. Native library: `native/ffm_types.c`

```c
#include <stdint.h>

/* On Linux/x64, int32_t matches the ABI of a 32-bit int. */
int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}

double mul_f64(double a, double b) {
    return a * b;
}

void write_sum(int32_t *out, int32_t a, int32_t b) {
    if (out != 0) {
        *out = a + b;
    }
}

struct Pair {
    int32_t left;
    int32_t right;
};

struct Pair make_pair(int32_t left, int32_t right) {
    struct Pair result = {left, right};
    return result;
}
```

There are no Java/JNI headers in this C library. FFM will look up these **exported native symbols** and call them directly according to the ABI. The `write_sum` function writes the result into memory allocated by Java; `make_pair` returns a **struct by value**, not `struct Pair*`.

The sample intentionally adds only small numbers so as not to cause signed overflow in C. For production data, you must define an overflow policy and explicit native error handling.

### 5.3. Java: `src/FFMMethodTypes.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.file.Path;

public class FFMMethodTypes {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Path library = Path.of("build", "libffm_types.so")
                .toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            // The library is loaded and its lifetime is bound to the arena.
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // C: int32_t add_i32(int32_t, int32_t)
            MemorySegment addAddress =
                    symbols.find("add_i32").orElseThrow();

            FunctionDescriptor addDesc = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);

            MethodHandle addBound =
                    linker.downcallHandle(addAddress, addDesc);
            MethodHandle addUnbound =
                    linker.downcallHandle(addDesc);

            System.out.println(
                    "descriptor type: " + addDesc.toMethodType());
            System.out.println(
                    "bound type: " + addBound.type());
            System.out.println(
                    "unbound type: " + addUnbound.type());

            MethodType expectedBound = MethodType.methodType(
                    int.class, int.class, int.class);
            MethodType expectedUnbound = MethodType.methodType(
                    int.class,
                    MemorySegment.class, int.class, int.class);

            System.out.println(
                    "bound verified: " +
                    addBound.type().equals(expectedBound));
            System.out.println(
                    "unbound verified: " +
                    addUnbound.type().equals(expectedUnbound));

            int boundResult =
                    (int) addBound.invokeExact(20, 22);
            int unboundResult =
                    (int) addUnbound.invokeExact(
                            addAddress, 7, 8);

            System.out.println("bound result: " + boundResult);
            System.out.println("unbound result: " + unboundResult);

            // C: double mul_f64(double, double)
            FunctionDescriptor mulDesc = FunctionDescriptor.of(
                    ValueLayout.JAVA_DOUBLE,
                    ValueLayout.JAVA_DOUBLE,
                    ValueLayout.JAVA_DOUBLE);

            MethodHandle multiply = linker.downcallHandle(
                    symbols.find("mul_f64").orElseThrow(),
                    mulDesc);

            System.out.println(
                    "double type: " + multiply.type());
            double product =
                    (double) multiply.invokeExact(1.5d, 2.0d);
            System.out.println("double result: " + product);

            // C: void write_sum(int32_t*, int32_t, int32_t)
            FunctionDescriptor writeDesc =
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT);

            MethodHandle write = linker.downcallHandle(
                    symbols.find("write_sum").orElseThrow(),
                    writeDesc);

            System.out.println("void type: " + write.type());

            MemorySegment output =
                    arena.allocate(ValueLayout.JAVA_INT);

            // MethodHandle with void return:
            // DO NOT try to cast the result to int or Object.
            write.invokeExact(output, 4, 5);
            System.out.println("out value: " +
                    output.get(ValueLayout.JAVA_INT, 0L));

            // C: struct Pair { int32_t left, right; }
            //    struct Pair make_pair(int32_t,int32_t)
            StructLayout pairLayout = MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("left"),
                    ValueLayout.JAVA_INT.withName("right"));

            FunctionDescriptor pairDesc = FunctionDescriptor.of(
                    pairLayout,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);

            MethodHandle makePair = linker.downcallHandle(
                    symbols.find("make_pair").orElseThrow(),
                    pairDesc);

            System.out.println(
                    "pair descriptor type: " +
                    pairDesc.toMethodType());
            System.out.println(
                    "pair bound type: " + makePair.type());

            // Returning struct by value: must pass SegmentAllocator
            // at the synthetic parameter position of the downcall handle.
            SegmentAllocator allocator = arena;
            MemorySegment pair = (MemorySegment)
                    makePair.invokeExact(allocator, 11, 12);

            System.out.println("pair values: " +
                    pair.get(ValueLayout.JAVA_INT, 0L) + "," +
                    pair.get(ValueLayout.JAVA_INT, 4L));

            // It is possible to create the right handle, yet call invokeExact
            // with the wrong Java return type at the call site.
            try {
                long wrongReturn = (long)
                        addBound.invokeExact(1, 2);
                System.out.println(wrongReturn);
            } catch (WrongMethodTypeException ex) {
                System.out.println(
                        "wrong exact return: WrongMethodTypeException");
            }
        }
    }
}
```

The program **does not use `System.loadLibrary`**: `SymbolLookup.libraryLookup(Path, Arena)` explicitly loads the file from the path. Therefore, setting `-Djava.library.path` is not required for this example as long as the library is in `build`.

Note that `import java.lang.invoke.MethodHandle` and `import java.lang.invoke.MethodType` are in a different package from `java.lang.foreign`: FFM creates the handle, while Java's `java.lang.invoke` provides the type and invocation mechanism.

### 5.4. Compiling and running

From the `ffm-method-types` directory on Linux x86-64:

```bash
mkdir -p build

cc -std=c11 -O2 -fPIC -shared \
  native/ffm_types.c -o build/libffm_types.so

javac -d build src/FFMMethodTypes.java

java --enable-native-access=ALL-UNNAMED \
  -cp build FFMMethodTypes
```

- `-fPIC -shared` builds an ELF shared library, exporting the C symbols listed above.
- `javac` requires **JDK 22+**. This is the official FFM API, so `--enable-preview` is not needed in JDK 22.
- `--enable-native-access=ALL-UNNAMED` grants permission to call **restricted FFM methods** on the classpath, specifically `SymbolLookup.libraryLookup` and `Linker.downcallHandle`. For named modules, grant permission only to the appropriate modules.
- `Path.toAbsolutePath()` makes library loading use an absolute path, though it still assumes the current working directory is the project root.
- When releasing for Windows/macOS, you must rebuild for the right ABI, name the file according to the OS, and account for C naming/export conventions; **do not reuse the Linux commands verbatim**.

**Expected stdout on the stated environment:**

```text
descriptor type: (int,int)int
bound type: (int,int)int
unbound type: (MemorySegment,int,int)int
bound verified: true
unbound verified: true
bound result: 42
unbound result: 15
double type: (double,double)double
double result: 3.0
void type: (MemorySegment,int,int)void
out value: 9
pair descriptor type: (int,int)MemorySegment
pair bound type: (SegmentAllocator,int,int)MemorySegment
pair values: 11,12
wrong exact return: WrongMethodTypeException
```

Each type line is the output of **`MethodType.toString()` at runtime**, not a type we guessed from the C symbol name.

### 5.5. Why does the example include three special signature styles?

**`add_i32`**:
- Each `JAVA_INT` gives the Java carrier `int`.
- Bound has two `int` parameters.
- Unbound adds a leading `MemorySegment` for the function address.

**`write_sum`**:
- `ofVoid` gives a `void` return.
- C `int32_t*` maps to the Java carrier `MemorySegment`.
- The call `invokeExact(output, 4, 5)` must be in a **void invocation** context; a return value cannot be expected.
- C writes to the output buffer; Java reads via `output.get(JAVA_INT, 0)`.
- Do not pass a default `byte[]` heap segment as a C pointer if the downcall has not been configured for heap access; `arena.allocate` allocates suitable native memory.

**`make_pair`**:
- A struct returned by value is described by a `GroupLayout`.
- `pairDesc.toMethodType()` only sees the native arguments `(int,int)MemorySegment`.
- The **actual downcall handle** also needs a `SegmentAllocator`, so the FFM runtime can allocate space to receive the returned struct.
- Since the return is a Java `MemorySegment`, the code reads fields according to the actual layout/offsets (here two consecutive ints, offsets 0 and 4). The demo uses the matching C struct and Linux/x64 ABI.

### 5.6. Checking program logic before applying to a real library

- The C function `add_i32` returns `int32_t`; Java `JAVA_INT` has carrier `int`, both 32-bit on the chosen ABI.
- C `mul_f64` takes/returns `double`; Java `JAVA_DOUBLE` has carrier `double`.
- C `write_sum` takes a **native pointer** (not an `int` holding an address); Java passes a `MemorySegment` with a valid lifetime.
- Struct `Pair` consists of two `int32_t` fields, so the layout illustrates two adjacent `JAVA_INT`s, 8 bytes total on Linux/x64; for other structs you must check actual C ABI padding/alignment.
- `SymbolLookup.libraryLookup` ties the library's lifetime to the arena. All handle invocations happen **within the arena's scope**; handles/symbols are not used after the arena closes.
- The example catches `WrongMethodTypeException` caused by the wrong **Java call-site return type**. This is a fundamentally different error from a descriptor that does not match the native ABI (which can crash).

## 6. Inspecting MethodType: how to read each parameter

A `MethodType` has:

```java
MethodType type = handle.type();

Class<?> result = type.returnType();
int arity = type.parameterCount();

for (int i = 0; i < arity; i++) {
    Class<?> parameter = type.parameterType(i);
    System.out.println(i + " -> " + parameter.getName());
}
```

This is a **fragment**; `handle` must already exist. You should not just look at `toString()` and parse it with regex; the `returnType()` and `parameterType(i)` APIs let you check the **exact Java classes**.

### 6.1. Strict type comparison with `MethodType.equals`

`MethodType` is a value-based immutable descriptor. Use:

```java
MethodType expected = MethodType.methodType(
        int.class, int.class, int.class);

if (!handle.type().equals(expected)) {
    throw new IllegalStateException(
            "Unexpected FFM downcall type: " + handle.type());
}
```

This pattern is useful in the initialization code of a binding library to catch **bound/unbound mistakes** or wrong carriers before the first call. However, it **does not verify the native declaration**; to confirm the ABI, you must check the C header, data model, compiler/platform, and native library documentation.

### 6.2. Using `MethodType.changeReturnType` and `insertParameterTypes` to explain

To understand the synthetic parameter difference:

```java
MethodType descriptorType =
        addDesc.toMethodType();  // (int,int)int

MethodType predictedUnbound =
        descriptorType.insertParameterTypes(
                0, MemorySegment.class); // (MemorySegment,int,int)int

System.out.println(
        predictedUnbound.equals(addUnbound.type())); // true
```

This is a fragment based on the variables from the `add_i32` example. The formula only holds for simple scalar cases **without options that add parameters**. For group returns or `captureCallState`, you must account for other synthetic arguments and still **read the actual `handle.type()`**.

**Do not try to manually alter the MethodType of a native descriptor just to force it to match a desired Java signature.** The `FunctionDescriptor` must still accurately describe the C function; `MethodHandle` combinators only adapt the Java call site, they do not turn the actual C function into a different native signature.

## 7. `invokeExact`, `invoke`, and `invokeWithArguments`

### 7.1. `invokeExact`: exact call-site type matching

`MethodHandle.invokeExact` is a **signature-polymorphic method**. The Java compiler infers the method type of the call site from the **static** argument types and the result type in the expression context.

For example, a handle with `(int,int)int`:

```java
// CORRECT: two ints, and the result type is also int.
int x = (int) addBound.invokeExact(20, 22);

// WRONG: the caller expects long instead of int.
// The native function does not automatically change its return type.
long y = (long) addBound.invokeExact(20, 22);
```

These two lines are fragments for comparison; the second line **may compile** but will throw `WrongMethodTypeException` at runtime because the actual `MethodType` does not match the call site `(int,int)long`. The complete example caught that exact error.

If you merely call `addBound.invokeExact(20, 22);` as a **statement** and discard the result, the call site typically has a `void` return type, which also fails to match a handle returning `int`. With `invokeExact`, *whether the result is used as a specific type* also affects the invocation signature.

**Advice:** when you need an `int`, declare an `int` variable or cast the result `(int)` in place; when you need a `long` because C returns a 64-bit `size_t`, the descriptor/carrier must also be `JAVA_LONG` rather than just casting in Java.

### 7.2. `invoke`: can adapt Java types

`handle.invoke(...)` can apply Java conversions permitted by `MethodHandle`, similar to `asType`. It is useful when call sites are not strictly fixed, but:

- Do not use `invoke` to mask a descriptor with the wrong ABI.
- Boxing/unboxing and conversions have overhead and can throw exceptions.
- On FFM hot paths, when the signature is stable, `invokeExact` provides type clarity and optimization.

For example, `invoke` can adapt certain primitive conversions:

```java
// Fragment: addBound has (int,int)int.
int sum = (int) addBound.invoke((short) 20, (short) 22);
```

Here `invoke` does not change C's `int32_t` type. It only adapts the **Java call-site short → int** according to MethodHandle rules before performing the downcall.

### 7.3. `invokeWithArguments` is the flexible invocation path

```java
Object result = addBound.invokeWithArguments(20, 22);
System.out.println(result); // 42
```

This is a fragment. `invokeWithArguments` returns an `Object` with boxing and handles a flexible argument list; it is suitable for reflection-like tooling, but **should not be the default** in high-performance native call loops. The value `42` in the example is a boxed `Integer`, not a C pointer.

### 7.4. `asType` cannot fix a wrong ABI

Suppose you do:

```java
MethodHandle adapted = addBound.asType(
        MethodType.methodType(
                int.class, short.class, short.class));
```

This is a fragment. The adapted handle has the Java signature `(short,short)int` and converts `short` to `int` before calling. **The native `add_i32` still receives two 32-bit integers** according to the original descriptor. You must distinguish between MethodHandle adaptation and C function description; you cannot change the C signature using `asType`.

## 8. C ABI mapping: a valid Java MethodType can still be wrong natively

### 8.1. `int`, `long`, `size_t` are not the same across all platforms

Java `int` is 32-bit and `long` is 64-bit by language specification. C `int`, `long`, and `size_t` depend on the **ABI/data model**.

| C type | Typical Linux/x64 | Typical Windows/x64 | Consequence for FFM |
| --- | --- | --- | --- |
| `int` | 32-bit | 32-bit | Usually `JAVA_INT` |
| `long` | 64-bit | 32-bit | Linux `JAVA_LONG`, Windows `JAVA_INT` |
| `long long` | 64-bit | 64-bit | Usually `JAVA_LONG` |
| `size_t` | 64-bit | 64-bit | `JAVA_LONG` on both these 64-bit systems |
| `void *` | 64-bit pointer | 64-bit pointer | `ADDRESS` → `MemorySegment` |

These are example mappings for common ABIs. A `C long` variable is not always a Java `long`. If you mistake C `long` on Windows x64 and use `JAVA_LONG`, `handle.type()` may still print `long` cleanly, but **the native call may violate the ABI**.

### 8.2. Reading Linker's `canonicalLayouts`

FFM provides a map of canonical layouts according to the native ABI:

```java
Linker linker = Linker.nativeLinker();

var canonical = linker.canonicalLayouts();
var cLong = canonical.get("long");
var cSizeT = canonical.get("size_t");

System.out.println(cLong);
System.out.println(cSizeT);
```

This is a fragment; the output depends on the ABI/runtime, so no fixed stdout is provided. It reports the canonical layout of C types on the platform itself, helping you design the right `FunctionDescriptor`. If you need the carrier, for a layout that is a `ValueLayout` you can use `((ValueLayout)cSizeT).carrier()`.

**Do not replace every C type with `JAVA_LONG` just because you are running a 64-bit JVM.** You must understand the C header and calling convention. For library typedefs, you may need to look up the platform type from the specific header rather than relying on the generic typedef name.

### 8.3. C `strlen` example and the `size_t` issue

Declaration:

```c
size_t strlen(const char *s);
```

On **Linux/x64**, `size_t` is 64-bit, so the descriptor is typically:

```java
FunctionDescriptor strlenDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,
        ValueLayout.ADDRESS);
```

The **bound** downcall handle has the Java type:

```text
(MemorySegment)long
```

C `const char *` does not turn into a Java `String`: you must create a native C string, e.g., `arena.allocateFrom("Hello")`, then:

```java
long length = (long) strlen.invokeExact(
        arena.allocateFrom("Hello")); // 5
```

This is a fragment where `strlen` has been resolved by the linker and `arena` is still alive. On a 32-bit ABI, `size_t` may map to `JAVA_INT`, making the MethodType `(MemorySegment)int`. Use `canonicalLayouts().get("size_t")` to avoid hard-coding incorrectly when multi-platform support is needed.

**Note:** `size_t` is unsigned; the Java carrier may be signed. For very large lengths exceeding the positive range of the Java type, the application must have its own policy for interpreting unsigned values/bounds.

## 9. Synthetic parameter for group/struct returns

A C function returning a struct by value:

```c
struct Pair { int32_t left; int32_t right; };
struct Pair make_pair(int32_t left, int32_t right);
```

is described by a returned **group layout** and two argument layouts:

```java
StructLayout pairLayout = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("left"),
        ValueLayout.JAVA_INT.withName("right"));

FunctionDescriptor pairDesc = FunctionDescriptor.of(
        pairLayout,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

`pairDesc.toMethodType()`:

```text
(int,int)MemorySegment
```

But the **bound** downcall handle has an added `SegmentAllocator`:

```text
(SegmentAllocator,int,int)MemorySegment
```

and the **unbound** downcall handle has:

```text
(MemorySegment,SegmentAllocator,int,int)MemorySegment
```

Meaning:

- The first `MemorySegment` of unbound is the **function address**.
- `SegmentAllocator` is where the FFM runtime allocates **memory to receive the struct returned by value**.
- The last two `int`s are the actual C parameters.
- The returned `MemorySegment` is a **view over the struct result**.

Example:

```java
// Fragment: makePair has been linked with pairDesc.
SegmentAllocator allocator = arena;

MemorySegment pair = (MemorySegment)
        makePair.invokeExact(allocator, 11, 12);

int first = pair.get(ValueLayout.JAVA_INT, 0L);
int second = pair.get(ValueLayout.JAVA_INT, 4L);
```

In this snippet, `arena` must still be alive, have sufficient access permissions, and be compatible with the struct ABI. **Do not confuse a struct by value with a pointer to a struct**:

- `struct Pair make_pair(...)` → returns a group layout, Java return carrier `MemorySegment`, handle has an added `SegmentAllocator`.
- `struct Pair* make_pair(...)` → returns `ValueLayout.ADDRESS`, Java return `MemorySegment`, **does not** generate a synthetic allocator parameter because the return is a pointer value.

Both cases have the same Java return carrier `MemorySegment`, yet **their native signatures and ownership rules are completely different**. This is why you must read both the **FunctionDescriptor** and `MethodHandle.type()`.

### 9.1. Why is the allocator a Java parameter that does not appear in the C header?

The FFM runtime needs a place to allocate the region holding the struct result, whereas the C ABI may return the struct via registers or use a hidden return buffer according to the calling convention. `SegmentAllocator` is the Java-side mechanism for managing result memory, **not a C `SegmentAllocator*` parameter**. Do not manually insert a pointer into `FunctionDescriptor` just to "match" the Java MethodType.

### 9.2. The struct layout must match the real ABI

`MemoryLayout.structLayout(...)` does not automatically insert all ABI padding; you must describe the actual alignment, field offsets, and trailing padding. For example, in this article there are two `int32_t`s, so on Linux/x64 no padding is needed between them. For C `struct { int a; double b; }`, the layout usually needs padding before `double`, and `sizeof` according to the ABI. A descriptor that successfully creates a handle does not prove your struct mapping is correct.

## 10. Linker options can also change MethodType

Certain `Linker.Option` values affect how the native linker creates the handle.

### 10.1. `captureCallState("errno")` adds a `MemorySegment`

Example:

```java
FunctionDescriptor descriptor = FunctionDescriptor.ofVoid();

Linker.Option capture =
        Linker.Option.captureCallState("errno");

MethodHandle handle =
        linker.downcallHandle(functionAddress, descriptor, capture);
```

This is a fragment on an ABI that supports capturing `errno`, not a standalone program. `descriptor.toMethodType()` is `()void`, but the **bound handle** has an added `MemorySegment` pointing to the **capture-state segment**:

```text
descriptor.toMethodType(): ()void
handle.type():            (MemorySegment)void
```

If using an **unbound handle**, the **function address** parameter is also added at the beginning, giving `(MemorySegment,MemorySegment)void`. For functions returning a struct, the order of synthetic parameters also includes the allocator; the reliable approach is to **print `handle.type()` and check the JDK/docs**, rather than guessing from the C header.

`Linker.Option.captureStateLayout()` specifies the layout needed to allocate the capture state. The state segment must have the right size/alignment; `errno` is state from the native call and should not be read later via another C function because it may be overwritten. Do **not** use `captureCallState` as a way to automatically turn a C error code into a Java exception.

### 10.2. `firstVariadicArg` is not a Java varargs array

For a C variadic function such as:

```c
int printf(const char *format, ...);
```

if specialized for a format string and one `int`, the descriptor has two native argument layouts: `ADDRESS` for the format and `JAVA_INT` for the value, and uses `Linker.Option.firstVariadicArg(1)` to indicate that argument index 1 starts the variadic part.

```java
FunctionDescriptor printfDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);

MethodHandle printf = linker.downcallHandle(
        printfAddress,
        printfDesc,
        Linker.Option.firstVariadicArg(1));
```

This is a **fragment**; using `printf` for a simple example is not recommended because format string/ABI and side effects introduce extra things to control. `firstVariadicArg(1)` adjusts the native calling convention for variadic arguments; it **does not turn the handle into Java `Object...` or `Object[]`**, nor does it automatically generate all type variants. To call with a different number/types of variadic arguments, you must design a separate specialized descriptor.

### 10.3. `critical(boolean)` is not a signature-fixing trick

`Linker.Option.critical(...)` marks a downcall for specific optimization conditions; it **does not make the ABI signature arbitrary**. In particular, critical functions must not call back into Java or perform actions that violate the critical call contract, and `critical` cannot be combined with `captureCallState`. Do not enable `critical` just to work around a `WrongMethodTypeException`.

## 11. Distinguishing catchable errors from dangerous ABI errors

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `WrongMethodTypeException` from `invokeExact` | Java call site does not match `handle.type()` in arguments or return | Print `handle.type()`, fix static types/casts/result and bound/unbound |
| Extra leading `MemorySegment` required on invoke | Used unbound `downcallHandle(descriptor)` | Pass function address before C arguments or bind the symbol |
| Extra `SegmentAllocator` required | Native return is a group layout by value | Pass an allocator compatible with the result's lifetime |
| Extra `MemorySegment` required even though C has no such parameter | Used `captureCallState` | Allocate capture segment according to `captureStateLayout` |
| `NoSuchElementException` on `orElseThrow()` | Symbol lookup did not find the name | Check exports, C++ name mangling, library path |
| `IllegalCallerException` or native access warning | Module has not been granted restricted FFM methods permission | Configure `--enable-native-access` for the right module |
| `IllegalArgumentException` in `downcallHandle` | Descriptor/layout/options unsupported by linker; invalid function address | Check canonical layouts, ABI, and flags |
| `IllegalStateException`/`WrongThreadException` when passing segment | Arena already closed or confined segment used from wrong thread | Fix ownership/lifetime/thread scope |
| Passing a heap segment for a C pointer is rejected | ADDRESS parameter usually requires a native segment | Use `Arena.allocate(...)`/native memory per contract |
| C function receives wrong data even though `handle.type()` is right | `FunctionDescriptor` has wrong ABI, signedness, struct padding, or pointer ownership | Cross-check C header, ABI, compiler, and each layout |
| JVM crash or corrupted data | Native signature mismatch/dangling pointer/invalid memory | Stop, verify descriptor and ownership; do not rely on Java exceptions |

### 11.1. Java MethodType errors and native ABI errors are completely different

**Java MethodType errors** are usually caught before actually calling C:

```java
try {
    long value = (long) addBound.invokeExact(1, 2);
} catch (WrongMethodTypeException ex) {
    System.out.println("wrong Java call-site return type");
}
```

But a **wrong native descriptor** is far more serious:

```java
// WRONG ABI if the C function actually takes/returns int32_t.
// Do NOT create/call this handle in real code.
FunctionDescriptor wrongNative = FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE,
        ValueLayout.JAVA_DOUBLE,
        ValueLayout.JAVA_DOUBLE);
```

The real C function takes two `int32_t` values in integer registers and returns `int32_t`, whereas the wrong descriptor expects floating-point registers and a double return. `handle.type()` can still look "reasonable" as `(double,double)double`, because the linker has no way to verify on its own that the C symbol actually has that signature. If the downcall is executed, the outcome is undefined, including a crash.

**Conclusion:** `MethodHandle.type()` checks the **Java invocation protocol**. `FunctionDescriptor` must match the **actual ABI** of the native function by cross-checking the documentation and C headers.

### 11.2. Difference between `ClassCastException` and `WrongMethodTypeException`

`WrongMethodTypeException` comes from a mismatch between the call-site type of `invokeExact`/adaptation and the handle's `MethodType`. `ClassCastException` can arise from casting a runtime object to the wrong class, especially when using `invoke`/`invokeWithArguments`/custom adaptation. Do not lump all FFM errors into a single "native linkage error" category; inspect the stack trace and actual `MethodType`.

## 12. Automating signature checks at initialization time

A Java library calling many C functions should have a step that verifies Java-facing method types as soon as handles are created.

```java
static void requireType(
        String symbol,
        MethodHandle handle,
        MethodType expected) {

    MethodType actual = handle.type();
    if (!actual.equals(expected)) {
        throw new IllegalStateException(
                symbol + " MethodType mismatch: expected " +
                expected + ", actual " + actual);
    }
}
```

This is **a static Java helper**; imports for `MethodHandle` and `MethodType` are required in the class containing the helper. Example:

```java
// Fragment for bound handle int32_t add_i32(int32_t,int32_t).
requireType(
        "add_i32",
        addBound,
        MethodType.methodType(
                int.class, int.class, int.class));
```

For cross-platform libraries, `requireType` helps catch **guessed carriers** or missing synthetic parameters. However, to ensure descriptors are correct across multiple OSes, you also need to:

1. Check `Linker.nativeLinker().canonicalLayouts()` for important C types.
2. Provide a native test suite with functions returning recognizable values, including `int`, `double`, pointer, and struct.
3. Use test values that do not cause undefined behavior (no overflows, no NULL pointers if the C function forbids them).
4. Use golden expected outputs that explicitly state the ABI/environment.
5. Ensure the library/symbols/segments stay alive until downcalls finish.
6. Test `char*` encoding, size/unsignedness, struct padding, and ownership.
7. Test both bound/unbound cases if the framework uses function pointers.

If cross-platform release is needed, have CI on at least Linux x64 and Windows x64; the actual ABIs can differ even when the Java `MethodType` looks identical.

## 13. Lifetime issues of symbols, downcall handles, and native data

### 13.1. Keeping the native library loaded

With:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup symbols =
            SymbolLookup.libraryLookup(path, arena);
    MemorySegment addr =
            symbols.find("add_i32").orElseThrow();

    MethodHandle handle =
            linker.downcallHandle(addr, descriptor);

    int result = (int) handle.invokeExact(1, 2);
}
```

This is a fragment. Library lookup is tied to `arena`. Once the arena closes, the library may be unloaded; do not store a bound handle in a static field to **call after the library has been unloaded**. The function pointer inside a bound handle does not by itself guarantee that the C module remains loaded indefinitely.

### 13.2. Native data must remain valid throughout the call

If a function takes `ADDRESS`, the Java argument is a `MemorySegment`. The native linker performs appropriate access/keep-alive checks, but it cannot guarantee that the C function uses the pointer properly in **all circumstances after the downcall returns**.

For example, if C saves the pointer into a global variable for asynchronous use: Java must not close the arena immediately after the downcall if C has not finished using the data. The design must include a **release callback, acknowledgment, or ownership transfer** per the API contract. Do not treat `handle.invokeExact` returning as proof that C no longer holds the pointer.

### 13.3. Downcalls have restricted access because errors can cross the JVM safety boundary

Neither the Java compiler nor the linker runtime can prove the true C header of an arbitrary symbol. `Linker.downcallHandle` is marked restricted because mismatches can corrupt the process. Only link trusted libraries, verify the exact ABI, read headers, and avoid native pointers from untrusted sources.

## 14. Common semantic traps

### 14.1. "If `FunctionDescriptor` prints right, `handle.type()` is definitely the same"

No. The linker may add synthetic params to the descriptor: function address for unbound, allocator for group return, capture-state segment for `captureCallState`. Always check the **actual handle type**.

### 14.2. "C `void*` is equivalent to Java `long`"

No. FFM `ADDRESS` has the Java carrier **`MemorySegment`**. A `long` is normally invalid as an `invokeExact` argument for a pointer parameter. To pass C NULL, use `MemorySegment.NULL` when allowed by the contract; do not pass Java `null` or `0L` as a function pointer.

### 14.3. "I cast `(long)` at the call site, so C will return 64 bits"

Wrong. Casting at the Java call site changes the **expected type of `invokeExact`**, not the `FunctionDescriptor`. If the native function actually returns `int`, `handle.type()` has an `int` return; casting the result directly to `long` at the `invokeExact` site can cause `WrongMethodTypeException`. To get a `long` from an `int`, receive `int` first:

```java
int raw = (int) addBound.invokeExact(20, 22);
long widened = raw;
```

### 14.4. "You can pass a Java String to a C char* because both are strings"

No. FFM `ADDRESS` requires a `MemorySegment` pointer. C `char *` has its own encoding/NUL-termination/lifetime rules. For example, `Arena.allocateFrom("Hello")` allocates a NUL-terminated native UTF-8 string; keep the arena alive while C calls `strlen`.

### 14.5. "A function returning `struct*` definitely adds a `SegmentAllocator`"

No. `struct *` is a **pointer value** with `ADDRESS` → `MemorySegment`; there is no synthetic allocator for a **return pointer**. Only when the **descriptor return is a group layout** for a struct by value does the handle get an added allocator. A `MemorySegment` carrier alone is not enough to tell which case it is.

### 14.6. "SymbolLookup found the name, so FFM has verified the signature"

No. Native symbol lookup typically returns only an **address**. FFM has no full C type information from the symbol name, so linking with the wrong ABI can crash. Verify the header and function typedef from the library.

### 14.7. "`invoke` and `asType` can fix any type mismatch"

No. They adapt the **Java-side invocation** within allowed limits. They have no power to turn a C function taking `double` into one taking `int32_t` in native machine code. If the descriptor is wrong, you must fix the descriptor.

## 15. Practical workflow when integrating a new C API

1. **Read the exact C declaration**: return type, argument types, calling convention, const/pointer, struct by value vs pointer, variadic or not.
2. **Determine the runtime ABI**: `Linker.nativeLinker()`, canonical layouts; check C `long`/`size_t`/pointers/struct padding.
3. **Create the FunctionDescriptor in return-first, args-after order** (or `ofVoid`).
4. **Resolve the symbol** using `SymbolLookup.defaultLookup` or `SymbolLookup.libraryLookup`; keep the library alive.
5. **Choose bound/unbound** according to the use case, without mixing them up.
6. **Create the MethodHandle** and print/verify `handle.type()`.
7. **Handle synthetic parameters**: function pointer if unbound, allocator if group return, capture segment if using `captureCallState`.
8. **Prepare native values**: C strings as native `MemorySegment`; output buffers with sufficient size/alignment; proper arena lifetime.
9. **Invoke with the exact static types** via `invokeExact`; `void` return in a statement context, primitive results with the proper cast.
10. **Verify outputs** against the C implementation using golden tests; do not just check that no Java exception was thrown.
11. **Clean up resources/lifetimes**: do not call function pointers after unload, do not close buffers while C still uses them, invoke the right deallocator.
12. **Create cross-platform tests** when code depends on `size_t`/`long`/struct ABIs.

This workflow reduces two distinct classes of errors: wrong Java MethodType (usually detectable) and wrong C ABI (potentially dangerous at the process level).

## 16. Self-check questions

**Q1.** What Java signature does `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` correspond to when creating a **bound** downcall?  
**Answer:** `(int,int)int`. The first `JAVA_INT` is the return, and the two following `JAVA_INT`s are the arguments.

**Q2.** With the same descriptor above, a handle is created with `linker.downcallHandle(desc)` without passing a function address. What is `handle.type()`?  
**Answer:** `(MemorySegment,int,int)int`. The first parameter is the function address.

**Q3.** C function `void update(int *p)`, Java descriptor `ofVoid(ADDRESS)`. What is the bound MethodType?  
**Answer:** `(MemorySegment)void`. `MemorySegment` is the C pointer; the return is `void`.

**Q4.** Java writes `long value = (long) addBound.invokeExact(1,2);` but the handle returns `int`. What happens?  
**Answer:** `WrongMethodTypeException` because the call-site return `long` does not match the actual return `int`. Receive `int` first and Java-widen to `long` if needed.

**Q5.** `struct Pair make_pair(int,int)`: why does the bound handle have an added `SegmentAllocator`?  
**Answer:** The native return is a group layout by value; FFM needs an allocator to create a buffer holding the struct result. This is not a declared C parameter.

**Q6.** If C returns `struct Pair*` instead of `struct Pair`, is `SegmentAllocator` added?  
**Answer:** No. The return layout is `ADDRESS`, carrier `MemorySegment`, without a group-return allocator.

**Q7.** On Windows/x64, should C `long` always be mapped to `JAVA_LONG` because Java `long` is 64-bit?  
**Answer:** No. C `long` is typically 32-bit on Windows/x64; you must choose the layout according to the ABI/canonical layouts, usually `JAVA_INT`.

**Q8.** When can `FunctionDescriptor.toMethodType()` and `MethodHandle.type()` differ?  
**Answer:** When the downcall has an unbound function address, when a group layout return adds an allocator, or when `captureCallState` or other linker options add Java arguments.

**Q9.** Does `Linker.Option.firstVariadicArg(1)` turn a Java MethodHandle into `Object...`?  
**Answer:** No. You must explicitly declare all concrete variadic arguments in the descriptor; the option describes their calling convention.

**Q10.** If `handle.type()` matches `(double,double)double`, does that prove the C symbol is `double f(double,double)`?  
**Answer:** No. The handle type is **built from the descriptor** provided by Java; symbol lookup does not automatically check the C declaration. A wrong descriptor can cause a crash.

**Q11.** An unbound handle has two consecutive `MemorySegment` parameters for `void write_sum(int32_t*,...)`. What is their order?  
**Answer:** First is the **function address**; next is C's **out buffer pointer**; after that come the `int`s.

**Q12.** Why should you not store a bound handle after closing the arena used with `SymbolLookup.libraryLookup`?  
**Answer:** The arena manages the lifetime of the library/symbols; after closing, the library can unload, and the old handle may point to an invalid function address.

## 17. Key takeaways

- **`FunctionDescriptor`** describes the **native signature via layouts**; **`MethodType`** describes the **Java call-site type** of a MethodHandle.
- **`FunctionDescriptor.toMethodType()` is not always `handle.type()`**; use `handle.type()` to inspect the actual downcall signature.
- **Bound downcall:** no need to pass the function address on every call. **Unbound downcall:** has an extra leading `MemorySegment` parameter for the address.
- **ADDRESS ↔ MemorySegment; JAVA_INT ↔ int; JAVA_DOUBLE ↔ double; ofVoid ↔ void**; C types like `long` and `size_t` must be mapped by ABI, not guessed by name.
- **Struct return by value** adds `SegmentAllocator`; **pointer-to-struct return** does not add an allocator.
- **`captureCallState`** adds a capture-state segment; the variadic option changes the calling convention, not free-form Java varargs.
- **`invokeExact`** requires Java argument/return types to match `MethodHandle.type()` strictly. A wrong Java type can throw `WrongMethodTypeException`.
- **A valid MethodType does not guarantee a valid ABI**. FFM does not infer C function prototypes from symbol names; a wrong descriptor can crash the JVM.
- **Keep the library and native segments alive** throughout the call, manage buffers/ownership per contract, and grant native access to the appropriate module.

### Official documentation

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): bound/unbound downcallHandle, hidden function address, SegmentAllocator for group layout returns, ABI mapping, and restricted methods.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): of/ofVoid, argumentLayouts, returnLayout, and toMethodType.
- [Oracle Java SE 22 — Linker.Option](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html): captureCallState, captureStateLayout, firstVariadicArg, and critical.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): libraryLookup(Path, Arena), defaultLookup, and native library lifetime.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): carrier types, size/alignment, and ADDRESS.
- [Oracle Java SE 22 — MethodHandle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html): invokeExact, invoke, invokeWithArguments, MethodType matching, and WrongMethodTypeException.
- [Oracle Java SE 22 — MethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodType.html): Java parameter/return type descriptor, equals, parameterType, and returnType.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): final FFM API in JDK 22, downcalls, and restricted access.
