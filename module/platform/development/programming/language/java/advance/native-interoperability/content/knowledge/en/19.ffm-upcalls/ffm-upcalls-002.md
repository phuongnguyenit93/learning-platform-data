# Preparing a MethodHandle for a Java Method as a Callback Using FFM

**Goal:** when a C/C++ function takes a **function pointer (callback)** argument, Java can provide a Java method as the implementation for that callback using the Foreign Function & Memory API (FFM). The most important step is preparing a `java.lang.invoke.MethodHandle` with the **exact number, order, and types of parameters as well as the return type** that the native callback function's ABI expects. From this `MethodHandle`, `Linker.upcallStub` creates a callback address that can be passed into C.

The complete conversion chain:

```text
Java method (static or instance)
       |
       | MethodHandles.lookup().findStatic / findVirtual
       v
Original Java MethodHandle
       |
       | bindTo / insertArguments / asType if needed
       v
Target MethodHandle with MethodType matching the callback ABI
       |
       | FunctionDescriptor.of(...) + Linker.upcallStub(handle, desc, arena)
       v
MemorySegment representing function pointer / upcall stub
       |
       | Passed via downcallHandle(...), layout ADDRESS
       v
C calls callback(int a, int b)
       |
       v
FFM converts C arguments -> Java method handle -> C return value
```

**Two boundaries must be separated:** `MethodHandle` is how the JVM represents an accurately typed callable target; it is **not a C function pointer**. `upcallStub` is what creates the ABI/native pointer bridge. A `MethodHandle` with the right Java type but paired with the **wrong C ABI**, or a stub whose lifetime has expired, can still lead to a JVM crash. Preparing the handle therefore includes **signature**, **target receiver**, **lifetime**, **thread**, and **error contract**.

> **JDK:** FFM `java.lang.foreign` was finalized in **JDK 22 (JEP 454)**. This article uses **Java 22+** and Linux x86-64 for the full runnable example. Java 17 has an incubator FFM with a different API; Java 19–21 have preview APIs. Because `Linker.upcallStub`, `downcallHandle`, and `SymbolLookup.libraryLookup` are restricted APIs, the example runs with `--enable-native-access=ALL-UNNAMED` when code is on the classpath. Only perform FFM with trusted native libraries and verified ABIs.

## 1. Callbacks in native code need a clearly described C contract

Consider a simple C API:

```c
typedef int (*int_binary_callback)(int left, int right);

int call_binary(int left, int right,
                int_binary_callback callback);
```

This is an **illustrative signature snippet**, not a standalone implementation. `callback` is a pointer to a function with the C signature:

```c
int callback(int left, int right);
```

On Linux x86-64 (System V ABI), C `int` is signed 32-bit; FFM uses `ValueLayout.JAVA_INT` as the corresponding layout. The callback takes two `int`s and returns an `int`. Therefore, the desired Java target must have the form:

```java
static int javaCallback(int left, int right) {
    return left + right;
}
```

And if Java wants to use an instance method, FFM still requires the handle **after binding the receiver** to have a final callable shape equivalent to `(int, int) -> int`.

### Mapping table for this callback

| C ABI | FFM `FunctionDescriptor` | Java carrier in `MethodHandle` |
| --- | --- | --- |
| `int left` | `ValueLayout.JAVA_INT` | `int` |
| `int right` | `ValueLayout.JAVA_INT` | `int` |
| Returns `int` | Return layout `ValueLayout.JAVA_INT` | `int` |
| Callback address `int (*)(int,int)` when passed to C | `ValueLayout.ADDRESS` in the descriptor **of the C function receiving the callback** | `MemorySegment` in the downcall handle |

An easy-to-miss point is that there are **two different FunctionDescriptors**:

- **Callback descriptor**: describes the function that **C will call**: `(int,int) -> int`.
- **Native caller descriptor**: describes the C function **receiving the callback pointer**: `(int,int,address) -> int`.

Do not put `ADDRESS` into the callback descriptor just because in Java you pass a `MemorySegment` containing the callback address. `ADDRESS` belongs at the callback parameter of the **outer C function**.

## 2. `MethodType` and `FunctionDescriptor`: two sides of the same contract

In Java:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodType;

FunctionDescriptor callbackDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, // C return int
        ValueLayout.JAVA_INT, // C left int
        ValueLayout.JAVA_INT  // C right int
);

MethodType required = MethodType.methodType(
        int.class, int.class, int.class);

System.out.println(callbackDesc.toMethodType().equals(required));
// true
```

The snippet above is **illustrated inside a Java method** with JDK 22+. `FunctionDescriptor.of(returnLayout, argumentLayouts...)` places the return layout **first** in the Java API. `MethodType.methodType(returnType, parameterTypes...)` also places the return type first. `callbackDesc.toMethodType()` gives the Java type FFM expects for this callback as:

```text
(int,int)int
```

Both **arity** and **carrier types** must be checked. Common mismatches:

| Java target result | Issue |
| --- | --- |
| `(int,int)int` | Matches C `int (*)(int,int)` on the chosen ABI |
| `(long,long)long` | Does not match because 64-bit Java `long` differs from 32-bit C `int` |
| `(Integer,Integer)Integer` | Boxed references, not native scalar carrier `int` |
| `(int)int` | Missing one argument |
| `(int,int)void` | Wrong return type |
| `(MemorySegment,MemorySegment)int` | Only valid when the C callback actually takes pointer arguments and the descriptor uses `ADDRESS` |
| `(int,int,int)int` | Has an extra Java argument not yet bound/dropped; cannot be passed directly into a two-parameter stub |

`Linker.upcallStub` checks that the `MethodHandle` has a type compatible with the type derived from `FunctionDescriptor`; some mismatches cause `IllegalArgumentException` immediately when creating the stub. However, **FFM cannot fully infer the real signature of a C symbol** from its address alone. An incorrect ABI description can still crash even if the Java code compiles.

**ABI note:** Linux x64 C `int` matches `JAVA_INT` in the example, but types such as C `long`, `size_t`, pointers, struct-by-value, and variadics have different conventions depending on OS/CPU. For portable code, look up `Linker.nativeLinker().canonicalLayouts()` and C headers instead of assuming C `long` always matches Java `long`. Some callbacks also require calling conventions/layout structures supported by the linker/ABI.

## 3. Obtaining a `MethodHandle` for a `static` Java method using `findStatic`

The simplest approach is to prepare a Java static method whose signature matches the callback:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

final class DemoTargets {
    static int safeAdd(int left, int right) {
        try {
            return Math.addExact(left, right);
        } catch (Throwable unexpected) {
            return Integer.MIN_VALUE; // Error value defined by the contract.
        }
    }
}

/* Illustrative snippet running in a method with access to DemoTargets. */
MethodHandle handle = MethodHandles.lookup().findStatic(
        DemoTargets.class,
        "safeAdd",
        MethodType.methodType(int.class, int.class, int.class)
);
```

Here `findStatic` searches for the method by **class, exact name, and MethodType**. If the name, parameters, or return type do not exist, the lookup fails with `NoSuchMethodException`; if the lookup does not have access permission, it can fail with `IllegalAccessException`.

- `MethodHandles.lookup()` carries the access privileges of the class performing the lookup. `private` methods are only accessible when appropriate permissions exist (e.g., lookup within the same class/nestmate).
- `MethodHandles.publicLookup()` is generally only suitable for truly public methods/public members; do not use it as a trick to bypass module access.
- `MethodHandles.privateLookupIn` may be needed when sufficient access permissions exist under Java module/access rules; it is not a shortcut to bypass security.
- The exact signature in `MethodType` is not a JNI descriptor like `(II)I`, even though both express type information.

**Do not create a lookup with `MethodType.methodType(void.class,...)` if the C callback returns `int`.** Java may accept a void method, but an FFM callback descriptor cannot turn a wrong return type into valid native data.

## 4. Java instance methods: handling the receiver with `findVirtual` and `bindTo`

A Java instance method has a `this` receiver variable. A `MethodHandle` from `findVirtual` normally has the **receiver as the first parameter**, even though the Java method signature appears to have only two parameters:

```java
final class OffsetAdder {
    private final int bias;

    OffsetAdder(int bias) {
        this.bias = bias;
    }

    int add(int left, int right) {
        return left + right + bias;
    }
}

// Illustrative code in a class with access to OffsetAdder.
MethodHandle virtual = MethodHandles.lookup().findVirtual(
        OffsetAdder.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class)
);
// virtual.type(): (OffsetAdder,int,int)int

OffsetAdder receiver = new OffsetAdder(10);
MethodHandle bound = virtual.bindTo(receiver);
// bound.type(): (int,int)int
```

**The `bindTo(receiver)` step is critical.** The C callback only passes `left` and `right`. It **does not know** what the Java receiver `this` is. If you pass an unbound `virtual` into `upcallStub` with a two-`int` descriptor, the types do not match.

`bindTo` fixes the receiver inside the MethodHandle. The Java callback can access that object's state through its method. This state requires thread-safety if C invokes the callback from multiple native threads. If the instance is an `AutoCloseable` resource, do not close the receiver before native code makes its final callback.

The bound `MethodHandle` can hold a reference to the receiver. However, **do not assume** the C function pointer has an infinite lifetime just because the Java object is still alive: the upcall stub address is still tied to the `Arena` passed into `Linker.upcallStub`. Both lifecycles must be managed simultaneously.

## 5. Fixing configuration parameters with `MethodHandles.insertArguments`

A Java method may have a configuration parameter that the C callback does not know about, for example:

```java
static int addWithBias(int bias, int left, int right) {
    return left + right + bias;
}
```

The original MethodHandle is `(int,int,int)int`. Use:

```java
MethodHandle raw = MethodHandles.lookup().findStatic(
        MyClass.class,
        "addWithBias",
        MethodType.methodType(
                int.class, int.class, int.class, int.class)
);
MethodHandle boundBias = MethodHandles.insertArguments(raw, 0, 10);
// raw.type():       (int,int,int)int
// boundBias.type(): (int,int)int
```

This is an **illustrative** snippet, where `MyClass` represents the class that declared `addWithBias`; it is not a complete program. `insertArguments(raw, 0, 10)` fixes the first Java parameter (`bias`) to 10. C will only pass the remaining two `int`s.

**Distinguish the three adaptation operations:**

| Technique | When to use? | Before and after |
| --- | --- | --- |
| `findStatic` | Callback is a Java static method | `(int,int)int` |
| `findVirtual` then `bindTo(receiver)` | Callback is an instance method | `(Receiver,int,int)int` → `(int,int)int` |
| `insertArguments` | There is a fixed configuration parameter | `(int,int,int)int` → `(int,int)int` |
| `dropArguments` | C passes an extra argument that the Java target intentionally ignores | For example `(int,int)int` → `(MemorySegment,int,int)int` |
| `asType` | Adjusts Java method types according to conversions supported by MethodHandle | Does not automatically change C ABI or fix a wrong descriptor |

Only use adapters to represent the **actual contract**; do not use `asType` to hide an incorrect mapping between `C int`/`C long`/pointer. `asType` can add Java boxing, casts, or conversions, but it cannot turn an incorrect ABI layout into a valid one.

## 6. Creating an upcall stub from a MethodHandle using `Linker.upcallStub`

Once the target has the right type:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

Linker linker = Linker.nativeLinker();
FunctionDescriptor callbackDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

try (Arena arena = Arena.ofConfined()) {
    // 'target' has been created/bound and has type (int,int)int.
    MemorySegment callbackPointer =
            linker.upcallStub(target, callbackDesc, arena);
    // Pass callbackPointer into C while the arena is still open.
}
```

This is an **illustrative Java pattern**; `target` must be provided in the calling code, and it is not yet a standalone runnable class. The result `callbackPointer` is a `MemorySegment` containing the **upcall stub address**. It has a **size of 0 bytes** by contract (it is a function pointer, not a character array/data buffer to read).

Lifecycle:

- `upcallStub` creates a native callable bridge and associates it with the arena.
- When `Arena.ofConfined()` is closed successfully, the stub is freed; **C must not call that pointer afterward**.
- `Arena.ofConfined()` enforces owner-thread confinement: the demo only calls C synchronously on the same thread that created the arena.
- If C will call the callback from another native thread or after the Java method returns, do not use a short-lived confined arena and hope everything remains valid; you need `Arena.ofShared()`/coordinated lifetime and callback thread-safety.
- `Arena.ofAuto()` has a GC-managed lifetime with non-deterministic timing; do **not** rely on it as a mechanism to guarantee a raw C function pointer stays alive long-term without explicit Java owner references.
- A callback stub is not an automatically converted Java `Runnable`/`Function`; C must invoke it according to the **C function pointer ABI**.

**Important note:** The `upcallStub` API is restricted. Failing to grant proper native access may result in `IllegalCallerException`. On the classpath, run with `--enable-native-access=ALL-UNNAMED`; with a named module, grant access to the appropriate module. Do not ignore warnings from newer JDKs about restricted/native operations.

## 7. Complete practice exercise: Java 22+ calls C, C calls back into Java

The example uses a small C shared library with two functions:

- `call_binary` invokes the Java callback **once** with two integers.
- `call_twice` invokes the Java callback **twice** to demonstrate that a stub can be reused repeatedly **within its valid lifetime**.

Java prepares three MethodHandles:
1. `findStatic` for `sum`.
2. `findStatic` + `insertArguments` for `sumWithBias` with bias 10.
3. `findVirtual` + `bindTo` for `OffsetAdder.apply` with bias 20.

All three prepared handles have `(int,int)int`, matching the callback descriptor. The C library **does not retain** the function pointer after returning, so `Arena.ofConfined()` and synchronous downcalls are appropriate.

### File `ffm_handle_callbacks.c`

```c
#include <limits.h> /* INT_MIN */
#include <stddef.h> /* NULL */

/* On Linux x86-64, C int matches FFM JAVA_INT (32-bit). */
typedef int (*binary_callback)(int left, int right);

/*
 * Contract:
 * - callback is only BORROWED while call_binary is running.
 * - C does not retain the pointer for asynchronous calls.
 * - INT_MIN is reserved as the error code for this demo.
 */
int call_binary(int left, int right, binary_callback callback) {
    if (callback == NULL) {
        return INT_MIN;
    }
    return callback(left, right);
}

/* Calls the same callback twice while the stub is alive. */
int call_twice(int left, int right, binary_callback callback) {
    if (callback == NULL) {
        return INT_MIN;
    }
    int first = callback(left, right);
    if (first == INT_MIN) {
        return INT_MIN;  /* Do not call the second time if the first reported an error. */
    }
    return callback(first, 1);
}
```

With a Linux/x64 compiler, the two symbols `call_binary` and `call_twice` are exported from the shared library. If `-fvisibility=hidden` is used in a production build, appropriate export attributes must be added; the demo command uses the default, so none are needed.

### File `FfmHandleCallbackDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class FfmHandleCallbackDemo {
    // By the demo contract, successful data never has this value.
    private static final int ERROR = Integer.MIN_VALUE;

    private static int safeSum(int left, int right, int bias) {
        try {
            return Math.addExact(Math.addExact(left, right), bias);
        } catch (Throwable failure) {
            // NEVER let a Throwable escape across the upcall boundary.
            return ERROR;
        }
    }

    private static int sum(int left, int right) {
        return safeSum(left, right, 0);
    }

    private static int sumWithBias(
            int bias, int left, int right) {
        return safeSum(left, right, bias);
    }

    public static final class OffsetAdder {
        private final int bias;

        public OffsetAdder(int bias) {
            this.bias = bias;
        }

        public int apply(int left, int right) {
            return safeSum(left, right, bias);
        }
    }

    private static MemorySegment stub(
            Linker linker,
            Arena arena,
            MethodHandle target,
            FunctionDescriptor descriptor) {

        if (!target.type().equals(descriptor.toMethodType())) {
            throw new IllegalArgumentException(
                    "Wrong upcall type: " + target.type());
        }
        return linker.upcallStub(target, descriptor, arena);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // C callback: int (*)(int, int)
        FunctionDescriptor callbackDesc = FunctionDescriptor.of(
                JAVA_INT, JAVA_INT, JAVA_INT);

        // C function:
        // int call_binary(int left, int right, callback pointer)
        FunctionDescriptor callerDesc = FunctionDescriptor.of(
                JAVA_INT, JAVA_INT, JAVA_INT, ADDRESS);

        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle staticHandle = lookup.findStatic(
                FfmHandleCallbackDemo.class,
                "sum",
                MethodType.methodType(
                        int.class, int.class, int.class));

        MethodHandle rawWithBias = lookup.findStatic(
                FfmHandleCallbackDemo.class,
                "sumWithBias",
                MethodType.methodType(
                        int.class,
                        int.class, int.class, int.class));

        MethodHandle biasedHandle = MethodHandles.insertArguments(
                rawWithBias, 0, 10);

        MethodHandle virtualHandle = lookup.findVirtual(
                OffsetAdder.class,
                "apply",
                MethodType.methodType(
                        int.class, int.class, int.class));
        MethodHandle instanceHandle =
                virtualHandle.bindTo(new OffsetAdder(20));

        System.out.println(
                "staticType=" + staticHandle.type());
        System.out.println(
                "biasedType=" + biasedHandle.type());
        System.out.println(
                "instanceType=" + instanceHandle.type());

        try (Arena arena = Arena.ofConfined()) {
            // Same arena manages the lifetime of library lookup and stubs.
            SymbolLookup nativeLib = SymbolLookup.libraryLookup(
                    Path.of("./libffmhandlecallbacks.so")
                            .toAbsolutePath(),
                    arena);

            MemorySegment callSymbol = nativeLib.find(
                    "call_binary").orElseThrow();
            MemorySegment twiceSymbol = nativeLib.find(
                    "call_twice").orElseThrow();

            MethodHandle callBinary = linker.downcallHandle(
                    callSymbol, callerDesc);
            MethodHandle callTwice = linker.downcallHandle(
                    twiceSymbol, callerDesc);

            MemorySegment staticStub = stub(
                    linker, arena, staticHandle, callbackDesc);
            MemorySegment biasedStub = stub(
                    linker, arena, biasedHandle, callbackDesc);
            MemorySegment instanceStub = stub(
                    linker, arena, instanceHandle, callbackDesc);

            int staticResult = (int) callBinary.invokeExact(
                    3, 4, staticStub);
            int biasedResult = (int) callBinary.invokeExact(
                    3, 4, biasedStub);
            int instanceResult = (int) callBinary.invokeExact(
                    3, 4, instanceStub);
            int twiceResult = (int) callTwice.invokeExact(
                    3, 4, staticStub);

            // Math.addExact overflows; the callback catches Throwable
            // and returns error code INT_MIN instead of throwing through C.
            int overflowResult = (int) callBinary.invokeExact(
                    Integer.MAX_VALUE, 1, staticStub);

            System.out.println("staticResult=" + staticResult);
            System.out.println("biasedResult=" + biasedResult);
            System.out.println("instanceResult=" + instanceResult);
            System.out.println("twiceResult=" + twiceResult);
            System.out.println("overflow=" + overflowResult);
        }
    }
}
```

### Build/run on Linux x86-64

Place both files in the same directory and ensure `javac`/`java` are from **JDK 22+**. Use a C compiler that provides a shared-library ABI compatible with the JDK process:

```bash
cc -std=c11 -Wall -Wextra -O2 -fPIC -shared \
  -o libffmhandlecallbacks.so ffm_handle_callbacks.c

javac FfmHandleCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmHandleCallbackDemo
```

`-Djava.library.path` is not needed because the example uses `SymbolLookup.libraryLookup(Path, Arena)` with an **absolute path** to `libffmhandlecallbacks.so`, rather than calling `System.loadLibrary`. Loading a native library via `libraryLookup` is restricted, so the `--enable-native-access=ALL-UNNAMED` flag has real effect. On JDK 22, FFM is final, so **`--enable-preview` is not needed**.

This code is intended for Linux x86-64 and 32-bit C `int`. When porting to macOS/Windows or another ABI, you must change the library filename, build command, and verify the C layout/calling convention. Do not assume all platforms support function pointers with the same ABI just because the Java code compiles.

### Expected stdout

```text
staticType=(int,int)int
biasedType=(int,int)int
instanceType=(int,int)int
staticResult=7
biasedResult=17
instanceResult=27
twiceResult=8
overflow=-2147483648
```

Explanation:

- `staticHandle`: `sum(3,4)=7`.
- `biasedHandle`: `sumWithBias(10,3,4)=17`; the `bias` parameter was fixed by `insertArguments` **before** creating the upcall stub.
- `instanceHandle`: `new OffsetAdder(20).apply(3,4)=27`; `bindTo` removed the receiver from the callback parameters that C needs to supply.
- `call_twice`: the static callback first returns 7, then computes `sum(7,1)=8`.
- `overflow`: `Math.addExact(Integer.MAX_VALUE,1)` throws `ArithmeticException` inside the callback; `safeSum` catches `Throwable` and returns `Integer.MIN_VALUE`. C receives this error value as `INT_MIN`.

**Error code limitation:** `Integer.MIN_VALUE` is a reserved sentinel in the **demo's contract**, which is only reasonable if the valid result domain excludes the sentinel. Production APIs must have a clearer error channel (for example, status + output pointer/struct, or a callback returning an error code and writing the result to another pointer). Do not assume every Java error can be converted into a valid integer in every system.

### When are resources freed?

With the same `Arena.ofConfined()`, Java creates the library lookup and three upcall stubs, calls C synchronously inside `try`, and then closes the arena when leaving the block. C **does not retain** the function pointer, so no native user is still calling the stub after `try`. The demo does not create native background threads or asynchronous callbacks. If C kept the pointer and called it after the arena closed, the code could crash. This is the critical difference between a valid example and a real-world callback registration service.

## 8. How does the signature change when the callback receives pointers?

If C declares:

```c
typedef int (*compare_t)(const void *left, const void *right);
```

then `(int,int)int` **is not suitable**. This is a callback that takes two **addresses**, not two direct integers. Correspondingly:

```java
FunctionDescriptor compareDesc = FunctionDescriptor.of(
        JAVA_INT, ADDRESS, ADDRESS);

// The Java target must have MethodType:
// (MemorySegment, MemorySegment) -> int.
```

When FFM passes a C pointer into a Java callback, the carrier is typically `MemorySegment`. A pointer does not inherently carry the length of the target buffer/struct. In many cases an address segment received from C has `byteSize() == 0`. You cannot simply call `segment.get(JAVA_INT,0)` without valid bounds.

If the C contract guarantees that each pointer always points to a single `int`, you can use `ADDRESS.withTargetLayout(JAVA_INT)` in the callback descriptor (supported by the linker) so FFM attaches appropriate bounds to the target segment. However, declaring the target layout must be accurate according to the **actual C ABI, alignment, and lifetime**. Do not use `reinterpret` arbitrarily to bypass bounds and hope the JVM can validate that C pointer.

Below is an illustration of the idea of reading two `int`s from C pointers:

```java
static int compareInts(MemorySegment left, MemorySegment right) {
    try {
        int l = left.get(JAVA_INT, 0);
        int r = right.get(JAVA_INT, 0);
        return Integer.compare(l, r);
    } catch (Throwable failure) {
        return 0;  // Illustrative fallback only, not a standard sort API.
    }
}

FunctionDescriptor compareDesc = FunctionDescriptor.of(
        JAVA_INT,
        ADDRESS.withTargetLayout(JAVA_INT),
        ADDRESS.withTargetLayout(JAVA_INT));
```

This snippet is **illustrative** only and requires appropriate class/method imports; it is not a full runnable example. It is equivalent to Oracle's FFM `qsort` guide: using `withTargetLayout` when you know the pointer points to a C `int`. **Do not** change `ADDRESS` to `JAVA_INT` just because the pointed-to data is an `int`.

## 9. Exception safety: do not let Java exceptions escape the target

This is the **paramount rule** in FFM upcalls.

The JDK 22 `Linker.upcallStub` specification states that the target `MethodHandle` **must not let exceptions escape**. If the target throws an exception and does not catch it, **the JVM may terminate abruptly**, rather than simply hitting a `Java catch` on the downcall caller side. This is unlike normal JNI Java exceptions reported as a thread's pending exception.

Dangerous example:

```java
// DO NOT pass this method directly into upcallStub.
static int unsafeDivide(int a, int b) {
    return a / b; // b == 0 -> ArithmeticException escapes!
}
```

Pattern with a boundary fallback:

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (Throwable unexpected) {
        return Integer.MIN_VALUE; // The native API must understand this code.
    }
}
```

These are two illustrative snippets, not full Java classes. Catching `Throwable` right at the boundary is used to **prevent any throwable from escaping through the callback function pointer**; swallowing critical errors should be weighed carefully in production designs. Do not perform complex JNI/FFM operations or heavy allocations in the fallback branch when the JVM is low on memory; using a predefined error code is more reliable than throwing another Java exception.

### Separating business errors from the callback ABI

In real systems, there should be a clear C contract:

```c
/* Example C contract that needs explicit implementation, not a complete demo:
 * 0 = success; non-zero = error.
 * out_value is only written on success.
 */
typedef int (*callback_with_status)(
        int left, int right, int *out_value);
```

Then the Java target has the form `(int,int,MemorySegment)int` matching the callback descriptor `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT, ADDRESS...)` (requiring a target layout and valid bounds for `out_value`). Java code can catch exceptions and return an error status, instead of trying to cram every value and error into a single `int`.

**Do not use `MethodHandles.catchException` half-heartedly.** This combinator is useful if the handler is declared with the right type, but the handler itself must also not let exceptions escape; the author still needs to understand carrier and error code mapping. A Java wrapper method with an explicit `try/catch(Throwable)` is usually easier to review for callbacks.

## 10. Callback pointer and Arena lifetimes are part of MethodHandle preparation

`MethodHandle` and upcall stubs have different lifecycles:

| What? | Java or native? | When does it become invalid? |
| --- | --- | --- |
| Target `MethodHandle` | Java object with method type/target | By Java reachability, but has no directly callable C address |
| Receiver bound via `bindTo` | Java object that the handle may hold | By reference/ownership of the related Java objects |
| `MemorySegment` from `upcallStub` | Native function pointer, tied to an arena | When the arena scope is closed/invalidated |
| `SymbolLookup.libraryLookup` / native symbol | C function address belonging to the library lookup | Depends on native library/arena lifetime per contract |
| C pointer kept in a registry | Raw native address | **Not automatically recognized as a Java reference by GC**; must have an explicit lifetime policy |

**Typical mistake:** creating a stub inside `try (Arena a = Arena.ofConfined())`, registering the function pointer with C, exiting `try`, and letting C invoke the callback the next night. The Java `MethodHandle` object may still be alive, but the native upcall stub has been deallocated. C calling the old address can cause a crash.

### Synchronous callback

If C only calls the callback **within a single downcall** and does not retain the function pointer, a confined arena and `try-with-resources` is usually the simplest solution. Close the arena **after the downcall returns**.

### Asynchronous/native-stored callback

If C keeps the callback in a registry/worker thread to call later:

1. The C API must separate `register(callback)`, `unregister(callback)`, and waiting for all currently running callbacks to finish.
2. Java uses an arena with an appropriate lifecycle, usually `Arena.ofShared()` if the callback will be called from multiple native threads.
3. Java keeps a live owner object for callback registrations, related method handle/receiver/buffers, and the arena.
4. Before closing, **unregister**, block new callbacks, and then **wait** for in-flight callbacks to finish.
5. Do not unload the C library while active callbacks or stubs still exist; do not let C dereference closed Java/FFM buffers.
6. Coordinate error handling, Java object state, and synchronization separately.

`Arena.ofAuto()` can also be used in some FFM demos, but it **does not** guarantee that a raw function pointer held long-term by C will keep the Java arena reachable. A C pointer does not automatically become a Java GC root. For long-lived callbacks, explicit lifetime and an unregister protocol are usually easier to prove correct.

### Can the callback be called from any thread?

A distinction must be made:

- `Arena.ofConfined()` is only suitable for defined thread-confined access. Do not pass a stub with a confined lifetime to arbitrary native worker threads and trust that FFM will automatically turn it into a shared callback.
- `Arena.ofShared()` supports lifetime and thread accessibility better suited for multi-threaded callbacks, but it **does not** automatically synchronize Java receiver state.
- If the C callback can run concurrently, a pure function like `sum` has no shared mutable state so it is simple; an `OffsetAdder` with mutable fields may need locks/atomics.
- Do not let the callback block for too long if C holds a native mutex or calls the callback inside a critical section; check for deadlock/reentrancy risks.

**Do not call `arena.close()` to "immediately cancel" an executing callback.** Closing an arena does not replace blocking new calls and waiting for native work to complete. Lifetime bugs at the FFM boundary can affect the entire process.

## 11. Callbacks with an extra `void *userData`: combining MethodHandle with context

Many C libraries pass an extra context pointer:

```c
typedef int (*callback_with_ctx)(
        void *user_data, int left, int right);

int schedule_or_invoke(
        callback_with_ctx cb, void *user_data);
```

You must verify that C actually calls the callback with **three** parameters in the order `user_data, left, right`. The target MethodHandle can accept `(MemorySegment,int,int)int`.

If Java **does not need** to use the C context, you can adapt an `(int,int)int` target using `dropArguments`:

```java
// 'bound' is a MethodHandle (int,int)int
MethodHandle ignoresContext = MethodHandles.dropArguments(
        bound, 0, MemorySegment.class);
// ignoresContext.type(): (MemorySegment,int,int)int

FunctionDescriptor descriptorWithContext = FunctionDescriptor.of(
        JAVA_INT, ADDRESS, JAVA_INT, JAVA_INT);
```

This is an illustrative snippet, requiring `bound` and relevant imports to be available. `dropArguments` adds a parameter to the type, which the target ignores at runtime. Do **not** use this if the C contract requires actually processing the context or receiving external state via `void *`.

If the context is fixed Java state, instead of passing a raw Java object reference through `void*`, it is usually more convenient to use `bindTo` with a Java receiver; the method handle attaches the Java state to the stub. When a C API strictly requires `void *userData` to distinguish multiple registrations, design an ID/opaque native context and independent lifetime, avoiding arbitrarily converting a `jobject`/Java reference into a raw C pointer.

If a C callback has arguments like `const char *` or `struct *`, the Java carrier must be `MemorySegment`; you need to know **encoding, byte length, alignment, ownership, and lifetime**. Do not infer from `ADDRESS` alone that a pointer holds a NUL-terminated string or a sufficiently long buffer.

## 12. Comparison with JNI callbacks

There are two different concepts of "native calling back into Java":

### JNI reverse call

C has `JNIEnv *`, a Java class/object, and a `jmethodID`, then calls:

```c
/* JNI pseudocode: env, receiver, methodID are valid. */
jint result = (*env)->CallIntMethod(
        env, receiver, methodID, (jint)3, (jint)4);
```

This is an **illustrative snippet**, not standalone. The JNI route uses VM metadata and `JNIEnv*`, and Java exceptions are represented via a **pending exception**; C checks `ExceptionCheck`/handles it according to contract.

### FFM upcall

C only sees a C function pointer like `int (*cb)(int,int)`:

```c
int result = callback(3, 4);
```

The FFM route uses `MethodHandle` + `FunctionDescriptor` + `Linker.upcallStub` to generate a native callable pointer. C does not need `JNIEnv*` at this call site.

| Characteristic | JNI Java method call | FFM upcall |
| --- | --- | --- |
| Java target | `jobject/jclass` + `jmethodID` | Java `MethodHandle`, can `bindTo` receiver |
| Called by C via | `Call<Type>Method` / `CallStatic<Type>Method` | C function pointer per ABI |
| Java signature | JNI descriptor `(II)I` and method kind | `MethodType` + FFM `FunctionDescriptor` |
| Bridge | JNI VM call interface | `Linker.upcallStub` |
| Error | JNI pending Java exception | **Do not let exceptions escape the upcall target**; JVM may terminate |
| Lifetime | JNI references/thread attach and JVM | Upcall stub `Arena`, native pointer, and target state |
| Does external C API need a pointer? | Does not automatically create a C function pointer | FFM is suitable when the C API requires a callback pointer |

Do not use the terms "JNI callback" and "FFM upcall" interchangeably when diagnosing exception handling; each mechanism has its own contract. For a C library with an existing callback pointer interface, FFM can reduce the need to write JNI glue just to translate between a function pointer and a Java method.

## 13. Common errors when preparing a MethodHandle

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `NoSuchMethodException` at `findStatic` | Method name/signature does not exist, static/instance mix-up | Check return/parameter types and use the right find method |
| `IllegalAccessException` | `Lookup` lacks permission to access the method/class | Place lookup code in the right class/module, use valid access |
| `WrongMethodTypeException` on `invokeExact` | Return/argument carriers at call site do not match handle exactly | Check `handle.type()` and cast/args properly |
| `IllegalArgumentException` at `upcallStub` | `MethodHandle` type is incompatible with descriptor | Compare `target.type()` with `descriptor.toMethodType()` |
| Extra `Receiver` in target type | `findVirtual` without `bindTo` | `virtual.bindTo(receiver)` |
| Target type `(int,int,int)int` but callback takes two `int`s | Java config arg not yet fixed | `insertArguments` with the right index and type |
| C crashes when calling callback pointer | Wrong C ABI/descriptor, stale stub, C calling wrong function pointer type | Cross-check C header, C layouts, arena lifetime, and native call sites |
| JVM terminates when callback throws a Java exception | Exception escaped the upcall `MethodHandle` | Wrap target with `try/catch(Throwable)` and a clear error code |
| `IllegalCallerException` when creating stub/library lookup | Native access not enabled for module | `--enable-native-access=ALL-UNNAMED` or the corresponding module |
| `UnsatisfiedLinkError` / symbol not found | Wrong file/library/symbol export | Check absolute Path, `nm -D`, C compiler flags |
| `WrongThreadException` at FFM call | Arena/segment unsuitable for thread | Choose confined/shared per contract, control threads |
| Crash after Java method returns | C retained stub pointer from a closed arena | Synchronous-only or proper owner/unregister/await |
| Callback reads wrong bytes from `ADDRESS` | Pointer lacks clear bounds/encoding | Use proper target layout, length, and C ownership |
| Java callback uses shared mutable state incorrectly | C calls callback concurrently, Java object lacks locks | Synchronization, immutable state, or atomic operations |
| Callback overhead worse than expected | Too many bridge crossings and conversions | Benchmark real C+Java; batch if the API allows |

Do not use `catch (Throwable t)` in Java **outside `downcall.invokeExact`** thinking it will handle a Java exception that escaped an upcall. The rule is to **catch inside the target or a properly configured handler method handle**, before execution returns to C.

## 14. Pre-implementation review process

A design checklist you can tick off:

1. **JDK and API:** Java 22+ finalized FFM; build/runtime on the same API version. Native access flag for the right module.
2. **C header:** callback typedef verified from actual C source/header, not guessing arity/types.
3. **ABI:** C `int`, `long`, pointers, structures, and calling convention mapped accurately to FFM layouts on the target OS/CPU.
4. **Callback descriptor:** `FunctionDescriptor` describes **the callback itself**, not the C function containing the callback parameter.
5. **Downcall descriptor:** has `ADDRESS` at the C parameter receiving the function pointer, with other parameters in the right order.
6. **Target:** Java `static`/instance method exists, `Lookup` has sufficient access, and `MethodType` is correct.
7. **Receiver:** if `findVirtual`, `bindTo` a still-valid receiver; if config param, `insertArguments` at the right position.
8. **Type verification:** `target.type().equals(callbackDesc.toMethodType())` after adapters.
9. **Exceptions:** target does not let exceptions escape; error return/status/secondary channel is clearly declared.
10. **Stub lifetime:** `MemorySegment` from `upcallStub` outlives **all** native callback calls, but is not held indefinitely without reason.
11. **Thread:** arena matches callback thread/confinement, Java receiver state is synchronized when needed.
12. **Does C retain the pointer?:** if yes, must have explicit `unregister` + in-flight callback drain before close/unload.
13. **Pointer arguments:** `ADDRESS` data pointers have clear bounds/alignment/encoding/lifetime; do not misapply `reinterpret`.
14. **Java callback state:** avoid shared mutable state or use locks/atomics; do not hold native locks that cause deadlock across callbacks.
15. **Failure paths:** library lookup/upcall creation/downcall errors do not leak arenas; `try-with-resources` closes closeable arenas.
16. **Tests:** happy path, bound receiver/config, callback called multiple times, overflow/error sentinel, concurrent calls, teardown, and ABI mismatch are tested in an isolated environment.

### Deliberate testing suggestions

- Start with a two-`int` C callback like the demo, without struct pointers, to reduce ABI variables.
- Print `MethodHandle.type()` before creating the stub; it must be `(int,int)int`.
- Call C with `(3,4)` and verify 7/17/27 when using the three target types.
- Use `Math.addExact` in the callback and test overflow to confirm the exception is handled **inside the callback**, not allowed to escape.
- Only after the synchronous case is right should you design async registration/teardown and test with native worker threads.
- Use `nm -D --defined-only libffmhandlecallbacks.so` (Linux) to inspect symbols when `libraryLookup.find` fails; on other systems use the corresponding symbol tool.
- When a crash occurs, save `hs_err_pid*.log` and the C stack trace; check descriptor/calling convention/lifetime first.

Do not put an incorrect callback ABI into a production program to "see what exception it throws." ABI issues can cause memory corruption or abort before any Java exception is ever created.

## 15. Self-check questions

**Question 1.** Why can't you pass a Java `MethodHandle` directly into a C `int (*callback)(int,int)` argument?

Because `MethodHandle` is a Java object/VM callable handle, **not a native code address** under the C ABI. `Linker.upcallStub` is needed to generate a `MemorySegment` representing the function pointer.

**Question 2.** What MethodHandle type does `findVirtual` for `int add(int,int)` return before binding the receiver?

`(Receiver,int,int)int`. C only supplies two `int`s, so `bindTo(receiver)` or an equivalent adapter is needed so the final target is `(int,int)int`.

**Question 3.** Can `MethodHandles.insertArguments` be used to fix a `bias` parameter?

Yes. With `sumWithBias(int bias,int left,int right)`, `insertArguments(raw,0,10)` turns the `(int,int,int)int` handle into `(int,int)int` compatible with the callback.

**Question 4.** Why is the callback descriptor `FunctionDescriptor.of(JAVA_INT,JAVA_INT,JAVA_INT)` while the C downcall descriptor adds `ADDRESS`?

Because the first descriptor is the **callback signature** taking two `int`s and returning `int`. The second descriptor describes the **C function receiving the callback pointer** as its third parameter, so it has `ADDRESS`.

**Question 5.** If a Java callback throws `ArithmeticException` across an upcall, will C receive a standard JNI error code?

No. The FFM specification requires the target **not to throw** across an upcall; the JVM may terminate abruptly. You must catch inside the callback/handler handle and define a C error channel.

**Question 6.** Can a stub created from `Arena.ofConfined()` be retained by C and called after the arena is closed?

No. Closing the arena invalidates the stub; calling a stale pointer is a severe native error. Design the callback as synchronous-only or use a registration owner with a clear lifecycle.

**Question 7.** A Java method takes `int left,int right` but the C callback actually takes `const int*`. Can you use the descriptor `JAVA_INT,JAVA_INT` just because the pointed-to values are also `int`?

No. C takes **pointers**, so the appropriate FFM carrier is `MemorySegment` via `ADDRESS`. Bounds, target layout, and ownership must be handled separately.

**Question 8.** Why might `findStatic` fail even though the Java method exists?

The name/return/parameter MethodType may not match, or `MethodHandles.Lookup` may lack access. An instance method cannot be obtained using `findStatic`.

**Question 9.** Does valid Java `(int,int)int` code guarantee that a C callback works properly on every OS?

No. `MethodType` only describes the Java-side types. The C ABI, calling convention, `long`/`size_t` sizes, structures, symbol exports, and native access policy must still be right.

**Question 10.** If you need to pass Java object state to a C callback, what is simpler than casting `jobject` to `void*`?

When the callback target is an instance method, use `findVirtual` then `bindTo(receiver)`; the method handle already captures the Java receiver. If the C API also has a mandatory `void* userData`, it can be handled via a `MemorySegment` context and a clear contract, without arbitrarily casting Java references.

**Question 11.** What can `MethodHandles.dropArguments` help with?

If a C callback has an extra argument that the Java target does not need, the adapter creates a handle that accepts that argument but ignores it. The callback descriptor must still reflect the **actual C signature**; ignoring it is a handling decision of the Java target.

**Question 12.** Why is `Arena.ofShared()` not enough by itself to guarantee multi-threaded callback safety?

A shared arena provides lifetime/access suitable for multiple threads, but it does not automatically synchronize Java receiver state, does not block native calls after unregister, and does not resolve data races/deadlocks. A coordinator and proper Java synchronization are needed.

## 16. Official documentation

- Oracle Java SE 22 — [`Linker`: upcall stubs, MethodHandle type, FunctionDescriptor, lifetime, upcall exceptions, and safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- Oracle Java SE 22 — [`FunctionDescriptor` and `toMethodType()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html).
- Oracle Java SE 22 — [`SymbolLookup`: native library lookup, arena lifetime, restricted method](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- Oracle Java SE 22 — [`Arena`: confined/shared arenas and close](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [`MethodHandles`: findStatic, findVirtual, insertArguments, dropArguments, catchException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- Oracle Java SE 22 — [`MethodHandle` and `invokeExact`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- Dev.java — [How to Handle a Call from Native Code Back to Java Code](https://dev.java/learn/api/io/ffm/upcall/).
- OpenJDK — [JEP 454: FFM finalized in JDK 22](https://openjdk.org/jeps/454).

**Remember:** prepare an FFM callback along the chain **Java method → MethodHandle → bind/adapt to match MethodType → C ABI-compatible FunctionDescriptor → Linker.upcallStub in a valid Arena → pass function pointer to C**. Normally C does not know the Java receiver, so `bindTo` is needed; do not let Java exceptions escape the upcall; manage the stub's lifetime and thread like a native resource. Having the right Java signature is **necessary**, but **not sufficient** if the ABI, ownership, or callback teardown is wrong.