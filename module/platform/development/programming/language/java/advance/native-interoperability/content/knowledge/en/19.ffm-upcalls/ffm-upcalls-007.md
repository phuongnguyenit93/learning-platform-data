# Callbacks from native threads and access limits on segments belonging to a thread-confined Arena

## 1. The core problem: a native callback can run on a different thread

The Foreign Function & Memory API (FFM) allows Java to **call C functions** (*downcall*) and allows C to **call back into Java** (*upcall*). An upcall stub is a C ABI function pointer, created with `Linker.upcallStub(...)` so that native code can invoke a Java `MethodHandle`.

The problem arises when a native library creates its own worker thread (for example `pthread_create` on Linux/macOS or `CreateThread` on Windows) and then invokes the callback pointer on **that worker thread**. In this case, the callback **does not run on the original Java thread that created the arena**, even though it is within the same application and the same JVM.

Logic example:

~~~text
Java thread MAIN
   |
   +-- Arena.ofConfined() --> MemorySegment DATA (owner = MAIN)
   |
   +-- Linker.upcallStub(targetJava, ..., Arena.ofShared())
   |                                     |
   |                                     +--> Function pointer CALLBACK
   |
   +-- FFM downcall invoke_native_thread(CALLBACK)
           |
           v
      C creates an OS worker thread
           |
           +--> CALLBACK(...)
                  |
                  v
             Java target runs on worker
                  |
                  +--> DATA.get(JAVA_INT, 0)
                             |
                             +--> WrongThreadException
                                  because DATA belongs to MAIN's
                                  confined arena, not the worker
~~~

**Key takeaway:** Allowing an upcall back into Java **does not make a `MemorySegment` from `Arena.ofConfined()` shareable across threads**. Thread-confinement is a rule of the **scope attached to the segment**, independent of whether the calling code originates from Java, JNI, or FFM.

The standard fix is to **use `Arena.ofShared()` for data that genuinely needs to be accessed from a native callback thread**, or to **copy the required values on the owner thread before handing off to the callback**. In particular, **the arena managing the upcall stub** and **the arena managing the data accessed by the callback** are two lifetime relationships that can be completely different.

This article focuses on **JDK 22+**, where `java.lang.foreign` has been standardized (JEP 454). On JDK 17, the following examples do not compile verbatim because the FFM API was still in the incubator stage at that time.

### Objectives

- Understand the journey Java → native downcall → OS worker → Java upcall and which threads are actually involved.
- Create `Linker.upcallStub`, `FunctionDescriptor`, and `MethodHandle` with the correct ABI.
- Distinguish between **the thread running the callback**, **the thread owning the confined arena**, and **the scope/lifetime of the upcall stub**.
- Explain why a confined segment still throws `WrongThreadException` even though the callback can be executed by the JVM.
- Build a **Java 22+ and C11** example with a native worker thread on Linux, macOS, and Windows x64.
- Read the exact stdout when a direct callback succeeds, a worker callback with a confined segment is rejected, and a worker callback with a shared segment succeeds.
- Avoid uncaught exceptions in upcalls, use-after-close, overdue asynchronous callbacks, and deadlocks between native/Java threads.
- Choose between a shared arena, copying data, and a queue that dispatches work back to the owner thread depending on the requirements.

## 2. Two call directions that must be distinguished

FFM has two communication directions:

| Direction | Who calls whom? | Key API | Execution thread |
| --- | --- | --- | --- |
| **Downcall** | Java → native function | `Linker.downcallHandle` and `MethodHandle.invokeExact` | Usually starts on the Java thread calling the downcall |
| **Upcall** | Native function → Java target | `Linker.upcallStub` and C function pointer | **The actual native thread calling the function pointer**, which may differ from the initiating thread |

Example C signatures:

~~~c
#include <stdint.h>

typedef int32_t (*callback_fn)(int32_t value);

int32_t invoke_direct(callback_fn callback, int32_t value);
int32_t invoke_native_thread(callback_fn callback, int32_t value);
~~~

These are **illustrative declarations**; section 7 will provide the complete C file.

- `invoke_direct` calls `callback(value)` immediately on the thread executing the C function, typically the original Java thread that entered the downcall.
- `invoke_native_thread` creates a **new OS thread**, has that thread call `callback(value)`, waits for the thread to finish via join, and only then returns the result.
- Both take the same **function pointer** type and the same `int32_t`; the difference is **the thread path**.

This is why a callback tested successfully in a synchronous `qsort` example **does not prove** that the callback will be able to access a confined segment if a native library invokes it from an independent worker thread.

### 2.1. A callback is a function pointer, not a Java native method

In FFM, Java creates a function pointer:

~~~java
MemorySegment stub = linker.upcallStub(
        targetMethodHandle, callbackDescriptor, arena);
~~~

The stub is passed into native C as a pointer argument via `ValueLayout.ADDRESS`. C calls it using normal function syntax, without needing a corresponding `native` Java method declaration, without calling `RegisterNatives`, and without implicit `JNIEnv *`/`jobject` parameters in the C callback signature.

Do not confuse an FFM callback prototype:

~~~c
typedef int32_t (*callback_fn)(int32_t value);
~~~

with a JNI native method:

~~~c
/* A JNI native method receives hidden JNIEnv* and jobject/jclass parameters. */
JNIEXPORT jint JNICALL Java_Package_Class_method(
        JNIEnv *env, jobject self, jint value);
~~~

A wrong `FunctionDescriptor` for a C function pointer can cause severe ABI errors, including a JVM crash. Only use types/ABIs verified to match the platform.

## 3. Three objects with three different responsibilities

**First — `MethodHandle target`**: specifies **which Java code** will run when native code calls the callback. The target can have an additional Java object or `MemorySegment` bound to it. The target itself does not determine the thread ownership of the captured memory region.

**Second — `MemorySegment stub`**: the result of `Linker.upcallStub(target, descriptor, arena)`. This is a **zero-sized segment** whose address is the native function pointer. The stub has a lifetime determined by the arena passed into `upcallStub`.

**Third — `MemorySegment data`**: the actual data region that the Java target may read/write. Data can be allocated from **a different arena**, with its own confined/shared rules.

Example:

~~~java
try (Arena stubArena = Arena.ofShared();
     Arena dataArena = Arena.ofConfined()) {

    MemorySegment data = dataArena.allocate(ValueLayout.JAVA_INT);

    MethodHandle target = /* Java MethodHandle capturing data */;
    MemorySegment stub = Linker.nativeLinker().upcallStub(
            target,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
            stubArena);

    // STUB belongs to the shared arena.
    // DATA belongs to the confined arena of the current Java thread.
}
~~~

This is **Java pseudocode** because the MethodHandle creation expression is abbreviated; it is not a standalone source file.

**Mistake to avoid:** "Since `Arena.ofShared()` was used when creating the upcall stub, every `MemorySegment` accessed by the target is shared." Incorrect. `stubArena` only manages the **stub resource**. `dataArena` remains confined, and only the owner thread is allowed to access `data`.

Conversely, a stub created in a confined arena **is also not a good choice** when you want to hand a function pointer to a native worker that does not share the same owner. In the hands-on example, we use a **shared arena for both the stub and the FFM library lookup**, so that an error on the function pointer itself is not confused with the confined data error we want to demonstrate.

## 4. Confined arena: the owner thread is a mandatory condition

`Arena.ofConfined()` creates an arena with an **owner thread**, usually the thread calling that factory method. Every segment allocated from this arena has thread-confinement:

~~~java
Arena arena = Arena.ofConfined();
MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
~~~

In the short example above, assuming it runs on `main`, **only the owner thread** can use memory access methods on `segment` and close the arena.

Example of valid access:

~~~java
segment.set(ValueLayout.JAVA_INT, 0L, 32);
int value = segment.get(ValueLayout.JAVA_INT, 0L);
~~~

Example of invalid access:

~~~java
Thread worker = new Thread(() -> {
    segment.get(ValueLayout.JAVA_INT, 0L);
});
worker.start();
~~~

This is an **illustrative code snippet**, not a complete program; if the exception is not caught, the worker may print a stack trace. The worker thread does not own the arena, so access will be rejected with `WrongThreadException` while the segment/scope is still alive.

A native thread entering Java via an upcall is also **the thread executing the callback**, and does not automatically become the owner of a confined arena created on `main`. This remains true even if the callback uses a Java object or record as a bridge to that segment.

### 4.1. `WrongThreadException` differs from `IllegalStateException`

| Issue | Typical outcome | Condition |
| --- | --- | --- |
| Segment alive, correct owner thread | Access succeeds if bounds/alignment are valid | Confined and current thread = owner |
| Segment alive, **wrong thread** | `WrongThreadException` | Confined and current thread differs from owner |
| Arena already closed | `IllegalStateException` | Scope is no longer alive |
| Access exceeds `byteSize()` | `IndexOutOfBoundsException` | Offset/length out of bounds |
| Misaligned access | `IllegalArgumentException` | Layout/address alignment not satisfied |

**`isAlive() == true` does not imply that the current thread is permitted to access.** Lifetime (alive/dead) and confinement (which thread) are **two separate check axes**. When both the scope has expired and the thread is wrong, you should not rely on a specific exception ordering; the design must guarantee both conditions before use.

### 4.2. `Arena.ofShared()` is not automatically thread-safe

`Arena.ofShared()` allows threads to access segments it allocates and allows closing from multiple threads according to the API contract. However:

- It does not automatically lock when two threads read/write the same memory location.
- It does not turn a `get` + `set` operation into an atomic update.
- It does not automatically keep data alive if the owner closes the arena too early.
- It does not guarantee that the C callback function is thread-safe.
- It does not resolve deadlocks between a native worker and a Java thread.

To read shared memory correctly, you still need to distinguish between **read-only sharing**, **data published via synchronization**, or **atomic access** via `VarHandle`/locking.

## 5. How are native threads handled by the JVM during an upcall?

In the FFM execution path on **HotSpot/OpenJDK**, an OS thread created by a native library when calling an upcall stub may **not yet be a Java thread attached to the JVM**. The FFM runtime handles attaching that thread to the JVM to run the Java target, and the HotSpot implementation describes a mechanism that attaches in **daemon** mode and detaches when the native thread terminates.

Note on the scope of this conclusion:

- This is an **FFM implementation detail of HotSpot/OpenJDK**, not a guarantee that every other JVM will use the same daemon policy.
- You do not need to manually call `AttachCurrentThread` just to make an FFM callback example run with an upcall stub on HotSpot. Do not arbitrarily call `DetachCurrentThread` from a Java callback.
- If you **explicitly write JNI code** on a native worker, that code's JNI attach/detach rules are a separate topic: `JNIEnv *` is thread-local and `AttachCurrentThread` is not synonymous with `AttachCurrentThreadAsDaemon`.
- The fact that the VM can execute the Java callback **does not transfer ownership of a confined arena to the new thread**.
- A native worker may have a different context class loader than the initiating Java thread; do not assume the callback will find application classes by name through the thread's context class loader.
- `ThreadLocal`, thread name, interrupts, and Java thread context may differ from Java main; do not use them as implicit assumptions if the callback needs accurate data.

**Safe approach:** the target MethodHandle is bound to Java code known at the time the upcall stub is created; pass data using primitive types, Java objects safe for sharing, or shared segments with proper lifecycle/synchronization.

## 6. An upcall stub must not let exceptions escape

JDK 22 `Linker.upcallStub` specifies that the target **must not throw exceptions out of the stub**. If an exception escapes the target MethodHandle across the native callback boundary, **the JVM may terminate abruptly**; in fact, the javadoc warns that the JVM will terminate abruptly.

Therefore, do **not** write:

~~~java
static int unsafeCallback(MemorySegment confinedData, int x) {
    return confinedData.get(ValueLayout.JAVA_INT, 0L) + x;
    // If the native thread is not the owner -> WrongThreadException
    // will escape the Java callback: may cause the VM to terminate.
}
~~~

This is **a static Java method illustrating incorrect behavior**, not called directly in the demo.

Instead, **intercept errors inside the target and convert them into a valid C result**:

~~~java
private static final int WRONG_THREAD = -700;
private static final int CALLBACK_ERROR = -701;

static int safeCallback(MemorySegment data, int x) {
    try {
        return data.get(ValueLayout.JAVA_INT, 0L) + x;
    } catch (WrongThreadException ex) {
        return WRONG_THREAD;
    } catch (Throwable unexpected) {
        // Never allow a Throwable to escape across the native boundary.
        // In production, log diagnostics through a safe channel.
        return CALLBACK_ERROR;
    }
}
~~~

This is a Java snippet; `MemorySegment` and `ValueLayout` need to be imported, and both constants are defined in the class. `WrongThreadException` belongs to `java.lang` in JDK 22, so it does not need to be imported.

For a C callback function returning `int32_t`, the two negative sentinels above are the demo's way of **reporting errors across the ABI**. **Do not use sentinels that collide with the valid result range in production**; you can design an additional status code, an output parameter, or a struct-shaped result, or record the error state in a thread-safe object for Java to read after the downcall.

Catching `Throwable` is a **last-resort safety net for the demo**. In real systems, design handling for `Error`/out-of-memory carefully and avoid performing complex Java operations during critical failures. The goal is to prevent an exception from accidentally crossing the function-pointer ABI.

## 7. Complete example: C creates a worker thread and calls a Java callback

The hands-on program contains:

1. A C library exporting two functions: `invoke_direct` and `invoke_native_thread`.
2. Both functions take the same callback type: `int32_t (*)(int32_t)`.
3. Java creates one confined data segment and one shared data segment; both store `32`.
4. Java creates **two upcall stubs, both with shared lifetimes**:
   - Stub A is bound to the confined data.
   - Stub B is bound to the shared data.
5. Java makes three calls:
   - `invoke_direct(stubA, 10)`: runs on the Java main thread, reads confined data validly → `42`.
   - `invoke_native_thread(stubA, 10)`: worker thread reads confined data → callback catches `WrongThreadException` and returns `-700`.
   - `invoke_native_thread(stubB, 10)`: worker thread reads shared data → `42`.

Crucially, **C waits for the worker to finish via join before returning**. Because of this, Java can close the arenas after the downcall completes without worrying about the callback still occurring later.

### 7.1. Directory structure

~~~text
native-thread-ffm/
  native_thread_callback.c
  NativeThreadCallbackDemo.java

After building:
  libthread_callback.so       (Linux)
  libthread_callback.dylib    (macOS)
  thread_callback.dll         (Windows)
  NativeThreadCallbackDemo.class
~~~

Choose one operating system to build on; there is no need to generate all three library files on the same machine.

### 7.2. Complete C file: `native_thread_callback.c`

~~~c
#include <stdint.h>
#include <stdlib.h>

#if defined(_WIN32)
    #include <windows.h>
    #define EXPORT __declspec(dllexport)
#else
    #include <pthread.h>
    #define EXPORT __attribute__((visibility("default")))
#endif

/*
 * Demo uses only common x64/ARM64 ABIs.
 * int32_t = Java ValueLayout.JAVA_INT (carrier int).
 * Callback does NOT have a hidden JNIEnv* parameter.
 */
typedef int32_t (*callback_fn)(int32_t);

typedef struct {
    callback_fn callback;
    int32_t input;
    int32_t result;
} Request;

static void run_callback(Request *request) {
    request->result = request->callback(request->input);
}

#if defined(_WIN32)

static DWORD WINAPI thread_entry(LPVOID argument) {
    run_callback((Request *) argument);
    return 0;
}

#else

static void *thread_entry(void *argument) {
    run_callback((Request *) argument);
    return NULL;
}

#endif

/* Call the callback directly on the thread calling into C. */
EXPORT int32_t invoke_direct(
        callback_fn callback, int32_t input) {
    if (callback == NULL) {
        return -500;
    }
    return callback(input);
}

/*
 * Create an OS worker thread, let the worker invoke the callback,
 * and JOIN the worker before returning to guarantee lifetime.
 */
EXPORT int32_t invoke_native_thread(
        callback_fn callback, int32_t input) {
    if (callback == NULL) {
        return -500;
    }

    Request request = {callback, input, -502};

#if defined(_WIN32)
    HANDLE thread = CreateThread(
            NULL, 0, thread_entry, &request, 0, NULL);

    if (thread == NULL) {
        return -501;  /* Failed to create worker. */
    }

    DWORD waitResult = WaitForSingleObject(thread, INFINITE);
    if (waitResult != WAIT_OBJECT_0) {
        /* Cannot safely return while the thread may still
           hold a pointer to request on the stack. */
        abort();
    }

    CloseHandle(thread);
#else
    pthread_t thread;

    if (pthread_create(
            &thread, NULL, thread_entry, &request) != 0) {
        return -501;  /* Failed to create worker. */
    }

    if (pthread_join(thread, NULL) != 0) {
        /* Abnormal condition: do not return while the worker
           may continue using request on the stack. */
        abort();
    }
#endif

    return request.result;
}
~~~

#### Explanation of decisions in C

- `EXPORT` ensures the symbols are exported from the native library: on Windows it uses `__declspec(dllexport)`, and on Linux/macOS it uses the standard GCC/Clang visibility attribute.
- `int32_t` has a fixed 32-bit width, conveniently matching `ValueLayout.JAVA_INT`.
- `callback_fn` has **exactly one `int32_t` parameter** and returns `int32_t`; this is the ABI contract for the upcall stub.
- `invoke_direct` **does not create a thread**: the callback typically runs on the same Java thread that made the downcall.
- `invoke_native_thread` creates a real worker, passing the address of `Request` on the C stack. It guarantees **joining before returning** so there is no dangling pointer to `request`.
- The native worker receives neither `JavaVM *` nor `JNIEnv *`; the demo uses an **FFM upcall stub**, not a manual native JNI callback.
- `-500` is a null callback pointer error; `-501` is a thread creation error; `-502` is only an initial value not returned when the worker completes normally. These negative codes are kept distinct from `-700` (wrong thread) and `-701` (callback exception) on the Java side.
- The `abort()` branches when join/wait fails are a **fail-fast choice for the demo** because it is not safe to return and free a stack frame that the worker might still be using. Production applications should have more appropriate worker lifecycles and error recovery.
- The example uses a **64-bit JDK and native compiler of the same architecture**, to avoid Windows 32-bit calling convention differences.

**`jni.h` is not needed in this C file**, because the library uses the normal C ABI and is called via FFM. There is no `JNI_OnLoad` or `Java_*` method.

### 7.3. Complete Java file: `NativeThreadCallbackDemo.java`

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

public final class NativeThreadCallbackDemo {
    private static final int WRONG_THREAD = -700;
    private static final int CALLBACK_ERROR = -701;

    private NativeThreadCallbackDemo() {
    }

    /*
     * Target MethodHandle will have the data parameter bound in advance,
     * so C only has to pass a single int32_t.
     *
     * DO NOT let exceptions escape from an FFM upcall!
     */
    private static int readMemory(MemorySegment data, int increment) {
        try {
            int base = data.get(ValueLayout.JAVA_INT, 0L);
            return base + increment;
        } catch (WrongThreadException ex) {
            return WRONG_THREAD;
        } catch (Throwable ex) {
            return CALLBACK_ERROR;
        }
    }

    private static MethodHandle boundCallback(MemorySegment data)
            throws ReflectiveOperationException {
        MethodHandle target = MethodHandles.lookup().findStatic(
                NativeThreadCallbackDemo.class,
                "readMemory",
                MethodType.methodType(
                        int.class, MemorySegment.class, int.class));

        // (MemorySegment, int) -> int
        // After binding: (int) -> int, matching callback_fn in C.
        return MethodHandles.insertArguments(target, 0, data);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        FunctionDescriptor callbackDescriptor =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor invokeDescriptor =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT);

        Path path = Path.of(
                System.mapLibraryName("thread_callback"))
                .toAbsolutePath();

        /*
         * The shared arena allocates both stubs and shared data.
         * The confined arena allocates data ONLY for main.
         */
        try (Arena sharedArena = Arena.ofShared();
             Arena confinedArena = Arena.ofConfined()) {

            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, sharedArena);

            MethodHandle direct = linker.downcallHandle(
                    library.find("invoke_direct").orElseThrow(),
                    invokeDescriptor);

            MethodHandle threaded = linker.downcallHandle(
                    library.find("invoke_native_thread").orElseThrow(),
                    invokeDescriptor);

            MemorySegment confinedData =
                    confinedArena.allocate(ValueLayout.JAVA_INT);

            MemorySegment sharedData =
                    sharedArena.allocate(ValueLayout.JAVA_INT);

            confinedData.set(ValueLayout.JAVA_INT, 0L, 32);
            sharedData.set(ValueLayout.JAVA_INT, 0L, 32);

            /*
             * Both STUBS belong to sharedArena.
             * The difference lies only in the DATA captured by the target.
             */
            MemorySegment confinedStub = linker.upcallStub(
                    boundCallback(confinedData),
                    callbackDescriptor, sharedArena);

            MemorySegment sharedStub = linker.upcallStub(
                    boundCallback(sharedData),
                    callbackDescriptor, sharedArena);

            int onMainThread =
                    (int) direct.invokeExact(confinedStub, 10);

            int onWorkerConfined =
                    (int) threaded.invokeExact(confinedStub, 10);

            int onWorkerShared =
                    (int) threaded.invokeExact(sharedStub, 10);

            if (onMainThread != 42
                    || onWorkerConfined != WRONG_THREAD
                    || onWorkerShared != 42) {
                throw new IllegalStateException(
                        "Unexpected callback result");
            }

            System.out.println("direct confined=42");
            System.out.println(
                    "native thread confined=WrongThreadException caught");
            System.out.println("native thread shared=42");
        }
    }
}
~~~

#### Key points in Java

**A. Upcall/downcall signature pair**

`callbackDescriptor`:

~~~text
(int) -> int

C callback: int32_t (*callback_fn)(int32_t)
FFM callback FunctionDescriptor:
    of(JAVA_INT, JAVA_INT)
Java target after binding:
    (int) -> int
~~~

`invokeDescriptor`:

~~~text
(MemorySegment, int) -> int

C function: int32_t invoke_native_thread(
    callback_fn callback, int32_t input)

FFM FunctionDescriptor:
    of(JAVA_INT, ADDRESS, JAVA_INT)
Java invokeExact:
    (int) threaded.invokeExact(stub, 10)
~~~

**B. Two intentionally distinct arenas**

- `sharedArena` allocates the upcall stubs and `sharedData`, and also manages the library lookup. The native thread is allowed to use **sharedData** while the scope is alive.
- `confinedArena` allocates `confinedData` on the Java main thread. Calling `data.get(...)` from the native worker (via the Java target) will be rejected with `WrongThreadException`.
- The stub bound to `confinedData` is still created from **sharedArena**. This allows observing the exact issue of **data confinement**, without mixing it up with an error caused by a function pointer having a confined scope.

**C. `MethodHandles.insertArguments` does not copy memory**

`boundCallback(confinedData)` creates a `(int) -> int` target, but it only binds the **Java reference to `confinedData`**. It does not copy bytes, does not change the owner thread, and does not convert a confined scope into a shared scope.

**D. Why doesn't the error crash the JVM?**

`readMemory` **catches `WrongThreadException` right inside the callback** and returns `-700` per the ABI. No Java exception crosses the native function pointer. The demo also has a fallback `catch (Throwable)` returning `-701` for unexpected errors, instead of letting an exception fly through the upcall stub.

**E. Why is it safe to close the arenas at the end of the `try` block?**

C has **joined the native worker before returning from the downcall**. Thus, when Java finishes the final `threaded.invokeExact(...)` call, no worker still holds the example's upcall pointer. Both arenas are closed upon exiting `try`; no one is still calling the stub or accessing the segments.

## 8. Compiling and running across platforms

### 8.1. Preparation

- Install **JDK 22 or newer**. Check that `javac -version` and `java -version` both point to that JDK.
- Use a compiler supporting C11 with the same CPU architecture as the JVM.
- Run commands from the directory containing `NativeThreadCallbackDemo.java` and `native_thread_callback.c`.
- Neither `javac -h` nor `jni.h` is needed because the C file has no JNI native methods.

Compile Java:

~~~bash
javac NativeThreadCallbackDemo.java
~~~

### 8.2. Linux x64 / ARM64 (GCC or Clang)

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared -pthread \
  native_thread_callback.c -o libthread_callback.so
~~~

`-pthread` enables the configuration needed for `pthread_create`/`pthread_join`. On modern Linux distributions, pthread may reside in libc, but using this flag is still recommended for an explicit build.

### 8.3. macOS x64 / ARM64 (Clang)

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib -pthread \
  native_thread_callback.c -o libthread_callback.dylib
~~~

### 8.4. Windows x64 (Visual Studio Developer Command Prompt)

~~~bat
cl /nologo /W4 /LD native_thread_callback.c /link /OUT:thread_callback.dll
~~~

The `#if defined(_WIN32)` branch uses `CreateThread` and `WaitForSingleObject` from Win32. Run in **x64 Native Tools Command Prompt**, using a 64-bit JDK. MSVC C supports the `int32_t` definition in `stdint.h`.

### 8.5. Running

Linux/macOS:

~~~bash
java --enable-native-access=ALL-UNNAMED NativeThreadCallbackDemo
~~~

Windows:

~~~bat
java --enable-native-access=ALL-UNNAMED NativeThreadCallbackDemo
~~~

`--enable-native-access=ALL-UNNAMED` grants native access to the classpath program, which is required for **restricted FFM methods** such as `libraryLookup`, `downcallHandle`, and `upcallStub`. JDK 22 does not require `--enable-preview`.

The shared library file must be in the **current working directory**, because `Path.of(System.mapLibraryName("thread_callback")).toAbsolutePath()` constructs an absolute path based on the working directory. The example uses FFM `libraryLookup(Path, Arena)`, so it does not need to rely on `-Djava.library.path` to locate the file like JNI's `System.loadLibrary`.

### 8.6. Exact stdout when running successfully

~~~text
direct confined=42
native thread confined=WrongThreadException caught
native thread shared=42
~~~

Explanation:

1. `direct` calls C synchronously and C invokes the stub immediately on the Java main thread; `confinedData.get` is allowed, reading `32 + 10 = 42`.
2. `threaded` creates a native OS thread; the callback runs on the new thread and tries to read `confinedData` owned by Java main; Java FFM throws `WrongThreadException`, the target catches it and returns `-700`; main prints the "caught" line.
3. Next, the native worker reads `sharedData` belonging to `Arena.ofShared()`, so it gets `32 + 10 = 42`; C joins the worker before returning.
4. All output is **printed in Java main after the downcalls return**, avoiding non-deterministic stdout ordering from running across multiple threads.

If the environment does not support creating OS threads or the C/Java ABI differs from expectations, the program will **not** print the three lines above and will take the error branch instead. Do not treat debug stdout from an arbitrary error as a successful result.

## 9. Why not create a confined upcall stub for the worker?

A developer might write:

~~~java
try (Arena confined = Arena.ofConfined()) {
    MemorySegment stub = linker.upcallStub(
            target, callbackDescriptor, confined);

    // Pass the stub to a self-created C worker thread...
}
~~~

This is an illustrative snippet, missing the `linker` and `target` variables; **do not use it for the worker demo**.

`Linker.upcallStub` takes an Arena to manage **the lifetime of the function pointer**. The JDK 22 Javadoc specifies that creating a stub with a confined arena from a non-owner thread can throw `WrongThreadException`; the stub is also no longer valid after that arena closes.

Therefore, for a callback used from a native worker thread, you should use a **shared arena with a sufficiently long lifetime** for the function pointer, and ensure the worker finishes before closing. This avoids accidental dependencies on the confinement/closure of the upcall stub itself.

**However, switching the stub to shared is not enough to fix a target accessing confined data.** You must change the ownership of the data or how the data is passed.

## 10. Two correct ways to fix the confined data error

### 10.1. Option A: allocate the data in `Arena.ofShared()`

This is the approach applied in the section 7 demo.

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_INT);
    value.set(ValueLayout.JAVA_INT, 0L, 32);

    MethodHandle target = /* bind value to the callback */;
    MemorySegment stub = linker.upcallStub(
            target, descriptor, arena);

    // The C worker is allowed to access value via the callback,
    // as long as it is alive and properly synchronized.
}
~~~

This is **Java pseudocode** (the MethodHandle creation part is abbreviated).

Additional management required:

- **Do not close the arena** while any callback could still occur.
- If Java main and the native callback concurrently **write/read the same data**, use synchronization or appropriate `VarHandle` access modes, rather than relying solely on being "shared".
- If C has multiple worker threads, clearly define the lifecycle and in-flight callback count.
- If C stores the pointer in a global variable, there must be an `unregister/stop` API and acknowledgment before `arena.close()`.
- A shared arena makes **cross-thread access permission** valid, but does not verify that the callback protocol is correct.

### 10.2. Option B: copy values to Java primitives before the upcall

If the callback only needs a few scalars, a safer and easier-to-control approach is to **read from the confined segment on the owner thread first**, and then bind the **primitive values** into the target:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandle;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// This snippet runs inside a method on the owner thread.
int base = confinedData.get(ValueLayout.JAVA_INT, 0L);

MethodHandle add = MethodHandles.lookup().findStatic(
        MyCallbacks.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));

// static int add(int base, int increment) { return base + increment; }
MethodHandle target = MethodHandles.insertArguments(add, 0, base);

// target only carries a Java int and does not hold the confined segment.
~~~

This is an **illustrative snippet**, and `MyCallbacks` is just a hypothetical class name. In real code, define the `add` method and create the upcall stub using an `Arena.ofShared()` that lives long enough for the native callback.

Advantages:

- The native worker callback does not read confined data.
- Does not unnecessarily open up native memory sharing.
- The primitive data is **copied** at bind time (a snapshot), so subsequent changes to the confined segment **do not automatically update the callback**.
- Reduces the risk of temporal bounds/close errors on native data when callbacks are asynchronous.

If the callback needs large amounts of data or bidirectional updates, copying everything each time can be costly; consider a shared arena or a message queue.

### 10.3. Option C: dispatch work back to the owner thread

If it is strictly required to process a confined segment **on the exact owner Java thread**, the callback on the native worker should not use the segment directly. Instead:

~~~text
Native worker calls upcall
       |
       v
Java callback receives event/primitive/immutable payload
       |
       v
Pushes task onto the owner's thread-safe queue
       |
       v
Callback returns status quickly to C (do not wait for owner if there is a wait cycle)
       |
       v
Java owner thread processes the queue
       |
       v
Owner reads/writes the confined segment validly
~~~

This is a **protocol diagram**, not a built-in FFM API. Java's `BlockingQueue` or an event loop can be used to coordinate, but **lifecycle and backpressure** must be designed appropriately.

**Deadlock warning:** if the Java owner is blocked inside `invoke_native_thread` waiting for `pthread_join`, while the worker's callback **waits for the owner to process the queue and return a result synchronously**, both can wait on each other forever. When using a queue in this case, the callback should return quickly and the owner should process **after the downcall returns**, or the architecture must allow the owner to process events while native code is running.

## 11. Asynchronous callbacks: lifetime is often more dangerous than thread ownership

In the demo, `invoke_native_thread` **joins the worker before returning**, so Java safely closes the arena after the downcall. A real-world native API may differ:

~~~c
/* API illustrating the idea; no implementation in the demo. */
void register_callback(callback_fn cb);
void launch_background_job(void);
void unregister_callback_and_wait(void);
~~~

If Java does:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment stub = linker.upcallStub(
            target, descriptor, arena);
    // native_register_callback(stub);
    // native_launch_background_job();
} // arena.close() while a native worker may still invoke the callback!
~~~

This is **dangerous pseudocode**. After the Arena closes, the upcall stub's function pointer is no longer valid; if C calls it later, it can cause a **crash or memory corruption** rather than just an easily handled Java exception.

The correct protocol:

~~~text
Java creates shared arena
    |
    +-- creates stub and required callback data
    +-- registers callback with native library
    +-- starts native worker(s)
    |
    +-- normal operation: callbacks may arrive
    |
    +-- stops accepting work / begins shutdown
    +-- unregisters callback or sends stop signal
    +-- waits for native confirmation that no in-flight callbacks remain
    +-- joins workers / releases native registrations
    |
    +-- arena.close() last
~~~

A shared Arena is a **lifetime manager**, not a magic reference counter that automatically knows whether C still holds the pointer. Java may only close after receiving sufficient completion signals from the native layer.

### 11.1. Is a callback on a new thread automatically "joined" by the JVM?

Do not rely on that. The FFM runtime can attach a worker to run Java, but **the JVM does not own the lifecycle protocol of OS workers created by a native library**. A worker can run longer than the downcall, or outlive the Java scope if the native library does not provide proper stop/join facilities.

The fact that a thread is attached as a daemon in HotSpot **does not guarantee that native work completes before JVM shutdown**. Production designs must explicitly stop workers, wait for callbacks to finish, and release stubs before unloading the library/VM.

### 11.2. Do not close a shared arena to "cancel a running callback"

`Arena.close()` is not equivalent to canceling a thread. If a callback/downcall is currently accessing a segment, closing may be rejected with `IllegalStateException` under temporal safety rules, or native code may use an invalidated pointer. Cancellation/waiting must happen at the **protocol layer**; do not use memory deallocation as a shutdown signal.

## 12. Upcalls receiving native pointers: a different ownership issue

The demo only passes `int32_t`, so it does not have to deal with raw pointers. In practice, callbacks often receive a `void *` or `struct *` provided by C:

~~~c
/* Illustrative ABI example, not part of the C file run in section 7. */
typedef int32_t (*read_fn)(const int32_t *ptr);
~~~

In Java, the descriptor can use:

~~~java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT));
~~~

When foreign code calls the upcall stub with such a pointer argument, the Java target receives a `MemorySegment` representing the pointer with a size matching the target layout, for example 4 bytes for an `int32_t`. The JDK 22 Linker Javadoc describes a pointer argument's segment as having an **always-alive scope** (global scope) rather than automatically inheriting the Arena from which C allocated the pointer.

**This is very important:**

- "Java received a `MemorySegment`" **does not prove** that the C pointer region remains valid long-term.
- The scope of the pointer argument segment **does not manage** when C may call `free(ptr)`.
- The callback must check for null pointers, ABI/size, and read/copy during the time native code guarantees the buffer is alive.
- Do not retain the pointer segment for use after the callback unless the native API has an explicit ownership contract, or copy the contents into Java-managed memory or an appropriate shared arena.
- On a native worker, a pointer segment argument may not be confined like a Java segment created by `Arena.ofConfined()`; **scope origins differ**, so do not generalize that "every segment is created by a Java arena".

If C passes a pointer to a buffer on the native worker's stack, the pointer can expire as soon as the C function returns. Do not confuse the lifetime of the Java wrapper with the lifetime of the native allocation.

## 13. JNI `AttachCurrentThread` differs from the FFM upcall path

If using traditional JNI from a native OS thread, the thread must be attached before calling JNI:

~~~c
/* JNI pseudocode, not part of the FFM C demo. */
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **) &env, NULL);
if (rc == JNI_OK) {
    /* Call JNI from THIS EXACT thread. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

This code belongs to the **JNI Invocation API**, requiring a valid `JavaVM *vm` and no Java frames on the stack when detaching. `JNIEnv *` is **thread-specific**; do not copy it from Java main or another JNI worker. `AttachCurrentThreadAsDaemon` differs from `AttachCurrentThread` in the daemon status of the newly attached thread.

With an FFM upcall stub:

~~~text
Java creates MethodHandle + FunctionDescriptor
     |
     v
Linker.upcallStub(...) -> C function pointer
     |
     v
Native OS worker calls function pointer
     |
     v
FFM runtime/VM transition brings worker into Java target
~~~

In the case of HotSpot/OpenJDK, the FFM runtime performs the attach for an unattached worker (per the implementation). You **do not** have to declare an FFM callback as a JNI method or manually pass `JNIEnv *` in `FunctionDescriptor` if the actual C ABI is just `int32_t(int32_t)`.

**Common mistake:** thinking that "since FFM already attached the native worker, Java main's confined segment will be usable." No. **Thread attachment** only enables the VM to run Java code; **confinement** still restricts segment access to the Arena's owner thread.

## 14. Thread identity, virtual threads, and callback context

An upcall from a C worker runs in the context of the **carrier OS thread/native thread** that entered the JVM. Do not assume:

- The callback will run on the same `Thread.currentThread()` as main.
- The callback will run on the same virtual thread that created the stub.
- `ThreadLocal` values from the Java caller are copied to the callback.
- The callback's context class loader is the same as the Java caller's.
- Java transaction/security/logging contexts are automatically propagated.
- A native worker callback will be scheduled on an Executor/Java thread that you pre-created.

If you want to preserve a business context, **pass the context explicitly** via an object bound in the MethodHandle, or via an ID/token that has a thread-safe mapping with a well-defined lifecycle.

With multiple concurrent callbacks, the target must also support **reentrancy**. For example, a callback writing to an unsynchronized `ArrayList` from multiple OS threads can cause a race; replace it with a concurrent queue or event loop, or use controlled synchronization.

### 14.1. Context class loader and class lookup

A native-attached thread usually does not have the same Java application call stack "above" it as Java main. If a callback needs to load classes or resources that depend on a class loader, retain a `Class<?>` or an appropriate class loader **from an explicit Java context**, rather than relying accidentally on the OS worker's thread context class loader.

Especially with plugins/hot reload, a bound target MethodHandle or Java object can **keep a class loader reachable** longer than expected. Native registrations must be cleaned up and stubs/handlers released alongside the plugin lifecycle.

## 15. Data synchronization and visibility when using a shared arena

In the demo, Java main writes `32` to `sharedData` **before** asking C to create the worker; the worker only reads. C uses `pthread_create`/`pthread_join` (or Win32 thread creation/wait) to organize the thread lifecycle clearly.

In more complex programs, you cannot assume all inter-thread reads/writes will have proper visibility just because of `Arena.ofShared()`. A shared arena permits access from multiple threads, but **does not enforce memory-ordering** for your algorithm.

When a callback updates data:

~~~java
// Illustrates the idea; DATA is created from Arena.ofShared().
int current = sharedData.get(ValueLayout.JAVA_INT, 0L);
sharedData.set(ValueLayout.JAVA_INT, 0L, current + 1);
~~~

Reading and then writing in **two operations** is not an atomic read-modify-write; two concurrent callbacks can lose updates.

If an atomic counter is needed, use a `VarHandle` with the appropriate access mode:

~~~java
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

VarHandle intVar = ValueLayout.JAVA_INT.varHandle();

// On a properly aligned segment belonging to a live shared scope:
int previous = (int) intVar.getAndAdd(sharedData, 0L, 1);
~~~

This is a snippet, not a standalone source file. Check `intVar.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` when supporting different layouts/ABIs.

**Two separate layers of safety:**

1. **Spatial/temporal/thread access:** MemorySegment, Arena scope, bounds, and `WrongThreadException`.
2. **Concurrent data:** atomic VarHandles, locks, happens-before, and native synchronization.

A correct callback design must satisfy **both**.

## 16. Common anti-patterns

### 16.1. Changing only the stub's Arena, without changing the data's Arena

~~~text
Arena.ofShared() -> upcall stub        [right direction]
Arena.ofConfined() -> captured data    [still readable only by main]
Native worker -> callback -> data.get  [WrongThreadException]
~~~

**Fix:** use shared data or move the snapshot/access back to the owner thread.

### 16.2. Catching exceptions after `invokeExact` instead of inside the upcall

~~~java
try {
    // C worker calls a Java target that may throw WrongThreadException.
    // (int) downcall.invokeExact(stub, 10);
} catch (WrongThreadException ex) {
    // NOT enough to protect the upcall: exceptions are not allowed
    // to escape across the native function-pointer boundary.
}
~~~

This is pseudocode illustrating an error. A catch in Java **outside the downcall** does not substitute for a catch **inside the target callback**. With an FFM upcall, an exception escaping the target can cause the JVM to terminate abruptly before the Java caller ever receives it.

### 16.3. Native code keeping the callback pointer after Java has closed the arena

~~~text
Java register(callback)
Java close arena
native worker callback(...)  -> function pointer has exceeded its lifetime
~~~

This can be a **JVM crash**. `unregister + wait for completion` is required before closing.

### 16.4. Native worker waits for Java main, Java main waits for native worker

~~~text
MAIN:
  downcall invoke_native_thread(...)
     -> C pthread_join(worker)

WORKER:
  upcall callback(...)
     -> waits for MAIN to process a synchronous task

MAIN cannot process the task because it is waiting for join.
WORKER cannot return because it is waiting for MAIN.
=> deadlock
~~~

Fix this by having the callback return quickly and push data into a queue, or by using an architecture that does not keep Java main blocked in a synchronous downcall while callbacks need to be processed.

### 16.5. Using a confined arena from a native thread even without shared mutable data

When a callback only needs a scalar `int`, **it is not necessary to share native memory**. Read the scalar on the owner first, bind it into the MethodHandle, or pass it via an immutable Java object; this reduces risk more cleanly than turning everything into shared memory.

### 16.6. Thinking a VM-attached thread is automatically allowed to close any arena

With `Arena.ofConfined()`, only the owner thread that created the arena has the right to close it. A native upcall thread, even though it can run Java, calling `confinedArena.close()` from a non-owner thread will throw `WrongThreadException`. Do not delegate cleanup responsibility to an arbitrary callback; the owner handles it after all callbacks have completed.

## 17. Diagnosis and troubleshooting table

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Callback from main can read data, callback from C worker fails | Captured segment belongs to main's `Arena.ofConfined()` | Shared arena, or copy primitive/queue back to owner |
| `WrongThreadException` | Accessing/closing a confined scope from another thread | Check the owner thread and the actual data arena |
| `IllegalStateException` when using a segment | Arena already closed, or lifetime race | Do not use after close; wait for all workers to finish |
| JVM terminates unexpectedly during upcall | Java exception escaped the target, or wrong ABI/invalid function pointer | Catch inside target; verify descriptor/prototype and lifetime |
| Callback from C does not run | Wrong/expired stub pointer, native never called it, thread creation failed | Check exports, status codes, C create/join, Arena scope |
| `WrongMethodTypeException` at `invokeExact` | Java types do not match the MethodHandle descriptor | Check `MethodHandle.type()`, carrier `int`/`MemorySegment` |
| `IllegalArgumentException` when creating stub | Target MethodHandle type does not match FunctionDescriptor | Use `MethodType.methodType(int.class,int.class)` after binding |
| `IllegalCallerException` / native-access warning | Restricted FFM API has not been granted native access | `--enable-native-access=ALL-UNNAMED` or specific module |
| `UnsatisfiedLinkError` / cannot load C library | Wrong `Path`, file name, architecture, dynamic dependencies | Build for correct OS, `System.mapLibraryName`, run in same directory |
| Callback reports wrong value | C `int32_t` mismatches descriptor/ABI or data race | Check C typedef, alignment, synchronization |
| Closing arena fails while callback is running | Close concurrent with in-flight accesses/downcalls | Stop/unregister/join before closing |
| Java main hangs waiting for C worker | Callback waits for main while main waits for join | Switch to asynchronous event queue/owner event loop |
| Error only on plugin unload | Stub/target/class loader still held by native code | Lifetime management, unregister, class loader references |
| Native worker keeps running at JVM exit | Relying on daemon attach to ensure native cleanup | Explicit shutdown, join, and stop before VM teardown |
| Shared arena, yet lost update results | Non-atomic `get`+`set` | Atomic VarHandle/lock and proper data publication |
| Java object still holds MemorySegment, but cannot use it | Scope already closed | Segment lifetime is not equal to Java reference lifetime |

### 17.1. Checking symbol exports

Linux:

~~~bash
nm -D libthread_callback.so
~~~

macOS:

~~~bash
nm -gU libthread_callback.dylib
~~~

Windows x64 Developer Command Prompt:

~~~bat
dumpbin /exports thread_callback.dll
~~~

For the demo library, you should see `invoke_direct` and `invoke_native_thread` as exported symbols. Exact names/decorations depend on the OS/ABI; with the chosen 64-bit C ABI, there is no C++ name mangling.

There is no need to look for `JNI_OnLoad` in the demo because this is an FFM-only library. If using C++ to export functions, use `extern "C"` to avoid name mangling and verify the convention.

## 18. Production design checklist for native thread callbacks

Before handing a Java function pointer to a native library, check:

- **Who calls the callback?** Immediately during the downcall, or on a separately created OS worker? How many threads can call concurrently?
- **Which thread owns the confined arena?** Does the target capture a confined segment from another thread?
- **Is the upcall stub's Arena** shared and long-lived enough for all native callbacks?
- **Does the captured data's Arena** actually have the required thread policy? Do not equate it with the stub arena.
- **Is there data that should be copied beforehand?** Scalar/immutable data can help avoid sharing native memory.
- **Does the Java target catch exceptions at the boundary?** Is there a status/error channel to report back to native code?
- **Does the C FunctionDescriptor** match the exact pointer/function signature, C integer widths, and calling convention?
- **Does the native worker lifetime** have a stop/join or unregister+ack before closing the stub arena?
- **Can `close`** run concurrently with a callback actively using the segment?
- **Does the callback wait for the owner Java thread?** Is the owner blocked in a downcall waiting for the worker?
- **Does thread context** such as class loader, ThreadLocal, or MDC need to be passed explicitly?
- **Does concurrent callback data** have proper atomics/locks/synchronization beyond just using `Arena.ofShared()`?
- **Do FFM pointer arguments** have well-defined ownership/lifetime from C, or are they just raw pointers with global scope?
- **Do error paths** when native thread creation fails allow Java to close the arena safely and log diagnostics?
- **Does VM shutdown** wait for native workers and in-flight callbacks to finish before tearing down native libraries?
- **Are the native access flag** and the target JDK's security/integrity restrictions configured?

## 19. Review questions with answers

**1.** Java main creates `Arena.ofConfined()`, allocates `MemorySegment data`, and passes a callback bound to `data` to a native OS worker. Why does the callback still fail even though the JVM can run Java code from the worker?

**Answer:** The JVM attach/transition allows the worker to **execute Java**, but it does not transfer **ownership of the confined arena**. `data.get` from the worker violates confinement and throws `WrongThreadException`.

**2.** Does `upcallStub(target, desc, Arena.ofShared())` automatically turn every captured MemorySegment into a shared one?

**Answer:** No. The stub belongs to the arena passed at creation, whereas captured segments retain the scope/owner thread of **the arena that allocated them**.

**3.** In the demo, why does `invoke_direct(stubA, 10)` return 42 while `invoke_native_thread(stubA, 10)` returns -700?

**Answer:** The direct callback runs right on the Java main thread, which is the proper owner of the confined data. The native-thread callback runs on a different OS worker, so the target catches `WrongThreadException` and returns the sentinel -700.

**4.** If a native callback causes the Java target to throw an uncaught exception, is wrapping the downcall in `try/catch` at the Java caller sufficient?

**Answer:** No. JDK 22 specifies that exceptions must not escape an upcall target; the JVM may terminate abruptly. The catch must be **inside the target** or wrapped with an appropriate MethodHandle combinator.

**5.** Does `Arena.ofShared()` prevent two callbacks incrementing the same counter from losing updates if each callback does `get` then `set`?

**Answer:** No. Shared only permits multi-threaded access; you must use an atomic mode such as `VarHandle.getAndAdd` or proper synchronization.

**6.** Why doesn't the example close the arena immediately after C creates the worker and returns?

**Answer:** C **does not** return to Java before the worker joins. Therefore, Java only closes when no native callbacks are pending. With a real async API, separate unregister/stop/join is required.

**7.** If a callback receives a C pointer in a Java `MemorySegment` argument, does that mean the pointer's lifetime is managed by a Java Arena?

**Answer:** No. An upcall pointer argument has a scope according to the linker contract, typically global/always alive, but C still owns the raw allocation; Java must obey the specified native lifetime.

**8.** Why might you copy a primitive instead of using a shared segment?

**Answer:** If the callback only needs a known scalar value, the owner reads it on the valid thread and binds the value into the target; the worker does not access the confined segment and unnecessary expansion of ownership is avoided.

**9.** A callback on an OS worker puts a task into a queue and waits for the owner to process it, while the owner is blocked in `pthread_join`. What will happen?

**Answer:** Deadlock: the owner waits for the worker, and the worker waits for the owner. Use a protocol that does not require a synchronous response, or let the owner process the queue outside the blocking call.

**10.** Does an FFM upcall from a native thread require Java to manually call `AttachCurrentThread` and store `JNIEnv *` globally?

**Answer:** Not in the HotSpot FFM example; the FFM runtime handles transition/attach. `JNIEnv *` is a thread-bound JNI API, not for global use; separate attach rules only apply when native JNI code itself calls JNI directly.

**11.** If Java still holds the `stub` object but the arena has closed, can C safely use that address?

**Answer:** No. The lifetime of an upcall function pointer is tied to the arena scope, not merely to the Java reference. Calling the pointer after close can crash.

**12.** In the example, why is `-pthread` needed on Linux/macOS while `jni.h` is not?

**Answer:** C creates workers using POSIX threads, so the threading environment must be built/linked properly. An FFM-only library does not use JNI function types/methods, so the JNI header is not needed.

## 20. Technical references

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall, `upcallStub`, lifetime, pointer arguments, warning that exceptions must not escape callbacks, and restricted native access.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared owner thread, `WrongThreadException`, `close`, and temporal safety.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): thread access checks, scope, bounds, and segment validity.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): ABI types of C callbacks and Java MethodHandles.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup(Path, Arena)` and library resource management.
- [Oracle Java SE 22 — JNI Invocation API](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/invocation.html): JNI `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, and `JNIEnv *` limitations.
- [Dev.java — FFM Upcalls](https://dev.java/learn/api/io/ffm/upcall/): explanation of turning a Java MethodHandle into a C function pointer.
- [OpenJDK — Foreign Linker Implementation Overview](https://cr.openjdk.org/~jvernee/docs/FL_Overview.html): implementer details on **upcalls from non-Java native threads**, daemon attach, and detach on thread death.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): standardization of FFM in Java 22.

**Conclusion:** A native worker can call back into Java via FFM `Linker.upcallStub`, but **the thread running the callback does not automatically become the owner** of a segment allocated by `Arena.ofConfined()` on another thread. You must manage the lifetimes of the stub and the data **separately**, **catch exceptions inside the callback**, use shared memory or copy/queue when crossing thread boundaries, and **wait for all native workers/callbacks to complete before closing the arena**.