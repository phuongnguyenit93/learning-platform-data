# Keeping the Stub Alive as Long as the Library Can Still Call Back

## Objectives

The Foreign Function & Memory API (FFM) allows Java to call C via a **downcall** and allows C to call back into Java via an **upcall stub**. When calling `Linker.upcallStub(target, descriptor, arena)`, the JVM creates a native function pointer corresponding to a Java `MethodHandle`. A C function can receive and **store** this pointer in a registry, a listener, an event loop, or a native thread.

A dangerous bug occurs when the Java side thinks callback registration is complete and closes the `Arena`, while C can still call back into that function pointer. A callback executed **after the arena has freed the stub** can cause a JVM crash or memory corruption. This is not an ordinary Java error that can always be caught with `try/catch`.

This lesson guides you through:

- Understanding the nature and lifecycle of the `MemorySegment` representing an upcall stub.
- Distinguishing the lifetimes of `Arena`, Java `MethodHandle`/captured state, the native library, and callback registration.
- Determining the safe-close condition: **stop accepting new callbacks → unregister → drain or join all in-flight/queued callbacks → close the arena**.
- Writing a complete **JDK 22+ + C11** example in which C holds the pointer across multiple Java calls, then unregisters it before Java closes the arena.
- Checking the descriptor, ABI, native access permissions, native symbol lifetime, and exception handling in the upcall target.
- Using an owner state machine and synchronization to avoid races between callback, unregister, and close.
- Distinguishing synchronous callbacks that only run within a single downcall from asynchronous callbacks that can arrive hours later.
- Testing safely without intentionally calling a freed function pointer.

> **JDK Requirement:** FFM in `java.lang.foreign` became a standard API starting in **JDK 22** under JEP 454. This `Linker.upcallStub` code cannot be compiled on Java 17; Java 17 has a different incubator API, or JNI can be used instead. The main example requires JDK 22+, a C compiler, and when running on the class path, `--enable-native-access=ALL-UNNAMED` for restricted FFM operations. `--enable-preview` is not required on JDK 22.

## 1. What is an Upcall Stub?

In C, a callback can be a function pointer:

~~~c
#include <stdint.h>

typedef int32_t (*callback_fn)(int32_t value);

int32_t register_callback(callback_fn callback);
~~~

These are **illustrative declarations**. `callback_fn` is not a Java object; C only sees a native address that can be called using the matching calling convention. Ordinary Java cannot cast a lambda to this kind of pointer. The FFM `Linker` creates a stub/trampoline, and when C calls that address, the JVM dispatches to the Java `MethodHandle`.

~~~text
Java method: int onEvent(int value)
                |
         MethodHandles.lookup()
                |
           MethodHandle
                |
       Linker.upcallStub(...)
                |
        MemorySegment stub
        (native function pointer)
                |
       C register_callback(stub)
                |
       C stores pointer in state
                |
          ... time passes ...
                |
       C calls pointer(value)
                |
         FFM upcall bridge
                |
       Java onEvent(value)
                |
         C receives int32_t
~~~

According to the Java SE 22 `Linker.upcallStub` specification:

- It accepts a `MethodHandle`, a `FunctionDescriptor`, an `Arena`, and optional linker options.
- It returns a **zero-length MemorySegment** with the native address of the upcall stub.
- **The Arena controls the lifetime of the stub**: if the arena is closed, the stub address is no longer valid.
- The target method handle must have carrier types compatible with the descriptor.
- The target **must not throw a Java exception across the upcall boundary**; the specification warns that the JVM may terminate abruptly.

Thus `MemorySegment stub` is both a Java handle for managing the address and a **native resource with a lifetime**. It does not automatically create a refcount with C libraries that have received the pointer.

## 2. The Most Important Condition: When Are Callbacks Truly Finished?

You must not decide when to close based on when `register_callback` returns. Instead, ask:

> **Has the native library completely lost the ability to use this function pointer, including callbacks currently running, waiting in a queue, and callbacks where a worker already holds a copy of the pointer?**

Only when the answer is guaranteed to be **yes** may you close the arena.

~~~text
CREATE arena and upcall stub
         |
REGISTER pointer with C library
         |
    CALLBACK ACTIVE
         |
 C may call one or more times
         |
  REQUEST STOP / CLOSING
         |
 prevent new callbacks from being scheduled
         |
 unregister pointer from registry
         |
 cancel/drain queued callbacks
         |
 wait for all in-flight invocations to finish
         |
    NATIVE QUIESCENT
         |
  ARENA.CLOSE() once
         |
       CLOSED
       pointer INVALID
~~~

Three conditions to distinguish:

1. **No new registrations:** the native library rejects new events related to the callback.
2. **No scheduled work:** every queue item holding the pointer has been canceled or completed, including tasks that have not yet started executing.
3. **No running invocations:** every thread has exited the upcall stub and the Java target, and does not retain the pointer for further use.

Merely clearing a C global variable is **not enough** if a native thread has already read the pointer into a local variable or a queue has already copied the pointer earlier.

### Use-after-free Counterexample

~~~text
Java: create arena
Java: create stub
Java: register(stub)
C:    g_callback = stubAddress

Java: return from register()
Java: arena.close()           <--- wrong

C:    event later
C:    g_callback(42)          <--- stub address has been freed
                                     => crash/undefined behavior
~~~

Do not attempt to run the counterexample: calling a function pointer whose lifetime has expired can crash the entire JVM.

## 3. Three Lifetimes That Must Not Be Confused

| Component | Who owns/manages it? | Condition under which it remains usable |
|---|---|---|
| Upcall stub | The `Arena` used when creating the stub | Scope is alive and not closed |
| Target `MethodHandle` | Java/FFM linker and owner references | Target/captured state has a valid lifetime |
| Native callback registration | C SDK/library | SDK still stores or can call the function pointer |
| Native library/symbols | `SymbolLookup.libraryLookup`, class loader, or OS loader | Library code has not been unloaded while downcalls/callbacks remain |
| Memory/data accessed by callback | Java object, another arena, or SDK | Not closed/freed or raced |
| Native worker/queue | SDK event loop/thread pool | Drained/joined before destroying the stub |

**Keeping a Java reference to `MemorySegment stub` does not prevent you from closing the arena yourself.** A Java object describing the segment can still exist when the native backing has been freed. Conversely, keeping the arena alive while the Java target's state has been closed early or the library code has been unloaded is also unsafe.

A useful ownership contract:

> `CallbackRegistration` owns the arena and the stub. The native SDK **borrows the address** while the callback is ACTIVE. The SDK must provide a way to unregister and confirm there are no remaining in-flight/queued callbacks. The Java owner closes the arena only after native code no longer has the right to call back. Other consumers must not close the arena on their own.

If you only read a return value from `register` and discard the owner, you may have lost the ability to control the lifecycle.

## 4. ABI and FunctionDescriptor Must Be Exact

Suppose C defines:

~~~c
typedef int32_t (*callback_fn)(int32_t value);
int32_t register_callback(callback_fn cb);
int32_t fire_callback(int32_t x);
void unregister_callback(void);
~~~

FFM mapping in this program:

| C signature | FFM descriptor | Java carrier |
|---|---|---|
| Callback `int32_t(int32_t)` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` | `int → int` |
| `register_callback(callback_fn)` | `FunctionDescriptor.of(JAVA_INT, ADDRESS)` | `MemorySegment → int` |
| `fire_callback(int32_t)` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` | `int → int` |
| `unregister_callback(void)` | `FunctionDescriptor.ofVoid()` | `() → void` |

`ValueLayout.ADDRESS` is for function pointer addresses. Do not replace it with `ValueLayout.JAVA_LONG` just because pointers on the current machine may be 64 bits wide. Do not assume C `long` is always equivalent to Java `long`: the C ABI varies by platform.

For the target:

~~~java
MethodHandle target = MethodHandles.lookup().findStatic(
        UpcallLifetimeDemo.class,
        "onValue",
        MethodType.methodType(int.class, int.class));

MemorySegment stub = linker.upcallStub(
        target,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT),
        arena);
~~~

This is a **Java snippet** that requires the appropriate imports and `linker`/`arena`. The full runnable example below includes an error-catching target.

An ABI mismatch such as C calling `void (*)(double)` while the Java stub describes `int(int)` can lead to a crash or memory corruption. A Java `ClassCastException` does **not** protect against calling a function pointer with the wrong ABI. For C++ libraries, a C ABI shim is required when needed; do not arbitrarily cast a C++ member-function pointer to a C callback.

## 5. Runnable JDK 22+ + C11 Example: C Holds the Callback Across Multiple Calls

The exercise has a C shared library and a Java program. C does not run a background thread; all operations run sequentially on a single thread so the output can be verified. The C library **stores** the pointer upon registration, then calls it on subsequent `fire_callback` calls. This is deferred registration across **multiple downcalls**, even though each individual fire is synchronous.

### 5.1. Native file `upcalllifetime.c`

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
    #define API __declspec(dllexport)
#else
    #define API __attribute__((visibility("default")))
#endif

typedef int32_t (*callback_fn)(int32_t value);

/*
 * SINGLE-THREADED demo.
 * Static C variables have no mutex; do not use concurrently.
 */
static callback_fn stored_callback = NULL;

API int32_t register_callback(callback_fn callback) {
    if (callback == NULL || stored_callback != NULL) {
        return 0;
    }
    stored_callback = callback;
    return 1;
}

API int32_t fire_callback(int32_t value) {
    callback_fn current = stored_callback;
    if (current == NULL) {
        return -1;
    }
    return current(value);
}

API int32_t is_registered(void) {
    return stored_callback != NULL ? 1 : 0;
}

API void unregister_callback(void) {
    stored_callback = NULL;
}
~~~

**Explanation:**

- `stored_callback` is a function pointer in the C library's memory; it **does not** hold a strong Java reference or extend the arena's lifetime.
- `register_callback` only stores the pointer and returns 1 on success; it does not immediately call Java.
- `fire_callback` can be called at later points in the program; if already unregistered, it returns `-1` and **does not access the old pointer**.
- `unregister_callback` clears the pointer. In this sample there is only one thread and no queue, so when it returns there are no remaining invocations using the pointer.
- Do not upgrade the sample to multi-threaded simply by adding `pthread_create`. When `fire` and `unregister` run concurrently, accessing `stored_callback` without synchronization is a C data race. You must design proper registry lock/refcount/quiescence separately.

### 5.2. Java file `UpcallLifetimeDemo.java`

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

public final class UpcallLifetimeDemo {

    /*
     * Do not let any Java Throwable escape the upcall target.
     * The C protocol receives a sentinel code when the callback fails.
     */
    private static int onValue(int value) {
        try {
            return Math.multiplyExact(value, 2);
        } catch (Throwable failure) {
            return Integer.MIN_VALUE;
        }
    }

    public static void main(String[] args) throws Throwable {
        MemorySegment escapedStub;

        try (Arena arena = Arena.ofShared()) {
            Path library = Path.of(
                    System.mapLibraryName("upcalllifetime"))
                    .toAbsolutePath();

            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            MethodHandle register = linker.downcallHandle(
                    symbols.find("register_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle fire = linker.downcallHandle(
                    symbols.find("fire_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            MethodHandle isRegistered = linker.downcallHandle(
                    symbols.find("is_registered").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));

            MethodHandle unregister = linker.downcallHandle(
                    symbols.find("unregister_callback").orElseThrow(),
                    FunctionDescriptor.ofVoid());

            MethodHandle target =
                    MethodHandles.lookup().findStatic(
                            UpcallLifetimeDemo.class,
                            "onValue",
                            MethodType.methodType(
                                    int.class, int.class));

            MemorySegment stub = linker.upcallStub(
                    target,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    arena);

            escapedStub = stub;
            boolean registered = false;

            try {
                int rc = (int) register.invokeExact(stub);
                if (rc != 1) {
                    throw new IllegalStateException(
                            "callback registration failed");
                }
                registered = true;

                System.out.println(
                        "registered="
                        + (int) isRegistered.invokeExact());
                System.out.println(
                        "first=" + (int) fire.invokeExact(7));
                System.out.println(
                        "second=" + (int) fire.invokeExact(11));
                System.out.println(
                        "overflowFallback="
                        + (int) fire.invokeExact(Integer.MAX_VALUE));
                System.out.println(
                        "stubScopeAliveDuring="
                        + stub.scope().isAlive());

            } finally {
                /*
                 * Native code stops holding the pointer before close.
                 * Unregister in this demo cannot fail/wait on threads.
                 */
                if (registered) {
                    unregister.invokeExact();
                }
            }

            System.out.println(
                    "registeredAfter="
                    + (int) isRegistered.invokeExact());

            System.out.println(
                    "fireAfterUnregister="
                    + (int) fire.invokeExact(7));

        } // Arena closes only AFTER C clears the pointer.

        System.out.println(
                "stubScopeAliveAfter="
                + escapedStub.scope().isAlive());

        // Do not call the closed stub address again!
    }
}
~~~

**Why does the example guarantee the lifetime?**

1. The Arena is created **before** the library lookup and the stub, staying alive until the end of the `try` enclosing all downcalls.
2. `SymbolLookup.libraryLookup(library, arena)` loads and looks up the library scoped to the arena; it is not unloaded while the callback is still registered.
3. Java creates a `MethodHandle` with the exact type `int(int)` and then `upcallStub` in the live arena.
4. Once C registers successfully, `registered=true`; every exit path from the inner `try` block goes through `finally` and `unregister_callback`.
5. `fire_callback` is called twice **after** `register_callback` has returned. The stub must stay alive throughout this interval.
6. The C code has a single Java thread, with no asynchronous event queue or thread holding a copy of the pointer; `unregister_callback` is synchronous and completely clears the pointer.
7. After unregistering, Java checks C `is_registered()==0` and calls `fire_callback` to receive `-1` without **dereferencing the pointer**.
8. Only after there is no longer a callback registration does the arena close. `escapedStub` is still held by Java to check its scope, but it can no longer be called from C.

**Production note:** if `unregister` can throw or does not guarantee draining, the arena's `try-with-resources` could close on an exception path **while C still holds the pointer**. This sample is safe because the demo's `unregister_callback` is designed as a synchronous, non-failing operation with no concurrent callbacks. For SDKs with asynchronous unregister, the owner must control closing with a dedicated state machine.

### 5.3. Compiling on Linux/macOS/Windows

Put both files in the same directory. Use JDK 22+ and a C11 compiler matching the JVM architecture. FFM does not use JNI headers, so **`javac -h` is not needed**.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  upcalllifetime.c -o libupcalllifetime.so

javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  upcalllifetime.c -o libupcalllifetime.dylib

javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /W4 upcalllifetime.c /Fe:upcalllifetime.dll
javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

`System.mapLibraryName("upcalllifetime")` returns the OS-specific library filename, such as `libupcalllifetime.so` or `upcalllifetime.dll`. `toAbsolutePath` points to the **current working directory**: run Java from the directory containing the binary. `SymbolLookup.libraryLookup(Path, Arena)` is a restricted method; `--enable-native-access=ALL-UNNAMED` applies to code on the class path. With a named module, replace it with the specific module to restrict permissions.

`Linker.downcallHandle` and `Linker.upcallStub` are also restricted operations. If you encounter `IllegalCallerException` or a native access warning, check your startup options, JDK version, and module configuration. If you encounter a library/symbol lookup error, check the filename, exported C symbols, compiler flags, OS/CPU architecture, and working directory.

### 5.4. Expected Output

~~~text
registered=1
first=14
second=22
overflowFallback=-2147483648
stubScopeAliveDuring=true
registeredAfter=0
fireAfterUnregister=-1
stubScopeAliveAfter=false
~~~

**Why are these lines correct?**

- `register_callback` returns 1 and stores the pointer → C reports registered.
- `fire_callback(7)` calls `onValue(7)` → 14. The callback does not expire after the first call.
- `fire_callback(11)` → 22, demonstrating that the pointer stays alive across multiple calls.
- `fire_callback(Integer.MAX_VALUE)` causes `Math.multiplyExact` to throw `ArithmeticException` inside the Java target, but the target catches `Throwable` and returns the sentinel `Integer.MIN_VALUE`; C does not receive a Java exception across the ABI.
- While still inside the arena, `stub.scope().isAlive()` is true.
- Java calls `unregister_callback`; C clears the pointer. `is_registered` returns 0 and `fire_callback` refuses to call it, returning -1.
- Java exits `try` and closes the arena; even though `escapedStub` is still a Java object, the scope is no longer alive, so it returns false.

The output above is inferred from the code and API contract; whether it runs successfully depends on the JDK, C compiler, and loading the native library in the right environment. **It is unnecessary, and unsafe, to try calling the pointer after arena.close to test for a crash.**

## 6. Why Are There Three Separate Lifetimes?

**Lifetime 1 — native stub.** `Linker.upcallStub` binds the stub to the arena. Once the arena closes successfully, native code no longer has the right to call that address.

**Lifetime 2 — C registration.** C may keep the pointer in a global variable, struct, event queue, or pass it to a thread. FFM is not automatically notified when a C library no longer wants to call a callback.

**Lifetime 3 — Java state and native library.** The Java target may use objects, buffers, or a second arena. The C library also needs its machine code/ABI to remain present long enough. Closing other state or unloading the shared library too early can cause the callback to fail even if the stub arena is still alive.

| Lifetime | Safe termination condition |
|---|---|
| Stub arena | Native code can no longer call the pointer |
| Java callback state | The last callback has completed and there are no remaining users |
| Native registration | Unsubscribed and confirmed drained by the SDK |
| Library lookup | No remaining callbacks/downcalls/native workers need the library code |
| Native user data | No remaining borrowed pointers/slices used by the callback or C |

**Holding `MemorySegment stub` in a Java field is not enough if `arena.close()` has already happened.** Nor should you use `Arena.ofAuto()` just because GC manages its lifetime: a raw pointer held by C does not automatically extend the reachability of the Java owner.

## 7. Synchronous Callbacks vs. Deferred Callbacks

### Called only synchronously, without retaining the function pointer

~~~c
typedef int32_t (*callback_fn)(int32_t);

int32_t call_once(callback_fn fn, int32_t x) {
    return fn(x);
}
~~~

This is an illustrative C function. If the C contract **guarantees it does not retain the pointer once `call_once` returns**, a short-lived arena can be used:

~~~text
Arena create
  -> upcallStub
  -> downcall(call_once)
      -> C calls Java target
      -> C returns
  -> arena.close
~~~

### Registered to be called back later

~~~c
static callback_fn stored;

void subscribe(callback_fn fn) {
    stored = fn;
}
~~~

This is an illustrative C snippet, **unsafe under concurrent access without a lock**. `subscribe` only retains the pointer; the callback may occur after the Java method returns, triggered by a timer, network packet, GPU completion, native worker, or SDK event loop. The arena must stay alive until the entire subscription ends, not just across the `subscribe` call.

An API named `stop` does not prove callbacks have stopped. Check the SDK documentation to see whether `stop` is a synchronous drain or merely a stop request that completes later.

## 8. Unregister Does Not Necessarily Eliminate Running Callbacks

Dangerous race:

~~~text
Native thread A                     Java thread B
      |                                   |
load g_callback                        unregister()
      |                                   |
      |                              g_callback = NULL
      |                                   |
      +-- already holds pointer copy  arena.close()
      |                                   |
      +---------------------> calls freed pointer
~~~

In C, one thread can read `g_callback` into a local variable before another thread clears the global variable. Even though the global pointer is NULL after unregister, the old copy still exists.

### Strong unregister vs. weak unregister

| SDK contract | After unregister returns | Can close arena immediately? |
|---|---|---|
| **Synchronous unregister and drain** | No remaining registration, queued/active callbacks, or pointer copies will ever call again | Yes, if that is a guarantee explicitly documented by the SDK |
| **Remove-from-registry only** | Prevents new callbacks, but callbacks already running or whose pointer is already held by a worker may continue | No; must join/drain |
| **Asynchronous unregister request** | SDK has received the command, not yet completed | No; must wait for confirmation |
| **Unregister + completion future** | Future may indicate request accepted or callback quiescent, depending on the contract | Only close after the “no future callback possible” milestone |
| **No unregister API** | Pointer may exist for the SDK's entire lifetime | Keep arena alive as long as the SDK can still call; may require process lifetime |

An API returning `OK` meaning only “request received” may not mean workers have stopped. You must distinguish **acceptance**, **cancellation**, and **completion**.

## 9. Multi-threaded Native Protocol: Quiescence/Lease

In a real SDK, a state machine and synchronization are required:

~~~text
              ACTIVE
                |
    native event takes lease
                |
      in_flight += 1
                |
       Java callback runs
                |
      in_flight -= 1
                |
 request_unregister()
                |
              STOPPING
      no new leases granted
      cancel/drain queued jobs
      wait in_flight == 0
                |
             QUIESCENT
                |
       Java arena.close()
                |
              CLOSED
~~~

An illustrative C algorithm with a `mutex`/`condition variable`:

~~~text
register(callback):
  lock(mutex)
  if state != UNREGISTERED: fail
  store callback pointer
  state = ACTIVE
  unlock(mutex)

reserve_and_invoke(value):
  lock(mutex)
  if state != ACTIVE: unlock; return NO_CALLBACK
  in_flight++
  local_callback = callback
  unlock(mutex)

  result = local_callback(value)  // do not hold mutex during upcall

  lock(mutex)
  in_flight--
  if state == STOPPING && in_flight == 0:
    signal(all_done)
  unlock(mutex)
  return result

unregister_and_drain():
  lock(mutex)
  state = STOPPING
  callback = NULL
  prevent_new_reservations()
  cancel_or_count_queued_work()
  while in_flight != 0 || queued_work_can_call:
    wait(all_done, mutex)
  state = QUIESCENT
  unlock(mutex)
  return COMPLETE
~~~

This is **pseudocode**, not runnable C11 source. To implement it, you must define the mutex, condition variable, memory ordering, and how to guarantee counters are always decremented even when a native worker encounters an error. Key goals:

1. **Increment the in-flight count before releasing the lock and before the worker uses the pointer.**
2. **Prevent new turns under the same lock/protocol** when transitioning to STOPPING.
3. Do not close the arena until the number of leases and queued jobs that can call the callback reaches zero.
4. Only report QUIESCENT when there is genuinely nowhere left that can call the pointer.

If a native worker **puts the pointer into a queue** before starting the invocation, the queue item must also be treated as holding a lease, or must be safely canceled before close. Counting only currently running Java targets is not enough when the queue still holds pointers.

### Do not hold a lock when entering a Java callback

If native code holds the registry mutex and then calls the Java target, and the target reentrantly calls `unregister` or another API that also needs the mutex, it can easily deadlock. The right approach is to increment `in_flight` under the lock, release the lock before the upcall, and then decrement the counter after the upcall returns.

### A callback requesting close on itself can self-deadlock

~~~text
C callback enters Java target
  -> Java target calls owner.close()
  -> close requests native_unregister_and_drain()
  -> drain waits for in_flight == 0
  -> in_flight includes the current callback itself
  -> callback cannot return because it is waiting for drain
~~~

**Defer the drain/close** to a coordinator outside the callback, or design a protocol that does not wait on itself. Do not close the stub arena while the current callback has not yet completed.

## 10. Java Owner and State Machine

For long-lived callbacks, a wrapper should own the `Arena`, `MethodHandle`, `MemorySegment stub`, registration token, and state.

| State | Can emit callbacks? | Can close arena? |
|---|---|---|
| NEW | No | Yes, if pointer has not been handed out |
| REGISTERING | Possibly, depending on whether C register calls synchronously | Unclear until result is known |
| ACTIVE | Yes | **No** |
| STOPPING | Running/queued callbacks may still occur | **No** |
| QUIESCENT | Native has confirmed no callers remain | **Yes** |
| CLOSED | No | Do not call close a second time |
| FAILED_STOP | Native callers may still remain | Unsafe to force close |

Owner model:

~~~text
CallbackOwner.start():
  create arena
  create MethodHandle and upcall stub
  call native register
  if success: state ACTIVE

CallbackOwner.close():
  transition ACTIVE -> STOPPING (lifecycle lock)
  stop accepting new operations
  call native unregister_and_drain
  if native confirms QUIESCENT:
      arena.close()
      state = CLOSED
  if failed:
      state = FAILED_STOP
      do not deallocate stub while native can still call
~~~

This is an **algorithmic skeleton**, not a standalone compilable class. If the wrapper wants `close()` to be idempotent, it must ensure only one caller actually invokes `Arena.close()`; `Arena.close()` itself is **not idempotent** and can throw `IllegalStateException` on a second close.

Do not hold the lifecycle lock while waiting for native drain if a completing callback needs that same lock, as that will deadlock. You can mark STOPPING under the lock, release the lock, wait for native, and then reacquire to commit CLOSED.

### A try-with-resources trap

`try (Arena arena = ...)` automatically calls `close()` on every exit path from the scope, **even when unregister fails**. This can cause UAF if native code still holds the pointer. The runnable example is safe because C unregister is synchronous, non-failing, and single-threaded; real SDKs with asynchronous/failable unregister must use a coordinating owner to **close only after quiescence**.

If you cannot confirm C has stopped using the pointer, keeping the arena alive and reporting a controlled resource-leak error is sometimes safer than freeing a stub that C can still call. This is a state that needs an architectural fix rather than swallowing the error.

## 11. Do Not Let Java Exceptions Escape the Upcall Target

`Linker.upcallStub` creates a direct bridge from a C function pointer into a Java target. According to JDK 22 `Linker`, if the target throws an exception across the upcall boundary, the JVM **may terminate abruptly**. Therefore, the callback boundary needs to catch errors and return a status according to the C ABI.

In the example:

~~~java
private static int onValue(int value) {
    try {
        return Math.multiplyExact(value, 2);
    } catch (Throwable failure) {
        return Integer.MIN_VALUE;
    }
}
~~~

This is a valid method. `Math.multiplyExact(Integer.MAX_VALUE,2)` throws `ArithmeticException`, but it is caught, so C receives a sentinel number instead of a Java exception.

In production:

- Catch at the outermost layer of the callback bridge, even when the callback invokes a user listener or plugin.
- Translate errors into a return code or enqueue them for error handling with a clear policy; do not throw across the upcall.
- Do not use a complex logger inside `catch` if the logger itself could throw.
- Do not assume every `Error` is recoverable; catching `Throwable` is merely a barrier so nothing crosses the ABI.
- The callback must return the exact carrier type; the error branch of `int(int)` must also return `int`.
- For `void` callbacks, you cannot arbitrarily return an integer error code; another status protocol is needed.
- Do not assume Java `catch` will save you from a C ABI mismatch, stub use-after-free, or native memory corruption.

## 12. Thread Confinement and Callback State

A native SDK may invoke a callback from a different thread than the one that registered it, or from multiple native threads concurrently. If the Java target uses `ArrayList`, a mutable map, a confined native segment, UI state, or `ThreadLocal`, these must be considered separately.

- `Arena.ofShared()` is usually a better fit when callbacks may be cross-thread and require explicit closing.
- `Arena.ofConfined()` fits certain synchronous/clearly confined calls; do not assume an arbitrary native thread can access confined resources.
- `Arena.ofAuto()` does not provide a completion handshake, and GC does not know a C pointer is still in use.
- `Arena.global()` lives indefinitely and can create memory leaks with repeated short-lived registrations.

**A shared arena does not mean the callback target is thread-safe.** If multiple threads update state, use synchronization/atomics or an actor/event-loop. Do not save one thread's `JNIEnv*` to use on another thread if the system also has JNI code, because `JNIEnv*` is thread-bound.

A live callback may access another native segment that has already been closed: the **stub** arena being alive does not automatically extend the lifetimes of resources the callback uses. The owner must manage the entire dependency graph.

## 13. Native Library Lifetime Matters Too

`SymbolLookup.libraryLookup(Path, Arena)` loads/retrieves symbols and binds the lookup/library lifetime to the arena, per the API contract. If the library's arena is closed while native code is running or a callback has not been unregistered, there is a risk of **unloading** code that is still needed.

The Java example uses the same arena for lookup and the stub. This makes sense because both are released only after C has no remaining registration. For applications where the library lifetime is longer than the callback lifetime, you can use separate arenas or loaders, but a clear order is needed:

~~~text
load library
  -> create stub and register
  -> callbacks active
  -> unregister + drain
  -> close stub arena
  -> when no downcalls/native work remain: release library lifetime
~~~

`System.loadLibrary` + `SymbolLookup.loaderLookup()` have different symbol visibility and classloader lifetime policies than `libraryLookup(Path,Arena)`. Do not swap them interchangeably just because the API names look similar. In all cases, the callback pointer must not outlive either the stub or the required native code.

## 14. Callbacks with Captured State

A target can be a `MethodHandle` bound to a Java object:

~~~java
final class Stats {
    private long events;

    synchronized int onEvent(int value) {
        events++;
        return value + 1;
    }
}
~~~

This is an illustrative class. A `findVirtual` + `bindTo(stats)` can make the target carry `Stats` state. You must design for:

- Java state must remain reachable according to the owner's lifecycle.
- If the state has `close()`, do not close it before the last callback completes.
- If callbacks run in parallel, the state must be thread-safe.
- Do not use `WeakReference` to “know when C no longer wants callbacks”: GC does not manage C registrations.
- Avoid having a callback receive an event after STOPPING and continue using closed resources; policy may return a “stopped” code, but the stub must only be freed after drain.

Keeping a `target`/`state` field in the owner clarifies ownership, but **does not save the stub** if the arena closes. The lifetime of the state and the lifetime of the native function pointer must be managed together.

## 15. Common Mistakes

| Mistake | Why it is dangerous | Fix |
|---|---|---|
| Closing the arena as soon as `register` returns | C still holds the function pointer | Keep the arena alive across the entire registration |
| Keeping a `MemorySegment stub` field while closing the arena | A Java reference does not keep freed native backing alive | Close only after drain |
| `unregister` only clears the global pointer | Another worker may already have copied the pointer | Count in-flight/queued leases |
| Using `Arena.ofAuto()` because C will hold the pointer | GC does not treat a raw C pointer as a Java strong reference | Explicit owner + close |
| Using the global arena for thousands of callbacks | Stubs are not deallocated in a timely manner | Arena per registration/owner |
| Descriptor uses `JAVA_LONG` instead of `ADDRESS` | Wrong ABI for a function pointer | Use `ADDRESS` |
| Java target has a type not matching the C typedef | Undefined behavior/crash | Validate ABI before registering |
| Target throws an exception across FFM | JVM may terminate abruptly | Catch and return status |
| Native holds a mutex during a Java upcall | Reentrant callback may deadlock | Take lease first, unlock, then call |
| Callback calls close on itself and waits for drain | Callback waits on itself | Defer close until after the callback |
| `shutdownNow()` then close | Worker may still be running | Actual join/completion |
| Testing by calling the pointer after close | Can crash the entire process | Only check scope/registry, do not dereference |
| Not handling register failure | Arena may leak or C may hold an unclear pointer | Atomic register contract, proper cleanup |
| Unregister fails yet `try` still closes | C may call the freed address | Quarantine; close only after quiescence |
| Library unloaded before unregister | Native code is still in use | Stop/drain before unload |
| Copying the pointer to a long and reusing it | No temporal bounds when C uses a raw address | Do not export the pointer indefinitely |
| Callback state closed before the last callback | Stub is alive but state is invalid | Tie state lifetime to registration |
| Multiple Java closers | Double-closing the arena, races | Single owner, state machine/lock |
| Using sleep to wait for workers | Timing does not prove quiescence | Real future/join/condvar/ack |
| Not counting queued jobs | Worker has the pointer but is not yet in-flight | Reservation lease from the moment the queue accepts the pointer |

## 16. Testing Safely

Do not rely on “it has never crashed” to prove a callback has the right lifetime. Test observable conditions without **calling a freed pointer**:

1. Register succeeds; C reports ACTIVE status.
2. C invokes the callback during the first downcall and returns the right value.
3. C invokes the callback a second time after `register` has returned, confirming the stub is still usable.
4. Java target intentionally triggers an internal exception that is caught; C receives the sentinel, and the JVM does not crash.
5. Unregister results in no pointer remaining in the C registry.
6. Call `fire` **after unregister but before arena.close**: C must refuse without dereferencing the pointer.
7. Close the arena after native QUIESCENT has been proven; check `stub.scope().isAlive()==false`.
8. Do not execute callbacks through a closed stub.
9. Register failure leaves no ambiguous partial registration.
10. Two native threads case: unregister blocks new turns and waits for all in-flight calls.
11. Queued-but-not-started events are canceled/counted before freeing.
12. Reentrant callback calling requestStop does not self-deadlock.
13. Unregister timeout does not automatically close the arena.
14. Two Java close callers do not cause a double-close.
15. Native library remains alive while callbacks and downcalls have not completed.
16. Test memory leaks/native allocations under repeated register/unregister cycles.
17. Test target state, captured references, and Java classloader lifetime in a plugin environment.
18. Test ABI/architecture on the exact production OS/CPU.

Race tests should use `CountDownLatch`, barriers, or native condition variables for coordination, not `Thread.sleep(...)`. Native sanitizers can help detect use-after-free in C code, but you should not intentionally dereference a freed stub address in a live JVM.

## 17. Self-Check Questions

**1. What does `upcallStub` return?** A zero-length `MemorySegment` holding the C function pointer address; its lifetime is tied to the arena passed in.

**2. C has stored the pointer and the Java registration method has returned. Can you close the arena?** No, unless the contract proves C can never call the pointer again later.

**3. Why is keeping a Java field `stub` not enough?** Because the arena may already be closed; a live reference does not reallocate the native trampoline.

**4. Do `register_callback` and the callback itself use the same FunctionDescriptor?** No. Register takes `ADDRESS`, whereas the example callback takes/returns `JAVA_INT`.

**5. The SDK clears the global pointer variable, but a native thread has already copied the pointer. Is it safe to close?** Not yet. You must wait for or cancel existing leases holding the pointer.

**6. Is `Arena.ofAuto()` suitable for callbacks held long-term by C?** It is not a way to guarantee the lifecycle; GC does not know that a raw C pointer is a registration that needs to be kept alive.

**7. Does `Arena.ofShared` automatically synchronize mutable state in the Java target?** No. The target and the native registry need their own synchronization.

**8. What happens if a Java callback throws an exception?** JDK 22 warns that the JVM may terminate abruptly if an exception crosses the upcall boundary. Catch it in the target and return a C error code.

**9. What bug can a callback hit if it calls unregister-and-drain on itself?** Self-deadlock if drain waits for the current callback to finish. Defer the close.

**10. Why is the example's call to fire after unregister still safe?** C checks for a NULL pointer and returns -1 without calling the old stub address.

**11. Is `Future.get()` on submitting a native job enough on its own?** No, if it only confirms submission and does not confirm that the native callback consumer has stopped.

**12. Is closing an arena a second time a no-op?** No. `Arena.close()` is not idempotent; the wrapper must manage state to avoid repeating it.

## References

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `upcallStub`, native function pointer, ABI safety, target exception handling.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): scope, lifetime, `ofShared`/`ofConfined`, close semantics.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup(Path, Arena)` and library lifetime.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): native calling signatures for upcalls/downcalls.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length address segment and scope.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM stabilized in JDK 22.
- [Dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): restricted native access and `--enable-native-access` option.

## Key Takeaways

**An upcall stub is a native function pointer whose lifetime is controlled by an Arena.** As long as the native library can still call the pointer, the arena must stay alive.

The right sequence:

1. Create a target `MethodHandle` whose type matches `FunctionDescriptor` and the C ABI.
2. Create the stub with `Linker.upcallStub` inside an arena managed by a single owner.
3. Register the pointer; keep the arena/stub/target state alive across all points where the library can still call back.
4. When stopping, prevent new callbacks, unregister the pointer, cancel/drain the queue, and wait for in-flight calls to complete.
5. Only when **quiescent**, call `arena.close()` once; also manage the library lookup lifetime.
6. Do not let Java throwables cross the upcall; return a status per the C protocol.
7. Do not try calling a freed pointer to test: that can be a memory-safety bug that crashes the JVM.

**One sentence to remember:** *A callback's lifetime ends when the library can no longer call back, not when the Java registration method returns.*
