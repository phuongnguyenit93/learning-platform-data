# Checking Invariants and Data Loss Bugs in Java Concurrency

## 1. Why Check Invariants?

A multithreaded program can throw no exceptions, never deadlock, and still return wrong results: an update disappears, the same record is processed twice, item counts between pipeline stages do not match, or shared state violates business rules. Bugs often appear only when multiple threads interleave at hard-to-reproduce moments.

An **invariant** is a condition that must hold at well-defined verification points. In concurrency, that condition can be a property of **state** (total balance remains constant), **output** (no ID is lost), **operation history** (each successful operation takes effect exactly once), or **lifecycle** (every accepted task completes, is cancelled, or is recorded as incomplete).

Examples:

- Counter: after `N` successful increments, the result must be `initial + N`.
- Internal fund transfer: when transferring `x` from A to B succeeds, `A + B` must be preserved and no balance may be negative if rules disallow it.
- Data pipeline: after all producers/consumers have stopped, each accepted ID must have either exactly one processing result or an intentional, inspectable rejection status.
- Task queue: a task confirmed as accepted must not vanish between acceptance, processing, retry, and result recording.
- Cache or concurrent collection: the structure must not be corrupted and updates must follow the chosen semantics, even under contention.

**Lesson objectives:** build an oracle independent of the code under test, induce difficult interleavings using synchronization utilities, check for lost/duplicate data, avoid false measurements caused by inconsistent snapshots, and understand the limits of stress tests.

This lesson uses only general Java 17+ APIs (`java.util.concurrent`, `AtomicInteger`, locks, queues, and test harnesses). No framework dependencies.

## 2. Classifying Invariants Before Writing Tests

| Type | Example condition | Verification point |
| --- | --- | --- |
| Count conservation | `accepted = processed + pending + inFlight + rejectedAfterAccept` | At a consistent checkpoint; states must be mutually exclusive. |
| Value conservation | `balanceA + balanceB = initialTotal` | Inside the lock protecting the snapshot or when all transfers have stopped. |
| Non-negative / bounded | `stock >= 0`, `activeTasks <= capacity` | After each atomic operation or from a consistent snapshot. |
| No lost IDs | Every accepted input ID is present in the result set or has a recorded failure status. | After workers finish and the queue has drained. |
| No duplicate effects | An ID has its result recorded only once according to the required semantics. | Using an ID set and occurrence counters, or by observing the target system. |
| Ordering | Elements from a single source arrive in order if the contract requires per-source FIFO. | Compare history per key/partition; do not enforce total order when the API does not guarantee it. |
| Liveness / progress | Every valid task eventually completes under the stated assumptions. | With deadlines/timeouts, active task counts, and cancellation policies. |

Do not enforce a global invariant at **every moment between statements** if an operation only guarantees correctness at transaction boundaries. For example, transferring funds across two fields requires a shared lock so readers see an atomic snapshot; reading each field without synchronization can observe half a transaction and draw a false conclusion.

### Defining What "Data Loss" Means

Pin down the exact scope of `accepted`:

- **Not yet accepted:** a producer calls `offer` on a full queue and receives `false`; rejection may be valid if the contract allows it and the caller knows. It must not be silently recorded as accepted.
- **Accepted but not yet processed:** the item is in the queue or with a worker; it cannot yet be concluded lost.
- **Processed but not yet committed:** an in-memory result is not necessarily durable. If the application restarts, a retry may be needed.
- **Committed but not yet acknowledged:** a retry can cause the effect to repeat; this is a duplicate issue alongside data loss.
- **Intentionally discarded:** there must be a reason, counter, or dead-letter record; if the contract allows it, this does not count as unexplained loss.

In an in-memory-only pipeline, a test can prove that items are not lost **during the observed run**. It does **not** prove durability across power loss, process crashes, or writes to external systems. Those guarantees require separate storage/commit protocols.

## 3. Common Cause: Non-Atomic Read–Modify–Write

Consider:

```java
int current = counter;
counter = current + 1;
```

Two statements perform read, compute, and write. If two threads both read `7` before either writes, both can write `8`: two increments were requested, but the actual increase is only one unit. That is a **lost update**.

```text
                  Thread A                  Thread B
state = 7
                  read -> 7
                                            read -> 7
                  compute 8
                                            compute 8
                  write 8
                                            write 8
state = 8         (expected 9; one update was lost)
```

A `volatile` variable solves certain visibility and ordering requirements, but **does not make `counter++` atomic**. Certain atomic operations and locks ensure read–modify–write steps cannot interleave; choose based on the invariant that must be protected.

Correct approaches for an independent counter:

- `AtomicInteger.incrementAndGet()` or `AtomicLong.incrementAndGet()`: a single atomic read–modify–write step.
- `synchronized` / `ReentrantLock` wrapping the entire read–modify–write.
- `LongAdder`: suitable for high-contention statistics counters; `sum()` while updates are ongoing is not an atomic snapshot. Do not use it in place of atomics for algorithms requiring exact sequential increments at every instant.

## 4. Java 17+ Example: Controlled Lost Update Reproduction

A stress test that spawns multiple threads running `counter++` may accidentally produce the right result on some runs. To **reliably** demonstrate lost updates, the following example uses `CyclicBarrier` to force four threads to read the old value together before any thread writes. After each round, all write `old + 1`. The safe branch uses `AtomicInteger.incrementAndGet()`.

Create **`LostUpdateInvariantDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LostUpdateInvariantDemo {
    private static final int THREADS = 4;
    private static final int ROUNDS = 20;

    private static final class UnsafeCounter {
        volatile int value;
    }

    private static int forcedLostUpdates() throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CyclicBarrier allRead = new CyclicBarrier(THREADS);
        CyclicBarrier allWrote = new CyclicBarrier(THREADS);
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < ROUNDS; i++) {
                        int old = counter.value;  // Four threads read together.
                        allRead.await();          // Wait until all have read.
                        counter.value = old + 1;  // Four threads write together.
                        allWrote.await();         // Wait until round ends before next read.
                    }
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
            return counter.value;
        } finally {
            pool.shutdownNow(); // In case a worker fails or hangs.
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static int atomicUpdates() throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int t = 0; t < THREADS; t++) {
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < ROUNDS; i++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
            return counter.get();
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        int expected = THREADS * ROUNDS;
        int unsafe = forcedLostUpdates();
        int safe = atomicUpdates();

        System.out.println("expected=" + expected);
        System.out.println("unsafe=" + unsafe);
        System.out.println("atomic=" + safe);
        System.out.println("unsafeInvariant=" + (unsafe == expected));
        System.out.println("atomicInvariant=" + (safe == expected));
    }
}
```

Run commands:

```bash
javac LostUpdateInvariantDemo.java
java LostUpdateInvariantDemo
```

Output when both parts complete within the timeout:

```text
expected=80
unsafe=20
atomic=80
unsafeInvariant=false
atomicInvariant=true
```

**Why is `unsafe` always 20 in this example?** On every round, `allRead.await()` prevents any thread from writing before all threads have read the pre-round value. Because all threads write the same `old + 1` value and `allWrote.await()` closes the round, the result increases by exactly one per round instead of four. This is a **test that intentionally forces a bad interleaving**, not the natural race frequency in a real application.

**Why is `atomic` 80?** There are exactly `4 × 20` calls to `incrementAndGet()`; each call performs an atomic increment, and `Future.get(...)` waits for all tasks to complete. `Future.get` also provides a happens-before relationship between actions inside the task and code after `get` returns successfully.

A timeout or exception causes the run to fail; that case must not be interpreted as producing the output above. `shutdownNow()` only requests interruption; tasks must cooperate to stop. Both barriers in the example support interruption.

## 5. Checking for Lost/Duplicate Data with Stable Identifiers

Incrementing a counter to the expected total is not enough: one item might be processed twice while another disappears, and the total still matches the expectation. To catch that bug, each input needs a **unique ID** or stable business key; verify three independent properties:

1. **Coverage:** all accepted IDs appear in the valid result set.
2. **Multiplicity:** each ID has the expected processing/commit count per the contract (usually once).
3. **Count:** total results, total distinct IDs, and accepted count agree once the system stabilizes.

Example: input is `{1,2,3,4}`, output is `{1,2,2,4}`. `input.size == output.size == 4`, yet ID `3` was lost and `2` was duplicated. Checking only the total count misses the bug.

Use an oracle separate from the code path under test: the producer records a successful ID as soon as the contract confirms acceptance; the output side records the actual result after commit. Sharing a single buggy counter for both "expected" and "actual" can make a test pass cleanly yet mean nothing.

## 6. Java 17+ Example: Checking a Producer–Consumer Queue for Zero Lost Records

This example uses a bounded `ArrayBlockingQueue` to create backpressure. Three producers send a total of 1,500 distinct IDs; two consumers take and record the IDs. The test waits for **producers to finish first**, then sends each consumer a stop marker so remaining items in the queue are processed. After consumers finish, the test measures missing, duplicate, and accepted/processed counts.

Create **`PipelineInvariantDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PipelineInvariantDemo {
    private static final int PRODUCERS = 3;
    private static final int CONSUMERS = 2;
    private static final int PER_PRODUCER = 500;
    private static final int TOTAL = PRODUCERS * PER_PRODUCER;

    private record Message(int id, boolean stop) { }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(64);
        Set<Integer> seen = ConcurrentHashMap.newKeySet();
        AtomicInteger accepted = new AtomicInteger();
        AtomicInteger processed = new AtomicInteger();
        AtomicInteger duplicates = new AtomicInteger();
        ExecutorService pool =
                Executors.newFixedThreadPool(PRODUCERS + CONSUMERS);
        List<Future<?>> consumers = new ArrayList<>();
        List<Future<?>> producers = new ArrayList<>();

        try {
            for (int c = 0; c < CONSUMERS; c++) {
                consumers.add(pool.submit(() -> {
                    while (true) {
                        Message message = queue.take();
                        if (message.stop()) {
                            return null;
                        }
                        if (!seen.add(message.id())) {
                            duplicates.incrementAndGet();
                        }
                        processed.incrementAndGet();
                    }
                }));
            }

            for (int p = 0; p < PRODUCERS; p++) {
                final int producerId = p;
                producers.add(pool.submit(() -> {
                    for (int i = 0; i < PER_PRODUCER; i++) {
                        int id = producerId * PER_PRODUCER + i;
                        queue.put(new Message(id, false));
                        accepted.incrementAndGet();
                    }
                    return null;
                }));
            }

            // Continue only after all producers have completed.
            for (Future<?> f : producers) {
                f.get(10, TimeUnit.SECONDS);
            }

            // FIFO markers placed after all items already put into the queue.
            for (int c = 0; c < CONSUMERS; c++) {
                if (!queue.offer(new Message(-1, true),
                                 5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Failed to send marker");
                }
            }

            for (Future<?> f : consumers) {
                f.get(10, TimeUnit.SECONDS);
            }

            int missing = 0;
            for (int id = 0; id < TOTAL; id++) {
                if (!seen.contains(id)) {
                    missing++;
                }
            }

            boolean ok = accepted.get() == TOTAL
                    && processed.get() == TOTAL
                    && seen.size() == TOTAL
                    && duplicates.get() == 0
                    && missing == 0;

            System.out.println("accepted=" + accepted.get());
            System.out.println("processed=" + processed.get());
            System.out.println("distinct=" + seen.size());
            System.out.println("duplicates=" + duplicates.get());
            System.out.println("missing=" + missing);
            System.out.println("INVARIANTS_OK=" + ok);

            if (!ok) {
                throw new AssertionError("Pipeline violated invariant");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Run:

```bash
javac PipelineInvariantDemo.java
java PipelineInvariantDemo
```

Output when all tasks complete normally:

```text
accepted=1500
processed=1500
distinct=1500
duplicates=0
missing=0
INVARIANTS_OK=true
```

**Why can the test draw a conclusion at the end?**

- Each producer owns a non-overlapping ID range; `put` succeeds before `accepted` is incremented. `ArrayBlockingQueue.put` waits when the queue is full instead of silently dropping items.
- After `Future.get(...)` for all producers, no producer can add more records; only then does the test send two markers.
- The queue is FIFO with respect to items actually enqueued. Each consumer stops when it sees a marker; because markers are added after all records, no data items remain behind a marker. The two consumers can still finish processing at different times.
- `seen.add(id)` uses a concurrent set to detect previously seen IDs; `duplicates` records repeated processing. `processed` counts processing executions, while `seen.size()` counts distinct IDs.
- The test reads the final numbers only **after both consumers have stopped**, avoiding comparisons of counters not captured at the same instant while the system is still active.
- `Future.get` has a timeout so it does not wait forever if a producer/consumer fails or misses a stop signal. The `finally` block shuts down the executor created by the program itself.

**Limitations:** this program demonstrates an in-memory Java pipeline for this execution path. `processed.incrementAndGet()` is only an in-RAM measurement and does not prove durable writes to a database or external system. `ConcurrentHashMap.newKeySet()` stores all IDs, which is fine for bounded tests but may not suit very large production telemetry.

## 7. Writing Tests That Catch Bugs Instead of Relying on Luck

### 7.1. Use Synchronization Utilities to Create Contention Points

- `CountDownLatch`: bring multiple threads to a starting line, or wait for an operation to finish.
- `CyclicBarrier` / `Phaser`: force threads to hit specific phases to reproduce adverse interleavings.
- `Semaphore`: limit the number of threads entering a sensitive phase.
- `Future.get(timeout, unit)` and `ExecutorService.awaitTermination`: bound wait times and propagate worker errors back to the test.
- `AtomicBoolean` / `AtomicInteger`: safely record test events or state.

Synchronize on **meaningful events**, such as "both threads have read the old version" or "consumer has taken the item but not yet committed." A `Thread.sleep(100)` usually only increases the chance of an accidental race, does not guarantee the desired interleaving, and easily causes flaky tests in CI.

### 7.2. Keep a Negative Control

A test against lost updates should have at least:

- A broken implementation branch that the test can catch (`unsafeInvariant=false` in the example).
- A fixed implementation branch that meets expectations.
- Assertions showing **expected** computed from input data, not derived from the variable under test.

If the test still PASSES when `AtomicInteger.incrementAndGet()` is intentionally replaced with unsynchronized `value++`, the test likely lacks contention or has an insufficiently strong oracle.

### 7.3. Run Stress Tests and Vary Load Conditions

After barrier-based tests, run multiple iterations varying thread counts, queue capacity, batch sizes, CPU/I/O work, executor types, and cancellation timing. A fixed seed can be used when randomizing inputs to reproduce the same data; however, a fixed seed **does not guarantee the same thread schedule**.

Stress testing can **detect** bugs when it fails, but a thousand PASS runs do not prove no bad interleavings remain. For lock-free algorithms, atomics, or complex memory ordering, consider **JCStress** (a harness for testing concurrent/JMM behavior). For throughput/latency, **JMH** is for performance benchmarking, not a proof of correctness.

## 8. Multi-Variable Invariants and Consistent Snapshots

Suppose `balanceA=100`, `balanceB=100`. A transfer of 30 units requires:

```text
Before: A=100, B=100, total=200
After:  A= 70, B=130, total=200
```

If A and B are updated without protecting the entire transaction, another thread can read between the two statements and see a temporary total of only 170. Using separate `volatile` fields or separate `AtomicLong` instances for each field still **does not** make the pair of values an atomic snapshot.

Pattern for protecting coupled state (illustrative snippet inside a Java class):

```java
private final Object balanceLock = new Object();
private long balanceA = 100;
private long balanceB = 100;

public boolean transferAToB(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative amount");
    }
    synchronized (balanceLock) {
        if (balanceA < amount) {
            return false;
        }
        balanceA -= amount;
        balanceB += amount;
        return true;
    }
}

public long totalSnapshot() {
    synchronized (balanceLock) {
        return balanceA + balanceB;
    }
}
```

Here both updates and snapshots go through the **same** monitor. A test can call `totalSnapshot()` after each transfer (or concurrently from another thread) and verify the total equals 200, because no mid-transfer state is observable. For any other invariant rules such as "non-negative" or "within limit," the logic must be checked **within the same synchronization boundary**.

However, the invariant `A + B = 200` is **not sufficient**: code could update A/B incorrectly while preserving the sum. You also need to check the number of successful transfers, per-account deltas, error notifications, and result history. That is why a robust system needs **multiple complementary invariants**, each protecting an independent property.

When operations span a database, network service, or multiple processes, an in-JVM monitor cannot create a cross-system atomic transaction. That requires appropriate commit and consistency mechanisms at the storage/communication layer; thread-level Java testing is only one part.

## 9. Happens-Before, Visibility, and Test Observation

There are two distinct risks:

1. **Non-atomic updates:** `counter++` can lose updates even if the variable is `volatile`.
2. **Stale reads:** a thread is not guaranteed to see state written by another thread without an appropriate happens-before relationship.

Relationships that commonly help design correct tests:

- Releasing a monitor and another thread acquiring the **same monitor** establishes a happens-before relationship.
- Writing a `volatile` and reading that volatile variable follows JMM rules; however, volatile does not protect multi-field transactions.
- A call to `AtomicInteger.incrementAndGet` provides an atomic update and the memory semantics of the corresponding atomic operations.
- Actions in a task happen-before `Future.get` returns normally, per the `java.util.concurrent` contract.
- Actions before `CountDownLatch.countDown` happen-before actions after another thread successfully returns from `await` on that latch.
- `Thread.join` after a thread completes also establishes corresponding visibility.

Practical conclusion: **wait for tasks to finish using synchronization utilities** before comparing final state. If you only check after `Thread.sleep`, a comparison may read mid-flight state or lack a clear memory visibility relationship.

### In-Flight Snapshots Can Be Wrong Even When Each Counter Is Atomic

Suppose a producer does:

```java
queue.put(item);
accepted.incrementAndGet();
```

A monitoring thread reads `queue.size()`, `accepted.get()`, and `processed.get()` separately while other threads are still working. Those reads do not form an atomic transaction, so the conservation equation can temporarily drift.

Solution: stop/freeze at a checkpoint before reading values; or design a proper snapshot/version protocol; or only apply the invariant over a **time window with a defined tolerance**. `size()` on many concurrent collections is an observed metric, not transactional with counters on other objects.

## 10. Data Loss Bugs in Queues and Pipelines

Common bugs:

| Bug | Mechanism | How to check or fix |
| --- | --- | --- |
| Ignoring `offer` result | Queue is full, `offer` returns `false`, but caller assumes the item was accepted. | Check the `boolean`, explicitly record reject/drop, or use `put`/timed `offer` per contract. |
| Stopping consumers too early | Stop marker is sent before producers finish. | Wait for producers to finish, send one marker per consumer, wait for consumers to finish. |
| Two consumers process the same ID on retry | Side effect completed but ACK was lost; item is redelivered. | Deduplicate by ID and verify the actual side effect/commit, not just the count. |
| Dropping data on exception path | Consumer takes an item then throws before commit; item never returns to queue. | Record failure/retry/dead-letter status and include it in the conservation invariant. |
| Using non-thread-safe structures | `HashMap`/`ArrayList` modified concurrently without synchronization. | Choose a lock or concurrent collection, and verify atomicity of operation sequences. |
| `check-then-act` race | `if (!map.containsKey(k)) map.put(k,v)` is not a single atomic step. | Use `putIfAbsent`, `compute`, or a lock as required. |
| Shutdown without draining | Executor is shut down while queued tasks remain unprocessed. | Implement a protocol to stop accepting new work, drain, await, and check incomplete tasks. |
| Treating timeout as success | Worker hangs; test times out and compares partial counters. | Propagate timeout as a test failure; cancel/clean up workers and collect diagnostics. |
| Computing expected from output | The same bug affects both oracle and result, causing a false PASS. | Derive expected from inputs/contract or an independent reference implementation. |

**No loss** and **no duplicates** are separate goals. Retries reduce data loss on transient errors, but can increase duplicate processing. "Exactly once" for an external side effect usually requires combining stable IDs, transactions/deduplication, and an appropriate commit/ack protocol. An in-memory `ConcurrentHashMap` is not sufficient across process crashes.

## 11. Checking Ordering and Linearizability

When an API promises atomic operations, we care about **linearizability**: every completed operation appears to take effect at a single point between its invocation and return, consistent with the real-time order of non-overlapping operations.

Final-value invariants alone cannot prove linearizability. For example, two threads calling `getAndIncrement`: a final counter value of 2 does not prove each thread received a distinct return value consistent with a valid history.

Testing techniques that increase confidence:

1. Record each operation with ID, start time, end time, input, output, and error.
2. Use a monotonic clock or synchronized event order to establish reliable before–after relationships; do not rely on interleaved `println` output as a specification.
3. Compare small histories against a sequential specification model, allowing overlapping operations to reorder.
4. Combine final-state invariants with invariants on **return values** and history. Aggregating final state alone is insufficient.

For a concurrent FIFO queue, two producers calling `put` concurrently do not have a simple global order determined by source line order across two threads. Check only the guarantees the API actually provides: for instance, the queue delivers items in the order they were successfully enqueued, whereas the order among concurrent producer calls depends on the actual linearization/order.

## 12. Properly Testing Abnormal Termination Paths

A pipeline test that only runs the "happy path" cannot catch data loss under errors. Add scenarios with **explicit expected outcomes**:

- Queue full: is the item rejected or does it wait? Is it mistakenly marked accepted?
- Consumer throws an exception after taking an item, before recording the result: is the item retried or moved to a failed bucket? Is it silently lost?
- Timeout/interrupt while a producer is in `put`: increment accepted only if `put` actually succeeded; handle exceptions explicitly.
- Retry after ACK failure: does one ID produce two side effects?
- Shutting down the executor with work remaining: how many tasks are queued/running; which tasks were cancelled; is unresolved state logged?
- Multiple consumers: can they process the same ID concurrently? The test must check multiplicity too.
- Rare timing bugs: run stress tests repeatedly, logging seed/input/thread dumps on failure.
- Restart/process crash: requires proper integration tests and durable storage state; in-memory tests cannot substitute.

You can use **fault injection**: a test hook that intentionally pauses or fails right after "item taken," before "commit," or right after commit, before ACK. This makes the failure reproducible and verifies retry/dedup policies against the contract.

## 13. Diagnostic Tools

**Thread dumps and `jcmd`** help locate stuck threads, deadlocks, monitors, parked threads, or blocked I/O:

```bash
jcmd <pid> Thread.print -l
```

`<pid>` is the actual JVM PID. A thread dump reflects only the instant it was captured. Many `WAITING` threads may simply be waiting legitimately for work; inspect stacks and system state.

**Java Flight Recorder (JFR)** analyzes lock events, parks, allocations, thread scheduling, and GC. It helps find performance or hang causes; it **does not by itself prove** data integrity, because you still need an oracle and ID/state checks.

**JCStress** is suited for testing low-level concurrent behavior, memory ordering, and allowed/forbidden outcomes under the Java Memory Model; **JMH** is suited for benchmarking. Do not use high throughput as a substitute for an invariant test.

**Metrics, logs, and traces** support production observability:

- Count accepted/rejected/processed/failed/retried at well-defined update points.
- Track histograms of queue wait time, processing time, deadlines, and in-flight task counts.
- Attach a correlation ID to each item to investigate count mismatches.
- Analyze invariants only after identifying a consistent checkpoint or an aggregation method that accounts for telemetry lag.

## 14. Mistakes That Cause Tests to Miss Bugs

1. **Checking only total count:** output missing one ID while duplicating another still PASSES.
2. **Believing `volatile` fixes `counter++`:** visibility is not atomicity.
3. **Reading two synchronized variables under different locks or separately:** produces inconsistent snapshots and false positives.
4. **Using `Thread.sleep` to guarantee interleavings:** the scheduler makes no guarantees on your chosen millisecond delay.
5. **Not collecting errors from tasks:** `ExecutorService.submit` stores exceptions in `Future`; without calling `get`, the test may treat a failed worker as success.
6. **Waiting without timeouts:** a deadlocked test can hang CI indefinitely.
7. **Measuring performance instead of correctness:** a fast benchmark with a data race is still wrong.
8. **Using non-thread-safe collections as the oracle:** test counters/Sets can race themselves, making conclusions unreliable.
9. **Sending shutdown markers before producers finish:** consumers may exit while new data is still arriving.
10. **Not checking drop/retry contracts:** a valid rejection is misclassified as loss, or silent loss is miscounted as rejection.
11. **Treating a single PASS as proof of no race:** stress runs can miss bad interleavings.
12. **Limiting the problem to RAM when the system needs durability:** you must test the actual source/target commit and ACK boundaries.

## 15. Complete Invariant Test Checklist

Before writing test code, answer:

1. **Source of truth:** where are the accepted input set, expected state, or reference model built from?
2. **Boundaries:** at what exact moment is an operation considered accepted, committed, failed, rejected, or acknowledged?
3. **Invariants:** which count, value, distinct ID, multiplicity, order, and liveness conditions must always hold?
4. **Checkpoint:** does the test check when the system is quiescent, or use a consistent snapshot while running?
5. **Races to force:** which interleavings can cause bugs? Can they be forced with latch/barrier/phaser?
6. **Error paths:** have queue full, exceptions, timeouts, retries, interrupts, cancellations, and shutdowns been tested?
7. **Evidence data:** on failure, does the test log input/ID, expected, output, stack trace, and reproduction metadata?
8. **Cleanup:** have all Futures been `get`/cancelled and test-owned executors shut down?
9. **Fix verification:** does the test fail (red) on an intentionally broken implementation and pass (green) on the fix?
10. **Scope of conclusion:** does the test prove correctness within a single JVM on a specific schedule, or does it also cover crashes/restarts/remote commits?

### Practice Exercises

1. Remove `allRead` from `LostUpdateInvariantDemo` and run it multiple times. Explain why the unsafe result can vary or occasionally be correct: the bug still exists even when the test happens to PASS.
2. Modify `PipelineInvariantDemo`: in one producer, use `queue.offer(...)` without checking the result when the queue is full, then compare the accepted/delivered oracle. Pinpoint the exact moment an item is rejected. Then fix it by checking the `boolean` or using `put`.
3. Create a consumer that intentionally processes an ID twice and another that skips an ID; checking total count will not catch it, while distinct sets and missing/duplicates must catch it.
4. Write a transfer test between two accounts; check `totalSnapshot()` under a single lock protecting both fields, then remove synchronization to reproduce wrong results. Also test negative balances and failed transfers.

## 16. Summary

In Java concurrency, **invariant checking** turns an "occasionally wrong" bug into a data-provable question: how many operations were accepted, does the final state satisfy the conditions, which IDs were lost, which IDs were duplicated, and at which checkpoint was the observation made.

To catch lost updates, intentionally create meaningful interleavings with `CyclicBarrier` or `CountDownLatch` and compare against an independent oracle. To catch data loss in pipelines, check **the ID set, occurrence counts, and totals** after waiting for all workers to finish. When deeper confidence is needed, add fault injection, stress/JCStress tests, and verify commit/retry paths at the actual storage layer.

### Java API References

- [`java.util.concurrent` — Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)
- [`CyclicBarrier`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [`AtomicInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [`Future`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)