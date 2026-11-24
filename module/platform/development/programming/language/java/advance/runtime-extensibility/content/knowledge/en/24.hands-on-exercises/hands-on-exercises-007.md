# Hands-On: Swapping Plugin Versions Under Active Requests and Verifying Resource Cleanup

A Java system supporting plugins may update implementations while the application is still serving requests. The difficulty does not lie in assigning `currentPlugin = newPlugin`, but in **requests that have already started using the old plugin** and **the old version's resources**. If you close files/JARs, connection pools, or workers while requests are still using them, those requests may fail mid-flight; if you never close them, the host leaks memory, threads, file handles, and class loaders after every version swap.

This exercise builds a **router with generations, leases, and graceful drain**, intentionally parks a v1 request mid-flight, switches the router to v2 while that request is still in-flight, confirms new requests run on v2, then lets the v1 request finish and verifies resource cleanup. The example uses **Java 17+**, two threads coordinated by CountDownLatch for a deterministic, repeatable test sequence, and a close-call counter to verify **exactly-once close**, requiring no HTTP server, Maven, Gradle, or external JARs.

Completion goals:

1. A request holding a **v1 lease acquired before cutover** always finishes on v1, even after the router selects v2.
2. Requests **admitted after cutover** route to v2.
3. v1 enters the **DRAINING** state and must not be closed while still in-flight.
4. Once v1's last lease is returned and retirement is requested, v1's resource is closed **exactly once**.
5. v2 stays open while ACTIVE, and is closed when the host shuts down with no remaining requests.
6. No request execution or heavy resource cleanup happens inside the routing lock.
7. Distinguish evidence of **close being called**, **OS/system resources being released**, and **class loaders being eligible for garbage collection**: these are three distinct levels of proof.

This is a **single-JVM model exercise**. It verifies fundamental invariants and synchronization techniques, though it does not replace a production plugin platform with ModuleLayer, URLClassLoader, network streams, databases, multi-node rollouts, side effects, and its own security boundaries.

## 1. Scenario and Test Requirements

Suppose the host has two handler versions:

- **v1** returns results prefixed with v1.
- **v2** returns results prefixed with v2.
- **Request A** acquires v1 before the switch, then pauses on a latch.
- **Main thread** activates v2 and requests retirement of v1.
- **Request B** arrives after the switch and routes to v2.
- Main thread then releases request A to continue, and waits for A to finish.
- Host verifies v1's resource was closed exactly once, even if retire is called again.
- Finally, host shuts down v2 and verifies v2's resource is also closed exactly once.

**Observed timeline:**

~~~text
Time            Worker handling A                 Main / Router
-----------     -------------------------------     ---------------------------
t0                                                  v1 is ACTIVE
t1              acquire(v1); inFlight(v1)=1
t2              wait on finishOld latch             confirm acquired
t3                                                  activate(v2), v1 DRAINING
t4                                                  retire(v1): NOT closed yet
t5                                                  acquire(v2), handle B
t6                                                  release(v2); v2 still ACTIVE
t7                                                  release finishOld latch
t8              use v1 to handle A
t9              release(v1); inFlight(v1)=0
t10             worker finishes                     v1 CLOSED, closeCalls(v1)=1
t11                                                 retire(v1) 2nd time: no duplicate close
t12                                                 shutdown: v2 CLOSED
~~~

The timestamps above show the **logical ordering enforced by latches**, without assuming OS scheduling speed or using Thread.sleep to manufacture races. In reality, request A might start work and block on I/O while request B and subsequent requests already run on v2. The exercise uses latches to control timing deterministically rather than guessing wait durations.

### Key terminology

| Term | Meaning in this exercise | Common misconception |
| --- | --- | --- |
| **Generation** | A plugin instance/version with its own lifecycle, counter, and state | Not merely a semantic version string |
| **ACTIVE** | Generation admitting new requests | Does not mean all current requests use this generation |
| **Lease** | Permission to use a generation bound to one request | Not a lock held throughout business-logic execution |
| **inFlight** | Number of leases issued and not yet returned | Does not automatically track out-of-contract background callbacks |
| **DRAINING** | Admits no new requests, waiting for existing leases to finish | Does not mean immediate resource closure |
| **CLOSING** | Won exclusive right to run one-time cleanup | Not proof that cleanup has finished |
| **CLOSED** | Cleanup returned successfully | Does not prove classes were immediately unloaded |
| **CLEANUP_FAILED** | Cleanup threw an error | Should not falsely report CLOSED or blindly retry |

The hardest part is **atomicity between selecting a version and incrementing inFlight**. If one thread reads `current=v1` without yet incrementing inFlight, while another thread swaps to v2, sees `inFlight(v1)=0`, and closes v1, the old request could use an already-closed resource. Therefore, in this example, both **acquire** and **activate** execute inside the same brief monitor.

## 2. Minimal Architecture for Practice

Each generation owns a Plugin and a tracked resource:

~~~text
+------------------------------- Host --------------------------------+
|                                                                     |
| Router                                                              |
|   gate: monitor                                                     |
|   active ----------------------------+                              |
|                                      |                              |
|    +---------------+       +---------v----------+                   |
|    | Generation v1 |       | Generation v2      |                   |
|    | DRAINING      |       | ACTIVE             |                   |
|    | inFlight = 1  |       | inFlight = 0       |                   |
|    | retire = true |       | retire = false     |                   |
|    | Plugin(v1)    |       | Plugin(v2)         |                   |
|    | Resource(v1)  |       | Resource(v2)       |                   |
|    +-------^-------+       +--------------------+                   |
|            |                                                        |
|      Lease of A                                                     |
|                                                                     |
+---------------------------------------------------------------------+
~~~

Here, **TrackedResource** is a simulated resource tracking `closeCalls`. It is actually closed via `AutoCloseable.close`, without opening real files or JARs. The advantage of a simulated resource is that test results are **exact, measurable, and independent of GC or the filesystem**. Later extension sections connect this lifecycle to URLClassLoader and real resources.

### Invariants to verify

- **B1 — Admission:** Only an ACTIVE generation issues new leases.
- **B2 — Pinning:** A lease stays pinned to the generation active when issued; it never re-reads `active` on each operation.
- **B3 — Safe retirement:** A DRAINING generation with `inFlight > 0` must never be closed.
- **B4 — Exactly-once cleanup attempt:** When DRAINING, `retirementRequested` is true, and `inFlight` hits 0, only one thread wins the transition to CLOSING and invokes cleanup.
- **B5 — No counter underflow:** Each lease releases only once, even if `close` is called repeatedly.
- **B6 — Short critical section:** Neither `plugin.handle` nor `plugin.close` runs inside the routing monitor.
- **B7 — Shutdown:** When the host stops accepting new requests, the ACTIVE generation transitions to DRAINING and closes once leases drain.
- **B8 — Failure visibility:** If cleanup throws an error, transition to CLEANUP_FAILED; never conflate with CLOSED.

B1 through B7 are directly observed in the example; B8 is illustrated by the exception-handling path and has a dedicated failure exercise in section 8.

## 3. Preparing the Environment

Requirements:

- **JDK 17 or newer**, with `javac` and `java` commands. No third-party libraries required.
- A working directory containing only the exercise's **PluginSwapLab.java** file.
- A terminal in that directory with write permissions for `.class` files during compilation.
- Ability to read stdout and any errors if tests fail.

Verify:

~~~bash
java -version
javac -version
~~~

Exact output depends on the installed JDK. Use **javac --release 17** to target Java 17, provided the compiler supports that target.

Directory layout after compilation:

~~~text
plugin-swap-lab/
├── PluginSwapLab.java
├── PluginSwapLab.class
├── PluginSwapLab$Router.class
├── PluginSwapLab$Generation.class
├── PluginSwapLab$Lease.class
├── PluginSwapLab$Plugin.class
├── PluginSwapLab$TrackedResource.class
└── ... other nested classes generated by javac
~~~

The `.class` listing illustrates the structure; specific types such as enum State produce their own `.class` files. There is no need to package `.class` files into a JAR to run this exercise.

## 4. Complete Java 17 Program

Create **PluginSwapLab.java** and copy the exact contents below. The file has a single public class in the default package so it runs cleanly with `java PluginSwapLab`.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class PluginSwapLab {
    enum State { PREPARED, ACTIVE, DRAINING, CLOSING, CLOSED, CLEANUP_FAILED }

    static final class TrackedResource implements AutoCloseable {
        private final AtomicInteger closeCalls = new AtomicInteger();

        void checkOpen() {
            if (closeCalls.get() != 0) {
                throw new IllegalStateException("Resource was already closed");
            }
        }

        int closeCalls() { return closeCalls.get(); }

        @Override public void close() { closeCalls.incrementAndGet(); }
    }

    static final class Plugin implements AutoCloseable {
        final String version;
        final TrackedResource resource = new TrackedResource();

        Plugin(String version) { this.version = version; }

        String handle(String request) {
            resource.checkOpen();
            return version + ":" + request;
        }

        int closeCalls() { return resource.closeCalls(); }

        @Override public void close() { resource.close(); }
    }

    static final class Generation {
        final Plugin plugin;
        State state = State.PREPARED;
        int inFlight;
        boolean retirementRequested;

        Generation(String name) { plugin = new Plugin(name); }
    }

    static final class Lease implements AutoCloseable {
        private final Router router;
        private final Generation pinned;
        private final AtomicBoolean returned = new AtomicBoolean();

        Lease(Router router, Generation pinned) {
            this.router = router;
            this.pinned = pinned;
        }

        String handle(String input) {
            if (returned.get()) {
                throw new IllegalStateException("Lease was returned");
            }
            return pinned.plugin.handle(input);
        }

        @Override public void close() {
            if (returned.compareAndSet(false, true)) {
                router.release(pinned);
            }
        }
    }

    static final class Router {
        private final Object gate = new Object();
        private Generation active;

        Router(Generation initial) {
            if (initial.state != State.PREPARED) {
                throw new IllegalArgumentException("Initial is not prepared");
            }
            initial.state = State.ACTIVE;
            active = initial;
        }

        Lease acquire() {
            synchronized (gate) {
                Generation g = active;
                if (g == null || g.state != State.ACTIVE) {
                    throw new IllegalStateException("No active plugin");
                }
                g.inFlight++;
                return new Lease(this, g);
            }
        }

        void activate(Generation candidate) {
            synchronized (gate) {
                if (active == null || candidate.state != State.PREPARED) {
                    throw new IllegalStateException("Invalid cutover");
                }
                Generation old = active;
                old.state = State.DRAINING;
                candidate.state = State.ACTIVE;
                active = candidate;
            }
        }

        void retire(Generation g) {
            Plugin toClose;
            synchronized (gate) {
                if (g == active) {
                    throw new IllegalStateException("Still active");
                }
                if (g.state == State.CLOSED ||
                    g.state == State.CLOSING ||
                    g.state == State.CLEANUP_FAILED) {
                    return;
                }
                if (g.state != State.DRAINING) {
                    throw new IllegalStateException("Not draining");
                }
                g.retirementRequested = true;
                toClose = beginCleanupIfReady(g);
            }
            performCleanup(g, toClose);
        }

        void release(Generation g) {
            Plugin toClose;
            synchronized (gate) {
                if (g.inFlight <= 0) {
                    throw new IllegalStateException("Lease count underflow");
                }
                g.inFlight--;
                toClose = beginCleanupIfReady(g);
            }
            performCleanup(g, toClose);
        }

        private Plugin beginCleanupIfReady(Generation g) {
            if (g.state == State.DRAINING &&
                g.retirementRequested && g.inFlight == 0) {
                g.state = State.CLOSING;
                return g.plugin;
            }
            return null;
        }

        private void performCleanup(Generation g, Plugin plugin) {
            if (plugin == null) return;
            boolean success = false;
            try {
                plugin.close();
                success = true;
            } finally {
                synchronized (gate) {
                    g.state = success ? State.CLOSED : State.CLEANUP_FAILED;
                }
            }
        }

        void shutdown() {
            Generation old;
            synchronized (gate) {
                old = active;
                active = null;
                if (old != null) old.state = State.DRAINING;
            }
            if (old != null) retire(old);
        }

        State stateOf(Generation g) {
            synchronized (gate) { return g.state; }
        }

        int inFlightOf(Generation g) {
            synchronized (gate) { return g.inFlight; }
        }
    }

    public static void main(String[] args) throws Exception {
        Generation v1 = new Generation("v1");
        Generation v2 = new Generation("v2");
        Router router = new Router(v1);

        CountDownLatch oldHasLease = new CountDownLatch(1);
        CountDownLatch finishOld = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            Future<String> oldRequest = worker.submit(() -> {
                try (Lease lease = router.acquire()) {
                    oldHasLease.countDown();
                    if (!finishOld.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Timed out waiting");
                    }
                    return lease.handle("A");
                }
            });

            if (!oldHasLease.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not acquire");
            }

            System.out.println("old-inflight=" + router.inFlightOf(v1));

            router.activate(v2);
            router.retire(v1);

            System.out.println("old-during-switch=" + router.stateOf(v1));
            System.out.println("old-close-before-finish=" + v1.plugin.closeCalls());

            try (Lease lease = router.acquire()) {
                System.out.println("new-request=" + lease.handle("B"));
            }

            finishOld.countDown();
            System.out.println("old-request=" + oldRequest.get(10, TimeUnit.SECONDS));

            System.out.println("old-after-drain=" + router.stateOf(v1));
            System.out.println("old-close-count=" + v1.plugin.closeCalls());

            router.retire(v1);
            System.out.println("old-close-after-retry=" + v1.plugin.closeCalls());

            router.shutdown();
            System.out.println("new-after-shutdown=" + router.stateOf(v2));
            System.out.println("new-close-count=" + v2.plugin.closeCalls());
        } finally {
            finishOld.countDown();
            worker.shutdownNow();
            router.shutdown();
        }
    }
}
~~~

### Why doesn't the program need real plugin libraries?

The goal of this exercise is to **verify version-swap and resource-cleanup invariants first**, avoiding noise from classpath resolution, ServiceLoader, ModuleLayer, or networking. TrackedResource simulates a closeable resource; that lets us pinpoint exactly when a resource is used after close or closed multiple times. Once the generation/lease mechanism is sound, real loaders, JARs, and resources can be wired into Plugin.

One notable detail: TrackedResource intentionally **does not guard itself to turn multiple closes into one**. Every close call increments the AtomicInteger. That way, if the router has a bug and closes twice, tests catch `closeCalls=2` rather than masking the bug behind an idempotent resource. In production, specific resources may or may not be idempotent; the router must still guarantee it never attempts duplicate closes.

## 5. Compiling, Running, and Comparing Stdout

Compile:

~~~bash
javac --release 17 -encoding UTF-8 PluginSwapLab.java
~~~

Run:

~~~bash
java PluginSwapLab
~~~

**Verified stdout from the unmodified program on JDK 17+:**

~~~text
old-inflight=1
old-during-switch=DRAINING
old-close-before-finish=0
new-request=v2:B
old-request=v1:A
old-after-drain=CLOSED
old-close-count=1
old-close-after-retry=1
new-after-shutdown=CLOSED
new-close-count=1
~~~

The program uses a 10-second timeout to **fail loudly** in hung environments or unresponsive schedulers. On a normal machine where both threads are scheduled, the stdout order above is deterministic because it is synchronized by two CountDownLatches and `Future.get`. A timeout or compiler version mismatch is an error condition to investigate, not a reason to expect arbitrary output.

### Line-by-line explanation

| Line | Evidence |
| --- | --- |
| old-inflight=1 | Worker A acquired a v1 lease; router recorded one request using v1 |
| old-during-switch=DRAINING | Switch stopped issuing new leases to v1 without closing its resource yet |
| old-close-before-finish=0 | v1 still has an in-flight request, so retire must not close prematurely |
| new-request=v2:B | A lease acquired after cutover routes cleanly to generation v2 |
| old-request=v1:A | Request A stays on v1 even though v2 is already ACTIVE |
| old-after-drain=CLOSED | Once A returns its lease, counter drops to 0 and v1 cleanup succeeds |
| old-close-count=1 | v1 resource cleanup ran exactly once |
| old-close-after-retry=1 | Repeated retire call did not trigger a second close |
| new-after-shutdown=CLOSED | Shutdown stops admission and cleans up v2 once leases drain |
| new-close-count=1 | v2's resource was also closed exactly once |

**Passing criteria**: all lines appear in order with the right states, no exceptions occur, and the worker finishes within the test timeout. Merely observing "the program didn't crash" is insufficient, since a design that leaks resources can still complete business logic without immediate errors.

## 6. Anatomy of the Synchronization Points

### 6.1. Acquiring atomically with switching

In `Router.acquire`:

~~~java
synchronized (gate) {
    Generation g = active;
    if (g == null || g.state != State.ACTIVE) {
        throw new IllegalStateException("No active plugin");
    }
    g.inFlight++;
    return new Lease(this, g);
}
~~~

This is an **excerpt from the Router class**, not a standalone program. It forces reading the pointer, checking ACTIVE, and incrementing inFlight to occur in a single critical section. Switching also acquires `gate` before updating the pointer and old state. Thus only two orderings are legal:

1. Acquire before switch: the request obtains v1 and `inFlight(v1)` is already incremented; switch cannot clean up v1 early.
2. Switch before acquire: the request reads `active=v2` and obtains a v2 lease.

There is no window where "v1 was chosen, not yet counted in inFlight, and already closed", as happens when reading a pointer and incrementing a refcount in two unsynchronized steps.

### 6.2. Lease pins the generation instead of re-reading current

Lease holds:

~~~java
private final Generation pinned;
~~~

Handling calls `pinned.plugin.handle(input)`, **not** `router.active.plugin.handle(input)` again. Thus request A can span the cutover timestamp while continuing to use v1 throughout its authorized logic.

In real applications, one request may invoke a plugin multiple times, pass through callbacks, or execute transactions. Pass the lease/context carrying the generation ID down to every step that needs the plugin; never quietly re-resolve `current` mid-workflow, because a single request could hit incompatible APIs or data schemas across versions.

### 6.3. Lease close is counting-idempotent

Lease uses an AtomicBoolean:

~~~java
if (returned.compareAndSet(false, true)) {
    router.release(pinned);
}
~~~

This is also an excerpt. If `close` is invoked twice, only the first call decrements inFlight. This prevents underflow and duplicate cleanup triggers. AtomicBoolean **does not mean the same Lease may be handled and closed concurrently from multiple threads**; the Lease owner must manage request ownership and never use it after closing. In production code, guard both plugin calls and actual completion timing.

### 6.4. Electing the single thread authorized to clean up resources

`Router.beginCleanupIfReady` returns a Plugin to close only when all three conditions hold:

~~~java
g.state == State.DRAINING
    && g.retirementRequested
    && g.inFlight == 0
~~~

Before leaving the critical section, the method sets **g.state = CLOSING**. Any other thread calling `retire` or `release` sees the state is no longer DRAINING and cannot win the same cleanup right. Actual cleanup (`plugin.close`) runs **outside the gate**.

This prevents two opposite bugs:

- **Premature close**: closing before all leases have returned.
- **Duplicate close**: two threads both observing `inFlight=0` and closing concurrently.

If `close` throws an unchecked exception, `finally` transitions state to CLEANUP_FAILED; it never lies that resources were released. Production implementations should log the failure and provide an intentional retry/compensation workflow rather than blindly retrying a close that may have non-idempotent side effects.

### 6.5. Cleanup runs outside the gate

If `plugin.close` calls into a thread pool, database, or host callback, the operation may block for a long time or re-enter other components. Calling `close` inside `synchronized(gate)` would stall incoming requests and risk lock-order deadlocks.

In this example, Router uses `gate` strictly to:

- inspect/update generation state;
- increment/decrement inFlight;
- decide who owns cleanup;
- swap the active pointer.

Both **Plugin.handle** and **Plugin.close** execute outside the gate. Production systems should add cleanup-completion tracking so controllers know whether a slow close finished or failed.

## 7. Guided Walkthrough: Milestone by Milestone

### Milestone A — observing v1 before cutover

Run the initial program. Explain why main must wait on:

~~~java
oldHasLease.await(10, TimeUnit.SECONDS)
~~~

If main did not wait, it might activate v2 before the worker actually acquired a lease, causing request A to acquire v2 by chance. Then the test would fail to prove the "in-flight v1 request" scenario.

**Self-check question:** If you replace the latch with `Thread.sleep(100)`, does the test still guarantee A acquired v1? **No.** The scheduler might delay the worker beyond 100 ms, or main might proceed sooner than expected. You need a synchronization primitive representing the actual event.

### Milestone B — activating v2 while v1 is still in-flight

Once the worker holds a v1 lease, main executes:

~~~java
router.activate(v2);
router.retire(v1);
~~~

At this point `inFlight(v1)=1`. Hence the state must be DRAINING and `closeCalls(v1)=0`. If any line showed v1 already CLOSED or `closeCalls > 0`, the host violated invariant B3 or the counter failed to reflect real work.

A tiny bug in routing could break this test: closing v1 directly inside `activate`. The test is designed to catch that bug when the worker resumes calling `Plugin.handle`.

### Milestone C — new requests see v2

After cutover, main acquires another lease:

~~~java
try (Lease lease = router.acquire()) {
    System.out.println("new-request=" + lease.handle("B"));
}
~~~

The required output is `new-request=v2:B`. If it prints `v1:B`, either the active pointer or the admission check failed to switch properly. If it blocks indefinitely, a lock may be held while waiting for the old request to finish.

### Milestone D — draining v1 and verifying exactly-once close

After request B completes, main opens the latch so A can proceed:

~~~java
finishOld.countDown();
String result = oldRequest.get(10, TimeUnit.SECONDS);
~~~

`Future.get` waits for the worker callable to finish, including the `try-with-resources` call to `Lease.close`. Therefore, when main inspects the state afterward (assuming cleanup didn't fail), v1 must be CLOSED and `closeCalls(v1)=1`.

Remember that `Future.get` only confirms completion of the work inside the callable. If a real plugin spawns fire-and-forget tasks and returns early, future completion **does not prove** those tasks stopped using that version; those tasks must be tracked under the real system's lifecycle/leases.

### Milestone E — repeated retire and shutdown

Main intentionally calls `retire(v1)` a second time. This is an **idempotency test for the lifecycle controller**, not an invitation for production code to retry infinitely. The CLOSED state is ignored and `closeCalls` stays at 1.

Next comes `router.shutdown`: the active pointer becomes null, generation v2 stops admitting new work, and then v2 is retired. Because no v2 leases remain, v2 cleanup finishes immediately. The line `new-close-count=1` proves the demo does not leak the ACTIVE generation's resources on host exit.

**An extra test:** After shutdown, call `router.acquire` inside a `try/catch`; it must throw `IllegalStateException("No active plugin")`. New requests must never receive an already-closed generation.

## 8. Variant Exercises to Test Real Failure Modes

Run each exercise below on a **separate temporary copy of PluginSwapLab.java** without modifying the verified baseline unless you saved a backup. These variants intentionally violate invariants or change policies, so stdout/exceptions will differ; therefore **do not expect section 5's standard output** from them.

### Exercise 1 — intentionally closing v1 too early

Try calling `v1.plugin.close()` right after `activate(v2)`, before `finishOld.countDown()`. `TrackedResource.closeCalls` increments to 1 while request A is still unfinished. When A resumes `handle`, `checkOpen` throws `IllegalStateException("Resource was already closed")`.

**Lesson:** An atomic pointer alone does not protect the old resource. Never "fix" this by removing `checkOpen`; defer cleanup until `inFlight` truly reaches 0.

### Exercise 2 — leaking a lease

In a test copy, remove `try-with-resources` in the worker and intentionally omit `lease.close`. The router issued a v1 lease, so the counter never returns to 0; v1 stays DRAINING even after business work returned. This is a **lease leak** that can pin JARs/thread pools indefinitely.

**Lesson:** Every request path needs a reliable `finally`/`try-with-resources` or completion callback. A request must never "forget" to return its lease when an exception occurs.

### Exercise 3 — closing twice

Insert an extra `lease.close()` call before the `try-with-resources` block ends. `AtomicBoolean.compareAndSet` ensures release executes only once. Verify `inFlight` never goes negative and `closeCalls` stays 1.

**Lesson:** Idempotent `close` is a defensive boundary safeguard, not a substitute for clear lease ownership in the request flow.

### Exercise 4 — shutting down while v2 still has active requests

Acquire a v2 lease after cutover, keep it open, and call `router.shutdown` from main. Because v2 has `inFlight > 0`, v2 must move to DRAINING and **not** close yet. Once the v2 lease closes, v2 transitions to CLOSED and `closeCalls=1`.

**Lesson:** The same drain protocol applies to both **version swaps** and **host shutdown**; never let shutdown tear down resources still in use.

### Exercise 5 — testing cleanup failure

Modify `TrackedResource.close` to throw an intentional RuntimeException on a failure-test copy. `Router.performCleanup` must move state to CLEANUP_FAILED via `finally`. At that point you cannot claim resources were freed; log the error and route to an operator review policy.

**Lesson:** Exactly-once attempt does not guarantee exactly-once effect. A close call may free half its resources before throwing; blind retries can cause further damage.

### Exercise 6 — stress testing concurrent admission

Spawn multiple workers with `Executors.newFixedThreadPool`, synchronize the starting line with a CountDownLatch, and call `acquire` and `activate` concurrently. Verify every Lease binds to a single generation, never executes on CLOSED, final counters equal 0, and no duplicate closes occur.

Avoid asserting things like "exactly 50% of requests went to v1" in a concurrency race test; ratios are decided by the scheduler. The invariant to measure is that **every admitted request falls cleanly before or after the cutover** per the monitor protocol.

### Exercise 7 — adding a rollback window

In the basic exercise, main calls `retire(v1)` right after switching, so v1 becomes CLOSED as soon as it drains. You cannot quickly roll back to an already-closed v1.

To support rollback, modify the controller to hold v1 in **STANDBY** when `inFlight=0` and `retirementRequested` is false, and allow reactivating from STANDBY after data-compatibility checks. Only retire/close once the rollback window expires. This is an **extension exercise**, not behavior already built into the current program. Before enabling rollback in production, check data schemas, side effects, and API versions; switching routes does not undo transactions that already committed.

## 9. From Simulated Resources to Real Plugin Resources

TrackedResource only observes `close` calls. In a real Java host, a generation may own:

- **URLClassLoader** keeping plugin JARs and resources open.
- **Plugin instance** with stop/close hooks.
- **ExecutorService** for the plugin's asynchronous tasks.
- **ScheduledExecutorService** for timers or polling.
- **Connection pools**, HTTP clients, file handles, streams, or native resources.
- **Event listeners**, callback registrations, MBeans, and ThreadLocals.
- **Caches** tied to plugin classes/instances, ServiceLoader or ModuleLayer references.
- **Active requests/streams** holding objects defined by that generation's class loader.

Stopping new request admission is necessary but not sufficient. Before closing the loader, ensure the generation's code no longer needs to load classes or resources from it, background tasks are stopped, listeners are unregistered, and all leases are released.

### 9.1. Closing a class loader does not mean immediate class unloading

`URLClassLoader.close()` closes underlying resources such as files/JARs managed by the loader and restricts subsequent class/resource lookups. It **does not delete already-defined Class objects**, does not stop threads executing old bytecode, and does not immediately free metaspace while strong references remain.

Therefore, distinguish three assertions:

1. **Cleanup invoked:** the host called close on the right generation once after `inFlight=0`.
2. **Resources released:** file handles, thread pools, sockets, or pools managed by the plugin were closed/terminated per contract. Measure each real resource type.
3. **Class unloading eligible/observed:** classes/loaders of the generation are no longer reachable; the JVM **may** garbage-collect and unload them. GC timing is non-deterministic; never write brittle tests asserting a WeakReference clears within a fixed number of milliseconds.

In real tests, use JFR/class-unloading diagnostics, a WeakReference to the loader with a generous observation window, and inspect file-handle/thread/metaspace counts across multiple reload cycles. A WeakReference is a useful signal, **not a deterministic pass criterion** after a single `System.gc()` call.

### 9.2. Composing AutoCloseable resources

A plugin manager can group multiple resources under a single owner object. Example skeleton (not a standalone class because it depends on host-supplied types):

~~~java
// REAL-WORLD ILLUSTRATION; requires concrete host-supplied classes/plugins.
final class PluginResources implements AutoCloseable {
    private final AutoCloseable pluginInstance;
    private final java.net.URLClassLoader loader;
    private final java.util.concurrent.ExecutorService executor;
    private final java.util.concurrent.atomic.AtomicBoolean closed =
            new java.util.concurrent.atomic.AtomicBoolean();

    PluginResources(
            AutoCloseable pluginInstance,
            java.net.URLClassLoader loader,
            java.util.concurrent.ExecutorService executor) {
        this.pluginInstance = pluginInstance;
        this.loader = loader;
        this.executor = executor;
    }

    @Override
    public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) return;

        Exception failure = null;
        try {
            pluginInstance.close();
        } catch (Exception e) {
            failure = e;
        }

        executor.shutdown();
        // Production: awaitTermination with deadline; include an escalation policy.
        try {
            loader.close();
        } catch (Exception e) {
            if (failure == null) failure = e;
            else failure.addSuppressed(e);
        }

        if (failure != null) throw failure;
    }
}
~~~

This is a **skeleton that compiles in its own file** thanks to fully qualified names, but it **is not safe to deploy as-is**: you must wait for the executor to actually terminate, prevent tasks from continuing to use the loader after closing, handle step-by-step failures, and track cleanup status/attempts. The shutdown order across callbacks/timers/tasks/loaders must match the plugin's contract; never treat `executor.shutdown()` as proof workers have stopped.

### 9.3. The Java module layer case

A plugin may be deployed via ModuleLayer instead of URLClassLoader. Even then, generation, lease, drain, and rollback concepts **are still required**, while cleanup depends on how class loaders, ModuleLayers, and resources were created. There is no universal `ModuleLayer.close()` API to shut down all classes and resources. The host must close objects with cleanup contracts, drop strong references to the layer/loader, and track tasks/callbacks.

Never create a new ModuleLayer on every deploy while keeping every layer in a static registry. Having zero active requests does not make a layer disappear if a registry or thread context class loader still holds a reference.

## 10. Asynchronous Requests: Leases Must Live Until Actual Completion

The demo worker used Future and try-with-resources: `Future.get` returns only after the callable finishes and the lease has closed. When a plugin returns a CompletableFuture or CompletionStage, **pass the lease to the completion callback**.

Wrong:

~~~java
// RISK ILLUSTRATION; assumes plugin.handleAsync returns CompletionStage<Result>.
try (PluginLease lease = router.acquire()) {
    return lease.plugin().handleAsync(input);
}
// Lease.close runs immediately after returning the stage while the task still uses the plugin.
~~~

Better organization:

~~~java
// ILLUSTRATIVE CODE: PluginLease, router, input, and Result are host-defined.
PluginLease lease = router.acquire();
try {
    return lease.plugin().handleAsync(input)
            .whenComplete((result, error) -> lease.close());
} catch (RuntimeException | Error error) {
    lease.close();
    throw error;
}
~~~

This assumes stage completion truly represents **all** plugin work. If the method spawns a fire-and-forget thread and returns an already-completed stage, the lease still releases too early. For uncooperative workers or untrusted scripts, enforcing timeouts inside the same JVM usually cannot safely stop execution; a worker-process architecture is needed.

Design `Lease.close` to be idempotent and thread-safe at the lifecycle level when callbacks arrive on another thread, and resolve use-versus-close races through explicit ownership. Never force-close a loader while stages remain active simply because the caller's API timeout elapsed.

### Workloads that should count toward in-flight

| Workload type | Appropriate release boundary |
| --- | --- |
| Synchronous HTTP request | End of full processing and response/cleanup needed by the plugin |
| CompletableFuture | When computation truly completes, including error/cancel |
| Message listener | After processing plus ack/nack/transaction per delivery semantics |
| Long-lived stream | When stream terminates or after safe handoff |
| Scheduled task | When callback actually finishes and registration is cancelled |
| Database transaction | After commit/rollback completes and resources are no longer used |
| External callback | When callbacks stop, are deregistered, or ownership transfers safely |

Release timing is dictated by the workload contract, not an arbitrary event such as "returning a Java Future object".

## 11. Resources Leaked Through Invisible References

Even after `close` and `inFlight=0`, an old loader may still remain uncollectable because:

- A thread outside the router is still running plugin code and holding a context class loader.
- A ThreadLocal in a host thread pool retains an instance or Class from the old loader.
- An event bus, registry, or scheduler still holds a plugin listener/callback.
- A static singleton in the host holds a Class, Method, service provider, or plugin object.
- ServiceLoader, logging/metrics, reflection caches, or proxies retain related references.
- A Future, Throwable, completion callback, or request context holds a v1 object.
- JMX/MBeans or framework integrations were not unregistered.

A v1 cleanup checklist must verify both **resource cleanup** and **reference cleanup**, not just calling `close`. In systems with frequent reloads, monitor trends for live class loaders, metaspace, threads, and handles after old generations clear leases and rollback windows.

**Note on memory tests:** GC and class unloading timing are up to the JVM. A single smoke test does not prove "zero leaks" just because metrics look flat after one reload; run stress cycles, diagnostics, and a reasonable observation window. Never build production logic around `System.gc()` as a way to reclaim plugins.

## 12. When Should Resources Not Be Closed Even When inFlight=0?

Some systems maintain a **rollback** window or long-lived handles not covered by a request counter. In those cases, a cleanup decision requires additional checks:

- The generation has been removed from the routing table and cannot issue new leases.
- No requests or background jobs are still using the generation.
- The rollback retention window has expired or an explicit retirement decision was made.
- No untracked sessions, callbacks, or external consumers remain outside lease accounting.
- Data and APIs are confirmed not to need the old generation to continue.
- Shared-scope resources are not mistakenly closed by a single generation.

In this exercise, main **explicitly calls `retire(v1)`** immediately after switching: once `inFlight` hits 0, v1 closes with no rollback window. That is a choice for this lab, **not the only rule for every product**.

If you want fast rollback to v1, keep v1 in a STANDBY state (admitting no new requests while keeping resources valid) until either recovery is needed or the retention window expires. The controller must then have an explicit mechanism to reactivate STANDBY after readiness/data-compatibility guards; never attempt to call `activate` on an already CLOSED Generation.

## 13. Resource Cleanup Checklist During Real Version Swaps

| Moment | Mandatory check | Symptom of failure |
| --- | --- | --- |
| Before switch | v2 prepared, startup/health OK; v1 still ACTIVE | Activating v2 before dependencies are ready |
| v1 request enters | Holds v1 lease, `inFlight(v1)` incremented | Request uncounted yet still using plugin |
| After switch | New routes go to v2; v1 is DRAINING | New requests still enter v1 or v1 closes early |
| While A is processing | `closeCalls(v1)=0`, v1 resources remain valid | File/loader/pool closed while in-flight remains |
| After A completes | `inFlight(v1)=0`; cleanup runs exactly once | Negative counter, double close, or lease leak |
| After cleanup | Old resources actually closed/terminated | Sockets/threads/JAR handles remain open |
| After repeated retire | No second cleanup occurs | `Resource.close` called again unexpectedly |
| After host shutdown | v2 stops admitting and drains before cleanup | Thread pool stays alive or v2 never closes |
| After many reloads | No unbounded retained listeners/ThreadLocals/loaders | Loaders, threads, or metaspace grow per deploy |

In production, every check should use a **generation ID**, not just a version label. The same v2 version could be loaded multiple times with distinct class loaders, artifacts/configs, and resource handles. Cleaning up the wrong generation can break requests in another valid session.

## 14. Failure Testing and Observability

### 14.1. Tests to put in CI

1. **In-flight swap**: worker holds v1, main activates v2, v1 does not close before release.
2. **Post-cutover admission**: new requests use v2; no references to v1 via active pointer.
3. **Concurrent acquire/cutover race**: both orderings are valid and never touch closed resources.
4. **Release exception path**: business handler throws; lease still releases in `finally`/`try-with-resources`.
5. **Double close lease**: inFlight never goes negative; cleanup never repeats.
6. **Retire while in-flight**: state stays DRAINING, `closeCalls=0`.
7. **Retire after in-flight=0**: cleanup triggers exactly once.
8. **Cleanup failure**: state becomes CLEANUP_FAILED, with appropriate metrics/errors and recovery workflow.
9. **Shutdown with in-flight**: stops new leases; waits for active tasks up to a deadline.
10. **Async future**: lease never releases before actual CompletionStage completion.
11. **Actual URLClassLoader/resource cleanup**: JAR handles, threads, and listeners close per lifecycle.
12. **Repeated deployments**: multiple v1→v2→v3 cycles do not grow retained references indefinitely.

### 14.2. Diagnosing lab failures

| Symptom | Where to check |
| --- | --- |
| `old-request` prints `v2:A` | Lease did not pin version, or worker acquired after cutover |
| `old-close-before-finish` > 0 | Premature cleanup; missing `inFlight` guard |
| `old-after-drain` stays DRAINING | Lease never released or `retirementRequested` not set |
| `old-close-count` equals 2 | Missing CLOSING transition under lock or bad retry lifecycle |
| `new-request` is not `v2:B` | active pointer did not switch or was read outside gate |
| Timeout at `Future.get` | Worker latch never released, deadlock, or hung task |
| `new-close-count` is 0 after shutdown | Active generation never retired or lease leaked |
| CLOSE called yet real resources stay busy | Stop hook incomplete; thread/callback holds resource |
| Class loader not GC'd after close | Strong references remain or GC hasn't run |
| Cannot roll back to v1 | v1 already CLOSED, no rollback window, or schema incompatible |

On timeouts, capture a **thread dump** while the process is stuck using `jcmd`/`jstack` as permitted by your environment. Look for threads holding `gate`, threads waiting on latches, threads running `close` with I/O or re-entering the router, and plugin locks. Never solve a deadlock by increasing sleep timers or calling `Thread.stop`.

### 14.3. Production-grade metrics

- `active_generation{plugin,tenant,instance}`, rollout epoch.
- `in_flight{plugin,generation}`, `oldest_in_flight_age`, and `drain_duration`.
- `requests_started/finished/failed{generation}`.
- `cleanup_attempts`, `cleanup_success`, `cleanup_failures`, `cleanup_duration{generation}`.
- `resources_open{type,generation}`, `plugin_threads_active`, `callback_registrations`.
- `loader_retirement_pending`, `classloader_retained_after_window` (sampled periodically).
- `version_switch_count`, `rollback_count`, and reasons.

Never emit raw request payloads, secrets, or arbitrary internal classpaths in metrics/logs. Bound metric cardinality if generation IDs are numerous so telemetry itself does not become a DoS vector.

## 15. Advanced Exercises and Completion Criteria

A complete practice path progresses through three levels:

### Level 1 — run the given scenario cleanly

**Mandatory:** Compile and run `PluginSwapLab.java`; obtain the exact stdout shown, confirming v1 resources never close before request A finishes and both v1 and v2 close once each. Explain verbally why CountDownLatch makes the result more reliable than `Thread.sleep`.

### Level 2 — test failure scenarios

**Mandatory for anyone deploying real plugins:** Build variants for premature close, missing release, double-close, shutdown while in-flight, and cleanup exceptions. Tests must detect each bug accurately via state, counters, or exceptions rather than merely checking whether the program exited. Never trigger real deadlocks on shared CI runners without timeouts or isolated processes.

### Level 3 — attach real resources and test lifecycles

Extend Generation to own a URLClassLoader, an executor, and a simulated event-bus registration. Passing requires:

- while v1 holds leases, none of v1's resources are closed;
- once leases/rollback windows drain, the executor is terminated, listeners are unregistered, and `loader.close()` succeeds;
- every resource closes once or per its documented idempotent contract;
- the host retains no unnecessary references to v1 after retirement;
- across many switch cycles, no stray threads or callbacks remain, JAR handles are released, and memory trends stay bounded.

**Pass/fail criteria must be grounded in each real resource**, never treating `System.gc()` or a cleared WeakReference within a fixed deadline as mandatory proof.

## 16. Summary Checklist

- [ ] At least two separate generations exist for two plugin loads/versions.
- [ ] In-flight requests hold a lease pinned to their selected generation.
- [ ] Acquire and activate coordinate atomically when reading routes/incrementing inFlight.
- [ ] Old generations stop admitting new requests before retirement.
- [ ] While `inFlight > 0`, old resources are never closed.
- [ ] Once `inFlight` hits 0 and retire is requested, close runs exactly once.
- [ ] Cleanup runs outside the routing lock with explicit failure states.
- [ ] Async callbacks, timers, and background tasks are accounted for in the lifecycle.
- [ ] Shutdown stops admission, drains requests, and cleans up the active generation.
- [ ] With real class loaders, close is not confused with immediate unloading/GC.
- [ ] If rollback is supported, old generations are retained intentionally and checked for data compatibility.
- [ ] CI tests cover races, exceptions, timeouts, repeated replacements, and resource leaks.

**Conclusion:** Safe plugin replacement requires **pinning requests with leases, switching routes atomically, waiting for in-flight drain, and cleaning up only the right generation at the right time**. The verified Java 17 program proves two seemingly conflicting goals can both hold: request A keeps using v1 after cutover while request B gets v2; v1 closes only after A returns its lease, and v2 cleans up on shutdown. This lays the groundwork for scaling to URLClassLoader/ModuleLayer and multi-plugin runtime extensibility, while real-resource checks, state compatibility, and rollback policies must still be engineered explicitly.

## Official References

- Java SE 17 — [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating thread order without sleeping.
- Java SE 17 — [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): managing workers and shutdown.
- Java SE 17 — [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): awaiting completion and handling timeouts.
- Java SE 17 — [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources.
- Java SE 17 — [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()` and limits of class loading/unloading.
- Java SE 17 — [AtomicBoolean](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): guarding one-time lease release.
- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion callbacks for asynchronous workloads.