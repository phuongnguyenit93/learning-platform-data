# Creating an upcallStub with the Appropriate FunctionDescriptor and Arena

> **Context:** Java Advance → Native Interoperability → Callbacks with FFM. This lesson guides you through using the Foreign Function & Memory API to convert **a Java `MethodHandle` into a native function pointer** using `Linker.upcallStub(target, descriptor, arena)`, match signatures using `FunctionDescriptor`, and choose an `Arena` so that the function pointer lives long enough while being released at the right time. The code runs on **JDK 22+** (FFM finalized in JEP 454); the `qsort` example uses the 64-bit OS C ABI with an 8-byte `size_t`.

## 1. What is an upcall and why is a native function pointer needed?

When Java calls a C/C++ function via FFM, that is a **downcall**. Conversely, a native library may need to call back into logic written in Java via a **callback**, such as a `qsort` comparison function, an SDK listener, an event-driven programming API, or a data processing library:

```c
// Standard C declaration; not a standalone program.
void qsort(void *base, size_t count, size_t elementSize,
           int (*compare)(const void *left, const void *right));
```

The `compare` argument is a **C function pointer**, not a Java `Comparator`, lambda, or ordinary object. Native code will store or invoke this address according to the C ABI.

FFM provides the conversion chain:

```text
Java method / lambda-bound state
           |
           | MethodHandles.lookup().findStatic/findVirtual
           v
MethodHandle  (Java signature / MethodType)
           |
           | FunctionDescriptor (native signature / C ABI)
           | Arena (lifetime of trampoline/code stub)
           v
Linker.upcallStub(target, descriptor, arena)
           |
           v
MemorySegment stub (function pointer address, size=0)
           |
           | passed as ADDRESS to native function
           v
Native C/C++ invokes function pointer
           |
           v
FFM runtime -> Java MethodHandle -> returns result to native
```

**Three mandatory elements** for an upcall to be created and used properly:

1. **`target` — MethodHandle:** represents a Java method whose **parameter types and return type** match the carrier types derived from the descriptor.
2. **`function` — FunctionDescriptor:** describes the **C function-pointer signature** according to the platform's ABI, not just the Java types visible in source code.
3. **`arena` — lifetime owner:** keeps the native stub/code pointer alive for the entire duration that C code may invoke it.

If only two of the three elements are right, the application can still encounter runtime errors, JVM crashes, or native use-after-free.

## 2. Distinguishing MethodHandle, FunctionDescriptor, MemorySegment, and Arena

| Object | Purpose | Example with comparator `int (*)(const int*, const int*)` |
|---|---|---|
| `MethodHandle` | Java call target, represented by `MethodType` | `(MemorySegment, MemorySegment)int` |
| `FunctionDescriptor` | C ABI signature (return layout, argument layouts) | `of(JAVA_INT, ADDRESS, ADDRESS)` with target layouts for both pointers |
| `Linker.nativeLinker()` | Binds to the current ABI, creates downcalls and upcalls | Native linker for Linux/x64, Windows/x64, etc. |
| `Linker.upcallStub(...)` | Creates a native trampoline for native code to call Java | Returns a `MemorySegment` containing the function pointer address |
| `Arena` | Manages the stub's lifetime | `Arena.ofConfined()` for a callback used only within a synchronous downcall |
| `MemorySegment` stub | **Function pointer**, not a Java data array | Passed as a `ValueLayout.ADDRESS` argument |
| `SymbolLookup` | Looks up native function names in a library | `defaultLookup().findOrThrow("qsort")` |

The easiest thing to confuse is **the two kinds of MemorySegment**:

- `arena.allocateFrom(JAVA_INT, ...)` creates a segment **containing the integers** to be sorted.
- `linker.upcallStub(...)` creates a segment **carrying only the native callback stub address**; `stub.byteSize()==0`. Do not call `stub.get(JAVA_INT,0)` to "read the callback". Pass `stub` into a C argument of type **function pointer**.

Both segments can reside in the same Arena for cleaner lifetime management, but they are two different kinds of resources with different meanings and usage.

## 3. Defining the descriptor from the C signature, not guessing from Java

C comparator example:

```c
int compare(const int *a, const int *b);
```

Under the example ABI, `int` is a 32-bit integer and the two pointers point to each `int` value. The corresponding FFM descriptor:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

FunctionDescriptor comparatorDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);
```

This is an **illustrative snippet**, placed inside a method/static initializer. Meaning of the order:

- The first parameter of `FunctionDescriptor.of(returnLayout, argLayouts...)` is the **layout of the return value**. `JAVA_INT` describes the comparator's `int`.
- The next two parameters are **pointer arguments**, each having the Java carrier type `MemorySegment`.
- `ADDRESS.withTargetLayout(JAVA_INT)` declares the **data type at the pointer target**, allowing FFM to create a view with the size of one `int` for the callback to read at offset 0.
- Do not write `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)`: the two C parameters are `const int*`, not two `int` values.
- Do not interpret `withTargetLayout` as a copy or allocation operation: it only describes the view/length that FFM applies to the pointer argument.

In Java, the callback will have the signature:

```java
// Java function definition snippet; not a complete program.
static int compare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    int y = b.get(ValueLayout.JAVA_INT, 0);
    return Integer.compare(x, y);
}
```

**Do not use `return x - y`** to compare two `int` values, because subtraction can overflow. `Integer.compare(x,y)` returns negative/0/positive in accordance with the C comparator contract.

### `ofVoid` and callbacks with no return value

For the C prototype:

```c
typedef void (*event_callback)(int value, void *context);
```

The descriptor uses `FunctionDescriptor.ofVoid(JAVA_INT, ADDRESS)`. The Java target receives `(int, MemorySegment)void`. If a C callback returns `void`, do not use `FunctionDescriptor.of(JAVA_INT,...)` just because you want Java to return a status; **the native ABI must be described accurately**.

## 4. Matching MethodType properly: Java carriers must match the descriptor

Here is a correct example when the Java comparator is a static method:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);

MethodHandle target = MethodHandles.lookup().findStatic(
        CallbackDemo.class,
        "compare",
        descriptor.toMethodType()
);
```

This code snippet only illustrates the lookup; it assumes `CallbackDemo.compare` has the signature `(MemorySegment, MemorySegment)int`, along with imports from `java.lang.invoke` and `java.lang.foreign`.

`descriptor.toMethodType()` converts native layouts into Java carrier types:

| C/FFM layout | Java MethodHandle carrier |
|---|---|
| `JAVA_INT` | `int.class` |
| `JAVA_LONG` | `long.class` |
| `JAVA_DOUBLE` | `double.class` |
| `ADDRESS` | `MemorySegment.class` |
| `FunctionDescriptor.ofVoid(...)` | `void.class` for return type |

Equivalent way to write it:

```java
MethodType.methodType(
        int.class, MemorySegment.class, MemorySegment.class
)
```

In practice, use `descriptor.toMethodType()` to avoid accidentally omitting parameters. If the callback is an **instance method**, `findVirtual` creates a handle with the receiver at the front; you must **bind the receiver** using `bindTo(instance)`, or use `MethodHandles.insertArguments` to achieve the exact MethodType required by the descriptor.

If the Java method accepts `long` while the descriptor is `JAVA_INT`, or the Java target returns `void` while the descriptor returns `JAVA_INT`, `upcallStub` typically throws `IllegalArgumentException` when types are incompatible. Do not fix this by casting pointers or coercing numbers arbitrarily: re-read the C prototype and how C types map under the real ABI.

**`FunctionDescriptor` does not turn a Java object into a native C object.** If a C callback accepts `void *userData`, this is a native pointer (represented as `MemorySegment`), not an arbitrary Java `Object`. To store Java state, the simplest approach is to **bind an instance into the MethodHandle** and maintain ownership/lifetime of the state, rather than trying to cast a Java object reference into `void*`.

## 5. Complete runnable example: qsort calling back a Java comparator

This example is particularly well suited for testing `upcallStub` because the C standard library's `qsort` invokes the callback **synchronously**, before `qsort` returns; therefore, **`Arena.ofConfined()`** is the clear choice when all invocations occur on the thread performing the downcall.

**File `QsortUpcallDemo.java`, JDK 22+ on an ABI with 32-bit `int` and 64-bit `size_t` (e.g., Linux x86_64):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import static java.lang.foreign.ValueLayout.*;

public final class QsortUpcallDemo {
    static final class CompareState {
        final AtomicReference<Throwable> failure =
                new AtomicReference<>();

        int compare(MemorySegment left, MemorySegment right) {
            try {
                int a = left.get(JAVA_INT, 0);
                int b = right.get(JAVA_INT, 0);
                return Integer.compare(a, b);
            } catch (Throwable error) {
                // DO NOT let Throwable escape a native callback.
                failure.compareAndSet(null, error);
                return 0; // fallback on a failed invocation.
            }
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // int compare(const int*, const int*)
        FunctionDescriptor compareDescriptor =
                FunctionDescriptor.of(
                        JAVA_INT,
                        ADDRESS.withTargetLayout(JAVA_INT),
                        ADDRESS.withTargetLayout(JAVA_INT)
                );

        CompareState state = new CompareState();
        MethodHandle compareHandle = MethodHandles.lookup()
                .findVirtual(CompareState.class, "compare",
                        compareDescriptor.toMethodType())
                .bindTo(state);

        // void qsort(void*, size_t, size_t, compare_fn)
        MethodHandle qsort = linker.downcallHandle(
                linker.defaultLookup().findOrThrow("qsort"),
                FunctionDescriptor.ofVoid(
                        ADDRESS, JAVA_LONG, JAVA_LONG, ADDRESS)
        );

        MemorySegment callbackPointer;

        try (Arena arena = Arena.ofConfined()) {
            callbackPointer = linker.upcallStub(
                    compareHandle, compareDescriptor, arena);

            // C array int[6] in off-heap memory.
            MemorySegment data = arena.allocateFrom(
                    JAVA_INT, 9, 4, 7, 1, 3, 2);

            // invokeExact matches the handle signature:
            // (MemorySegment, long, long, MemorySegment)void.
            qsort.invokeExact(data, 6L,
                    JAVA_INT.byteSize(), callbackPointer);

            if (state.failure.get() != null) {
                throw new IllegalStateException(
                        "callback failed", state.failure.get());
            }

            System.out.println("result="
                    + Arrays.toString(data.toArray(JAVA_INT)));
            System.out.println("stubBytes="
                    + callbackPointer.byteSize());
        } // qsort has returned; no native caller uses the stub anymore.

        System.out.println("stubAlive="
                + callbackPointer.scope().isAlive());

        // DO NOT invoke the function pointer after the Arena has closed.
    }
}
```

Run with JDK 22+:

```bash
javac -encoding UTF-8 QsortUpcallDemo.java
java --enable-native-access=ALL-UNNAMED QsortUpcallDemo
```

**Successful stdout (behavior and values verified on JDK 24):**

```text
result=[1, 2, 3, 4, 7, 9]
stubBytes=0
stubAlive=false
```

**Why is each part necessary?**

1. `Linker.nativeLinker()` knows the current JVM's ABI; `defaultLookup()` finds `qsort` in the native libraries provided by the runtime.
2. `compareDescriptor` describes the comparator's **function pointer signature**; the two `ADDRESS.withTargetLayout(JAVA_INT)` layouts give the callback a view capable of reading a C `int`.
3. `findVirtual(...).bindTo(state)` keeps the callback receiver attached to the MethodHandle and removes the receiver from the parameter list, so the target has `(MemorySegment,MemorySegment)int` matching the descriptor.
4. `linker.upcallStub(compareHandle,compareDescriptor,arena)` creates a native function pointer within the Arena's scope.
5. `arena.allocateFrom(JAVA_INT,...)` copies the numbers into native memory rather than passing the internal address of a Java heap array directly.
6. `qsort.invokeExact(data, 6L, 4L, callbackPointer)` goes **Java → C**; each time the comparator is called, control goes **C → Java → C**.
7. Once `qsort` returns, no synchronous `qsort` invocation is still using the callback; closing the Arena at the end of `try` is safe in this example.
8. `stubBytes=0` reminds you that `callbackPointer` is only a **function address**, not a 4-byte data segment.
9. `stubAlive=false` only illustrates that the scope is closed; it does **not** turn that pointer back into a usable pointer.

The pattern catches `Throwable` **inside** `CompareState.compare` and records the error in an `AtomicReference`. If an error occurs, the comparator returns fallback 0 only to **avoid throwing across the native boundary**; after `qsort` returns, Java checks the error and throws from the **Java call stack**, where it is safer to report the failure. In production, you must decide how to handle a comparator failure mid-sort: the result may not be in the right order and should be discarded.

### ABI limitations of the example

The code describes C `size_t` using `JAVA_LONG` (8 bytes), which is right on many 64-bit platforms, though not all platforms. If the JVM runs on a 32-bit ABI, `size_t` may be 4 bytes, requiring `JAVA_INT` and adjusting the argument carriers when calling `invokeExact`. For cross-platform deployment, check `linker.canonicalLayouts().get("size_t")` or use bindings generated by `jextract`, rather than hard-coding `size_t` mapping across architectures.

ABI mismatches **can crash the JVM**, not merely throw a Java exception. Always use the exact C header and test on the target OS/CPU/toolchain.

## 6. Why does upcallStub return a 0-byte MemorySegment?

An `upcallStub` returns a `MemorySegment` with a **native address**. The API specifies that the resulting segment's size is **0** because it does not contain a user data region that can be read with `get/set`; the address inside the segment is the native code trampoline generated by the linker.

Correct operations:

```java
MemorySegment functionPointer =
        linker.upcallStub(target, callbackDescriptor, arena);

// Pass functionPointer to a C argument of type function pointer.
// Example: registerCallback.invokeExact(functionPointer);
// You may check functionPointer.byteSize() == 0.
```

This is a snippet; the variables are declared in outer code. Do not use `functionPointer.asSlice(0,...)`, `reinterpret`, or `get(JAVA_INT,0)` to "access the callback code" because the pointer does not represent a Java/C data buffer. Do not manually call C `free(functionPointer.address())`; the Arena is the owner of the stub.

If a callback needs to return a **data pointer**, the Java target's return value must be a `MemorySegment` carrying a valid native address, and the native consumer must have a clear ownership/lifetime contract for the **data** pointed to. A native function may retain the address after the callback; if Java closes the Arena containing the data before native code finishes using it, a dangling pointer will occur. Returning a pointer in an upcall does **not** automatically extend the data's lifetime.

## 7. Choosing the right Arena: callback scope decides

| Arena | Who can access and close? | When to use for upcall stub | Key point to remember |
|---|---|---|---|
| `Arena.ofConfined()` | Owner Java thread; closed on owner | Synchronous callback and no other native thread retains/calls the pointer | Closed after the native downcall returns; unsuitable as a default for callbacks that may arrive from foreign workers |
| `Arena.ofShared()` | No fixed owner thread; explicit close, multi-thread access | Retained SDK callback, callbacks may arrive from multiple native threads | **Unregister + quiescence + join** before `arena.close()` |
| `Arena.ofAuto()` | GC-managed, cannot be explicitly closed | Cases where deterministic release timing is unnecessary and Java reachability is clear | Native C holding a raw pointer is **not** treated as a Java strong reference |
| `Arena.global()` | Global scope, no explicit close | Only for callbacks designed to live for the entire JVM/process lifetime | Stub/native resources are not reclaimed via `close`; easy to leak if used for short-lived callbacks |

**Quick selection:**

- C function invokes the callback immediately within a single synchronous call and finishes (e.g., `qsort`): `try(Arena arena = Arena.ofConfined())`.
- SDK registers the callback and invokes it at a later time, not on the same call stack, or callbacks come from another native thread: **`Arena.ofShared()` + lifecycle owner + stop/unregister/drain**.
- Callback genuinely needs to exist until process exit: consider the global Arena, but accept the long lifetime and account for leaks.
- Unsure how long the SDK retains the callback pointer? **Not yet safe to create/close the stub**. Read the native contract first.

**Do not treat a shared arena as a thread-safety guarantee for a Java listener.** `Arena.ofShared` enables multi-threaded scope management/access; Java state inside the callback still needs `AtomicInteger`, locks, queues, or separate thread confinement to avoid data races. The fact that a callback may run on a native-created thread also affects thread-local context and UI/framework applications; do not assume it runs on the Java main thread.

### Why is `Arena.ofAuto()` hard to control for SDK-retained callbacks?

A native SDK may store only **a machine address** in a C struct without holding a Java reference to the `Arena` or `MemorySegment`. Java GC does not treat that raw address as a strong reference. If Java does not keep the owner/stub/state reachable under a deterministic contract, using a GC-managed arena can cause the stub to be freed while native code still holds the function pointer. Using `ofShared` with `close()` after unregistering is clearer when a callback exists for the lifetime of a session.

## 8. Second example: SDK retains callback across multiple native calls

`qsort` only needs the callback during a single synchronous downcall. Many native SDKs work differently: Java calls `register_callback(fn)`, native code **stores the pointer**, and a `fire_callback` call happens later. In this case, the Arena must not be closed as soon as `register_callback` returns.

The following simple Linux example uses a **single-threaded/synchronous dispatch SDK** to focus on illustrating **retained function pointer + shared Arena + unregister**. It does **not** spawn pthreads itself. To run callbacks from a native worker, you must extend the C code with stop, join, and an in-flight barrier as in section 9.

### 8.1. Native file `callback_demo.c`

```c
// C11; example library must only be called sequentially from a single control thread.
typedef void (*event_callback)(int value);

static event_callback current = 0;

int register_callback(event_callback cb) {
    if (cb == 0 || current != 0) {
        return -1;
    }
    current = cb;              // RETAINS the native function pointer.
    return 0;
}

void fire_callback(int value) {
    // In this example, fires synchronously; callback returns before this function.
    if (current != 0) {
        current(value);
    }
}

void unregister_callback(void) {
    // Sample SDK has no native worker/concurrent in-flight calls.
    current = 0;
}
```

**Explicit limitation:** the global variable `current` is not synchronized; only call sequentially from one control thread. If one thread calls `fire_callback` while another calls `unregister_callback`, this can be a C data race and is not safe enough. A real SDK must define thread safety and guarantee that unregister has prevented new callbacks and waited for running callbacks (or allow the client to use its own barrier).

### 8.2. Java file `CallbackRegistrationDemo.java`

```java
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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static java.lang.foreign.ValueLayout.*;

public final class CallbackRegistrationDemo {
    private static final AtomicInteger last = new AtomicInteger(-1);
    private static final AtomicReference<Throwable> failure =
            new AtomicReference<>();

    private static void onValue(int value) {
        try {
            last.set(value);
        } catch (Throwable error) {
            // Never let Throwable escape an upcall.
            failure.compareAndSet(null, error);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Shared arena lives across register -> fire -> unregister.
        try (Arena arena = Arena.ofShared()) {
            SymbolLookup sdk = SymbolLookup.libraryLookup(
                    Path.of("./libcallback_demo.so").toAbsolutePath(),
                    arena);

            MethodHandle register = linker.downcallHandle(
                    sdk.findOrThrow("register_callback"),
                    FunctionDescriptor.of(JAVA_INT, ADDRESS));

            MethodHandle fire = linker.downcallHandle(
                    sdk.findOrThrow("fire_callback"),
                    FunctionDescriptor.ofVoid(JAVA_INT));

            MethodHandle unregister = linker.downcallHandle(
                    sdk.findOrThrow("unregister_callback"),
                    FunctionDescriptor.ofVoid());

            MethodHandle javaTarget = MethodHandles.lookup()
                    .findStatic(CallbackRegistrationDemo.class,
                            "onValue",
                            MethodType.methodType(void.class, int.class));

            MemorySegment callbackPointer = linker.upcallStub(
                    javaTarget,
                    FunctionDescriptor.ofVoid(JAVA_INT),
                    arena);

            int status = (int)register.invokeExact(callbackPointer);
            if (status != 0) {
                throw new IllegalStateException("register failed");
            }

            try {
                fire.invokeExact(7);    // Native -> onValue(7)
                fire.invokeExact(21);   // Native -> onValue(21)

                if (failure.get() != null) {
                    throw new IllegalStateException(
                            "callback failed", failure.get());
                }
                System.out.println("last=" + last.get());
            } finally {
                unregister.invokeExact();
                // SDK no longer stores the callback address.
            }
        } // Close arena AFTER unregister and after all synchronous fires.

        System.out.println("unregistered");
    }
}
```

Compile/run commands on Linux with GCC and JDK 22+:

```bash
gcc -std=c11 -fPIC -shared \
  -o libcallback_demo.so callback_demo.c

javac -encoding UTF-8 CallbackRegistrationDemo.java
java --enable-native-access=ALL-UNNAMED CallbackRegistrationDemo
```

**Expected stdout on successful run:**

```text
last=21
unregistered
```

Explanation:

- `SymbolLookup.libraryLookup(Path,arena)` opens the native library and ties the lookup/library lifetime to the appropriate arena. Use the exact built file path and native access permission.
- `register`, `fire`, and `unregister` are **downcall handles** for the three C entrypoints; `javaTarget` is the **Java MethodHandle** for the callback.
- `FunctionDescriptor.ofVoid(JAVA_INT)` describes `void (*event_callback)(int)`. Do not use `FunctionDescriptor.of(JAVA_INT,...)` because the callback function does not return a value.
- `upcallStub(javaTarget, ..., arena)` creates a pointer that C can store. After `register`, **do not close the arena**, even though the Java `register` invocation has returned.
- `fire_callback` invokes the stored pointer; Java `onValue` updates the `AtomicInteger`. Using an atomic makes the listener ready for cases requiring state synchronization, but **does not fix** C-side data races if the C implementation is called from multiple threads.
- In `finally`, `unregister.invokeExact()` removes the pointer from the SDK. Because the C example only invokes synchronously and sequentially on one thread, after the last `fire.invokeExact` returns there are no in-flight callbacks.
- Only after `unregister` does execution exit `try` and call `arena.close()`, rendering the stub and symbol lookup unused.

**Why choose `Arena.ofShared` even though the C example is synchronous?** To demonstrate a session owner that can live across multiple calls and avoid a design restricted to one owner thread if the SDK later extends callbacks to come from a worker. If you are certain all operations are on the same Java owner thread and the SDK has no async callbacks, `ofConfined` can still be used, provided all operations and closing happen on that exact thread.

**Exception note:** the demo assumes SDK register/fire/unregister all fulfill the contract and unregister does not fail. A real SDK needs error-code handling, shutdown ownership, stop/await when native workers exist, and must not close the Arena after a failed unregister if the SDK might still retain the pointer. Do not attempt to run the `callback_demo.c` example as a multi-threaded production SDK.

## 9. Native worker invoking callbacks asynchronously: stop, unregister, join, then close

Some C/C++ libraries store callbacks and invoke them later from a timer, I/O thread, or worker pool. The function pointer must remain alive **throughout the entire period the SDK might call it**.

```text
Java: Session OPEN                  Native SDK:
   create Arena.ofShared()
   create MethodHandle
   upcallStub -> fnPtr
   register(fnPtr)  -----------------> stores fnPtr in registry
   start()           ----------------> worker thread
                                       |
                                       +--> callback(fnPtr) ---> Java method
                                       +--> callback(fnPtr) ---> Java method
   requestStop()     ----------------> stop new callbacks
   unregister()      ----------------> remove registration
   awaitQuiescent()  <---------------- worker + in-flight calls done
   arena.close()                     no native user of fnPtr remains
   Session CLOSED
```

Actual API names may vary: `stop`, `unregister`, `join`, `drain`, or `awaitStopped`; the order depends on the SDK's guarantees. For example, one SDK may require **unregister before stop**, while another has `stopAndJoin` that does both. Do not assume that `unregister` always waits for running callbacks. What must be proven before `arena.close()` is:

1. No native entrypoint can **start** invoking the function pointer anymore.
2. All running callbacks have **returned**.
3. All workers that could hold and invoke the pointer have been **joined/drained**, or have an equivalent synchronization/retention guarantee.
4. No queued tasks or SDK objects containing the function pointer remain to be invoked later.
5. The library providing the callback trampoline and the target Java state remain alive throughout that period.

**Serious mistake:**

```java
// ANTI-PATTERN: DO NOT run.
MemorySegment callbackPointer;
try (Arena arena = Arena.ofShared()) {
    callbackPointer =
            linker.upcallStub(target, descriptor, arena);
    sdkRegister.invokeExact(callbackPointer);
} // Arena closes while SDK still holds the pointer.
  // Later callback: may jump into a freed native code stub.
```

The JVM is not guaranteed to throw `IllegalStateException` **before** C calls a freed machine address. From C's perspective, this can be a **dangling function pointer** and cause a crash or memory corruption. Checking `MemorySegment.scope().isAlive()` only lets Java check the view's state; it cannot make native C storing the pointer "magically" become safe.

### Do not hold locks needed by the callback while joining

If the controller holds a mutex and then calls `join(worker)`, while the callback on the worker wants to acquire that same Java/native mutex, a deadlock can occur. A good lifecycle owner separates non-blocking `requestStop()` from `awaitStopped()`, and only releases the pointer upon receiving acknowledgement from the SDK. If the callback calls `close()` and `close` tries to join the callback thread itself, that is also a self-join/lock inversion.

## 10. Distinguishing lifetimes of stub, data, library, and Java callback state

A successful upcall typically involves **multiple** owners:

| Resource | Who manages it? | When does it end? |
|---|---|---|
| Native upcall stub/trampoline | Arena passed to `upcallStub` | After unregister + all callbacks quiescent, `arena.close()` |
| Java MethodHandle / listener / bound receiver | Java reference graph, callback registration owner | Kept reachable until after the final callback |
| Native library/symbol lookup | `SymbolLookup.libraryLookup(..., arena)` or runtime loader | Do not unload while native code can still run or function pointers are still in use |
| Native user-data/context pointer | SDK or native application owner | Per allocator-specific destroy, after in-flight callbacks |
| Callback input pointer | Native side invoking the callback | Usually valid **only within a single callback invocation** or per SDK docs |
| Java data segment passed down to native | Arena that allocated the data | Lives long enough for the native operation/callback that may hold it |
| Native worker/timer | SDK/executor | Stopped and joined before destroying resources it accesses |

Closing the stub Arena does **not** free data buffers allocated by the SDK. Closing the data Arena does **not** automatically unregister the function pointer in the SDK. Clearing a Java listener reference does not automatically stop native callbacks. Each resource has its own lifecycle API and may depend on others.

When a callback receives a `MemorySegment` pointing to native data and `FunctionDescriptor` has `ADDRESS.withTargetLayout(T)`, the argument segment has a view corresponding to `T.byteSize()` per the type/ABI contract. **Do not retain the pointer view and read from it after the native SDK has freed the memory**: the global scope of a pointer argument does not guarantee physical memory lifetime; Java's size checks also do not prevent native use-after-free.

## 11. Describing callbacks with pointer parameters and context data

An SDK might provide:

```c
// Illustrative header. Context is void* managed by the application/SDK.
typedef void (*event_cb)(int code, const char *message, void *userData);
int sdk_register(event_cb callback, void *userData);
int sdk_unregister(event_cb callback, void *userData);
```

Rough FFM callback descriptor:

```java
FunctionDescriptor cbDesc = FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,  // const char *message
        ValueLayout.ADDRESS   // void *userData
);

// Java target: void callback(int, MemorySegment, MemorySegment)
```

This is an illustrative snippet, **not independently runnable**. Because plain `ADDRESS` does not specify the size of the memory pointed to, `message` is usually a **size=0** segment. Do not use `message.get(JAVA_BYTE,0)` without a contract on length and scope. If `message` is a NUL-terminated C string and the API guarantees a valid memory region, you can use the appropriate C/FFM string API with a defined lifetime/encoding. If the SDK also provides `size_t length`, you should use the bounded length and verify it before creating a view.

**Do not convert a Java Object directly into a C `void*`.** Java references are not native pointers. The simple approach for Java state is to bind a receiver into the `MethodHandle`, or manage a numeric registry/token with a synchronized mapping. If the C API requires `userData`, you can allocate a separate native context in an Arena and pass a valid address, but you must establish ownership and lifetime of the context independently of the stub.

### C callbacks returning a pointer or struct

A callback of type `const char *(*cb)(int)` requires `FunctionDescriptor.of(ADDRESS,JAVA_INT)` and a Java target returning `MemorySegment` (not `String`). The memory region that the pointer points to must remain alive long enough per the C contract; if a string is allocated in an `Arena.ofConfined` that closes before C reads it, the callback is still broken even if the MethodHandle signature matches.

A callback returning a `struct` by value requires an ABI-compatible group layout, explicit padding, and a matching Java MethodHandle carrier. Do not guess struct layouts; measure C `sizeof`/`offsetof` or use a binding generator.

## 12. Preventing Java exceptions from escaping an upcall

This risk is **different** from normal Java exceptions when Java calls Java. The `Linker.upcallStub` specification requires that the target MethodHandle **must not throw exceptions out**: if the target throws an exception during an upcall, **the JVM may terminate abruptly**. Do not write:

```java
// ANTI-PATTERN: DO NOT use directly as an upcall target.
static int badCompare(MemorySegment a, MemorySegment b) {
    throw new IllegalStateException("cannot compare");
}
```

Safe approach:

```java
// Illustrative snippet inside a state object.
private final AtomicReference<Throwable> failure =
        new AtomicReference<>();

int safeCompare(MemorySegment a, MemorySegment b) {
    try {
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0)
        );
    } catch (Throwable t) {
        failure.compareAndSet(null, t);
        return 0; // Fallback value matching the int carrier.
    }
}
```

You should not call `throw new RuntimeException` inside `catch` because that is still an exception escaping across the native boundary. If the C callback returns `void`, `catch` can record the error into shared state/logs and return normally. After the native downcall or from the control thread, the application reads `failure` and decides to:

- Report the error/exception **at the Java caller** once the callback has finished.
- Stop the SDK per protocol and release the stub after quiescence.
- If the C ABI has a return code for reporting errors, return a valid error code from the callback (not necessarily always 0).
- Do not destroy/free native pointers while the callback is mid-invocation.

**Note:** the comparator fallback `0` is only a way to isolate the JVM from exceptions. `qsort` may not produce valid output if the comparator failed; Java must treat the operation's result as failed and not use the partially sorted array.

`MethodHandles.catchException` can also wrap a MethodHandle with a handler, but you must verify the exact method type and the handler must also **not throw**. For this lesson, `try/catch(Throwable)` directly inside the target is the clearest approach.

## 13. Using Java receivers, closures, and MethodHandles properly

When a callback needs Java state, do not use a `static mutable global` as the sole mechanism for all sessions. A dedicated state class, bound to the MethodHandle, creates an independent callback for each registration:

```java
// Illustrative Java snippet; assumes descriptor has been created.
final class Counter {
    private final java.util.concurrent.atomic.AtomicInteger calls =
            new java.util.concurrent.atomic.AtomicInteger();

    int onCompare(MemorySegment a, MemorySegment b) {
        calls.incrementAndGet();
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0));
    }

    int calls() { return calls.get(); }
}

Counter state = new Counter();
MethodHandle unbound = MethodHandles.lookup().findVirtual(
        Counter.class, "onCompare", descriptor.toMethodType());

MethodHandle bound = unbound.bindTo(state);
// unbound.type() has receiver Counter at the first position.
// bound.type() only has (MemorySegment,MemorySegment)int.
```

This is a design snippet; in a real program you must add **catch(Throwable)** inside the target so `get`/callback errors do not escape. In the complete `QsortUpcallDemo` example, `CompareState` already does this.

**`bindTo` only retains the Java receiver**; it does not manage the lifecycle of the native registration. The native SDK still holds the function pointer; the Java owner must keep appropriate references to the stub, method handle, state, and Arena until after unsubscribing. Do not treat "the garbage collector sees the method handle" as proof that the native pointer is still valid after the arena closes.

Some common MethodHandle mistakes:

- Using `findStatic` to look up an instance method, or `findVirtual` for a static method → lookup exception.
- Forgetting to `bindTo` the receiver so the MethodHandle has an extra parameter beyond the descriptor.
- Java target uses `long` while the C prototype uses `int` (or vice versa) → wrong carrier/ABI.
- Java target `throws Exception` without actually handling it internally → fatal error when native invokes it.
- Native C retains the pointer after the Java owner scope ends → dangling stub.
- Using `MethodHandle.asType` to mask a wrong C prototype: Java adaptation cannot fix native calling conventions or pointer widths.

## 14. C ABI types, size_t, calling conventions, and FunctionDescriptor

`Linker.nativeLinker()` only knows the current ABI. The C header must be the source of truth for callbacks:

```c
// Two callbacks with DIFFERENT ABIs: do not share a descriptor.
int (*compare_ptr)(const void *, const void *);
void (*event_ptr)(int value);
```

| C signature | Suggested FunctionDescriptor under common ABIs | Java target carrier |
|---|---|---|
| `int f(int)` | `of(JAVA_INT, JAVA_INT)` | `(int)int` |
| `void f(int)` | `ofVoid(JAVA_INT)` | `(int)void` |
| `double f(double,double)` | `of(JAVA_DOUBLE,JAVA_DOUBLE,JAVA_DOUBLE)` | `(double,double)double` |
| `int f(const int*,const int*)` | `of(JAVA_INT,ADDRESS.withTargetLayout(JAVA_INT),ADDRESS.withTargetLayout(JAVA_INT))` | `(MemorySegment,MemorySegment)int` |
| `void f(void*)` | `ofVoid(ADDRESS)` | `(MemorySegment)void` |

The table is **illustrative**: C `int`, `long`, `size_t`, `wchar_t`, `bool`, and pointer size have ABI-specific mappings. `linker.canonicalLayouts()` provides canonical layouts for C type names supported by the linker. On typical Linux/x64, both `size_t` and `long` can be 8 bytes; on Windows/x64 `long` is typically 4 bytes even though pointers and `size_t` are typically 8. Do not infer ABI solely from Java primitive names.

`FunctionDescriptor.of(...)` interprets the **return layout first**, whereas `FunctionDescriptor.ofVoid(...)` only takes **argument layouts**. `ValueLayout.ADDRESS` should be used for native pointers, not replaced with `JAVA_LONG` just because the current machine uses 64-bit pointers; calling conventions and pointer representation still have their own rules.

**Important:** The Java linker can detect **incompatible** MethodHandle/descriptor pairs, but it cannot independently verify that a C function pointer or native symbol name actually has the signature you declared. C code casting a callback to the wrong function pointer type and calling it can crash the JVM or cause undefined behavior. For tricky ABIs or complex structs, generating bindings with `jextract` from the exact C header is usually more reliable than typing layouts by hand.

## 15. How do upcalls differ from JNI callbacks?

| Characteristic | JNI calling back into Java | FFM upcallStub |
|---|---|---|
| Call path | Native thread uses `JNIEnv*` and `Call<Type>Method` | Native code calls the function pointer created by `upcallStub` |
| Method description | `jmethodID`/`jobject` with JNI signature | Java `MethodHandle` + native `FunctionDescriptor` |
| Java reference lifecycle | `NewGlobalRef`/`DeleteGlobalRef` when retaining a Java object | Java state and MethodHandle must stay reachable; stub belongs to Arena |
| Native thread | Thread must attach to the JVM before using `JNIEnv*` | FFM runtime performs the upcall bridging step; still need to manage native workers and callback lifetimes |
| Exceptions | JNI pending exception belongs to the JNI thread | Do not let Java Throwable escape the upcall target; may cause JVM termination |
| Cleanup | Stop workers then delete JNI refs/SDK handles | Unregister/drain/join, close Arena, free native resources per owner |
| Common pitfalls | Using `JNIEnv*`/local JNI refs on the wrong thread | Wrong ABI descriptor or closing Arena while native still holds the function pointer |

FFM does **not** make native memory safety automatic. It changes certain representations and provides scope checks on the Java side, but if native code calls a freed address, Java's scope cannot resurrect the code stub.

Systems can use both JNI and FFM. Do not mix different handle/allocator release mechanisms: an FFM `upcallStub` is owned by an `Arena`, must not be `free`d by C, and a JNI `jobject` is not a C function pointer.

## 16. Common mistakes and how to fix them

| Mistake | Symptom/risk | Fix |
|---|---|---|
| `upcallStub` receives a target type different from the descriptor | `IllegalArgumentException` at creation | Use `descriptor.toMethodType()`, bind receiver properly |
| C callback returns `void` but Java descriptor returns `JAVA_INT` | Wrong C ABI; crash/undefined behavior | `FunctionDescriptor.ofVoid(...)` matching prototype |
| C pointer arbitrarily described with `JAVA_LONG` | Wrong calling convention/ABI | Use `ValueLayout.ADDRESS` |
| C `size_t` assumed to always be `JAVA_LONG` | Wrong on 32-bit ABI | Use `canonicalLayouts().get("size_t")`/generated binding |
| Forgetting `withTargetLayout` while callback calls `get` immediately | Pointer argument segment is typically 0 bytes long | Choose a bounded target layout per C contract, or handle bounds safely |
| Native passes NULL pointer while callback calls `get` at offset 0 | Invalid/null pointer access | Check `MemorySegment.NULL` or address, per C contract |
| Reading `const int*` after native has freed the data | Use-after-free | Only read within valid callback lifetime, copy if needed longer |
| Using `Arena.ofConfined` for callbacks from another SDK thread | Violates thread confinement/lifetime assumptions | Use a shared Arena and proper shutdown protocol |
| Closing Arena immediately after `register` | SDK still holds a freed function pointer | Unregister/drain/join before closing |
| Using `Arena.ofAuto` when only native holds the raw pointer | GC may reclaim stub when Java reachability is lost | Session owner + explicit `Arena.ofShared` |
| Keeping stubs for the whole JVM with `Arena.global()` for every request | Native stub/resource leak | Choose a closeable Arena per session |
| Java callback throws `RuntimeException` | JVM may terminate abruptly | Target `catch(Throwable)` itself and pass error via status/state |
| Java comparator uses `a - b` | Integer overflow, wrong ordering | `Integer.compare(a,b)` |
| Java callback calls stop/join from the worker itself | Deadlock/self-join | Callback only signals requestStop; control thread performs await |
| Unregister does not wait for in-flight callbacks yet Arena closes immediately | Use-after-free | Wait for SDK quiescence barrier before closing |
| Callback reads/writes the same Java object without locking | Data race | Appropriate atomic/queue/locking, independent of Arena |
| Finding `qsort` via `defaultLookup` fails | Native library lookup differs by OS/loader | Check native symbol/ABI, use libraryLookup when needed |
| FFM restricted method without native access | Warning or IllegalCallerException depending on JDK/options | `--enable-native-access=ALL-UNNAMED` or module name |
| Using `jdk.incubator.foreign` JDK17/18 tutorials for JDK22+ | Mismatched API/signature names | Use stable `java.lang.foreign` from JDK22+ |

### Minimum debugging checklist

1. Open the exact C header and write out the **exact callback typedef** first.
2. Check the OS/CPU ABI, canonical layouts, and type widths.
3. Print or check `descriptor.toMethodType()` against `target.type()`.
4. Confirm `upcallStub` uses an Arena that is still alive.
5. Ensure the native function pointer is only stored and invoked per contract.
6. Never let a Throwable escape the Java target.
7. If callbacks run on a native worker, determine stop/unregister/in-flight/join.
8. Close the Arena only after proof that the callback is no longer running.
9. For native data pointers, verify bounds, alignment, ownership, and lifetime.
10. When a crash occurs, combine native sanitizers and unit tests; do not rely solely on Java `try/catch`.

## 17. Exercises with answers

**Exercise 1 — determine the descriptor.** A C SDK requires `void (*cb)(int eventCode)`. The Java target is `static void onEvent(int code)`. Which descriptor is right?

**Answer:** `FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT)`, `MethodType.methodType(void.class,int.class)`. `FunctionDescriptor.of(JAVA_INT,JAVA_INT)` would have the wrong return type.

**Exercise 2 — two int pointers.** C `int (*cmp)(const int*, const int*)`. If the Java target is `int compare(int a,int b)`, can it be used directly with `ADDRESS,ADDRESS`?

**Answer:** No. The two C parameters are pointers, so the MethodHandle carriers must be `MemorySegment,MemorySegment`. Use `ADDRESS.withTargetLayout(JAVA_INT)` to read each value at offset 0, then `Integer.compare`.

**Exercise 3 — Arena lifetime.** Java calls `register(cb)` and closes `Arena.ofConfined()` when register returns; the SDK stores the callback and will invoke it after 3 seconds. Is this safe?

**Answer:** No. The SDK still holds the raw function pointer; the arena has already freed the stub. Use an Arena that lives for the registration/session and close only after unregister + in-flight callback quiescence. If callbacks may arrive from a foreign thread, prefer `Arena.ofShared()`.

**Exercise 4 — inspecting the segment.** `upcallStub` returns a `MemorySegment` with `byteSize()==0`. Should you call `reinterpret(4)` then `get(JAVA_INT,0)` to read the callback's return value?

**Answer:** No. The stub contains the address of **native trampoline code**, not a data segment. The return value comes from the Java MethodHandle when native code invokes the function pointer, not from bytes that can be `get` from the stub.

**Exercise 5 — exceptions.** A Java comparator throws `IllegalArgumentException` while `qsort` invokes it through the function pointer. Can it be caught with `try/catch` around `qsort.invokeExact` in Java?

**Answer:** You must not rely on that. The upcall specification warns that an exception escaping the target can terminate the JVM abruptly. Catch `Throwable` directly inside the callback, record the error in Java state or status, and handle it after the downcall.

**Exercise 6 — native worker.** SDK `unregister(cb)` only prevents new callbacks, while running callbacks have not yet returned. Is it safe to call `arena.close()` immediately?

**Answer:** Not yet. You must wait for in-flight callbacks to complete or receive an SDK quiescence acknowledgement before closing the stub Arena. If workers/queues hold the pointer, stop/join/drain them as well.

**Exercise 7 — ABI.** C `qsort` runs on an ABI with a 4-byte `size_t`. Java hard-codes `JAVA_LONG` for both `size_t` parameters. What is the risk?

**Answer:** The downcall descriptor has the wrong ABI. You must use the canonical `size_t` layout for the platform, with the matching Java MethodHandle carrier (e.g., `JAVA_INT` when 4 bytes), and the right number of args. You cannot just change the literal value from `6L` to `6` if the descriptor has not been fixed.

**Exercise 8 — state.** A C SDK needs to hold a callback long-term while multiple Java sessions are active concurrently. Is it good to use one static `AtomicInteger last` and one `Arena.global()` for all sessions?

**Answer:** It easily mixes state across sessions and never releases native stubs. Design separate state/MethodHandle per registration, keep a closeable shared Arena per session, and unregister + join before closing.

**Exercise 9 — pointer target.** A C callback receives `const uint8_t* bytes` and `size_t length`. Can you read 100 bytes simply because Java receives `MemorySegment bytes`?

**Answer:** No. You must check the `length` provided by C, the ABI of `size_t`, NULL pointers, native buffer lifetime, and bounds when creating a view/copy. `ADDRESS` does not automatically know how many bytes are actually valid.

**Exercise 10 — final ordering.** An SDK has stopped callbacks and joined all workers, and now you want to close the Arena and unload the shared library. What needs to be considered?

**Answer:** You must be certain there are no in-flight native calls, pending callback/function pointer invocations, or data pointers from the library. After quiescence, close the Arena to release the stub and lookup/library per ownership, then unload dependencies per API. Do not call `dlclose` while code in the library is still executing.

## 18. Summary and references

**Formula to remember:**

```java
// Illustrates the three inputs; not a standalone runnable file.
MemorySegment callback = linker.upcallStub(
        targetMethodHandle,  // correct Java carrier types
        functionDescriptor, // correct native C ABI
        arena               // correct lifetime
);
```

Every component matters:

- **`FunctionDescriptor`** describes the native callback prototype: return type, parameters, and ABI-accurate pointer/target layouts.
- **`MethodHandle`** represents the Java logic executed when native calls it, with a `MethodType` matching the descriptor and never throwing `Throwable` out.
- **`Arena.ofConfined()`** is suitable for **synchronous callbacks scoped to the downcall** that finish before closing.
- **`Arena.ofShared()`** is suitable for callbacks **retained long-term or potentially arriving from foreign threads**, though you still must **unregister, drain/join, and then close**.
- **`MemorySegment` stub size 0** represents a function address, not data to `get/set`.
- **FFM cannot rescue an expired native function pointer**. A pointer still stored in C after the Arena closes can cause a JVM crash when invoked.

### Official documentation

- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 25 — Linker: `upcallStub`, qsort callback, safety/exceptions, and ABI](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 25 — Upcalls: Passing Java Code as a Function Pointer](https://docs.oracle.com/en/java/javase/25/core/upcalls-passing-java-code-function-pointer-foreign-function.html)
- [Oracle Java SE 25 — FunctionDescriptor, `of`/`ofVoid`/`toMethodType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle Java SE 25 — Arena: confined/shared/automatic/global scopes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 25 — ValueLayout/AddressLayout, `withTargetLayout`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Oracle Java SE 24 — Restricted methods and `--enable-native-access`](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html)
- [Oracle Java SE 22 — SegmentAllocator and `allocateFrom`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
