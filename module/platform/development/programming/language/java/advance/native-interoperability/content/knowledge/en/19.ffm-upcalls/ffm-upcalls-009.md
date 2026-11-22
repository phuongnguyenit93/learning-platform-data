# Unregistering a callback, waiting for in-flight calls, and then closing the Arena in Java FFM

## 1. The core of the problem

In the Foreign Function & Memory API (FFM), a Java program can use `Linker.upcallStub` to create a **native function address** for a Java `MethodHandle`. A C library can hold this address and call back into Java whenever an event occurs.

~~~java
// JDK 22+, illustrative snippet, not a standalone program.
MemorySegment functionPointer = linker.upcallStub(
        target,
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT),
        arena);
~~~

`functionPointer` is a `MemorySegment` representing the **upcall stub address**, not a callback registration automatically managed by FFM. Java code itself must pass this address to the C library through a registration API.

Once C has stored the pointer, the dangerous scenario:

~~~text
Native worker T1                       Java controller T2
--------------------------------       -------------------------------
pointer = registered_callback;
                                       unregister_callback();
                                       arena.close();  <-- frees stub
pointer(42);             <-- calls an address that may have become invalid
~~~

**Simply removing the callback from the registry does not mean running or about-to-run callbacks have finished.** T1 may have already read and held the pointer before T2 unregistered. If T2 closes the Arena too early, C can still call a raw pointer to freed code memory, leading to memory corruption, a JVM crash, or undefined behavior.

Rule of this article:

> **Block new callback calls → wait for all already-admitted calls to complete → confirm workers/queues no longer use the address → only then close the Arena.**

These three milestones must be clearly distinguished:

| Milestone | Meaning | Safe to close Arena? |
| --- | --- | --- |
| `unregisterRequested` | Java has just sent the unregistration request | No |
| `noNewCallbacks` | Native registry rejects new dispatches | Not enough |
| `drained` / `quiescent` | All in-flight invocations, held pointers, or queued items have finished processing per contract | Yes, if no users of related resources remain |
| `arena.close()` | Upcall stub lifetime ends, memory owned by the arena is freed | Must occur after drained |

**Article scope:** Java FFM has been final since **JDK 22**, using Linux/x86-64 and C11/POSIX pthreads for runnable examples. The `Linker` and `Arena` APIs had specific characteristics in preview JDKs 19–21; code in this article targets JDK 22+.

## 2. What does FFM know about lifecycle, and what can it not know?

### 2.1. An upcall stub has the lifetime of its Arena

In JDK 22, `Linker.upcallStub(target, descriptor, arena)` creates a native function pointer that C can call. `arena` manages the lifetime of that stub address. Once Java calls `arena.close()` successfully, the stub address is no longer valid for C to call.

However:

- `Linker` does not automatically know **how many native threads** have stored the pointer.
- `Arena.close()` does not automatically remove the pointer from all registries, native queues, and event loops.
- Checking the scope of a Java `MemorySegment` does not replace checking all raw pointer copies existing in C.
- A native call through a freed function pointer does not necessarily produce a safe Java exception; C can crash the JVM.
- An `unregister` call in a C library might only remove the entry and return immediately; whether its semantics wait for active callbacks or not is a matter of **the library's own contract**.

### 2.2. Choosing `Arena.ofShared()` for the C worker callback example

~~~java
Arena arena = Arena.ofShared();
~~~

A shared arena allows segments bound to it to be used in a multithreaded context and can be closed explicitly. In the example, C creates a separate pthread to call the Java callback, so this is a simple choice for thread ownership.

Comparison:

| Arena | Lifetime | Threads allowed to use segment | Main issue |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Explicit close from owner | Only the thread that created the arena | Unsuitable if access/closing needs to happen outside the owner |
| `Arena.ofShared()` | Explicit close | Multiple threads | **Still must manage unregister and drain** |
| `Arena.ofAuto()` | GC decides when to reclaim | Multiple threads | Does not guarantee deadline-bound cleanup |
| `Arena.global()` | Lives for the entire process | Multiple threads | Cannot be closed to free stub, easily hides leaks |

**`ofShared` does not mean the C callback is automatically thread-safe.** It does not protect the callback's Java state, does not wait for native workers, and does not turn an asynchronous registration into a synchronous call.

### 2.3. Upcall and downcall paths

There are two kinds of FFM invocation:

~~~text
Java  -- downcallHandle -->  C register_callback(ptr)
Java  <-- upcall stub ---    C worker calls ptr(event)
Java  -- downcallHandle -->  C unregister_and_drain()
Java  -- Arena.close() -->   stub lifetime ends
~~~

- `downcallHandle` creates a Java `MethodHandle` to call a native function.
- `upcallStub` creates a native function pointer for C to call a Java `MethodHandle`.
- `SymbolLookup.libraryLookup` looks up C symbols in a shared library.
- `FunctionDescriptor` must match the ABI **exactly**: wrong argument count/order/types or return type can cause a crash.
- In real programs, downcalls, upcalls, and library lookup can all be restricted operations: enable native access for the appropriate module.

## 3. Subtle race: copying the pointer before it is removed

Suppose a native library uses a mutex only to manage a callback variable:

~~~c
/* Illustrative anti-pattern; not a standalone program. */
pthread_mutex_lock(&mu);
callback_fn local = registered_callback;
pthread_mutex_unlock(&mu);

/* Another thread may unregister and close the arena here. */

if (local != NULL) {
    local(42);  /* Risk of using an invalidated pointer. */
}
~~~

The mutex protects **reading the value in the registry**, but does not protect **the lifetime after the pointer has been copied**. If Java changes the registry pointer to NULL and then closes the Arena, `local` still holds the old pointer.

The correct pattern needs to combine **admission control** and **in-flight accounting**:

~~~c
/* Pseudocode: reservation/counter part, not standalone. */
pthread_mutex_lock(&mu);
if (!stopping && registered_callback != NULL) {
    callback_fn local = registered_callback;
    ++in_flight;       /* Reserve before unlocking. */
    pthread_mutex_unlock(&mu);

    local(42);         /* Callback runs outside the mutex. */

    pthread_mutex_lock(&mu);
    --in_flight;
    pthread_cond_broadcast(&changed);
}
pthread_mutex_unlock(&mu);
~~~

Unregistering also uses **the same mutex**:

~~~c
/* Pseudocode: unregister must wait for counter to reach zero. */
pthread_mutex_lock(&mu);
stopping = 1;
registered_callback = NULL;

while (in_flight != 0) {
    pthread_cond_wait(&changed, &mu);
}
pthread_mutex_unlock(&mu);

/* Must join/ack event sources and queued work before reporting drained. */
~~~

When a worker is admitted to call the callback, it increments `in_flight` **before releasing the mutex**. Therefore, unregister cannot falsely observe `in_flight == 0` while a worker has already captured the pointer but has not yet been "counted".

Do not wait for the counter using an unsynchronized busy loop; nor rely solely on C `volatile`. A POSIX mutex and condition variable provide explicit synchronization for `in_flight`, `stopping`, and `registered_callback`.

## 4. Lifecycle contract that should be clearly specified in the native API

A callback registration API should define:

1. **Registration ownership:** who creates the registration, who is allowed to unregister, and whether multiple calls are supported.
2. **Admission boundary:** after which point the native library does not allow a new dispatch to hold the pointer.
3. **Active reservation:** a callback is considered in-flight from **before the thread releases the lock and holds a copy of the pointer**, not only from when the Java target begins.
4. **Completion:** after the callback actually returns, the native worker decrements the counter and notifies.
5. **Drain:** native unregister waits for the active count to reach 0, along with all related native workers/queued jobs.
6. **Acknowledgement:** returning success confirms that no one can call that function pointer anymore.
7. **Close:** Java only closes the Arena containing the stub after acknowledgement.
8. **Failure:** if drain is not confirmed, do not close merely because of a timeout or Java `Future.cancel(true)`.

State machine:

~~~text
NEW
 |
 | create stub, register pointer
 v
REGISTERED -- request stop --> STOPPING
                                  |
                                  | block new admissions
                                  | wait in-flight == 0
                                  | join/ack workers
                                  v
                               DRAINED
                                  |
                                  | arena.close()
                                  v
                                CLOSED

STOPPING -- timeout/error --> NOT_CONFIRMED (Arena retained, escalate)
~~~

**Do not infer meaning from the name `unregister`.** Some libraries use it to remove a listener from a map and return immediately; other libraries make it a synchronous barrier. You must read the native documentation or build a wrapper with a verifiable protocol.

## 5. Complete C11 program: one worker, one upcall, and one drain barrier

The example consists of two files: `callback_drain.c` and `CallbackDrainDemo.java`. C creates **one pthread**, fires the callback once with the value 7, and then waits to stop; Java intentionally keeps the callback blocked on a latch. Main calls native unregister while the callback is running. C only returns success after the callback returns and the pthread joins.

### 5.1. File `callback_drain.c`

~~~c
#include <pthread.h>
#include <stddef.h>

typedef void (*callback_fn)(int);

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;

static callback_fn registered_cb = NULL;
static pthread_t worker;
static int running = 0;
static int stop_requested = 0;
static int in_flight = 0;

static void *worker_main(void *unused) {
    (void)unused;

    pthread_mutex_lock(&mu);

    if (!stop_requested && registered_cb != NULL) {
        /*
         * Reserve callback under the same mutex that unregister uses.
         * After ++in_flight, the controller must wait for this call.
         */
        callback_fn cb = registered_cb;
        ++in_flight;

        pthread_mutex_unlock(&mu);
        cb(7); /* Java FFM upcall; DO NOT hold the mutex. */
        pthread_mutex_lock(&mu);

        --in_flight;
        pthread_cond_broadcast(&cv);
    }

    /* Demo has a single event; worker waits for shutdown. */
    while (!stop_requested) {
        pthread_cond_wait(&cv, &mu);
    }

    pthread_mutex_unlock(&mu);
    return NULL;
}

/*
 * Controller registers one callback in the demo.
 * Returns 0 on success; negative value on error.
 */
int register_callback(callback_fn cb) {
    if (cb == NULL) {
        return -1;
    }

    pthread_mutex_lock(&mu);

    if (running) {
        pthread_mutex_unlock(&mu);
        return -2;
    }

    registered_cb = cb;
    stop_requested = 0;
    in_flight = 0;

    if (pthread_create(&worker, NULL, worker_main, NULL) != 0) {
        registered_cb = NULL;
        pthread_mutex_unlock(&mu);
        return -3;
    }

    running = 1;
    pthread_mutex_unlock(&mu);
    return 0;
}

/*
 * Must only be called by the controller, NOT inside the callback/worker.
 * Only one unregister caller at a time.
 * Returning 0 means native has drained and joined.
 */
int unregister_and_drain(void) {
    pthread_mutex_lock(&mu);

    if (!running) {
        pthread_mutex_unlock(&mu);
        return 0;
    }

    /* Block all new dispatches under the same admission lock. */
    stop_requested = 1;
    registered_cb = NULL;
    pthread_cond_broadcast(&cv);

    /* Wait for the reserved callback to actually return. */
    while (in_flight != 0) {
        pthread_cond_wait(&cv, &mu);
    }

    pthread_t to_join = worker;
    pthread_mutex_unlock(&mu);

    /* Join outside the mutex so the worker can lock mu and exit. */
    if (pthread_join(to_join, NULL) != 0) {
        return -4;
    }

    pthread_mutex_lock(&mu);
    running = 0;
    pthread_mutex_unlock(&mu);

    return 0;
}
~~~

### 5.2. Checking the C synchronization logic

- `register_callback` registers a callback and creates a pthread while the mutex is locked. The worker will have to acquire the mutex before deciding to dispatch.
- `worker_main` checks `stop_requested`, holds a local pointer, and increments `in_flight` under the same mutex.
- While the Java callback is blocking, the worker **does not hold the mutex**; thus unregister can acquire the mutex and set the stop flag.
- Unregister sets `registered_cb=NULL` to block new dispatches, then waits for `in_flight==0` via `pthread_cond_wait`.
- `pthread_cond_wait` releases the mutex while waiting, giving the worker a chance to decrement the counter and signal.
- The `while` loop is mandatory because spurious wakeups can occur and the predicate may not yet be satisfied.
- When the callback returns, the worker decrements the counter and calls `pthread_cond_broadcast`, then sees stop requested and returns.
- `pthread_join` waits for the worker to **actually terminate**, not just receive the stop request.
- Only after joining succeeds does `unregister_and_drain` return `0`.

**Demo limitations:** The API only has **one registration, one native worker, and one controller**. Do not call two `unregister_and_drain` concurrently; two callers might try to join the same pthread. In a production library, you need `STOPPING/DRAINED` states, a single shutdown owner, generation tokens, and coordination across controllers.

### 5.3. Building the shared library on Linux

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared -pthread \
  -o libcallbackdrain.so callback_drain.c
~~~

`-pthread` is the appropriate flag for compiling/linking POSIX threads with GCC/Clang. The two functions are not declared `static`, so under the default visibility configuration on Linux, they can be found with `SymbolLookup`.

In production, you should check the return values of `pthread_mutex_lock`, `pthread_cond_wait`, and OS primitives, as well as handle native worker cancellation. The example uses statically initialized primitives and focuses on the quiescence contract.

## 6. Complete Java 22+ program: register, wait for callback, drain, then close

### 6.1. File `CallbackDrainDemo.java`

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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class CallbackDrainDemo {
    private static final CountDownLatch ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch RELEASE =
            new CountDownLatch(1);
    private static final AtomicInteger RECEIVED =
            new AtomicInteger(-1);
    private static final AtomicReference<Throwable> CALLBACK_ERROR =
            new AtomicReference<>();

    /*
     * Callback matching C: void (*callback_fn)(int).
     * Do not let a Throwable escape across an FFM upcall.
     */
    private static void onValue(int value) {
        try {
            ENTERED.countDown();
            RELEASE.await();
            RECEIVED.set(value);
        } catch (Throwable error) {
            CALLBACK_ERROR.compareAndSet(null, error);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Arena arena = Arena.ofShared();

        MethodHandle unregister = null;
        boolean registered = false;
        boolean drained = false;

        try {
            Path path = Path.of("libcallbackdrain.so")
                    .toAbsolutePath();
            SymbolLookup lib =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle register = linker.downcallHandle(
                    lib.find("register_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            unregister = linker.downcallHandle(
                    lib.find("unregister_and_drain").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));

            MethodHandle javaTarget =
                    MethodHandles.lookup().findStatic(
                            CallbackDrainDemo.class,
                            "onValue",
                            MethodType.methodType(
                                    void.class, int.class));

            MemorySegment stub = linker.upcallStub(
                    javaTarget,
                    FunctionDescriptor.ofVoid(
                            ValueLayout.JAVA_INT),
                    arena);

            int registrationCode =
                    (int) register.invokeExact(stub);
            if (registrationCode != 0) {
                throw new IllegalStateException(
                        "Register failed: " + registrationCode);
            }
            registered = true;

            /* Know for sure the callback is running, do not guess timing. */
            if (!ENTERED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Callback did not start");
            }

            /*
             * Main will call unregister and may block.
             * Helper thread releases callback after an observation window of 100ms.
             */
            Thread releaser = new Thread(() -> {
                try {
                    Thread.sleep(100);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    RELEASE.countDown();
                }
            }, "callback-releaser");
            releaser.start();

            int stopCode = (int) unregister.invokeExact();
            if (stopCode != 0) {
                throw new IllegalStateException(
                        "Drain failed: " + stopCode);
            }
            drained = true;

            releaser.join();

            if (CALLBACK_ERROR.get() != null) {
                throw new IllegalStateException(
                        "Upcall failure", CALLBACK_ERROR.get());
            }

            System.out.println("registered=true");
            System.out.println("callbackEntered=true");
            System.out.println("unregisterStatus=0");
            System.out.println("received=" + RECEIVED.get());
            System.out.println(
                    "callbackFinishedBeforeReturn="
                    + (RECEIVED.get() == 7));
        } finally {
            /* Do not leave callback stuck if main throws an error. */
            RELEASE.countDown();

            /*
             * If already registered but not yet confirmed drained,
             * keep requesting native drain before closing.
             * When C returns an error, do not close a stub that C might call.
             */
            if (registered && !drained) {
                int code = (int) unregister.invokeExact();
                if (code != 0) {
                    throw new IllegalStateException(
                            "Drain not confirmed; Arena retained: "
                            + code);
                }
                drained = true;
            }

            if (!registered || drained) {
                arena.close();
            }
        }

        System.out.println(
                "arenaAliveAfterClose="
                + arena.scope().isAlive());
    }
}
~~~

### 6.2. Running Java

~~~bash
javac CallbackDrainDemo.java

java --enable-native-access=ALL-UNNAMED \
  CallbackDrainDemo
~~~

**Expected stdout if the program runs successfully on Linux x86-64 with JDK 22+:**

~~~text
registered=true
callbackEntered=true
unregisterStatus=0
received=7
callbackFinishedBeforeReturn=true
arenaAliveAfterClose=false
~~~

Line-by-line explanation:

- `registered=true`: C returned 0 upon receiving the callback pointer and starting the worker.
- `callbackEntered=true`: `ENTERED.await` confirmed C entered `onValue`.
- `unregisterStatus=0`: native unregister prevented new dispatches, waited for the callback to return, and joined the worker.
- `received=7`: the callback received the exact argument passed by C and wrote the result before returning.
- `callbackFinishedBeforeReturn=true`: Java can observe the callback's value after the native drain completes.
- `arenaAliveAfterClose=false`: Java closed the arena **after** acknowledgement, invalidating the scope.

In the example, `Thread.sleep(100)` only helps simulate a callback blocking long enough for the learner to observe. **The 100 ms duration is not the safety mechanism**. What provides proof of drain is native `in_flight`, the condition variable, and `pthread_join`.

### 6.3. Why not use a simple `try (Arena arena = ... )`?

With a long-lived, asynchronous callback registration, if code inside the block throws an exception, Java `try-with-resources` will call `arena.close()` upon exiting the block. If unregister/drain has not happened yet, that can be a **premature close**.

The example uses an explicit `Arena` and `finally` that mandates requesting drain before closing. If native code returns an error unable to verify quiescence, the example **keeps the arena unclosed**; this is a relative safety measure against use-after-free risk, **not an ideal operating mode**. Production needs logging, a watchdog, and an isolate/restart policy when a native worker is uncooperative.

### 6.4. A Java callback must not throw errors across C

The JDK 22 `Linker.upcallStub` documentation warns that the target method handle should not let exceptions escape out of the upcall. If that happens, the JVM may terminate abruptly. Therefore:

~~~java
// Illustrative safe pattern for the exception boundary.
static void onEvent(int code) {
    try {
        process(code);
    } catch (Throwable error) {
        reportFailure(error); // reportFailure must also not throw.
    }
}
~~~

In the full program, `onValue` catches `Throwable` and stores the error in an `AtomicReference` for the coordinating thread to check **after drain**. C receives a normal callback return and can decrement `in_flight` per protocol.

In real applications, Java callbacks should be kept short and avoid actions that can block indefinitely. If a callback only enqueues a Java job, you must address the **lifetime of data used by the job**: the job may continue running after the upcall returns.

## 7. Explaining the C and FFM signatures

C header of the demo:

~~~c
typedef void (*callback_fn)(int);
int register_callback(callback_fn callback);
int unregister_and_drain(void);
~~~

Java descriptors:

~~~java
// JDK 22+, snippet, not yet a standalone runnable file.
FunctionDescriptor callbackSignature =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);

FunctionDescriptor registerSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS);

FunctionDescriptor unregisterSignature =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);
~~~

| C signature | FFM descriptor | Java MethodHandle type |
| --- | --- | --- |
| `void callback(int)` | `ofVoid(JAVA_INT)` | `(int)void` |
| `int register_callback(callback_fn)` | `of(JAVA_INT, ADDRESS)` | `(MemorySegment)int` |
| `int unregister_and_drain(void)` | `of(JAVA_INT)` | `()int` |

Do not confuse a **pointer to a function** with the callback result. `ValueLayout.ADDRESS` is used to pass the function pointer; `ofVoid(JAVA_INT)` describes **the signature that pointer points to**.

Because `SymbolLookup.libraryLookup` uses the same Arena as `upcallStub`, closing it can also release/unload the library lookup when the native library is no longer in use. Thus, the unregister-drain-close order protects **both the stub and the library lifetime**.

## 8. Why must you unlock before calling the callback?

Anti-pattern:

~~~c
/* Wrong: holding the mutex across a user callback. */
pthread_mutex_lock(&mu);
registered_cb(7);
pthread_mutex_unlock(&mu);
~~~

The Java callback might call back into a C API that needs that same mutex, creating a **reentrancy deadlock**. The unregister controller also needs the mutex to update state and can be blocked indefinitely. The callback might wait on a future that is itself waiting on unregister, causing a hard-to-detect dependency cycle.

Correct order:

1. Lock.
2. Check state allowing dispatch.
3. Increment counter and capture pointer.
4. Unlock.
5. Call Java callback.
6. Lock.
7. Decrement counter, signal.
8. Unlock.

If the Java callback itself calls **synchronous `unregister_and_drain` on the very registration currently running**, it can still deadlock: unregister waits for the counter to reach zero, but the counter only decrements **after the callback returns**, while the callback is waiting for unregister to return.

**Fix:** the callback only **sends a non-blocking requestStop** to another controller and returns; that controller performs drain and close after the callback has exited.

## 9. Unregister might only mean “block further calls”, not “done”

Many C libraries provide APIs like:

~~~text
remove_listener(handle)       // Prevents generating new dispatches.
wait_for_idle(handle)         // Waits for already-dispatched callbacks to finish.
destroy_registration(handle)  // Frees context.
close_arena()                 // Java frees the upcall stub.
~~~

You cannot assume `remove_listener` includes `wait_for_idle` internally. Even a library with a `stop_stream()` API might:

- Stop the event producer, while the worker pool still has pending items.
- Remove the callback from a map, while a thread has already grabbed the old pointer.
- Cancel a new listener, while a callback has already been submitted to another executor.
- Wait for the main thread, while a secondary C thread still holds user-data.
- Return “stop requested”, not “stopped”.

If a library has no drain API, you sometimes have to write a C wrapper managing **admission + in-flight counter + join/ack**. Java cannot adequately check C raw pointers merely by inspecting `Thread.isAlive()` of a Java thread.

## 10. Systems with multiple native threads and registration generations

In the demo, **one callback** is called on **one worker**; `pthread_join` confirms that worker has exited. With multiple native threads, you must maintain registration state:

~~~text
Registration {
  id, generation
  state = ACTIVE | STOPPING | DRAINED
  callbackPointer
  activeCount
  nativeQueue
  workerHandles
  userDataPointer
}
~~~

Safe protocol for each registration:

~~~text
admit(event):
  lock
  if state != ACTIVE: reject
  activeCount++
  capture pointer and generation
  unlock

  invoke callback (without lock)

  lock
  activeCount--
  if state == STOPPING and activeCount == 0: notify
  unlock

stop_and_drain():
  lock
  state = STOPPING
  stop accepting new events
  remove pointer from registry
  while activeCount != 0: condition_wait()
  unlock
  join/fence remaining event sources and queues
  return DRAINED
~~~

Constraints:

- **The counter must be incremented before releasing the admission lock.** If incremented when starting the Java call, there is a race window where the worker already holds the pointer but is not yet counted.
- **Generation tokens** prevent an old callback from being treated as the callback of a new registration after a numeric ID/address is reused (ABA problem).
- Callbacks already **queued** but not yet run can be counted in active reservations or must be canceled+acked per contract. Do not ignore queued work.
- `user_data` may be a pointer to a native buffer or Java-owned state: keep user-data alive until drain too, not just the upcall stub.
- To support **multiple concurrent unregister controllers**, native state must ensure only one owner performs stop/join; other callers wait for the DRAINED state instead of jointly joining the same pthread.
- An atomic pointer store to NULL does not solve memory reclamation for readers that already hold the pointer. Lock-free algorithms require reference counting/hazard pointers/epochs or an equivalent safe mechanism.

With callbacks executing in parallel, you must count all active invocations and have sufficiently strong synchronization. `Arena.ofShared()` allows multithreaded access but **does not automatically make Java/native shared state thread-safe**.

## 11. Deallocation order for multiple resources

Besides the stub, a callback may use:

- Native library loaded via `SymbolLookup.libraryLookup(path, arena)`.
- `void* user_data` and buffers allocated with an Arena.
- Native context/registration handle of the library.
- Java target object and state captured by the callback.
- Worker pool, timers, event loop, or queues.
- Java tasks enqueued by the callback that still hold references to native memory.

A generally safe order:

~~~text
1. Stop accepting new events and issue the unregister request.
2. Block native dispatch admissions via synchronization.
3. Wait for callbacks that already hold the pointer to actually return.
4. Join/ack all related event sources and native workers.
5. Clean up native registration/context while the library is still loaded.
6. Wait for Java tasks using shared native data, or copy the data beforehand.
7. Close the Arena owning the upcall stub and native buffers.
8. Close the library Arena if separate (after all downcalls/users finish).
9. Release Java owner references.
~~~

Steps 5–8 must be adjusted according to the actual contract; the invariant is that **no native thread uses the callback pointer or library code after they are freed/unloaded**. The example uses a single shared Arena so the sequence is clearly visible.

**Do not** use `Arena.global()` as a general “quick fix”: the callback pointer will not be reclaimed, yet registries/event sources may still dispatch and native resources may leak until process exit.

## 12. Timeout: timing out is different from completing drain

A real system may set a deadline for shutdown. If a callback hangs in I/O or deadlocks, `unregister_and_drain` can wait forever. However, timing out does not prove the callback is safe to free.

| Result | Meaning | Allowed to close stub? |
| --- | --- | --- |
| `DRAINED` | Native confirmed no remaining users of the callback | Yes, per ownership |
| `STOPPING` | Admission blocked but still active | Not yet |
| `WAIT_TIMED_OUT` | Supervisor timed out without a quiescence ack | **No** |
| `FAILED` | Native API reported an error, state not proven | **No**, unless independently proven |
| `CANCEL_REQUESTED` | Only issued a cancel signal | **No** |

A `Future.cancel(true)` in Java also does not automatically stop a native C thread waiting for a callback to return. Java `Thread.interrupt()` has no contract to “kill a C function at any instruction”. If a callback blocks forever, fix the blocking path: cooperative cancellation, timeouts in native I/O itself, wake-up conditions, or **process isolation**.

With an uncooperative native library, the safer approach is sometimes to keep the Arena alive and mark a temporary error/leak, then restart/isolate the process. **Arbitrarily closing the Arena while C still holds a raw pointer can crash the entire JVM**, so do not treat closing after a timeout as “cleanup”.

## 13. Typical mistakes to avoid

### Mistake 1 — closing immediately after unregister

~~~java
// Wrong if unregister only removes the pointer from the registry.
int rc = (int) unregister.invokeExact();
arena.close();
~~~

You must clearly understand the return contract: does `rc == 0` actually imply **drain and quiescence**?

### Mistake 2 — waiting a few milliseconds and guessing the callback is done

~~~java
// Wrong: time is not synchronization.
unregister.invokeExact();
Thread.sleep(500);
arena.close();
~~~

A callback may block on I/O, be delayed by the scheduler, or still be queued. Only a protocol-compliant confirmation signal allows closing.

### Mistake 3 — not incrementing in-flight when capturing the pointer

~~~c
/* Wrong because there is a gap between copying the pointer and the counter. */
callback_fn cb = registered_cb;
/* unregister could close the stub here */
++in_flight;
~~~

Blocking admission and reserving must be atomic with respect to unregister.

### Mistake 4 — holding the mutex while calling the user callback

The callback may re-enter the library or wait for a controller that needs the mutex, causing a deadlock. Unlock before calling; every completion path must decrement the counter.

### Mistake 5 — callback synchronously unregistering itself

This is a self-deadlock: unregister waits for the current callback to finish; the callback waits for unregister. The callback only issues an async request, and a controller handles the drain afterward.

### Mistake 6 — using `try-with-resources` unchecked

~~~java
// Wrong if the callback outlives the block scope and an error occurs mid-way.
try (Arena arena = Arena.ofShared()) {
    nativeRegister.invokeExact(stub);
    operationThatMayThrow();
} // May close before unregister/drain.
~~~

For long-lived asynchronous registrations, use a lifecycle/`finally` ensuring native quiescence before closing, or an `AutoCloseable` abstraction whose close follows the proper protocol.

### Mistake 7 — trusting a Java latch for one callback means the whole registry is idle

One callback having returned does not prove other workers/queues no longer hold the pointer. The native registry must provide acknowledgement for **the entire registration**.

### Mistake 8 — exception escaping across an FFM upcall

~~~java
// Wrong: JVM may terminate abruptly when an exception escapes across an upcall.
static void badCallback(int value) {
    throw new IllegalStateException("unexpected");
}
~~~

Wrap the callback, record errors through an appropriate mechanism, and let C receive a return per the published ABI.

### Mistake 9 — freeing the user-data buffer before the stub

Even if the stub is still alive, the callback may dereference a `void* user_data` that has already been freed. Clean up **stub, user-data, and native context** after all users have finished.

### Mistake 10 — two controllers unregistering/joining concurrently

A pthread must not be joined concurrently by two uncoordinated controllers. Apply a single owner or a state machine ensuring one thread performs the drain while others wait for the result.

## 14. How to write a Java API that manages registration clearly

Instead of letting callers invoke `nativeUnregister()` and `arena.close()` in scattered places, you can encapsulate ownership:

~~~java
// Design pseudocode: NOT a standalone runnable Java program.
final class NativeCallbackRegistration implements AutoCloseable {
    // Holds: Arena arena, MemorySegment stub,
    // nativeHandle, state, lock and an unregister/drain function.

    public void close() {
        // (1) Serialize concurrent close attempts.
        // (2) Native unregister: stop admission.
        // (3) Await all in-flight callbacks and worker acknowledgement.
        // (4) If and only if DRAINED, close arena.
        // (5) Mark CLOSED. Otherwise report failure, retain resources.
    }
}
~~~

`AutoCloseable` is only useful if `close()` **implements the proper protocol**. If the native API only removes the callback without draining, putting it in `close()` does not add quiescence.

You can use a clearer result than a boolean:

| State | Status for caller |
| --- | --- |
| `REGISTERED` | Callback may still be dispatched |
| `STOPPING` | New events blocked, waiting for active ones |
| `DRAINED` | Native confirmed no users of the pointer remain |
| `CLOSED` | Arena closed successfully |
| `FAILED_NOT_DRAINED` | Shutdown must not be considered successful |

Do not use `Future.cancel(true)` or `Thread.isInterrupted()` as a shortcut to jump directly from REGISTERED to CLOSED.

## 15. Testing lifecycle/races in CI

| Test | Expectation |
| --- | --- |
| Unregister when callback has not been called yet | Native prevents dispatch, drains, then returns success |
| Unregister while callback is blocking | Does not return success before callback returns |
| Unregister after worker captures pointer, before calling | Reservation already incremented, drain waits properly |
| Multiple callbacks running concurrently | Active counter reaches zero after all finish |
| Callback returns very quickly | No lost wakeup or negative active counter |
| Callback re-enters library | No deadlock from holding registry mutex |
| Callback requests to stop itself | Only requests async; does not wait on itself |
| Callback reports Java error | Exception handled internally, does not escape upcall |
| Unregister returns native error | Arena not closed without drain guarantee |
| Waiting for drain past deadline | Reports WAIT_TIMED_OUT, does not close |
| New generation registered after old generation | Does not deliver old callback into new registration |
| Java task enqueued from callback | Task still using native data must also finish/copy |
| Native library unloaded | No worker remains executing code in the library |
| Shared Arena closed while users remain | Must be prevented by lifecycle protocol, not relying on GC |

**The core test of this article** is carried out directly through the two programs: Java waits for `ENTERED` to confirm the C→Java callback has started, holds it with `RELEASE`, calls native unregister, and only closes the Arena after unregister waits for the active count and joins successfully.

## 16. Pre-merge review checklist

- [ ] Understood whether the native unregister API only removes or guarantees drain?
- [ ] Is there an admission lock/state to block new callbacks?
- [ ] Does the worker reserve in-flight before releasing the lock and holding the pointer?
- [ ] Do all callback return paths release the reservation + notify?
- [ ] Are there other native queues, timers, or worker pools still holding the pointer?
- [ ] Can the callback run from C-created threads; is the Arena appropriate?
- [ ] Is the C registry mutex released before calling Java?
- [ ] Can the callback synchronously unregister itself and cause a self-deadlock?
- [ ] Does the Java upcall target catch exceptions and prevent `Throwable` from escaping?
- [ ] Does `FunctionDescriptor` match the C function-pointer ABI exactly?
- [ ] Is the native registration unregistered by only one owner at a time?
- [ ] Are concurrent unregister/re-register and generation reuse tested?
- [ ] Do queued Java tasks using native data get waited on?
- [ ] Is it confirmed that native workers have terminated before the library is unloaded?
- [ ] Are the stub and user-data kept alive until after drain?
- [ ] Does failure/timeout prevent `arena.close()` if there is no ack yet?
- [ ] Is `--enable-native-access` enabled for downcall/upcall/library lookup?
- [ ] Is there a test for an in-flight callback right when the controller wants to close?
- [ ] Are request-stop, drained, and arena-close timings measured and logged?
- [ ] When native cannot be canceled, is there proper escalation/isolation?

## 17. Self-check questions

1. Why is `registered_cb = NULL` not enough to prove the callback has stopped?
2. At what point must the in-flight counter be incremented?
3. Why not hold `pthread_mutex` while calling the Java callback?
4. Why must `pthread_cond_wait` be inside a `while` loop checking the predicate?
5. What guarantee does `pthread_join` add to the single-worker demo?
6. Can Java `Arena.close()` automatically erase raw pointers existing in C?
7. If the callback comes from another C thread, why is `Arena.ofShared()` convenient in the example?
8. Can a Java callback throw a `Throwable` across an upcall stub?
9. In the example, why is `ENTERED.await` more important than a `Thread.sleep` before unregister?
10. What does `unregisterStatus=0` prove under the written C contract?
11. If native unregister returns -4, can the Arena be closed as if drained?
12. Why must a callback not synchronously unregister its own current registration?
13. When a native library only has `removeListener`, what primitive does Java still need?
14. Does `Future.cancel(true)` guarantee the native worker has left the callback?
15. If a Java callback enqueues a task using a native buffer and returns, can the buffer be closed immediately?
16. Why must library unloading tied to `SymbolLookup.libraryLookup` be considered?
17. Why are generation tokens useful when reusing callback registration IDs?
18. Does `Arena.global()` fix the inherent race of a native registry?

**Suggested answers:** (1) a worker may have already captured the pointer or be running; (2) when granted dispatch permission, under the admission lock; (3) avoid deadlock/reentrancy; (4) guard against spurious wakeups and recheck the condition; (5) worker has actually terminated; (6) no; (7) multithreaded lifetime/access, still needs drain; (8) no, it can cause the JVM to terminate; (9) confirms the callback has started; (10) native blocked admission, waited for active zero, joined successfully; (11) no; (12) self-deadlock because it waits for the callback itself to return; (13) drain/fence/ack in-flight; (14) no; (15) not yet, must copy or wait for the task to complete; (16) workers must no longer execute library code; (17) prevents old callbacks from being misassigned to a new registration; (18) no, it only keeps the stub alive longer and risks leaking.

## 18. Authoritative references

- [Oracle JDK 22 — `Linker.upcallStub` and lifetime/exception warnings](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `Arena`: shared/confined and `close()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle JDK 22 — `SymbolLookup.libraryLookup` and native library lifecycle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `FunctionDescriptor`: `of`, `ofVoid`, carrier types](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Open Group/POSIX — `pthread_cond_wait`](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_cond_wait.html)
- [OpenJDK — FFM asynchronous upcall tests](https://github.com/openjdk/jdk/blob/master/test/jdk/java/foreign/TestUpcallAsync.java)

**Conclusion:** When a native library already holds an FFM callback address, **unregistering** is not equivalent to **all callback calls being finished**. Block admission, count and drain in-flight invocations, wait for all native workers/queued jobs to complete, and only then call `arena.close()`. Use a barrier/ack with a clear contract; do not rely on `sleep`, `Future.cancel`, or setting the registry pointer to NULL alone. If quiescence is not yet proven, keep the Arena alive and handle the error via operational policy rather than closing an upcall stub that C could still call.
