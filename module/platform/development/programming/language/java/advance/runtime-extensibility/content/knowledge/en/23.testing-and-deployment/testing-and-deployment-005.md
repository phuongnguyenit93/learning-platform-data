# Testing Concurrent Invocation, Initialization Failure, Shutdown, and Multi-Generation Replacement of Java Plugins

## 1. The Problem: Sequential Happy-Path Tests Are Not Enough

A Java system with runtime extensibility can discover plugins via `ServiceLoader`, load plugins from dedicated class loaders, or build dynamic `ModuleLayer`s. Those mechanisms **find and load code**, yet they do not prove that the **plugin manager** is safe under concurrent requests, mid-startup failures, concurrent shutdown, or hot replacement across implementation generations.

Plugin testing must focus on **behavior at time boundaries**, not merely `assertEquals` on a business method:

1. **Concurrent invocation:** Two or more requests may enter a plugin simultaneously. Does the manager accurately count active (*in-flight*) requests and protect shared state?
2. **Initialization failure:** A plugin may open resources and then throw. Does the host accidentally publish an unready instance into the registry or leak resources?
3. **Shutdown:** While requests are executing, does shutdown block new requests, wait for existing requests, and close resources at the right moment?
4. **Multi-generation replacement:** While an older plugin version is still handling requests, can the host activate a new version, route new requests to it, and reject late callbacks from the old version?

**Desired outcome:** tests must be reproducible, actively control thread scheduling, include timeouts to detect deadlocks, and assert state and ownership—never using `Thread.sleep(...)` to "hope" a race occurs.

### 1.1. Responsibility Boundaries

```text
   SPI / ModuleFinder / class loader
             │ discover implementation
             ▼
       Plugin Manager
     verify → initialize → READY
             │
             ▼
       Router / Registry
       ┌─────────────────┐
       │ Generation G1   │ ◄── old request, lease granted
       │ QUIESCING       │
       └─────────────────┘
             │ atomic traffic switch
             ▼
       ┌─────────────────┐
       │ Generation G2   │ ◄── new request
       │ ACTIVE          │
       └─────────────────┘
             │
             ▼
  Wait for G1 in-flight = 0 → stop G1 → close resources
```

The host owns *routing*, lifecycle, timeouts, version compatibility, and cleanup. The plugin owns thread safety of its implementation or must publish a sequential-execution policy. **Thread-safe routing does not make a non-thread-safe plugin implementation thread-safe.**

## 2. Test Model: State, Generation, Lease, and Invariants

A model sufficient to catch critical bugs:

| Component | Responsibility | Key Assertion |
| --- | --- | --- |
| `Plugin` | `initialize`, `handle`, `close` | Never handles before init; safe cleanup after failed init |
| `Generation` | Instance/plugin version + state + in-flight count | Grants leases only in ACTIVE; shutdown waits for exact request count |
| `Router` | Reference to the current generation | Swap and lease acquisition share synchronization |
| `Lease` | Temporary permission for one request to use a generation | Acquired once; released in `finally` |
| `Failure record` | Root cause of startup/stop/callback failure | Original error is not lost even if cleanup succeeds |
| `Generation ID` | Distinguishes instantiation cycles | Old callbacks cannot mutate new generation state |

States can be `NEW`, `INITIALIZING`, `ACTIVE`, `QUIESCING`, `STOPPING`, `STOPPED`, and `FAILED`. This is an application-designed enum, **not built-in states of `ServiceLoader`**.

### 2.1. Invariants That Must Never Break

- **Admission:** Only `ACTIVE` accepts new requests and increments `inFlight`.
- **Atomicity:** Checking `ACTIVE` and incrementing `inFlight` must occur inside the **same critical section**, avoiding races with stop.
- **Release:** Once a lease is granted, every exit path (success, exception, interrupt) decrements `inFlight` exactly once.
- **No premature close:** Never invoke `close` while `inFlight > 0` when the contract requires graceful shutdown and requests still hold resources.
- **Quiesce:** Once the gate closes, **no new leases are granted for the old generation**, while already-granted leases are allowed to finish.
- **No early publish:** A candidate becomes the current generation **only after** initialization and readiness succeed.
- **Atomic cutover:** There is no window where two router paths both accept new requests after the switch is published.
- **Fencing:** Callbacks originating from an old generation cannot update the registry or state of a newer generation.
- **Cleanup:** Partial initialization must still be cleaned up; repeated stop calls must not double-close.
- **Failure history:** A failed startup whose cleanup transitions to `STOPPED` must not erase `lastFailure`.

### 2.2. A Lease Matters More Than a `volatile` Field

Counterexample:

```java
// Dangerous PSEUDOCODE: non-atomic check and increment.
if (state == State.ACTIVE) {
    inFlight++;
    plugin.handle(request);
    inFlight--;
}
```

Thread A may read `ACTIVE`, thread B transitions to `STOPPING` and closes resources, and only then does A increment `inFlight` and call the plugin. A `volatile State` only guarantees visibility, not atomicity across *check → increment → use*.

Correct design pattern:

```text
Route request:
  synchronized(generation.lock):
    require ACTIVE
    inFlight += 1
  try:
    plugin.handle(request)
  finally:
    synchronized(generation.lock):
      inFlight -= 1
      signal waiters

Stop generation:
  synchronized(generation.lock):
    state = QUIESCING
    reject new leases
    wait until inFlight == 0
  plugin.close()
```

This is **pseudocode**. In applications with a router, picking the current generation and acquiring its lease must be coordinated under **the same lock/CAS mechanism as the swap**. If the router reads the old generation and pauses before acquiring a lease, a swap can slip in between.

## 3. Testing Concurrent Invocation

### 3.1. What Must Be Proven?

Do not merely fire 100 requests and observe matching outputs. A solid concurrent invocation test should prove:

1. At least **two handlers are inside the execution region simultaneously** before either is allowed to finish.
2. The manager's `inFlight` equals the number of granted leases; no lost increments or decrements.
3. Requests return accurate results without sharing unprotected mutable data.
4. Once handlers finish and release, `inFlight == 0`.
5. Exceptions also release leases so shutdown never hangs forever.
6. When a plugin policy permits only sequential execution, the router/executor genuinely serializes calls instead of hoping the plugin does not race.

### 3.2. Use `CountDownLatch` Instead of `Thread.sleep`

`CountDownLatch` creates two deterministic synchronization points:

```text
Thread A: acquire → handle → entered.countDown ─┐
                                                ├─ await(release)
Thread B: acquire → handle → entered.countDown ─┘

Test: await(entered == 0)
      assert inFlight == 2
      assert observedMaxConcurrent == 2
      release.countDown()
      assert outputs and inFlight == 0
```

The test knows for certain both requests have entered the handler before opening the gate. `Thread.sleep(100)` proves nothing: a slow CI runner, GC pause, or different scheduler can make tests both false-positive and flaky.

Use `CountDownLatch.await(timeout, unit)` in tests to **fail on hangs**, not to control ordering via wall-clock time. A timeout is only a safety guard; it never proves an algorithm is right without assertions on synchronized state.

### 3.3. Cover Exception Paths Too

Release pattern:

```java
// Illustration: acquire()/release() belong to a properly synchronized Generation.
generation.acquire();
try {
    return plugin.handle(input);
} finally {
    generation.release();
}
```

If `plugin.handle` throws `IllegalArgumentException`, `IOException`, or `InterruptedException`, `finally` still runs. Tests should inject controlled failures into `handle` and verify `inFlight == 0` and shutdown does not hang.

If a thread is interrupted while waiting, do not silently clear the interrupt flag or auto-retry in a way that processes the request twice. Typically propagate `InterruptedException` at test/host boundaries or restore the interrupt flag when signatures do not throw it.

## 4. Testing Initialization Failures

### 4.1. Different Failure Phases

| Failure Point | Trace to Verify | Host Behavior |
| --- | --- | --- |
| Provider discovery | Missing provider or broken SPI descriptor | Distinguish absent provider from `ServiceConfigurationError` |
| Verify | Missing dependency/version, duplicate ID, policy denial | Do not initialize/publish |
| Constructor | Constructor/initializer throws | No usable instance; clean up auxiliary resources if allocated |
| Initialize before opening resources | Invalid config/secret | `FAILED`, never ACTIVE |
| Initialize **after opening resources** | File, socket, or worker thread created before later step fails | Clean up opened parts, zero leaks |
| Start/readiness | Unready, timeout, dependency failure | Candidate is never published |
| During replacement | New generation fails initialization | **Keep old generation** serving if cutover has not occurred |

A test asserting only that an exception is thrown is **insufficient**. Simultaneously check: candidate is not published, no requests reach the candidate, partial resources are freed, root cause is preserved, and the old generation (if any) keeps serving.

### 4.2. Separate Initialize from Publish

Flow:

```text
construct candidate
        │
        ▼
verify dependencies/config
        │
        ▼
initialize candidate
        ├─ FAILED → close partially initialized resources → report
        ▼
readiness check
        ├─ FAILED → cleanup candidate → keep old generation
        ▼
atomic swap in router
        │
        ▼
old generation QUIESCING → drain → STOPPED
```

If the host publishes a candidate before `initialize` finishes, requests can observe an unconfigured object or half-opened resources.

In test code, intentionally set `resourceOpened=true` **before throwing**, then assert after `close` that the flag returns to `false`. This catches missing cleanup bugs that tests throwing at the very top of `initialize` miss.

### 4.3. Avoid Auto-Retrying a Broken Instance

Do not blindly re-invoke `initialize` on the same object after a failure, because instance fields, threads, connections, and subscriptions may be left in an undefined state. A safer strategy is usually:

```text
FAILED instance → best-effort cleanup → STOPPED
→ retry with a NEW generation/instance after backoff
```

If the host explicitly supports restarting the same instance, that must be a documented capability tested across every failure stage—not just a retry loop wrapped around `start()`.

## 5. Testing Shutdown: Quiescing, Draining, and Closing

### 5.1. A Proper Shutdown Has Three Milestones

1. **Close admission:** No further new requests acquire a lease on the stopping generation.
2. **Drain in-flight:** Wait for already-admitted requests to complete (or hit deadline/cancellation policy).
3. **Cleanup:** Close plugin resources exactly once and record `STOPPED`.

`QUIESCING` is the window where the gate is closed while old requests still run. `STOPPING` is the phase where the manager prepares/executes cleanup; exact state names depend on your system.

### 5.2. Use Latches to Force Shutdown to Race with Handlers

```text
Request thread                  Shutdown thread
--------------                  ---------------
acquire generation lease
handle() enters
block on release latch
                                close gate
                                assert new request rejected
                                wait for inFlight = 0
assert plugin not yet closed
release latch
handle returns
release lease
                                plugin.close() once
                                state = STOPPED
```

Mandatory assertions:

- The running handler finishes on the old generation without swapping instances mid-flight.
- After the gate closes, a **new** request is rejected or routed to another generation, never granted another old lease.
- While one request remains blocked, `closeCount == 0` and shutdown has not completed.
- Only after the lease is released do we see `closeCount == 1` and state `STOPPED`.
- Calling stop a second time does not close twice.
- If `close` fails, the host records the cleanup failure instead of reporting false success.

### 5.3. Timeouts and Cancellation

Demo models often wait indefinitely to drain, while tests use timeouts to avoid hanging forever. **Production must have deadlines.** However, `Future.cancel(true)`/`Thread.interrupt()` does not guarantee a handler blocked on I/O stops immediately, nor does it guarantee resources can be closed safely while a thread still uses them.

When deadlines expire, the host needs a clear policy: mark timeout, block admission, log live requests, cap resources, and potentially **isolate in a separate process** when forced termination is required. Never simply call `URLClassLoader.close()` and assume every plugin thread died; Java class unloading requires zero live references to the loader.

### 5.4. Dependency Graph During Shutdown

If plugin Report depends on Storage:

```text
Start: Storage → Report
Stop:  Report  → Storage
```

Tests must verify Report is quiesced/flushed/closed **before** Storage closes, even under concurrent requests. `ServiceLoader` does not manage this dependency ordering automatically.

## 6. Testing Multi-Generation Replacement

### 6.1. What Is a Generation?

A *generation* is **one plugin instance with a unique identity for a single activation**, such as `pluginId=pdf, generation=7` and `generation=8`. Generation differs from a version string `1.2.3`: two restarts of the same version are still **two distinct generations**.

Tie state to `pluginId + generationId + instanceId` or an equivalent token. Never store state keyed solely by plugin name if two instances of that name can overlap during traffic cutover.

### 6.2. Zero-Downtime Replacement Flow

```text
T0:  current = G1 (ACTIVE)
     request A acquires G1 lease, currently running

T1:  create G2, verify/init/readiness
     G1 continues serving new requests

T2:  swap atomically:
     G1 close gate → QUIESCING
     current = G2 (ACTIVE)

T3:  request B is routed to G2
     request A still completes on G1

T4:  inFlight(G1) = 0
     stop/close G1 → STOPPED
     current remains G2

T5:  create G3, swap similarly:
     G2 QUIESCING, current=G3
     late callbacks from G1/G2 are ignored
```

At T2, **closing G1's gate and assigning `current=G2` must be coordinated**. Writing only:

```java
// Racy PSEUDOCODE if route() reads reference before swap.
current = newGeneration;
oldGeneration.stopAccepting();
```

allows a request that already read reference G1 before acquiring a lease to still enter G1 after the swap occurs. The runnable example solves this by having Router and Generation use consistent locking so **swap and lease acquisition are linearly ordered**.

### 6.3. Testing Stale Callbacks

An asynchronous task may complete after a newer generation has been published. If the callback simply executes `registry.put(pluginId, result)`, it can overwrite the newer version's state.

**Fencing token:**

```text
callback(sourceGeneration, result):
  synchronized(router.lock):
    if sourceGeneration != current:
        reject stale update
    else:
        publish result
```

In a distributed system, you may need a monotonic fencing token verified by the backend rather than just in-memory object identity. Tests should create three generations G1, G2, G3 and intentionally send G1/G2 callbacks **after** G3 becomes current; they must be rejected, while G3's callback is accepted.

### 6.4. Candidate Fails Before Swap

If G2 fails to initialize, the router must retain G1:

```text
G1 ACTIVE ────────────────► G1 ACTIVE
                  G2 INITIALIZING
                         │ failure
                         ▼
                      G2 FAILED
                         │ cleanup
                         ▼
                      G2 STOPPED
```

This test catches implementations that "assign `current = candidate` first, then call `candidate.start()`", which leaves the system with no working provider after a failed deployment.

## 7. Testing Tools in Java 17+

| Tool | Purpose | What to Watch Out For |
| --- | --- | --- |
| `CountDownLatch` | Block/release test checkpoints | One-shot; cannot be reset |
| `CyclicBarrier` | Synchronize multiple threads at a checkpoint | Handle broken barrier/timeout |
| `Phaser` | Multi-phase synchronization | More complex; fits multi-step tests |
| `ExecutorService` | Run requests/shutdown on worker threads | Shut down executor in `finally` |
| `Future.get(timeout, unit)` | Wait for results, detect hangs | Timeout is only a guard, not ordering proof |
| `CompletableFuture` | Test async startup/callbacks | Unwrap errors, control executor and cancellation |
| `AtomicInteger` | Count handle/close calls, measure max concurrency | Does not replace multi-variable atomic protocols |
| `AtomicReference` | Hold current generation or snapshot | A pointer CAS alone does not close old generation's gate |
| `synchronized`/`ReentrantLock` | Group check + acquire or swap into critical section | Do not hold locks across potentially blocking plugin code |
| JUnit 5 `assertTimeoutPreemptively` | Framework-level test timeout | Runs in another thread; interrupt/cancel has limits; avoid leaking threads after test |
| Awaitility (external) | Wait for eventual conditions with deadline | Do not poll when deterministic latches can coordinate |

To keep the example runnable with only JDK 17+, the code below uses **custom assert helpers** and `CountDownLatch`. When integrating into CI, each case can become a JUnit 5 `@Test`. JUnit is not required to run the sample program.

## 8. Complete Java 17+ Example: Multi-Thread and Three-Generation Tests

### 8.1. Goals and Structure

For ease of reproduction, the example is **a single Java file** with static nested types. It simulates a Router, each `Generation` with its own gate and in-flight counter, and a `FakePlugin` with explicit latches so tests control scheduling.

Five test cases:

1. Two calls genuinely overlap concurrently and release accurately.
2. Initialize fails **after** allocating a resource; not published and properly cleaned up.
3. Stop while a call is running; does not close prematurely or accept new calls.
4. Replace G1 → G2 → G3, leased request on G1 completes, stale callbacks are rejected.
5. Candidate G2 fails initialization; G1 keeps serving until a valid replacement arrives.

File:

```text
LifecycleTests.java
```

### 8.2. Complete `LifecycleTests.java` Source

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class LifecycleTests {
    private static final long TIMEOUT_SECONDS = 10;

    interface Plugin {
        void initialize() throws Exception;
        String handle(String request) throws Exception;
        void close() throws Exception;
    }

    enum State {
        NEW, INITIALIZING, ACTIVE, QUIESCING,
        STOPPING, STOPPED, FAILED
    }

    static final class FakePlugin implements Plugin {
        final String version;
        final boolean failInitialize;
        final CountDownLatch entered;
        final CountDownLatch release;
        final AtomicInteger concurrent = new AtomicInteger();
        final AtomicInteger maximum = new AtomicInteger();
        final AtomicInteger closeCount = new AtomicInteger();
        volatile boolean resourceOpen;

        FakePlugin(String version, boolean failInitialize,
                   int expectedCalls, boolean blockHandlers) {
            this.version = version;
            this.failInitialize = failInitialize;
            this.entered = new CountDownLatch(expectedCalls);
            this.release = new CountDownLatch(blockHandlers ? 1 : 0);
        }

        @Override
        public void initialize() {
            // Intentionally open resource BEFORE simulating failure.
            resourceOpen = true;
            if (failInitialize) {
                throw new IllegalStateException("init denied");
            }
        }

        @Override
        public String handle(String request) throws Exception {
            if (!resourceOpen) {
                throw new IllegalStateException("not initialized");
            }
            int now = concurrent.incrementAndGet();
            maximum.accumulateAndGet(now, Math::max);
            try {
                entered.countDown();
                if (!release.await(
                        TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "handler gate timed out");
                }
                return version + ":" + request;
            } finally {
                concurrent.decrementAndGet();
            }
        }

        @Override
        public void close() {
            if (concurrent.get() != 0) {
                throw new IllegalStateException(
                    "closed while handler is running");
            }
            closeCount.incrementAndGet();
            resourceOpen = false;
        }
    }

    static final class Generation {
        final long id;
        final Plugin plugin;
        final Object monitor = new Object();
        final CountDownLatch gateClosed = new CountDownLatch(1);
        private State state = State.NEW;
        private int inFlight;
        private boolean shutdownStarted;
        private Exception lastFailure;

        Generation(long id, Plugin plugin) {
            this.id = id;
            this.plugin = plugin;
        }

        void start() throws Exception {
            synchronized (monitor) {
                require(state == State.NEW,
                        "start must begin from NEW");
                state = State.INITIALIZING;
            }
            try {
                plugin.initialize();
                synchronized (monitor) {
                    state = State.ACTIVE;
                }
            } catch (Exception error) {
                synchronized (monitor) {
                    lastFailure = error;
                    state = State.FAILED;
                }
                throw error;
            }
        }

        void acquire() {
            synchronized (monitor) {
                require(state == State.ACTIVE,
                        "generation not ACTIVE");
                inFlight++;
            }
        }

        String runLeased(String input) throws Exception {
            return plugin.handle(input);
        }

        void releaseLease() {
            synchronized (monitor) {
                require(inFlight > 0, "unbalanced release");
                inFlight--;
                monitor.notifyAll();
            }
        }

        void quiesce() {
            synchronized (monitor) {
                require(state == State.ACTIVE
                        || state == State.QUIESCING,
                        "cannot quiesce current state");
                if (state == State.ACTIVE) {
                    state = State.QUIESCING;
                    gateClosed.countDown();
                }
            }
        }

        void shutdown() throws Exception {
            synchronized (monitor) {
                if (shutdownStarted) {
                    // Concurrent stop: wait for first cleanup to finish.
                    while (state == State.STOPPING) {
                        monitor.wait();
                    }
                    return;
                }
                require(state == State.NEW
                        || state == State.ACTIVE
                        || state == State.QUIESCING
                        || state == State.FAILED,
                        "invalid shutdown state");
                shutdownStarted = true;
                state = State.STOPPING;
                gateClosed.countDown();

                // wait() releases monitor so in-flight requests can finish lease.
                while (inFlight != 0) {
                    monitor.wait();
                }
            }

            Exception closeError = null;
            try {
                plugin.close();
            } catch (Exception error) {
                closeError = error;
            }

            synchronized (monitor) {
                if (closeError == null) {
                    state = State.STOPPED;
                } else {
                    state = State.FAILED;
                    lastFailure = closeError;
                }
                monitor.notifyAll();
            }
            if (closeError != null) {
                throw closeError;
            }
        }

        State state() {
            synchronized (monitor) {
                return state;
            }
        }

        int inFlight() {
            synchronized (monitor) {
                return inFlight;
            }
        }

        Exception lastFailure() {
            synchronized (monitor) {
                return lastFailure;
            }
        }
    }

    static final class Router {
        private final Object lock = new Object();
        private Generation current;
        private String publishedMarker;

        // Initialize candidate before replacing current.
        Generation swap(Generation candidate) throws Exception {
            candidate.start();
            synchronized (lock) {
                Generation old = current;
                if (old != null) {
                    old.quiesce();
                }
                current = candidate;
                return old;
            }
        }

        String route(String request) throws Exception {
            Generation selected;
            synchronized (lock) {
                selected = current;
                require(selected != null,
                        "no current generation");
                // Select current and acquire as one transaction.
                selected.acquire();
            }
            try {
                return selected.runLeased(request);
            } finally {
                selected.releaseLease();
            }
        }

        void stopCurrent() throws Exception {
            Generation old;
            synchronized (lock) {
                old = current;
                if (old != null) {
                    old.quiesce();
                    current = null;
                }
            }
            if (old != null) {
                old.shutdown();
            }
        }

        boolean publishIfCurrent(Generation source, String value) {
            synchronized (lock) {
                if (current != source
                        || source.state() != State.ACTIVE) {
                    return false;
                }
                publishedMarker = value;
                return true;
            }
        }

        String marker() {
            synchronized (lock) {
                return publishedMarker;
            }
        }
    }

    static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    static void await(CountDownLatch latch, String stage)
            throws InterruptedException {
        require(latch.await(TIMEOUT_SECONDS, TimeUnit.SECONDS),
                "timeout waiting for " + stage);
    }

    static String result(Future<String> future) throws Exception {
        return future.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    static void testConcurrentCalls() throws Exception {
        Router router = new Router();
        FakePlugin fake = new FakePlugin("v1", false, 2, true);
        Generation g1 = new Generation(1, fake);
        require(router.swap(g1) == null, "first swap");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(() -> router.route("A"));
            Future<String> b = pool.submit(() -> router.route("B"));

            await(fake.entered, "two calls enter handler");
            require(g1.inFlight() == 2, "two active leases");
            require(fake.maximum.get() == 2,
                    "handlers did not overlap");

            fake.release.countDown();
            require(result(a).equals("v1:A"), "request A");
            require(result(b).equals("v1:B"), "request B");
            require(g1.inFlight() == 0, "leases drained");

            router.stopCurrent();
            require(g1.state() == State.STOPPED, "stopped");
            require(fake.closeCount.get() == 1, "closed once");
            System.out.println("PASS concurrent calls");
        } finally {
            fake.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testFailedInitialization() throws Exception {
        Router router = new Router();
        FakePlugin bad = new FakePlugin("bad", true, 0, false);
        Generation candidate = new Generation(1, bad);
        boolean failed = false;
        try {
            router.swap(candidate);
        } catch (IllegalStateException expected) {
            failed = expected.getMessage().equals("init denied");
        }
        require(failed, "initialize should fail");
        require(candidate.state() == State.FAILED, "failed state");
        require(candidate.lastFailure() != null, "failure recorded");
        require(bad.resourceOpen, "partial resource was opened");

        boolean rejected = false;
        try {
            router.route("must-not-run");
        } catch (IllegalStateException expected) {
            rejected = true;
        }
        require(rejected, "failed candidate must not be published");
        candidate.shutdown();
        require(candidate.state() == State.STOPPED, "cleanup done");
        require(!bad.resourceOpen, "partial resource closed");
        require(bad.closeCount.get() == 1, "one cleanup");
        require(candidate.lastFailure() != null,
                "failure history retained");
        System.out.println("PASS initialization rollback");
    }

    static void testGracefulStop() throws Exception {
        Router router = new Router();
        FakePlugin fake = new FakePlugin("stop", false, 1, true);
        Generation g1 = new Generation(1, fake);
        router.swap(g1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> running =
                pool.submit(() -> router.route("live"));
            await(fake.entered, "request entered");

            Future<?> stopping = pool.submit(() -> {
                router.stopCurrent();
                return null;
            });
            await(g1.gateClosed, "admission gate closed");
            require(g1.inFlight() == 1, "one in-flight request");
            require(fake.closeCount.get() == 0,
                    "cannot close while running");

            boolean rejected = false;
            try {
                router.route("late");
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            require(rejected, "new request after stop rejected");

            fake.release.countDown();
            require(result(running).equals("stop:live"),
                    "old request completes");
            stopping.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            require(g1.state() == State.STOPPED, "shutdown completed");
            require(fake.closeCount.get() == 1, "closed once");
            g1.shutdown();
            require(fake.closeCount.get() == 1,
                    "second shutdown did not close twice");
            System.out.println("PASS graceful stop");
        } finally {
            fake.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testMultipleGenerations() throws Exception {
        Router router = new Router();
        FakePlugin p1 = new FakePlugin("v1", false, 1, true);
        Generation g1 = new Generation(1, p1);
        router.swap(g1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> oldCall =
                pool.submit(() -> router.route("old"));
            await(p1.entered, "G1 request entered");

            FakePlugin p2 = new FakePlugin("v2", false, 0, false);
            Generation g2 = new Generation(2, p2);
            require(router.swap(g2) == g1, "G1 retired");
            require(g1.state() == State.QUIESCING,
                    "old gate closed");
            require(router.route("new").equals("v2:new"),
                    "new request routes to G2");

            require(!router.publishIfCurrent(g1, "stale-g1"),
                    "stale G1 callback rejected");
            require(router.publishIfCurrent(g2, "fresh-g2"),
                    "G2 callback accepted");

            Future<?> draining = pool.submit(() -> {
                g1.shutdown();
                return null;
            });
            require(p1.closeCount.get() == 0,
                    "G1 must not close early");
            p1.release.countDown();
            require(result(oldCall).equals("v1:old"),
                    "G1 in-flight request completes");
            draining.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            require(g1.state() == State.STOPPED, "G1 retired");

            FakePlugin p3 = new FakePlugin("v3", false, 0, false);
            Generation g3 = new Generation(3, p3);
            require(router.swap(g3) == g2, "G2 retired");
            require(!router.publishIfCurrent(g1, "late-g1"),
                    "late G1 rejected");
            require(!router.publishIfCurrent(g2, "late-g2"),
                    "late G2 rejected");
            require(router.publishIfCurrent(g3, "fresh-g3"),
                    "G3 accepted");
            require(router.marker().equals("fresh-g3"),
                    "newest callback wins");
            require(router.route("latest").equals("v3:latest"),
                    "new request routes to G3");

            g2.shutdown();
            router.stopCurrent();
            require(g2.state() == State.STOPPED, "G2 stopped");
            require(g3.state() == State.STOPPED, "G3 stopped");
            require(p1.closeCount.get() == 1
                    && p2.closeCount.get() == 1
                    && p3.closeCount.get() == 1,
                    "every generation cleaned once");
            System.out.println("PASS multi-generation replacement");
        } finally {
            p1.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testFailedCandidateKeepsOld() throws Exception {
        Router router = new Router();
        FakePlugin previous = new FakePlugin(
            "stable", false, 0, false);
        Generation g1 = new Generation(1, previous);
        router.swap(g1);

        FakePlugin broken = new FakePlugin(
            "broken", true, 0, false);
        Generation g2 = new Generation(2, broken);
        boolean failed = false;
        try {
            router.swap(g2);
        } catch (IllegalStateException expected) {
            failed = expected.getMessage().equals("init denied");
        }
        require(failed, "candidate initialization fails");
        require(g1.state() == State.ACTIVE,
                "old generation still ACTIVE");
        require(router.route("ok").equals("stable:ok"),
                "old generation still handles requests");
        g2.shutdown();
        require(!broken.resourceOpen, "candidate cleaned");
        router.stopCurrent();
        require(previous.closeCount.get() == 1, "old cleaned");
        System.out.println("PASS failed replacement rollback");
    }

    public static void main(String[] args) throws Exception {
        testConcurrentCalls();
        testFailedInitialization();
        testGracefulStop();
        testMultipleGenerations();
        testFailedCandidateKeepsOld();
        System.out.println("ALL TESTS PASSED");
    }
}
```

### 8.3. Compiling and Running

With **JDK 17+**, place all the code above in `LifecycleTests.java` and run:

```powershell
javac -encoding UTF-8 LifecycleTests.java
java LifecycleTests
```

**Expected stdout when all assertions succeed:**

```text
PASS concurrent calls
PASS initialization rollback
PASS graceful stop
PASS multi-generation replacement
PASS failed replacement rollback
ALL TESTS PASSED
```

Worker threads may run in varying order, yet the program **prints each PASS line only after verifying that case**, so successful stdout stays in the exact order above. On a bug, the program throws `AssertionError`/exception or hits a test timeout instead of printing fake PASS lines.

### 8.4. Reading the Key Components

**`FakePlugin`** is a minimal stateful *test double*:

- `entered` signals exactly how many requests have entered the handler.
- `release` holds requests inside the handler until the test allows completion.
- `concurrent` and `maximum` prove genuine overlap, not merely submitting two `Future`s.
- `resourceOpen` models a resource allocated during `initialize`; turned on before throwing to test partial-initialization cleanup.
- `closeCount` proves no premature or duplicate close.

**`Generation`** encapsulates state and admission:

- `start()` transitions `NEW → INITIALIZING → ACTIVE` or `FAILED`, retaining `lastFailure`.
- `acquire()` increments `inFlight` only when state is `ACTIVE`.
- `releaseLease()` always decrements once and calls `notifyAll()` for shutdown waiters.
- `quiesce()` blocks new leases without interfering with granted leases.
- `shutdown()` waits for `inFlight == 0` before calling plugin `close()`; `shutdownStarted` prevents double-close.
- `gateClosed` is purely a **test observation point**, not a lifecycle mechanism every plugin must expose.

**`Router`** guards the *current generation*:

- `route()` reads `current` and calls `selected.acquire()` under the **same router lock**.
- `swap()` initializes the candidate **first**, then under the router lock closes the old generation's gate and assigns the new current.
- `stopCurrent()` closes the gate and clears current under lock, then stops the old generation **outside the lock**.
- `publishIfCurrent()` rejects callbacks from older generations, rather than comparing only plugin IDs.

Never hold the router lock while calling `plugin.handle` or `plugin.close`. Plugin code may block, throw, or call back into the host; holding a global lock across it risks deadlocks and serializes all requests.

### 8.5. Why Avoid `Thread.sleep`?

The concurrent case proceeds only after both threads reach `fake.entered`. The stop case checks rejection only after `g1.gateClosed` is signaled. The replacement case holds G1 on `release` until G2 is published. With these latches, tests **actively force meaningful interleavings**.

The 10-second timeout on `await`/`Future.get` only flags deadlocks or hung CI runs. It must never be used to assume a thread "probably" reached a point just because 10 ms elapsed.

### 8.6. Important Limitations of This Demo

This is an **illustrative test harness**, not a production-ready plugin manager. Specifically:

- `Generation.start()` and `shutdown()` follow a coordinated workflow; the demo **does not** support canceling a blocked `initialize()` from another thread.
- `shutdown()` in the demo waits indefinitely for in-flight requests to finish; `InterruptedException` while waiting has no rollback protocol. Production needs timeouts, interrupt policies, and accurate state cleanup if the stopping thread is interrupted.
- `swap()` does not serialize **multiple concurrent candidate swaps**; a production manager must serialize deployment operations, maintain generation sequences/fencing tokens, and roll back candidates on failed publish.
- `FakePlugin` uses `volatile boolean resourceOpen` and atomics for test instrumentation; real plugins may contain complex mutable state and must protect their own thread safety.
- `close()` in the test always succeeds; close failures, retry policies, and FAILED transitions require dedicated tests.
- `ServiceLoader`/JAR loading/class loaders are separated from this demo to focus on **lifecycle and concurrency**. You can connect this manager to providers discovered via SPI or `ModuleLayer` after verifying identity and dependencies.
- The callback assertions here apply to **an in-JVM registry**. When callbacks write to a database or distributed system, store-validated fencing tokens are required to truly prevent stale writes.

The goal of the example is turning race-prone conditions into **reproducible test assertions**, then extending them for production architecture.

## 9. Organizing Tests with JUnit 5 and CI

### 9.1. How to Port to JUnit 5

In a project using JUnit 5, each case maps to a `@Test` method using `Assertions.assertEquals`, `assertThrows`, `assertTrue`, and appropriate timeouts. The runnable section above intentionally avoids framework dependencies so it runs on any JDK.

You can keep `FakePlugin`, `Generation`, and `Router` as test fixtures, then split:

```java
// Illustrative snippet using JUnit Jupiter; requires junit-jupiter dependency
// and placement in a test class with proper @Test imports.
@Test
void rejectedAfterStop() throws Exception {
    // Arrange: request is blocked on latch.
    // Act: stop closes gate, observed via latch.
    // Assert: new route rejected; close has not run.
    // Release: open latch in finally and wait for stop to finish.
}
```

When using `assertTimeoutPreemptively`, the framework executes test code in another thread; interruption cannot reliably terminate blocking I/O or arbitrary plugin code. Always put **explicit cleanup in `finally`**, preventing lingering executors/threads from polluting subsequent tests.

### 9.2. Designing a Fake Plugin with Fault Injection

An advanced fake can expose:

```text
failOnVerify
failOnInitializeBeforeResource
failOnInitializeAfterResource
failOnStart
failOnHandle
failOnClose
blockInitialize
blockHandle
blockClose
emitLateCallback
```

Each case must assert:

- Event ordering (`verify/initialize/start/handle/close`).
- Invocation counts and remaining open resources.
- State and failure history after every transition.
- Current generation is not wrongly overwritten.
- Acceptance/rejection of new requests after quiescing.
- In-flight count returns to 0 even when handlers throw.

Do not force a single fake to handle every fault if that hurts readability; multiple small fakes, one per behavior, work fine.

### 9.3. Additional Test Cases

| Scenario | Key Assertion |
| --- | --- |
| Two concurrent calls | Both enter handler before release; `maxConcurrent >= 2` |
| N requests, one throws | `inFlight` returns to 0; stop does not deadlock |
| Request arrives right after quiesce | No lease granted on old generation |
| Stop while handler is blocked | Resources not closed before release |
| Two concurrent stop calls | Closed exactly once; both callers see consistent result |
| Initialize fails before resource open | Not published; safe cleanup |
| Initialize fails after resource open | Zero leaks; root cause preserved |
| Start/readiness timeout | Never ACTIVE; candidate cleaned up; old generation keeps running |
| Close throws | Failure logged, no false STOPPED status, other resources handled per contract |
| Candidate replacement fails | Current unchanged; traffic keeps routing to old |
| Swap G1 → G2 while G1 runs request | Old request returns from G1, new requests go to G2 |
| Swap G1 → G2 → G3 | Stale G1/G2 callbacks do not mutate G3 |
| Concurrent G2 and G3 deployments | Serialization/CAS and cleanup of losing candidate |
| Restart same plugin version | Generation ID is still incremented/new |
| Stop before async callback completes | Old callback is fenced, does not republish |
| Dependency plugin B stopped | Dependent plugin A stops using closed B |
| Repeated hot reloads | No retained old loader via threads/TCCL/`ThreadLocal`/listeners |
| Broken artifact/module/SPI | Distinguish missing provider from broken configuration |

### 9.4. Running in CI

- Run deterministic latch-based tests on every pull request.
- Run repeated/concurrency stress tests in a dedicated job to catch rare races; **stress tests do not replace invariant tests**.
- Test across supported JDK versions and varied CPU counts where available.
- Set deadlines for both the test suite and each `Future`; capture thread dumps on timeout with generation ID and phase logged.
- Never use `sleep` as a synchronization primitive; use latches/barriers/phasers or schedule-testing tools.
- Test with **real JAR/module artifacts** (SPI descriptors, JPMS `uses/provides`, class-loader policy) alongside unit-level lifecycle harnesses.
- If deploying via rolling upgrades, test restarts and failed deployments in a multi-instance staging environment, not just one JVM.

## 10. Common Mistakes and Fixes

| Mistake | Why Dangerous | Proper Test |
| --- | --- | --- |
| Firing two `Future`s and assuming concurrency | Does not prove handlers overlapped | Use latches to wait until both enter handler |
| `Thread.sleep(100)` waiting for stop | Flaky across schedulers/CI | Latch/event confirming gate actually closed |
| Checking state and incrementing counter separately | Races with closing gate | Atomic lease acquisition under lock/CAS protocol |
| Testing stop only when idle | Misses premature close bugs | Block handler, start stop, assert `closeCount=0` |
| Asserting only that initialize throws | Misses leaked partial resources and publication | Resource flag + no-current + cleanup assertions |
| Publishing candidate before readiness | Broken deployment kills healthy provider | Start candidate before swap; test failure rollback |
| Swapping current and closing gate uncoordinated | Request can acquire old lease after cutover | Route acquire and swap share lock |
| Comparing only plugin ID for callbacks | Old/new generations share the same ID | Fence with generation instance/token |
| Reusing FAILED object after partial error | State/resources left undefined | Fresh instance/generation after cleanup |
| Calling `URLClassLoader.close()` and treating stop as done | Threads/callbacks still run; classes not unloaded | Quiesce, drain, clean up, clear references |
| Testing only success paths | Misses exception/interrupt/deadline bugs | Inject faults per phase |
| Asserting thread count instead of in-flight leases | Does not reflect admitted requests | Assert admission and manager counters |
| Using race stress as sole evidence | Can pass while rare races remain | Combine invariants + deterministic interleaving + stress |

## 11. Pre-Deployment Testing Checklist

- [ ] Distinguish `NEW/INITIALIZING/ACTIVE/QUIESCING/STOPPING/STOPPED/FAILED` and desired vs. observed states.
- [ ] Guard transitions so only `ACTIVE` grants leases.
- [ ] Router selects current and acquires lease atomically with swap.
- [ ] Release leases in `finally` even when handlers throw.
- [ ] Test overlapping handlers using latches, never `sleep`.
- [ ] Test init failure **after** resource allocation and verify single cleanup.
- [ ] Never publish a failed candidate; keep old generation `ACTIVE` if cutover hasn't occurred.
- [ ] Stop closes gate first, drains in-flight work, then closes resources.
- [ ] Repeated/concurrent stops never double-close; close failures record status and logs.
- [ ] Hot replacement keeps old requests on old generation and routes new requests to new generation.
- [ ] Stale G1/G2 callbacks cannot mutate G3 registry; enforce generation tokens.
- [ ] Define timeout/cancellation policies for handlers and shutdown in production.
- [ ] Test SPI/class-loader/module/dependency errors separately from lifecycle harnesses.
- [ ] Test repeated hot-reload cycles and leak checks (threads, TCCL, caches, callbacks, loader refs).
- [ ] Run deterministic unit tests + artifact integration tests + concurrency stress in CI.

**Conclusion:** good plugin lifecycle testing does not simply ask "does the code run?", it asks "**when events overlap, which invariants still hold?**" Actively force races with latches/barriers, track in-flight leases and states, force initialization failures after allocation, prove graceful shutdown never closes early, and enforce generation fencing across G1 → G2 → G3. With these assertions in place, you have solid evidence for deploying and upgrading plugins without dropping requests or leaking resources.

**Java SE 17 Documentation:** [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html), [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), [`AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html).
