# Describing C Signatures with FunctionDescriptor.of or ofVoid in Java FFM

## 1. The problem to solve: How does Java know what arguments a C function has?

In the **Foreign Function & Memory API (FFM)**, Java code can directly call a native function of a C library via `Linker` and `MethodHandle`. To create a handle, the Java program needs to describe the **exact C signature at the ABI level**: how many arguments the function takes, what data types/widths/alignments they have, and what it returns. The class responsible for this is **`java.lang.foreign.FunctionDescriptor`**.

The two most important factories:

~~~java
// Java 22+; this is an API excerpt, not a standalone program.
FunctionDescriptor.of(returnLayout, argumentLayouts...);
FunctionDescriptor.ofVoid(argumentLayouts...);
~~~

- **`FunctionDescriptor.of(returnLayout, argLayouts...)`**: used for C functions **that have a return value**. The first layout is the **C result type**, and the subsequent layouts are the **C parameters in exact order**.
- **`FunctionDescriptor.ofVoid(argLayouts...)`**: used for C functions whose **return type is `void`**. Pass only the layouts of the parameters; **there is no return layout**.
- Both accept **0 parameters**. A C function `int forty_two(void)` is described by `FunctionDescriptor.of(ValueLayout.JAVA_INT)`; `void reset(void)` by `FunctionDescriptor.ofVoid()`.
- `FunctionDescriptor` **is only a signature description**; it does not look up symbols, does not call native functions, does not allocate memory, and **does not automatically verify C headers**.
- `Linker.downcallHandle` uses the descriptor to create a `MethodHandle` that calls the native function. **A wrong descriptor can cause wrong results, memory corruption, or a JVM crash**, even when Java compiles without errors.

Examples on a **Linux x86-64** environment with 32-bit C `int`:

| C signature | Java FFM descriptor | Expected method handle type |
| --- | --- | --- |
| `int add(int a, int b);` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` | `(int,int)int` |
| `void store(int *out, int value);` | `FunctionDescriptor.ofVoid(ADDRESS, JAVA_INT)` | `(MemorySegment,int)void` |
| `double mul(double x, double y);` | `FunctionDescriptor.of(JAVA_DOUBLE, JAVA_DOUBLE, JAVA_DOUBLE)` | `(double,double)double` |
| `void reset(void);` | `FunctionDescriptor.ofVoid()` | `()void` |
| `void *allocate(size_t n);` | `FunctionDescriptor.of(ADDRESS, sizeTLayout)` | Depends on the carrier of `size_t` |
| `size_t strlen(const char *s);` | `FunctionDescriptor.of(sizeTLayout, ADDRESS)` | Depends on the ABI of `size_t` |

`JAVA_INT`, `ADDRESS`, and `JAVA_DOUBLE` in the table are constants of `ValueLayout`; static imports can be used for brevity, but the full examples will write `ValueLayout.JAVA_INT` to make them easy to follow.

**Lesson objectives:** understand how to choose `of`/`ofVoid`, read C prototypes, choose the right `MemoryLayout` according to the ABI, understand `toMethodType` and `invokeExact`, use `Linker`/`SymbolLookup` to run real examples with Java 22+, and avoid especially dangerous mistakes such as describing `void*` as `void` or describing a C pointer as a C struct value.

## 2. Version lock-in: FFM JDK 22+ and differences from preview releases

This lesson uses the **final FFM API from JDK 22** (JEP 454):

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

In JDK 17–18, FFM was still in the incubator module `jdk.incubator.foreign`; JDK 19–21 used `java.lang.foreign` in preview form and had many renames/signature changes. Do not take a `FunctionDescriptor.of` example from one preview release to another without checking the **exact version's Javadoc**.

With JDK 22 and later:

- `FunctionDescriptor` and the memory layouts officially belong to `java.base`; **`--enable-preview` is not required** for a program that only creates descriptors.
- Creating a downcall handle with `Linker.downcallHandle` and loading a native library with `SymbolLookup.libraryLookup` are **restricted** operations: grant native access to the module calling them, for example `--enable-native-access=ALL-UNNAMED` when running a class on the classpath.
- `FunctionDescriptor.of(...)` itself **is not a C call**. Therefore, a program that only prints descriptors (section 8) does not need a native library and does not need native access permission.
- The policy for warning/blocking restricted operations changes across later JDK versions; check the actual JDK and flags. For the program demonstrating C linking (section 9), **explicitly enable native access**.

Before starting:

~~~bash
java -version
javac -version
~~~

If the build is using JDK 21 preview while the terminal runs JDK 22, compilation failure may be due to the toolchain/preview flag, not the nature of describing C signatures. Always clearly record the **target JDK, OS, CPU architecture, and C compiler ABI**.

## 3. How to read the two factory signatures accurately

In JDK 22, the relevant methods are:

~~~java
static FunctionDescriptor of(
        MemoryLayout resLayout,
        MemoryLayout... argLayouts);

static FunctionDescriptor ofVoid(
        MemoryLayout... argLayouts);
~~~

### 3.1. `of`: the result comes first, not the first C parameter

C:

~~~c
/* Illustrative prototypes. */
int sum(int left, int right);
double ratio(double numerator, double denominator);
char *duplicate_text(const char *source);
~~~

FFM on Linux/x64, with verified ABI mappings:

~~~java
// Java 22+; non-standalone excerpt.
FunctionDescriptor sumDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,    // C return int
        ValueLayout.JAVA_INT,    // C parameter 1: left
        ValueLayout.JAVA_INT);   // C parameter 2: right

FunctionDescriptor ratioDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE, // C return double
        ValueLayout.JAVA_DOUBLE, // C parameter 1
        ValueLayout.JAVA_DOUBLE);// C parameter 2

FunctionDescriptor dupDescriptor = FunctionDescriptor.of(
        ValueLayout.ADDRESS,     // C return char*
        ValueLayout.ADDRESS);    // C parameter const char*
~~~

The order `of(return, arg1, arg2, ...)` differs from `FunctionDescriptor.ofVoid(arg1, arg2, ...)`. If you accidentally write:

~~~java
// WRONG if the target is int sum(int,int).
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

then you have declared **one** C parameter, not two. The Java code still compiles and the descriptor still exists, but when using it to link to `sum`, the native call may pass the wrong number of arguments.

### 3.2. `ofVoid`: the C result is `void`

C:

~~~c
/* Illustrative prototypes. */
void reset(void);
void log_code(int code);
void store(int *destination, int value);
~~~

Java:

~~~java
// Java 22+, excerpt.
FunctionDescriptor resetDescriptor =
        FunctionDescriptor.ofVoid();

FunctionDescriptor logDescriptor =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);

FunctionDescriptor storeDescriptor =
        FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT);
~~~

There is no corresponding “`ValueLayout.JAVA_VOID`” to pass into `of`. **`void` as a return** is represented by having no return layout; `void` in a **C parameter list `f(void)`** means **no parameters**, so pass 0 argument layouts.

Comparison:

| C declaration | Meaning | Choose factory |
| --- | --- | --- |
| `void stop(void);` | No arguments, no result | `ofVoid()` |
| `int status(void);` | No arguments, returns int | `of(JAVA_INT)` |
| `void update(int id);` | One int argument, no result | `ofVoid(JAVA_INT)` |
| `int update(int id);` | One int argument, returns int | `of(JAVA_INT, JAVA_INT)` |
| `void *create(void);` | No arguments, returns **pointer** | `of(ADDRESS)` |
| `void consume(void *p);` | One **pointer** argument, no result | `ofVoid(ADDRESS)` |

**A pointer to type `void` (C `void*`) is not a function returning `void`.** This is a conceptual confusion that very easily leads to a wrong descriptor.

## 4. FunctionDescriptor describes the ABI, not the Java source signature

C prototype:

~~~c
int add_i32(int a, int b);
~~~

FFM descriptor:

~~~java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

After `Linker` creates the downcall handle, the corresponding Java `MethodHandle` has the form:

~~~text
(int, int) -> int
~~~

You do not declare a Java `native int add(int,int)`; FFM works with a `MethodHandle` that the JVM creates based on the **C calling convention**. `FunctionDescriptor` is not a hand-passed `MethodType` like some older incubator CLinker APIs.

The differences:

| Component | Java type/API | Which question does it answer? |
| --- | --- | --- |
| C prototype | `int add(int,int);` | What does the native function expect according to the header? |
| FFM descriptor | `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` | What ABI layout do the return/arguments have? |
| Java carrier type | `int.class`, `MemorySegment.class` | Which Java object/primitive is passed through the handle? |
| Method type | `(int,int)int` | Which Java arguments and return does `invokeExact` need? |
| Symbol address | `MemorySegment` from `SymbolLookup` | Where is the function located in the native library? |
| Linker handle | `MethodHandle` from `downcallHandle` | Which ABI downcall execution mechanism is used? |

Creating a descriptor **does not prove** the symbol exists. Symbol lookup **does not carry enough signature information** for the JVM to automatically know what types the native function takes. Therefore, it is possible to create a handle that is “valid in Java” yet points to a C function with a different prototype: FFM will not automatically fix ABI errors for you.

### 4.1. `returnLayout()` and `argumentLayouts()`

~~~java
// Java 22+, excerpt.
FunctionDescriptor d = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS, ValueLayout.JAVA_INT);

boolean hasReturn = d.returnLayout().isPresent(); // false
int arguments = d.argumentLayouts().size();        // 2
~~~

- `returnLayout()` returns `Optional<MemoryLayout>`: with `ofVoid` it will be empty; with `of` it will contain a layout.
- `argumentLayouts()` returns a read-only list in the **exact order of C parameters**. There is no “hidden argument” named return in this list.
- Descriptors cannot be modified by calling `argumentLayouts().add(...)`, because the returned list is unmodifiable.
- `toMethodType()` allows checking the Java carrier types that the layouts dictate, which is very useful before calling `MethodHandle.invokeExact`.

## 5. Mapping from C types to `MemoryLayout`

Do not choose a `ValueLayout` just because the name looks similar. C types must be mapped according to the **ABI of the native library** on the current OS/architecture. Reference table for **Linux x86-64/System V ABI**:

| C type | Commonly used FFM layout | Java carrier |
| --- | --- | --- |
| `_Bool` / `bool` | `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| `char`, `signed char`, `unsigned char` | `ValueLayout.JAVA_BYTE` | `byte` |
| `short` / `unsigned short` | `ValueLayout.JAVA_SHORT` | `short` |
| `int` / `unsigned int` | `ValueLayout.JAVA_INT` | `int` |
| `long` / `unsigned long` | `ValueLayout.JAVA_LONG` | `long` |
| `long long` / `unsigned long long` | `ValueLayout.JAVA_LONG` | `long` |
| `float` | `ValueLayout.JAVA_FLOAT` | `float` |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| `size_t` | `ValueLayout.JAVA_LONG` | `long` |
| `char*`, `const char*`, `int*`, `void*`, function pointer | `ValueLayout.ADDRESS` | `MemorySegment` |
| C struct **by value** | `MemoryLayout.structLayout(...)` matching ABI | `MemorySegment` |
| C union **by value** | `MemoryLayout.unionLayout(...)` matching ABI | `MemorySegment` |

Do not treat this table as strictly portable. For example, on Windows x64, C `long` is usually **32-bit**, whereas on Linux x64 it is **64-bit**. On 32-bit systems, `size_t` can be 32-bit. Choosing the wrong return layout causes the result from registers/stack to be decoded incorrectly.

### 5.1. Querying canonical layouts when a linker is available

JDK 22 allows querying C type mappings according to the current native ABI:

~~~java
// Java 22+, illustration; linker is allowed on supported targets.
Linker linker = Linker.nativeLinker();

MemoryLayout cInt = linker.canonicalLayouts().get("int");
MemoryLayout cLong = linker.canonicalLayouts().get("long");
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cPtr = linker.canonicalLayouts().get("void*");
~~~

The API returns a map of canonical C types according to the linker's ABI. For cross-platform applications, check the actual mapping instead of assuming `JAVA_LONG` is always used for `long` or `size_t`.

Regarding signed/unsigned, C canonical layouts generally describe size/calling convention, and **do not automatically convert Java primitives into unsigned types**. For example, use `Integer.toUnsignedLong(intValue)` to interpret an `unsigned int` result, but you must clearly know that the native function uses an unsigned contract.

### 5.2. `void*`/pointers do not become Java data automatically

`ValueLayout.ADDRESS` represents **a C pointer at the ABI level**, while the Java carrier is `MemorySegment`:

~~~java
// Java 22+, descriptor example, not a complete native call.
FunctionDescriptor strlen = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,    // size_t on Linux x64
        ValueLayout.ADDRESS);     // const char*
~~~

Passing a Java `String` directly into `invokeExact` does not work: you need a compatible native buffer (for example `arena.allocateFrom("hello")`) and must follow encoding, NUL terminator, and lifetime rules.

A pointer returned from C can be `NULL`. In modern FFM, `MemorySegment.NULL` represents the native null address; **do not** call `getString(0)`/`reinterpret` indiscriminately without checking NULL, bounds, ownership, and native allocation lifetime.

### 5.3. C arrays in parameter lists

In C function parameters, a declaration such as:

~~~c
void process_values(int values[], int count);
~~~

is normally adjusted to the equivalent pointer type `int*`. The descriptor is therefore:

~~~java
// Java 22+, excerpt.
FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);
~~~

Not `sequenceLayout(n, JAVA_INT)` like a struct-by-value, because **the C parameter receives the address** of the first element, not a Java array object or a copy-by-value of the entire array.

Conversely, a **struct with an inline array field** still needs to declare `sequenceLayout(...)` when constructing the `StructLayout` for that struct.

## 6. Pointer to struct differs from struct passed by value

Consider C:

~~~c
// Illustrative declarations, not a standalone program.
struct Point { int x; int y; };

void move_point(struct Point *p, int dx, int dy);
struct Point translate(struct Point p, int dx, int dy);
~~~

For `move_point`, the first parameter is a **pointer**:

~~~java
// Java 22+, describes only the signature of the pointer function.
FunctionDescriptor pointerDescriptor = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

For `translate`, the parameter and return are **struct by value**, so the descriptor must use a `GroupLayout` (here a `StructLayout` can be constructed):

~~~java
// Java 22+, excerpt, POINT must be verified with C sizeof/alignof/offsetof.
var POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));

FunctionDescriptor byValue = FunctionDescriptor.of(
        POINT, POINT, ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
~~~

This **does not mean** you can arbitrarily call any ABI just because `POINT.byteSize()==8`. With struct by value, the C calling convention may split fields into registers, stack, or an sret area. The linker uses the ABI to handle this, but **you must describe the C layout accurately**.

Also note: downcalls returning a **group layout by value** usually have an additional Java `SegmentAllocator` argument to allocate memory to hold the result. `FunctionDescriptor.toMethodType()` only converts layouts into carrier types; **the actual method type of the downcall handle may have an extra leading parameter**. Do not infer the full arity of every handle from `toMethodType` when there is a struct return.

### 6.1. Padding inside a group layout, not a standalone argument

`MemoryLayout.paddingLayout(n)` helps describe padding bytes **inside** `structLayout`:

~~~java
// Java 22+; illustrates layout under a hypothetical ABI.
MemoryLayout RECORD = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));
~~~

However, the `FunctionDescriptor.of`/`ofVoid` factories **do not accept a padding layout directly** as a return or argument:

~~~java
// WRONG: must not use a padding layout as a C parameter!
FunctionDescriptor wrong = FunctionDescriptor.ofVoid(
        MemoryLayout.paddingLayout(4));
~~~

JDK 22 throws `IllegalArgumentException` if a return or argument layout is a padding layout. Padding belongs inside composite/group layouts when required by the ABI; it does not represent a C argument.

### 6.2. The ABI of composite types needs C verification

With a struct:

~~~c
// Real header should be used to measure; the following is illustrative only.
struct Packet {
    unsigned char kind;
    int count;
    double value;
};
~~~

You need to measure `sizeof(struct Packet)`, `_Alignof(struct Packet)`, `offsetof(struct Packet, count)`, `offsetof(struct Packet, value)` using the exact C compiler/flags of the library. `MemoryLayout.structLayout(...)` does not automatically add all padding that the C compiler chose. A wrong layout can cause `Linker.downcallHandle` to reject the descriptor or, worse, communicate with the wrong ABI.

## 7. `toMethodType()` and carrier type rules

`FunctionDescriptor.toMethodType()` is useful for checking the **Java types inferred from the layouts**, before making a native call.

| Layout | JDK 22 carrier |
| --- | --- |
| `ValueLayout.JAVA_INT` | `int` |
| `ValueLayout.JAVA_LONG` | `long` |
| `ValueLayout.JAVA_DOUBLE` | `double` |
| `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| `ValueLayout.ADDRESS` | `MemorySegment` |
| `GroupLayout` / `SequenceLayout` | `MemorySegment` |
| `ofVoid` without return layout | `void` |

Example:

~~~java
// Java 22+, excerpt.
FunctionDescriptor add = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
System.out.println(add.toMethodType());       // (int,int)int

FunctionDescriptor set = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);
System.out.println(set.toMethodType());       // (MemorySegment,int)void
~~~

A `MethodHandle` has `type()`, which is Java metadata about parameters/return. `invokeExact` requires an **exact match** of the type, including Java primitive width, return context, and argument count. Some errors only appear at invocation time:

~~~java
// Assume addHandle is a MethodHandle of type (int,int)int:
int ok = (int) addHandle.invokeExact(1, 2);     // Valid.
long bad = (long) addHandle.invokeExact(1, 2);  // WrongMethodTypeException.
~~~

`invoke` can perform conversions according to some MethodHandle rules, but it **does not fix a wrong ABI descriptor**. Do not replace `invokeExact` with `invoke` as a way to fix a type error without checking the C function prototype.

### 7.1. Bound versus unbound `downcallHandle`

In FFM JDK 22, you can create:

~~~java
// Java 22+, excerpt; symbol and descriptor are created elsewhere.
MethodHandle bound =
        linker.downcallHandle(symbol, descriptor);

MethodHandle unbound =
        linker.downcallHandle(descriptor);
~~~

- `bound` already has the C function address attached, so the handle is called with the function's arguments (plus any special ABI auxiliary arguments when present).
- `unbound` does not have an address attached yet; the Java method handle needs an extra **`MemorySegment` argument for the native function address**.
- For functions returning a struct by value, the linker may add a `SegmentAllocator` to hold the return value; check **`handle.type()`** instead of assuming it always equals `descriptor.toMethodType()`.
- The `symbol` result from `SymbolLookup.find(...)` is a `MemorySegment` representing a function address, not a byte buffer to read/write arbitrarily.

For the runnable examples in section 9, `bound` is used to focus on how to choose `of` and `ofVoid`; there are no other hidden ABI arguments because the return types are `int`, `double`, or `void`.

## 8. Standalone runnable example 1 — describing signatures, no C call

The program **`DescriptorOnly22.java`** uses only the FFM API to create descriptors and inspect `returnLayout`, `argumentLayouts`, and `toMethodType`. It runs with **JDK 22+** without needing a C library or granting restricted native access permission.

Create the file:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

public final class DescriptorOnly22 {
    public static void main(String[] args) {

        FunctionDescriptor add = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT);

        FunctionDescriptor store = FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT);

        FunctionDescriptor reset = FunctionDescriptor.ofVoid();

        FunctionDescriptor strlen = FunctionDescriptor.of(
                ValueLayout.JAVA_LONG,
                ValueLayout.ADDRESS);

        System.out.println(
                "add.hasReturn=" + add.returnLayout().isPresent());
        System.out.println(
                "store.hasReturn=" + store.returnLayout().isPresent());
        System.out.println(
                "add.arguments=" + add.argumentLayouts().size());
        System.out.println(
                "store.arguments=" + store.argumentLayouts().size());

        System.out.println(
                "add.type=" + add.toMethodType());
        System.out.println(
                "store.type=" + store.toMethodType());
        System.out.println(
                "reset.type=" + reset.toMethodType());
        System.out.println(
                "strlen.type=" + strlen.toMethodType());
    }
}
~~~

Run:

~~~bash
javac DescriptorOnly22.java
java DescriptorOnly22
~~~

Exact stdout:

~~~text
add.hasReturn=true
store.hasReturn=false
add.arguments=2
store.arguments=2
add.type=(int,int)int
store.type=(MemorySegment,int)void
reset.type=()void
strlen.type=(MemorySegment)long
~~~

Explanation:

1. `add` uses `of`, so it has a return layout. The first layout is not counted in `argumentLayouts().size()`.
2. `store` uses `ofVoid`, so `returnLayout().isPresent()` is `false` even though it has two arguments.
3. `reset` has no C parameters and returns no value.
4. `strlen` describes the example `size_t strlen(const char*)` **on Linux x86-64**; `JAVA_LONG` is only a mapping suitable for the stated target, not representative of every ABI.
5. The string `(MemorySegment,int)void` means Java calls a handle that takes a `MemorySegment` for a C pointer and an `int` for a C int, with no return value.
6. There is no `Linker.downcallHandle` in this program, so no native symbol is called and no native access permission is requested.

If you print `FunctionDescriptor.toString()`, the textual representation of the object may not be stable output that you should check with string comparison. For tests, `returnLayout`, `argumentLayouts`, and `toMethodType` are clearer.

## 9. Standalone runnable example 2 — C library and Java FFM calling real `of` / `ofVoid`

This section is an end-to-end example on **Linux x86-64** with a **C11 compiler (`cc`/GCC/Clang)** and **JDK 22+**.

Objectives:

- C provides `int32_t add_i32(int32_t,int32_t)` — return value; uses `FunctionDescriptor.of`.
- C provides `void store_i32(int32_t*,int32_t)` — no return; uses `FunctionDescriptor.ofVoid`.
- C provides `double multiply_f64(double,double)` — demonstrates the `double` carrier.
- Java loads `libffmdescriptors.so`, looks up symbols with `SymbolLookup.libraryLookup`/`find`, creates bound downcall handles, calls `invokeExact`, and reads the result from native memory.
- The program also prints the types of the handles so learners see that **the descriptor determines the callsite**.

Working directory:

~~~text
ffm-descriptor-demo/
  native_math.c
  FfmDescriptorsDemo.java
~~~

### 9.1. C code: `native_math.c`

~~~c
#include <stdint.h>

/* On Linux x86-64, int32_t uses the 32-bit int ABI. */
int32_t add_i32(int32_t left, int32_t right) {
    return left + right;
}

/* C returns void: the observable effect is writing to the pointer area. */
void store_i32(int32_t *destination, int32_t value) {
    if (destination != 0) {
        *destination = value;
    }
}

double multiply_f64(double left, double right) {
    return left * right;
}
~~~

The C code uses two `int32_t` arguments both within a small range, so the addition in the example **does not overflow signed int32_t**. `store_i32` does not allocate, does not return a pointer, and does not retain `destination` after returning. Java must allocate a valid memory region for one `int32_t`, keep that memory alive throughout the native call, and then read the data after the call finishes.

In a real library, a C API may specify that null is invalid rather than silently ignoring it; this example uses a null check for illustration, **not as a default recommendation for every API**.

### 9.2. Java code: `FfmDescriptorsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmDescriptorsDemo {
    public static void main(String[] args) throws Throwable {

        Linker linker = Linker.nativeLinker();

        FunctionDescriptor addSignature =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor storeSignature =
                FunctionDescriptor.ofVoid(
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor multiplySignature =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_DOUBLE,
                        ValueLayout.JAVA_DOUBLE,
                        ValueLayout.JAVA_DOUBLE);

        try (Arena arena = Arena.ofConfined()) {
            Path libraryPath =
                    Path.of("libffmdescriptors.so").toAbsolutePath();

            SymbolLookup library =
                    SymbolLookup.libraryLookup(libraryPath, arena);

            MethodHandle add = linker.downcallHandle(
                    library.find("add_i32").orElseThrow(),
                    addSignature);

            MethodHandle store = linker.downcallHandle(
                    library.find("store_i32").orElseThrow(),
                    storeSignature);

            MethodHandle multiply = linker.downcallHandle(
                    library.find("multiply_f64").orElseThrow(),
                    multiplySignature);

            System.out.println("add.type=" + add.type());
            System.out.println("store.type=" + store.type());
            System.out.println("multiply.type=" + multiply.type());

            int sum = (int) add.invokeExact(17, 25);

            MemorySegment cell = arena.allocate(
                    ValueLayout.JAVA_INT);
            store.invokeExact(cell, 91);

            int stored = cell.get(ValueLayout.JAVA_INT, 0);

            double product =
                    (double) multiply.invokeExact(1.5d, 2.0d);

            System.out.println("sum=" + sum);
            System.out.println("stored=" + stored);
            System.out.println("product=" + product);
        }
    }
}
~~~

Step-by-step explanation:

1. `Linker.nativeLinker()` gets the native linker for the ABI the JVM is running on.
2. The three descriptors describe the **exact return type and exact order of C arguments**. There is no step to pass a `MethodType` manually.
3. `Arena.ofConfined()` allows loading the library/holding the symbol lookup and allocating temporary buffers within a closeable scope.
4. `SymbolLookup.libraryLookup(Path, arena)` is the way to get symbols from a custom library by path, unlike `Linker.defaultLookup()`, which is usually used for system libraries.
5. `library.find("add_i32").orElseThrow()` returns a native function address as a `MemorySegment`; if the symbol is not exported, it fails explicitly.
6. `downcallHandle(symbol, descriptor)` creates a **bound handle**; each handle needs the exact number and types of Java arguments according to the descriptor.
7. `add.invokeExact(17,25)` returns `int` because the C function returns `int32_t` on the stated ABI. The `(int)` cast in Java is required for the `invokeExact` callsite.
8. `store.invokeExact(cell,91)` is a statement-style call with a **`void` return type**. There is no C return value to assign. Instead, C writes the number 91 into the `cell` memory region.
9. `cell.get(ValueLayout.JAVA_INT,0)` reads the result through the output pointer written by C.
10. `multiply.invokeExact(1.5d,2.0d)` takes two `double`s and returns a `double`; the `d` suffix is optional but makes the type explicit.
11. At the end of `try`, the arena closes; do not reuse the `cell` pointer or the library's symbols beyond the defined lifetime.

### 9.3. Build the library and run the program

In the directory containing the two files, execute:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -o libffmdescriptors.so native_math.c

javac FfmDescriptorsDemo.java

java --enable-native-access=ALL-UNNAMED \
  FfmDescriptorsDemo
~~~

The commands above do not need to generate a JNI header and do not call `javac -h` because this is an **FFM downcall**, with no Java `native` methods bound by JNI.

**Expected stdout on Linux x86-64 when the library is built and loaded successfully:**

~~~text
add.type=(int,int)int
store.type=(MemorySegment,int)void
multiply.type=(double,double)double
sum=42
stored=91
product=3.0
~~~

Why this is reliable:

- `17 + 25 = 42` with C `int32_t`; no overflow.
- `store_i32` writes 91 into a valid `int32_t*` region; Java reads back the same bytes via `JAVA_INT`.
- `1.5 × 2.0 = 3.0` in `double`; Java `Double.toString` prints `3.0` for this value.
- `MethodHandle.type()` represents the Java carrier type of a **bound** native function handle; because the C returns are not group layouts, there is no extra `SegmentAllocator` argument.
- `store.type` ends with `void`, matching `FunctionDescriptor.ofVoid`.

If the program reports that the library cannot be found, check the **working directory**, whether `libffmdescriptors.so` exists, whether the architectures of the C compiler and JVM match, and DLL dependencies. If it reports `IllegalCallerException`/native access warnings, check the flag/module for the right JDK; **do not change the descriptor** just to work around permission errors.

## 10. Why `ofVoid` is not “doing nothing”

A C function returning `void` can still:

- Write to an output pointer: `void store_i32(int32_t *dest, int32_t value)`.
- Modify native context state: `void reset(Context*)`.
- Send data to a device, file, or network.
- Accept a callback pointer and register a long-running task.
- Produce side effects not visible through a return value.

An FFM descriptor only expresses the **return value according to the ABI**, not side effects or ownership contracts.

Example:

~~~c
/* Illustrative C signature. */
void copy_bytes(void *dest, const void *src, size_t count);
~~~

Java description on Linux x64:

~~~java
// Java 22+; descriptor declaration only, not a standalone program.
FunctionDescriptor copy = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,   // dest
        ValueLayout.ADDRESS,   // src
        ValueLayout.JAVA_LONG);// size_t Linux x64
~~~

To call safely, you must ensure `dest`/`src` point to live memory regions of at least `count` bytes, do not violate the real API's overlap rules, and the C function has the right semantics. `ofVoid` does not prove that the output region is large enough.

If the C function returns `int error_code` instead of `void`, you must use `of(JAVA_INT,...)` even if **application logic treats the result only as an error code**. Do not arbitrarily change it to `ofVoid` because you do not want to read the return: the ABI still has an actual return value.

## 11. How to declare `void f(void)`, parameterless functions, and pointer returns

Three commonly confused cases:

~~~c
int get_version(void);
void reset(void);
void *create_context(void);
~~~

Descriptions:

~~~java
// Java 22+, excerpt.
FunctionDescriptor getVersion =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);

FunctionDescriptor reset =
        FunctionDescriptor.ofVoid();

FunctionDescriptor createContext =
        FunctionDescriptor.of(ValueLayout.ADDRESS);
~~~

Do not manually add a `ValueLayout.ADDRESS` for the `void` parameter in `f(void)`. In C, the keyword `void` used alone in a prototype `f(void)` represents **no parameters**, not a pointer.

Conversely:

~~~c
void dispose_context(void *context);
~~~

must use `ofVoid(ValueLayout.ADDRESS)` — the function has **one pointer argument** and **no return**.

### 11.1. A returned pointer must have ownership rules

If calling `create_context()` returns a `MemorySegment` pointer:

- It may return `MemorySegment.NULL`, which must be checked.
- A memory segment describing an address does not automatically create a Java object that owns the native struct.
- If C allocates the context, there is usually a corresponding `dispose_context(context)` function. Java must call the right native method when done, rather than using `Arena.close()` to free a region created by C that does not belong to the arena.
- Do not read directly from a zero-length address segment without knowing its bounds, lifetime, and the required restricted APIs.
- To let a callback or secondary thread keep the pointer after the Java invocation, thread safety, lifetime, and cleanup must be clear.

**Summary:** `FunctionDescriptor.of(ADDRESS)` only says “the native return is a pointer”. It does not say how many bytes the memory region is or how it is freed.

## 12. Combining descriptors with `Linker` and `SymbolLookup`

The complete call path:

~~~text
C header: return_type fn(arg1_type, arg2_type);
     |
     +--> Determine ABI, widths, pointer/struct, ownership
               |
               +--> FunctionDescriptor.of(...) / ofVoid(...)
                             |
         Native library --> SymbolLookup.find("fn")
                             |
                             +--> MemorySegment: function address
                             |
                Linker.downcallHandle(symbol, descriptor)
                             |
                     Java MethodHandle
                             |
              invokeExact(...) with matching carrier types
                             |
                    Native C function runs
~~~

You can create the descriptor **before** loading the native library, because it does not depend on the specific address of the function. You can reuse one descriptor for multiple symbols that have the **same signature**, provided the ABI matches.

Example:

~~~java
// Java 22+ excerpt, assuming linker and symbolA/symbolB are valid.
FunctionDescriptor unaryInt = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

MethodHandle a = linker.downcallHandle(symbolA, unaryInt);
MethodHandle b = linker.downcallHandle(symbolB, unaryInt);
~~~

However, **having the same number of parameters and return is not enough** to confirm two C functions are compatible; you must consider the actual type/ABI prototypes, including signedness, floating point, varargs, aggregate returns, and callback pointers.

### 12.1. `SymbolLookup.find` is not a C signature check

`find("name")` usually only knows the **symbol name**, returning `Optional<MemorySegment>`, without knowing whether it is `int(int,int)` or `void(int*)`. Some native binaries have symbol tables/debug info, but the FFM linker does not reliably infer C prototypes from them automatically.

The signature must be taken from the **library's header/public API**, not guessed from the function name. A name like `read_value` does not tell you whether the C return is `int`, `long`, a pointer, or `void`.

### 12.2. Loading libraries: default, loader, and library lookup

| Lookup | Symbol source | When to use |
| --- | --- | --- |
| `Linker.nativeLinker().defaultLookup()` | Common system libraries exposed by the native linker | `strlen`, `malloc` if the symbol exists on the platform |
| `SymbolLookup.loaderLookup()` | Libraries loaded via `System.load/System.loadLibrary` associated with the caller class loader | When the same class loader owns a JNI-loaded library |
| `SymbolLookup.libraryLookup(Path/String, Arena)` | A specific library, loaded/looked up with lifetime tied to an arena | When the application actively calls a custom C library via FFM |

Do not assume `defaultLookup()` always contains symbols in custom libraries or that the `strlen` symbol is identical across all OSes. And do not confuse a **filename** such as `libffmdescriptors.so` with a **logical library name** passed to `System.loadLibrary`.

## 13. Descriptors and MethodHandles for struct-returning functions: auxiliary parameters

For scalar returns such as `int` or `double`, a **bound** downcall handle has a `type()` that matches `descriptor.toMethodType()` in simple examples.

For group returns such as:

~~~c
/* Illustrative C declaration. */
struct Pair { int first; int second; };
struct Pair make_pair(int x, int y);
~~~

the descriptor can be:

~~~java
// Java 22+, illustrates layout after verifying C ABI.
MemoryLayout PAIR = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("first"),
        ValueLayout.JAVA_INT.withName("second"));

FunctionDescriptor makePair = FunctionDescriptor.of(
        PAIR, ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
~~~

`makePair.toMethodType()` expresses `(int,int)MemorySegment` according to carrier rules. **However**, when `Linker` creates a downcall handle for a C function returning a struct by value, the handle needs an **additional `SegmentAllocator`** to know where to store the result. Therefore, `handle.type()` can be a longer Java signature than `descriptor.toMethodType()`.

Based on Java SE 22 `Linker`, do not forget the parameter added by the linker. When working with aggregate-by-value, you should:

1. Measure the exact `sizeof/alignof/offsetof` of the C struct with the target C compiler.
2. Construct the exact group layout, including any necessary padding.
3. Verify that the target linker supports that layout.
4. Print `handle.type()`, then create the `invokeExact` callsite with the exact arguments, including `SegmentAllocator`.
5. Ensure the result storage remains alive and is used on the proper thread/lifetime of the arena.

**Do not treat `FunctionDescriptor.toMethodType()` as complete proof for special ABI handles.** For unbound downcalls, there is also the C function address.

## 14. Describing variadic C functions: `of` is not enough without a linker option

A function such as:

~~~c
int printf(const char *format, ...);
~~~

takes one fixed parameter, the format string, followed by a variable number of arguments. FFM does not “know” how many C values the format string will lead to. You must create a descriptor for **a specialized callsite** and mark the variadic boundary.

Conceptual example (JDK 22+, Linux x64):

~~~java
// Illustrative; not a standalone program:
// "printf(\"%d + %d\", 2, 3)" has 1 fixed and 2 variadic args.
FunctionDescriptor printfDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,     // return int
        ValueLayout.ADDRESS,      // fixed: const char* format
        ValueLayout.JAVA_INT,     // variadic: first int
        ValueLayout.JAVA_INT);    // variadic: second int

MethodHandle printf = linker.downcallHandle(
        printfSymbol,
        printfDescriptor,
        Linker.Option.firstVariadicArg(1));
~~~

`firstVariadicArg(1)` means the parameter at **index 1 of the C argument list** (zero-based) is the first variadic argument; `format` has index 0. It **does not** count the return layout.

C variadic calls apply **default argument promotions**: for example, `float` is usually promoted to `double`, and integer types smaller than `int` can be promoted to `int`. The native linker may reject unpromoted variadic layouts. If varargs are misdescribed, the native call can fail even if the Java arguments have the right numeric types.

Do not call a variadic C function simply with a descriptor of only the fixed arguments and expect the system to send extra varargs automatically. `FunctionDescriptor` must reflect the **specific callsite**, `Linker.Option` must reflect the **variadic start position**, and the ABI must be checked.

## 15. Modifying/inserting argument layouts immutably

`FunctionDescriptor` is immutable/value-based. Besides the two main factories, JDK 22 provides:

| Method | Effect |
| --- | --- |
| `appendArgumentLayouts(extra...)` | Returns a new descriptor with appended arguments |
| `insertArgumentLayouts(index, extra...)` | Returns a new descriptor with arguments inserted at index, 0-based |
| `changeReturnLayout(newLayout)` | Returns a new descriptor with the return layout replaced/set |
| `dropReturnLayout()` | Returns a new descriptor with no return layout |
| `argumentLayouts()` | Reads an unmodifiable list of argument layouts |
| `returnLayout()` | Reads the optional return layout |
| `toMethodType()` | Converts layouts to a Java method type via carrier rules |

Java 22+ example:

~~~java
// Illustrative excerpt.
FunctionDescriptor unary = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

FunctionDescriptor binary =
        unary.appendArgumentLayouts(ValueLayout.JAVA_INT);

FunctionDescriptor binaryVoid =
        binary.dropReturnLayout();
~~~

Check:

~~~text
unary.toMethodType()      -> (int)int
binary.toMethodType()     -> (int,int)int
binaryVoid.toMethodType() -> (int,int)void
~~~

`unary` is unchanged after calling `appendArgumentLayouts`. `dropReturnLayout` does not “turn” a C function with a return into a void C function in the native library; it only **creates a different signature description**. If you use the new descriptor to link the same old symbol with a different prototype, the result may be wrong.

`insertArgumentLayouts` can throw `IllegalArgumentException` when the index is invalid; all argument-adding methods reject **a standalone padding layout**. Do not use `changeReturnLayout`/`dropReturnLayout` as a way to bypass an ABI mismatch.

## 16. Debugging common errors when describing FunctionDescriptor

| Symptom | Possible design error | Check/fix |
| --- | --- | --- |
| `WrongMethodTypeException` on `invokeExact` | Wrong number of Java arguments, primitive type, or return cast | Print `handle.type()` and compare with the Java callsite |
| `IllegalArgumentException` when creating descriptor | Passed `paddingLayout` as argument/return layout | Padding belongs only in group layouts, not as a standalone C argument |
| `IllegalArgumentException` on `downcallHandle` | Layout not supported by linker, invalid option | Check the ABI and layout types |
| `IllegalCallerException` / native-access warning | Module not granted permission for restricted FFM calls | Use `--enable-native-access` for the right module/JDK |
| `NoSuchElementException` at `find(...).orElseThrow()` | Symbol not exported/not in that library lookup | Check symbol name, visibility, library name, and lookup |
| `UnsatisfiedLinkError` or library load error | Native file not found/missing dependency/wrong architecture | Check path, ABI, file permissions, dependencies |
| Java receives abnormal numbers from a `long`-returning function | C `long` has a different width from Java long on the ABI | Use `canonicalLayouts()` for the C target |
| C function has no return but Java reads a value | Confused `ofVoid` with `of` | Read the C prototype; if return is `void`, use `ofVoid` |
| C function returns a pointer but descriptor is `ofVoid` | Confused `void*` with `void` | Pointer return uses `of(ADDRESS)` |
| C takes a pointer but Java passes primitive `int` | Used `JAVA_INT` instead of `ADDRESS` | C `int*` requires a pointer, a valid Java `MemorySegment` |
| Java calls native and process crashes | Descriptor mismatches ABI, invalid memory, wrong lifetime | Check header, calling convention, pointers, memory bounds |
| Data from C struct has shifted fields | Wrong padding, alignment, by-value/by-pointer | Measure `sizeof`/`alignof`/`offsetof` with a C probe |
| Java only checked `descriptor.toMethodType` but handle type differs | Unbound symbol argument or struct return allocator | Print the actual `handle.type()` |
| C varargs code returns wrong values | Did not declare specialized signature, did not use `firstVariadicArg` | Describe the exact callsite and default argument promotions |
| Confused `System.loadLibrary` with `libraryLookup` | Two different loading/lookup mechanisms | Determine class-loader lookup vs library-scoped lookup |
| Code describes `size_t` as `int` on Linux x64 | 64-bit return width truncated | Use canonical `size_t` mapping and check ABI |

### 16.1. Dangerous misconception: “If Java compiles, the descriptor is right”

Not true. C symbols usually do not provide C type metadata for `Linker` to verify automatically. Knowing only an address does not allow inferring the function type that the address points to. Many mismatches only surface when the function is called, potentially causing **memory corruption/crash** instead of a Java exception.

Bad example:

~~~c
/* Actual C: two parameters, returns double. */
double compute(double x, double y);
~~~

~~~java
// Wrong ABI! Java code creating the descriptor still compiles.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

If you use that descriptor to call `compute`, the call may pass arguments in the wrong registers and read the return from the wrong registers. **Do not run** an intentionally wrong ABI test on an important system; fix the descriptor according to the C header and test in an isolated development environment.

### 16.2. `invokeExact` vs `invoke`

`MethodHandle.invokeExact` checks the signature at the Java callsite:

~~~java
// Assume add is a MethodHandle of type (int,int)int.
int value = (int) add.invokeExact(3, 4);
~~~

If the `value` variable is changed to `long` or `3L` is passed without changing the handle, `WrongMethodTypeException` can occur. `invoke` may allow some Java method handle conversions, but **does not** turn an `int*` into valid memory or replace `C long` with the right ABI type.

When debugging, print `handle.type()`, `descriptor.returnLayout()`, `descriptor.argumentLayouts()`, and compare against the real C declaration.

## 17. Native function callbacks / upcalls use descriptors with the same C rules

`FunctionDescriptor` is not only for Java → C downcalls. For a Java callback converted into a function pointer for C, `Linker.upcallStub(targetHandle, descriptor, arena)` also needs a descriptor that **matches the C callback signature**.

C callback example:

~~~c
/* Illustrates C type only, not a standalone program. */
typedef void (*on_value)(int value);
~~~

Java description:

~~~java
// Java 22+, excerpt:
FunctionDescriptor callbackSignature =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);
~~~

This is a callback returning `void` and taking one `int`. The target Java `MethodHandle` needs a compatible method type `(int)void`. The stub is allocated within the lifetime of an `Arena`; do not let native code call the function pointer after the arena has closed.

**Unlike downcalls:** an unhandled Java exception escaping an upcall callback can have severe consequences, up to JVM termination. The callback must handle errors appropriately inside, without assuming Java exceptions will automatically turn into C error codes. In addition, thread attachment, callback reentrancy, owner/lifetime, and synchronization of the native context must be clear.

The `of`/`ofVoid` rules are completely the same: **returning void** uses `ofVoid`; **returning int** uses `of(JAVA_INT,...)`; **returning pointer** uses `of(ADDRESS,...)`.

## 18. Safe workflow for choosing a descriptor for any C function

### Step 1 — obtain the exact C prototype

Example:

~~~c
// Real ABI header, illustrative example:
int32_t process(const uint8_t *bytes, size_t length, uint32_t flags);
~~~

Identify how many parameters there are, the return type, pointer vs by-value aggregate, `const`, packing, varargs, and calling convention. Do not guess from the method name or similar Python/C#/Java data bindings.

### Step 2 — choose the right ABI and canonical types

On Linux x64 usually:

- `int32_t` corresponds to 32-bit `int` → `ValueLayout.JAVA_INT`.
- `const uint8_t *` is a pointer → `ValueLayout.ADDRESS`.
- `size_t` is usually 64-bit → `ValueLayout.JAVA_LONG`.
- `uint32_t` is 32-bit unsigned → `ValueLayout.JAVA_INT` at the carrier level, converting unsigned values when needed.

On other ABIs, query `Linker.nativeLinker().canonicalLayouts()` or compile a C probe instead of copying the Linux table.

### Step 3 — decide between `of` and `ofVoid`

It returns `int32_t`, so use `of`:

~~~java
// Java 22+, description for Linux x64:
FunctionDescriptor process = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,     // C return int32_t
        ValueLayout.ADDRESS,      // const uint8_t *
        ValueLayout.JAVA_LONG,    // size_t
        ValueLayout.JAVA_INT);    // uint32_t
~~~

If the C header changes to `void process(...)`, the new descriptor must be `ofVoid(ADDRESS,JAVA_LONG,JAVA_INT)`. Do not switch just because Java does not care about the return code.

### Step 4 — check the Java carrier/MethodHandle type

For the `process` descriptor:

~~~text
(MemorySegment,long,int)int
~~~

If using a bound downcall handle for this C function, the Java callsite must pass a live `MemorySegment` pointer, a `long` length, and `int` flags. When you only have a heap `byte[]`, you need to prepare memory compatible with the native pointer contract (usually native allocation) and ensure the memory is not freed before C finishes using it.

### Step 5 — check lifetimes and out-parameters

For pointer arguments, determine **input/output**, whether `NULL` is valid, size/endianness, ownership of the memory region, and whether native code retains the pointer after returning. With `ofVoid`, many results reside in out-parameters, so this step is especially important.

### Step 6 — create the linker handle and run two-sided tests

- Which compiler/ABI was the library built with?
- Did `SymbolLookup` find the right symbol?
- Did `Linker.downcallHandle` accept the layouts?
- Does `handle.type()` match the Java callsite?
- Did a C test call the function with known inputs/expected outputs?
- Does the Java downcall return the right output, including boundary values, null/zero-length, and errors?
- Have you tested the platforms/architectures you actually support?

Do not start with benchmarks or optimizing `invokeExact` until correctness and safety have been proven.

## 19. Pre-merge review checklist

- [ ] Read the **actual C header** instead of guessing the signature from the symbol name?
- [ ] Recorded the exact **target JDK** (JDK 22+ final) and native ABI?
- [ ] Functions with a return value use `FunctionDescriptor.of(return, args...)`?
- [ ] Functions returning `void` use `FunctionDescriptor.ofVoid(args...)`?
- [ ] `void f(void)` is described with **0 arguments**, not `ADDRESS`?
- [ ] `void*` is described as pointer `ADDRESS`, not confused with `void`?
- [ ] `of` is not missing an argument due to miscounting the return layout as an argument?
- [ ] C `char*`/`int*`/`struct T*` use `ADDRESS`, not the pointee layout as by-value?
- [ ] C struct/union **by value** uses an exact group layout according to `sizeof/alignof/offsetof`?
- [ ] C `long`, `size_t`, `bool`, and unsigned types are mapped according to the ABI?
- [ ] `ValueLayout` and `FunctionDescriptor` do not use a padding layout as a standalone C parameter?
- [ ] `returnLayout` and `argumentLayouts` accurately reflect the C prototype?
- [ ] `descriptor.toMethodType()` is checked, and `handle.type()` is checked if there are linker-added params?
- [ ] `invokeExact` uses the exact Java primitive types, arity, and return context?
- [ ] Downcall `Linker`/`SymbolLookup` is granted proper native access?
- [ ] Native library is loaded properly and the symbol is actually exported?
- [ ] Variadic C functions have `firstVariadicArg` at the right index and proper promotions?
- [ ] Native buffers are large enough, properly aligned, and alive while C uses them?
- [ ] Out-parameters of `ofVoid` are allocated by Java and read back as specified?
- [ ] C function does not retain pointers to buffers after the arena closes?
- [ ] Tested normal inputs, boundaries, null/error codes, and ABI differences on every platform committed to supporting?

## 20. Self-check questions

1. What is the first parameter of `FunctionDescriptor.of(return, args...)`? Is it counted as a C function argument?
2. Why must `void reset(void)` use `ofVoid()` rather than `ofVoid(ADDRESS)`?
3. Does `void *create(void)` need `of` or `ofVoid`, and why?
4. What descriptor does the C signature `int add(int,int)` map to on Linux x64?
5. What descriptor does the C signature `void write(int*,int)` map to, and how does Java observe the output?
6. What Java carrier type does `ValueLayout.ADDRESS` have? Why not pass a Java `String` directly for `char*`?
7. Does `FunctionDescriptor.toMethodType()` always equal `boundHandle.type()`? Give one exception.
8. Why does `SymbolLookup.find("function")` not prove that the C signature is compatible with the descriptor?
9. Why should C `long` not be mapped to `JAVA_LONG` for every OS/ABI?
10. How does describing a C struct **by value** differ from a pointer to a struct?
11. What extra option is needed besides a specialized descriptor when describing `printf(const char*, ...)`?
12. Why can `FunctionDescriptor.ofVoid` still produce side effects and out-parameters?
13. Can `MemoryLayout.paddingLayout(8)` be inserted directly as an `ofVoid` argument?
14. When `invokeExact` reports `WrongMethodTypeException`, what is the first step that helps debug?
15. Does `appendArgumentLayouts` mutate the original descriptor?
16. If a C function returns a pointer to a new native allocation, is the caller's `Arena.close()` guaranteed to free that allocation?
17. What descriptor does a Java method handle callback for C `void (*on_event)(int)` need?
18. Should you trust that a descriptor is correct just because the Java compiler and linker successfully create a handle?

**Summary answers:** (1) return layout, not counted in the argument list; (2) C `(void)` means no arguments; (3) `of(ADDRESS)` because it returns a pointer; (4) `of(JAVA_INT,JAVA_INT,JAVA_INT)`; (5) `ofVoid(ADDRESS,JAVA_INT)`, read the native memory that the `out` pointer points to; (6) `MemorySegment`, requires a native-compatible buffer and lifetime; (7) no, unbound symbol argument or allocator for struct return; (8) symbol lookup only finds the address; (9) Windows x64 typically uses 32-bit C long; (10) by-value uses `StructLayout`, pointer uses `ADDRESS`; (11) `Linker.Option.firstVariadicArg(index)`; (12) C still has side effects; (13) no, throws `IllegalArgumentException`; (14) print `handle.type()` and compare C signature/descriptor/callsite; (15) no, returns a new descriptor; (16) no, must call the appropriate native disposer; (17) `ofVoid(JAVA_INT)`; (18) no, must verify against the C header and ABI/native tests.

## 21. Official documentation

- [Oracle JDK 22 — `FunctionDescriptor`: `of`, `ofVoid`, `returnLayout`, `toMethodType`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle JDK 22 — `Linker`: native ABI, `downcallHandle`, variadic options, canonical layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `SymbolLookup`: `find`, `libraryLookup`, `loaderLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `ValueLayout`: primitive carriers and `ADDRESS`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle JDK 22 — `MemoryLayout`: group/sequence/padding](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle JDK 22 — `MemorySegment`: pointer, bounds, lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle JDK 22 — `Arena`: memory allocation and deallocation](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [Oracle JDK 22 — Restricted Methods and Native Access](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html)

**Conclusion:** `FunctionDescriptor.of` is for C functions **with a return value**; the first argument is the return layout, followed by the layouts of the C parameters. `FunctionDescriptor.ofVoid` is for C functions **returning `void`**, and only accepts arguments. Choosing the right factory is only the first step: for safe FFM, you must also **map types according to the real C ABI**, distinguish pointers from by-value structs, check `MethodHandle.type()`, grant proper native access, and ensure valid pointers/lifetimes. A descriptor can compile and still misdescribe a C function; always verify against the C header and native tests.
