# Defining Native Handle Ownership Bound to a Java Object

## Objectives

A Java object can represent a resource created in C/C++: a memory region allocated with `malloc` or `new`, a socket, a file descriptor, a graphics library object, a codec context, a database connection, or a struct with internal state. A Java object lives in the heap managed by the JVM; a native resource, on the other hand, follows the **allocation/deallocation rules of the native library itself**. Therefore, a `long handle` field in Java **does not automatically create ownership or a release mechanism**.

This lesson focuses on answering these questions: **Who creates the handle? Who owns the resource? Who only borrows it? When can it be used? Who closes it, how many times is it closed, and what happens when the Java object is garbage collected?**

After studying this lesson, you will be able to:

- Distinguish between a **JNI reference**, an **opaque native handle**, a **native pointer**, and the actual resource that the pointer/handle points to.
- Define **unique ownership**, **borrowed handle**, **shared ownership**, and **ownership transfer** models using clear API contracts.
- Build a Java `AutoCloseable` wrapper with open/closed states, a `0L` sentinel, an idempotent `close()`, and post-close access control.
- Call JNI properly using a Java 17 + C example with `nativeCreate`, `nativeRead`, `nativeIncrement`, and `nativeDestroy`; understand the safety limits of encoding a pointer as a `jlong`.
- Prevent `double free`, `use-after-free`, native memory leaks, handle type mismatches, `close`/operation races, and mid-operation error handling issues.
- Know how to use `Cleaner` as a fallback rather than a replacement for explicit lifecycle management.
- Design and test an ownership contract clear enough to be reviewed at the JVM–native boundary.

## 1. A Java object is not synonymous with a native resource

Consider a Java class describing a native counter:

~~~java
final class NativeCounter {
    private long handle;
}
~~~

`handle` is just **64 bits of data** in Java. It can represent:

1. A native address encoded as an integer (pointer-as-handle convention).
2. A lookup token/ID in a native library's registry table.
3. An OS descriptor or opaque value returned by an SDK.
4. An index plus a generation counter to detect stale handles.

**None of these representations automatically enforce ownership.** Nor should `long handle` be confused with `jobject`:

| Concept | Who manages it? | What is it? | Released by what? |
|---|---|---|---|
| Java object, e.g. `NativeCounter` | JVM/GC | Java instance containing fields and methods | GC manages the object's heap memory |
| `jobject` / `jclass` local JNI reference | JVM/JNI | Reference valid within a native frame | `DeleteLocalRef` or when the frame ends |
| JNI global reference | JVM/JNI | Root keeping a Java object alive across native calls | `DeleteGlobalRef` |
| JNI weak global reference | JVM/JNI | Weak root, does not keep the object alive | `DeleteWeakGlobalRef` |
| `jlong` native handle | Library convention | Integer/token with meaning defined by the API | **Not automatically released** |
| `malloc`-allocated state | C/native allocator | C memory region | Matching `free`, exactly once |
| `new`-allocated C++ object | C++ allocator | C++ instance | Matching `delete`, exactly once |
| OS socket/file handle | OS/native SDK | Operating system resource | `close`/`closesocket`/platform-specific destroy API |

For example: GC can reclaim `NativeCounter`, but if `handle` holds an address allocated by `malloc`, the JVM **does not automatically call `free`** based on that numeric value. Conversely, `DeleteGlobalRef` only removes a JNI reference to a Java object; it **does not free** a `malloc` pointer stored in a Java field.

Therefore, lifecycles must be designed across **two worlds**: Java memory managed by GC and native resources with a specific owner.

## 2. Define the ownership contract before writing the API

A native handle may be accessed in multiple places, but each release must have a **single valid rule**. Document clearly in the API documentation:

- **Creation source:** `nativeCreate`, an SDK API, a factory, or a function returning a borrowed handle?
- **Owner:** A Java wrapper, a native manager, a process-wide registry, or another C++ object?
- **Caller permissions:** Allowed to read/write, store, copy, transfer ownership, or call destroy?
- **Validity scope:** From creation until `close`, until the end of a callback, until the end of a native session, or based on a refcount?
- **Who releases it and with which function:** `nativeDestroy`, `free`, `delete`, SDK release; matching allocator and version.
- **Post-close rule:** The handle is invalid; every operation must report an error or return a clear state, **never** dereferencing the old address.
- **Thread-safety:** Can operations, callbacks, close, and a background Cleaner run concurrently?
- **Errors and cancellation:** If initialization fails partway through, who releases the already-acquired resources? If `close` fails, can it be retried or must further use be blocked?
- **Library boundaries:** Does the handle remain valid after native library unload, process restart, or class loader unload?

### Four ownership models

| Model | Meaning | Who is allowed to destroy? | When to use |
|---|---|---|---|
| **Unique ownership** | One owner manages the lifecycle | Only the owner (or a management layer acting on its behalf) | Each Java wrapper owns exactly one native resource |
| **Borrowed/non-owning** | Only borrows permission to use within a stated duration | **Must not** destroy | Callbacks, getters returning an internal view/handle |
| **Shared/refcounted ownership** | Multiple owners, each holding a retained right | Releases its own right; native destroys only on the last release | Objects shared across wrappers/threads |
| **Ownership transfer (move)** | Owner A hands off ownership to B | B after transfer; A must be invalidated | Native factories or APIs returning ownership |

**Never turn a borrow into ownership by copying a `long`.** Copying the bit pattern of a handle does not call `retain`, does not grant additional ownership, and does not extend its lifetime.

An example contract should be written in concrete terms:

> `createNative(initial)` returns a new **owned** handle. Each successful handle belongs to a single `NativeCounter`. `readNative` and `incrementNative` only **borrow** the handle for the duration of the call. `destroyNative` takes ownership of the handle, frees the resource exactly once, and invalidates the handle. After `close()`, the Java wrapper does not invoke any operation with the old handle.

This definition matters more than whether the field in Java is named `pointer`, `address`, or `handle`.

## 3. States and invariants for a unique owner

For a simple owner class, we use a state machine:

~~~text
       Java constructor
              |
              v
   nativeCreate(...) succeeds
              |
              v
        OPEN (handle != 0)
           |        |
           |        +--- value()/increment(): temporarily borrows handle
           |
           v
    close(): changes state
           |
           v
        CLOSED (handle == 0)
           |        |
           |        +--- any operation: IllegalStateException
           |
           +--- calling close() again: does nothing
~~~

If `nativeCreate` fails, the object **must not be published** in the OPEN state with an invalid handle. If `nativeDestroy` cannot fail (like `free` on a valid pointer in the example), `close` can set the handle to `0` and then destroy once.

Minimum invariants:

1. `OPEN` only when the handle currently represents valid native state.
2. `CLOSED` when the handle equals the sentinel `0L`; only use this sentinel if the native API guarantees it never issues that value as a valid handle.
3. An **owned** handle must never have two independent Java wrappers calling native destroy on it.
4. No native operation may use the resource **after** destruction completes.
5. Calling `close` repeatedly on the **same wrapper** must be harmless (idempotent on the Java side).
6. Before a resource is successfully handed over to a new owner, mid-way errors must be cleaned up by whoever still holds ownership.
7. Do not treat a negative `long` sign as proof of an invalid handle: if encoding a raw pointer, the high bit may be set; compare against the defined sentinel, **do not** assume `handle > 0`.

**Idempotence in the wrapper does not mean native `free` is idempotent.** Calling C standard `free` a second time on the same already-freed non-null pointer is undefined behavior. The Java wrapper must ensure `nativeDestroy` **receives each handle to be destroyed at most once**, or the native registry must have an independent deduplication mechanism.

## 4. Java design pattern: AutoCloseable as the primary closing path

For resources with a clear lifecycle such as files, contexts, or sessions, use `AutoCloseable` and `try-with-resources` to close proactively. Do not wait for GC.

~~~java
try (NativeCounter counter = new NativeCounter(5)) {
    System.out.println(counter.value());
    System.out.println(counter.increment());
} // close() is called when exiting the block (even if a Java exception occurs)
~~~

This is an **illustrative Java snippet**; the full runnable class is in the next section. `AutoCloseable` lets Java guarantee that `close()` is called upon exiting `try` by language mechanism. It does not dictate how the native resource is destroyed; you must implement `close` properly yourself.

Design decisions in the wrapper class:

- **Hide the handle:** make it `private`; normal APIs should not expose a `long` that callers can arbitrarily forge or pass between wrappers.
- **Keep a single owner:** no copy constructor creating a second wrapper from the same raw address without performing ownership transfer/refcounting.
- **Every method using the handle checks OPEN before calling JNI.**
- **Synchronize `close` and native operations on the same lock** to prevent close from running concurrently with a call currently using the handle.
- **Do not add complex Java logic after acquiring native state but before the owner is ready:** if that phase can throw, use `try/finally` cleanup when the factory cannot return the object.
- **Do not keep native resources alive indefinitely** just because a Java object is still referenced; provide `close` so the application can release resources early.

## 5. Complete Java 17 + JNI C example: one owner, one release

This exercise uses a native `CounterState` struct on the C heap. The Java wrapper holds a handle encoding the struct's address. `close` is responsible for destroying the state and preventing reuse. This is an **educational pattern for a trusted internal handle inside a single wrapper**, not a system for validating untrusted handles or sharing pointers arbitrarily across multiple Java objects.

### 5.1. Java file: `NativeCounterDemo.java`

~~~java
public final class NativeCounterDemo {
    static {
        System.loadLibrary("nativecounterdemo");
    }

    private static native long createNative(int initial);
    private static native int readNative(long handle);
    private static native int incrementNative(long handle);
    private static native void destroyNative(long handle);

    public static final class NativeCounter implements AutoCloseable {
        private long handle;

        public NativeCounter(int initial) {
            long created = createNative(initial);
            if (created == 0L) {
                throw new OutOfMemoryError("Cannot allocate NativeCounter");
            }
            handle = created;
        }

        private void requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("NativeCounter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return readNative(handle);
        }

        public synchronized int increment() {
            requireOpen();
            return incrementNative(handle);
        }

        public synchronized boolean isClosed() {
            return handle == 0L;
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return; // Closing a second time does not free again.
            }

            long owned = handle;
            handle = 0L; // Invalidated in Java before nativeDestroy.

            destroyNative(owned); // Called only once for this handle.
        }
    }

    public static void main(String[] args) {
        NativeCounter counter = new NativeCounter(5);

        try (counter) {
            System.out.println("before=" + counter.value());
            System.out.println(
                    "afterIncrement=" + counter.increment());
            System.out.println("afterRead=" + counter.value());
        }

        System.out.println("closed=" + counter.isClosed());

        counter.close();
        System.out.println(
                "closedTwice=" + counter.isClosed());

        try {
            counter.value();
        } catch (IllegalStateException error) {
            System.out.println("afterClose=" + error.getMessage());
        }
    }
}
~~~

**Key ownership decisions:**

- `NativeCounterDemo` contains `private static native` JNI methods; normal application code cannot call them directly with an arbitrary handle number.
- `new NativeCounter(5)` receives exactly **one** native allocation. The `handle` field is only assigned when creation succeeds.
- `value()` and `increment()` borrow the handle while the method runs without taking new ownership; the native code is not free to release the resource in these two calls.
- `value()`, `increment()`, and `close()` are all `synchronized` on the **same Java object**, so normal calls to this wrapper cannot read the handle and free it concurrently. A `close` from another thread cannot cut in while `readNative` is running.
- `close()` replaces the handle with `0L` before calling destroy. `destroyNative` in the example only performs `free` on a valid pointer and does not report errors; this ordering ensures a subsequent close will not call `free` again.
- After closing, `value()` throws `IllegalStateException` in **Java** before passing the old pointer to C.
- `try (counter)` is Java 9+ syntax for effectively final variables; Java 17 supports it. After the block, we still use the Java wrapper to observe the CLOSED state, **not** to use the freed native resource.

**Explicit limitation:** synchronization here only protects public calls on the **wrapper itself**. If another native module retains/copies the raw pointer, or a user breaks encapsulation with reflection/Unsafe, the JVM has no way to detect the stale pointer. This pattern does not replace a native registry with validation/refcounting when handles are shared or untrusted.

### 5.2. Generating the JNI header

In the directory containing the Java file, with JDK 17 or later:

~~~bash
javac -h . NativeCounterDemo.java
~~~

This command compiles `NativeCounterDemo.class`, `NativeCounterDemo$NativeCounter.class`, and generates `NativeCounterDemo.h` from the signatures of the native methods. Using `javac -h` ensures the exported JNI function names match the Java declarations exactly; whenever you change a class/package name or signature, you need to regenerate the header and rebuild the native library.

### 5.3. C file: `nativecounterdemo.c`

~~~c
#include "NativeCounterDemo.h"

#include <stdint.h>
#include <stdlib.h>

typedef struct {
    jint value;
} CounterState;

/*
 * Only use with a trusted handle, created by createNative,
 * not yet destroyed, and kept alive by a single owner.
 */
static CounterState *state_from(jlong handle) {
    return (CounterState *)(uintptr_t)(uint64_t)handle;
}

JNIEXPORT jlong JNICALL
Java_NativeCounterDemo_createNative(
        JNIEnv *env, jclass declaringClass, jint initial) {
    (void)declaringClass;

    CounterState *state = malloc(sizeof *state);
    if (state == NULL) {
        jclass errorClass = (*env)->FindClass(
                env, "java/lang/OutOfMemoryError");
        if (errorClass != NULL) {
            (*env)->ThrowNew(
                    env, errorClass, "native malloc failed");
            (*env)->DeleteLocalRef(env, errorClass);
        }
        return (jlong)0;
    }

    state->value = initial;
    return (jlong)(uintptr_t)state;
}

JNIEXPORT jint JNICALL
Java_NativeCounterDemo_readNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)env;
    (void)declaringClass;

    CounterState *state = state_from(handle);
    return state->value;
}

JNIEXPORT jint JNICALL
Java_NativeCounterDemo_incrementNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)declaringClass;

    CounterState *state = state_from(handle);
    if (state->value == INT32_MAX) {
        jclass errorClass = (*env)->FindClass(
                env, "java/lang/ArithmeticException");
        if (errorClass != NULL) {
            (*env)->ThrowNew(
                    env, errorClass, "counter overflow");
            (*env)->DeleteLocalRef(env, errorClass);
        }
        return (jint)0;
    }

    ++state->value;
    return state->value;
}

JNIEXPORT void JNICALL
Java_NativeCounterDemo_destroyNative(
        JNIEnv *env, jclass declaringClass, jlong handle) {
    (void)env;
    (void)declaringClass;

    CounterState *state = state_from(handle);
    free(state);
}
~~~

**Step-by-step explanation:**

1. `createNative` allocates `CounterState` with `malloc`. After a successful allocation, C sets `value` and returns the handle as `jlong`, transferring ownership to the Java wrapper.
2. `readNative` and `incrementNative` only **borrow** the pointer and do not `free` it. `readNative` does not retain the pointer after returning; `incrementNative` updates it within the lifetime guaranteed by the owner.
3. `incrementNative` checks `INT32_MAX` to avoid signed integer overflow of `jint` (corresponding to Java's 32-bit `int`). If it overflows, it throws `ArithmeticException` via JNI; the Java wrapper remains **OPEN**, because a failed addition does not mean the native state was freed.
4. `destroyNative` frees the exact allocation with `free`. For this handle, any `readNative`/`incrementNative` call afterward would be a use-after-free, so the wrapper prevents calling them again.
5. There is no `DeleteLocalRef` for the native pointer because it is not a JNI object reference. In the two exception-throwing branches, `errorClass` is a local JNI reference from `FindClass`, so it is properly released with `DeleteLocalRef`.
6. `uintptr_t` expresses the pointer ↔ integer conversion on platforms that have a sufficiently wide integer type. **This is an ABI-dependent implementation pattern**: this code assumes the platform's pointers can round-trip through `uintptr_t` and a 64-bit `jlong`. It does not automatically fit capability-pointer architectures, pointers wider than 64 bits, or systems with special handle rules.
7. **There is no native validation step in `state_from`.** If the input is a forged number, null, an already-freed handle, or concurrently used by another owner, dereferencing/freeing it can cause a crash or undefined behavior. That is why the Java API intentionally does not expose `handle`, and a registry mechanism is needed if protection against untrusted input is required.

### 5.4. Compiling and running

Choose **one** operating system matching the JVM you are using. `JAVA_HOME` must point to a JDK 17+ with JNI headers and a compatible architecture.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativecounterdemo.c -o libnativecounterdemo.so

java -Djava.library.path=. NativeCounterDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  nativecounterdemo.c -o libnativecounterdemo.dylib

java -Djava.library.path=. NativeCounterDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" nativecounterdemo.c /Fe:nativecounterdemo.dll
java -Djava.library.path=. NativeCounterDemo
~~~

These commands rely on `System.loadLibrary("nativecounterdemo")` and the JVM's standard filename conventions on each OS. On Windows, you must use a Developer Command Prompt with `cl` configured. The native binary must match the **JVM process** architecture, C runtime, and dependent libraries; otherwise, you may hit `UnsatisfiedLinkError` immediately at load time, before any output.

### 5.5. Expected output

When compilation, loading, and execution succeed:

~~~text
before=5
afterIncrement=6
afterRead=6
closed=true
closedTwice=true
afterClose=NativeCounter is closed
~~~

From the output:

- The counter starts at 5, increment increases it to 6, and reading it again still returns 6.
- Exiting `try` calls `close` → the handle becomes `0L` and the native state is freed.
- Calling `close` again is a no-op in the wrapper, without a second `free`.
- After close, `value` throws `IllegalStateException` from Java **before** calling JNI, avoiding use of the invalidated pointer.

This is the deterministic logical output for **sample code in the right environment**; do not treat stdout as proof that it can prevent all lifetime bugs in a complex application. For memory safety, you must inspect resource ownership and other execution paths, including concurrency.

## 6. Critical mistake: two wrappers owning the same handle

Suppose somehow two Java objects hold the same pointer:

~~~text
Java wrapper A ---> 0xABC ---> C resource R
Java wrapper B ---/

A.close()  ---> free(R)
B.value()  ---> dereference freed R    (use-after-free)
B.close()  ---> free(R) again          (double free)
~~~

**This cannot be fixed** with `if (handle != 0)` in each wrapper: when `A` sets *A's field* to zero, *B's field* still holds the old number. The states of the two wrappers are not linked.

There are three proper ways to handle this, depending on the contract:

1. **Unique owner:** disallow creating B from the same resource. If transferring A → B, ensure the transfer operation revokes A's ownership and grants new ownership to B atomically according to the model used.
2. **Shared ownership:** the native object has a reference count or shared control block. Each wrapper receives an **independent retain right**, and each wrapper's `close` only releases its own right; only the final release destroys the resource.
3. **Borrowed view:** B must never destroy. B is only used while owner A is alive and has an appropriate lease/lock; after A.close, B must not be accessed. Do not rely solely on a copied `long` to check this.

If an SDK API returns `getHandle()` but the documentation says “owned by the library, do not free”, that is a **borrowed handle** even if it is represented by a pointer. Do not attach a `Cleaner` that automatically calls `free` on this value.

## 7. Concurrent close and operation: why is synchronization required?

The following code is a **counterexample**:

~~~java
public int value() {
    if (handle == 0L) {
        throw new IllegalStateException("closed");
    }
    return readNative(handle);
}

public void close() {
    if (handle != 0L) {
        destroyNative(handle);
        handle = 0L;
    }
}
~~~

If thread T1 has just checked that the handle is valid, T2 can interleave with `destroyNative`, and then T1 calls `readNative` with the freed pointer. In addition, two concurrent `close` calls can both see nonzero and call destroy twice. This is an **illustrative Java anti-pattern**, not code permitted in production.

### Solution for the single-wrapper pattern

In the full runnable example, `value`, `increment`, and `close` are all `synchronized` on the same Java object, so:

~~~text
T1 enters synchronized value()
    ---> readNative(handle) completes
    ---> T1 exits monitor

T2 enters synchronized close()
    ---> handle = 0
    ---> destroyNative(old)
    ---> T2 exits monitor
~~~

Or T2 may enter before T1; in that case T1 sees a zero handle and throws an error. **There is no third ordering** in which one thread closes the resource in the middle of another thread's native call, as long as every access path to the same resource goes through the same wrapper/monitor and the native method does not hand the handle off to an independent agent.

Simply adding `volatile long handle` is **not enough**: volatile helps with visibility/ordering of field reads and writes, but does not keep the resource alive throughout `readNative`. `AtomicLong.getAndSet(0)` can prevent two closes from both freeing, but **cannot by itself prevent** an operation that already read the old handle from being interrupted by close. You need a lock, refcount/lease, or a registry that actually manages in-flight usages.

### When the JVM calls back into Java during a native operation

Java monitors are **reentrant**. If a native operation calls back into another Java method that can `close()` the same owner on the **same thread**, the monitor can be re-acquired and the resource closed **right in the middle of the native call**. The simple `synchronized` pattern above is safe because `readNative`/`incrementNative` are leaf operations that **do not call back** and do not export the handle.

For native APIs with callbacks or reentrant logic, you need an `inUse`/`closing` state, a lease, or a native-side reference count; closing must be deferred until all in-flight borrows complete. **Do not** assume `synchronized` solves all kinds of reentrancy.

### Using multiple wrappers or non-Java threads

A native handle accessed through a process-wide registry, a dedicated C thread, a background worker, or a callback can escape the scope of the wrapper's monitor. In that case, locking on wrapper A **does not protect** wrapper B or another C thread. Native ownership design must participate in synchronization where the resource is actually used.

## 8. Native registry and generation tokens: when is it better than a raw pointer?

`jlong` does not have to hold a pointer. For libraries requiring validity checks at the native boundary, one option is a registry table:

~~~text
Java:
  long token = 0x0007_0000002A   (encoded example, not an address)

Native registry (locked/synchronized):
  slot 42; generation 7 ---> CounterState*
  slot 43; generation 2 ---> FileState*

nativeRead(token):
  decode slot=42, generation=7
  acquire protected lease / retain
  validate active + correct resource type
  use CounterState
  release lease

nativeDestroy(token):
  mark slot 42 closing/closed, invalidate token
  wait/defer until all in-flight leases end
  release resource exactly once
~~~

This is a **conceptual diagram**, not standalone code or a standard token format. A practical registry needs:

- Resource type and access permission checks; do not allow a `FileHandle` to be used as a `CounterHandle`.
- A generation counter so an old token does not mistakenly point to a new resource when a slot is reused (**ABA/stale handle**).
- Protection of lookup → use with a lock/lease/refcount synchronized with destroy; simply checking the token and releasing the lock **before** dereferencing still has a race.
- A plan for when the generation counter wraps, when the process reloads, and when the library/classloader unloads.
- Clear rules for ownership transfer, retain, and release; do not just add a table while ignoring the lifecycle.
- Never take a token from untrusted external input and treat it as permission to dereference an arbitrary raw pointer.

**Benefit:** can return an “invalid/stale handle” error instead of dereferencing a bad address. **Cost:** lookup and synchronization overhead, and the registry structure needs memory, refcount, and shutdown management.

For an internal wrapper with few operations, a raw pointer + unique owner may suffice. For public APIs, plugin systems, multiple owners, or complex concurrency, a registry/opaque ID is usually easier to control.

## 9. Ownership transfer: never leave two owners after a “move”

A factory can create a native resource in C, then hand ownership to Java. The right contract is:

~~~text
Native create():
  allocate R
  |
  +-- failure during preparation: native free(R)
  |
  +-- ownership transfer succeeds:
           Java wrapper owns R
           native factory does NOT free(R) anymore
~~~

If a native API transfers a handle from wrapper A to B, it must invalidate A and only allow B to destroy. The transfer must be synchronized with active borrows. **Do not** write `new Wrapper(a.handle)` and let both wrappers `close`.

A safer pattern is for a Java factory to receive the handle and immediately assign it to a clearly scoped owner; if constructing the Java wrapper has steps that might throw after the native allocation, use `try/finally` or a separate transaction:

~~~java
long acquired = createNative(5);
boolean transferred = false;
try {
    NativeCounter wrapper = adoptOwned(acquired);
    transferred = true;
    return wrapper;
} finally {
    if (!transferred && acquired != 0L) {
        destroyNative(acquired);
    }
}
~~~

This is an **illustrative snippet** for a factory flow (assuming `adoptOwned` exists, checks preconditions, and **does not itself destroy the handle when reporting an error**). If the factory hands the resource off elsewhere and then throws an exception later, setting the `transferred` flag must accurately reflect the moment of ownership transfer; a code snippet cannot replace a defined ownership protocol.

**Document semantics in every API**: names like `borrow`, `retain`, `adoptOwned`, `detachOwned`, and `release` usually communicate lifetime better than a generic `fromHandle` function. Names must still be accompanied by documentation and tests.

## 10. `Cleaner` is a fallback, not the primary lifecycle

Java GC only manages the Java heap. If code forgets `close()` and the wrapper becomes unreachable, the native state can persist until the process exits. A `Cleaner` can register an action to release the resource when the JVM detects the referent is phantom-reachable. However:

- **There is no guarantee when, or even whether, a cleaning action will run before the process exits.** Therefore `Cleaner` does not replace `AutoCloseable`.
- The cleaning action **must not hold a strong reference to the owner itself**, otherwise the owner can never become phantom-reachable. Avoid lambdas like `() -> this.close()` or non-static inner classes that accidentally capture `this`.
- Explicit `cleanable.clean()` allows triggering the action during `close`, but the action must guard against double invocation using valid ownership logic.
- Cleaner can run on a different thread from the wrapper's methods; operations and cleaner destroy need shared synchronization/leases.
- Do not assume every native destructor is safe to run on a cleaner thread: some libraries require destruction on a specific thread, UI context, or event loop.
- If a Cleaner action calls a JNI static native method from Java, library loading and thread context must be valid. A native pointer does not automatically carry a JNI environment for an arbitrary thread.

### Illustrating a separate state mechanism for Cleaner

~~~java
import java.lang.ref.Cleaner;

final class ResourceOwner implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private long handle;

        State(long handle) {
            this.handle = handle;
        }

        synchronized long requireOpen() {
            if (handle == 0L) {
                throw new IllegalStateException("closed");
            }
            return handle;
        }

        @Override
        public synchronized void run() {
            if (handle != 0L) {
                long old = handle;
                handle = 0L;
                nativeDestroy(old);
            }
        }
    }

    private static native void nativeDestroy(long handle);

    private final State state;
    private final Cleaner.Cleanable cleanable;

    ResourceOwner(long ownedHandle) {
        if (ownedHandle == 0L) {
            throw new IllegalArgumentException("invalid handle");
        }
        state = new State(ownedHandle);
        cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
~~~

**This is a standalone snippet illustrating Cleaner structure, not a complete program**: you must define/load the native library and have a factory issuing a valid `ownedHandle`; never pass an arbitrary number to `nativeDestroy`. `State` holds no reference to `ResourceOwner`, avoiding a strong reference cycle from the cleaning action back to the owner. Making `run()` synchronized prevents two concurrent cleanups on the same state; a method using the resource **must also synchronize on the same State for the duration of the native call** if it wants to be safe against Cleaner.

`requireOpen()` only returns the raw handle after releasing `State`'s monitor: **that is not enough** to protect a subsequent native call before Cleaner runs. To implement a real `read()`, design `synchronized int read() { check; return nativeRead(handle); }` **inside State**, or use a lease/refcount. The purpose of the Cleaner snippet above is to illustrate separating state from the referent and one-time release ownership, **not** to claim the full pattern is already thread-safe for all operations.

With Java 17, `Cleaner` is the supported fallback mechanism. Do not use the `finalize()` finalizer for native lifecycle contracts: finalization has unpredictable timing and many safety/maintenance risks. When resources are scarce, explicit `close` design and leak monitoring remain the top priority.

### When is `Reference.reachabilityFence` needed?

If code extracts a raw pointer from a Java owner and uses it in an operation that does not keep a reference to the owner long enough, JIT/GC may consider the owner no longer reachable before the native use completes; Cleaner could then run early. `Reference.reachabilityFence(owner)` is a tool to keep an object reachable up to a defined point, but it **does not replace synchronization/leases** when someone else can call `close()` explicitly.

In the `NativeCounterDemo` example, synchronized instance methods hold the owner's own monitor throughout the native call, so the premature-cleanup issue via Cleaner does not arise (and the main example does not use Cleaner). In APIs using asynchronous native work or external callbacks, you must design separate keep-alive ownership matching the duration of the work.

## 11. JNI global references and native handles are two independent obligations

Suppose a native resource holds a reference to a Java callback to invoke later:

~~~c
/* Before an error/pending exception occurs, in the constructor. */
jobject saved_callback = (*env)->NewGlobalRef(env, callback);

/* When destroying the resource, if the callback reference is owned: */
(*env)->DeleteGlobalRef(env, saved_callback);
~~~

These are **illustrative JNI lines** inside a C function with valid `env`/`callback` variables. `NewGlobalRef` can fail; check for `NULL`. Once a callback global ref is successfully created, the native state owns **two kinds** of resources:

1. Native memory holding the struct.
2. A JNI global reference used to keep a Java object reachable across multiple JNI calls.

A proper destructor may have to `DeleteGlobalRef` and then `free` the struct. Calling only `free` on the struct will **leak the global reference**; calling only `DeleteGlobalRef` and forgetting `free` will leak native memory.

Keep in mind:

- A `jobject` local reference created in a native method must not be cached for use in subsequent callbacks/calls; if long-term storage is needed, use `NewGlobalRef` and `DeleteGlobalRef`.
- A global ref can keep a Java object alive unintentionally; that object may in turn retain other resources, causing a large leak.
- A weak global ref does not substitute for an owning reference; you must check whether the object has already been GC'd and promote it to a valid local reference if you want to use it.
- `JNIEnv*` is bound to a thread; another native thread must attach properly to use JNI, then detach when appropriate; do not share an env pointer across threads.
- `DeleteGlobalRef` is allowed while a Java exception is pending; however, most other JNI methods are **not allowed** in that state. Design destructors/cleanup so they do not make arbitrary extra JNI calls while an exception is pending.

Do not mistake `jlong` for a “long-lived Java reference”: it is only a primitive token, and **GC cannot keep native state alive based on a numeric pointer**.

## 12. Exception safety: a resource has only one cleanup path

Initialization can consist of multiple steps:

~~~text
malloc struct              OK
nativeOpenSocket           OK
NewGlobalRef(callback)     FAIL
Java wrapper has not received handle yet
~~~

Who must close the socket and `free` the struct? **The C factory**, because ownership transfer to Java has not completed. Java `close` cannot clean up a resource it has never received.

A simple C skeleton:

~~~c
NativeState *state = NULL;
jobject callback_global = NULL;

/* state = malloc(...); */
/* if (state == NULL) ... goto cleanup; */

/* state->socket = native_open(...); */
/* if (socket invalid) ... goto cleanup; */

/* callback_global = (*env)->NewGlobalRef(env, callback); */
/* if (callback_global == NULL) goto cleanup; */

/* When everything succeeds: attach to state, transfer ownership. */
/* return (jlong)(uintptr_t)state; */

cleanup:
    if (callback_global != NULL) {
        (*env)->DeleteGlobalRef(env, callback_global);
    }
    if (state != NULL) {
        /* Close socket if opened, then free(state). */
    }
    return (jlong)0;
~~~

This is an **illustrative skeleton, not a standalone C function**: the `NativeState` type and `native_open` are not defined. The key point is that each acquisition stage has a state flag/field sufficient to clean up the successful parts even if a later stage fails.

If a JNI call has already set a pending Java exception, JNI cleanup must be limited to permitted operations (such as `DeleteGlobalRef` or the corresponding `Release...` calls). Do not arbitrarily call `FindClass`/`ThrowNew` again while an exception is still pending. Native resources owned by C can still be cleaned up using the appropriate C/OS functions.

### What if Close fails?

In the main example, `nativeDestroy` calls `free` on a valid pointer and has no error-reporting mechanism. In practice, `closeNative` may need to flush a file, send data, close a connection, release a GPU context, or call an SDK destructor that can fail.

Contract decisions:

- Is closing **best-effort** or guaranteed to release?
- After a cleanup error, is the handle destroyed or still valid?
- Can it be retried, and could retrying cause a double-free?
- Are close errors reported to the caller via exception, status, or log?
- When `try-with-resources` has an error from the `try` body **and** `close` throws an error, Java handles suppression according to its mechanism; do not swallow close errors without a policy.

If a destructor can fail while leaving the resource alive, setting `handle=0` before destroying (as in the sample) can make retries impossible. In that case, you need an `OPEN → CLOSING → CLOSED/FAILED` state machine or an idempotent native release protocol—**do not copy the `free` pattern verbatim to these kinds of resources**.

## 13. Invalidated handles, security, and ABI

### Do not treat a raw pointer as a safe identifier

A `jlong` containing a real address is data particularly sensitive to internal assumptions: if a caller supplies `0x12345678` or an already-freed pointer and JNI dereferences it, the program can crash. **A pointer has no runtime tag** telling Java whether it is still alive or what struct type it belongs to.

Do not put raw native addresses into network protocols, databases, serialized Java objects, or public logs as a stable ID. When a process restarts, ASLR changes the address space layout and old pointers become meaningless. If a persistent ID is needed, design a business ID independent of the pointer.

### Data types and platforms

- `jlong` always corresponds to Java's 64-bit `long`. Native pointers may have different widths; `uintptr_t` exists on platforms that support an unsigned integer large enough to hold a pointer.
- Pointer ↔ integer conversion is implementation/ABI-dependent, not an absolute guarantee for every kind of pointer.
- Do not cast a `jobject` to `jlong` and use it like a `malloc` pointer; JNI references are opaque and have their own lifetime managed by the JVM.
- A JNI library must be built for the exact OS/CPU/ABI of the JVM, with matching allocators/deallocators. Do not return a pointer allocated by C++ `new` and free it via C `free`.
- Do not use the same `long` for multiple resource types without a type check. A wrong-type token can lead to an invalid cast and wrong destructor.

### Avoiding ABA and repeated frees

After `free(R)`, the allocator can reuse the same address for a new resource. A stale `long` carrying the address bits of R can suddenly point to a different object—the **ABA** bug. Comparing pointer values to detect stale handles is insufficient. Registry tokens with generations and invalidation, plus locks/refcounts, are usually a more suitable design whenever any path stores handles long-term or shares them.

## 14. The Java–native protocol must agree on closing

An example of a clear API contract:

| API | Input ownership | Output ownership | Effect |
|---|---|---|---|
| `nativeCreate(int)` | No input handle | Returns a new **owned** handle, or reports error | C creates native state; Java receives ownership |
| `nativeRead(long)` | **Borrowed** handle while OPEN | Returns Java primitive value | Does not retain handle after return |
| `nativeIncrement(long)` | **Borrowed** handle while OPEN | Returns value | Does not destroy or retain |
| `nativeDestroy(long)` | **Consumes owned** handle | No output handle | Destroys exactly one resource, old handle invalid |
| `NativeCounter.close()` | Wrapper owns handle | Does not transfer handle | Transitions wrapper to CLOSED, calls destroy at most once |
| `NativeCounter.value()` | Does not expose handle; internal borrow | Returns `int` | Throws `IllegalStateException` if CLOSED |

Several conventions should be stated clearly in the library's JavaDoc:

> **Thread-safety:** All instance methods operating on the handle are synchronized on the same wrapper. Do not supply the raw handle to asynchronous native code or another wrapper. This approach is insufficient for reentrant native callbacks or multi-owner systems.

> **Lifetime:** The resource is released when `close` succeeds; callers must use `try-with-resources`. There is no guarantee the native resource is cleaned up if the caller forgets `close` in a design without a Cleaner.

> **Failure:** A failed `createNative` does not return a usable owner; `readNative`/`incrementNative` do not consume ownership. `nativeDestroy` in the demo only frees a `malloc` allocation and does not report errors; other backends must have their own contracts.

> **Invalidation:** After `close`, every operation other than `isClosed`/`close` on the wrapper throws an error before calling JNI. Copies of the handle outside the wrapper (if any) are **not protected** by this rule.

Document the contract on both sides of the code review, not just as a comment on the `handle` field.

## 15. Testing lifecycle and concurrency

An ownership test suite does not just check “can create and can call”. Test the following scenarios:

| Test | Expected result |
|---|---|
| Create a resource then read/write | Operation executes while OPEN |
| `try-with-resources` exits normally | `close` called once, state becomes CLOSED |
| `try` body throws a Java exception | `close` is still called by language mechanism |
| Call `close` two or more times | No double-free; subsequent calls are no-ops or follow a specific contract |
| Call `value` after `close` | Clear Java error, no dereference of stale pointer |
| Two Java threads call `value` and `close` concurrently | With synchronized wrapper: either value completes before close, or sees CLOSED; no UAF |
| Native constructor/acquire fails partway through | All acquired resources are cleaned up, no half-baked owner |
| Native operation throws a Java exception | Ownership is not unintentionally destroyed; valid cleanup path remains |
| Copy the same handle into two independent owners | Must be forbidden or handled by registry/refcount; never two destroys for the same resource |
| GC occurs while resource is still OPEN | Do not rely on GC to determine when the native resource is freed |
| With `Cleaner` fallback | Does not keep owner alive via capture; action is designed with proper thread/lease; explicit close is primary |
| Callback/reentrant close | Mechanism forbids/defers close while native is borrowing, does not free mid-call |
| Native library unload/shutdown | No remaining resources/callbacks using code or global state of the unloaded library |

### How to track allocations and releases

In a test environment, you can add a **native** counter and assert the number of live resources after a test run, or use AddressSanitizer/Valgrind/a platform-appropriate leak detector. In debug builds, a registry can log tokens, resource types, owners, and OPEN/CLOSED states, **without logging raw pointers in production**.

A `System.gc()` test **does not** prove Cleanup will definitely run, because GC and Cleaner make no timing guarantees. Functional tests must call `close` proactively. Cleaner tests only verify the fallback under non-deterministic timing assumptions, without turning it into the primary contract.

With HotSpot, `-Xcheck:jni` helps catch some JNI misuse bugs (bad references, pending exceptions, etc.), but **does not replace** a sanitizer for the C heap or prove the correctness of ownership/locking.

## 16. Common bugs and how to fix them

| Symptom | Common cause | Fix |
|---|---|---|
| Java object disappears but native memory keeps growing | Only Java object GC'd, no `nativeDestroy` | `AutoCloseable`, `try-with-resources`, leak measurement; Cleaner only as fallback |
| Crash after `close()` | JNI still uses stale handle | Check OPEN and synchronize operation/close; native lease |
| Double-free | Two owners both call destroy or close is not idempotent | Single owner or explicit retain/release; close once |
| Java handle field is zeroed but native thread still uses pointer | Asynchronous native work is still running | Wait/defer destroy until in-flight usages complete |
| `volatile long handle` still has UAF | Visibility does not preserve lifetime across the JNI call | Lock/refcount/lease |
| Global JNI references leak | Native struct holds `NewGlobalRef` but destructor only calls `free` | `DeleteGlobalRef` then free the struct properly |
| C++ resource destroyed with `free` | Wrong allocator/deallocator | Use matching `delete`/SDK destroy |
| Handle looks valid but points to a wrong new object | Address/registry slot reused (ABA) | Generation token/registry and validation |
| Wrapper GC'd during background operation | Ownership does not keep object/resource alive until finished | Strong reference/lease/reachability fence depending on design |
| Cleaner runs on an unsuitable thread | Destructor requires UI/thread-affine context | Explicit close or dispatch cleanup to an allowed thread |
| Java constructor throws after native allocation | Transfer incomplete, resource not released | Factory with `finally` and explicit ownership commit |
| C calls Java while a pending exception exists in destructor | Cleanup invokes disallowed JNI APIs | Separate permitted cleanup and handle exceptions deliberately |

## 17. Self-check exercises

**Exercise 1 — who owns it?** A C API returns a `FILE*` opened by a factory. A Java wrapper holds the address number as a `long`. Once returned to Java successfully, who closes the file? **The owner specified in the API contract**, typically the wrapper via `close` and JNI destroy using `fclose` (not `free` directly on `FILE*`).

**Exercise 2 — borrowed handle.** Native method `getInternalHandle()` returns a pointer to state belonging to owner A. Java B saves the handle and calls nativeDestroy when done. What is wrong? **B only borrows it and must not destroy it**. To use it longer requires an explicit retain or a protocol guaranteeing A still owns it and stays alive for the entire borrow duration.

**Exercise 3 — double close.** Why is `if (handle != 0) { destroyNative(handle); handle = 0; }` unsafe across two threads without synchronization? Both threads can read nonzero and both destroy. Fix: `synchronized`/lock or an atomic state transition mechanism coordinated with operation lifetimes.

**Exercise 4 — read/close race.** Is atomic `getAndSet(0)` in close enough? **No**, if a prior operation already read the handle and is running or about to enter JNI. You need a lease/lock keeping the resource alive until the operation completes.

**Exercise 5 — raw handle.** Why not let clients pass an arbitrary `long` to `nativeRead`? Because it could be cast to an invalid pointer and dereferenced, causing a crash; you need encapsulation and, if input is untrusted, a registry lookup checking token/type/lifetime.

**Exercise 6 — Cleaner.** What is dangerous about writing `CLEANER.register(this, () -> this.close())`? The action captures `this` by strong reference, which can prevent the owner from becoming phantom-reachable. Use a `static State` separated from the owner and `cleanable.clean()` on explicit close.

**Exercise 7 — dual resource.** A native struct has a `jobject callbackGlobal` from `NewGlobalRef` and a `malloc` buffer. What must destroy do? **`DeleteGlobalRef`** in a valid JNI environment and **`free`** the buffer/struct with the matching allocator. These are two independent ownership obligations.

**Exercise 8 — failed close.** If a native SDK `destroy` can fail while leaving the resource unreleased, should you always set the handle to 0 before calling it? Not by default. You need to define the post-error state, retry rules, or native idempotence. The pattern in this lesson applies to `free`, which does not report errors.

## References

- [Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): JNI references, Java/native method invocation, exception handling, and global/local refs.
- [Java SE 17 — JNI Design: Global and Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): lifecycle and scope of JNI references.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): explicit resource closing contract.
- [Java SE 17 — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): how to register cleaning actions, state, and GC limitations.
- [Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): keeping a referent reachable up to a program point.
- [Java SE 17 — try-with-resources (JLS `14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): close, exceptions, and suppressed exceptions.

## Key takeaways

**A native handle is an opaque value, not a self-managing lifecycle object.** A Java object holding a handle must have an **ownership contract**: creation, borrowing, transfer, release, synchronization, and error handling.

- **Unique owner:** one wrapper is responsible for destroying exactly once; `close()` is idempotent, and every method checks OPEN.
- **Borrowed handle:** must not be destroyed, and must not be kept beyond the owner's/lease's lifetime.
- **Shared handle:** must have retain/release or a refcount/registry; copying a `long` does not create ownership.
- **Concurrency:** must keep the resource alive for the entire native operation; volatile/atomic checks alone are not enough to prevent use-after-free.
- **GC and Cleaner:** GC does not automatically free `malloc` just because a Java `long` disappears; `AutoCloseable` and `try-with-resources` are the proactive closing mechanism. Cleaner is only a fallback with no timing guarantees.
- **JNI references differ from native pointers:** `DeleteGlobalRef` releases a JNI root, while `free`/`delete`/SDK release frees a native resource. If an object owns both, it must clean up both properly.

Design a clear contract before writing JNI: **who owns the resource at each point in time and who has the right to end its lifetime**. That is the foundation for avoiding leaks, double-frees, and use-after-free bugs.
