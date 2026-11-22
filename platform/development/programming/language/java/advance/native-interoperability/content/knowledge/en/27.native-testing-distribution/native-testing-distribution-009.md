# Testing Multiple Closes, Access After Close, and Late Callbacks in Java/Native Interoperability

## 1. Objectives and Scope of the Test

When Java works with a C/C++ library via JNI or the Foreign Function & Memory (FFM) API, a Java object may simply be an **owning wrapper** around a pointer, file descriptor, native handle, off-heap memory region, or callback function. If the wrapper is closed at the wrong time, the failure is often worse than an ordinary `IllegalStateException`: *double free*, *use-after-free* (UAF), reading corrupted data, leaks, deadlocks, or crashing the entire JVM.

This article focuses on three scenarios that must be tested before distributing a Java/native library:

1. **Multiple closes:** calling `close()` twice, multiple times, concurrently from multiple threads, and during error cleanup. The native resource must be freed **at most once**; the behavior of subsequent close calls must conform to the API contract.
2. **Access after close:** invoking Java/native operations after closing completes; also testing races between an in-progress operation and a thread starting to close. It must **block before passing a freed pointer into native code**.
3. **Late callbacks:** a callback that is already scheduled or running when `close()` is called; callbacks arriving during shutdown and even after closing finishes. It must not invoke an invalid listener or use a freed `jobject`/function pointer.

The Level 1 context is **Testing and Distribution**: therefore, this article does not stop at explaining the lifecycle. We need a clear *test oracle*, repeatable automated test execution, acceptance criteria before release, and observation of native errors using appropriate tools.

> **Core principle:** checking Java state only protects the Java layer. Before freeing native memory/registration, there must be a guarantee from the native runtime that **no worker or callback can still use the reclaimed memory region**.

## 2. Defining the Ownership Contract Before Writing Tests

A good test starts from the contract between the Java wrapper and the native library, rather than guessing from the current implementation.

| Contract Question | Must Specify |
| --- | --- |
| Who owns the native handle? | Exclusive wrapper ownership, shared ownership via reference count, or a borrowed handle only? |
| Is `close()` idempotent? | Does the wrapper intentionally define "subsequent close is a no-op" or intentionally throw an exception to catch bugs? |
| What is allowed after `close()`? | Pure Java metadata getters may be valid; any operation requiring a native pointer must be rejected. |
| What about an in-flight native operation? | Does `close()` wait for in-flight operations to finish, cancel safely, or return a "busy" error? |
| Which thread is a callback dispatched to? | Event loop, Java executor, a native worker attached to the JVM, or the caller's thread? |
| Does shutdown guarantee quiescence? | Does `unregister` only prevent new callbacks, or does it also **wait for existing callbacks to complete**? |
| What if freeing the resource fails? | Is there a `FAILED` state/controlled retry, or transition to an unrecoverable error; do not mark as "freed" when unknown. |
| Can handles be reused? | A *generation* identifier is needed to prevent old callbacks from being confused with a new session (ABA). |

For custom-designed JNI wrappers, **idempotent close** is often convenient for `try-with-resources`, cleanup in `finally`, and concurrent shutdown. However, this is **the wrapper's contract**, not a rule imposed on every native API.

**FFM difference:** starting from JDK 22, `Arena.ofConfined()` and `Arena.ofShared()` can be closed once; **`Arena.close()` is not idempotent**. Closing an already-closed arena throws `IllegalStateException`. An outer wrapper can implement idempotence itself while still closing the underlying arena exactly once. `Arena.ofGlobal()` and `Arena.ofAuto()` have their own lifecycles and cannot be treated as manually closed arenas.

### Recommended State Table for a Native Wrapper

```text
            create succeeds
NEW --------------------------------> OPEN
                                       |
                                       | close() starts
                                       v
                                    CLOSING
                                     |   |
                  reject new use ----+   +---- stop registration
                                         |     wait for in-flight work
                                         |     free exactly once
                                         v
                                      CLOSED
```

For a wrapper with an *idempotent close* contract:

- `OPEN` → `OPEN`: normal operation; starting an operation requires acquiring a **lease/in-flight counter** before leaving the synchronized block.
- `OPEN` → `CLOSING`: one thread wins coordination of close; prevents new operations/callbacks from being accepted.
- `CLOSING` → `CLOSED`: unregister callbacks, wait for all accepted operations/callbacks to complete, synchronize with native workers, destroy the resource once, then publish closed.
- `CLOSING` and `CLOSED`: subsequent close calls wait or return according to the contract; no additional `free` is performed.
- In any state other than `OPEN`, new operations throw `IllegalStateException` or a documented error result. Late callbacks are **safely ignored or reported as canceled**, without touching the old native handle.

If the destroy step fails, a real system must design a dedicated error state (`FAILED`) and retry/cleanup policy. Do not treat a `finally { state = CLOSED; }` as proof that native resources were freed successfully; the runnable example below uses a fake backend assuming unregister/destroy never fail to focus on illustrating races.

## 3. Required Test Matrix

| ID | Initial Setup | Trigger | Pass Criteria |
| --- | --- | --- | --- |
| T01 | Resource `OPEN` | `close(); close(); close();` | Native destructor called **exactly once**; subsequent calls follow the contract. |
| T02 | Resource `OPEN` | 10 threads concurrently call `close()` | No double free, no hang; all threads finish within deadline. |
| T03 | Resource `CLOSED` | `read/write/invoke` | Rejected at the Java boundary; native backend call count does not increase. |
| T04 | Operation has entered native, blocked by a latch | Another thread calls `close()` | Resource is not freed until the operation returns or cancels per protocol. |
| T05 | Callback has been accepted and is processing | Another thread calls `close()` | Close waits for the callback to finish (or follows defined cancellation protocol), then frees. |
| T06 | `close()` has transitioned to `CLOSING` | Native callback arrives | Callback is no longer delivered to listener; closed handle is not read. |
| T07 | `close()` completed | Late/queued callback | Ignored in a controlled way; no crash/UAF, listener not called. |
| T08 | Old handle freed, native reuses address for new handle | Old callback carrying old generation | Old event is rejected, not mistakenly bound to the new session. |
| T09 | Native unregisters, but callback is still in-flight | `close()` and callback race | Real *quiescence* barrier in native, context is not freed prematurely. |
| T10 | Native constructor fails midway | Error cleanup and repeated close | No leaked/duplicate cleanup; only frees what was acquired. |
| T11 | Native destroy throws error or reports unknown state | `close()`, then retry | Records error and exact state; does not silently call free twice. |
| T12 | On FFM shared/confined arena | Access or close at wrong time/thread | Correct FFM exception; do not project JNI wrapper semantics onto Arena. |

Each test must observe **both sides**: Java assertions (exceptions, number of callbacks received/ignored, state) **and** native evidence (allocation/free counters, sanitizers, logs, or per-handle generation). Relying solely on a boolean `closed` flag is insufficient.

## 4. Self-Contained Java 17+ Example: Testing Lifecycle with a Fake Native Backend

This lab uses **a single pure Java file** to test the state machine deterministically without needing `.so/.dll/.dylib` libraries. `FakePort` acts as the JNI/native backend with a `destroy` counter; in production, replace this interface with JNI bindings and test further with native instrumentation. The test uses `CountDownLatch` and `Future.get(timeout)` instead of "sleeping arbitrarily for a few seconds" to actively induce races.

**Create file `NativeLifecycleTest.java`:**

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.ConcurrentHashMap;

public final class NativeLifecycleTest {
    enum State { OPEN, CLOSING, CLOSED }

    interface NativePort {
        long create();
        void execute(long handle);
        void unregisterCallbacks(long handle);
        void destroy(long handle);
    }

    static final class FakePort implements NativePort {
        private final AtomicLong ids = new AtomicLong(900);
        private final ConcurrentHashMap<Long, AtomicBoolean> live =
                new ConcurrentHashMap<>();
        final AtomicInteger executions = new AtomicInteger();
        final AtomicInteger unregisters = new AtomicInteger();
        final AtomicInteger destroys = new AtomicInteger();

        public long create() {
            long h = ids.incrementAndGet();
            live.put(h, new AtomicBoolean(true));
            return h;
        }

        public void execute(long h) {
            AtomicBoolean alive = live.get(h);
            if (alive == null || !alive.get()) {
                throw new AssertionError("use after native free");
            }
            executions.incrementAndGet();
        }

        public void unregisterCallbacks(long h) {
            unregisters.incrementAndGet();
        }

        public void destroy(long h) {
            AtomicBoolean alive = live.get(h);
            if (alive == null || !alive.compareAndSet(true, false)) {
                throw new AssertionError("double native free");
            }
            destroys.incrementAndGet();
        }
    }

    static final class NativeOwner implements AutoCloseable {
        private final Object gate = new Object();
        private final NativePort port;
        private final long handle;
        private State state = State.OPEN;
        private int inFlight;
        private int delivered;
        private int ignored;
        // Test-only instrumentation; do not expose this in a public API.
        final CountDownLatch closeStarted = new CountDownLatch(1);

        NativeOwner(NativePort port) {
            this.port = port;
            this.handle = port.create();
        }

        void use(Runnable beforeNativeCall) {
            synchronized (gate) {
                if (state != State.OPEN) {
                    throw new IllegalStateException("resource is closing");
                }
                inFlight++;
            }
            try {
                beforeNativeCall.run();
                port.execute(handle);
            } finally {
                finishOperation();
            }
        }

        // Simulates a Java callback delivered through a valid native registration.
        void onCallback(Runnable listener) {
            synchronized (gate) {
                if (state != State.OPEN) {
                    ignored++;
                    return;
                }
                inFlight++;
            }
            try {
                listener.run();
                synchronized (gate) {
                    delivered++;
                }
            } finally {
                finishOperation();
            }
        }

        private void finishOperation() {
            synchronized (gate) {
                inFlight--;
                if (inFlight == 0) gate.notifyAll();
            }
        }

        int ignoredCallbacks() {
            synchronized (gate) {
                return ignored;
            }
        }

        int deliveredCallbacks() {
            synchronized (gate) {
                return delivered;
            }
        }

        @Override
        public void close() {
            boolean interrupted = false;
            synchronized (gate) {
                if (state == State.CLOSED) return;
                if (state == State.CLOSING) {
                    while (state != State.CLOSED) {
                        try {
                            gate.wait();
                        } catch (InterruptedException e) {
                            interrupted = true;
                        }
                    }
                    if (interrupted) Thread.currentThread().interrupt();
                    return;
                }
                state = State.CLOSING;
                closeStarted.countDown();
            }

            try {
                port.unregisterCallbacks(handle);
                synchronized (gate) {
                    while (inFlight != 0) {
                        try {
                            gate.wait();
                        } catch (InterruptedException e) {
                            interrupted = true;
                        }
                    }
                }
                port.destroy(handle);
            } finally {
                synchronized (gate) {
                    state = State.CLOSED;
                    gate.notifyAll();
                }
                if (interrupted) Thread.currentThread().interrupt();
            }
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("latch timed out");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new AssertionError(e);
        }
    }

    static void mustReject(Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("closed resource accepted an operation");
        } catch (IllegalStateException expected) {
            // This is the specified rejection at the Java boundary.
        }
    }

    static void mustStillBeWaiting(Future<?> future) throws Exception {
        try {
            future.get(100, TimeUnit.MILLISECONDS);
            throw new AssertionError("closed before in-flight callback finished");
        } catch (TimeoutException expected) {
            // The close is intentionally waiting for its in-flight lease.
        }
    }

    static void testSequential() {
        FakePort port = new FakePort();
        NativeOwner owner = new NativeOwner(port);
        owner.use(() -> { });
        owner.onCallback(() -> { });
        owner.close();
        owner.close();
        owner.close();

        mustReject(() -> owner.use(() -> { }));
        owner.onCallback(() -> {
            throw new AssertionError("late callback must not run");
        });
        check(port.executions.get() == 1, "unexpected native execute");
        check(port.destroys.get() == 1, "resource freed more than once");
        check(port.unregisters.get() == 1, "unregistered more than once");
        check(owner.deliveredCallbacks() == 1, "lost early callback");
        check(owner.ignoredCallbacks() == 1, "late callback not ignored");
        System.out.println("sequential: PASS");
    }

    static void testRace() throws Exception {
        FakePort port = new FakePort();
        NativeOwner owner = new NativeOwner(port);
        CountDownLatch useStarted = new CountDownLatch(1);
        CountDownLatch allowUse = new CountDownLatch(1);
        CountDownLatch callbackStarted = new CountDownLatch(1);
        CountDownLatch allowCallback = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            Future<?> use = pool.submit(() -> owner.use(() -> {
                useStarted.countDown();
                await(allowUse);
            }));
            Future<?> callback = pool.submit(() -> owner.onCallback(() -> {
                callbackStarted.countDown();
                await(allowCallback);
            }));
            await(useStarted);
            await(callbackStarted);

            Future<?> firstClose = pool.submit(owner::close);
            await(owner.closeStarted);
            Future<?> repeatedClose = pool.submit(owner::close);

            mustReject(() -> owner.use(() -> { }));
            owner.onCallback(() -> {
                throw new AssertionError("callback during close delivered");
            });

            allowUse.countDown();
            use.get(2, TimeUnit.SECONDS);
            mustStillBeWaiting(firstClose);
            check(port.destroys.get() == 0,
                    "native destroy happened before callback completed");

            allowCallback.countDown();
            callback.get(2, TimeUnit.SECONDS);
            firstClose.get(2, TimeUnit.SECONDS);
            repeatedClose.get(2, TimeUnit.SECONDS);
            owner.close();

            owner.onCallback(() -> {
                throw new AssertionError("callback after close delivered");
            });

            check(port.executions.get() == 1, "lost native operation");
            check(port.destroys.get() == 1, "double free under race");
            check(port.unregisters.get() == 1, "double unregister");
            check(owner.deliveredCallbacks() == 1, "lost accepted callback");
            check(owner.ignoredCallbacks() == 2, "late callbacks not rejected");
            System.out.println("race: PASS");
        } finally {
            allowUse.countDown();
            allowCallback.countDown();
            pool.shutdownNow();
            check(pool.awaitTermination(2, TimeUnit.SECONDS),
                    "threads did not terminate");
        }
    }

    public static void main(String[] args) throws Exception {
        testSequential();
        testRace();
    }
}
```

**Compile and run:**

```bash
javac NativeLifecycleTest.java
java NativeLifecycleTest
```

**Expected stdout when tests pass:**

```text
sequential: PASS
race: PASS
```

If any assertion fails, the program throws `AssertionError` and is not counted as PASS. The 2-second deadline is only suitable for a lab running on a normal machine; in CI with slow virtualized environments, you can make the timeout configurable and record the timeout cause, instead of retrying arbitrarily. `mustStillBeWaiting` uses a short timeout to prove that close is still waiting in a scenario where the callback is blocked by a latch.

### Why Does the Example Prevent These Specific Races?

- `inFlight++` is performed **inside the same monitor** as the `state == OPEN` check. If an operation acquired a lease before close, it is allowed to run; close must wait for `inFlight == 0`.
- When close transitions `OPEN → CLOSING` inside the monitor, any subsequent operation/callback **is not granted a lease**, even if the native handle has not yet been destroyed.
- The Java monitor is not held during `port.execute` or while invoking the user listener. Doing so avoids the risk of close holding the lock while native is waiting on another callback thread; however, complex shutdown schemes still require separate deadlock and reentrancy analysis.
- Only the first thread transitioning from `OPEN` to `CLOSING` calls `unregisterCallbacks` and `destroy`; repeated close calls during `CLOSING` wait until `CLOSED`. Free/unregister calls are counted with atomics.
- The test creates **one in-flight use** and **one in-flight callback**, requires close to still be waiting when use finishes while the callback is not yet done, and then verifies freeing happens exactly once.
- Callbacks arriving during `CLOSING` and after `CLOSED` are dropped without calling the listener. The `FakePort` class checks that `execute` is never called after free.

**Intentional limitations of the lab:** `FakePort.unregisterCallbacks` does not spawn its own native threads and does not prove that native registration has stopped. The example assumes `unregisterCallbacks`/`destroy` succeed, and does not simulate native release failure, cancellation/reentrancy, or a callback that is currently in C but has not yet entered Java. When integrating real JNI, **native worker join/quiescence** must be added before calling `destroy` or `DeleteGlobalRef`; these conditions must be verified in integration tests and cannot be inferred from a PASS on the fake.

## 5. Real Callback Teardown Sequence in JNI

A JNI callback may carry a native context pointer, `JavaVM*`, a Java object held by a global reference (`jobject`), and a C/C++ worker thread. The appropriate teardown order must come from the specific native API. General pattern:

```text
Java close()
    |
    +-- atomically transition OPEN -> CLOSING
    +-- reject new Java operations and callbacks
    +-- native_unregister_callback(handle)
    +-- signal native workers to stop accepting new work
    +-- join/drain in-flight native workers and callbacks
    +-- delete JNI global references (using valid JNIEnv* on calling thread)
    +-- native_destroy(handle) exactly once
    +-- publish CLOSED / wake waiting close callers
```

This is a **conceptual ordering diagram**, not standalone runnable C code. A native API might need to destroy the context before the ref or vice versa, but it must guarantee **no one is still using the object before freeing it**.

### 5.1. JNI Rules That Must Be Upheld

- A JNI local reference typically lives only within the scope of the current native call. If a native worker wants to retain a Java callback to invoke later, it must create a `NewGlobalRef` (or documented reference mechanism), and delete it exactly once with `DeleteGlobalRef` **once all callback invocations that could use that ref have finished**.
- `JNIEnv*` is **thread-local**, and must not be stored and reused on another C thread. Workers not created by Java need to use `JavaVM*` and `AttachCurrentThread` (or the daemon variant when appropriate) to obtain their own `JNIEnv*`; detach when finished per contract. Do not detach while Java frames are still on the stack.
- After `DeleteGlobalRef`, native must not reuse the freed reference, even if the Java wrapper has already decided to "drop the callback".
- If C invokes a Java callback and Java throws an exception, JNI must check/handle the pending exception according to the contract. Do not arbitrarily make further JNI calls while an exception is pending, and do not let the native worker continue as if the callback succeeded.
- Pointer addresses, handles, and callback contexts passed via `long` must not be considered safe solely because of a Java `volatile closed`. If Java checks `!closed` and another thread frees right before JNI uses the handle, that is a classic check-then-use race.

**Common deadlock:** thread A calls `close()` and waits for worker B to finish; worker B calls a Java listener and waits for A to process it on the same event loop that A is blocking. You must stipulate that callback delivery can run on another thread, perform shutdown without blocking the event loop, or structure completion in two phases. **Do not call `close()` directly from a callback if close waits for that very callback to drain**, unless the implementation has a dedicated reentrancy protocol.

### 5.2. Particularly Dangerous Late Callback Cases

A callback may be enqueued **before** `unregister`, yet execute **after** `unregister` returns. Therefore, you must check whether the API explicitly states "unregister returns only after callbacks have quiesced" or merely "future dispatch is disabled". For the latter, another **join/flush/acknowledgement** is required and the callback context must still be kept alive until quiescence is reached.

A callback may exist **outside Java** before entering `onCallback`; Java `inFlight` only counts callbacks **that have already entered the method**. Freeing a global ref or function pointer as soon as Java `inFlight == 0` is wrong if native still has callbacks in flight.

The typical solution is reference counting or an epoch/generation managed **on the native side**, combined with stopping registration, stopping workers, waiting for callbacks holding a native lease to exit, and only then freeing. When a callback receives an event, it checks the context lifetime/generation **before dereferencing**. Never read the generation by dereferencing a freed context pointer: you need a control block that lives long enough or a separate thread-safe handle registry.

### 5.3. ABA: Reused Pointers

Suppose session A has address `0x1000`, A is closed and freed. The allocator reuses `0x1000` for session B. A late callback from A carrying `0x1000` arrives, finds B, and delivers data to the wrong session. Checking "pointer != 0" or comparing addresses cannot distinguish the two lifetimes.

A protocol can use a `(slotId, generation)` pair; each time a slot is reused, the generation is incremented, and a callback is only accepted when the generation matches and the session is still `OPEN`. The registry must be synchronized; check and acquire a lease before access, and disallow deleting the backing context while any lease is held. Test T08 actively forces slot reuse to verify that stale events are dropped.

## 6. FFM API: Tests Have Different Semantics Than JNI

With **JDK 22+**, FFM provides `Arena`/`MemorySegment` and checks lifetime when accessing segments through the Java API. The following standalone example requires JDK 22+ (does not run on JDK 17):

**File `ArenaLifetimeTest.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaLifetimeTest {
    public static void main(String[] args) {
        MemorySegment segment;
        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 7);
            System.out.println("value=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            segment.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("access after close succeeded");
        } catch (IllegalStateException expected) {
            System.out.println("access after close: rejected");
        }

        Arena shared = Arena.ofShared();
        shared.close();
        try {
            shared.close();
            throw new AssertionError("double close succeeded");
        } catch (IllegalStateException expected) {
            System.out.println("double arena close: rejected");
        }
    }
}
```

**Run with JDK 22+:**

```bash
javac ArenaLifetimeTest.java
java ArenaLifetimeTest
```

**Stdout:**

```text
value=7
access after close: rejected
double arena close: rejected
```

FFM ensures that access via `MemorySegment` is checked for temporal safety, but you still need to watch out for:

- `Arena.ofConfined()` only allows the owner thread to access/close; calling from another thread throws `WrongThreadException`. `Arena.ofShared()` allows multiple threads to access, but close can throw `IllegalStateException` if a related access/downcall is in progress; tests must cover concurrent behavior.
- When closing an arena, segments allocated by that arena are no longer valid. **Do not** change the test condition to "FFM can read an arbitrary pointer after close" just because a machine address is a `long`.
- `Linker.upcallStub(...)` creates a function pointer bound to the arena's lifetime. If C retains the function pointer and calls it after the arena closes, the risk of crashing the JVM **still exists**; FFM does not automatically unregister callbacks in the native library.
- Certain operations such as reinterpreting from an arbitrary address/unsafe native pointer can bypass the segment's built-in checks; you must respect the owner and lifetime of the underlying memory region.
- If an FFM downcall/upcall is a restricted operation on the JDK in use, configure the module's native access according to the target JDK's documentation; this is an **access permission** issue, independent of lifetime bugs.

Do not try to use `Arena.ofGlobal()` to "solve" late callbacks; the unbounded lifetime of a global arena makes resource reclamation difficult and hides leaks. Choose the right arena and unregister/quiescence protocol.

## 7. Systematic Race Testing, Avoiding False PASS

**Use latches/barriers to create intentional ordering.** Three points worth verifying are: (a) an operation has acquired a lease before close, (b) close has transitioned to `CLOSING` while the operation is still busy, (c) a new callback arrives after the transition. Writing small tests with these conditions is much more stable than `Thread.sleep(...)`.

**Use finite deadlines.** Every latch, `Future.get`, or shutdown has a timeout; if exceeded, the test reports a timeout with a thread dump and latest state instead of hanging CI. A single timeout could be due to high machine load; repeat in a controlled environment and collect evidence before concluding there is a deadlock.

**Repeat across many interleavings.** After deterministic tests, run a stress suite multiple times and vary seeds/scheduling, including concurrent callbacks and closes, closing from multiple threads, canceling during initialization, and executor shutdown. If possible, use a suitable model checker/concurrency-testing framework to find rare orderings; do not infer absolute safety from 1,000 PASS runs.

**Native evidence:** add per-handle instrumentation in C/C++ with atomic counters and states; log `allocate(handle, generation)`, `register`, `unregister`, `callback_enter`, `callback_exit`, `free`. A test must not finish when `freeCount==1` while native threads are still running after the test; wait for quiescence before final assertions.

### Running Real Tests with JVM and Native Instrumentation

When integrating native JNI, some ways to increase detection capability:

```bash
# Test class is just an example name in a real application:
java -Xcheck:jni -cp app-and-tests.jar com.acme.NativeIntegrationTests
```

`-Xcheck:jni` checks many JNI usage errors (invalid references, pending exceptions, wrong thread...), but **is not a general-purpose memory sanitizer** and does not prove the absence of UAF.

For C/C++ native libraries, build specifically for testing with AddressSanitizer/UndefinedBehaviorSanitizer when the toolchain and JVM runtime are compatible:

```bash
# Illustrates compiler/linker flags used for the native library test build itself:
gcc -g -O1 -fno-omit-frame-pointer \
    -fsanitize=address,undefined -fPIC -shared \
    -o libbridge-test.so bridge.c
```

The snippet above is a **sample of build flags**, and cannot be run alone without the project's `bridge.c` along with its JNI include/link dependencies. The sanitizer runtime must be loaded properly according to the toolchain/OS; if linking/preloading errors occur, fix the harness before concluding it is a bug. Run in a **separate subprocess**, checking exit code, stderr/sanitizer reports, JVM fatal logs (`hs_err_pid...`), and OS core/dump if available. A bad native race can crash the entire JVM, so do not bundle all crash-prone tests into a single main test runner process.

### Separating Tests by Level

| Test Level | Used to Prove | Limitations |
| --- | --- | --- |
| Java fake/unit (Section 4 example) | API contract, state ordering, counters, late delivery at the Java boundary | Cannot see C global refs, live native threads, or real memory |
| JNI/FFM integration with native test library | Native handle, callback registration, teardown, generation, ABI, and thread attach | Requires a real harness and symbols from the same build |
| Stress + sanitizer + subprocess | Many rare interleavings, real UAF/double free, process crashes | Does not prove zero bugs remain; overhead alters timing |
| End-to-end on release artifacts | Closing along the real application path and packaged libraries | Difficult to force scheduling; must be supplemented by lower-level tests |

## 8. Common Bugs and Fixes

| Bug | Consequence | Fix |
| --- | --- | --- |
| `if (!closed) nativeUse(handle)` then another thread frees | Check-then-use race → UAF | Check and acquire lease in the same synchronized block; close waits for leases |
| Only using `AtomicBoolean.compareAndSet(false,true)` to close | Prevents double free but does not stop an already-started native operation | Add lifecycle gate/in-flight count and native quiescence |
| `close()` sets `handle=0` after freeing | Another thread that already copied the old handle still uses it | Protect the entire usage lifecycle; do not just set to 0 |
| Immediately calling `DeleteGlobalRef` right after `unregister` | Queued callback/running worker still uses `jobject` | Confirm unregister blocks new dispatch **and** drains old callbacks before deleting ref |
| Storing `JNIEnv*` in a global variable used from another thread | JNI thread-affinity violation, undefined behavior/crash | Store `JavaVM*`, attach the right thread, obtain that thread's `JNIEnv*` |
| Native worker calls back into Java right during UI/executor shutdown | Listener is called after close or event queue rejects the task | Transition to `CLOSING` first, stop emitting events, handle task cancellation/waiting |
| Callback calls `close()` and close waits for that same callback to finish | Self-deadlock | Schedule close onto a controller thread or support two-phase close |
| Second call to FFM `Arena.close()` | `IllegalStateException` | Test the exact FFM contract or close through an idempotent wrapper |
| Closing shared arena while a downcall is using a segment | Runtime may reject close; uncontrolled retries are error-prone | Synchronize quiescence; test access/close races per JDK version |
| Reusing handle address for a new session | Old callback mistakenly targets new session (ABA) | Generation/epoch + lease-granting registry, do not dereference freed context |
| Java callback throws an exception across the upcall boundary | Can abruptly terminate the JVM with FFM upcalls | Target must catch, report, and return a valid native value |
| Test passes because the callback never ran | False positive | Count accepted/ignored/finished, force triggering and synchronize with latches |

### Failure Cases Must Not Be Masked

If the native destroy function can fail, the wrapper must clearly represent the state. For example, if the native destructor returns `BUSY` because callbacks remain: do not set `CLOSED` and erase handle info; preserve ownership so there is a way to clean up safely and report the error, or fail fast with a reliable message. If the destructor ran partially and then reported an error, **do not automatically retry free** unless the contract confirms idempotence. This is a case that requires dedicated fault-injection testing (T11), independent of the fake lab where destroy always succeeds.

## 9. Acceptance Criteria for Distributing a Java/Native Library

Before release, define a verifiable set of criteria:

1. **API documentation:** specify who owns the handle, whether close is idempotent, post-close behavior, callback thread, reentrancy, and close failures.
2. **Lifecycle assertions:** for every handle, `allocations == frees == 1` after successful teardown; all in-flight operations/callbacks have defined completion or cancellation; no worker retains a freed pointer.
3. **Race suite:** T01–T12 tailored to the real API; run `close/use`, `close/callback`, multiple closers, and handle generation reuse races; every test has a timeout.
4. **JNI/FFM correctness:** validate `JNIEnv*` thread affinity, global refs, upstream unregister + drain, FFM arena/thread scope, upcall-stub lifetime; do not misrepresent exception contracts.
5. **Build matrix:** test across the JDKs and OS/architectures the library claims to support; a JDK release does not automatically guarantee identical native ABI, libc, or sanitizers.
6. **Packaging:** test from the real artifacts (JAR, `.so`/`.dll`/`.dylib`, launcher, JVM flags, paths), not just from the build directory; ensure symbols and hashes/debug info are traceable on crash.
7. **Diagnosability:** when a test fails or a subprocess crashes, preserve stdout/stderr, JVM fatal logs, native symbol/build ID, and core/minidumps where collectible; record test seed, timestamp, PID, and binary version.
8. **Release gate:** deterministic tests must always PASS, stress/sanitizer runs detect no UAF/double free within test scope, no leaks/live workers remain after shutdown, and any unverifiable limitations are clearly documented.

Do not equate "never crashed in tests" with proof of absolute safety. JNI/native code can manifest bugs after millions of interleavings. The value of the suite is forcing critical invariants to be verified and producing sufficient evidence when a crash occurs.

## 10. Self-Assessment Questions

**Scenario A.** Two threads both read `closed=false`; one thread calls `nativeFree` and the other calls `nativeRead`. Is merely changing `closed` to `volatile` enough? **No.** Volatile helps with visibility, but does not turn the two operations "check + use pointer" into a lease protected against close.

**Scenario B.** `close()` is called three times; free count is 1. Can we conclude the wrapper is thread-safe? **Not yet.** We must prove no in-flight operation/callback uses the pointer after free and that multiple closers do not deadlock.

**Scenario C.** `unregister_callback` returns, but a queued callback still holds `jobject`. Can `DeleteGlobalRef` be called yet? **No**, unless the native API guarantees that callbacks needing the ref have quiesced; we must wait for the queue/callbacks to drain first.

**Scenario D.** Closing `Arena.ofShared()` a second time throws `IllegalStateException`. Is this a Java regression? **No.** That is the official contract of `Arena.close()`; only a custom wrapper can choose idempotent close.

**Scenario E.** The fake test in Section 4 PASSES, but JNI integration reports heap-use-after-free in a callback. Is this a contradiction? **No.** The fake does not verify global-ref lifetime, native thread joins, or callbacks that are in C before entering Java.

**Scenario F.** An event for session A receives the exact pointer address, but is processed in session B. Why? **ABA**: the allocator reused the address; a generation/epoch and synchronized registry lookup are needed.

## 11. Authoritative References

- [Oracle — `Arena` (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifecycle, non-idempotent close, confined/shared, `WrongThreadException`, and concurrent access.
- [Oracle — `MemorySegment` / FFM package (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/package-summary.html): temporal safety and segment scope.
- [Oracle — `Linker` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): upcall stub lifetime, native calls, and failure when a Java exception crosses an FFM upcall boundary.
- [JNI Specification — Global/Local References](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, pending exceptions.
- [JNI Specification — Invocation API](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html): `AttachCurrentThread`, `DetachCurrentThread`, per-thread `JNIEnv*`.
- [OpenJDK JEP 454](https://openjdk.org/jeps/454): FFM API becomes final in JDK 22; goals and safety boundaries.

What matters when distributing a Java/native library is turning resource lifecycle into a **testable contract**: accept operations only with a valid lease; transition to closing once; stop and wait for accepted native callbacks/operations; destroy the resource exactly once; reject all late uses and late callbacks. It is these invariants—not a single boolean flag—that prevent double free, use-after-free, and hard-to-reproduce shutdown bugs.
