# Releasing Native Resources with Explicit close and Limitations of Cleaner or GC

## 1. The Lifecycle Problem: Java Objects Differ from Native Resources

A Java application using JNI may hold **resources outside the Java heap**: memory allocated by `malloc`, file descriptors, native sockets, image processing libraries, C/C++ buffers, GPU objects, database handles, or pointers to third-party library structures. Usually a Java object acts as a *wrapper* and stores a `long` value representing the native handle:

```text
Java heap                            Native memory / OS resource
-----------------                    ----------------------------
NativeBuffer instance                Buffer *p = malloc(...)
  ├─ Java fields                          └─ value = 42
  └─ long address -------------> p
```

**The GC knows about collecting Java objects**, but does not automatically know how to call `free(p)`, close a socket, destroy a C++ object, or release the corresponding GPU handle. Native resources can continue to exist **after the Java object is no longer used** if there is no proper release code.

Three management approaches have different meanings:

1. **Explicit `close()`:** the application determines when usage ends and calls the release API in a known control flow.
2. **`Cleaner`:** a cleanup action that may run when a Java object becomes *phantom reachable*, usually on a thread managed by the Cleaner; suitable as a **last-resort safety net** if the caller forgets `close()`, **not a release deadline**.
3. **GC:** collects Java heap memory according to JVM policy; there is no guarantee it will run when you want, and it does not replace a native resource closing protocol.

**Main principle:** resources that must be returned on time must have **clear ownership and explicit `close()`**, usually using `AutoCloseable` + `try-with-resources`. `Cleaner` only helps handle missed cases; do not design program correctness to depend on whether GC runs in time.

## 2. AutoCloseable and try-with-resources: Predictable Release

The `java.lang.AutoCloseable` interface declares `close()`. A JNI wrapper can implement `AutoCloseable` so callers can use:

```java
try (NativeBuffer buffer = new NativeBuffer(42)) {
    int value = buffer.read();
    System.out.println(value);
} // Java calls buffer.close() when leaving this scope.
```

This is a **usage snippet**; `NativeBuffer` is fully implemented in section 5.

Benefits:

- `close()` is called when exiting the block, including when an exception occurs in the `try` body.
- The closing time is tied to **the end of the scope**, independent of GC, memory pressure, or the Cleaner thread.
- Ownership responsibility is clearly expressed: whoever opens it closes it, unless the API has a transparent ownership transfer mechanism.
- If both the `try` body and `close` throw exceptions, Java keeps the `try` body exception as the primary error and can store the close exception in the **suppressed exceptions** list (`Throwable.getSuppressed()`).

Example:

```text
open resource
   |
   v
try-with-resources
   |
   +--> use resource
   |       |
   |       +--> succeeds ----------------+
   |       |                             |
   |       +--> throws exception --------+
   |                                     |
   v                                     v
close() is called before leaving scope
   |
   +--> native release (free/close/cancel)
   |
   v
must not use closed resource
```

`try-with-resources` guarantees **the `close()` call is executed according to Java language rules**; it **does not guarantee** that the driver, OS, disk, or C library always executes the release operation successfully. If the native API can report an error on close, you must design how to handle, propagate, or record that error. Do not equate "a close call occurred" with "all I/O flushed successfully".

### Good Close Contract for a JNI Wrapper

A wrapper with a native handle typically needs:

- **Close exactly once** at the native layer; repeated `close` calls must not cause a `double free`.
- **Fail fast** with `IllegalStateException` when reading/writing after close, instead of passing a freed pointer down to C/C++.
- **Synchronize close with ongoing operations**, avoiding thread A still using the handle while thread B has already freed it.
- **Release on partial constructor failure**, not leaking a newly created native allocation that has not yet been registered for cleanup.
- **Have a clear policy for errors during close**; if `close` can fail, do not silently ignore it and do not delegate error reporting responsibility to Cleaner.
- **Do not use GC as a transaction completion condition**: before returning a result or finishing a request, resources that need closing must be closed along a deterministic control flow.

## 3. Why Relying Only on GC Is Not Enough

### 3.1. Java Heap and Native Memory Do Not Share the Same Ownership Mechanism

The JVM's GC handles reachability of **Java objects**. A small object holding only a `long address` can correspond to very large native memory. Heap pressure can remain low even when native heap or GPU memory is nearly exhausted. When the JVM does not yet see a need for GC, native resources are not yet released by mechanisms that depend on GC.

`System.gc()` only requests or hints at GC, **it is not an API to "release native resources immediately"**. The JVM may not perform GC immediately, may only collect a subset of objects, and does not promise Cleaner will finish before `System.gc()` returns.

### 3.2. An Object "No Longer Used in Source" Does Not Mean Immediate Collection

The JIT can optimize the live range of local variables; GC depends on remaining strong roots, the collector type, and collection timing. Native resources should not have timeouts or quotas based on conditions like:

```java
buffer = null;
System.gc(); // Must not be treated as a replacement for buffer.close().
```

In a long-running server application, thousands of native allocations can exhaust file descriptors or off-heap memory before Cleaner gets a chance to run, even though the Java heap still looks fine.

### 3.3. JVM Shutdown Has No Guarantee of Running All Cleaner Actions

The Cleaner API explicitly states that behavior during `System.exit` is implementation-specific; cleaning actions are not guaranteed to be called. The default Cleaner thread is a **daemon**, and the system may terminate before fallback cleanup completes. Crashes, killed processes, power loss, or native aborts even further prevent relying on Java-side cleanup.

Even `finally` and `try-with-resources` cannot run in every case of sudden process death; however, they allow **predictable release on normal Java control paths and normal exception propagation**, far better than waiting for GC.

## 4. How Does Cleaner Actually Work?

`java.lang.ref.Cleaner` was introduced in Java 9 and is available in Java 17+. Cleaner tracks a Java object and a registered `Runnable` action. When the object becomes **phantom reachable** and the JVM processes the corresponding reference, Cleaner can run the action on the Cleaner thread.

Registration:

```java
private static final Cleaner CLEANER = Cleaner.create();
Cleaner.Cleanable cleanable = CLEANER.register(owner, cleanupState);
```

- `owner` is the **Java object whose reachability is tracked**.
- `cleanupState` is a `Runnable` containing enough information to release the native resource.
- `cleanable.clean()` unregisters and triggers the cleaning action **explicitly**, at most once.
- If `clean()` is not called and `owner` becomes phantom reachable, Cleaner can run the action **asynchronously** later.
- The cleaning action runs **at most once** by the `Cleanable` contract, but automatic execution timing is **not guaranteed**.
- Exceptions thrown by the cleaning action on the Cleaner thread are ignored by the Cleaner API; therefore it is **not a reliable resource management error-reporting channel**.

### The Cleaner Action Must Never Hold a Strong Reference to the Owner

A common mistake:

```java
// WRONG: this lambda references this, which can keep owner reachable.
cleanable = CLEANER.register(this, () -> nativeFree(this.address));
```

Cleaner must hold the `Runnable` so it can run it. If the `Runnable` retains `this`, we create a strong reference path back to the tracked object:

```text
Cleaner -> cleanup action -> owner
                            ^
             owner cannot become phantom reachable
```

Consequence: the action may **never** run automatically; right when `close` is forgotten, the fallback also loses its effect.

**Correct pattern:** create a `static nested class State implements Runnable`, containing only independent data such as the native address, file descriptor, or release state. **State must not contain `NativeBuffer` or any callback/lambda holding the owner**. When the constructor registers, `Cleaner.register(this, state)` can track the owner without the action keeping the owner alive.

### Do Not Relax Deadlines Using Cleaner

Cleaner does not guarantee deadlines, ordering across multiple resources, shutdown order, or thread affinity. A native resource that must be released on a specific thread (for example, some GPU/context/GUI handles, peripheral devices, or C libraries with thread-local state) **cannot by default be released directly from the Cleaner thread**. You must design closing on the right thread and, if there is a fallback, a mechanism to safely dispatch work to the owner thread — though that dispatch mechanism is also not guaranteed to complete at shutdown.

## 5. Complete JNI Example: Deterministic Close, Cleaner Only as Fallback

We build `NativeBuffer`, a Java wrapper for a C allocation holding a `jint`. The code illustrates the essential concepts:

1. `nativeAlloc(int)` uses `malloc`, returning the handle to Java as a `long`.
2. `read()` uses the native pointer while the resource is still open.
3. `close()` calls `Cleaner.Cleanable.clean()` to release **right on the close call path**, without waiting for GC.
4. `State.run()` retrieves the handle and sets it to 0 using `AtomicLong.getAndSet(0)`, preventing native `free` twice if close and the Cleaner action race.
5. Both `read()` and `close()` are `synchronized`, so calls through the same wrapper do not overlap.
6. `Reference.reachabilityFence(this)` keeps the wrapper strongly reachable until after the native operation to avoid premature cleanup due to JIT optimization.
7. The Cleaner action resides in a **static nested class**, holding no strong reference to the wrapper.

The example is for JDK **17+** and a C compiler on Linux/macOS/Windows. It models real native memory; no driver, GUI, or GPU is needed.

### 5.1. File `src/example/jni/NativeBuffer.java`

```java
package example.jni;

import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicLong;

public final class NativeBuffer implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    static {
        System.loadLibrary("nativebuffer");
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    // Must not reference NativeBuffer.this.
    private static final class State implements Runnable {
        private final AtomicLong address = new AtomicLong();

        void setAddress(long value) {
            address.set(value);
        }

        long address() {
            return address.get();
        }

        @Override
        public void run() {
            long ptr = address.getAndSet(0L);
            if (ptr != 0L) {
                nativeFree(ptr);
            }
        }
    }

    public NativeBuffer(int value) {
        State fresh = new State();  // Create State before native allocation.
        long ptr = nativeAlloc(value);

        if (ptr == 0L) {
            throw new IllegalStateException("nativeAlloc returned null");
        }
        fresh.setAddress(ptr);

        Cleaner.Cleanable registration;
        try {
            registration = CLEANER.register(this, fresh);
        } catch (RuntimeException | Error failure) {
            fresh.run();  // If registration fails, release immediately.
            throw failure;
        }

        this.state = fresh;
        this.cleanable = registration;
    }

    public synchronized int read() {
        long ptr = state.address();
        if (ptr == 0L) {
            throw new IllegalStateException("Resource is closed");
        }

        try {
            return nativeRead(ptr);
        } finally {
            Reference.reachabilityFence(this);
        }
    }

    public synchronized boolean isClosed() {
        return state.address() == 0L;
    }

    @Override
    public synchronized void close() {
        cleanable.clean();
    }

    private static native long nativeAlloc(int value);
    private static native int nativeRead(long ptr);
    private static native void nativeFree(long ptr);

    public static void main(String[] args) {
        NativeBuffer buffer = new NativeBuffer(42);

        try (buffer) {  // Java 9+: buffer variable is effectively final.
            System.out.println("Value: " + buffer.read());
        }

        buffer.close(); // Second close: does not call free again.
        System.out.println("Closed: " + buffer.isClosed());

        try {
            buffer.read();
        } catch (IllegalStateException expected) {
            System.out.println("Read after close: blocked");
        }
    }
}
```

**Why does the constructor create `State` before `nativeAlloc`?** If allocating the auxiliary Java object fails **after** `malloc` has been called, there is a risk of losing the native address without a cleanup owner. The pattern creates `State` before native allocation, then updates the address and registers with Cleaner. If `CLEANER.register` fails, the catch block releases the handle immediately. The C code below has an error-reporting path for `malloc` failure.

**Why does `close()` call `cleanable.clean()` instead of calling `nativeFree` directly?** Because the same cleaning action is used for **explicit close** and fallback, the `Cleanable` mechanism guarantees the action runs at most once. `State.run()` additionally uses `getAndSet(0)` to block double-free at the state layer, and `isClosed()` can check the state.

In practice, if the native release function can fail and needs clear error reporting, you should design a dedicated close path to handle error reporting; **do not** treat a Cleaner action—which is allowed to run asynchronously and ignores exceptions—as the primary error-handling mechanism.

### 5.2. Using javac -h to Generate the JNI Header

From the project root directory, on a Linux/macOS shell:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
    -d build/classes \
    src/example/jni/NativeBuffer.java
```

The result has the class file `build/classes/example/jni/NativeBuffer.class` and the JNI header `build/include/example_jni_NativeBuffer.h`.

The prototypes generated by `javac -h` (omitting comments/guards):

```c
#include <jni.h>

JNIEXPORT jlong JNICALL Java_example_jni_NativeBuffer_nativeAlloc
  (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_example_jni_NativeBuffer_nativeRead
  (JNIEnv *, jclass, jlong);

JNIEXPORT void JNICALL Java_example_jni_NativeBuffer_nativeFree
  (JNIEnv *, jclass, jlong);
```

Separately verified the Java code with `javac -h` on JDK 24: the class compiles successfully and the header has these exact three prototypes. `JNICALL` and `JNIEXPORT` must be preserved in the C function definitions according to the JNI ABI.

### 5.3. File `NativeBuffer.c`

```c
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include "example_jni_NativeBuffer.h"

typedef struct {
    jint value;
} Buffer;

JNIEXPORT jlong JNICALL Java_example_jni_NativeBuffer_nativeAlloc(
        JNIEnv *env, jclass cls, jint value) {
    (void)cls;

    Buffer *p = (Buffer *)malloc(sizeof(*p));
    if (p == NULL) {
        jclass oom = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
        if (oom != NULL) {
            (*env)->ThrowNew(env, oom, "native malloc failed");
            (*env)->DeleteLocalRef(env, oom);
        }
        return 0L;
    }

    p->value = value;
    return (jlong)(intptr_t)p;
}

JNIEXPORT jint JNICALL Java_example_jni_NativeBuffer_nativeRead(
        JNIEnv *env, jclass cls, jlong handle) {
    (void)env;
    (void)cls;

    // Handle only arrives here from Java wrapper after checking open.
    Buffer *p = (Buffer *)(intptr_t)handle;
    return p->value;
}

JNIEXPORT void JNICALL Java_example_jni_NativeBuffer_nativeFree(
        JNIEnv *env, jclass cls, jlong handle) {
    (void)env;
    (void)cls;

    if (handle != 0L) {
        free((void *)(intptr_t)handle);
    }
}
```

For common JNI platforms where pointers are no wider than 64 bits, `intptr_t` supports converting a pointer to a sufficiently wide integer, which is then stored in `jlong`. This is **illustrative ABI code on common platforms**, not a pointer serialization standard or a safe handle across two processes. Do not write these addresses to a database to reload after a process restart.

**More important than the cast:** `nativeRead(handle)` **is only safe when the handle is valid and not yet freed**. C cannot verify by checking `handle != 0` that the pointer has not been freed; the lifecycle protection contract lies in the Java wrapper and synchronization rules. Do not expose a native method that accepts an arbitrary pointer from untrusted Java code.

`nativeFree` uses `free`, which is a simple release operation with no Java callbacks and no specific thread requirement. This makes it suitable as a Cleaner fallback. For a native resource requiring thread-affine release or an operation that can fail, the solution must be more complex and the example cannot be applied verbatim.

### 5.4. Build and Run on Linux

Requirements: **JDK 17+**, GCC, and `JAVA_HOME` pointing to a JDK directory with `include/jni.h`.

```bash
gcc -std=c11 -O2 -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -Ibuild/include \
    -o build/native/libnativebuffer.so \
    NativeBuffer.c

java -Djava.library.path=build/native \
    -cp build/classes \
    example.jni.NativeBuffer
```

**Stdout when compiled and loaded successfully:**

```text
Value: 42
Closed: true
Read after close: blocked
```

Explanation:

- `new NativeBuffer(42)` allocates `Buffer` in C.
- `read()` retrieves `jint value` via `nativeRead`, printing `42`.
- Exiting `try (buffer)` forces a call to `close()`; `cleanable.clean()` runs the action, `getAndSet(0)` retrieves the old pointer, and `nativeFree` frees it.
- The second `buffer.close()` cannot free the native pointer again.
- `isClosed()` sees the address is already `0`; the subsequent `read()` throws `IllegalStateException` **before calling JNI**, then Java catches it and prints the last line.
- No need to call `System.gc()`, and no dependence on Cleaner scheduling.

### 5.5. Build on macOS and Windows

**macOS**, after generating the class/header with the same `javac -h` command:

```bash
clang -O2 -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -Ibuild/include \
    -o build/native/libnativebuffer.dylib \
    NativeBuffer.c

java -Djava.library.path=build/native \
    -cp build/classes \
    example.jni.NativeBuffer
```

**Windows**, from a Visual Studio Developer Command Prompt configured with JDK, `cl`, and `JAVA_HOME`:

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\example\jni\NativeBuffer.java

cl /nologo /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" NativeBuffer.c /Febuild\native\nativebuffer.dll

java -Djava.library.path=build\native -cp build\classes example.jni.NativeBuffer
```

`System.loadLibrary("nativebuffer")` takes a logical name; the JVM maps it to `libnativebuffer.so` (Linux), `libnativebuffer.dylib` (macOS), or `nativebuffer.dll` (Windows). The native compiler and JVM must match in architecture/ABI. If a newer JDK environment requires granting native access permission when running JNI, add the appropriate runtime option for the version/module, such as `--enable-native-access=ALL-UNNAMED` when supported and needed.

**Actual verification:** the `NativeBuffer.java` part and JNI header were compiled/generated with `javac -h`. The C source is designed to be compatible with the header; running C requires a C compiler and a JVM environment for the target OS. The stdout output describes the execution path when building and loading the native library succeeds.

## 6. Four Lifecycle Paths That Must Be Solved Separately

### 6.1. Normal Path: Calling close Before Scope Ends

```text
new NativeBuffer
   -> nativeAlloc
   -> Cleaner.register
   -> read, read, ...
   -> close
   -> cleanable.clean
   -> State.address.getAndSet(0)
   -> nativeFree(handle)
   -> returns to Java with resource closed
```

This is the **expected** path. It works regardless of whether GC or the Cleaner thread is running at that time. If the caller uses `try-with-resources`, cleanup is also called when the `try` body throws an exception.

### 6.2. Forgotten Close Path: Can Only Hope for Cleaner

```text
new NativeBuffer
   -> nativeAlloc
   -> Cleaner.register
   -> caller drops reference to wrapper
   -> [can be very long, no deadline]
   -> GC determines phantom reachability
   -> Cleaner processes action
   -> State.run -> nativeFree
```

This path **cannot be used as proof of release timing**. The process may terminate before the action runs, or native memory may grow before GC collects enough object wrappers. This is a **best-effort fallback**, not a contract completion condition.

### 6.3. Constructor Failure Path

A constructor may create a native resource and then fail at the next step, for example because it cannot register with Cleaner. If the Java object constructor is left to fail by default without cleanup, the native allocation becomes an orphan.

In the example:

```text
State = new State()              // auxiliary Java resource
nativeAlloc()                    // native resource opened
State.setAddress(...)
Cleaner.register(...)  -- if fails --> State.run() -> nativeFree()
```

If `malloc` in C fails, `nativeAlloc` creates an `OutOfMemoryError` (or a JNI lookup exception error if creating the exception fails), with no valid pointer to free. **Do not rely by default on Cleaner to clean up resources from an incomplete constructor.**

When opening multiple resources sequentially in a constructor, use local variables with `try/finally` or an *acquire → validate → transfer ownership* procedure to release all allocated components if any step fails.

### 6.4. Concurrent Close and Use Path

On a JNI wrapper, a dangerous situation:

```text
Thread A                            Thread B
--------                            --------
ptr = address  // nonzero
                                    close() -> free(ptr)
nativeRead(ptr)  // use-after-free!
```

**`AtomicLong.getAndSet(0)` only prevents double-free of competing releases; it does NOT automatically prevent use-after-free between read and close.**

The example handles **Java calls** with `synchronized read()` and `synchronized close()` on the same wrapper:

```text
Thread A                         Thread B
--------                         --------
enter monitor(buffer)
get pointer
nativeRead(pointer)
Reference.reachabilityFence(buffer)
exit monitor(buffer)
                                 enter monitor(buffer)
                                 cleanable.clean -> free(pointer)
                                 exit monitor(buffer)
```

If thread B arrives first, A will read address = 0 and throw `IllegalStateException`. If A arrives first, B waits until A finishes reading before freeing. With multiple native threads or C callbacks using the handle outside the two Java methods, **the wrapper's monitor does not automatically protect all native consumers**; a native mutex, ref counting, lease/borrow API, or appropriate lifecycle management mechanism is required.

## 7. Reference.reachabilityFence and "Premature Cleaning"

A subtle case: Java code may only read `long address` and then call a native method, and afterwards **not read any more fields of the wrapper**. The JIT can sometimes prove the Java object is no longer needed after reading the address; the collector may consider the owner no longer strongly reachable **before the native operation completes**, even though the source code is still inside the method.

Conceptual example:

```java
long ptr = state.address();
int result = nativeRead(ptr);
// If owner is considered no longer alive before nativeRead finishes,
// the Cleaner action could free ptr right while it is in use.
```

`Reference.reachabilityFence(this)` guarantees the passed-in object remains strongly reachable **at least until the point the fence is called**. Placing the fence in `finally` after the native operation ensures it is executed even if the JNI call ends with a Java exception:

```java
try {
    return nativeRead(ptr);
} finally {
    Reference.reachabilityFence(this);
}
```

This protects against **premature GC-based cleanup** of the owner itself. It does **not** replace synchronization between explicit close and use, and does not automatically protect a handle freed by another native thread that does not respect ownership. That is why the example uses **both `synchronized` and `reachabilityFence`**, each solving a different kind of race.

## 8. Why Must State Be Independent and Release Only Once?

### 8.1. Separating the Referent from the Action

`CLEANER.register(this, fresh)` has two distinct roles:

- `this` is the owner used to track GC reachability.
- `fresh` holds the handle and knows how to release it, but **does not reference `this`**.

With `State` being a `static final class`, there is no implicit outer instance. Do not write the cleanup action using an instance method reference like `this::releaseNative`, or a lambda directly accessing the owner's fields; those expressions can keep the owner reachable.

### 8.2. Atomic Swap to 0 Before Free

```java
long ptr = address.getAndSet(0L);
if (ptr != 0L) {
    nativeFree(ptr);
}
```

Setting to 0 first ensures that if the action is called again, there is no old pointer to free. `Cleaner.Cleanable.clean()` already has an **at-most-once** contract; `getAndSet` is a guard at the state layer and makes `isClosed` work. However, if native free **can fail**, marking 0 before the release operation means it cannot be retried via state; a different closing and error-reporting protocol must be designed rather than copying this pattern for resources with complex cleanup failure semantics.

### 8.3. Do Not Use Finalizer as Primary Cleanup

`Object.finalize()` is deprecated and has many limitations: unpredictable timing, ordering, deadlock risk, and resurrection issues. For off-heap resources, modern APIs prefer **explicit close**; `Cleaner` is only a more controlled fallback option than finalization, **not turning asynchronous cleanup into deterministic cleanup**.

## 9. Comparison of Release Mechanisms

| Mechanism | When it is called | Native release on time? | Notes |
| --- | --- | --- | --- |
| `close()` called on time by caller | When caller decides it is done with resource | **Can be designed to be on time**, if release code succeeds | Primary choice for JNI handles |
| `try-with-resources` | When leaving scope, including due to normal exceptions | **Yes**, thanks to deterministic `close` call | Should be used for resources with clear scope |
| `Cleaner.Cleanable.clean()` called explicitly | Immediately at the code calling `clean()` | **Possible**, if action is suitable and completes | In the example, called from `close()` |
| Automatic Cleaner action | After phantom reachability and Cleaner processing | **No** | No deadline; asynchronous; separate thread |
| GC / `System.gc()` | According to collector/runtime decision | **No** | GC does not automatically know about a JNI wrapper's `malloc`/`free` |
| `finalize()` | Legacy finalization mechanism (deprecated) | **No** | Do not use as a release strategy |
| `Runtime.addShutdownHook` | Some orderly shutdown paths | **Not guaranteed** | Does not run in all termination types; does not replace `close` |

A resource with a *capacity* constraint, for example at most a few hundred file descriptors or native handles, needs **contractual closing** and possibly added quota/backpressure. Do not just "wait for GC" when the wrapping Java object is very lightweight compared to a large native allocation.

## 10. When Is Cleaner Fallback Inappropriate?

### Resources Bound to a Thread or Context

Some native APIs require release on the exact OS thread or context that created them: GPU graphics contexts, GUI toolkits, some C/C++ thread-affine libraries, COM apartments, thread-local allocators. The Cleaner thread is **different** from the owner thread; directly calling the native destructor from Cleaner can violate the library's contract.

The solution is **explicit close in the right context**. If you still want a fallback, the action might only log a warning/leak or request dispatching work to the right owner thread via an appropriate mechanism; there is no guarantee the request will be processed if the owner thread/process has died.

### Cleanup That Can Block for Long or Produce Important Errors

The Cleaner thread serves many actions; an action that performs long I/O, invokes Java callbacks, waits on locks, or executes a complex destructor can delay other actions. Cleanup tasks should be short, safe, independent of the phantom-reachable object, and minimize blocking.

If `close` can throw an error that needs to be surfaced to the caller, design an **explicit close path** with clear error/exception return. Cleaner remains only a fallback that cannot guarantee error reporting like `close`. In the example, `free` is used because it can release simply, with no business semantics needing error reporting.

### Resources Related to Transactions or Flushing

For example, writing native files, flushing database transactions, committing messages, sending data to a device: putting decisive operations into Cleaner can cause data loss or violate transactions. **Explicit close/commit/rollback is mandatory**, handling failures in Java code that has the authority to decide business outcomes.

## 11. Debugging and Testing Native Lifecycles

A reasonable test suite should be divided into two groups: **deterministic tests** for explicit close and **best-effort observations** for Cleaner fallback.

### Deterministic Tests

- Create wrapper, call native operation, then `close`: confirm it can no longer be used.
- Call `close` a second time: no `double free` or crash occurs.
- Call `read` after close: throws `IllegalStateException` in Java before touching the native pointer.
- Throw an exception inside `try-with-resources`: confirm close is still called; if close also throws, check suppressed exception.
- Concurrent read/close: verify no use-after-free across all handle access paths.
- Constructor fails after native allocation: verify cleanup occurs in the exception branch.
- Stress test many `open/read/close` cycles, monitoring native memory, file descriptors, and release logs. When appropriate, AddressSanitizer, Valgrind, or an OS-appropriate native profiler can be used.

### Do Not Write Unit Tests That Rely on GC as a Deadline

Example of what **not** to do:

```java
NativeBuffer buffer = new NativeBuffer(10);
buffer = null;
System.gc();
Thread.sleep(100);
assert nativeAllocationCount() == 0; // Not guaranteed!
```

GC may not collect, the Cleaner action may not have run yet, and 100ms is not part of the contract. If you must test the Cleaner fallback, use a separate integration test with a deadline per test harness requirements and accept environment-dependent results; **do not use it as a standard to guarantee release in the application**.

For JNI debugging, `-Xcheck:jni` on HotSpot/OpenJDK also helps detect some JNI violations, but **cannot replace** handle ownership protection and read/close synchronization. Bugs like double-free or C pointer use-after-free usually require sanitizers and dedicated native testing.

## 12. Common Misconceptions and Mistakes

| Misconception | Why it is wrong | Correct approach |
| --- | --- | --- |
| "Java has GC so there is no need to free malloc memory" | GC does not own arbitrary C allocations | Native allocation must have native release |
| "Setting `buffer = null` then `System.gc()` is equivalent to close" | GC has no deadline; Cleaner may not have run | Explicit `close()` |
| "Cleaner runs when the object goes out of scope" | Leaving source scope does not mean phantom reachability or immediate action scheduling | Use `try-with-resources` |
| "Using Cleaner means the JVM always cleans up at shutdown" | Not guaranteed on System.exit, crash, or killed process | Close before shutdown while flow is still under control |
| "Cleaner action can call `this.nativeFree()`" | Action holds owner => owner is not phantom reachable | Separate `static State` without capturing owner |
| "AtomicLong getAndSet(0) prevents all races" | Only prevents repeated release; does not prevent read-vs-free | Synchronize/manage borrow, use reachability fence |
| "Only `synchronized close()` is needed" | Unsynchronized native operations can still hold a stale handle | Synchronize **all** handle usage paths |
| "Cleaner can call destructor on any native thread" | Resource may be thread-affine | Close on the right thread/context |
| "After calling free, the old long address can still be used" | Use-after-free, can crash JVM | Zero handle, check closed before JNI |
| "A large native buffer will make heap GC run in time automatically" | Heap pressure does not fully reflect native resource pressure | Deterministic close, quota, observe native metrics |
| "All errors during close can be ignored" | Can lose data, leak resources, or violate transactions | Design error reporting for explicit close |

## 13. Checklist for Reviewing a JNI Wrapper

1. **Ownership:** Who owns the native handle? Is the creator or receiver responsible for closing? When passed across FFI/JNI, is the handle copied elsewhere without transferring ownership?
2. **Acquisition:** If creating the native resource succeeds but the subsequent registration/constructor step fails, is cleanup done with `finally`/catch?
3. **Explicit close:** Does the wrapper have `AutoCloseable` and `close` compatible with `try-with-resources`? Does the API document the state after close?
4. **Double-free:** Does repeated close cause duplicate release? Does state transition atomically from OPEN to CLOSED?
5. **Use-after-free:** Does close wait for native operations currently using the resource? Do all read/write/methods share the same synchronization protocol?
6. **Cleaner reachability:** Does the cleanup action hold a strong reference to the owner? Did it accidentally use a non-static inner class, lambda, or method reference capturing `this`?
7. **Cleaner limitations:** Is cleanup safe on the Cleaner thread? Could there be blocking, JNI callbacks, exceptions, or thread affinity?
8. **Reachability fence:** Is there a risk the owner is considered unreachable by JIT while the native method still uses the raw pointer? Is `Reference.reachabilityFence(owner)` placed appropriately after the last use?
9. **Errors:** How are native release failures reported? Are exceptions swallowed by the Cleaner thread? Does closing mask the primary error?
10. **Tests:** Are there deterministic unit tests for close, close twice, use-after-close, constructor failure, concurrent close/read, and exception in scope?

## 14. Self-Check Questions

**Question 1.** A Java wrapper only holds a `long address` to `malloc`. Why cannot GC automatically replace `free(address)`?

**Answer:** GC manages Java heap objects and reachability; it does not understand the contract of the C allocation attached to `long`, and does not automatically call a custom destructor. Native resources require explicit release code and clear ownership.

**Question 2.** Does `System.gc()` guarantee that the Cleaner action runs before the next statement is executed?

**Answer:** No. GC may not happen immediately or may not process that object; the action runs asynchronously after the object becomes phantom reachable and Cleaner is notified.

**Question 3.** How does `cleanable.clean()` differ from "waiting for GC to invoke Cleaner"?

**Answer:** `clean()` is called explicitly and triggers the cleaning action immediately in the operating thread, at most once; waiting for GC/cleaner thread is asynchronous with no deadline.

**Question 4.** Why is a lambda like `() -> nativeFree(this.address)` unsuitable as a Cleaner action?

**Answer:** Because it captures `this`; Cleaner holds the action, the action holds the owner, so the owner may never become phantom reachable to trigger automatic cleanup.

**Question 5.** Has `AtomicLong.getAndSet(0)` solved all concurrency issues?

**Answer:** Not yet. It helps avoid double-free if multiple cleanups are triggered together, but does not prevent another thread that already fetched the pointer from continuing to use it while close just freed it. You must synchronize/manage handle usage rights.

**Question 6.** Does `Reference.reachabilityFence(this)` replace `synchronized`?

**Answer:** No. The fence keeps the owner strongly reachable up to a defined point against GC-based cleanup; `synchronized` protects against concurrent explicit close. The two mechanisms solve two different kinds of races.

**Question 7.** A native resource needs to be released on the thread that created it. Should release be called directly from the Cleaner thread?

**Answer:** Not by default. Thread/context ownership must be respected; use explicit close on the right thread or design an appropriate fallback, while not relying on the fallback to guarantee a deadline.

**Question 8.** A Java request has finished with a native buffer and needs to release it immediately to serve the next request. Which mechanism should be chosen?

**Answer:** `try-with-resources` and `close` at the end of the scope/request, checking for release errors if any. Cleaner/GC are only fallbacks and do not guarantee release timing.

## Official Documentation

- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Oracle Java SE 17 — Cleaner and Cleaner.Cleanable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Oracle Java SE 17 — Cleaner.Cleanable.clean()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)
- [Oracle Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object))
- [Oracle Java SE 17 — JVM GC: Other Considerations / Cleaner](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html)
- [Oracle Java SE 17 — JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — javac -h](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Conclusion:** **Explicit `close()` is the primary contract for JNI lifecycle**; `try-with-resources` enforces the contract at a known time. **`Cleaner` is a fallback with no deadline guarantee** and should only run short, owner-independent cleanup that is safe for the executing thread. **GC does not own native handles and cannot replace timely free/close**.
