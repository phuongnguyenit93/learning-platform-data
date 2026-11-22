# Designing a Java-Side AutoCloseable with Explicit Closed State When Wrapping a C++ Library

## Learning Objectives

When a Java application uses a C++ library, Java can hold a **native handle** pointing to an object allocated with C++ `new`, a factory function, or a custom allocator mechanism. **The Java garbage collector does not automatically know how to call a C++ destructor** and cannot infer when a C++ handle must be freed. Therefore, the Java-side wrapper needs a **clear ownership and lifecycle contract**: create the resource, use the resource, close **exactly once**, and reject all operations after closing.

`AutoCloseable` together with `try-with-resources` provides a resource-closing interface familiar to Java. However, merely adding `implements AutoCloseable` **does not automatically guarantee** that the native pointer is safe. The wrapper must have an **observable closed state**, block **use-after-close**, avoid **double-free**, control concurrent operations between `get` and `close`, and handle the error path of the native destructor appropriately.

You will learn:

- To distinguish Java references, native pointers/handles, **owner**, and **borrower**.
- To design an `OPEN → CLOSED` state machine (or `OPEN → CLOSING → CLOSED` in complex systems), with `isClosed()` and `IllegalStateException` errors.
- To make `close()` **idempotent by wrapper contract**, even though `AutoCloseable` does not require all implementations to be idempotent.
- To place `synchronized` or a shared lock around **the state check, native call, and release** to avoid races that cause use-after-free.
- To create a C ABI façade for a C++ opaque object, and then write a Java wrapper using FFM (JDK 22+) or following similar principles with JNI.
- To use `try-with-resources`, distinguish native resource lifetime from Java `Arena`, and choose an appropriate policy when a destructor cannot reliably report success.
- To test repeated close, use-after-close, concurrent close, initialization failures, and callback/async resource retention.

This lesson includes **a standalone Java 17+ example** using a simulated native bridge, verified on JDK 24, and **a practical C++/Java FFM illustration** for Linux x64 (the C++ part was statically reviewed; it is not claimed that the native binary was executed).

## 1. The Problem: The Java Object Is Still Alive, but the C++ Object May Have Been Deleted

A simple wrapper typically holds:

~~~text
Java heap                                   Native heap (C++)
+--------------------------------+           +----------------------+
| NativeCounter Java wrapper     |           | CounterHandle       |
| - handle: MemorySegment/long --+---------->| value = 7            |
| - closed: boolean              |           | native allocation    |
+--------------------------------+           +----------------------+

Java wrapper is still referenced ≠  C++ allocation still exists.
C++ allocation is deleted        ≠  Java wrapper automatically becomes null.
~~~

If other code calls native `delete` without the wrapper knowing, Java still holds a **dangling** pointer value. Conversely, if the Java wrapper does not call the destructor even when it is no longer used, the C++ resource may **leak** until the process terminates.

In C++:

~~~cpp
CounterHandle* h = counter_create(7);
int32_t v = 0;
counter_get(h, &v);  // valid while h is alive
counter_destroy(h);  // free once
// counter_get(h, &v);  // use-after-free: must not be called
// counter_destroy(h);  // double-free: must not be called
~~~

This is an illustrative snippet using a **C ABI façade** fully defined in later sections; it is not yet a standalone C++ program. After `destroy`, the bit value of `h` may still be non-zero, but that does **not** make the pointer valid.

Therefore, the Java side must **track state with its own data**, not rely on GC or address comparisons.

## 2. Determine Ownership Before Writing `close()`

Three common models:

| Model | Who allocates/creates? | Who must destroy? | What may the Java wrapper's `close()` do? |
| --- | --- | --- | --- |
| **Owned handle** | Native factory creates a new resource and transfers ownership to Java | Java wrapper | Call the destructor/deallocator **exactly once** |
| **Borrowed handle** | Native library or another owner holds the resource | Original owner | Only end the wrapper's access rights if the contract allows; **do not delete** the resource itself |
| **Shared/ref-counted handle** | Native API grants shared ownership and has `retain/release` | Each owner holds one reference count | Call **`release` once** for its own ownership share, not necessarily calling `delete` directly |

A Java class whose `close()` calls `delete` is **only correct** when it owns the native object under the C++ contract. If C++ returns a pointer into a singleton, a region inside a container, or a subobject of another object, calling delete can corrupt data or cause a crash.

**Design rule:** each owned wrapper has **a single release authority**. Do not create two Java wrappers that both “own” the same raw handle if the native library has no reference-counting mechanism. If multiple views over one resource are needed, use a single owner and issue **borrowed views** with bounded lifetimes, or a native retain/release protocol.

### Factory Ownership Example

~~~text
native counter_create(7)
   |
   +--> returns valid CounterHandle* and transfers ownership to Java
          |
          v
   new NativeCounter(handle) -> State OPEN
          |
          +--> get()/operation() multiple times while OPEN
          |
          +--> close() exactly once -> counter_destroy(handle)
                                      State CLOSED
          |
          +--> subsequent close() = no-op
          +--> subsequent get() = IllegalStateException
~~~

This is an **explicitly chosen and implemented** contract, not an inherent feature of every C++ library.

## 3. What Do `AutoCloseable` and `try-with-resources` Do, and What Do They Not Do?

`AutoCloseable` has one method:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

The `AutoCloseable` interface has been standard Java since Java 7. `try-with-resources` automatically calls `close()` when exiting the block, even if the body throws an exception.

~~~java
try (NativeCounter c = new NativeCounter(7)) {
    System.out.println(c.value());
} // c.close() is called whether the body returns or throws.
~~~

The example assumes class `NativeCounter` implements `AutoCloseable` as in the hands-on section below.

**What `AutoCloseable` does not automatically guarantee:**

- The interface **does not require** all implementations to be idempotent; however, a wrapper freeing a C++ resource **should proactively implement repeated close as a no-op**.
- It does not create a `closed` flag, does not clear the native handle, and does not call the C++ destructor automatically.
- It does not synchronize between a thread currently using the pointer and another thread closing it.
- It does not know whether a C++ handle is owned or borrowed.
- It cannot fix a wrong C++ allocator or an exception crossing the C ABI.
- It does not protect against the native library destroying the resource on its own outside the contract.

You can override `close()` as a method that **declares no checked exception**:

~~~java
@Override
public void close() {
    // The wrapper itself performs the release.
}
~~~

This approach avoids forcing callers to catch the interface's generic `Exception` when using the wrapper. If native release can report an error, define a clear exception policy (for example, unchecked `IllegalStateException` or an appropriate custom exception), while avoiding unsafe retries.

### Why Is `IllegalStateException` Commonly Chosen for Operations After Closing?

After `close()`, `value()` does not fail because of a bad Java argument; the error lies in **the object's lifecycle**. `IllegalStateException("Counter is closed")` clearly expresses the contract: the object has terminated its right to call native code.

Do not return a default value such as 0 to mask use-after-close, because 0 may be a valid C++ result and the error will silently propagate into business data.

## 4. Minimal State Machine: OPEN, CLOSED

So that the Java wrapper represents its state clearly:

~~~text
                native resource created successfully
          +-----------------------------------------+
          |                                         v
    CONSTRUCTING                                OPEN
          |                                      |
          | if create fails: do not publish       | first close()
          | owned wrapper                        v
          +--> constructor throws              CLOSED
                                                  |
                                     2nd close(): no-op
                                     operation(): fail-fast
~~~

In a simple structure, using **`boolean closed`** and a **non-null handle when OPEN** is sufficient. There is no need for a complex enum if close/destructor is synchronous, non-reopenable, and native release does not require an asynchronous step.

Important **invariants**:

1. **OPEN:** `closed == false` and the native handle belongs to the wrapper, not a null pointer per contract.
2. **CLOSED:** `closed == true` and the wrapper never calls a native function with the old handle.
3. **Idempotent close:** an owned wrapper issues at most **one** destructor call; subsequent closes are no-ops.
4. **No reopen:** do not assign a new handle to an already CLOSED wrapper. To use another resource, create a **new wrapper**.
5. **No raw pointer escape:** the public API does not return `long address`/`MemorySegment handle` so clients cannot bypass the `closed` guard.
6. **Synchronization:** every operation and close must check/change state under the same concurrency-protection mechanism.

A `CLOSING` state may exist if native cleanup takes time, involves callbacks, reference counting, cancellation, or failures that need recording. However, **do not introduce unnecessary state complexity** if a single lock + synchronous close suffices.

### Why Not Just Check `handle != 0`?

You can choose `0` as a sentinel for a null C pointer, but if:

- the native resource has been freed yet the handle variable still holds the old address;
- the library has handle IDs where 0 is not necessarily invalid;
- native close returns an error and it is unclear whether the resource has been released;

then checking only the handle number does not fully reflect the lifecycle. Use **`closed` as the source of truth** for Java access rights, while also resetting the handle to a valid sentinel to reduce the risk of accidentally using an old pointer. The null/sentinel must match the specific contract.

## 5. Designing the Right Java Wrapper: Blocking Use-After-Close and Repeated Close

A simulated version **without needing JNI/FFM yet**:

~~~java
public final class Counter implements AutoCloseable {
    private long handle;      // Simulated ID in this example, not a raw C pointer.
    private boolean closed;

    public Counter(int initial) {
        this.handle = FakeBridge.create(initial);
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException("Counter is closed");
        }
    }

    public synchronized int value() {
        requireOpen();
        return FakeBridge.read(handle);
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) return;
        closed = true;
        long oldHandle = handle;
        handle = 0L;
        FakeBridge.destroy(oldHandle);
    }
}
~~~

This is an **illustrative excerpt** inside the simulated `LifecycleLab` class provided in full in Section 10; do not copy and run it separately without `FakeBridge`.

Every detail is intentional:

- `final class` prevents subclasses from overriding `close` or calling native code through an unguarded branch.
- `handle` is private; clients cannot pass the old pointer through the bridge themselves.
- `closed` is checked via `requireOpen` before calling native code.
- `value` and `close` are both `synchronized` on **the same Java monitor**, so operations cannot interleave on **the same wrapper**.
- `close` sets `closed = true` before calling release to prevent another close from freeing twice even if release fails. The handle is replaced with a sentinel.
- `isClosed` is an observable API; it does not replace `requireOpen` inside operations themselves, because between a client calling `isClosed()` and `value()`, another thread could close it.
- `FakeBridge.destroy` appears only once on the OPEN → CLOSED path.

### Why Does Ordering Inside `close` Matter?

Counter-example:

~~~java
// DO NOT do this:
public synchronized void closeBad() {
    FakeBridge.destroy(handle);
    closed = true;
}
~~~

In case the destructor throws an exception, `closed` remains false. A caller retrying `closeBad()` may destroy a partially or completely freed resource, leading to **double-free**. In addition, without a guard at the start, repeated closes can call the destructor again.

A better approach for a destructor that **cannot be safely rolled back or retried** is to invalidate usage rights **before** calling native release. If release reports an error, the Java state remains CLOSED, but **a possible native leak / unknown release status** must be recorded; do not report that release definitely succeeded just because `closed=true`.

## 6. Dangerous Race: Checking `closed` Then Calling Native on Another Thread

A pattern that looks right but is **unsafe**:

~~~java
// NOT safe enough if close can run on another thread.
public int valueBad() {
    if (closed) throw new IllegalStateException("closed");
    return NativeBridge.get(handle);
}

@Override
public void closeBad() {
    if (!closed) {
        NativeBridge.destroy(handle);
        closed = true;
    }
}
~~~

An interleaving can occur:

~~~text
Thread A                                  Thread B
--------                                  --------
if (!closed)  -> true
                                         if (!closed) -> true
                                         destroy(handle)
                                         closed = true
NativeBridge.get(handle)  // USE AFTER FREE
~~~

**Adding `volatile boolean closed` only improves visibility**; it does not turn `if (!closed) → native call` into an atomic operation. `AtomicBoolean.compareAndSet` only prevents **two closes** from both winning; it **does not prevent an operation in progress** from running concurrently with destroy.

### Simple Approach: Hold the Same Lock Throughout the Native Call

~~~java
public synchronized int value() {
    requireOpen();
    return NativeBridge.get(handle);
}

@Override
public synchronized void close() {
    if (closed) return;
    closed = true;
    long old = handle;
    handle = 0L;
    NativeBridge.destroy(old);
}
~~~

This is a snippet, assuming `NativeBridge` has the functions shown above. If thread A has entered `value`, thread B waits on the monitor before closing; if B closes first, A enters later and gets `IllegalStateException`. **There is no path that calls native code with a handle already released by the wrapper** between these two operations.

A shared lock also guarantees visibility of `handle` and `closed` across threads passing through synchronized methods. `isClosed()` is also synchronized to avoid reading unsynchronized state.

**Condition:** the lock solves concurrency for **this wrapper**. If another API holds the same native handle and calls destroy outside the wrapper, a Java lock cannot save it. Ownership must be coordinated system-wide.

### When `synchronized` Is Not Enough or Not Appropriate

If a native function calls back into Java (callbacks), may block for a long time, has thread affinity, or holding a lock risks deadlock, you should not hold an intrinsic lock across an uncontrolled native call without evaluation. In that case, a different model is needed:

- Explicit `OPEN / CLOSING / CLOSED` states with clear locking.
- An `inFlightOperations` counter; only release when no operations are still running.
- `close` blocks new operations, waits for in-flight ones to finish, or cancels per contract.
- Do not wait for a native worker while still holding a lock that the callback needs to re-acquire.
- The native pointer is only actually freed after all parties permitted to use it have finished.

This is an **advanced design**; this lesson uses a simple lock because native `counter_get` is a short, synchronous function with no callbacks and does not retain the resource after returning.

## 7. C++ Façade: Do Not Export Class ABI Directly to Java

In C++, RAII uses constructors/destructors, but **C++ class ABIs have name mangling, overloads, and exception semantics that depend on the toolchain**. For Java FFM or JNI to interoperate stably, export **C ABI functions** taking an opaque pointer:

~~~text
Java NativeCounter                      C ABI façade               C++ object
------------------                      ------------               ----------
new NativeCounter(7) ─── counter_create(7) ──────────────> new CounterHandle
value() ──────────────── counter_get(handle,&out) ────────> read value
close() ──────────────── counter_destroy(handle) ────────> delete CounterHandle
~~~

The C ABI façade must state clearly:

- `counter_create` returns an **owned** pointer, or null when creation fails.
- `counter_get` only reads and does not retain the out pointer after returning; returns status 0 on success, nonzero on invalid input.
- `counter_destroy` takes an owned pointer and frees it **once**. The caller must never use the handle after destroy.
- C++ exceptions **must not** escape across the C/FFM/JNI ABI; there is a status/error contract and destructors are guaranteed not to throw.
- All function signatures, pointer types, encoding, and `int32_t` must match the native ABI.

### 7.1. C/C++ Header: `demo_counter.h`

~~~c
#ifndef DEMO_COUNTER_H
#define DEMO_COUNTER_H

#include <stdint.h>

#ifdef __cplusplus
#define DEMO_NOEXCEPT noexcept
extern "C" {
#else
#define DEMO_NOEXCEPT
#endif

typedef struct CounterHandle CounterHandle;

/* Returns owned CounterHandle*, NULL if allocation fails. */
CounterHandle *counter_create(int32_t initial) DEMO_NOEXCEPT;

/* Returns 0 when OK; -1 when handle/out is invalid. */
int counter_get(const CounterHandle *handle,
                int32_t *out_value) DEMO_NOEXCEPT;

/* Owner caller must invoke at most once per live handle. */
void counter_destroy(CounterHandle *handle) DEMO_NOEXCEPT;

#ifdef __cplusplus
}
#endif
#undef DEMO_NOEXCEPT

#endif
~~~

**`CounterHandle` is an opaque type** to C/Java. The header does not need to expose fields; Java simply passes a pointer back to the façade. `extern "C"` disables C++ name mangling for exported functions. The `DEMO_NOEXCEPT` macro allows the header to be **read by both C and C++ compilers** while C++ declarations still have an exception specification matching the implementation.

### 7.2. C++ Implementation: `demo_counter.cpp`

~~~cpp
#include "demo_counter.h"
#include <new>

struct CounterHandle {
    int32_t value;
};

extern "C" CounterHandle *counter_create(int32_t initial) noexcept {
    // Trivial aggregate constructor; nothrow new returns nullptr on OOM.
    return new (std::nothrow) CounterHandle{initial};
}

extern "C" int counter_get(const CounterHandle *handle,
                           int32_t *out_value) noexcept {
    if (handle == nullptr || out_value == nullptr) {
        return -1;
    }
    *out_value = handle->value;
    return 0;
}

extern "C" void counter_destroy(CounterHandle *handle) noexcept {
    delete handle;
}
~~~

This is a complete implementation for the three APIs declared in the header, targeting C++17 and common ABIs where `int32_t` is 32-bit. `CounterHandle` only contains an integer with a trivial destructor; no C++ exceptions are thrown in either get or destroy. The factory uses `std::nothrow`.

**Do not interpret `noexcept` as a cure-all for every C++ error:** if a destructor actually throws when declared `noexcept`, C++ may call `std::terminate`. A production library should design destructors not to throw, move recoverable errors to a dedicated status/release API, and verify ownership/allocators upfront. Passing a dangling pointer to `counter_get` or double-deleting is still **undefined behavior**, even with null checks and `noexcept`.

### 7.3. Building the Linux Native Library

Place `demo_counter.h` and `demo_counter.cpp` in the same directory and use a C++17 compiler:

~~~bash
g++ -std=c++17 -Wall -Wextra -Werror -fPIC -shared \
    demo_counter.cpp -o libdemo_counter.so
~~~

The name `libdemo_counter.so` matches `System.loadLibrary("demo_counter")` on Linux. This is a **Linux sample command**, not to be used verbatim on Windows/macOS; `.dll`/`.dylib` names, export attributes, and linker flags differ. For a Windows DLL, `__declspec(dllexport)` may be needed on the symbols.

**Testing limitation:** the C++ part was not natively compiled in an environment that only had Java JDK 24 without `g++`/`clang++`. The stdout outputs below are expected per contract when the native binary is built and loaded properly.

## 8. Real Java Wrapper Using FFM: Clear Ownership and CLOSED State

FFM uses `Linker`, `SymbolLookup`, and `MethodHandle` to call a C ABI without writing JNI glue manually. This example requires **JDK 22+** and had its **Java syntax checked on JDK 24**; it is not claimed to have been run end-to-end with the C++ library in an environment lacking a compiler.

Create file `NativeCounter.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class NativeCounter implements AutoCloseable {
    private static final MethodHandle CREATE;
    private static final MethodHandle GET;
    private static final MethodHandle DESTROY;

    static {
        System.loadLibrary("demo_counter");

        Linker linker = Linker.nativeLinker();
        SymbolLookup lookup = SymbolLookup.loaderLookup();

        CREATE = linker.downcallHandle(
                lookup.findOrThrow("counter_create"),
                FunctionDescriptor.of(
                        ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

        GET = linker.downcallHandle(
                lookup.findOrThrow("counter_get"),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.ADDRESS, ValueLayout.ADDRESS));

        DESTROY = linker.downcallHandle(
                lookup.findOrThrow("counter_destroy"),
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));
    }

    // Owned handle. Do not expose externally.
    private MemorySegment handle;
    private boolean closed;

    public NativeCounter(int initial) {
        try {
            MemorySegment ptr =
                    (MemorySegment) CREATE.invokeExact(initial);
            if (ptr.address() == 0L) {
                throw new IllegalStateException(
                        "counter_create returned NULL");
            }
            handle = ptr;
            // When constructor succeeds: closed defaults to false.
        } catch (RuntimeException | Error e) {
            throw e;
        } catch (Throwable t) {
            throw new IllegalStateException(
                    "create invocation failed", t);
        }
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException("Counter is closed");
        }
    }

    public synchronized int value() {
        requireOpen();

        // out_value is a temporary native buffer that only needs to live for this call.
        try (Arena scratch = Arena.ofConfined()) {
            MemorySegment out = scratch.allocate(ValueLayout.JAVA_INT);

            int status = (int) GET.invokeExact(handle, out);
            if (status != 0) {
                throw new IllegalStateException(
                        "counter_get status=" + status);
            }
            return out.get(ValueLayout.JAVA_INT, 0);
        } catch (RuntimeException | Error e) {
            throw e;
        } catch (Throwable t) {
            throw new IllegalStateException(
                    "get invocation failed", t);
        }
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }

        // Prevent any further use/release before calling native.
        closed = true;
        MemorySegment toDestroy = handle;
        handle = MemorySegment.NULL;

        try {
            DESTROY.invokeExact(toDestroy);
        } catch (Throwable t) {
            // Do not retry when it is unknown whether the native resource was freed.
            throw new IllegalStateException(
                    "destroy failed; handle invalidated", t);
        }
    }
}
~~~

### Why Does This Code Satisfy the Contract?

**(1) Initialization:** `CREATE` is an FFM downcall to `counter_create(int32_t)`. C returns the pointer as a `MemorySegment`. When address is 0, the constructor fails and does not publish an OPEN wrapper. Never call `counter_destroy` on an invalid null handle to recover from a creation error.

**(2) Get:** `GET` takes two `ADDRESS` arguments: the owned `handle` and the `out` address for `int32_t*`. `Arena.ofConfined()` manages only **the temporary `out` buffer**, not the C++ object created by `counter_create`.

**(3) Close:** the native C++ object is freed **only** by `counter_destroy`. `Arena.close()` of the temporary buffer has neither the authority nor the ability to delete that C++ object.

**(4) Guard:** `requireOpen()` runs inside `synchronized value()`, and `close()` shares the same monitor. There is no interleaving between native `counter_get` and `counter_destroy` on the same wrapper.

**(5) Explicit state:** `isClosed()` returns a boolean. A second `close()` is a no-op. After close, `value()` immediately throws `IllegalStateException` **before calling C++**.

**(6) FFM loading:** `System.loadLibrary` loads the library into the class loader; `SymbolLookup.loaderLookup()` looks up symbols from libraries loaded into this class loader, matching JDK 24 documentation. `Linker.downcallHandle` requires native-access permission because it is a restricted FFM API.

**(7) Signature:** `int32_t` is mapped to `JAVA_INT` for the Linux x64 ABI in the example, and pointers to `ADDRESS`. Always verify the actual ABI and C signature when porting. `invokeExact` requires exact Java carrier type matches; do not arbitrarily cast `MemorySegment` to `long`.

**(8) Release failure:** the simple native destructor example has no recoverable error state. If the Java FFM `DESTROY` call encounters a `Throwable`, the Java state remains CLOSED and reports “handle invalidated”; **it does not claim the native resource was definitely freed**. Investigate the error; do not blindly retry to avoid double-free.

### What the Example Does Not Automatically Solve

- The C++ library might retain the pointer in another thread/callback and destroy it outside the wrapper: this **violates the ownership assumption**.
- If `counter_get` internally invokes a Java callback, the Java monitor may participate in a deadlock; the code must be redesigned for that case.
- If the native resource requires creator-thread affinity, `synchronized` is not enough: it serializes concurrency but does not pin the executing thread.
- If you need failed releases to be retryable, the native C ABI must **explicitly define** whether on error the handle still belongs to the caller or was partially freed; the state machine will differ.
- Assigning `MemorySegment.NULL` to the field only clears the Java wrapper's pointer; it **does not delete** the native allocation. The actual release is performed by `counter_destroy`.

## 9. Java Client Using `try-with-resources` and Expected Output

Create file `CounterApp.java`:

~~~java
public final class CounterApp {
    public static void main(String[] args) {
        NativeCounter c = new NativeCounter(7);

        try (c) {
            System.out.println("value=" + c.value());
            System.out.println("closed-in-scope=" + c.isClosed());
        }

        // Repeated close() is a no-op per wrapper contract.
        c.close();
        System.out.println("closed-after=" + c.isClosed());

        try {
            c.value();
        } catch (IllegalStateException expected) {
            System.out.println("use-after-close="
                    + expected.getClass().getSimpleName());
        }
    }
}
~~~

This is a standalone client once `NativeCounter.java`, `CounterApp.java`, and the native shared library have been built.

On Linux:

~~~bash
javac -encoding UTF-8 NativeCounter.java CounterApp.java
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. CounterApp
~~~

**Expected stdout** if the Linux library builds properly and the C++ ABI matches:

~~~text
value=7
closed-in-scope=false
closed-after=true
use-after-close=IllegalStateException
~~~

The output does not print a native memory address (which depends on the allocator and ASLR). A production test should add **native instrumentation** to confirm `counter_destroy` runs exactly once, rather than relying only on Java `close()` not throwing.

**Important:** This is the expected logical output of the complete C++/FFM example, **not end-to-end stdout observed in an environment without a C++ compiler**. A pure-Java lab that was actually executed follows right below.

## 10. Standalone Java 17+ Lab: Simulating Native Handles and Destructor

To verify **lifecycle semantics** without needing a C++ compiler or FFM, this example uses a Java map to simulate the native heap. Each native handle is simulated by an ID number **that is not a real C address**. Releasing removes the ID from the map and increments a destroy counter; if destroyed twice, the test throws an error to detect it.

Create file `LifecycleLab.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class LifecycleLab {
    private static final class FakeBridge {
        private static long next = 1L;
        private static final Map<Long, Integer> values = new HashMap<>();
        private static int destroyCount;

        static synchronized long create(int initial) {
            long handle = next++;
            values.put(handle, initial);
            return handle;
        }

        static synchronized int read(long handle) {
            Integer value = values.get(handle);
            if (value == null) {
                throw new AssertionError("invalid handle");
            }
            return value;
        }

        static synchronized void destroy(long handle) {
            if (values.remove(handle) == null) {
                throw new AssertionError("double free");
            }
            destroyCount++;
        }

        static synchronized int destroyCount() {
            return destroyCount;
        }
    }

    public static final class Counter implements AutoCloseable {
        private long handle;
        private boolean closed;

        public Counter(int initial) {
            handle = FakeBridge.create(initial);
        }

        private void requireOpen() {
            if (closed) {
                throw new IllegalStateException("Counter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return FakeBridge.read(handle);
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) return;

            closed = true;
            long h = handle;
            handle = 0L;
            FakeBridge.destroy(h);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter c = new Counter(7);
        try (c) {
            System.out.println("value=" + c.value());
            System.out.println("closed-in-scope=" + c.isClosed());
        }

        c.close();
        System.out.println("closed-after=" + c.isClosed());
        System.out.println("destroy-count=" + FakeBridge.destroyCount());

        try {
            c.value();
        } catch (IllegalStateException e) {
            System.out.println("use-after-close="
                    + e.getClass().getSimpleName());
        }

        Counter raced = new Counter(9);
        Thread t1 = new Thread(raced::close);
        Thread t2 = new Thread(raced::close);
        t1.start();
        t2.start();
        t1.join();
        t2.join();

        System.out.println("raced-closed=" + raced.isClosed());
        System.out.println("total-destroys=" + FakeBridge.destroyCount());
    }
}
~~~

Compile and run with **JDK 17+**, no native access required:

~~~bash
javac -encoding UTF-8 LifecycleLab.java
java LifecycleLab
~~~

**Stdout verified with JDK 24**:

~~~text
value=7
closed-in-scope=false
closed-after=true
destroy-count=1
use-after-close=IllegalStateException
raced-closed=true
total-destroys=2
~~~

### Reading the Experiment Results

- Inside `try`, the object is OPEN, `value() == 7`, and `isClosed() == false`.
- Exiting `try`, Java calls `close()`; `destroy-count=1` proves one resource was destroyed.
- The subsequent `c.close()` does not increment the count.
- `c.value()` after close throws `IllegalStateException` in Java **before** `FakeBridge.read`.
- Two threads call `raced.close()` concurrently. Each wrapper has its own monitor, so only one thread passes through the OPEN → CLOSED transition, while the other sees CLOSED and no-ops.
- Total native destroys is 2: each of the **two Counter instances** is destroyed **once**. Different thread orderings do not affect the output.

Important note: this test verifies **Java wrapper logic**; it does not prove that native `delete` is actually called properly in the FFM/JNI version. Integration tests need C++ counters/hooks or ASan to observe real native allocations.

## 11. Resource Closing Failures: CLOSED State and Resource Release Are Two Separate Events

An advanced design issue: if a native destructor/deallocator **can report an error**, `close()` having transitioned to the CLOSED state **is not sufficient** to say the resource was definitely released successfully.

Suppose a native API returns a status:

~~~c
/* Illustrative prototype, not part of demo_counter.h in Section 7. */
int counter_release_ex(CounterHandle *h);
~~~

You must clearly determine:

1. Status 0: has the handle been completely released?
2. Non-zero status: is the handle still completely intact and retryable, or was it partially released?
3. Can an error occur even though native code already freed the handle?
4. Is there a native logging/error object to help diagnose post-release issues?
5. Who has the right to retry and when? Is it safe when multiple threads call close?

If the native contract **does not** guarantee the post-failure state, the safer approach is to **close Java usage rights** immediately before release, do not retry spontaneously, record a potential leak, and surface the error to the owner.

~~~java
// Illustrative idea, not a direct replacement for NativeCounter in Section 8:
if (!closed) {
    closed = true;              // Java object can no longer be used.
    MemorySegment old = handle;
    handle = MemorySegment.NULL;
    // Call native release exactly once.
    // On error: report + instrumentation, do not blindly retry.
}
~~~

For an API that explicitly specifies “failure leaves the resource fully owned and unchanged”, a dedicated retry state such as `CLOSE_FAILED` can be designed, but **retryable** and **terminal** failures must be clearly distinguished. Never assume `close()` will always succeed or can always be retried.

### Do Not Let `InterruptedException` Leak Out of `close` Unless Required

The `AutoCloseable` Javadoc recommends not letting `close` throw `InterruptedException`, because it can alter the interrupted state and complicate `try-with-resources` syntax. If shutdown must wait for a native worker, clearly define cancel/timeouts/retry, preserve thread interruption semantics, and choose an exception type that fits the Java application contract.

### Try-with-resources When Both the Body and Close Fail

Example:

~~~java
try (NativeCounter c = new NativeCounter(7)) {
    throw new IllegalStateException("work failed");
}
~~~

If `close()` also throws, Java **keeps the exception from the body as primary** and places the exception from `close` into the **suppressed exceptions** list (except in special cases per Java semantics). When debugging, check `Throwable.getSuppressed()`; do not just look at the first error and conclude that cleanup succeeded.

This example is a snippet to explain language semantics, not tied to fixed stdout.

## 12. JNI Wrappers Also Need Closed State Just Like FFM Wrappers

If a project does not use FFM (for example, needing Java 17 + JNI), a Java class can hold an opaque `long` handle returned by a JNI method:

~~~java
public final class JniCounter implements AutoCloseable {
    private long handle;
    private boolean closed;

    public JniCounter(int initial) {
        long h = nativeCreate(initial);
        if (h == 0L) {
            throw new IllegalStateException("nativeCreate returned NULL");
        }
        handle = h;
    }

    private void requireOpen() {
        if (closed) throw new IllegalStateException("closed");
    }

    public synchronized int value() {
        requireOpen();
        return nativeGet(handle);
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) return;
        closed = true;
        long h = handle;
        handle = 0L;
        nativeDestroy(h);
    }

    private static native long nativeCreate(int initial);
    private static native int nativeGet(long handle);
    private static native void nativeDestroy(long handle);
}
~~~

This is an **illustration of Java source requiring a corresponding JNI implementation**, not a standalone runnable file. It intentionally omits `System.loadLibrary` and JNI C++ glue to focus on state; in a real project you must load the library and declare matching Java native signatures. Map the handle to a pointer in JNI using ABI-safe casts (`intptr_t`/`uintptr_t`, without assuming Java `long` equals a C pointer size on every platform) and do not throw C++ exceptions across the JNI boundary.

The common principle remains unchanged: `AutoCloseable` in Java still controls **access rights**, **ownership**, and **lifetime** of the resource. Only the native invocation mechanism differs: JNI uses native methods and `JNIEnv`, while FFM uses `Linker`/`MethodHandle`.

## 13. `Arena`, `MemorySegment`, and C++ Destructors Are Not Interchangeable

In FFM, `Arena.ofConfined()`/`Arena.ofShared()` manages **memory allocated by the Arena and resources bound to that scope**. However, if native C++ code returns `CounterHandle*` from `new`, the `MemorySegment` representing that pointer **does not automatically carry a C++ destructor**.

| Resource | Allocated by | Correct method to free |
| --- | --- | --- |
| Temporary `int32_t*` out buffer | `arena.allocate(JAVA_INT)` | `arena.close()` |
| C++ opaque object | `counter_create` with C++ `new` | `counter_destroy` exactly once per ownership |
| Raw pointer wrapper | `MemorySegment` value from `ADDRESS` | Does not own memory; does not auto-`free` |
| FFM upcall stub | `linker.upcallStub(..., arena)` | Close arena **after** native code no longer invokes the callback |
| C string allocated with `malloc`/native allocator | Native function/library | Matching deallocator per API, not Arena close by default |
| JNI global reference | `NewGlobalRef` | `DeleteGlobalRef`, different from a C++ destructor |

**A dangerous case:** creating a C++ handle with `counter_create`, then calling `MemorySegment.ofAddress(pointer.address()).reinterpret(...)` and believing that a sized view attached to an Arena will call `delete`. That is false. `reinterpret`/scope only describes view access rights; the allocator and destructor of the C++ object remain independent.

A Java `Cleaner` can be designed as a backstop for forgotten closes, but it does not replace deterministic release (see Section 15).

## 14. Borrowed Views, Clone/Copy, and Single-Time Ownership

Suppose a native API has:

~~~cpp
// Illustrative prototype:
CounterHandle* counter_get_child(CounterHandle* parent);
~~~

If `child` is a **borrowed pointer** belonging to parent, Java must not construct `new NativeCounter(child)` whose default constructor would own/delete child. Options include:

- A `BorrowedCounterView` that only calls native code while **the parent is still OPEN**.
- The borrowed view holds a strong reference to the parent to prevent the Java parent from being GC'd early, while the parent cannot be closed while the view is in use (sharing the lock/lifetime protocol).
- A native API `counter_retain(child)`/`counter_release(child)` if transitioning to shared ownership is supported.
- True copying via native `counter_clone(child)` creating a new allocation, after which another Java wrapper owns the clone.

**Not equivalent:** copying a Java wrapper object or cloning a `MemorySegment` reference does not duplicate the native object. If two wrappers both call native delete on the same address, double-free is a severe risk.

When a native method creates a new resource and returns a handle, **every error branch after create but before the wrapper receives ownership** must clean up the resource if needed. If the Java constructor fails after create succeeds, use a try/catch/finally structure to call release once or transfer ownership atomically.

## 15. `Cleaner`, Finalization, and Shutdown Hooks: Only a Secondary Safety Net

Some libraries use `java.lang.ref.Cleaner` to clean up native memory if callers forget `close()`. However:

- When `Cleaner` runs is **non-deterministic**. GC may not occur before the process exits.
- `Cleaner` must have **a separate State object** as its cleaning action, holding no back-reference to the Java wrapper itself that would keep the wrapper alive indefinitely.
- The cleaning action must be made idempotent and coordinated with explicit `close()` to avoid double-free.
- If the native resource requires freeing on a specific thread, the Cleaner thread may be unsuitable.
- If the native library has already been unloaded before the cleaner runs, calling the destructor through a stale function pointer is very dangerous.
- `finalize()` is deprecated for removal and is not a reliable resource-release mechanism for new code.
- `Runtime.addShutdownHook` does not replace `close()`: shutdown order, abrupt termination, and dependencies are not guaranteed like normal try-with-resources.

If using `Cleaner`, **ensure no callback/native worker is still using the resource** before cleanup and avoid designs where multiple owners release the same address. For workloads involving database handles, GPU contexts, C++ objects with affinity, or native threads, explicit owner `close()` is usually the centerpiece of the design.

### Example of Flawed Thinking

~~~java
// Wrong by contract, even though the Java source compiles:
class BadWrapper {
    long nativePointer;
    @Override
    protected void finalize() throws Throwable {
        nativeDestroy(nativePointer);
    }
}
~~~

This is a **counter-example**, has no `nativeDestroy` implementation, and should not be run. GC does not know when native work is still using the pointer; finalizers do not guarantee timely release and have safety/lifecycle issues. Use `AutoCloseable` with an explicit owner instead of relying on finalization.

## 16. Callbacks, Async Native Work, and Handling Slow Close

A simple `synchronized` wrapper works well when `counter_get` is **synchronous and does not retain the handle** after returning. If the C++ API spawns background tasks or stores callback function pointers, the lifecycle is harder:

~~~text
Java wrapper OPEN
    |
    +-- startAsync(handle) -> native worker holds handle
    |
    +-- close() called from Java
             |
             +-- block new operations
             +-- request native cancel/unregister
             +-- wait for all in-flight operations/callbacks to finish
             +-- counter_destroy(handle)
             +-- Java state CLOSED
~~~

Key point: **do not call delete while a native worker still holds the pointer**. If close merely invalidates the Java field and deletes immediately, the native worker may dereference freed memory. There must be a protocol from the native library confirming no users remain.

A complex system may need:

- Reference counts / in-flight leases around each native use.
- State locks and a condition/latch so close waits for the lease count to reach 0.
- Native unregister/cancel APIs with acknowledgment.
- Avoiding waiting for callbacks while holding a lock that the callback also needs.
- Thread affinity: some C++ objects must be destroyed on a native event-loop/creator thread.
- Clear timeout/error states; if the worker cannot be stopped, report an error and **do not pretend the resource was safely freed**.

**Do not apply the simple simulated pattern to an async native API lacking lifecycle guarantees.** A `CLOSING` state is useful to represent that close has been requested while native code has not yet released; the `isClosed()` API must clearly define whether it means “no longer permitted for use” or “native has freed”, avoiding conflating the two concepts.

## 17. Edge Cases That Must Be Designed For

| Scenario | Risk | Recommended Rule |
| --- | --- | --- |
| `counter_create` returns NULL | Constructor could publish an invalid handle | Fail fast, do not create an OPEN wrapper |
| C++ factory throws an exception | Exceptions must not cross the FFM/C ABI | C ABI catches/maps errors, returns status/null |
| `value()` after close | Use-after-free | Throw `IllegalStateException` before downcall/JNI |
| 2nd `close()` | Double delete | Idempotent/no-op |
| Two threads close concurrently | Double delete if guard is non-atomic | One monitor/lock protecting the transition |
| Thread A calling get, B closing | UAF if using only a volatile flag | One lock protecting both native call and close |
| `close()` throws after already freeing | Blind retry could double-free | Invalidate state before release, record error |
| Native destructor can fail while retaining handle | Leak or lost ownership if state is wrong | Requires retryability contract and `CLOSE_FAILED` state if safe |
| Native worker still holds pointer | UAF after Java close | Cancel/unregister, drain in-flight then free |
| Borrowed pointer owned by wrapper | Invalid/double-free | Distinguish owner/borrower at the type level |
| Two wrappers own the same pointer | Double delete | Transfer ownership, retain/release, or true clone |
| Native library unloads before wrapper close | Calling stale function pointer | Bind classloader/library lifetime |
| Native operation returns error code | Java fails to notice failure | Map status to exception/domain result |
| UI thread calls slow close | UI freeze/deadlock | Coordinate async cleanup with a clear contract |

**Exceptions that cannot simply be “caught and continued”:** segmentation faults from invalid native pointers, heap corruption from double-free, and wrong C++ calling conventions can usually kill the JVM. Prevent them via ownership/state/ABI contracts rather than relying on Java `try/catch`.

## 18. Test Strategy: Proving Release Happens Exactly Once

Recommended test suite:

1. **Create success:** owned handle is non-NULL, state is OPEN, operation returns expected data.
2. **Create failure:** factory returns NULL/error status → constructor fails, does not publish resource, and does not call destructor on invalid pointer.
3. **Implicit close:** `try-with-resources` exits scope → destructor called exactly once.
4. **Explicit + implicit close:** call `close()` inside `try` and let it auto-close again → still one destructor call.
5. **Repeat close:** 2/3/10 consecutive times → no-op, no crash.
6. **Use-after-close:** every public method touching native code (including getters/mutators/callback registration) → `IllegalStateException` before the native call.
7. **Concurrent close:** multiple threads calling `close` → destroy count remains 1.
8. **Get vs close:** use `CountDownLatch` or a barrier to make native get wait; close must wait for get to finish (or use an explicit lease protocol).
9. **Destroy failure:** simulate native release returning an error at different points; wrapper does not blindly retry and reports uncertain ownership.
10. **Shared/borrowed views:** close parent/view in proper lifetime order; no double free.
11. **Native sanitizers:** ASan/UBSan on the C++ binary (when supported) to detect UAF/double-free; heap profiler/Valgrind tools where appropriate.
12. **Leak tests:** create/close many resources and check native allocation counts, not just Java heap usage.

### An Interleaving Test Must Have the Right Criterion

For a wrapper using a single monitor, if a real operation is held inside native code, the closing thread **must not** call `counter_destroy` before the operation returns. That is a necessary condition, not just checking Java `closed` after joining. A test with native hooks/latches can log event timestamps to prove ordering, whereas a test should not rely on a random `Thread.sleep` duration and assume the race was adequately exercised.

### Testing Close Failure Must Not Create a Double-Free

If a mock destructor intentionally “frees then throws”, the Java wrapper must keep `closed=true`, avoiding a second destroy call. If a mock destructor “throws before freeing”, the wrapper may leak; **it is impossible to guarantee both no-leak and no-double-free without a native contract distinguishing the two states**. This is why the C ABI cleanup status must be designed clearly from the start.

## 19. Anti-Patterns and How to Fix Them

| Anti-pattern | Why is it wrong? | Alternative |
| --- | --- | --- |
| `class NativeThing { long ptr; }` without close | No lifecycle owner | `implements AutoCloseable`, CLOSED state, and release |
| `close(){ nativeDelete(ptr); }` | Second call deletes twice | Guard + set CLOSED + invalidate ptr |
| Checking only `if (ptr != 0)` | Cannot clearly express ownership/failure | `closed` as the API contract |
| Using only `volatile closed` | Check-then-call race still exists | Lock around both operation and destroy |
| `AtomicBoolean.getAndSet(true)` then destroy while operation is unlocked | Can UAF during operation | Lock or in-flight lease protocol |
| Exposing `public long address()` | Client bypasses guard/destroy | Encapsulate handle, expose only safe operations |
| Setting `ptr=0` without calling native delete | Resource still leaks | Call the right destructor/deallocator |
| Calling C `free` on C++ `new` | Allocator mismatch | Export C ABI factory/destructor pair |
| Using `Arena.close()` to destroy a C++ object | Arena does not know the C++ destructor | Call `counter_destroy` |
| Calling `counter_destroy` from Cleaner as the sole mechanism | GC scheduling is non-deterministic | Explicit `close()`, Cleaner only as optional backstop |
| Copying native pointer into two owned Java objects | Double-free | One owner or retain/release |
| Calling close while callback/native thread still uses handle | UAF/deadlock | Unregister/drain, then release |
| Swallowing all native get errors and returning 0 | Hides broken state | Map status to clear exception |
| Treating closed flag == successful native free | Diverges if release fails | Distinguish closed access from release status |
| Fixing a raw pointer via `reinterpret` or casting `long` | Does not restore freed memory | Respect lifetime/ABI |
| Using Java `null` as an FFM C null address | Not a valid pointer carrier per contract | `MemorySegment.NULL` |

## 20. Self-Check Questions

**Q1.** Why doesn't `AutoCloseable` automatically free `new CounterHandle` in C++?

Because it only defines the **`close()` interface**. The caller must implement `close` to call the right native destructor, protect state, and manage ownership. Java's GC does not automatically understand C++ allocators.

**Q2.** Does `AutoCloseable.close()` require idempotence according to the Javadoc?

No. The interface does not strictly require it, though the Javadoc **encourages** implementations to make close idempotent. For a wrapper owning a C++ pointer, idempotence is typically a safety requirement to avoid double-free.

**Q3.** Why is `volatile boolean closed` still not enough?

Because thread A can read `closed=false`, thread B frees the native pointer, and then A calls native code. Check and call are not atomic. A lock or lease/refcount is needed to protect **the duration while the native call is using the pointer**.

**Q4.** Does `isClosed()==false` prove that the native object is definitely still alive?

Only if **the ownership contract** is respected and no other native owner deletes it independently. If the native library frees it outside the wrapper, Java state can be wrong. That is why raw handles should not be exposed and an ownership policy is needed.

**Q5.** Why can setting `closed=true` before native release be reasonable?

If release fails or throws an exception after freeing partially or completely, Java does not retry and reuse a pointer whose state is now unknown. That can come with a leak if release fails before freeing; a native contract is needed to handle this accurately.

**Q6.** If `close()` is called a second time while CLOSED, what should happen in the example?

Return immediately without calling `counter_destroy` again. The state remains CLOSED.

**Q7.** What happens if two wrappers both receive the same C++ pointer and both have `close()` calling delete?

There is a risk of double-free. Choose one owned wrapper, a borrowed view, or native reference counting where each share is retained and released separately.

**Q8.** What is `Arena.ofConfined()` in `value()` of the FFM wrapper freeing?

It only allocates and frees **the temporary out buffer** for `int32_t*`. The C++ `CounterHandle` belongs to `counter_create` and requires `counter_destroy`.

**Q9.** After `close()` when native cleanup throws, should `close()` be called again automatically?

No, if the state of the native handle is not known for sure. Blind retry can cause double-free. Report the error and rely on the status/ownership contract before deciding on recovery.

**Q10.** A native async operation still holds the handle when Java calls `close()`. What must be done?

Block new operations, cancel/unregister or wait for in-flight operations to complete, and only then destroy. When needed, use a `CLOSING` state and native acknowledgment instead of freeing immediately.

**Q11.** Does `try-with-resources` guarantee close order?

Yes. With multiple resources in the `try` header, Java closes them in **reverse order of declaration**. If resources depend on each other, choose the declaration order accordingly and check suppressed exceptions.

**Q12.** Can `Cleaner` be used instead of `AutoCloseable`?

It should not be. Cleaner/GC does not guarantee release timing and has thread/library lifetime constraints. For a C++ wrapper with a clear owner, use explicit `close()` and `Cleaner` only as a backstop if the design is provably safe.

## 21. Production Implementation Checklist

- [ ] Does the native factory return an owned handle or a borrowed pointer? Document clearly in docs/C ABI.
- [ ] What is the exact native destructor/deallocator? Is there a stable `extern "C"` ABI?
- [ ] Is the wrapper `final` or are subclassing and ownership strictly controlled?
- [ ] Is the native handle private so clients cannot hold a raw pointer to bypass guards?
- [ ] Is the OPEN/CLOSED state protected by a consistent concurrency mechanism?
- [ ] Does `isClosed()` accurately describe the wrapper's **usage rights**, without conflating it with release success?
- [ ] Does every public native operation call `requireOpen()` while holding the proper lock/lease?
- [ ] Is `close()` idempotent: is the destructor called at most once per ownership share?
- [ ] Does `close()` invalidate the handle + state according to a clear failure policy?
- [ ] Does the constructor handle the factory returning NULL and prevent owned resources from leaking on init failure?
- [ ] Is `try-with-resources` used at call sites where possible instead of relying on GC?
- [ ] Are resources prevented from being closed while native callbacks/async workers are still using them?
- [ ] Does the C ABI prevent C++ exceptions from escaping across the JNI/FFM boundary?
- [ ] Do FFM `SymbolLookup` and `Linker` use the right native library, ABI, and permissions?
- [ ] Is native C++ code built with the right target, compiler, and `libstdc++`/`libc++` runtime?
- [ ] Do tests verify repeated close, use-after-close, concurrent close, operation vs close, close failure, and leaks?
- [ ] Is double-delete prevented when using borrowed views and resource sharing?
- [ ] Is Cleaner/finalizer avoided as the sole release mechanism?

## Official References

1. [Oracle Java SE 24 — AutoCloseable](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/AutoCloseable.html): `close`, try-with-resources, the principle of releasing before throwing exceptions, and idempotence recommendations.
2. [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se24/html/jls-14.html#jls-14.20.3): closing resources in reverse order, primary/suppressed exceptions.
3. [Oracle Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): downcalls, C ABI, and restricted native access.
4. [Oracle Java SE 24 — SymbolLookup](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `loaderLookup()` after `System.loadLibrary()` and lifetime of native symbols.
5. [Oracle Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): allocating out buffers, scope, and thread confinement.
6. [Oracle Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, native addresses, bounds, and lifetime.
7. [Oracle Java SE 24 — Cleaner](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Cleaner.html): limitations and guidelines for using cleaning actions.
8. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): official FFM API since Java 22.

**Summary:** A Java wrapper owning a C++ resource must clearly specify **who may close, what close does, and what is forbidden after close**. `AutoCloseable` connects with `try-with-resources`; `closed`/`isClosed` makes state explicit; **a lock or lease** protects the pointer throughout native calls; **the right native destructor for the allocator called exactly once** prevents leaks/double-free. When a resource has a callback/async lifetime, a shutdown protocol must be designed rather than merely adding a boolean.
