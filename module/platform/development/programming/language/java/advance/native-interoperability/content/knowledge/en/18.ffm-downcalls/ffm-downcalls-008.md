# Variadic Functions, firstVariadicArg, and C Promotion Rules in Java FFM

A `variadic` C function is declared with `...`, such as `int printf(const char *format, ...);`. The `...` part allows each call to have a **different number and types of arguments**, but it is not an array containing type metadata. When Java uses the Foreign Function & Memory API (FFM) to call this function, the native linker must be provided with a **specialized signature**, including the layout of **each actual argument**, and the starting position of the variadic part using `Linker.Option.firstVariadicArg(index)`. The variadic part must also obey **C's default argument promotions**: `float` becomes `double`, and narrow integer types are promoted to `int` or `unsigned int` according to representation rules.

The key point: **FFM does not automatically perform C promotions for you.** If you write a Java `float` and declare `ValueLayout.JAVA_FLOAT` at the `...` position, you are describing the native call incorrectly; the JDK 22 native linker may reject it. If you declare the wrong `firstVariadicArg`, the ABI may pass values in a register or stack region different from what the C function expects, leading to garbage data, undefined behavior, or a JVM crash.

This article belongs to the **Calling Functions with FFM** group, for **Java 22+** using the final `java.lang.foreign` API (JEP 454). We explain the exact argument positions and promotion rules, the case of passing no variadic arguments, Java carrier/C ABI mapping, `printf`/`va_arg`, and then create a **complete C11 + Java 22+ example** to demonstrate two specialized handles for the same symbol, variadic `float`/`short`, and a function with two fixed parameters. Build instructions on Linux/macOS/Windows, stdout, exercises, and a safety checklist are included.

## 1. How does C declare fixed arguments and variadic arguments?

Prototype:

~~~c
#include <stdio.h>

/* format is a fixed parameter; ... is the variadic part. */
int printf(const char *format, ...);
~~~

A C call:

~~~c
printf("%d and %.2f", 7, 1.25f);
~~~

Mapping:

~~~text
Actual C source: printf("%d and %.2f", 7, 1.25f);
Argument index:                 0       1      2
Declaration:                const char* ...    ...
ABI type after promotion:       char*   int   double
                                |       \_____/
                                |       variadic
                                fixed

FFM descriptor: result JAVA_INT
                arguments ADDRESS, JAVA_INT, JAVA_DOUBLE
Option:         Linker.Option.firstVariadicArg(1)
~~~

Even though the last expression is `1.25f` (C `float`), when the C caller passes it through `...` it is **promoted to double**. `printf`, upon encountering `%.2f`, therefore reads a `double`, not a `float`.

C also has functions with more than one fixed argument:

~~~c
long long add_from(int base, int count, ...);
~~~

The position of `base` = 0; `count` = 1; the first variadic argument = **2**, so use `firstVariadicArg(2)`. `firstVariadicArg` takes the **0-based index of the argument layout** in the function descriptor, **not counting the return layout**.

**Distinguishing Java varargs:** Java `void log(Object... items)` actually receives `Object[]`. C `void log(const char *fmt, ...)` has no automatic `Object`/`int[]` array and carries no runtime type tag. `FunctionDescriptor` in FFM cannot automatically infer the signature from the `fmt` string.

## 2. C `va_list` consumes each argument according to its promoted type

Inside a C function, the `<stdarg.h>` header provides `va_list`, `va_start`, `va_arg`, `va_end`. For example:

~~~c
#include <stdarg.h>

/* Illustrative snippet: only correct when the C caller passes count ints. */
long long sum_variadic(int count, ...) {
    va_list ap;
    va_start(ap, count);
    long long total = 0;
    for (int i = 0; i < count; ++i) {
        total += va_arg(ap, int);
    }
    va_end(ap);
    return total;
}
~~~

`va_start(ap, count)` relies on the **name of the last fixed parameter**. Each `va_arg(ap,int)` retrieves an argument at the next variadic position that the caller **passed compatible with `int`**. `va_arg` **does not check whether there are enough arguments**, does not inspect the Java caller, and does not automatically fix types. If the caller passes two arguments but count=3, C reads a non-existent value: undefined behavior.

With a mix:

~~~c
/* Illustrative C snippet: each variadic pair consists of an int then a double. */
double sum_pairs(int pairs, ...) {
    va_list ap;
    va_start(ap, pairs);
    double total = 0.0;
    for (int i = 0; i < pairs; i++) {
        int whole = va_arg(ap, int);
        double fraction = va_arg(ap, double);
        total += whole + fraction;
    }
    va_end(ap);
    return total;
}
~~~

If a C caller passes `short whole` and `float fraction` in `...`, the compiler uses **int** and **double** according to promotions; Java FFM must also build the `JAVA_INT` and `JAVA_DOUBLE` descriptor accordingly. Do not change C to `va_arg(ap, short)` or `va_arg(ap,float)`: those types do not match the promoted argument.

**Warning:** In production code, you must validate count within the API's allowed range and handle errors, but guarding count does not prove the caller actually supplied enough arguments. The count and order contract must be verified at the binding.

## 3. Table of C default argument promotions

Applies to **arguments in `...`**, not automatically applied to fixed prototype parameters.

| Original C type | Type when passed through `...` | Common FFM layout on desktop ABIs | Notes |
| --- | --- | --- | --- |
| `float` | **`double`** | `ValueLayout.JAVA_DOUBLE` | Java must pass `double`, not `float` |
| `char`, `signed char` | `int` if `int` can represent the value | `JAVA_INT` | Java `byte` must be cast to `int` |
| `unsigned char` | `int` if it fits the full range, otherwise `unsigned int` | Usually `JAVA_INT` | Verify special ABIs |
| `short` / `unsigned short` | `int` or `unsigned int` per integer promotions | Usually `JAVA_INT` | `JAVA_SHORT` is inappropriate at `...` |
| `_Bool` | `int` in integer promotions | Usually `JAVA_INT` | C only has 0/1 for `_Bool` |
| C enumeration | integer-promoted type | Usually `JAVA_INT` | Enum has implementation-defined underlying type/range |
| `int` / `unsigned int` | Keeps corresponding kind | `JAVA_INT` | Signedness needs proper mapping |
| `double` | `double` | `JAVA_DOUBLE` | Not promoted to `long double` |
| `long` / `long long` | Keeps corresponding kind | canonical C layout | C `long` is 32-bit on Windows x64, typically 64-bit on Linux x64 |
| C pointer (`void*`, `char*`) | Pointer | `ADDRESS` | Correct pointer lifetime and type |
| Struct/union | Not automatically converted to primitive | ABI group layout if supported by native linker | Passing variadic aggregates is complex; prefer a typed wrapper |

**Exact integer promotions:** Small integer types convert to `int` **if `int` can represent all values of the original type**, otherwise to `unsigned int`. On common OS/CPUs (32-bit `int`), `char` and `short` mostly become `int`. Do not assume this on every C implementation.

**Common pitfall:** A `float f=0.1f` value converted to `double` **does not become** the same value as the literal `0.1d`. It keeps the number rounded at float precision, then represents it in double. That is also C default promotion semantics. For exact stdout in the example, we choose `1.25f` and `2.5f`, both of which are exactly representable in binary floating point.

## 4. `firstVariadicArg` marks the ABI boundary rather than adding arguments

JDK 22 provides:

~~~java
// API description snippet only; see runnable example in section 8.
Linker.Option.firstVariadicArg(int index);
~~~

For a `FunctionDescriptor` with `N` argument layouts, the index is in the range **0 ≤ index ≤ N**:

- `index=0`: marks all arguments as variadic; only use if the contract/prototype actually has that meaning.
- `0 < index < N`: the argument layout at index and all layouts after it are variadic.
- `index=N`: **no variadic arguments in this specific call**.
- **You must still pass `firstVariadicArg` when `index=N`** to mark that the original function has `...`; some C ABIs still distinguish a variadic call from a non-variadic call when the number of variadic elements is 0.

For example, with `long long sum_ints(int count, ...)`:

| C call | Argument layouts in descriptor (excluding return) | `firstVariadicArg` |
| --- | --- | ---: |
| `sum_ints(0)` | `(JAVA_INT)` | 1 = N |
| `sum_ints(1,42)` | `(JAVA_INT,JAVA_INT)` | 1 |
| `sum_ints(3,10,20,-5)` | `(JAVA_INT,JAVA_INT,JAVA_INT,JAVA_INT)` | 1 |

The same C symbol has three **specialized forms** and requires `MethodHandle`s with the corresponding arities. `firstVariadicArg(1)` does not turn Java `invokeExact` into a method with `Object...`. Java must still supply the exact number and exact carrier types according to `FunctionDescriptor`.

With `long long add_from(int base,int count,...)`, the number of fixed arguments is 2; use `firstVariadicArg(2)` even when no extra arguments are passed (`N=2`). Using index 1 by mistake causes FFM to treat `count` as variadic even though the C declaration states it is fixed.

### 4.1. Why does the boundary affect the ABI?

Some C ABIs pass variadic arguments differently from fixed prototypes, especially regarding floating-point/vector registers and related metadata. Evidence that a descriptor "happened to work" on one machine is not enough to prove portability. `firstVariadicArg` helps the linker apply the appropriate rules for arguments starting at the specified position. You need to know the **exact number of fixed arguments from the C header** instead of guessing from tests.

The Oracle JDK 22 `Linker` also specifies that the native linker only supports linking a **specialized form** of a variadic function; it does not automatically apply default promotions. The native linker may reject a layout representing an unpromoted C type at a variadic position; on Linux/x64, examples include C `float`, `char`, and `short`. However, you cannot rely on the linker to catch **every** wrong descriptor: a C symbol does not contain enough type/argument-count metadata to cross-check.

## 5. Building `FunctionDescriptor` with the right return, fixed, and variadic arguments

With C:

~~~c
long long sum_ints(int count, ...);
~~~

FFM Java 22+:

~~~java
// Illustrative snippet: requires Java imports, linker, and symbol before running.
FunctionDescriptor callThree = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG, // C long long result
        ValueLayout.JAVA_INT,  // fixed count, index 0
        ValueLayout.JAVA_INT,  // vararg index 1
        ValueLayout.JAVA_INT,  // vararg index 2
        ValueLayout.JAVA_INT); // vararg index 3

MethodHandle sumThree = linker.downcallHandle(
        sumSymbol, callThree,
        Linker.Option.firstVariadicArg(1));

long value = (long) sumThree.invokeExact(3, 10, 20, -5);
~~~

**Note on method-handle typing:** `ValueLayout.JAVA_INT` produces Java carrier `int`, `JAVA_LONG` is Java `long`; in `invokeExact`, the call site must use the exact argument/return Java types. If the original Java variable is `short`, cast it explicitly to `int`, and similarly cast `float` to `double` when participating in a variadic call. If it does not match `MethodHandle.type()`, Java usually throws `WrongMethodTypeException`, but **this is a Java type check**, not proof that the actual C ABI signature is right.

Descriptor for a call with no extra args:

~~~java
FunctionDescriptor callZero = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,
        ValueLayout.JAVA_INT);

MethodHandle sumZero = linker.downcallHandle(
        sumSymbol, callZero,
        Linker.Option.firstVariadicArg(1));
long zero = (long) sumZero.invokeExact(0);
~~~

**Important:** the return layout **stands separately before the argument list** and **is not counted in `firstVariadicArg`**. If the function returns `void`, use `FunctionDescriptor.ofVoid(...)`; the argument layouts list still starts at index 0.

### 5.1. When to use `JAVA_FLOAT`?

If the C function does not have `...`:

~~~c
double fixed_float(float x);
~~~

then `x` is a fixed prototype parameter with C type `float`. The appropriate FFM descriptor on common ABIs is:

~~~java
FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE, // C double return
        ValueLayout.JAVA_FLOAT); // C fixed float argument
~~~

Do **not** promote `fixed_float(float)` to `double`: ellipsis promotions do not apply to a fixed parameter that already has a prototype. Conversely, a `float` passed through `...` must become `double`. The complete example runs both to prove it.

## 6. Mismatches in `printf` and how to reduce risk

Prototype:

~~~c
int printf(const char *format, ...);
~~~

In Java FFM, the call equivalent to `printf("%d + %.2f",7,1.25)` requires:

~~~java
// JDK 22+ snippet, assuming linker is Linker.nativeLinker()
// and the native C library contains the printf symbol in defaultLookup().
MethodHandle printf = linker.downcallHandle(
        linker.defaultLookup().find("printf").orElseThrow(),
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,    // C int return
                ValueLayout.ADDRESS,     // const char* fixed
                ValueLayout.JAVA_INT,    // %d: promoted int
                ValueLayout.JAVA_DOUBLE),// %f: double
        Linker.Option.firstVariadicArg(1));

try (Arena arena = Arena.ofConfined()) {
    MemorySegment fmt = arena.allocateFrom("%d + %.2f\n");
    int printed = (int) printf.invokeExact(fmt, 7, 1.25d);
}
~~~

This is an **illustrative snippet**, not a standalone runnable file: it needs imports, `throws Throwable`, native access permission, and native `printf` present in the corresponding lookup. To test consistently across Linux/macOS/Windows, the article uses a custom C library in section 7 instead of depending on libc and `printf`'s locale.

With format-based APIs, **having the right layout is not enough**: each conversion specifier must match the actual data type after promotions:

- `%d` requires C `int` (Java layout is usually `JAVA_INT`).
- `%f`/`%.2f` of `printf` requires **double**, not float; FFM `JAVA_DOUBLE`.
- `%s` requires C `char*` pointing to a byte string with a NUL terminator and valid lifetime; FFM `ADDRESS`/`MemorySegment`.
- `%p` requires an appropriate pointer; do not use Java `long` just because pointers are 8 bytes wide.
- `%ld` requires C `long`, `%lld` requires C `long long`, `%zu` requires `size_t`. C `long` is typically 32-bit on Windows x64 but 64-bit on Linux x64; see `linker.canonicalLayouts()`.
- `%*.*f` consumes two variadic `int`s for width/precision **before** a `double`.
- `%n` writes through a pointer; a user-controlled format string can create an arbitrary read/write risk. Do not pass an untrusted string as the format.

**Wrong type/wrong count is C undefined behavior**, which can crash the JVM rather than necessarily throwing a Java exception. `printf("%d", 1.5)` does not automatically cast double to int. In particular, never use `sprintf` without capacity; when formatted C output is needed, prefer `snprintf` with a buffer cap and check the result.

A safer C wrapper API usually separates typed functions:

~~~c
/* Interface illustration only; not a complete standalone runnable file. */
int log_i32(const char *label, int32_t value);
int log_f64(const char *label, double value);
int log_blob(const unsigned char *bytes, size_t count);
~~~

These three functions can be called with fixed FFM descriptors, without attaching runtime varargs metadata. For dynamic format data from a Java client, a `pointer+length`-style wrapper is usually more maintainable than a system that dynamically generates every variadic signature.

## 7. Complete C11: `varbridge` library with three variadic forms and one fixed function

To learn from a standalone example, we use a pure C ABI, without `JNIEnv` or `Java_package_Class_method` functions. The library exports four functions:

- `sum_ints(int count,...)`: reads `count` variadic `int`s; Java creates one handle for 3 extras and one handle for 0 extras.
- `sum_pairs(int pair_count,...)`: sequentially reads `int,double` pairs; Java prepares `short/byte` as `int` and `float` as `double`.
- `add_from(int base,int count,...)`: two fixed args, testing `firstVariadicArg(2)`.
- `fixed_float(float value)`: non-variadic control case, `JAVA_FLOAT` input.

Layout:

~~~text
ffm-varargs/
├── native/
│   └── varbridge.c
├── src/
│   └── VariadicDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

Create the complete file `native/varbridge.c`:

~~~c
#include <stdarg.h>

#if defined(_WIN32)
#define API_EXPORT __declspec(dllexport)
#else
#define API_EXPORT __attribute__((visibility("default")))
#endif

/* Demo for common targets: 32-bit int, 64-bit long long, 64-bit double. */
_Static_assert(sizeof(int) == 4, "C int must be 4 bytes");
_Static_assert(sizeof(long long) == 8, "C long long must be 8 bytes");
_Static_assert(sizeof(double) == 8, "C double must be 8 bytes");

API_EXPORT long long sum_ints(int count, ...) {
    if (count < 0 || count > 16) {
        return -1;
    }

    va_list ap;
    va_start(ap, count);
    long long total = 0;
    for (int i = 0; i < count; ++i) {
        total += (long long) va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

API_EXPORT double sum_pairs(int pair_count, ...) {
    if (pair_count < 0 || pair_count > 8) {
        return -1.0;
    }

    va_list ap;
    va_start(ap, pair_count);
    double total = 0.0;
    for (int i = 0; i < pair_count; ++i) {
        int whole = va_arg(ap, int);
        double fraction = va_arg(ap, double);
        total += (double)whole + fraction;
    }
    va_end(ap);
    return total;
}

API_EXPORT long long add_from(int base, int count, ...) {
    if (count < 0 || count > 16) {
        return -1;
    }

    va_list ap;
    va_start(ap, count);
    long long total = (long long)base;
    for (int i = 0; i < count; ++i) {
        total += (long long) va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

API_EXPORT double fixed_float(float value) {
    return (double)value;
}
~~~

**This is the complete C11 file**, compiled into a shared library, with no `main`. `API_EXPORT` ensures the C symbols appear in the binary on GCC/Clang/MSVC. `_Static_assert` prevents using the example on targets that differ from the stated width assumptions; you still need to verify the target architecture/toolchain ABI when deploying.

Because `va_arg(ap, int)` is only used after Java has sent an `int`, and `va_arg(ap, double)` is only used after Java `double`, C reads the exact values. `sum_ints` limits count≤16 so summing up to 16 `int`s can be represented in `long long` without overflow. For `sum_pairs`, count≤8; both Java and C must agree that **each pair consumes two arguments**. These guards do not fix a mismatch when the caller says 3 but only supplies two variadic arguments.

**Note on `va_start`:** in `add_from(int base,int count,...)` you must call `va_start(ap,count)` because `count` is the **last named parameter**. Calling `va_start(ap,base)` does not properly describe the starting position of variadic parameters in C and can cause undefined behavior.

## 8. Complete Java 22+: specializing four call forms

Create the complete file `src/VariadicDemo.java`, without a package declaration:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class VariadicDemo {
    private VariadicDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of("build", "lib",
                System.mapLibraryName("varbridge")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            MemorySegment sumAddress =
                    symbols.find("sum_ints").orElseThrow();

            // sum_ints(3, 10, 20, -5): 1 fixed + 3 variadic ints.
            MethodHandle sumThree = linker.downcallHandle(
                    sumAddress,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    Linker.Option.firstVariadicArg(1));

            long sum3 = (long) sumThree.invokeExact(3, 10, 20, -5);

            // Same C function, but this time with NO extra args.
            // Still use firstVariadicArg(1), equal to N=1.
            MethodHandle sumZero = linker.downcallHandle(
                    sumAddress,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT),
                    Linker.Option.firstVariadicArg(1));

            long sum0 = (long) sumZero.invokeExact(0);

            // Each pair consumes int + double after promotion.
            MethodHandle pairs = linker.downcallHandle(
                    symbols.find("sum_pairs").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.JAVA_INT,    // fixed pair_count
                            ValueLayout.JAVA_INT,    // promoted short
                            ValueLayout.JAVA_DOUBLE, // promoted float
                            ValueLayout.JAVA_INT,    // promoted byte
                            ValueLayout.JAVA_DOUBLE),// promoted float
                    Linker.Option.firstVariadicArg(1));

            short firstWhole = 7;
            float firstFraction = 1.25f;
            byte secondWhole = -2;
            float secondFraction = 2.5f;

            double pairSum = (double) pairs.invokeExact(
                    2,
                    (int) firstWhole, (double) firstFraction,
                    (int) secondWhole, (double) secondFraction);

            // Two fixed arguments: base index 0, count index 1.
            MethodHandle addFrom = linker.downcallHandle(
                    symbols.find("add_from").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.JAVA_INT,  // fixed base
                            ValueLayout.JAVA_INT,  // fixed count
                            ValueLayout.JAVA_INT,  // variadic
                            ValueLayout.JAVA_INT), // variadic
                    Linker.Option.firstVariadicArg(2));

            long twoFixed = (long) addFrom.invokeExact(100, 2, 20, -3);

            // Non-variadic: fixed C float -> JAVA_FLOAT.
            MethodHandle fixedFloat = linker.downcallHandle(
                    symbols.find("fixed_float").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_DOUBLE,
                            ValueLayout.JAVA_FLOAT));

            double fixed = (double) fixedFloat.invokeExact(1.25f);

            System.out.println("sum3=" + sum3);
            System.out.println("sum0=" + sum0);
            System.out.println("pairSum=" + pairSum);
            System.out.println("twoFixed=" + twoFixed);
            System.out.println("fixedFloat=" + fixed);
        }
    }
}
~~~

**Why do these calls match C?**

1. `sumThree` takes Java arguments `(int,int,int,int)`, returns `long`, fixed count has index 0; the linker knows indices 1..3 are variadic.
2. `sumZero` takes `(int)`, returns `long`, `index=N=1`, still attaches firstVariadicArg because the C prototype has `...`.
3. `pairs` takes `(int,int,double,int,double)`; `short`/`byte` are explicitly cast in Java to int, `float` to double before `invokeExact`. C `va_arg(ap,int)` and `va_arg(ap,double)` read in the right order.
4. `addFrom` has `firstVariadicArg(2)`, avoiding mistakenly marking fixed `count` as variadic.
5. `fixedFloat` takes `float`, returns `double`, and needs no option, helping distinguish the fixed-parameter ABI from the ellipsis.
6. `SymbolLookup.libraryLookup(path,arena)` uses the path to the built library, and `Arena` remains open throughout the downcalls. After close, do not continue calling MethodHandles tied to library symbols.
7. `MethodHandle.invokeExact` requires exact Java carrier types; `throws Throwable` is a concise way to write the educational example.

**Do not use `javac -h`:** this is a C ABI called directly by FFM, not JNI-style native methods. There are no `JNIEnv*` or `jobject` parameters.

## 9. Building on Linux, macOS, and Windows

Run from the root directory `ffm-varargs`. Requires **JDK 22+** with final FFM, a C compiler supporting C11, and a shared library with the same CPU architecture as the JVM.

### 9.1. Linux (GCC/Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/varbridge.c -o build/lib/libvarbridge.so

javac -d build/classes src/VariadicDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes VariadicDemo
~~~

### 9.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/varbridge.c -o build/lib/libvarbridge.dylib

javac -d build/classes src/VariadicDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes VariadicDemo
~~~

### 9.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /std:c11 /LD native\varbridge.c ^
  /link /OUT:build\lib\varbridge.dll

javac -d build\classes src\VariadicDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes VariadicDemo
~~~

The Windows commands use **Command Prompt**, with `^` for line continuation. MSVC needs `/std:c11` support; run from a Developer Command Prompt configured for x64. The JDK and the shared library must have the same architecture. `System.mapLibraryName("varbridge")` produces the corresponding OS name.

**Native-access flag:** `--enable-native-access=ALL-UNNAMED` is for the classpath/unnamed module; for a named module, grant permission by module name instead of opening it to all. `SymbolLookup.libraryLookup` and `Linker.downcallHandle` are restricted operations. JDK 22+ **does not require `--enable-preview`**.

### 9.4. Expected stdout from source

~~~text
sum3=25
sum0=0
pairSum=8.75
twoFixed=117
fixedFloat=1.25
~~~

The calculations are determined as:

- `sum3` = 10 + 20 - 5 = **25**.
- `sum0` = 0 because C count is 0 so it does not read any `va_arg`.
- `pairSum` = (7 + 1.25) + (-2 + 2.5) = **8.75**.
- `twoFixed` = base 100 + 20 - 3 = **117**.
- `fixedFloat` = float 1.25f converted by C to double 1.25 to return; fixed input is still passed as C `float`.

This is stdout **derived from the source logic** assuming a correct ABI and successful build, not a claim that the compiler was run on your machine. Run an actual integration test on the target OS/architecture to confirm.

### 9.5. Checking exported C symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libvarbridge.so
~~~

Expected names:

~~~text
sum_ints
sum_pairs
add_from
fixed_float
~~~

macOS: `nm -gU build/lib/libvarbridge.dylib` (Mach-O tools usually prepend `_` to symbol names); Windows: `dumpbin /exports build\lib\varbridge.dll`. `symbols.find(...).orElseThrow()` throws `NoSuchElementException` if the name is not found. Do not confuse lookup/export errors with promotion or `firstVariadicArg` errors.

## 10. When mapping the C ABI, type names are not enough

FFM `ValueLayout` has a Java carrier and specific size/alignment. The **C ABI** also depends on OS/CPU/compiler. In particular:

- C `int` is typically 32 bits wide on desktop platforms; `ValueLayout.JAVA_INT` fits in the example with `_Static_assert(sizeof(int)==4)`.
- C `double` is typically 64 bits wide; the example checks `sizeof(double)==8` and uses `JAVA_DOUBLE`.
- C `long long` in the example is 8 bytes; the return layout uses `JAVA_LONG` on common targets, and a static assert guards the width.
- C `long` is typically 64-bit on Linux x64 but 32-bit on Windows x64. `JAVA_LONG` is a 64-bit Java long and must not be mapped by default for every C long.
- C `size_t` is typically 64-bit on 64-bit and 32-bit on 32-bit. Do not use Java `int` or `long` based on the name.
- Pointers use `ValueLayout.ADDRESS` with Java carrier `MemorySegment`, **not** `JAVA_LONG` just because pointers are 8 bytes.
- C `long double` is not synonymous with `double`; the linker may not support the corresponding layout on the target ABI.

To inspect canonical mappings:

~~~java
// Java 22+ illustrative snippet, not a standalone program.
Linker linker = Linker.nativeLinker();
var cInt = linker.canonicalLayouts().get("int");
var cLong = linker.canonicalLayouts().get("long");
var cLongLong = linker.canonicalLayouts().get("long long");
var cSizeT = linker.canonicalLayouts().get("size_t");
var cDouble = linker.canonicalLayouts().get("double");
~~~

**Correct order:** (1) determine the C type *after default promotion* at each variadic position; (2) get the ABI layout for that type; (3) match the Java carrier at `invokeExact`. Getting canonical `"float"` and placing it directly in a variadic position is still wrong: the C caller has already converted float to double.

For C++ APIs with `...`, do not assume vtable/name mangling and C++ exception semantics are handled automatically by FFM. If possible, write a C ABI wrapper with `extern "C"` and typed parameters for stable binding.

## 11. Why can a small discrepancy cause a big error?

A native function does not contain enough metadata for FFM to determine whether you declared the right descriptor. Discrepancies can occur at three layers:

| Layer | What must be right | Common mistakes |
| --- | --- | --- |
| **Java MethodHandle** | Java carrier and arity match descriptor | `WrongMethodTypeException` from passing float/short when handle expects double/int |
| **FFM → C ABI** | `firstVariadicArg`, type layouts, return layout, register classes are right | Linker rejects unsupported layout or produces a non-portable call |
| **C callee** | `va_arg(ap,T)`, count/format/types match caller | Undefined behavior, wrong numbers, memory corruption, or JVM crash |

Some ABI mismatches have no reliable exception to catch. In particular, swapping a `JAVA_INT` for `JAVA_DOUBLE` in the descriptor or setting the wrong index can cause C to read the wrong floating-point/integer register. `-Xcheck:jni` is also not a complete solution for **FFM downcall** errors; the JNI checker and the FFM API are two different boundaries.

For production programs, you should **restrict the set of supported signatures**, run them through tests on each OS/architecture, and split the contract into typed C wrappers when the `...` structure is too dynamic. Do not let users supply both an unchecked format string and a list/native type and pass them directly through FFM.

### 11.1. How to cache specialized handles?

If you only have forms like `sum_ints(count=0)`, `sum_ints(count=1)`, and `sum_ints(count=3)`, create three handles with separate descriptors and cache them by **(symbol, return ABI, ordered argument layouts, firstVariadicArg)**. Do not cache a handle of type `(int,int,int,int)→long` and use it to call with one argument. Handles and symbol addresses must remain valid throughout the lifetime of the native library/`Arena` holding `libraryLookup`.

For a printf-style API, you can provide typed Java wrappers:

~~~java
// Illustrative Java interface snippet, no implementation here.
int printInt(MemorySegment format, int value);
int printDouble(MemorySegment format, double value);
int printIntDouble(MemorySegment format, int value, double value);
~~~

Each wrapper uses a tested specialized FFM handle. If a dynamic format is incompatible with the wrapper, reject it or use Java-side formatting, rather than arbitrarily casting data to fit the ABI.

## 12. Common errors and how to handle them

| Symptom/anti-pattern | Cause | Fix |
| --- | --- | --- |
| `JAVA_FLOAT` in ellipsis region | C `float` is promoted to `double` | Use `JAVA_DOUBLE` and Java `double` |
| `JAVA_SHORT/JAVA_BYTE` in ellipsis region | C integer promotions | Use C promoted type/layout, usually `JAVA_INT` |
| Calling variadic function without `firstVariadicArg` | ABI is not described as variadic | Always add the option, even with no extras |
| `firstVariadicArg(1)` for C with two fixed params | Wrong fixed/variadic boundary | Count the parameter list and use index 2 |
| `firstVariadicArg(N+1)` | Index out of [0,N] | Keep index within bounds per `argumentLayouts` |
| Using the same handle for different numbers of extras | `MethodHandle` has fixed arity | Create another specialized handle |
| `invokeExact` with Java `short` when layout is `JAVA_INT` | Carrier mismatch | Explicitly cast `(int) value` |
| `invokeExact` with Java `float` when layout is `JAVA_DOUBLE` | Carrier mismatch | Explicitly cast `(double) value` |
| `va_arg(ap,float)` for C ellipsis float | C already promoted float to double | Use `va_arg(ap,double)` |
| `va_start(ap,base)` when last fixed is `count` | Wrong last named parameter | `va_start(ap,count)` |
| C count mismatches number of passed arguments | No runtime arity check in C `...` | Constrain count and descriptor, test positive cases |
| `printf` format `%s` with Java `String` | Java String is not a C pointer | Allocate C string buffer with NUL/encoding/lifetime |
| `printf` format controlled by input | Can cause format-string vulnerability | Fixed format, escape data, typed wrappers |
| C `long` assumed 64-bit on Windows x64 | LLP64 vs LP64 | Use `canonicalLayouts()` |
| `long double` described as `JAVA_DOUBLE` | Different ABI and not guaranteed supported | Use a fixed C wrapper |
| Code works on Linux but fails on Windows | Different variadic ABI or native export | Check index, layouts, build arch, ABI |
| Missing native-access flag | Restricted operations are blocked | Grant permission to the right module |
| Library lookup succeeds but symbol is missing | Wrong C export/name path | Check `nm`/`dumpbin` |
| Java closes arena too early | Symbol/lookup lifetime ends | Keep scope alive until all downcalls finish |

### 12.1. Why is `printf("%f", 1.25f)` different from `fixed_float(1.25f)`?

In C, the literal `1.25f` has type `float`. But `printf` has `...`, so C automatically promotes float to double and `printf` reads a double. `fixed_float(float)` has a prototype explicitly declaring float, so it receives a float. This reflects the **C contract** rather than the absolute safety of a Java conversion. The FFM Java caller must describe the two different ABI types accurately.

## 13. Exercises by difficulty

1. How many fixed arguments does `int printf(const char *fmt,...)` have, and what is the first variadic index? **One, index 1.**
2. What index does `void log(int severity,const char *fmt,...)` have? **2.**
3. How many argument layouts does `sum_ints(0)` need? Is the option needed? **One fixed `JAVA_INT`; `firstVariadicArg(1)` is needed.**
4. How many argument layouts does the descriptor for `sum_ints(1,42)` need? **Two `JAVA_INT`s, index 1.**
5. Can `sum_ints(3,10,20,-5)` use the handle of `sum_ints(0)`? **No: different arity.**
6. C `float f=1.25f; log(1,f)`, what is the argument of `f` at the C ABI? **double; FFM `JAVA_DOUBLE`.**
7. Which Java carrier does Java `byte b=-2` need when entering a C ellipsis expecting `int`? **Java int, cast `(int)b`.**
8. Why is `JAVA_BOOLEAN` not used directly for `_Bool` at a C ellipsis? **Integer promotion, usually `int`.**
9. What input layout does C `double fixed_float(float)` need? **`JAVA_FLOAT`, because the input is fixed rather than variadic.**
10. C `void output(int count,...)` reads `va_arg(ap,double)` when Java passes `JAVA_INT`: what is wrong? **Promoted types do not match; undefined behavior.**
11. How many variadic arguments and what types does C `printf("%*.*f",width,precision,value)` need? **Three: int, int, double.**
12. Should C `long` on Windows x64 automatically map to `JAVA_LONG`? **No; C long is typically 32-bit.**
13. Why not omit `firstVariadicArg` if all arguments are int? **The variadic ABI can differ and the spec requires the option.**
14. When a C API takes a C++ object or `long double` via ellipsis and the linker does not support it, what should you do? **Typed C ABI wrapper.**
15. How do you handle an untrusted printf format? **Do not use input as format; build a fixed format or format in Java beforehand.**
16. Why does testing on one OS not prove correctness? **The C ABI and register calling convention differ by target.**

The exercises intentionally ask about contracts/types rather than asking you to run **ABI-mismatched FFM snippets**. Do not deliberately call native code with a mismatched descriptor just to see which exception the JVM throws; a wrong ABI can crash the entire process.

## 14. Checklist before putting C variadic downcalls into production

- [ ] Does the C header have `...`? Have you counted **fixed parameters** to choose the right 0-based `firstVariadicArg(index)`?
- [ ] Have you built a `FunctionDescriptor` containing each actual argument layout in the exact order of **one specialized call**?
- [ ] Did you attach the `firstVariadicArg` option **even when passing no extra arguments** (`index=N`)?
- [ ] Have you applied **default argument promotions** for all `...`: `float→double`, narrow integers→`int/unsigned int` per C?
- [ ] Are the Java carriers at `invokeExact` `int`/`double`/`MemorySegment` compatible with the layouts, without mistakenly using `short/float`?
- [ ] Does C `va_arg(ap,T)` consume the right argument type/count, is `va_start` based on the last fixed parameter, and is `va_end` called?
- [ ] Have return type, C `long`/`long long`/`size_t`, pointers, signedness, and ABI canonical layouts been verified on the target?
- [ ] Have you tested the descriptor/`firstVariadicArg` on each target OS/CPU/ABI, rather than inferring from one lucky run?
- [ ] For format-based APIs, do format specifiers, width/precision `*`, encoding, NUL terminator, buffer capacity, and arg count match?
- [ ] Is the format string free from untrusted input control; have you avoided `sprintf` without capacity and unwanted `%n`?
- [ ] Is the native library exported with the right name, do the JVM/compiler architectures match, and does the arena keep symbols alive throughout downcalls?
- [ ] Have you granted appropriate native access permission on JDK 22+; without confusing the final API code with Java 17 incubator/Java 21 preview?
- [ ] When the number/types of arguments vary freely at runtime, have you considered a **typed C wrapper + array/count** to reduce the risk of varargs mismatch?
- [ ] Are you avoiding relying on Java's `IllegalArgumentException`/`WrongMethodTypeException` as proof that the C ABI/format is completely right?

**Conclusion:** Calling a C `...` function through FFM does not mean Java automatically has "C varargs". Each call must be **specialized into a fixed descriptor**, mark the boundary correctly with `Linker.Option.firstVariadicArg`, and use **C default-promoted types** for the variadic part. When the number and types of dynamically generated arguments cannot be proven with certainty, a **C wrapper with a typed signature** is a safer, clearer, and more testable choice.

### Authoritative references to check

- Oracle, [JDK 22 Linker — Variadic functions](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): specialized forms, `printf` example, promotion, and native linker limitations.
- Oracle, [JDK 22 Linker.Option — firstVariadicArg](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html#firstVariadicArg(int)): index [0,N], no extra argument case, calling convention rules.
- Oracle, [JDK 22 FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): return/argument layouts, MethodHandle Java carrier.
- Oracle, [JDK 22 SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): finding C symbols and library lifetime.
- cppreference, [C default argument promotions](https://en.cppreference.com/w/c/language/conversion): integer promotions and float-to-double.
- cppreference, [C `va_arg`](https://en.cppreference.com/w/c/variadic/va_arg): how to read C variadic arguments with the right promoted type.
- cppreference, [C printf](https://en.cppreference.com/w/c/io/fprintf): format strings, arguments after promotions, and undefined behavior.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): FFM becoming a standard API since JDK 22.