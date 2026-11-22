# Testing Events, Callbacks, and Concurrent Operations Deterministically in Java I/O

## 1. The Problem: Correct I/O Yet Flaky Tests

In Java I/O programs, many events do not happen at a fixed instant: `WatchService` receives directory changes, `CompletionHandler` reports read/write completion, thread pools run file tasks, or callbacks resume work after a channel finishes a partial transfer.

Tests like this easily turn into **flaky tests**: identical code and inputs sometimes pass and sometimes fail due to machine speed, thread scheduling, caches, OS differences, or filesystem mechanics. For example:

~~~java
startAsyncCopy();
Thread.sleep(100);
assertOutputExists(); // Wrong: 100 ms does not prove the copy finished.
~~~

This is **broken illustrative code**, not a standalone program. A developer machine might finish in under 100 ms, while a heavily loaded CI runner may take longer. Raising the sleep to 2 seconds just slows tests down without establishing a real causal relationship.

**Deterministic testing** means verifying **explicitly defined completion states and conditions**, controlling necessary synchronization points rather than using wait durations as proof that work finished. Distinguish:

- **Logical order under the test's control:** prepare inputs first, register callbacks, await a completion signal, then assert results.
- **Execution order chosen by the scheduler/OS:** which thread runs first, exact callback timing, how events coalesce. These should normally **not** be hardcoded in assertions.
- **Final state correctness:** exact bytes read/written, each request reporting a single terminal result, no out-of-scope data.
- **Concurrency properties:** controlled tests forcing critical interleavings to confirm correctness when operations genuinely run concurrently.

After this lesson, you will be able to use `CountDownLatch`, `Future`, `CompletableFuture`, `CompletionHandler`, bounded timeouts, isolated temp roots, and reliable `WatchService` testing strategies.

## 2. What Makes an Assertion Deterministic?

The right question when testing async I/O is not "Is there a result after 100 ms?" but "**Which condition proves the operation finished?**".

| Scenario | Flaky-Prone Assertion | Stronger Verification |
| --- | --- | --- |
| Async file write | Sleep 100 ms then `Files.exists` | Await callback/`Future` completion, then read and verify contents |
| Receiving a callback | `sleep` then check counter | `CompletableFuture.get(timeout)` or `CountDownLatch.await(timeout)` |
| Two workers running together | Wait a few ms and assume parallelism | Use latch/barrier proving **both are ready** before releasing them |
| `WatchService` file creation event | Rigidly assert exactly 1 `ENTRY_CREATE` across all OSes | Test parser with fake events; integration test combines state snapshots with optional event observation |
| Socket data processing | One `read` must yield a full message | Use framing, loop until enough bytes arrive, and await completion |
| Checking completion order | Callback A must always precede B | If business contract requires order, enforce sequence/id; otherwise assert result set |
| Timeout testing | Wait forever to see if it hangs | Bounded deadline, fail clearly with timestamp, and clean up |
| Exception testing | Worker error thrown directly onto test thread | Propagate error via `Future.get`, completion, or test error collector |

**Determinism does not mean every thread follows the same schedule on every run.** We make *pass/fail* outcomes independent of scheduling luck, or explicitly control the race points under test.

## 3. Design Principles to Prevent Flaky Tests

1. **One scenario, one isolated resource scope:** create a separate temp directory per test; never share hardcoded files.
2. **Clear initial state:** initialize files/queues/buffers before emitting events or launching tasks.
3. **Named completion signals:** e.g., `CompletableFuture<Void> saved` meaning "save completed", not "save method invoked".
4. **Bounded waits:** `get(5, TimeUnit.SECONDS)` or `await(5, TimeUnit.SECONDS)`; on expiration, fail and clean up resources.
5. **Assert only on synchronized data:** never read a `ByteBuffer` while I/O is pending, or read a file before the writer confirms completion when the protocol requires it.
6. **Check actual byte counts:** a `completed(n, ...)` callback may report bytes for **one** read/write step, not necessarily the entire request.
7. **Decouple event-logic unit tests from native event delivery:** logic you own can be tested deterministically; `WatchService`/OS delivery has platform limits.
8. **Guarantee terminal state on error paths:** callback errors must complete futures exceptionally rather than only logging and leaving callers waiting forever.
9. **Close thread pools, channels, `WatchService`, and temp roots:** prevent leftover resources from corrupting later tests.
10. **Capture sufficient failure diagnostics:** record request ID, offset, byte count, barrier state, cause, and wait duration—not merely "assert failed".

Not every race surfaces in a single run. Combine controlled-ordering tests, stress tests, instrumentation, and invariant checks across varied schedules.

## 4. `CountDownLatch`: Controlling "Simultaneous Start" Instead of Sleeping

`CountDownLatch` is a countdown counter down to 0; one or more threads can `await()` until enough `countDown()` calls occur. Once the count hits 0, waiting threads proceed.

Suppose two workers run concurrently:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

// Each worker:
ready.countDown();
if (!go.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Start signal timed out");
}
// Begin the I/O under test.

// Test thread:
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Workers not ready");
}
go.countDown();
~~~

This is an **illustrative snippet** requiring imports for `CountDownLatch` and `TimeUnit`; real workers must be launched from a thread pool. `ready` proves both workers reached the sync point; `go` releases them once setup completes.

**Important:** a latch does not force CPUs to run both workers on the exact same nanosecond. It creates an intentional starting gate so both *can contend* right after the same signal, without `Thread.sleep`.

To avoid hanging when a worker never reaches the barrier:

- Every test `await` should carry a timeout.
- Even if `ready.await` fails, release `go` or cancel workers so they aren't stranded forever.
- Use a thread pool with **enough workers**: a single-thread pool requiring two tasks at a latch deadlocks/starves itself.
- Collect all outcomes via `Future.get(timeout)`; exceptions inside workers do not automatically surface on the test thread.

`CountDownLatch` is single-use. For repeated sync rounds, consider `CyclicBarrier` or `Phaser`, understanding broken-barrier handling and timeouts.

## 5. `Future` and `CompletableFuture`: Awaiting Results Instead of Guessing State

A `Future<T>` retrieves a result or failure cause:

~~~java
Future<String> work = executor.submit(() -> "done");
String result = work.get(5, TimeUnit.SECONDS);
if (!"done".equals(result)) {
    throw new AssertionError("Unexpected result");
}
~~~

This is an **illustrative snippet** using a created `ExecutorService executor`; import `Future` and `TimeUnit`.

`get(timeout, unit)` bounds how long the test thread waits. `TimeoutException` means the **wait** timed out, not necessarily that the worker stopped. `Future.cancel(true)` requests cancellation, yet interrupted threads need not exit immediately if the task ignores interruption.

`CompletableFuture<T>` fits bridging callbacks onto an awaitable completion signal:

~~~java
CompletableFuture<Integer> finished = new CompletableFuture<>();

// Success callback:
finished.complete(actualBytes);

// Failure callback:
finished.completeExceptionally(error);

// Test thread:
int actualBytes = finished.get(5, TimeUnit.SECONDS);
~~~

This is an **illustrative snippet** requiring `CompletableFuture` and `TimeUnit`; `error` holds the failure cause. `CompletableFuture` completes only once: later `complete` or `completeExceptionally` calls do not overwrite an already published result.

**Visibility note:** receiving a result from `Future.get`/`CompletableFuture.get` provides a sound synchronization point for reading state published by the task. However, if other threads are still mutating a shared buffer or collection, you cannot assume the whole system is quiescent; verify ownership and completion scope.

## 6. Testing `CompletionHandler` for Asynchronous I/O

Java NIO.2 uses callbacks:

~~~java
channel.read(buffer, fileOffset, attachment,
        new CompletionHandler<Integer, RequestState>() {
            @Override
            public void completed(
                    Integer n, RequestState state) {
                // One read finished: handle n and decide whether to read more.
            }

            @Override
            public void failed(
                    Throwable error, RequestState state) {
                // Fail the entire request.
            }
        });
~~~

This is an **API snippet**, not a standalone program. `channel` is an `AsynchronousFileChannel`, `buffer` is a `ByteBuffer`, `fileOffset` is a `long`, and `RequestState` is an application context type.

### 6.1. Do not equate one callback with the whole request

Suppose the goal is reading 5 bytes from a file, and the first callback returns 2 bytes:

- `n = 2` means 2 bytes were read in that single call.
- `ByteBuffer.position()` already advanced by 2—**do not advance it a second time**.
- If the buffer has space remaining, initiate the next read at `fileOffset + 2`.
- Complete the request-level future only once all required bytes arrive or the policy permits early EOF.

When `n == -1` on a read, EOF was reached. If more bytes were required, fail with `EOFException`. For `n == 0`, distinguish a full buffer, a special provider, or a no-progress condition; e.g., stable file tests may fail explicitly rather than spinning hot.

### 6.2. Test both success and failure paths

For callback logic you own, verify:

- `completed` processes positive byte counts accurately.
- `failed` terminates the request cleanly on error and still runs cleanup.
- On partial completion, code issues follow-up operations or accumulates bytes accurately.
- A late completion callback or duplicate event **does not** trigger duplicate business processing.
- Callback errors are never swallowed, and the test thread sees the cause via the future.

**Never invoke a real channel's callback manually and claim it verifies kernel async I/O.** For logic unit tests, extract a `readAsync` adapter or inject a fake completion source to invoke the handler deterministically. For integration tests, use real channels and await futures/latches, without asserting thread names or exact callback timing.

## 7. `WatchService`: Events Are Not Target State

`WatchService` reports provider-detected changes on registered directories. Common events are `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE`. `OVERFLOW` warns that events may have been dropped.

Behaviors you **must not assert identically across all OSes/filesystems**:

- One write produces exactly one event.
- Modify events follow create events in fixed count or timing.
- Remote changes over NFS/SMB always deliver events.
- A newly created file is completely written when `ENTRY_CREATE` arrives.
- Every `ENTRY_MODIFY` implies a meaningful business-content change.

Therefore, split tests into two categories:

| Test Type | Goal | Appropriate Assertions |
| --- | --- | --- |
| **Parser/reconciler unit tests** | Test handling of known event streams | Feed scripted ordered, duplicate, `OVERFLOW`, and invalid-key events; assert final state/output |
| **Real filesystem integration tests** | Verify API/provider registration and detection in target environment | Use reasonable deadlines, record whether events arrived, always verify file snapshot; assert delivery only if required by environment spec |
| **NFS/SMB reliability tests** | Measure cross-machine change detection | Multi-host test scenarios measuring detection rate and latency against directory scans |
| **`OVERFLOW` recovery tests** | Verify full-rescan policy when events drop | Inject an overflow signal into the app component; no need to overload the OS for a real overflow |

If a test creates `marker.txt` after registering a watcher, portable tests **can** assert the file exists with exact content while treating event arrival as diagnostic observation. That deterministically tests **snapshot correctness**, rather than asserting watcher delivery guarantees.

### 7.1. A bounded event polling loop

~~~java
WatchKey key = watchService.poll(1, TimeUnit.SECONDS);
if (key != null) {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            requestFullRescan();
            continue;
        }
        // Mark path dirty, then inspect real file state.
    }
    if (!key.reset()) {
        // Registration invalidated; trigger recovery.
    }
}
~~~

This is an **illustrative snippet** with an open `watchService` and application-defined `requestFullRescan()`. `poll(timeout) == null` means only that **no key was signaled** within the wait window; never conclude the directory didn't change. Treat `event.context()` on entry events as a relative name and validate it before accessing paths.

### 7.2. Reducing flakiness via reconciliation

When an event arrives, treat it as a hint that "this path may be dirty". The reconciler scans and reads actual file state. In tests, assert the data has the right version once the reconciler signals completion; never assert event counts.

To test idempotency, deliver the same `ENTRY_MODIFY` event twice and verify business logic produces one final outcome or deduplicates by version/id. To test overflow, inject an `OVERFLOW` signal and assert a full scan is scheduled, rather than trying to make the OS generate overflow on cue.

## 8. Concurrency Testing: Invariants Matter More Than Schedules

Suppose two tasks write distinct files in separate directories. A test may need to ensure:

1. Both tasks **reached the ready point** before starting the phase under test.
2. Both are released by the same coordination signal.
3. Each task writes only its own file; neither touches the other's file.
4. Business outcomes publish only after the task completes.
5. Results are collected via `Future.get`, surfacing worker exceptions onto the test thread.
6. On timeout or failure, the executor is not left running indefinitely.

**Never assert "task A must finish before B"** unless the real program contract enforces that order. After `go.countDown()`, whether the OS runs A or B first is non-deterministic.

### Comparing results independent of completion order

If tasks carry IDs, collect outputs into `Map<Id, Result>` and assert by ID rather than arrival order. To test "each ID processed exactly once", use a state table and atomic/idempotent conditions instead of an unsynchronized `int` counter mutated by multiple threads.

When testing genuine data races, you sometimes must force rare interleavings using hooks/barriers **placed at exact logic points**. For instance, both workers read an old version before both attempt to write, verifying compare-and-set or transaction semantics. Merely adding threads or load does not guarantee hitting the race.

## 9. Standalone Java 17+ Example: Events, Callbacks, and Two Coordinated Operations

This example runs three checks in one program with no external libraries:

- **Events:** registers a `WatchService` on a temp directory, creates `marker.txt`, waits briefly to observe an event. The event may or may not arrive; passing verifies the **content snapshot**.
- **Callback:** reads all 5 bytes of `ready` via `AsynchronousFileChannel.read(..., CompletionHandler)` and bridges completion onto a `CompletableFuture`.
- **Concurrency:** submits two tasks to a 2-thread pool, using `ready` and `start` latches so both reach the starting gate before signaling. Each task creates its own temp subdirectory and writes a file with the same relative name.

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

                // Variable used in diagnostics, not as a pass criterion:
                // provider might not emit the event.
                if (sawCreate) {
                    // Real apps could update metrics here.
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
            start.countDown(); // Release both even if setup fails.

            if (!bothReady) {
                throw new IllegalStateException("Workers did not get ready");
            }

            // Read by fixed ID: independent of which task finished first.
            System.out.println("alpha result: "
                    + alpha.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("beta result: "
                    + beta.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("All checks passed");
        } finally {
            pool.shutdownNow();
            // Wait for workers to stop before deleting active data.
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

Run with JDK 17 or newer:

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

### Explaining what guarantees correctness

1. `Files.createTempDirectory` provides an isolated area for the entire demo. Tasks `alpha` and `beta` also create separate subdirectories, allowing both to write `same-name.txt` without collision.
2. The watcher is registered **before** creating `marker.txt`. `watch.poll(1, SECONDS)` is a bounded observation, not a mandatory event for snapshot verification to pass. `key.pollEvents()` and `key.reset()` run when a key arrives.
3. `sawCreate` is strictly diagnostic data, omitted from stdout to keep expected output deterministic. In environment-specific tests, you can log or record it as a metric to track delivery rates.
4. Assertions on existence and real content use `Files.readString`. The test does not depend on `ENTRY_MODIFY` counts or OS callback timing.
5. `AsynchronousFileChannel` reads at explicit offsets. When a callback receives `n` bytes, `ByteBuffer.position()` has advanced by `n`; if space remains, code continues at `offset + n`. Only after 5 bytes arrive does `finished.complete(total)` run.
6. `CompletableFuture.get(5, SECONDS)` acts as the synchronization point. Only afterward does the program `flip` the buffer and decode `"ready"`. I/O errors complete `finished` exceptionally.
7. `pool` has **two workers**, matching the two tasks waiting at `start`. `ready.await` proves both reached the sync point before the main thread releases `start`.
8. Even if a worker fails to reach setup in time, `start.countDown()` still fires before throwing. This prevents stranding the other worker on the latch forever.
9. `alpha.get` and `beta.get` enforce timeouts and print in a **fixed identifier order**, independent of actual thread completion order.
10. `finally` calls `shutdownNow()` then `awaitTermination` to reduce the risk of deleting files still in use by workers. If workers do not stop in time, the demo deliberately preserves `root` and throws rather than deleting an active tree.
11. `Files.walkFileTree` deletes files before directories and does not follow symbolic links by default. Never run recursive deletion on untrusted external paths.

**Transparent limitations:** this is a simple integration demo, not a tool guaranteeing detection of all production races. A 5-second timeout suits a demo; heavily loaded CI runners may exceed deadlines and fail even when the algorithm is sound. Production test suites need SLA-appropriate deadlines, proper test resources, and clear timeout diagnostics. `finally` in this demo could throw a cleanup/termination error masking an earlier failure; real frameworks should preserve the primary error and attach cleanup errors as suppressed exceptions.

## 10. Testing Event/Callback Logic With Fakes to Control Order

To unit test **deliberately injecting event A, B, duplicate A, and then `OVERFLOW`**, do not wait for the OS to produce that schedule. Decouple application logic from the event-receiving adapter.

Example interface:

~~~java
interface EventSink {
    void onCreated(Path relativePath);
    void onModified(Path relativePath);
    void onOverflow();
}
~~~

This is an **illustrative API** importing `Path`. The production `WatchService` adapter translates `WatchEvent`s into calls on `EventSink`; unit tests can invoke them directly:

~~~java
sink.onCreated(Path.of("input.txt"));
sink.onModified(Path.of("input.txt"));
sink.onModified(Path.of("input.txt")); // Duplicate event.
sink.onOverflow();
~~~

This is an **illustrative snippet** assuming `sink` is an initialized test instance; not standalone. Assertions should check:

- `input.txt` is queued as "dirty" only once if the application deduplicates.
- `onOverflow()` flags that full reconciliation is needed; subsequent events do not clear the rescan flag.
- Consumers run parse/I/O only when snapshots are ready; fake events do not magically materialize physical files.
- When current content hasn't changed, re-processing an event causes no unwanted side effects (idempotency).

Similarly with `CompletionHandler`, separate result handling into a component accepting an injected completion source. Unit tests can fire `completed(2)` then `completed(3)`, or `failed(IOException)`, without forcing a real filesystem to split reads into exact halves.

**Never use fakes to replace integration tests completely.** Fakes verify your own logic; separate tests must confirm adapters work with the real library, JDK, and provider in the target environment.

## 11. Races and Event Ordering: Testing What Actually Must Hold

### 11.1. Shared-file read/write races

Two threads writing to the same file or unsynchronized mutable `ByteBuffer` can produce schedule-dependent corruption. To test a synchronization strategy, define clear invariants:

- Each record carries a unique sequence ID.
- When a writer publishes a new version, readers never observe a half-written record.
- No duplicate commits for the same request ID.
- Buffers are never read before the I/O operation completes.
- No temporary file is ever published as final after an error.

Place latches/barriers right around the contended section under test; for example, both workers read the old version and then both attempt compare-and-set. Once the barrier opens, only one valid commit succeeds. Never assert that thread `pool-1-thread-1` must win.

### 11.2. Lost updates and visibility

An `int count` incremented via `count++` by two threads suffers **lost updates** due to non-atomic read-modify-write. When tests count callbacks, use `AtomicInteger` or proper synchronization instead of reading/writing an unsynchronized plain field.

When a test awaits a successful `CountDownLatch.await`, worker actions *before* `countDown` have a happens-before relationship with actions *after* `await` succeeds in the waiting thread per the concurrency memory model. However, actions **after** the worker calls `countDown` are not guaranteed finished when the waiter wakes; place the signal strictly after publishing the required state.

### 11.3. Callbacks invoked multiple times

If an adapter or layer can fire duplicate signals, `CompletableFuture.complete` returning `false` after completion helps prevent publishing a result twice. Nevertheless, **single-completion futures do not protect side effects executed before `complete`**. If a callback writes to a database twice before calling `complete`, duplicates still happen. Place idempotency/deduplication before business side effects.

## 12. Cases Required for Testing Timeouts, Cancellation, and Failures

For every asynchronous operation, tests need independent failure paths:

| Scenario | Controlled Trigger | What Must Be Verified |
| --- | --- | --- |
| Callback success | Fake handler fires `completed(n)` or real file I/O | Exact result and full byte count |
| Callback failure | Fake handler calls `failed(exception)` | Request future completes exceptionally; no endless wait |
| Partial read | Fake returns 2 bytes first, remainder next | Offset/buffer updated properly; incomplete payload not processed |
| Early EOF | File shorter than requested size | Reports missing-data error; never treats as success |
| Wait timeout | Controlled delay via uncompleted latch/future | `get(timeout)` throws timeout; cancel/cleanup policy runs |
| Task failure | `Callable` deliberately throws | `Future.get` throws `ExecutionException` wrapping cause |
| Concurrent start | Two workers hit `ready` then receive `go` | No file collisions and invariants hold |
| Watch duplicate/overflow | Inject fake event source | Deduplication and full rescan per design |
| Native watch drops event | Scenario on provider with unreliable delivery | Snapshot still reconciled or fallback polling runs |
| Non-responsive worker | Fake task ignores interruption | Reports timeout; does not report "cleanup succeeded" |

**Time in tests** serves two distinct roles: (1) a **guard deadline** preventing infinite hangs; (2) **business time**, controlled via a fake clock/ticker when logic depends on "after 10 minutes". Never call `Thread.sleep(10 * 60 * 1000)` to test business durations.

For `ScheduledExecutorService`, timer-logic tests can inject a fake scheduler/clock to trigger due tasks deterministically. When integration-testing a real scheduler, assert within generous tolerances and deadlines; never demand millisecond-exact timer firing.

## 13. Resources and Cleanup Are Part of the Assertion

Correct data output from a test that leaks thread pools or file handles still makes later tests in the suite flaky. Therefore:

- Each scenario creates its own temporary root; helpers delete only roots **they created and own**.
- Open streams, channels, and watch services with `try-with-resources` where applicable.
- `ExecutorService` requires `shutdown`/`shutdownNow` and `awaitTermination`; on Java 17, do not rely on `try (ExecutorService e = ...)` syntax.
- Never delete directories while tasks are still using them. Shut down and confirm termination before cleanup whenever races are possible.
- If callbacks remain pending or tasks time out, decide whether to cancel/close resources, wait for termination, or retain artifacts with an explicit warning.
- When cleanup fails, preserve the original error via suppressed exceptions or framework mechanisms.
- On Windows, open files/channels can block file deletion. Close them before deleting.
- `WatchService` can throw `ClosedWatchServiceException` when closed while a thread waits; handle this as a controlled lifecycle path rather than swallowing all exceptions.
- When a root contains symlinks, `walkFileTree` does not follow them by default; still avoid trees modified concurrently by untrusted processes.

Tests should finish in a clean, known state: all tasks completed/cancelled, all futures observed, no forgotten handles, and temp directories deleted or flagged with why they were retained.

## 14. How to Verify Stability

Passing once only proves a test passed **that one time**. To build confidence:

1. Run repeatedly under varying CPU/I/O load and concurrency levels; measure failure rates.
2. Test across Linux/Windows/macOS if portability is required; observe `WatchService` differences across local filesystems and NFS/SMB.
3. Keep assertions **independent of specific latencies**: use generous guard timeouts for the environment, never "callback must return within 20 ms" unless testing an explicit SLA.
4. Log traces with IDs, thread, offset, actual byte count, and barrier state on failure.
5. Never use repeat/stress runs as an excuse to skip controlled-interleaving tests. Stress raises the odds of hitting races, without guaranteeing full schedule coverage.
6. Test faults like overflow, duplicates, early EOF, callback failures, and timeouts using fakes or fault injection instead of waiting for rare glitches naturally.
7. Never let tests touch uncontrolled external systems (shared directories, fixed ports, live databases) without isolation.

### A short project QA matrix

| Test | Controlled? | Passes Based On |
| --- | --- | --- |
| Unit: parser handles duplicate `ENTRY_MODIFY` | Yes, fake event source | Only one valid state update |
| Unit: callback reads 2 + 3 bytes | Yes, fake completion | Buffer/offset correct, completes at 5 bytes |
| Integration: `AsynchronousFileChannel` | Partial; callback schedule set by provider | Future completes, exact bytes/content match |
| Integration: local `WatchService` | Limited; delivery set by provider | Snapshot matches; events observed and logged |
| Integration: two workers with start barrier | Controlled start gate; OS schedules afterward | Both results accurate, no collision |
| Stress: many workers reading/writing | Unfixed interleaving | Invariants and error rates across runs |
| End-to-end: processing files over NFS/SMB | Controls file generation only, not remote delivery | Final data accurate, watcher + reconciliation, latency monitoring |

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Proper Approach |
| --- | --- | --- |
| `Thread.sleep` then assert file exists | Flaky on fast/slow machines | Await completion signal, then verify |
| `Future.get()` without timeout | Tests can hang forever | `get(timeout, unit)` and cleanup |
| `CountDownLatch.await()` without timeout | Stuck if worker fails before `countDown` | `await(timeout, unit)` |
| 1-thread pool with barrier needing 2 tasks | Starvation/deadlock | Pool with enough workers or different sync design |
| Asserting exact `WatchService` event counts | Varies across OS/provider | Assert state or inject into parser |
| Assuming event arrival means file write finished | Risk of reading partial file | Await producer completion or publish protocol |
| Treating one callback as full request completion | Breaks on partial I/O | Track total bytes and offset |
| Forgetting `failed(...)` in `CompletionHandler` | Test waits on future forever | `completeExceptionally` |
| Reading buffer while async read is pending | Races / incomplete data reads | Await completion and enforce ownership |
| Asserting callbacks run on a hardcoded thread name | Varies across providers/executors | Assert results only; test executor separately if contracted |
| Sharing one file path across parallel tests | Collisions and false failures | Dedicated root per scenario |
| Plain counter incremented in multi-threaded callbacks | Lost updates / visibility bugs | `AtomicInteger` / locks and synchronization |
| Asserting uncontracted task completion order | Results fluctuate | Compare results by ID or set |
| Cancelling `Future` and assuming side effects rolled back | Partially written file may remain | Cleanup/staging and explicit cancel states |
| Cleaning up before workers stop | Races, file deletion failures | Shutdown, await termination, then delete |
| Testing only the success path | Unhandled error/EOF/timeout paths | Test failures and recovery via fakes/injection |

## 16. Self-Check Questions

**Question 1.** A thread calls `Thread.sleep(500)` before checking a file created by an async writer. Is this proof the writer finished?

**Answer:** No. Sleeping only pauses the thread; it does not confirm the callback, channel, or writer finished. Wait for a writer-published completion signal.

**Question 2.** Why are both `ready` and `start` latches needed when running two workers?

**Answer:** `ready` tells the test thread both workers reached setup completion; `start` releases them together once everything is ready, reducing scheduler skew before the contended moment.

**Question 3.** `CompletableFuture.get(5, SECONDS)` times out. Can you immediately reuse the `ByteBuffer` passed to that I/O operation?

**Answer:** No. Timing out only stops waiting; the I/O operation may still be running and accessing the buffer. Close/cancel/await termination per contract first.

**Question 4.** `WatchService` emits two `ENTRY_MODIFY` events for one file. Should the test fail because it expected one event?

**Answer:** No, unless you are testing a specific provider contract that guarantees it. Application logic should accept duplicates and reconcile real state.

**Question 5.** You must verify the parser triggers a full rescan on overflow, yet real overflows are hard to trigger on CI. What should you do?

**Answer:** Extract the parser/reconciler behind an event-accepting API and unit test it by injecting an `OVERFLOW` event. Keep a separate integration test for the `WatchService` adapter.

**Question 6.** Two concurrent tasks return accurate results yet finish in different orders across runs. Is the test broken?

**Answer:** No, if business logic does not require ordering. Assert results by request ID rather than completion timestamp.

**Question 7.** A callback reads 2 bytes, then the next reads 3 bytes. Should the next read reuse the old offset?

**Answer:** No. With `AsynchronousFileChannel`, read at `oldOffset + 2` while keeping the system-updated `ByteBuffer.position()`.

**Question 8.** A test passes, yet its executor was never shut down and a thread is still writing files. Is the test fully isolated?

**Answer:** Not yet. Background tasks can interfere with subsequent tests or leak resources. Awaiting termination and controlled cleanup are part of a reliable test.

## 17. Key Takeaways

- **Test against completion signals and invariants**, never arbitrary sleep durations.
- **`WatchService` events are change hints, not guarantees of count, order, or write completion**; use fakes for logic tests and snapshots/reconciliation for state tests.
- **NIO.2 callbacks must handle partial I/O, failures, and buffer ownership**; bridge request state to `CompletableFuture`/`CountDownLatch` for bounded waits.
- **Concurrency tests need barriers right at contended points**, adequately sized pools, and scheduler-independent assertions.
- **Cleanup must also be deterministic:** isolate resource scopes, shut down/await workers before deleting, and never let async exceptions get lost.
