# Callbacks, Function Pointers, and the Upcall Concept in Java FFM

## Learning Objectives

When Java calls a C library using the **Foreign Function & Memory API (FFM)**, the familiar direction is from Java to native: a **downcall**. However, many C APIs expect to receive a **function pointer** so they can later call back into the application's code, such as a `qsort` comparator, an event listener, or a callback reporting task completion. When native code calls back into Java logic, that process is called an **upcall**.

FFM allows turning a **Java `MethodHandle`** into a **native function pointer** via `Linker.upcallStub`. This is not a cast of a Java object to a machine address, but rather the JVM generating an **upcall stub** that can be called by C according to the declared ABI.

After this lesson, you will be able to:

- Distinguish between a callback, a C function pointer, a downcall, an upcall, and an upcall stub.
- Read a C prototype with a parameter `int (*comparator)(const void *, const void *)`.
- Properly combine `MethodHandle`, `FunctionDescriptor`, `Linker`, `Arena`, and `ValueLayout.ADDRESS`.
- Create/pass a function pointer to native code and explain the lifetime of an upcall stub.
- Run a Java example calling C `qsort`, in which C calls back into a comparator written in Java.
- Identify errors involving ABI, signature, callback exceptions, pointer bounds, races, asynchronous callback registration, shutdown, and ownership.

**Version:** the examples use the official `java.lang.foreign` **API from JDK 22+** (JEP 454), tested with **JDK 24**. **JDK 17** has the FFM incubator with a different package and API, so this example will not run verbatim on it. `upcallStub` is a restricted method and requires **native-access permission**.

## 1. What are callbacks and function pointers in C?

In C, a function can take a pointer to another function as a parameter. A classic example is the `qsort` function in the standard C library:

~~~c
#include <stdlib.h>

void qsort(void *base,
           size_t nmemb,
           size_t size,
           int (*compar)(const void *a, const void *b));
~~~

This is a **prototype**, not a redefinition of the `qsort` function in the program. `qsort` takes a region of elements to sort, the number of elements, the size of each element, and a **comparator function pointer**.

Analyzing each parameter:

| C Parameter | Role |
| --- | --- |
| `void *base` | Starting address of the region containing the elements |
| `size_t nmemb` | Number of elements in the array |
| `size_t size` | Size of **each element** in bytes |
| `int (*compar)(const void *, const void *)` | An **address of a function** that can take two pointers and return an `int` |

When `qsort` performs sorting, it calls the `compar` function pointer to determine the order of the elements. According to the `qsort` contract, the comparator must return a **negative** number if the first element is less than the second, **0** if they are equal, and a **positive** number if greater. It does not need to return exactly -1, 0, 1; only the sign of the result matters.

A comparator written in C typically looks like:

~~~c
#include <stdint.h>
#include <string.h>

int compare_i32(const void *a, const void *b) {
    int32_t left;
    int32_t right;
    memcpy(&left, a, sizeof left);
    memcpy(&right, b, sizeof right);

    return (left > right) - (left < right);
}
~~~

The snippet above is a **C function snippet**, illustrating a typical callback. `memcpy` helps read the two values without relying on a cast that could cause alignment violations; the example assumes the elements are `int32_t` according to the defined format. Do not use `return left - right;` without handling integer overflow.

If Java wants to pass its own comparator to `qsort`, C **does not understand** a Java `Comparator<Integer>` or `java.lang.invoke.MethodHandle`. C requires an **ABI-compliant function pointer**. Therefore, an upcall stub bridge is needed.

## 2. Three call directions: downcall, upcall, and callback registration

~~~text
Java application                  Native C library
----------------                  ----------------
Java main
    |
    | downcall: qsort(array, n, size, callbackPointer)
    +---------------------------------------------->
                                                   qsort
                                                     |
                                                     | calls function pointer
                                                     v
                                        [FFM-generated upcall stub]
                                                     |
    <------------------------------------------------+
    |
Java static compare(leftSegment, rightSegment)
    |
    | returns int (negative / zero / positive)
    +---------------------------------------------->
                                                   qsort continues
    <----------------------------------------------+
    |
Java receives the sorted array result
~~~

- **Downcall:** Java calls a C function. FFM uses `Linker.downcallHandle` and `MethodHandle` to perform this.
- **Upcall:** Native C calls back into a **Java method handle** via a function pointer address created with `Linker.upcallStub`.
- **Callback:** A general concept: a function passed/registered for another party to call at an appropriate time. In the example, the callback logic resides in Java.
- **Synchronous callback:** Native calls the callback during the downcall itself and completes before the downcall returns, such as the typical `qsort` example.
- **Asynchronous/retained callback:** C stores the function pointer in a registry and calls it **after** the registration call has finished; this requires separate lifetime, unregistration, and concurrency design.

An upcall is not a mechanism that uses `JNIEnv *` to run a Java method in handwritten JNI code. The FFM linker performs the translation between the C ABI and the Java method handle. If the system also uses JNI, you must distinguish the two mechanisms and not pass `JNIEnv *` pointers across threads arbitrarily.

## 3. A function pointer is not the address of a Java method on the heap

A native function pointer is an **ABI-callable code address**; it is not a `jobject`, not a `Class` address, and not a pointer to a `MethodHandle` Java object. The JVM is responsible for generating thunks/stubs and converting arguments/return values.

In Java FFM:

~~~java
Linker linker = Linker.nativeLinker();

MemorySegment functionPointer =
        linker.upcallStub(targetHandle, callbackDescriptor, arena);
~~~

This is an **illustrative snippet**; the three variables `targetHandle`, `callbackDescriptor`, and `arena` must be created beforehand; it is not a standalone runnable Java file.

Meaning:

1. `targetHandle` is Java logic that can be invoked via a `MethodHandle`.
2. `callbackDescriptor` defines the **C signature** and the layout of the parameters/return value.
3. `linker` knows the ABI of the current OS/CPU.
4. `arena` manages the lifetime of the function pointer stub.
5. `functionPointer` is a **`MemorySegment` with a non-zero address and `byteSize() == 0`** pointing to the stub. This is a **function pointer**, not a data region for reading/writing bytes.

Therefore, never treat a function pointer like the memory of an `int` or a byte array. **Do not** call `functionPointer.get(JAVA_INT,0)` and do not manually `free` the stub's address; only pass it to a C API that actually expects a function pointer, while the stub is still alive.

## 4. Five FFM components involved in an upcall

| Component | Typical Usage | Important Contract |
| --- | --- | --- |
| `Linker.nativeLinker()` | Obtain the linker supporting the current ABI | Not an arbitrary linker for another OS's ABI |
| `MethodHandles.lookup().findStatic(...)` | Create a method handle to the Java callback | Type must match the Java signature derived from the descriptor |
| `FunctionDescriptor` | Describe return/argument layouts of the C callback | Correct parameter count, order, types, and ABI |
| `Linker.upcallStub(target, desc, arena)` | Create a function pointer that calls back into Java | Restricted, requires native access and a live arena |
| `Arena` | Manage the lifetime of the stub | Must not be closed before C can no longer invoke the callback |

`ValueLayout.ADDRESS` appears in two different places:

- In the **callback descriptor**, `ADDRESS` describes a C parameter of pointer type, for example `const void *a`.
- In the **downcall descriptor**, `ADDRESS` describes a C parameter of **function pointer** type, for example `compar` of `qsort`, because the value passed to C is still an address.

Do not mistakenly assume that `ADDRESS` proves the pointer points to 4 or 8 bytes: **a pointer value does not carry bounds on its own**. When the callback is actually invoked, if the layout is only `ADDRESS`, the `MemorySegment` parameter for the pointer normally has size 0.

## 5. The MethodHandle type must match the FunctionDescriptor

C callback:

~~~c
int compare(const void *left, const void *right);
~~~

A Java method can be chosen as the target:

~~~java
static int compare(MemorySegment left, MemorySegment right) {
    // Read elements, compare, and return negative, 0, or positive.
    return 0;
}
~~~

However, looking at the function name alone is not enough. A descriptor is needed:

~~~java
FunctionDescriptor comparisonDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.ADDRESS
);
~~~

With this descriptor, the JVM derives the method handle type:

~~~text
(MemorySegment, MemorySegment)int
~~~

You can check it with:

~~~java
MethodType methodType = comparisonDescriptor.toMethodType();
~~~

Use `MethodHandles.lookup().findStatic(...)` with `methodType` to create the target handle, or build a matching handle using combinators from `java.lang.invoke`.

If the method handle returns `long` instead of `int`, has an extra `MemorySegment` argument, or swaps the parameter order, `upcallStub` cannot arbitrarily guess or cast it to the C ABI. A target type incompatible with the descriptor can cause stub creation to throw **`IllegalArgumentException`**. In cases where the target signature and descriptor **both look valid in Java but are wrong for the actual C ABI**, native code may crash when calling the function pointer.

### Target layout for callback pointers

In `qsort`, the C comparator receives pointers to individual elements. With a contract that elements are 4-byte C `int`s, Java can declare:

~~~java
FunctionDescriptor comparisonDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);
~~~

`withTargetLayout` makes the two pointer arguments received in Java be `MemorySegment`s with **`byteSize() == 4`**. Without a target layout, the two pointer parameters passed into the upcall are normally **0-byte segments**, and `get(JAVA_INT,0)` will be blocked by bounds checking.

**Warning:** `AddressLayout.withTargetLayout` is a **restricted operation**. It trusts that C will pass a valid pointer to a region with the declared size/alignment; it **does not verify the actual C memory allocation**. With a wrong ABI or invalid pointer, the program may suffer memory corruption or a JVM crash. Only use it when the C API has a specific contract for the pointer arguments.

## 6. ABI specification: do not hardcode `size_t` across all systems

The `qsort` function uses `size_t` for `nmemb` and `size`. On many 64-bit systems, `size_t` can be represented by Java `long`/`JAVA_LONG`; on 32-bit systems it is usually different. **Do not assume C `size_t` is always `long`**.

Since JDK 22, `Linker.canonicalLayouts()` provides layouts of basic C types according to the linker/ABI. You can use:

~~~java
Linker linker = Linker.nativeLinker();
ValueLayout sizeT = (ValueLayout) linker.canonicalLayouts().get("size_t");
MemoryLayout cInt = linker.canonicalLayouts().get("int");
~~~

On the tested Java 24 Windows/x64 environment, `size_t` has carrier `long.class` and C `int` has size 4. This lesson includes a runnable example for common ABIs satisfying those two conditions; the code **checks them itself** before calling native:

~~~java
if (sizeT.carrier() != long.class || cInt.byteSize() != 4) {
    throw new UnsupportedOperationException(
            "Example requires size_t=64-bit and C int=32-bit");
}
~~~

Note that C `int` having size 4 does not necessarily guarantee every exotic ABI is modeled correctly; in the example targeting Linux/x64 and Windows/x64, `ValueLayout.JAVA_INT` is correct. On other ABIs, design the descriptor based on canonical layouts and the corresponding method type, rather than trying to force mismatched types with `invokeExact`.

## 7. Complete example: C `qsort` calling a Java comparator via upcall

This example **does not require writing or compiling C code**: it calls `qsort` already present in the native C runtime that the JVM linker can look up. It still performs a **native downcall and a real upcall**, not merely simulating a Java callback.

Prerequisites to run:

- **JDK 22+**, tested on JDK 24 Windows/x64.
- The native runtime exposes the `qsort` symbol via `linker.defaultLookup()`. Oracle does not guarantee the exact same set of symbols across all OSes; if the symbol is missing, use `SymbolLookup.libraryLookup(...)` on an actual native library or a separate library fixture.
- The platform satisfies 4-byte C `int` and 8-byte Java `long` for C `size_t`; the program checks this condition.
- Run with native-access permission for the unnamed module.

### 7.1. Java source: `CallbackQsortDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class CallbackQsortDemo {
    private static final AtomicInteger calls = new AtomicInteger();
    private static final AtomicReference<Throwable> callbackError =
            new AtomicReference<>();

    private static int compare(MemorySegment left, MemorySegment right) {
        try {
            calls.incrementAndGet();

            int a = left.get(ValueLayout.JAVA_INT, 0);
            int b = right.get(ValueLayout.JAVA_INT, 0);
            return Integer.compare(a, b);
        } catch (Throwable t) {
            // Do not let exceptions cross the native callback boundary.
            callbackError.compareAndSet(null, t);
            return 0; // ABI-valid fallback value; error will be reported after downcall.
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        ValueLayout sizeT = (ValueLayout)
                linker.canonicalLayouts().get("size_t");

        if (sizeT.carrier() != long.class
                || linker.canonicalLayouts().get("int").byteSize() != 4) {
            throw new UnsupportedOperationException(
                    "Example requires size_t=64-bit and C int=32-bit");
        }

        FunctionDescriptor comparatorDesc = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));

        MethodHandle comparator = MethodHandles.lookup().findStatic(
                CallbackQsortDemo.class,
                "compare",
                comparatorDesc.toMethodType());

        FunctionDescriptor qsortDesc = FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS, // base: void*
                sizeT,               // nmemb: size_t
                sizeT,               // size: size_t
                ValueLayout.ADDRESS  // compar: function pointer
        );

        MethodHandle qsort = linker.downcallHandle(
                linker.defaultLookup().find("qsort").orElseThrow(),
                qsortDesc);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment array =
                    arena.allocateFrom(ValueLayout.JAVA_INT, 9, 2, 7, 1, 5);

            MemorySegment comparatorPointer = linker.upcallStub(
                    comparator, comparatorDesc, arena);

            System.out.println("stub-nonnull="
                    + (comparatorPointer.address() != 0L));

            // exact method type: (MemorySegment,long,long,MemorySegment)void
            qsort.invokeExact(array, 5L, 4L, comparatorPointer);

            if (callbackError.get() != null) {
                throw new IllegalStateException(
                        "Java callback failed", callbackError.get());
            }

            System.out.println("callback-called=" + (calls.get() > 0));
            System.out.println("sorted=" +
                    Arrays.toString(array.toArray(ValueLayout.JAVA_INT)));
        }
    }
}
~~~

Save `CallbackQsortDemo.java` in your working directory and run:

~~~bash
javac -encoding UTF-8 CallbackQsortDemo.java
java --enable-native-access=ALL-UNNAMED CallbackQsortDemo
~~~

Stdout on **tested JDK 24 Windows/x64**:

~~~text
stub-nonnull=true
callback-called=true
sorted=[1, 2, 5, 7, 9]
~~~

`callback-called` is computed as a boolean rather than printing the number of times the comparator ran, because `qsort` does not promise a fixed number of comparator calls across C runtimes. The `Comparator` must provide a consistent ordering; the example uses `Integer.compare` to avoid overflow from directly subtracting two integers.

### 7.2. Why does the example genuinely involve an upcall?

The execution path is:

1. Java allocates the int data in **native memory** via `Arena.allocateFrom`.
2. Java creates `MethodHandle comparator` pointing to the static method `compare`.
3. Java creates `comparatorPointer` via `Linker.upcallStub`; this pointer can be called by C.
4. Java uses the `qsort` downcall handle to call the **C runtime** with the newly created function pointer.
5. `qsort` invokes the comparator pointer when comparing elements.
6. The upcall stub converts the two native pointers into 4-byte `MemorySegment`s according to the target layouts, then invokes Java's `compare` method.
7. The Java comparator returns an `int` following the negative/0/positive rule, native `qsort` continues, and writes the sorted result into the array.
8. When `qsort` returns, Java verifies the callback did not report an error, then prints the sorted array.
9. Exiting the try block, `arena.close()` reclaims the array and the stub. No native code retains the pointer after this point.

**Do not** call `comparatorPointer.get(JAVA_BYTE,0)`: this is a function pointer with `byteSize` 0, not a data region that can be dereferenced. **Do not** manually jump to/call a raw numeric address like `comparatorPointer.address()` from Java; the FFM linker manages the ABI boundary.

### 7.3. Why use `Integer.compare` instead of `a - b`?

If `a = Integer.MAX_VALUE` and `b = -1`, the operation `a-b` will overflow 32-bit signed and can produce the wrong sign. `qsort` needs a correct, consistent comparison order. `Integer.compare(a,b)` satisfies that for Java `int` when C `int` corresponds to 32-bit.

### 7.4. When a callback fails

In `compare`, the code catches `Throwable` and stores the first exception in `callbackError`. Returning `0` is a **C `int`-typed fallback code**, not an assertion that sorting succeeded. After `qsort` returns, Java **checks and reports the error**.

This mechanism avoids letting a Java exception cross the C ABI boundary. For async callbacks, there is no waiting downcall to check; a separate error channel is needed (queue, future, controlled logging, or an API-appropriate error callback). If the callback operation cannot safely complete after an error, choose a native API with a **cancellation/status** mechanism rather than continuing to sort unconditionally.

**Important:** You cannot safely recover from all native memory faults using Java try/catch; if C passes a bad pointer or wrong layout, the code can crash the JVM before Java handles any exception.

## 8. UpcallStub is a function pointer, but its lifetime belongs to Arena

When calling:

~~~java
MemorySegment stub = linker.upcallStub(target, descriptor, arena);
~~~

FFM generates a stub in native code and returns a **0-byte segment** carrying the function pointer address. `Arena` determines when the stub is freed. Once the arena closes, **C must no longer call** that function pointer.

### How to understand it properly

| Condition | What is allowed? |
| --- | --- |
| Stub just created, arena still alive | Can pass the pointer to a native API with a compatible signature |
| C invokes the callback synchronously and returns before the arena closes | Simple case, use try-with-resources like the `qsort` example |
| C retains the pointer to call in the future | Must keep the arena and related resources alive until unregistration and all in-flight callbacks finish |
| Arena has closed | **Do not** call the pointer anymore; risk of use-after-free/JVM crash |
| `stub.byteSize() == 0` | This is normal: a function pointer is not a data buffer |
| `stub.address() != 0L` | Only confirms there is an address; does not prove the signature is right or the lifecycle is safe |

For synchronous callbacks on the thread that created the arena, `Arena.ofConfined()` provides an easily controlled scope. **For callbacks executed by C from another thread or retained long-term**, you must consider `Arena.ofShared()`, thread access rules for `MemorySegment`s received from Java, and shutdown synchronization mechanisms.

Do not blindly choose `Arena.ofAuto()` if native C retains the function pointer across multiple calls; the callback lifecycle is dictated by C, whereas GC timing does not provide a reliable unregistration signal.

### Do not free a stub with C `free`

An upcall stub is not an allocation created by the caller via C `malloc`. `Linker.upcallStub` and the arena own the appropriate release mechanism. Do not call `free(stub.address())` and do not use `MemorySegment.NULL` as a substitute for unregistering; changing the value in a Java variable does not invalidate any copies of the function pointer that C has stored.

## 9. Asynchronous callback registration: a different contract

Not every native API is like `qsort`. Consider an illustrative C interface:

~~~c
typedef void (*event_callback)(int event_code, void *user_data);

void register_event_callback(event_callback cb, void *user_data);
void unregister_event_callback(void);
~~~

This is a **hypothetical prototype**, not an existing library to load/run. Suppose `register_event_callback` retains the function pointer and can call it **after register returns**. A safe model needs to distinguish the phases:

~~~text
Java creates callback target + upcall stub in a long-lived arena
                |
                v
C register_event_callback(stub, userData)
                |
                v
Native event loop / native worker thread
                |
                +-- callback(stub) occurs 0, 1, or more times
                |
                v
Java requests unregister
                |
                v
C confirms no new callbacks can be emitted
and all in-flight callbacks have finished
                |
                v
Java closes arena, releasing related resources
~~~

**Calling unregister alone may not be enough** if the C library does not guarantee waiting for in-flight callbacks. The library contract must clearly state when native has stopped using the pointer (which may require joining workers, flushing event queues, reference counts, or synchronization). The arena must not be closed before that point.

With multiple callbacks running concurrently:

- Java state used by the callback must be thread-safe.
- If the callback reads/writes a `MemorySegment` allocated from a confined arena on another thread, it may encounter `WrongThreadException`; choose an appropriate arena/access scope.
- Do not hold a Java mutex and call a native function if the native function can synchronously call back into Java and try to re-acquire a mutex/lock in a way that causes a deadlock. Java monitors are reentrant on the same thread, but multiple locks/threads can create a wait cycle.
- Do not assume the callback always executes on the Java main thread, Swing EDT, or JavaFX Application Thread. If the UI needs updating, dispatch the work to the UI framework's thread.
- A callback running on a different native thread may have its own context; avoid relying on `ThreadLocal` or transaction context from the registering thread.

## 10. Java callback state, context pointers, and Java objects

Some C APIs pass an extra `void *user_data` to the callback so the caller can distinguish registrations. That is a **native pointer-sized value**; there is no mechanism to automatically turn a Java object into a C pointer.

**Wrong:** casting a Java object or `System.identityHashCode(obj)` into a `void *` and expecting the native callback to find the exact object back.

The right design options:

1. **Bind Java state into `MethodHandle`:** For a Java instance with an `onEvent` method, `lookup.findVirtual(...).bindTo(instance)` creates a handle that already contains the receiver. The stub goes with that handle; the native caller only sees the pointer. Ensure the lifetimes of the stub/instance are coordinated.
2. **Native context allocation:** If the C API strictly requires `user_data`, allocate a native struct/token in a live arena; the mapping from token → Java object is explicitly managed by the application and cleaned up upon unregistration.
3. **ID-based registry:** C stores an integer/opaque token via `uintptr_t` or a struct according to a verified ABI; a Java registry manages the mapping, synchronization, and cleanup. Do not assume every bit pattern can be safely converted directly into a pointer.
4. **Immutable payload copy:** If only data owned by C is needed, copy it to native memory rather than keeping a Java object reference disguised as a pointer.

Approaches vary depending on the library's contract. Do not apply `ValueLayout.ADDRESS` to a Java `long` and call it a valid pointer without an API that reliably creates/receives addresses.

### Registering multiple callbacks

If a native API registers multiple listeners, each registration can have its own stub, handler/receiver, and resources. Use a clear owner to unregister the right callback. Do not reuse an old stub after its arena has closed; do not rely on the numeric address as a long-term ID, because the allocator may reuse addresses.

## 11. Exceptions from a Java callback: why are they so dangerous?

Oracle JDK 24's description of `Linker.upcallStub` states very clearly: **the target method handle should not throw any exceptions; if it does, the JVM may terminate abruptly**. This is a native boundary, not a normal Java-to-Java call that can automatically propagate a stack trace through C.

Wrong:

~~~java
static int unsafeCompare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    int y = b.get(ValueLayout.JAVA_INT, 0);
    if (x == 0) {
        throw new IllegalStateException("cannot compare zero");
    }
    return Integer.compare(x, y);
}
~~~

This is a **counter-example** (do not use as an actual callback); throwing `IllegalStateException` can cross the native ABI boundary and cause the runtime to terminate unexpectedly.

It is much better to **catch errors inside the callback**, record the state, return an appropriate C ABI value, and handle it at the Java/native owner layer when the contract allows:

~~~java
static int safeCompare(MemorySegment a, MemorySegment b) {
    try {
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0));
    } catch (Throwable failure) {
        // Store the error in a thread-safe error channel.
        return 0; // Never a promise of a valid sort result.
    }
}
~~~

The snippet above is only a sample and does not implement the error channel; the full example used `AtomicReference<Throwable>`. If the callback is `void`, the error handler must still ensure it does not exit via a Java exception. Do not assume `try/catch` can catch a segmentation fault caused by a wrong ABI or pointer.

**API Design:** A callback returning an `int` status should have a clear convention understood by C, e.g., nonzero for error, if the native API supports it. However, the `qsort` comparator **does not** have a separate error status; the sample code stores the error for Java to check when the downcall returns.

## 12. Pointer arguments in upcalls do not have bounds automatically

A C callback like:

~~~c
int compare(const void *a, const void *b);
~~~

When C calls the callback, FFM converts `a` and `b` into `MemorySegment`s. If the callback descriptor declares plain `ADDRESS`, the corresponding segments normally have `byteSize()==0` and global scope; you cannot call `get(JAVA_INT,0)` directly.

When you **know for sure C always passes a pointer to a 4-byte int**, you can use `ADDRESS.withTargetLayout(JAVA_INT)`. This **does not** make the C memory owned by Java; it only attaches bounds based on the native contract.

Safety rules:

- Check for pointer address 0 if C allows NULL, though **non-NULL is not enough** to guarantee the pointer is still valid.
- The target layout must match the actual data; for example, a `double` array cannot be read as an `int` region just because both have an address.
- A C pointer may only be valid **for the duration of a single callback**. Do not retain the segment wrapper from the callback to read after the native library has freed/reallocated the data.
- C `const void *` is a read-only contract; the `ADDRESS` layout does not automatically enforce immutability across all Java/native aliases.
- Ensure proper alignment with `ValueLayout`. On packed structs, unaligned layouts and ABI-correct logic may be required.
- If you want to keep data after the callback, copy the bytes into a Java/arena region you own **during the callback's lifetime** and verify the size beforehand.
- Do not create a raw pointer from a Java heap segment by casting addresses, because the JVM GC manages the heap and can move objects.

If a callback receives `void *ctx`, do not dereference `ctx` without knowing its length/ownership. `MemorySegment.NULL` is a C null pointer and may be valid depending on the API; check `ctx.address()==0L` before using.

## 13. ABI and signature: which errors can Java catch, and which can it not?

Two layers must be distinguished:

**Java MethodHandle layer:** FFM can match the target handle's type against the `FunctionDescriptor`. If the parameter count/types are incompatible, `upcallStub` can throw `IllegalArgumentException`.

**Native C ABI layer:** The JVM cannot inspect the machine/foreign library and automatically infer every function pointer signature. If C calls the stub using a function pointer with a calling convention, return type, variadic status, or argument layouts different from the descriptor, behavior can be undefined, leading to memory corruption/JVM crash.

| Error | When does it occur? | Prevention |
| --- | --- | --- |
| Java target has wrong `MethodType` | When calling `upcallStub` or building the handle | Derive type from descriptor, use `findStatic`/`findVirtual` with matching signature |
| C callback is `int (char*)` but Java describes `int(int)` | Native calls the function pointer | Compare against actual C header/ABI, do not guess |
| C `size_t` hardcoded as `JAVA_LONG` on another ABI | In `qsort` downcall | Use `canonicalLayouts().get("size_t")` |
| Pointer-to-pointer confused with pointer-to-data | Callback treats `T **` as `T *` | Diagram indirection levels; use the right layout/address slot |
| Native calls callback after arena close | Asynchronous/registered callback | Unregister + drain in-flight callbacks before close |
| Java callback throws exception across upcall | While callback is running | Catch errors in target, return fallback/status per C contract |
| C callback passes invalid pointer/expired lifetime | When Java accesses the segment | Check contract; do not treat `withTargetLayout` as validation |
| Stub used with wrong thread/confinement | Callback from native worker thread | Choose appropriate Arena/segments and synchronization |
| Native access not enabled | When calling restricted method | Run with flag or permitted module configuration |
| Native function symbol not found | Creating `qsort` downcall | Check `SymbolLookup`/actual shared library path |

`Linker.upcallStub` can reject a descriptor not supported by the linker. This is different from an ABI mismatch that the linker does not have enough information to detect. Accuracy of C headers, compiler targets, data layouts, and calling conventions is the integrator's responsibility.

## 14. Thread model: the callback may not return on the registering thread

The `qsort` example illustrates a synchronous call and has a simple scope. However, many C libraries have native worker threads, callback queues, or event loops.

- An FFM callback can run on **the thread the native library uses to call the function pointer**, not necessarily the Java thread that registered the listener.
- `Arena.ofConfined()` is suitable when the stub and memory segments are only used within the owner thread/a synchronous call with a clear contract.
- When callbacks are invoked from different threads, `Arena.ofShared()` or a thread-accessible lifetime mechanism may be more appropriate, **but a shared arena itself does not protect shared mutable state**.
- Synchronize Java data: use atomics/locks/queues accordingly; reading native memory must also account for data races.
- Avoid holding a Java lock across a downcall if C can call back synchronously and the callback needs the locked resources; design to avoid deadlock.
- Do not let a callback close the very arena/stub being invoked if C might still use the function pointer; wait for coordinated lifetime from the owner.
- If the callback needs to update the UI, dispatch to the proper UI thread; do not update UI directly from an arbitrary native callback thread.

Do not assume an FFM upcall has the same contract as a JNI native method with a pre-passed `JNIEnv *`. A `MethodHandle` is Java logic; working with JNI separately requires appropriate attach/context mechanisms.

## 15. Callbacks returning a pointer need an extra lifetime contract

A callback with return type `void *` or `char *` will have a descriptor returning `ValueLayout.ADDRESS` and a Java target returning `MemorySegment`. This is a dangerous case: C may retain the address returned by Java.

Example **prototype only**:

~~~c
const char *get_name(void *ctx);
~~~

If the Java callback returns a pointer to a buffer allocated with `Arena.ofConfined()` inside the callback and that arena closes immediately on return, C receives a **dangling pointer**. This cannot be fixed by keeping a Java `String`: you must prepare a native region with the right encoding/terminator, keep it alive per the C contract, and determine who is responsible for freeing it.

Similarly, if the C API requires the callback to return a pointer that C will `free`, the returned region must be allocated with an allocator that C is allowed to free. You cannot arbitrarily return `arena.allocate(...)` and expect C's `free` to be compatible; an ownership mismatch can crash.

Additionally, a method handle returning `MemorySegment.NULL` means a C null pointer; do not use Java `null` as an arbitrary substitute. The native ABI carrier for `ADDRESS` is `MemorySegment`.

## 16. Synchronous vs. asynchronous upcalls: design comparison

| Property | Synchronous like `qsort` | Registered / asynchronous callback |
| --- | --- | --- |
| When C calls the callback | During a downcall | After registration returns, possibly much later |
| Who manages stub lifetime? | `try (Arena ...)` block surrounding the downcall | Long-lived owner, closed after unregister and drain |
| Typically suitable Arena | Confined when thread/lifetime are guaranteed | Shared or design suitable for native worker threads |
| Callback state | Can be state of the current call | Needs to be thread-safe, guard against callbacks after shutdown |
| Error reporting | Java can check error channel after downcall | Needs asynchronous error channel or native status contract |
| Closing the stub | After downcall returns and callback finishes | After ensuring C can no longer call the pointer |
| Callback data pointers | Trust memory only for the duration C guarantees | Needs explicit ownership/snapshot if outliving the callback |

Common point: **you cannot just keep the numeric address of a function pointer to make a callback live forever**. What matters is that both the arena and the native library agree on the time boundaries, and that the Java target/state remain valid.

## 17. Performance and practical considerations

A callback crossing the Java/native boundary has costs related to ABI transitions, thread state, and the JVM runtime. Therefore:

- Do not assume FFM upcalls are always faster than JNI callbacks or pure C functions. Benchmark on your actual JDK/OS/CPU and workload.
- With `qsort`, the comparator may be called many times; performing network I/O, heavy logging, allocating many objects, or blocking inside the callback can incur huge overhead.
- Avoid invoking a Java callback per byte of a large stream if data can be batched per the API contract.
- When native synchronously calls back into Java, the callback can trigger reentrant logic; design for idempotency/synchronization if the API permits it.
- Do not confuse `MethodHandle` with Java reflection `Method.invoke`: the target handle is used by the linker for the ABI boundary, while handle lookup/adaptation is done before the callback.
- Check the case where the native library is unloaded while stubs/pointers are still retained; symbol lookup, downcall handles, and upcall stubs are all subject to the lifecycle of the associated native resources.

## 18. Troubleshooting scenarios

### 18.1. `IllegalArgumentException` when creating an upcall stub

Check that `FunctionDescriptor.of` has the exact return/argument layouts matching the C callback prototype, and that `comparatorDesc.toMethodType()` matches the static method signature. If the C comparator returns `int`, the Java target must not be declared `void` or `long`. When using an instance method callback, you need `bindTo(instance)` before pairing it with a descriptor that lacks a receiver parameter.

### 18.2. `IllegalCallerException` when creating stub/downcall

`upcallStub` and downcall handle creation are restricted. On the classpath, run `java --enable-native-access=ALL-UNNAMED ...`; on the module path, grant permission to the appropriate module. Depending on the JDK and native access control mode, missing permissions can lead to warnings or errors; do not ignore the contract.

### 18.3. Native `qsort` not found in default lookup

`Linker.defaultLookup()` is chosen by the JVM and the set of symbols varies by platform. The learning example ran on the tested JDK 24 Windows/x64, but other OSes/JDKs are not guaranteed to expose `qsort` identically. When a real C API belongs to a separate shared library, use `SymbolLookup.libraryLookup` with the right path/library and check for symbol errors before calling.

### 18.4. `IndexOutOfBoundsException` in the Java comparator

If the two pointer callback arguments are described with `ADDRESS` without a target layout, they normally have size 0; `get(JAVA_INT,0)` will fail. When the C contract guarantees each pointer points to a 4-byte int, use `ADDRESS.withTargetLayout(JAVA_INT)`. Do not assign an arbitrarily large target layout to bypass the error, as that breaks memory safety.

### 18.5. Native worker invokes callback after plugin stops

This is a **use-after-free** lifetime bug that can cause a crash, not just a Java exception. You must design `unregister`/`cancel`/`join` so there are no in-flight callbacks and no remaining call paths before closing the arena. If the native API does not support unregistration, do not close the stub while native still holds the pointer; revisit the architecture or retain the lifetime until the native subsystem has completely terminated.

### 18.6. Callback returns 0 but native result is incorrect

A comparator returning 0 means two elements are equivalent **according to the comparator**. If 0 is used as a fallback because Java code encountered an error, the sort result is no longer trustworthy. Record the error and detect it after the downcall (or via an async error channel); do not silently interpret the sort as successful.

### 18.7. Callback is called more times than expected

`qsort` does not guarantee a specific call count/comparison order. Do not count invocations as part of correctness requirements. If an API callback can be invoked repeatedly, the handler must have appropriate logic (especially for callbacks with side effects).

## 19. Code review checklist for FFM upcalls

- [ ] Read the C callback prototype accurately, including return type, arguments, pointer indirection, and calling convention?
- [ ] Does `FunctionDescriptor` describe the right ABI/C types, without guessing `size_t` or struct layouts from Java types?
- [ ] Does `MethodHandle.type()` match `FunctionDescriptor.toMethodType()`?
- [ ] Is `Linker.upcallStub` called with native-access permission and a live arena?
- [ ] Is the function pointer passed as a `MemorySegment` for the C function pointer/`ValueLayout.ADDRESS` parameter?
- [ ] Are you avoiding dereferencing the `upcallStub` as a data buffer or calling C `free` on the stub's address?
- [ ] For pointer arguments received from C, have size, alignment, lifetime, and NULL policy been determined before `get`/`set`?
- [ ] If using `withTargetLayout`, is the target layout verified by the C contract?
- [ ] Does the callback target catch errors within the boundary and **not** let Java exceptions escape to C?
- [ ] For synchronous callbacks, does the arena live at least for the duration of the downcall; for async callbacks, are unregistration and draining of in-flight callbacks implemented?
- [ ] Is Java callback state thread-safe; are you avoiding assuming the callback runs on the main/UI thread?
- [ ] Are you avoiding using confined segments in callbacks on another native thread without checking ownership?
- [ ] If the callback returns a pointer, does that memory stay alive as long as C needs it and does the deallocator match the owner?
- [ ] Are there no double-free, use-after-free, dangling callback pointer, or post-unload callback issues?
- [ ] Tested empty input, duplicates, negative/positive elements, multiple callback invocations, shutdown races, and error paths.
- [ ] Tested on the actual target OS/CPU/JDK, with the real native library and ABI rather than just reading Java source?

## 20. Self-check questions

**Question 1.** What is it called when native C invokes a function pointer leading to a Java `MethodHandle` via FFM?

**Answer:** An **upcall**, connected via `Linker.upcallStub`. Java calling C is a downcall.

**Question 2.** Can you pass a Java `Comparator<Integer>` directly as the `int (*compar)(...)` parameter of `qsort`?

**Answer:** No. You must create a Java `MethodHandle` of the matching type, declare the C function descriptor, create an upcall stub (a native function pointer), and then pass that pointer to the `qsort` downcall.

**Question 3.** Why does `upcallStub` take an `Arena`?

**Answer:** The Arena **manages the stub's lifetime**. After the arena closes, the function pointer is no longer valid; C must not continue calling it.

**Question 4.** For a C callback `int compare(const void *a, const void *b)`, what does the Java descriptor look like?

**Answer:** Return `JAVA_INT`, two arguments as `ADDRESS`. If the API guarantees each pointer points to a 4-byte int, you can use `ADDRESS.withTargetLayout(JAVA_INT)` so Java receives 4-byte segments; this is a restricted operation requiring a trusted contract.

**Question 5.** Why does the `qsort` downcall descriptor use `sizeT` instead of a fixed Java `JAVA_LONG`?

**Answer:** C `size_t` is ABI-dependent. The example inspects `linker.canonicalLayouts().get("size_t")` and only runs on a 64-bit `size_t` ABI.

**Question 6.** If a Java callback target throws an exception that escapes out of the upcall, what can happen?

**Answer:** Oracle Javadoc warns that the JVM may **terminate abruptly**. You must catch inside the callback, return an ABI-compliant fallback/status, and report the error via a separate mechanism.

**Question 7.** Why does `stub.byteSize() == 0` not mean the callback is broken?

**Answer:** An upcall stub represents a **function pointer**, not a data buffer. A 0-byte segment with an address is the normal return type of `upcallStub`.

**Question 8.** C retains the callback after `register` returns. Can Java close the arena immediately?

**Answer:** No. The arena must remain alive as long as C can still invoke it; you must unregister and wait for all in-flight callbacks to finish before closing.

**Question 9.** A C callback takes `void *user_data`. Can you cast a Java object into a raw pointer?

**Answer:** No. Bind Java state into the method handle or use a native context/registry with clear lifetime and synchronization.

**Question 10.** Does `qsort` promise exactly 7 comparator calls for 5 elements?

**Answer:** No. C libraries may have different algorithms/comparison counts. Only verify that the callback was invoked and the array was sorted properly.

**Question 11.** Is using a confined arena for a callback receiving data from another native worker thread guaranteed to be correct?

**Answer:** No. You must consider thread access permissions, stub lifetime, and segments. A shared arena or another synchronization design may be necessary, depending on the native callback contract.

**Question 12.** A callback returns a `MemorySegment` representing a C pointer. Can you return memory from an arena that closes right when the callback returns?

**Answer:** Not if C will continue using the pointer. You must keep the allocation alive at least until C is done and release it using the proper ownership mechanism.

## Official Documentation

1. [Oracle Java SE 24 — Linker API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): `upcallStub`, `downcallHandle`, `nativeLinker`, canonical C layouts, ABI, and safety considerations.
2. [Oracle Java SE 24 — FFM Guide](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html): guide to upcalls using C `qsort` and function pointers.
3. [Oracle Java SE 24 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): signature layouts and `toMethodType`.
4. [Oracle Java SE 24 — AddressLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html): `ADDRESS`, `withTargetLayout`, and pointer bounds.
5. [Oracle Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared memory lifetime.
6. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): official FFM API since Java 22.
7. [Java 24 — MethodHandles](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html): `findStatic`, `bindTo`, and combinators.

**Conclusion:** A **callback** is the general call-back pattern; a **function pointer** is a C ABI-compliant function address; an **upcall** is native code calling Java through an **FFM upcall stub**. A correct integration does not just create a pointer, but also gets the **C signature, native access, Arena lifetime, callback data ownership, and the rule against letting Java exceptions escape across the C boundary** right.
