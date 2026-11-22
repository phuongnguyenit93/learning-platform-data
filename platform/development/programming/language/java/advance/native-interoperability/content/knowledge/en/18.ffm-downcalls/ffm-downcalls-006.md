# Calling with invokeExact Using Exact Parameter Types and Return Types

When using the **Foreign Function & Memory API (FFM)** to call a C function from Java, `Linker.downcallHandle(...)` creates a `java.lang.invoke.MethodHandle`. The fundamental difference from a normal Java method is that calling `handle.invokeExact(...)` succeeds only when **the signature at the call site (call-site method type) matches `handle.type()` identically**, including:

1. **The number of parameters** and **the parameter order**.
2. **The static Java type** of each argument expression: `int` differs from `long`, `double` differs from `float`, `MemorySegment` differs from `Object`.
3. **The return type requested by the call site**: `int` differs from `long`, `void` differs from any value-bearing type.
4. Special FFM parameters when present: function address for an unbound handle, allocator for struct return, call-state capture buffer, etc.

**`invokeExact` does not perform automatic boxing/unboxing, widening, narrowing, argument conversion, or return type adaptation.** If there is a mismatch, the JVM throws `WrongMethodTypeException`. This is a **Java MethodHandle** type error, which must still be distinguished from a more serious error: a `FunctionDescriptor` declaring **the wrong C prototype** can lead to undefined behavior, memory corruption, or a JVM crash even when `invokeExact` matches the created handle.

This lesson belongs to the **Calling Functions with FFM** group. We build a small C shared library, use Java 22+ to create downcall handles, print exact results, intentionally trigger `WrongMethodTypeException` cases safely, and then explain `invoke`/`asType`, ABI, pointers, `size_t`, void, threads, and lifetimes.

> **Version:** The FFM API in `java.lang.foreign` was finalized in **JDK 22** (JEP 454). This example runs on **Linux/x86-64, JDK 22+, and C11**. Do not use these imports/APIs as-is on Java 17; in JDK 21 it was still a preview feature. Calling native code with FFM requires granting appropriate native access permissions.

## 1. Two Signatures Must Be Correct: C ABI and Java MethodType

Consider the C prototype:

```c
int add_exact(int a, int b);
```

To call it from Java, we describe the C signature according to the ABI:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
    ValueLayout.JAVA_INT,
    ValueLayout.JAVA_INT,
    ValueLayout.JAVA_INT);
```

The Java snippet above assumes `import java.lang.foreign.*;` and is a snippet **inside a method**, not a standalone file. In `FunctionDescriptor.of(returnLayout, argumentLayouts...)`, the first element is the **return layout**, and the remaining two elements are the **argument layouts**. On Linux/x86-64, C `int` usually corresponds to `JAVA_INT`, with carrier `int.class`. For other ABIs, query `Linker.nativeLinker().canonicalLayouts().get("int")` rather than guessing.

If a bound downcall handle is created from the exact function symbol address, the Java type of this handle is:

```text
(int,int)int

Java call-site:
    int result = (int) add.invokeExact(7, 5);
                       ^              ^  ^
                       |              |  |
             requires return int     int int
```

**Casting the result** to `(int)` is important. Even though Java has a variable of type `int` on the left-hand side, writing it explicitly still helps the compiler emit the exact return descriptor at the call site and helps the reader confirm `int` from the MethodHandle.

The two verification layers are completely different:

| Layer | Who checks? | What is checked | If wrong |
| --- | --- | --- | --- |
| **Java call site ↔ MethodHandle** | JVM when executing `invokeExact` | Does the static `MethodType` match `handle.type()`? | `WrongMethodTypeException` before calling the function |
| **FFM FunctionDescriptor ↔ C binary** | Integrator, build/tests/ABI probe | Are the actual C types, calling convention, pointers, and structs correct? | May cause memory corruption, crash, wrong data; not automatically verified by the JVM |

Do not read a message saying “`invokeExact` worked” as proof that the C ABI is safe. You can misdescribe a C function and then call Java **matching that exact wrong descriptor**.

## 2. `MethodHandle.invokeExact` Is a Signature-Polymorphic Call

`MethodHandle.invokeExact` has a Java declaration that looks like:

```java
public final Object invokeExact(Object... args) throws Throwable;
```

However, this is a **signature-polymorphic method**: the JVM compiler is not forced to pack all arguments into `Object[]` or return an `Object` as shown by reflection. At each call site, the compiler records a *symbolic method descriptor* based on **the actual argument expression types** and **the return type expected by the context**.

All examples below are different call sites:

```java
int a = (int) mh.invokeExact(1, 2);   // (int,int)int
long b = (long) mh.invokeExact(1, 2); // (int,int)long
mh.invokeExact(1, 2);                 // (int,int)void
int c = (int) mh.invokeExact(1L, 2L); // (long,long)int
```

This is **illustrative code inside a method**, assuming `mh` is a `MethodHandle`. If `mh.type()` is `(int,int)int`, only **the first line** matches. The remaining three lines may compile, but at runtime they will cause `WrongMethodTypeException`.

### 2.1. Java Does Not Insert Numeric Conversions Automatically When Using `invokeExact`

In a regular Java method, an `int` can be widened to `long` via Java method invocation conversion; the Java compiler knows the static method's signature. However, `invokeExact` is signature-polymorphic and **does not perform Java method invocation conversions** to adapt the call-site type to the handle type. A literal `7` is `int`; a literal `7L` is `long`. Therefore:

```java
long answer = (long) handleLong.invokeExact(7L);
```

Is correct for a handle of type `(long)long`. Whereas:

```java
long answer = (long) handleLong.invokeExact(7);
```

Requests type `(int)long` and **does not** automatically turn `7` into `7L` for `invokeExact`. Even if the number is small enough to be represented by every type, the type descriptor is still wrong.

### 2.2. Boxing/Unboxing Does Not Happen Automatically Either

If the handle expects primitive `int`:

```java
Integer boxed = Integer.valueOf(7);
int answer = (int) add.invokeExact(boxed, 5);
```

The expression `boxed` has static type `Integer`, not `int`. At the call site, the JVM does not unbox it to `int` for `invokeExact`. The right way is to produce the primitive explicitly:

```java
int primitive = boxed.intValue();
int answer = (int) add.invokeExact(primitive, 5);
```

Both snippets are **illustrative code**, not standalone. The goal is to distinguish the static type of an expression from “a value that looks like the number 7”.

### 2.3. The Return Type Is Part of the Contract

The easiest thing to overlook: `invokeExact` cares about **the return type at the call site as well**.

```java
// Given MethodHandle.type() == (int,int)int:
int x = (int) add.invokeExact(2, 3);  // Correct.
long y = (long) add.invokeExact(2, 3); // Wrong: returns long.
add.invokeExact(2, 3);                // Wrong: statement expects void.
```

If you want to ignore the result while still calling the C function, you must receive the exact type and then intentionally discard the variable:

```java
int ignored = (int) add.invokeExact(2, 3);
// Do not use ignored for subsequent logic.
```

Or create an **adapter handle** with return type `void` using appropriate combinators if the API's intent is to discard the result. Do not assume that calling it as a statement will automatically discard the return value. Conversely, for a native C function returning `void`, the right way to call it is usually as a **statement** without a cast.

## 3. From `FunctionDescriptor` to `MethodHandle.type()`

FFM describes C types using `MemoryLayout`. A `ValueLayout` has a **Java carrier**; that is the type the method handle accepts/returns for that value. A pointer is represented by `AddressLayout`, with carrier `MemorySegment.class`.

Examples (for Linux/x86-64):

| C prototype fragment | FFM layout | Java carrier | Type needed at `invokeExact` |
| --- | --- | --- | --- |
| `int` | canonical `"int"` | `int` | Literal `7` or `int` variable |
| `long long` | canonical `"long long"` | `long` | `7L` or `long` variable |
| `double` | canonical `"double"` | `double` | `2.5` or `double` variable |
| `float` | canonical `"float"` | `float` | `2.5f` or `float` variable |
| `void *` / `int *` | canonical `"void*"` | `MemorySegment` | Valid `MemorySegment` |
| `size_t` (Linux/x64) | canonical `"size_t"` | `long` | `long`, but check each ABI |
| C `void` return | `FunctionDescriptor.ofVoid(...)` | `void` | Call as a statement |

**Do not hard-code “C long = Java long” across all operating systems.** LLP64 on Windows/x64 typically has a 4-byte C `long`; Linux/x64 LP64 typically has an 8-byte C `long`. `canonicalLayouts` and the resulting `handle.type()` are the source of truth for the running handle, but must be compared against the target library's headers and ABI.

### 3.1. Inspecting the Handle Type Directly

```java
System.out.println(handle.type());

boolean matches = handle.type().equals(
    MethodType.methodType(int.class, int.class, int.class));
```

This is code inside a method that already has `MethodHandle handle`, importing `java.lang.invoke.MethodType`. This `equals` check can be placed in startup validation to **fail fast** if the descriptor/carrier does not match the written call site.

`FunctionDescriptor.toMethodType()` also converts layout carriers into a `MethodType`. For **a simple bound downcall with only scalar/pointer types and no special linker parameters**, `descriptor.toMethodType()` matches `handle.type()`. However, do not treat that as an absolute rule for every downcall: unbound handles and certain ABI features add hidden parameters.

## 4. C11 Example: Four Clear Function Prototypes

To avoid depending on `libc`/symbol availability or assumed ABIs, we compile our own C shared library on Linux. File **`exact_ffi.c`**:

```c
/* exact_ffi.c: ISO C11, compiled into libexactffi.so. */

/* C int -> Java int on common Linux/x86-64. */
int ffi_add(int a, int b) {
    return a + b;
}

/* C long long -> Java long on Linux/x86-64. */
long long ffi_double_ll(long long value) {
    return value * 2;
}

/* C double -> Java double. */
double ffi_average(double left, double right) {
    return (left + right) / 2.0;
}

/* C void return; first param is int* (native address). */
void ffi_store_int(int *destination, int value) {
    if (destination != 0) {
        *destination = value;
    }
}
```

This is a **complete C file**. C functions are exported on Linux with standard compiler flags; there is no `JNIEXPORT` marker because this is an **FFM downcall**, not a JNI native method registered with the JVM. On Windows, you need export/calling convention settings appropriate for the compiler rather than copying the Linux build command as-is.

The input domain in the demo avoids C signed integer overflow: `7 + 5` and `21 * 2` are both valid. FFM **does not** automatically translate native errors from every library into Java exceptions: with other C code, you must read the contract regarding errno/status and ownership.

Corresponding function prototypes:

| C function | C signature | Expected Java MethodHandle |
| --- | --- | --- |
| `ffi_add` | `int(int,int)` | `(int,int)int` |
| `ffi_double_ll` | `long long(long long)` | `(long)long` |
| `ffi_average` | `double(double,double)` | `(double,double)double` |
| `ffi_store_int` | `void(int*,int)` | `(MemorySegment,int)void` |

In particular, C `int*` does not become Java `int[]` or `long` when called via FFM. It is a pointer to valid native memory, represented by `MemorySegment`.

## 5. Complete Java 22+ Example: Right Types, Wrong Types, and Explicit Adapter

File **`ExactInvokeDemo.java`** below:

- Uses canonical C layouts from the currently running ABI instead of guessing C types.
- Loads `libexactffi.so` with `SymbolLookup.libraryLookup(Path, Arena)`.
- Creates **bound downcall handles** for the four function symbols.
- Verifies `MethodType` before calling.
- Uses `invokeExact` with exact primitive types/return casts.
- Tests four **mismatched call sites** and catches `WrongMethodTypeException`.
- Uses `asType` to intentionally **widen return** from `int` to `long` when needed.

### 5.1. `ExactInvokeDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.AddressLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.file.Path;
import java.util.Map;

public final class ExactInvokeDemo {
    private ExactInvokeDemo() {}

    private static MemoryLayout require(
            Map<String, MemoryLayout> abi, String name) {

        MemoryLayout layout = abi.get(name);
        if (layout == null) {
            throw new IllegalStateException(
                "Missing C layout: " + name);
        }
        return layout;
    }

    private static MethodHandle downcall(
            Linker linker,
            SymbolLookup symbols,
            String symbolName,
            FunctionDescriptor signature) {

        MemorySegment address = symbols.find(symbolName).orElseThrow(
            () -> new IllegalStateException(
                "Missing C symbol: " + symbolName));

        return linker.downcallHandle(address, signature);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi =
            linker.canonicalLayouts();

        MemoryLayout cInt = require(abi, "int");
        MemoryLayout cLongLong = require(abi, "long long");
        MemoryLayout cDouble = require(abi, "double");
        MemoryLayout cPointer = require(abi, "void*");

        // The example set intentionally targets Linux/x86-64.
        // Do not silently call native if carriers differ.
        if (!(cInt instanceof ValueLayout.OfInt)
                || !(cLongLong instanceof ValueLayout.OfLong)
                || !(cDouble instanceof ValueLayout.OfDouble)
                || !(cPointer instanceof AddressLayout)) {
            throw new IllegalStateException(
                "Unexpected C ABI for this example");
        }

        try (Arena arena = Arena.ofConfined()) {
            Path library =
                Path.of("libexactffi.so").toAbsolutePath();

            SymbolLookup symbols =
                SymbolLookup.libraryLookup(library, arena);

            FunctionDescriptor addSig = FunctionDescriptor.of(
                cInt, cInt, cInt);
            FunctionDescriptor doubleSig = FunctionDescriptor.of(
                cLongLong, cLongLong);
            FunctionDescriptor averageSig = FunctionDescriptor.of(
                cDouble, cDouble, cDouble);
            FunctionDescriptor storeSig = FunctionDescriptor.ofVoid(
                cPointer, cInt);

            MethodHandle add = downcall(
                linker, symbols, "ffi_add", addSig);
            MethodHandle twice = downcall(
                linker, symbols, "ffi_double_ll", doubleSig);
            MethodHandle average = downcall(
                linker, symbols, "ffi_average", averageSig);
            MethodHandle store = downcall(
                linker, symbols, "ffi_store_int", storeSig);

            boolean typesOk =
                add.type().equals(MethodType.methodType(
                    int.class, int.class, int.class))
                && twice.type().equals(MethodType.methodType(
                    long.class, long.class))
                && average.type().equals(MethodType.methodType(
                    double.class, double.class, double.class))
                && store.type().equals(MethodType.methodType(
                    void.class, MemorySegment.class, int.class));

            System.out.println("types-ok=" + typesOk);
            if (!typesOk) {
                throw new IllegalStateException(
                    "Unexpected downcall MethodType");
            }

            // Correct: int arguments, int result.
            int sum = (int) add.invokeExact(7, 5);
            System.out.println("add=" + sum);

            // Correct: both argument and result are long.
            long doubled = (long) twice.invokeExact(21L);
            System.out.println("double-long-long=" + doubled);

            // Correct: double + double -> double.
            double avg = (double)
                average.invokeExact(2.0, 3.0);
            System.out.println("average=" + avg);

            // Correct: pointer has carrier MemorySegment.
            // Native C function returns void, called as a statement.
            MemorySegment slot = arena.allocate(cInt);
            store.invokeExact(slot, 123);
            System.out.println(
                "stored=" + slot.get(ValueLayout.JAVA_INT, 0));

            // Wrong 1: call-site parameters are long,long.
            try {
                int value = (int) add.invokeExact(7L, 5L);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "wrong-args=WrongMethodTypeException");
            }

            // Wrong 2: call-site return type is long.
            try {
                long value = (long) add.invokeExact(7, 5);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "wrong-return=WrongMethodTypeException");
            }

            // Wrong 3: statement implicitly requires void return.
            try {
                add.invokeExact(7, 5);
                System.out.println("unreachable");
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "ignored-return=WrongMethodTypeException");
            }

            // Wrong 4: Integer is not unboxed automatically.
            Integer boxedA = Integer.valueOf(7);
            Integer boxedB = Integer.valueOf(5);
            try {
                int value = (int) add.invokeExact(
                    boxedA, boxedB);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "boxed-args=WrongMethodTypeException");
            }

            // Intentional: adapter widens int return -> long.
            MethodHandle addWithLongReturn = add.asType(
                MethodType.methodType(
                    long.class, int.class, int.class));

            long widened = (long)
                addWithLongReturn.invokeExact(7, 5);
            System.out.println("adapted-return=" + widened);
        }

        System.out.println("complete");
    }
}
```

**Why does the sample have `throws Throwable`?** `MethodHandle.invokeExact` declares that it can throw `Throwable`; Java code must catch it or declare `throws` appropriately. The sample code uses `main(String[]) throws Throwable` for brevity. In a production program, you should not treat every `Throwable` like a normal input error: you need to distinguish Java linkage/type errors from native library errors and serious failures.

**Why is `SymbolLookup.libraryLookup` inside `try (Arena arena ...)`?** The symbol lookup and library lifetime are tied to the passed arena. Keep the arena alive while using the handles. `Arena.ofConfined()` fits because all calls in the demo execute on one thread; if you pass handles/buffers across multiple threads, choose a scope and synchronization compatible with the library.

**Why use an absolute `Path`?** The sample program builds `libexactffi.so` into the working directory. `Path.of(...).toAbsolutePath()` avoids relying on the OS native library search path when calling `libraryLookup(Path, Arena)`. Run it in the directory containing both the library and the class file.

### 5.2. Actual MethodType Signatures That Must Match

The check at the beginning of the program compares:

```text
add:      (int,int)int
twice:    (long)long
average:  (double,double)double
store:    (MemorySegment,int)void
```

Specifically, `store.invokeExact(slot, 123);` is correct because the MethodHandle returns `void` and the Java statement also requests `void`. Do not add an `(Object)` or `(Void)` cast. Conversely, a method returning `int` that you call as a statement will have a call-site return of `void` and receive `WrongMethodTypeException`.

The variable `slot` has declared type **`MemorySegment`**. When FFM describes a C pointer with `AddressLayout`, it needs a `MemorySegment` argument; if you only pass a raw `long address` even though 64-bit matches the pointer size, the call-site type does not match.

### 5.3. Compiling and Running on Linux

Requires JDK 22+ and a C compiler supporting C11. Place `exact_ffi.c` and `ExactInvokeDemo.java` in the same directory:

```bash
cc -std=c11 -O2 -Wall -Wextra -Wpedantic \
   -fPIC -shared exact_ffi.c -o libexactffi.so

javac ExactInvokeDemo.java

java --enable-native-access=ALL-UNNAMED ExactInvokeDemo
```

`--enable-native-access=ALL-UNNAMED` grants permission to call FFM restricted methods for code running on the classpath/unnamed module. If the application runs in a named module, you must configure native access for the exact module instead of granting permission to the entire application by default.

**Exact expected stdout on Linux/x86-64 with the two files above:**

```text
types-ok=true
add=12
double-long-long=42
average=2.5
stored=123
wrong-args=WrongMethodTypeException
wrong-return=WrongMethodTypeException
ignored-return=WrongMethodTypeException
boxed-args=WrongMethodTypeException
adapted-return=12
complete
```

The four `WrongMethodTypeException` lines are **intentionally triggered** to observe signature differences and are caught by Java. They are not C crashes, and they do not cause native functions to be called with a wrong ABI. C code only actually runs on the call paths where the Java call-site type matches.

Note: This is **expected stdout determined from the code**, not a benchmark result; actual timing and library loading depend on the JDK, dynamic linker, and OS. On Windows/macOS, you need library names, compiler flags, calling conventions, and export rules different from Linux.

## 6. Reading Each Error to Understand What "Exact" Means

### 6.1. Wrong Parameter: `int` vs `long`

The handle expects `(int,int)int`. You call:

```java
int value = (int) add.invokeExact(7L, 5L);
```

Java literals `7L` and `5L` are `long`. The call site requests `(long,long)int`. The mismatch is detected at the MethodHandle layer, not by C `int add_exact` trying to read two 64-bit values. There is no implicit narrowing.

Fix:

```java
int value = (int) add.invokeExact(7, 5);
```

Or if the input data is `long` from another API, range-check it and then convert **explicitly**:

```java
long raw = 7L;
int checked = Math.toIntExact(raw);
int value = (int) add.invokeExact(checked, 5);
```

`Math.toIntExact` throws `ArithmeticException` if `raw` exceeds the `int` range, rather than silently truncating 32 bits. This is a business-logic validation step before the FFM downcall, **not** a conversion performed by `invokeExact`.

### 6.2. Wrong Return Type: `int` vs `long`

The handle returns `int`, yet:

```java
long value = (long) add.invokeExact(7, 5);
```

The call site requests `long`. It does not auto-widen even though widening `int → long` is completely valid in normal Java. Distinguish **a cast outside the call** from **a cast directly on the result of `invokeExact`**:

```java
int original = (int) add.invokeExact(7, 5);
long widened = original;             // Normal Java widening.
```

If you want to write a single expression:

```java
long widened = (long) (int) add.invokeExact(7, 5);
```

The cast closest to `invokeExact` is `(int)` and requests a Java call-site return of `int`; then the outer cast converts Java `int` to `long`. To avoid misreading, using an intermediate variable is the clearest approach.

### 6.3. Ignoring the Return Value Does Not Make the Type `void`

In Java, you can write `someIntMethod();` as a statement and ignore the return value, because the compiler knows that static method returns `int`. With `invokeExact`, however, a statement constructs a call-site return type of **`void`**. When the handle returns `int`, a type mismatch occurs immediately.

Two correct ways:

```java
int ignored = (int) add.invokeExact(7, 5);

// Or intentionally create a handle with return type void:
MethodHandle onlySideEffect =
    MethodHandles.filterReturnValue(
        add,
        MethodHandles.empty(MethodType.methodType(
            void.class, int.class))); // THIS IS AN EXAMPLE OF WRONG COMBINATION
```

**Do not use the combiner example above as runnable code**: it is a cautionary construct because the filter must have the exact parameter/return contract, and constructing `empty` with type `(int)void` here does not correspond to every desired invocation pattern. The **simple, reliable** way to discard a return value is still to receive the exact type and not use the result. In library code that uses many `MethodHandle` types, check `MethodHandles.dropArguments/filterReturnValue` against the Javadoc and test `handle.type()` after composing.

### 6.4. Boxing and Reference Types

`invokeExact` does not automatically unwrap `Integer` into `int`, nor does it automatically upcast/downcast every reference type to fit the handle.

```java
Integer boxed = Integer.valueOf(7);
int a = (int) add.invokeExact(boxed, 5); // Mismatch.
int b = (int) add.invokeExact(boxed.intValue(), 5); // Correct.
```

If a handle requires exact `MemorySegment` and you store the segment in a variable of type `Object`:

```java
Object obj = arena.allocate(4);
// store.invokeExact(obj, 123); // Call-site (Object,int)void: wrong.
MemorySegment segment = (MemorySegment) obj;
store.invokeExact(segment, 123); // If segment is valid: right type.
```

This snippet is an example assuming `arena` and `store` already exist. **Having `Object` hold a `MemorySegment` at runtime is not enough**; the compiler uses **the static type of the expression** at the call site. Casting explicitly to `MemorySegment` gives the expression the exact Java reference type.

### 6.5. `float`, `double`, and Integer Literals

For C `double average(double,double)`, Java must pass `double`:

```java
double ok = (double) average.invokeExact(2.0, 3.0);

// The two literals 2f and 3f are float: mismatch in invokeExact.
// double bad = (double) average.invokeExact(2f, 3f);
```

Similarly, C `float` usually corresponds to Java `float` and requires `2.0f`; using `2.0` will request `double`. For primitive `boolean`/`byte`/`short`/`char`, do not assume Java numeric promotion will occur for you when calling `invokeExact`.

### 6.6. MethodHandle with Extra or Missing Parameters

If the C prototype has two parameters and the downcall handle's descriptor also has two, the call site must have exactly two arguments. You cannot pass an extra status argument or omit a parameter and expect FFM to infer it.

```java
// add.type() == (int,int)int
int ok = (int) add.invokeExact(7, 5);

// Wrong arity:
// int wrong = (int) add.invokeExact(7);
```

A more structured programming style is to use a Java wrapper with an explicit signature:

```java
static int addTwo(MethodHandle handle, int left, int right)
        throws Throwable {
    return (int) handle.invokeExact(left, right);
}
```

This snippet is only valid if the handle you pass actually has `(int,int)int`; the wrapper does not replace startup verification.

## 7. `invokeExact`, `invoke`, `invokeWithArguments`, and `asType`

The same `MethodHandle` can be called in multiple ways, but **you should not choose a permissive way just to hide ABI mistakes**.

| API | Mechanism | When appropriate | What to watch out for |
| --- | --- | --- | --- |
| `invokeExact` | Requires call site == `handle.type()` strictly | Downcalls with known exact method type; hot paths; strict reviews | Return type must also match |
| `invoke` | Can adapt according to `MethodHandle.asType(...)` rules | General Java APIs that intentionally allow conversions | Has boxing/numeric conversions, does not fix a wrong C descriptor |
| `invokeWithArguments` | Accepts arguments as objects, adapts dynamically | Diagnostics/prototyping, dynamic dispatch | Boxing, allocations, errors detected late, less type clarity |
| `asType(MethodType)` | Creates an adapter handle with a new type | Intentional conversions, controlled at a boundary | Must know conversion semantics and value ranges |
| `explicitCastArguments` | Converts types using broader casting rules | Mandatory bridges with a clear contract | Can narrow unintentionally if not validated |

### 7.1. How Does `invoke` Differ from `invokeExact`?

If a handle has type `(int,int)int`, calling `invoke` from a caller expecting `long` can use the `int → long` conversion according to adapter semantics:

```java
long widened = (long) add.invoke(7, 5);
```

That is **MethodHandle adaptation**, not the C function suddenly changing its return to `long`. If you use `invokeExact` at the same call site, the mismatch throws `WrongMethodTypeException`. You should not use `invoke` blindly when the C signature is uncertain; it only masks Java type differences and does not validate how C passes data.

### 7.2. `asType` When You Want a New Contract

In the full runnable program:

```java
MethodHandle addWithLongReturn = add.asType(
    MethodType.methodType(long.class, int.class, int.class));

long widened = (long)
    addWithLongReturn.invokeExact(7, 5);
```

This adapter changes **the Java type of the handle from `(int,int)int` to `(int,int)long`** by converting the result, while the native function still takes two C `int`s and returns a C `int`. This is a clean way to build a wrapper API returning Java `long` without misdeclaring the native `FunctionDescriptor`.

`asType` can allow other conversions; that does not mean every numeric conversion preserves data. When `long → int`, `double → int`, or unsigned bit patterns are involved, you must check ranges and policies before choosing an adapter. For hot paths, you can create the adapter once at initialization instead of rebuilding it per request.

### 7.3. Why Not Default to `invokeWithArguments`?

`invokeWithArguments(Object... args)` is flexible, but it weakens code readability: maintainers cannot clearly see the primitive types or expected return type from the call site itself, and conversions/boxing cause extra work. It has a place in runtime discovery frameworks or dynamic user-facing APIs, but for static C functions, `invokeExact` generally helps **fail fast** on wrong Java MethodTypes and is easier to code-review.

Neither `invoke` nor `invokeWithArguments` can make a freed pointer safe, infer the right native prototype from a symbol name, or fix a wrong calling convention.

## 8. `void` and Pointers: Separate Type Safety from Memory Safety

In the example, C has:

```c
void ffi_store_int(int *destination, int value);
```

Java descriptor:

```java
FunctionDescriptor storeSig = FunctionDescriptor.ofVoid(
    cPointer, cInt);
```

The result is a handle that takes a `MemorySegment`, an `int`, and returns **`void`**:

```java
MemorySegment slot = arena.allocate(cInt);
store.invokeExact(slot, 123);
```

This is correct in terms of **Java types**. However, if you pass a segment with an invalid address, insufficient byteSize, or a closed arena, you can get an FFM safety exception or a severe native error depending on the violation. A matching signature **does not prove the pointer points to writable memory**.

### 8.1. Do Not Turn a Pointer into `long` Just Because It Is 64-bit

A C pointer goes through `AddressLayout`, with Java carrier `MemorySegment`. Do not write:

```java
// Wrong: assumes C int* can be passed as Java long.
// store.invokeExact(slot.address(), 123);
```

If `slot.address()` is a `long`, the call site becomes `(long,int)void`, which differs from `(MemorySegment,int)void`. Even if you convert an integer into a segment where allowed by the API, you still need a contract for pointer provenance, ownership, alignment, and lifetime.

### 8.2. `Arena` Manages the Lifetime of Memory Regions

`Arena.ofConfined()` creates a scope accessible only from the owner thread and closeable. `arena.allocate(cInt)` allocates off-heap memory according to the layout's alignment, and that region remains valid while the arena is alive. `store.invokeExact(slot,123)` finishes before `try-with-resources` closes the arena.

In async code, a C library may **retain the pointer for use after the function returns**. If Java closes the arena immediately after the downcall, the pointer becomes dangling when a late C callback arrives. This is a serious memory-lifetime bug even though `invokeExact` matched the types. You need an owner that keeps the allocation alive until actual native completion/cancellation.

### 8.3. Read-Only and Heap Segments

When an address layout expects a native pointer, a standard FFM downcall does not accept a heap segment as a native pointer (unless using a specialized option under specific conditions), because the Java heap does not have a stable native address in the way C APIs require. Use `Arena.allocate` or a proper native segment when the C function expects a pointer.

If the C function will write data, the segment/memory must be writable under the actual contract. `MemorySegment.asReadOnly()` is not a mechanism that turns a C pointer into a `const int*` automatically enforced by C. Java metadata does not protect against arbitrary operations inside a C library that receives a raw address; the trust boundary remains native code.

## 9. Why `FunctionDescriptor.toMethodType()` Does Not Always Equal the Downcall Handle Type

For a bound handle with scalar/pointer parameters and return, and no special linker options:

```java
FunctionDescriptor fd =
    FunctionDescriptor.of(cInt, cInt, cInt);

MethodHandle bound = linker.downcallHandle(
    symbols.find("ffi_add").orElseThrow(), fd);

System.out.println(fd.toMethodType().equals(bound.type()));
// true in this example
```

This is a snippet inside a method that already has `linker`, `symbols`, and `cInt`.

However, FFM has other handle forms. **You must inspect the final `handle.type()`**, especially when building generic wrappers.

### 9.1. Bound Handle vs Unbound Handle

Two overloads:

```java
MethodHandle bound =
    linker.downcallHandle(address, descriptor);

MethodHandle unbound =
    linker.downcallHandle(descriptor);
```

This snippet assumes `address` and `descriptor` are valid.

- **Bound:** the native function address is already attached when creating the handle; for simple signatures, the call site only passes the C arguments.
- **Unbound:** the handle **takes an additional `MemorySegment` at the beginning**, pointing to the native function address; you can reuse one handle for multiple symbols sharing the same ABI signature.

If `descriptor` describes `int(int,int)`:

```text
Bound handle:     (int,int)int
Unbound handle:   (MemorySegment,int,int)int
```

For an unbound handle, the type-correct call is:

```java
int result = (int) unbound.invokeExact(
    functionAddress, 7, 5);
```

Do not add an address argument for a bound handle. Do not confuse this extra `MemorySegment` with a pointer argument declared by the C function; this is **the address of the function symbol**, not the address of a data buffer.

### 9.2. Struct/Union Returned by Value

If a native function returns a C `struct`/`union` by value and `FunctionDescriptor` uses a group layout as the return, the downcall handle requires an extra **`SegmentAllocator`** parameter so Java can allocate space for the result according to the ABI. Typically you pass an appropriate `Arena`, and receive a `MemorySegment` containing the struct result. For an unbound handle, there is also the function address argument at the start; the exact order should be confirmed via `handle.type()`.

Example method types may look like:

```text
Bound, struct by value:   (SegmentAllocator,...C args...)MemorySegment
Unbound, struct by value: (MemorySegment,SegmentAllocator,...C args...)MemorySegment
```

These are **signature shape diagrams**, not descriptions of a specific ABI or a complete program. For real aggregates, you must check the actual layout/padding from the C header and `sizeof/offsetof`. Do not treat a struct return as a pointer return and omit the allocator.

### 9.3. Linker Options Can Change the Type

Some options such as capturing call state (for example `errno` or OS errors) can add requirements for an auxiliary memory region at the call site, depending on the JDK/linker API. Do not assume `FunctionDescriptor.toMethodType()` always reflects all parameters added by the linker. Create the handle, call `type()`, verify prefix/arity/return, and only then write `invokeExact`.

Rule: **MethodHandle is the truth for the Java call-site type; the C header/prototype is the truth for the native ABI. You need both.**

## 10. `size_t`, C `long`, and Choosing the Return Type by ABI

This is an especially important case for `invokeExact`. C:

```c
size_t strlen(const char *s);
```

On many 64-bit ABIs, `size_t` uses Java `long`; on 32-bit ABIs it may use Java `int`. If you declare the handle using the exact canonical layout, **the return type at the call site must also change with the ABI**.

**Illustrative code inside a Java method** that already has `Linker linker`, `Arena arena`, and native access granted:

```java
Map<String, MemoryLayout> abi =
    linker.canonicalLayouts();

ValueLayout sizeT =
    (ValueLayout) abi.get("size_t");
MemoryLayout ptr = abi.get("void*");

MethodHandle strlen = linker.downcallHandle(
    linker.defaultLookup().find("strlen").orElseThrow(),
    FunctionDescriptor.of(sizeT, ptr));

MemorySegment cText = arena.allocateFrom("Hello");

if (sizeT.carrier() == long.class) {
    long n = (long) strlen.invokeExact(cText);
    System.out.println(Long.toUnsignedString(n));
} else if (sizeT.carrier() == int.class) {
    int n = (int) strlen.invokeExact(cText);
    System.out.println(Integer.toUnsignedLong(n));
} else {
    throw new IllegalStateException("Unsupported size_t");
}
```

The call sites in both branches are valid for **Java compilation**; the branch executed for the current carrier is the one that matches the actual handle. If you need a more portable wrapper, normalize the result after receiving the exact type; do not alter the function descriptor incorrectly to “make it fit” Java source.

The code above uses `linker.defaultLookup()`, so it requires a platform where the default lookup exposes `strlen`; on Linux/x64 this is common, though not guaranteed on every JVM/OS. The main code of this lesson uses a custom C library so stdout is always deterministic.

### 10.1. Signedness Is Not Solved by `invokeExact`

C `size_t` is unsigned. If the Java carrier is `int` and native returns bit pattern `0xFFFFFFFF`, the corresponding Java value can be `-1`. `Integer.toUnsignedLong` changes how the bit pattern is **interpreted** into `4294967295`; it does not change the ABI.

With carrier `long` and unsigned 64-bit values, use `Long.toUnsignedString` or appropriate unsigned comparisons, and do not assume every C `size_t` value is a non-negative Java signed long.

Similarly, C `long` on Linux/x64 usually has carrier `long.class`, whereas on Windows/x64 it is usually `int.class`. `invokeExact` reporting `WrongMethodTypeException` because Java code hard-coded `long` is only a symptom; the solution starts with reading the ABI/canonical layout and C header, not forcing `asType` to mask the mistake.

## 11. Variadic Functions and Default Argument Promotions

If a C function uses `...`, for example:

```c
int printf(const char *format, ...);
```

C has **default argument promotions**: for example, a C `float` in the variadic part is usually promoted to `double`, and small integer types are usually promoted to `int` or `unsigned int` depending on range.

The FFM linker requires **a descriptor for a specialization with a concrete parameter list**, along with the option `Linker.Option.firstVariadicArg(index)`. It does not automatically promote the wrong type you pass in an `invokeExact` call.

Example descriptor for `printf("%d", 42)` on Linux/x64:

```java
MethodHandle printf = linker.downcallHandle(
    linker.defaultLookup().find("printf").orElseThrow(),
    FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT),
    Linker.Option.firstVariadicArg(1));

MemorySegment format = arena.allocateFrom("%d");
int count = (int) printf.invokeExact(format, 42);
```

This is an **illustrative snippet inside a method**, not a standalone file. If run, `printf` prints `42` to C stdout; the return value `count` represents the number of characters printed according to the C contract. Only use format strings controlled by the application; never pass arbitrary user-supplied format strings to `printf`. If specializing a variadic `float`, describe the **promoted C `double`** and Java call-site `double` in the descriptor.

**Do not** simply see `ValueLayout.JAVA_FLOAT` and pass `2.0f` to a C vararg; matching `invokeExact` on Java types for a wrong descriptor still does not mean the C varargs ABI is right.

## 12. Distinguishing `WrongMethodTypeException` from Actual Native Errors

Several errors have similar-sounding messages but different root causes:

| Situation | Error class/symptom | Origin |
| --- | --- | --- |
| Java calls `invokeExact(7L)` for `(int)int` | `WrongMethodTypeException` | Java MethodHandle call site mismatch |
| Return cast `(long)` when handle returns `int` | `WrongMethodTypeException` | Wrong expected return type |
| Calling `invokeExact` as statement when handle returns `int` | `WrongMethodTypeException` | Call site requests `void` |
| MethodHandle needs `MemorySegment`, `Object` passed | `WrongMethodTypeException` | Variable's static type differs |
| Library cannot find symbol | `NoSuchElementException` from `orElseThrow()` or app-created error | Lookup/config/library |
| Using FFM restricted API without enabling permission | May throw `IllegalCallerException`, depending on JDK | Native-access policy |
| Segment already closed | `IllegalStateException`/scope error | FFM lifetime |
| Confined segment on wrong thread | `WrongThreadException` | Thread confinement |
| Passing heap segment as native pointer when disallowed | May throw `IllegalArgumentException` | Memory safety contract |
| Native function declaration has wrong arity/ABI | May produce wrong data, crash JVM | **FunctionDescriptor mismatches C binary** |
| C function returns error status without throwing in Java | Normal C value from MethodHandle's perspective | Application must interpret native error code |
| C function blocks indefinitely or deadlocks | Call does not return | Native dependency, not a type mismatch |

`WrongMethodTypeException` is a good sign that the JVM blocked a call **before entering C**. However, it does not mean you are using FFM safely on other paths. You must separately verify C function prototypes, integer widths, pointers, valid memory, alignment, module native access, error codes, and thread safety.

### 12.1. Why Shouldn't You “Catch and Ignore” Every Mismatch?

If production code repeatedly causes `WrongMethodTypeException`, that indicates a design bug in an adapter or in the source code. You should not catch it and return a fake default value as if C data had been processed. Fail fast at startup using `handle.type()` and fix the call site/descriptor, instead of letting requests fail repeatedly at runtime.

Other exceptions like `IllegalStateException` for a closed segment also usually signal a contract violation. Avoid catching broad `Throwable` and arbitrarily retrying native calls; a call down into C with side effects may have already executed before an error was recorded at another layer.

## 13. Performance: Exact Types Do Not Mean Free Native Calls

`invokeExact` has the advantage of a clearly typed call site, which can help the JVM optimize the adapter path under suitable conditions. However, total cost still includes the FFM transition, ABI marshalling, native execution, pointer validation, memory copying/ownership, CPU caches, and other JNI/VM interactions.

You should not assume “`invokeExact` is always X% faster than `invoke`” without benchmarking on the exact runtime/CPU/C library. The JIT can optimize static adapters, especially when the handle is constant or cached. For very short C functions, the boundary-crossing cost can be a significant fraction of the body.

Practice:

- Create `Linker`/lookup/`MethodHandle` **once** during component initialization, not looking up native symbols on every request unnecessarily.
- Cache type-verified handles and ensure the library remains loaded with an appropriate lifetime.
- Use `invokeExact` on hot paths when the method type is known; if an adapter is needed, build `asType` **once**.
- Avoid boxing and `Object...` on hot paths when dynamic dispatch is not needed.
- Keep bytes/pointers alive until the downcall finishes; do not close the arena prematurely.
- Measure throughput, p95/p99 latency, allocations, CPU, and native library behavior under realistic workloads.
- Do not choose a workaround that alters `FunctionDescriptor` to change the carrier and think of it as an optimization; ABI correctness comes first.

### 13.1. Using the Same Handle Across Multiple Threads

`MethodHandle` is immutable and shareable on the Java side, but **that does not mean every argument and native library is thread-safe**. If the handle calls a C function that uses global state or a pointer from a confined arena, another thread may race or be blocked by scope checks. The FFM type-safe boundary and concurrency safety are two separate contracts.

Do not pass a `MemorySegment` from `Arena.ofConfined()` to another worker thread and expect `invokeExact` to turn it into shared memory automatically. Use `Arena.ofShared()` when multi-thread access actually exists with proper synchronization, or use clear per-request ownership.

## 14. Essential Debugging and Testing Checklist

### 14.1. Testing Correct Types and Results

1. `add.type()` equals `(int,int)int`; calling `(int) invokeExact(7,5)` returns 12.
2. `twice.type()` equals `(long)long`; calling `(long) invokeExact(21L)` returns 42.
3. `average.type()` equals `(double,double)double`; calling `(double) invokeExact(2.0,3.0)` returns 2.5.
4. `store.type()` equals `(MemorySegment,int)void`; writes to native slot and reads back 123.
5. `invokeExact` with `long,long` on an `int,int` handle must throw `WrongMethodTypeException`.
6. Returning `long` at the call site when the handle returns `int` must throw a mismatch.
7. Calling a handle returning `int` as a statement must throw a mismatch because `void` is expected.
8. An `Integer` argument must throw a mismatch if the handle requires primitive `int`.
9. Adapter `asType((int,int)long)` must receive the `long` result accurately without changing the C prototype.
10. Method handles are created from the proper `SymbolLookup` and descriptor before invocation.
11. Disabling native-access permissions must trigger the appropriate policy error, never bypassed via reflection.
12. Calling with an expired/wrong-thread buffer must be blocked by the FFM scope contract, not treated as a MethodHandle type error.
13. Never test dangerously wrong C descriptors just to see if the JVM crashes; use review/header/compiler probes.

### 14.2. Code Review Checklist Questions

- What is the exact native C header of the symbol? Does the C API have special macros/typedefs/calling conventions?
- Have Java layouts been matched against canonical C types for the running ABI?
- Does `FunctionDescriptor.of(...)` have the right parameter count, order, and return layout?
- Is the downcall **bound** or **unbound**? Is there an extra function address at the start?
- Does a function returning `struct` by value require a `SegmentAllocator` at the call site?
- Do linker options add capture state or variadic specialization that must be accounted for?
- Was `handle.type()` checked immediately after creation?
- Does `invokeExact` have the exact **static** type for all arguments?
- Does the result cast closest to the call match the handle's return type?
- If the function returns non-void, is `invokeExact` accidentally being called as a statement?
- If the function returns `void`, is code trying to receive an `Object` or `Void`?
- Is boxing/implicit widening/`Object` context altering the call-site descriptor?
- Is the pointer argument a `MemorySegment`, with a live arena, right thread, and proper memory ownership?
- For C `size_t`/`long`, is Java `long` hard-coded regardless of ABI?
- Are stdout, native side effects, return status, timeouts, and resource cleanup tested?

### 14.3. Workflow for Handling `WrongMethodTypeException`

```text
Downcall MethodHandle throws WrongMethodTypeException
       |
       v
Print/log handle.type()
       |
       v
Determine call-site symbolic type:
    - each argument expression type
    - expected return type
    - count and order
       |
       v
Does it match handle.type() identically?
       |
       +--> No: fix call-site/cast/argument types,
       |        or intentionally create an asType adapter.
       |
       +--> Yes: check the actual running code path/handle,
                 wrapper, and linker options.
       |
       v
Separately verify FunctionDescriptor against C header/ABI.
       |
       v
Test return, side effects, lifetime, and native errors.
```

Printing `handle.type()` is helpful, but it does not replace checking the **compiler-generated call-site descriptor**. If you suspect the static type was altered by a generic wrapper or compiler context, use `javap -c -v` to inspect bytecode and symbolic descriptors during debugging; in normal production code, explicit casts and local variables are more readable.

## 15. Conclusion and References

**Key rule:** when an FFM downcall handle has type `(int,int)int`, call it with `(int) handle.invokeExact(7,5)`. Do not pass `7L`, do not try to receive `long`, do not call it as a statement, and do not pass `Integer` expecting automatic unboxing. For a C `void` function, a statement `invokeExact(...)` is the right form; for a C pointer, use a `MemorySegment` in the proper scope. When you truly want a Java API different from the native type, create an intentional `asType` adapter **after** describing the C ABI accurately.

An easy sentence to remember: **`FunctionDescriptor` must match C; `invokeExact` must match `MethodHandle.type()`.** Getting the first layer wrong can crash; getting the second layer wrong is usually caught by the JVM with `WrongMethodTypeException`.

### Official Documentation

- [Java SE 22 — MethodHandle: invokeExact, call-site descriptor, and WrongMethodTypeException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 22 — WrongMethodTypeException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html)
- [Java SE 22 — MethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 22 — FFM Linker: downcallHandle, canonicalLayouts, bound/unbound handles](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 22 — FunctionDescriptor and toMethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Java SE 22 — SymbolLookup: libraryLookup, lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — ValueLayout and Java carriers](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
