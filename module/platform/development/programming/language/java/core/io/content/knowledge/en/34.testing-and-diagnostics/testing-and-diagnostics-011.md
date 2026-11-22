# Testing Events, Callbacks, and Concurrent Operations Deterministically in Java I/O

## 1. The Problem: Correct I/O, Flaky Tests

In Java I/O programs, many events do not happen at a fixed instant: `WatchService` receives directory changes, `CompletionHandler` signals read/write completion, thread pools run file tasks, or callbacks continue work after a channel finishes a partial transfer.

Tests for this kind of code easily become **flaky tests**: the same code and inputs pass sometimes and fail other times due to machine speed, thread scheduling, caches, OS behavior, or filesystem quirks. For instance:

~~~java
startAsyncCopy();
Thread.sleep(100);
assertOutputExists(); // Wrong: 100 ms does not prove the copy finished.
~~~

This is **buggy illustrative code**, not a standalone program. A fast developer laptop may finish in under 100 ms, while a heavily loaded CI runner may take longer. Increasing the sleep to 2 seconds only makes tests slower without establishing a real causal relationship.

**Deterministic testing** means asserting **well-defined states and completion conditions**, controlling the necessary synchronization points rather than treating elapsed sleep time as proof that work finished. Distinguish:

- **Logical ordering the test controls:** create inputs first, register callbacks, wait for a completion signal, then verify results.
- **Execution ordering chosen by the scheduler/OS:** which thread runs first, exact callback timing, or how events are coalesced. These are usually **not** things to assert rigidly.
- **Final-state correctness:** read/written bytes match, each request reports one terminal outcome, and no out-of-scope data is touched.
- **Concurrency properties:** tests deliberately induce critical interleavings and verify correctness when operations genuinely run concurrently.

After this lesson, you will be able to use `CountDownLatch`, `Future`, `CompletableFuture`, `CompletionHandler`, bounded timeouts, isolated temporary roots, and reliable `WatchService` testing strategies.

## 2. What Makes an Assertion Deterministic?

The right question when testing async I/O is not "Is the result there after 100 ms?" but "**What condition proves the operation has completed?**"

| Scenario | Flaky Assertion | More Reliable Check |
| --- | --- | --- |
| Asynchronous file write | Sleep 100 ms then `Files.exists` | Wait for callback/`Future` completion, then read and verify contents |
| Receiving a callback | `sleep` then check a counter | `CompletableFuture.get(timeout)` or `CountDownLatch.await(timeout)` |
| Two workers running together | Wait a few ms and assume parallelism | Use a latch/barrier confirming **both are ready** before proceeding |
| `WatchService` reports file creation | Rigidly assert exact `1` `ENTRY_CREATE` across all OSes | Unit-test parser with mock events; integration-test with state snapshots plus optional event observation |
| Processing socket data | One `read` must yield a whole message | Use framing, loop reads until full bytes arrive, wait for completion |
| Checking completion order | Callback A must always precede B | If business logic mandates order, enforce sequence/IDs and coordinate; otherwise assert result set |
| Testing timeouts | Wait forever to see if it hangs | Bounded deadline, clear failure reporting, and cleanup |
| Checking exceptions | Hope worker errors surface on the test thread | Collect errors via `Future.get`, completion, or test error collector |

**Determinism does not mean every thread runs in the exact same schedule every time.** We want *pass/fail* criteria to be independent of lucky scheduling, or to explicitly control the contention points under test.

## 3. Design Principles to Avoid Flaky Tests

1. **One scenario, one isolated resource scope:** create a dedicated temporary directory per test; never use shared fixed files.
2. **Explicit initial state:** set up files, queues, and buffers before emitting events or launching tasks.
3. **Named completion events:** e.g., `CompletableFuture<Void> saved` means "finished saving," not "called the save method."
4. **Bounded waits:** `get(5, TimeUnit.SECONDS)` or `await(5, TimeUnit.SECONDS)`; on expiration, fail the test and clean up resources.
5. **Assert only on synchronized data:** never read a `ByteBuffer` while I/O is pending, and never read a file before the writer confirms completion if the protocol requires it.
6. **Check actual byte counts:** a `completed(n, ...)` callback may report bytes for only **one** read/write step, not necessarily the full request.
7. **Separate unit tests of event logic from native event delivery:** logic under our control can be tested deterministically; `WatchService`/OS delivery has platform limits.
8. **Ensure terminal states on error paths:** callback errors must complete the future exceptionally rather than merely logging and leaving callers waiting forever.
9. **Close thread pools, channels, `WatchService`, and temp roots:** prevent leaked resources from polluting subsequent tests.
10. **Capture sufficient diagnostics on failure:** log request ID, offset, byte count, barrier state, cause, and wait time; never just print "assert failed."

Not every race condition manifests on a single run. Combine controlled ordering tests, stress tests, instrumentation, and invariant checks across different schedules.

## 4. `CountDownLatch`: Coordinating "Same-Phase Start" Instead of Sleeping

`CountDownLatch` is a countdown counter to zero; one or more threads can `await()` until enough `countDown()` calls occur. Once the counter reaches zero, waiting threads proceed.

Suppose two workers run:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

// Each worker:
ready.countDown();
if (!go.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Start signal timed out");
}
// Start the I/O work under test.

// Test thread:
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Workers not ready");
}
go.countDown();
~~~

This is an **illustrative snippet** requiring imports for `CountDownLatch` and `TimeUnit`; real workers must be launched from a thread pool. `ready` signals both workers reached the synchronization point; `go` releases them once setup is done.

**Important:** a latch does not force the CPU to run both workers at the exact same nanosecond. It creates an intentional starting gate so both *can contend* right after the same signal, without relying on `Thread.sleep`.

To avoid hanging when a worker never reaches the barrier:

- Every test `await` should have a timeout.
- If `ready.await` fails, still release `go` or cancel workers so they aren't stranded indefinitely.
- Use a thread pool with **enough workers**: a single-thread pool requiring two tasks to meet at a latch deadlocks/starves itself.
- Collect all outcomes via `Future.get(timeout)`; worker exceptions do not automatically surface on the test thread.

`CountDownLatch` is single-use. For repeated synchronization rounds, consider `CyclicBarrier` or `Phaser`, and be sure to handle broken barriers and timeouts.

## 5. `Future` and `CompletableFuture`: Await Outcomes, Do Not Guess State

A `Future<T>` retrieves a result or failure cause:

~~~java
Future<String> work = executor.submit(() -> "done");
String result = work.get(5, TimeUnit.SECONDS);
if (!"done".equals(result)) {
    throw new AssertionError("Unexpected result");
}
~~~

This is an **illustrative snippet** using an existing `ExecutorService executor`; import `Future` and `TimeUnit`.

`get(timeout, unit)` bounds how long the test thread waits. `TimeoutException` means **waiting** timed out, not necessarily that the worker stopped. `Future.cancel(true)` requests cancellation, yet an interrupted thread need not stop immediately if the task ignores interrupts.

`CompletableFuture<T>` fits well when bridging a callback into an awaitable completion signal:

~~~java
CompletableFuture<Integer> finished = new CompletableFuture<>();

// Success callback:
finished.complete(actualBytes);

// Failure callback:
finished.completeExceptionally(error);

// Test thread:
int actualBytes = finished.get(5, TimeUnit.SECONDS);
~~~

This is an **illustrative snippet** requiring `CompletableFuture` and `TimeUnit`; `error` holds the failure cause. `CompletableFuture` completes at most once: subsequent `complete` or `completeExceptionally` calls do not overwrite an already-published result.

**Visibility note:** receiving a result from `Future.get`/`CompletableFuture.get` provides a clean happens-before boundary for observing state published by the task. However, if other threads still mutate a shared buffer or collection, do not assume the entire system is quiescent; define ownership and completion scope clearly.

## 6. Testing `CompletionHandler` for Asynchronous I/O

Java NIO.2 uses callbacks:

~~~java
channel.read(buffer, fileOffset, attachment,
        new CompletionHandler<Integer, RequestState>() {
            @Override
            public void completed(
                    Integer n, RequestState state) {
                // One read completed: handle n and continuation condition.
            }

            @Override
            public void failed(
                    Throwable error, RequestState state) {
                // Complete the entire request exceptionally.
            }
        });
~~~

This is an **API illustration snippet**, not a standalone program. `channel` is an `AsynchronousFileChannel`, `buffer` is a `ByteBuffer`, `fileOffset` is a `long`, and `RequestState` is an application context type.

### 6.1. Do Not Equate One Callback with the Entire Request

Suppose the goal is reading 5 bytes from a file, yet the first callback returns 2 bytes:

- `n = 2` means 2 bytes were read in that single invocation.
- `ByteBuffer.position()` has already advanced by 2—**do not advance it a second time**.
- If the buffer still has space, initiate the next read with the file offset incremented by 2.
- Complete the outer request future only once all bytes arrive or when policy allows early EOF.

When `n == -1` on a read, EOF was reached. If the request needed remaining bytes, fail with `EOFException`. For `n == 0`, distinguish a full buffer, provider quirks, or zero progress; stable-file tests can fail explicitly rather than hot-retrying.

### 6.2. Test Both Success and Failure Paths

For callback logic you own, verify:

- `completed` handles positive byte counts properly.
- `failed` terminates the request with an error and still runs cleanup.
- On partial completion, code triggers the next read or accumulates bytes correctly.
- A late or duplicate callback **does not** cause duplicate business processing.
- Callback errors are not swallowed, and the test thread receives the cause via the future.

**Never invoke a real channel's callback manually and claim you tested kernel async I/O.** For unit-testing logic, extract a `readAsync` adapter or inject a fake completion source to drive the handler deterministically. For integration tests, use real channels and await via futures/latches without asserting specific thread names or absolute callback timestamps.

## 7. `WatchService`: Events Are Not the Target State

`WatchService` reports directory changes detected by the provider for registered directories. Common events are `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE`. `OVERFLOW` indicates events may have been dropped.

Certain behaviors **must not be asserted identically across all OSes and filesystems**:

- One write produces exactly one event.
- Modify events must follow create events in a fixed count or timing.
- A change from another machine over NFS/SMB must always arrive.
- A newly created file is completely written when `ENTRY_CREATE` arrives.
- Every `ENTRY_MODIFY` always means a business-meaningful content change occurred.

Accordingly, split tests into two categories:

| Test Type | Goal | Appropriate Assertions |
| --- | --- | --- |
| **Parser/reconciler unit test** | Verify code handles a known event sequence | Feed mock events with ordering, duplicates, `OVERFLOW`, invalid keys; assert resulting state |
| **Real-filesystem integration test** | Verify API/provider can register and detect changes in target environment | Use reasonable deadlines, record whether events arrived, always verify file snapshot; assert delivery only if the environment defines it as mandatory |
| **NFS/SMB reliability test** | Evaluate changes made by another host | Two-host scenario measuring detection rate and latency against directory scans |
| **`OVERFLOW` recovery test** | Verify full-rescan policy when events are dropped | Inject an overflow signal into the app component without trying to overload native queues for a real overflow |

If a lesson creates `marker.txt` after registering a watcher, a portable test **can** assert the file actually exists with expected contents while merely observing event delivery. That is a deterministic test of **snapshot correctness**, not proof the watcher always delivers events.

### 7.1. A Bounded Event Polling Loop

~~~java
WatchKey key = watchService.poll(1, TimeUnit.SECONDS);
if (key != null) {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            requestFullRescan();
            continue;
        }
        // Mark path dirty, then inspect actual state.
    }
    if (!key.reset()) {
        // Registration invalidated; switch to recovery.
    }
}
~~~

This is an **illustrative snippet** with an open `watchService` and application-defined `requestFullRescan()`. `poll(timeout) == null` only means **no key was signaled** within the wait window; never conclude the directory did not change. Treat `event.context()` on entry events as a relative name and validate it before accessing the path.

### 7.2. Reducing Flakiness via Reconciliation

When an event arrives, treat it as a hint that "a path may be dirty." The reconciler scans and reads the actual file state. In tests, assert the data has the right version after the reconciler finishes; do not assert event counts.

To test idempotency, deliver the same `ENTRY_MODIFY` event twice and verify business logic produces only one final outcome or deduplicates by version/ID. To test overflow, inject an `OVERFLOW` signal and assert a full scan is scheduled, rather than expecting the OS to generate an overflow on cue.

## 8. Concurrency Testing: Invariants Matter More Than Scheduling

Suppose two tasks write different files in their own directories. A test may need to guarantee:

1. Both tasks **reached the ready point** before the test phase starts.
2. Both are released by the same coordination signal.
3. Each task writes only its own file without touching the other's.
4. Each business result is published only after that task completes.
5. Outcomes are retrieved via `Future.get` so worker exceptions propagate to the test thread.
6. On timeout or failure, the executor does not keep running indefinitely.

**Never assert "task A must finish before B"** unless the real program enforces that contract. After `go.countDown()`, whether the OS schedules A or B first is non-deterministic.

### Comparing Results Without Relying on Order

If tasks have IDs, collect results into a `Map<Id, Result>` and assert by ID rather than arrival order. To test "each ID is processed exactly once," use state tables and atomic/idempotent conditions rather than reading an unsynchronized `int` counter mutated by multiple threads.

When testing real data races, you may need to force rare interleavings with hooks/barriers **at specific logical points**—for example, both workers reading the old version before attempting to write, verifying compare-and-set or transactions. Simply increasing thread counts or stress iterations does not guarantee hitting the race.

## 9. Standalone Java 17+ Example: Events, Callbacks, and Two Coordinated Operations

The following example runs three checks in one dependency-free program:

- **Event:** registers `WatchService` on a temporary directory, creates `marker.txt`, and waits briefly to observe events. Events may or may not arrive; passing this section asserts **content snapshot**.
- **Callback:** reads all 5 bytes of `ready` via `AsynchronousFileChannel.read(..., CompletionHandler)` and bridges completion to `CompletableFuture`.
- **Concurrency:** submits two tasks to a 2-thread pool, using `ready` and `start` latches so both reach the starting gate before release. Each task creates its own temporary directory and writes a file with the same relative name.

**File `DeterministicIoTestDemo.java`:**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class DeterministicIoTestDemo {
    private static final int WAIT_SECONDS = 5;

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("deterministic-io-");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Path watched = Files.createDirectory(root.resolve("watched"));
            Path marker = watched.resolve("marker.txt");

            // Event is observed but does not decide test pass/fail.
            try (WatchService watch =
                         FileSystems.getDefault().newWatchService()) {
                watched.register(
                        watch,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                Files.writeString(
                        marker, "ready", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);

                WatchKey key = watch.poll(1, TimeUnit.SECONDS);
                boolean sawCreate = false;
                if (key != null) {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.ENTRY_CREATE
                                && marker.getFileName()
                                        .equals(event.context())) {
                            sawCreate = true;
                        }
                    }
                    key.reset();
                }

                // Variable used for diagnostic logic, not as a
                // pass criterion: provider may not emit an event.
                if (sawCreate) {
                    // In a real app, this could update metrics.
                }
            }

            boolean snapshotOk = "ready".equals(
                    Files.readString(marker, StandardCharsets.UTF_8));
            if (!snapshotOk) {
                throw new AssertionError("File snapshot mismatch");
            }
            System.out.println("Snapshot verified: true");
            System.out.println("Watch event required for pass: false");

            int callbackBytes = readFullyWithHandler(marker);
            System.out.println("Callback bytes read: " + callbackBytes);

            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);

            Future<String> alpha = pool.submit(
                    () -> runScenario(root, "alpha", "ONE", ready, start));
            Future<String> beta = pool.submit(
                    () -> runScenario(root, "beta", "TWO", ready, start));

            boolean bothReady = ready.await(
                    WAIT_SECONDS, TimeUnit.SECONDS);
            start.countDown(); // Release both even if setup failed.

            if (!bothReady) {
                throw new IllegalStateException("Workers did not get ready");
            }

            // Read by fixed ID: does not depend on which task finishes first.
            System.out.println("alpha result: "
                    + alpha.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("beta result: "
                    + beta.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("All checks passed");
        } finally {
            pool.shutdownNow();
            // Wait for workers to stop before deleting data in use.
            boolean stopped =
                    pool.awaitTermination(WAIT_SECONDS, TimeUnit.SECONDS);
            if (stopped) {
                deleteTree(root);
            } else {
                throw new IllegalStateException(
                        "Executor did not terminate; temp root retained");
            }
        }
    }

    private static int readFullyWithHandler(Path file)
            throws Exception {
        try (AsynchronousFileChannel channel =
                     AsynchronousFileChannel.open(
                             file, StandardOpenOption.READ)) {
            ByteBuffer data = ByteBuffer.allocate(5);
            CompletableFuture<Integer> finished =
                    new CompletableFuture<>();

            CompletionHandler<Integer, Long> handler =
                    new CompletionHandler<>() {
                private int total;

                @Override
                public void completed(Integer n, Long offset) {
                    if (n == -1) {
                        finished.completeExceptionally(
                                new EOFException("Incomplete payload"));
                        return;
                    }
                    if (n == 0) {
                        finished.completeExceptionally(
                                new IOException("Read made no progress"));
                        return;
                    }

                    total += n;
                    if (!data.hasRemaining()) {
                        finished.complete(total);
                        return;
                    }
                    long next = offset + n;
                    try {
                        channel.read(data, next, next, this);
                    } catch (RuntimeException error) {
                        finished.completeExceptionally(error);
                    }
                }

                @Override
                public void failed(Throwable error, Long offset) {
                    finished.completeExceptionally(error);
                }
            };

            channel.read(data, 0L, 0L, handler);
            int total = finished.get(WAIT_SECONDS, TimeUnit.SECONDS);
            data.flip();
            if (!"ready".equals(
                    StandardCharsets.UTF_8.decode(data).toString())) {
                throw new AssertionError("Callback payload mismatch");
            }
            return total;
        }
    }

    private static String runScenario(
            Path parent, String name, String payload,
            CountDownLatch ready, CountDownLatch start)
            throws Exception {
        Path ownRoot = Files.createTempDirectory(parent, name + "-");
        ready.countDown();

        if (!start.await(WAIT_SECONDS, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Start signal timed out");
        }

        Path file = ownRoot.resolve("same-name.txt");
        Files.writeString(
                file, payload, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);

        String actual = Files.readString(file, StandardCharsets.UTF_8);
        if (!payload.equals(actual)) {
            throw new AssertionError("Unexpected concurrent write");
        }
        return actual;
    }

    private static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attributes)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error) throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac -encoding UTF-8 DeterministicIoTestDemo.java
java DeterministicIoTestDemo
~~~

**Expected stdout when the provider supports `WatchService`, file I/O works, and tasks finish within the deadline:**

~~~text
Snapshot verified: true
Watch event required for pass: false
Callback bytes read: 5
alpha result: ONE
beta result: TWO
All checks passed
~~~

### Explaining What Guarantees Correctness

1. `Files.createTempDirectory` provides a private workspace for the entire example. Tasks `alpha` and `beta` each create separate subdirectories, so both write `same-name.txt` without colliding.
2. The watcher is registered **before** creating `marker.txt`. `watch.poll(1, SECONDS)` is a bounded observation, not a mandatory event for the snapshot test to pass. `key.pollEvents()` and `key.reset()` run when a key arrives.
3. `sawCreate` is purely diagnostic and omitted from stdout to keep expected output deterministic. In environment-specific tests, log it or record delivery metrics.
4. Actual existence and content assertions use `Files.readString`. The test does not depend on `ENTRY_MODIFY` counts or OS callback schedules.
5. `AsynchronousFileChannel` reads with explicit offsets. When a callback receives `n` bytes, `ByteBuffer.position()` has already advanced by `n`; if space remains, code continues at `offset + n`. `finished.complete(total)` runs only once all 5 bytes arrive.
6. `CompletableFuture.get(5, SECONDS)` is the synchronization point. Only afterward does the program `flip` the buffer and decode `"ready"`. I/O failures complete `finished` exceptionally.
7. `pool` has **two workers**, matching the two tasks waiting at `start`. `ready.await` proves both reached the barrier before the main thread releases `start`.
8. Even if one worker fails to reach setup in time, `start.countDown()` is still called before throwing so the other worker does not hang forever on the latch.
9. `alpha.get` and `beta.get` have timeouts and print in **fixed identifier order**, independent of actual thread completion order.
10. `finally` calls `shutdownNow()` then `awaitTermination` to avoid deleting files while workers are still active. If workers fail to stop in time, the demo deliberately retains the root and throws rather than deleting an in-use tree.
11. `Files.walkFileTree` deletes files before directories and does not follow symbolic links by default. Never run recursive deletion on an untrusted external path.

**Transparency on limitations:** this is a simple integration demo, not a guarantee that every production race will be detected. The 5-second timeout suits a demo; heavily loaded CI machines might exceed it even when the algorithm is sound. Real test suites should set deadlines matching environment SLAs, allocate appropriate test resources, and emit clear diagnostics on timeout. `finally` in this example can throw a cleanup/termination error overriding an earlier failure; production frameworks should preserve the primary error and attach cleanup errors as suppressed exceptions.

## 10. Testing Event/Callback Logic with Fakes to Control Ordering

So unit tests can **deliberately emit event A, B, duplicate A, then `OVERFLOW`**, do not wait for the OS to produce that schedule. Separate application logic from the event-receiving adapter.

Example interface:

~~~java
interface EventSink {
    void onCreated(Path relativePath);
    void onModified(Path relativePath);
    void onOverflow();
}
~~~

This is an **illustrative API** importing `Path`. The production `WatchService` adapter translates `WatchEvent` into calls on `EventSink`; unit tests can invoke it directly:

~~~java
sink.onCreated(Path.of("input.txt"));
sink.onModified(Path.of("input.txt"));
sink.onModified(Path.of("input.txt")); // Duplicate event.
sink.onOverflow();
~~~

This is an **illustrative snippet** assuming `sink` is an initialized test object; not standalone. Assertions should verify:

- `input.txt` is added to the "dirty" list only once if deduplication is implemented.
- `onOverflow()` flags a full reconciliation; subsequent events do not clear the rescan request.
- The consumer executes parse/I/O once a snapshot is ready; fake events do not magically materialize physical files.
- When content is unchanged, reprocessing an event creates no unwanted side effects (idempotency).

Similarly for `CompletionHandler`, separate result-handling logic into a component accepting an injectable completion source. Unit tests can emit `completed(2)` then `completed(3)`, or `failed(IOException)`, without forcing a real filesystem to produce a two-step partial read.

**Never use fakes to completely replace integration tests.** Fakes verify your logic; separate tests must verify the adapter works with real libraries, JDK, and providers in the deployment environment.

## 11. Races and Event Ordering: Testing What Actually Must Hold

### 11.1. Shared-File Read/Write Races

Two threads writing to the same file or an unsynchronized mutable `ByteBuffer` can produce schedule-dependent corruption. To test a synchronization strategy, define explicit invariants:

- Every record carries a unique sequence ID.
- When a writer publishes a new version, readers never observe a half-written record.
- No duplicate commits occur for the same request ID.
- Buffers are never read before the I/O operation finishes.
- No temporary file is ever published as complete after an error.

Place latches/barriers right around the contention window you want to test—for instance, both workers reading the old version before attempting compare-and-set. Once the barrier opens, only one valid commit is accepted. Never assert that thread `pool-1-thread-1` must win.

### 11.2. Lost Updates and Visibility

An `int count` variable incremented by two threads with `count++` can suffer **lost updates** because the operation is non-atomic. If a test counts callback invocations, use `AtomicInteger` or proper synchronization instead of unsynchronized reads/writes on a plain variable.

When a test waits on `CountDownLatch.await` and it succeeds, actions performed by the worker before `countDown` have a happens-before relationship with actions after `await` in the waiting thread per the concurrency memory model. However, actions **after** the worker calls `countDown` are not guaranteed to have finished when the waiter wakes up; place the signal only after all published state is complete.

### 11.3. Callbacks Invoked Multiple Times

If an adapter or application layer might fire duplicate signals, `CompletableFuture.complete` returning `false` after completion helps avoid publishing a result twice. Nevertheless, **a single-completion future does not protect side effects executed before `complete`**. If a callback wrote to a database twice before calling `complete`, duplication still happened. Enforce idempotency/deduplication before performing business side effects.

## 12. Scenarios to Test for Timeouts, Cancellation, and Failures

For every asynchronous operation, tests should cover independent failure paths:

| Scenario | Controlled Trigger | What Must Be Verified |
| --- | --- | --- |
| Callback succeeds | Fake handler emits `completed(n)` or real file I/O | Correct result and full byte count |
| Callback fails | Fake handler calls `failed(exception)` | Request future completes exceptionally; does not hang |
| Partial read | Fake returns 2 bytes first, remainder next | Offset/buffer update properly; incomplete data is not processed |
| Premature EOF | Use a file shorter than requested length | Reports missing data; does not report success |
| Wait timeout | Controlled delay via incomplete latch/future | `get(timeout)` throws timeout; cancellation/cleanup policy runs |
| Task failure | `Callable` deliberately throws an exception | `Future.get` throws `ExecutionException` wrapping the cause |
| Concurrent start | Two workers reach `ready` then receive `go` | No file collisions and invariants hold |
| Duplicate/overflow watch events | Inject fake event source | Deduplication and full rescan work per design |
| Native watcher drops events | Scenario on non-deterministic provider | Snapshot still reconciles or falls back to polling |
| Unresponsive worker | Fake task ignores interruption | Reports timeout; does not falsely claim "cleanup succeeded" |

**Time in tests** serves two distinct roles: (1) a **safety deadline** preventing infinite hangs; (2) **business time**, controlled via a fake clock/ticker when logic depends on "after 10 minutes." Never call `Thread.sleep(10 * 60 * 1000)` to test business-time rules.

With `ScheduledExecutorService`, test timer logic by injecting a mock scheduler/clock to trigger due tasks deterministically. When integration-testing a real scheduler, assert with generous bounds and deadlines—never demand millisecond-exact timer firing.

## 13. Resources and Cleanup Are Also Part of the Assertions

Correct output data paired with a leaked thread pool or open file handle still causes future test flakiness. Therefore:

- Each scenario creates its own temporary root; helpers delete only roots **they created and own**.
- Open streams, channels, and watch services with `try-with-resources` where appropriate.
- `ExecutorService` requires `shutdown`/`shutdownNow` and `awaitTermination`; on Java 17, do not rely on `try (ExecutorService e = ...)` syntax.
- Never delete a directory while tasks are still using it. Shut down and await termination before cleanup when races are possible.
- If callbacks are pending or tasks time out, cancel/close resources, await termination, or retain artifacts with an explicit warning.
- When cleanup fails, preserve the original error using suppressed exceptions or framework support.
- On Windows, open files/channels can prevent deletion. Close them before deleting.
- `WatchService` can throw `ClosedWatchServiceException` if closed while a thread is waiting; treat this as an expected lifecycle branch to handle explicitly rather than swallowing all exceptions.
- When a root contains symlinks, `walkFileTree` does not follow symlinks by default; still avoid trees modified concurrently by untrusted processes.

Tests should finish in a clean state: every task completed or canceled, every future observed, zero dangling handles, and temporary directories deleted (or retained with a clear reason).

## 14. How Do You Verify Stability?

A single pass only proves the test passed **that one time**. To increase confidence:

1. Run repeatedly under varying CPU/I/O loads and concurrency levels; track failure rates.
2. Test across Linux/Windows/macOS when portability matters; observe `WatchService` differences across local, NFS, and SMB filesystems.
3. Keep assertions **independent of tight latencies**: use deadlines generous enough for the environment, never "callback must finish in 20 ms" unless testing an explicit SLA.
4. Log traces with IDs, threads, offsets, actual byte counts, and barrier states on failure.
5. Never use stress/repeat runs as an excuse to skip controlled interleaving tests. Stress merely increases the odds of hitting a race; it does not explore every schedule.
6. Test errors like overflow, duplicates, early EOF, callback failures, and timeouts via fakes or fault injection instead of waiting for rare failures naturally.
7. Never let tests touch uncontrolled external systems (shared directories, fixed ports, real databases) without isolation.

### A Brief QA Matrix for Projects

| Test | Controlled? | Pass Criterion |
| --- | --- | --- |
| Unit: parser handles duplicate `ENTRY_MODIFY` | Yes, fake event source | Only one valid state update |
| Unit: callback reads 2 + 3 bytes | Yes, fake completion | Buffer/offset accurate, completes at 5 bytes |
| Integration: `AsynchronousFileChannel` | Partially; callback schedule set by provider | Future completes, actual bytes/content match |
| Integration: local `WatchService` | Limited; delivery set by provider | Snapshot matches; events observed and logged |
| Integration: two workers with start barrier | Controlled start gate; OS schedules afterward | Both results accurate, zero collisions |
| Stress: multiple workers reading/writing | Non-deterministic interleavings | Invariants and error rates hold across runs |
| End-to-end: files from NFS/SMB | File creation controlled; remote delivery uncontrolled | Final data valid, watcher + reconciliation, latency monitored |

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| `Thread.sleep` then assert file exists | Flaky on fast/slow machines | Await completion signal, then verify |
| `Future.get()` without timeout | Test can hang forever | `get(timeout, unit)` and cleanup |
| `CountDownLatch.await()` without timeout | Hangs if worker fails before `countDown` | `await(timeout, unit)` |
| 1-thread pool with a 2-task barrier | Starvation/deadlock | Enough workers in pool or redesign sync |
| Asserting exact `WatchService` event counts | Varies across OS/providers | Assert state or inject into parser |
| Assuming an event means the file finished writing | Can read partial files | Await producer completion or publish protocol |
| Treating one callback as the entire request | Fails on partial I/O | Track total bytes and offsets |
| Forgetting `CompletionHandler.failed(...)` | Test waits on future forever | `completeExceptionally` |
| Reading buffer while async read is pending | Races / incomplete data | Await completion and enforce ownership |
| Asserting callback runs on a hardcoded thread name | Providers/executors vary | Assert result; test executor separately if contracted |
| Sharing one file path across parallel tests | Collisions and false failures | Separate root per scenario |
| Plain counter variable across multi-thread callbacks | Lost updates / visibility bugs | `AtomicInteger`/locks and synchronization |
| Asserting task completion order without a contract | Outcomes fluctuate | Compare results by ID or as a set |
| Canceling a `Future` and assuming side effects rolled back | File may be partially written | Cleanup/staging and explicit cancel state |
| Cleaning up before workers stop | Races, file deletion failures | Shutdown, await termination, then delete |
| Testing only the success path | Errors/EOF/timeouts go untested | Test failures and recovery via fakes/injection |

## 16. Self-Check Questions

**Q1.** A thread calls `Thread.sleep(500)` before checking a file created by an async writer. Is that proof the writer finished?

**Answer:** No. Sleeping only pauses the thread for a duration; it does not confirm the callback, channel, or writer completed. Wait for a completion signal published by the writer.

**Q2.** Why use two latches, `ready` and `start`, when running two workers?

**Answer:** `ready` lets the test thread know both workers reached the setup point; `start` releases them together once everything is ready, reducing scheduler skew before contention.

**Q3.** `CompletableFuture.get(5, SECONDS)` times out. May you immediately reuse the `ByteBuffer` assigned to that I/O operation?

**Answer:** No. Timing out only stops waiting; the I/O operation may still be running and accessing that buffer. Close, cancel, and wait for termination per contract first.

**Q4.** `WatchService` emits two `ENTRY_MODIFY` events for one file. Should a test fail because it expected exactly one?

**Answer:** No, unless you are specifically testing a provider contract that guarantees it. Application logic should tolerate duplicates and reconcile against actual state.

**Q5.** You must verify the parser runs a full rescan on overflow, yet triggering a real overflow on CI is unreliable. What should you do?

**Answer:** Extract the parser/reconciler behind an event-accepting API and unit-test it by injecting an `OVERFLOW` event. Keep a separate integration test for the `WatchService` adapter.

**Q6.** Two parallel tasks return right results yet finish in different orders across runs. Is the test broken?

**Answer:** No, if business rules do not require ordering. Assert outcomes by request ID rather than completion timing.

**Q7.** A callback reads 2 bytes, and the next step reads 3 bytes. Should the next read reuse the old file offset?

**Answer:** No. With `AsynchronousFileChannel`, read at `oldOffset + 2`, while keeping the system-updated `ByteBuffer.position()`.

**Q8.** A test passes, yet its executor was never shut down and a thread is still writing a file. Can the test be considered fully isolated?

**Answer:** No. Background tasks can interfere with later tests or leak resources. Awaiting termination and controlled cleanup are integral parts of a reliable test.

## 17. Takeaways

- **Assert on completion signals and invariants**, not arbitrary sleep durations.
- **`WatchService` events are change hints, not guarantees of count, order, or file-write completion**; use fakes to test logic and snapshots/reconciliation to test state.
- **NIO.2 callbacks must handle partial I/O, failures, and buffer ownership**; bridge request state to `CompletableFuture`/`CountDownLatch` for bounded waits.
- **Concurrency tests need barriers right at contention points**, enough pool threads, and scheduler-independent assertions.
- **Cleanup must also be deterministic:** isolate resource scopes, shut down and await workers before deleting, and never drop asynchronous exceptions.
