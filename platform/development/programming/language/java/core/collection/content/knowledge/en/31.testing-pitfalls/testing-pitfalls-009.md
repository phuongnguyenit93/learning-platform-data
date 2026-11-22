# Testing Atomicity, Snapshots, and Weak Consistency Under Concurrency

> **Scope:** Java Core Collections — Testing and Pitfalls. This article focuses on how to design tests and choose pass/fail criteria for collections accessed and modified concurrently. Examples use Java 17 or later.

## 1. Three Different Contracts to Test

A collection supporting concurrent access does not mean that every sequence of operations in a program is atomic, nor does it mean that iterating over it will observe a single fixed state. Before writing tests, determine the exact contract promised by the API.

| Property | Question to Answer | Example | Test Criterion |
| --- | --- | --- | --- |
| **Atomicity** | Does an operation execute as an indivisible unit without interleaving interference? | `ConcurrentHashMap.merge` updating a single key | Total update count has no lost updates once all tasks complete |
| **Snapshot** | Does a reader observe a fixed version throughout an entire traversal? | `CopyOnWriteArrayList` iterator | An earlier iterator does not see elements added after the iterator was created |
| **Weak consistency** | Under concurrent writes, which changes is an iterator allowed to reflect? | `ConcurrentHashMap` iterator | No concurrent modification failure; every observed entry satisfies its invariant, without enforcing an exact element list |

**Key takeaway:** an atomic operation on individual keys does not produce an atomic snapshot of the entire map. A thread-safe iterator also does not mean the iterator returns the state of the map at a single point in time.

## 2. Foundations: Data Races, Happens-Before, and Linearizability

- **Data race:** multiple threads access the same data with at least one write operation without proper synchronization; results may depend on scheduling and memory visibility. Standard `HashMap` and `ArrayList` do not provide a safe contract for unsynchronized concurrent modification.
- **Happens-before:** a relationship that guarantees ordering and memory visibility between actions. For instance, operations prior to `CountDownLatch.countDown()` happen-before actions after the corresponding `await()` returns; task completion happens-before actions following a successful `Future.get()` in the waiting thread. Use these mechanisms so tests can validly read final outcomes.
- **Atomicity / linearizability:** an atomic operation can be reasoned about as taking effect at a single point between its invocation and return. When multiple calls overlap, the observed outcome must correspond to some valid sequential execution according to the operation's contract. Do not extrapolate this guarantee across multiple separate statements.
- **Visibility vs. atomicity:** `volatile` helps threads see updated values, but it does not turn `x++` into an atomic increment. `synchronized` protects an entire transaction only if every related read and write path acquires the same lock.

Non-atomic example:

```java
Integer old = counts.get("java");
counts.put("java", old + 1);
```

`ConcurrentHashMap.get` and `put` are both thread-safe when called individually, yet two threads can still both read `0` and both write `1`. To increment a counter for the same key, use `merge` or `compute` on `ConcurrentHashMap`, or use a dedicated counter value such as `AtomicInteger` or `LongAdder` when appropriate for the data model.

## 3. Testing Lost Updates with a Controlled Schedule

Simply launching two threads thousands of times and hoping a bug surfaces is a weak test: the race might never occur on the test machine. Instead, we construct a schedule that **forces both threads to read the same old value** before allowing either to write. Then we compare that against a proper `merge` operation.

Save as `LostUpdateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LostUpdateDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        counts.put("java", 0);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                jobs.add(pool.submit(() -> {
                    int old = counts.get("java");
                    bothRead.countDown();
                    allowWrite.await();
                    counts.put("java", old + 1);
                    return null;
                }));
            }

            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Không đủ hai lượt đọc");
            }
            allowWrite.countDown();
            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }
            System.out.println("get + put = " + counts.get("java"));

            counts.put("java", 0);
            jobs.clear();
            for (int i = 0; i < 2; i++) {
                jobs.add(pool.submit(() -> {
                    counts.merge("java", 1, Integer::sum);
                    return null;
                }));
            }
            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }
            System.out.println("merge = " + counts.get("java"));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac LostUpdateDemo.java
java LostUpdateDemo
```

Output when tasks complete normally:

```text
get + put = 1
merge = 2
```

Explanation:

1. `bothRead` ensures both tasks have read the value `0`. `allowWrite` opens only after both reads complete, so both `put` calls write `1`: one update is **reproducibly** lost.
2. `merge("java", 1, Integer::sum)` on `ConcurrentHashMap` atomically updates the `java` key; once both increments complete, the value must be `2`.
3. `Future.get` propagates task exceptions to the test thread and establishes the required happens-before ordering before asserting the final value. Always use timeouts so tests do not hang indefinitely.
4. `shutdownNow` is placed in `finally` to release the executor even if the test fails. When production code needs a graceful shutdown, prefer `shutdown` followed by an appropriate `awaitTermination`.

**Contract note:** the `merge` call above guarantees atomic update for *a single key*. It does not turn reading two keys and transferring a balance between them into an atomic transaction. If an invariant spans multiple keys, you must design locking, transactions, or an atomic immutable state reference covering the entire operation.

### When Testing a High-Volume Counter

If `T` threads each invoke `merge` `N` times on the same key, then after **all `Future`s complete successfully**, the final invariant is `count == T * N`. Be mindful of integer overflow with `int`; use `long` or `LongAdder` as needed. `LongAdder.sum()` is not an atomic snapshot while updates are still in flight; assert exact equality only after all writer threads have stopped. Do not use `ConcurrentHashMap.size()` or `isEmpty()` as proof of an exact instantaneous state while the map is being mutated concurrently.

## 4. Testing Snapshots: Which Version Is Being Traversed?

A snapshot is a stable view within the boundaries of its contract. A `CopyOnWriteArrayList` iterator holds a reference to the backing array at **the moment the iterator was created**, so subsequent element additions or removals do not alter the contents of that traversal. This iterator does not support `remove`, `add`, or `set`.

Save as `SnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

public class SnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> shared =
                new CopyOnWriteArrayList<>(List.of("A", "B"));

        Iterator<String> oldIterator = shared.iterator();
        shared.add("C");

        List<String> observed = new ArrayList<>();
        oldIterator.forEachRemaining(observed::add);

        System.out.println("Iterator cũ: " + observed);
        System.out.println("Danh sách mới: " + shared);

        AtomicReference<List<String>> published =
                new AtomicReference<>(List.of("A", "B"));
        List<String> before = published.get();

        published.updateAndGet(current -> {
            List<String> next = new ArrayList<>(current);
            next.add("C");
            return List.copyOf(next);
        });

        System.out.println("Snapshot cũ: " + before);
        System.out.println("Snapshot mới: " + published.get());
    }
}
```

```bash
javac SnapshotDemo.java
java SnapshotDemo
```

```text
Iterator cũ: [A, B]
Danh sách mới: [A, B, C]
Snapshot cũ: [A, B]
Snapshot mới: [A, B, C]
```

These two approaches address different requirements:

- **`CopyOnWriteArrayList`:** every mutation creates a new array version. Active iterators see the old array, making it suitable for workloads with frequent reads/traversals and infrequent writes. Write overhead and memory allocation grow linearly with the list size.
- **`AtomicReference<List<T>>` with an immutable list:** a reader acquires a single reference and retains it for the entire operation. A writer builds a new list and atomically swaps the reference; `updateAndGet` may retry its lambda under contention, so the lambda must be side-effect-free. Note that `List.copyOf` only makes the list structure immutable—it does not automatically make mutable elements inside the list immutable.

**Do not equate a snapshot with "any copy".** Calling `new ArrayList<>(sharedArrayList)` or `List.copyOf(sharedArrayList)` does not guarantee a consistent snapshot if a plain `ArrayList` is concurrently mutated without synchronization. When using `Collections.synchronizedList`, perform the copy **while holding the same lock** used by all writers:

```java
// Illustrative snippet: shared is created and accessed consistently through the wrapper.
List<String> shared = java.util.Collections.synchronizedList(
        new java.util.ArrayList<>());

// Writer threads use shared.add/remove and never touch the backing list directly.
List<String> stable;
synchronized (shared) {
    stable = List.copyOf(shared);
}
// Traverse stable outside the lock: the list structure will not change.
```

Holding the lock while creating a snapshot temporarily blocks writers. If you traverse `shared.iterator()` directly, you must hold the lock on `shared` **for the entire duration of the traversal** per the wrapper's contract. The iterator returned by `synchronizedList` is not itself a snapshot.

### What a Snapshot Test Suite Should Prove

1. Create an iterator or snapshot at a well-defined point.
2. Add, remove, or structurally modify the collection **after** that point.
3. Traverse the old iterator or snapshot and verify it matches the initial version.
4. Obtain a new iterator or snapshot and verify it reflects the updated state.
5. Clearly distinguish between "structural stability of the element list" and "deep immutability": if an element object itself has mutable state that gets modified, a structural snapshot does not automatically protect that element's internal state.

Never rely on waiting for another thread to "run long enough" to establish the snapshot point; use `CountDownLatch`, `Phaser`, or a barrier to deterministically control the exact order of iterator creation → write → traversal when the scenario requires determinism.

## 5. Testing Weakly Consistent Iterators

`ConcurrentHashMap` provides **weakly consistent** iterators: they may reflect some updates made after the iterator was constructed, are not required to reflect all of them, and do not throw `ConcurrentModificationException` merely because the map is modified concurrently. Observed entries may reflect states from different points in time. Consequently, a test asserting that "the iterator must return exactly [1, 2, 3, 4] while a writer is running" violates the contract.

Save as `WeakIteratorDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WeakIteratorDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<Integer, String> data = new ConcurrentHashMap<>();
        for (int i = 0; i < 1000; i++) {
            data.put(i, "v" + i);
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<?> writer = pool.submit(() -> {
                start.await();
                for (int i = 1000; i < 2000; i++) {
                    data.put(i, "v" + i);
                }
                return null;
            });

            Future<Integer> reader = pool.submit(() -> {
                start.await();
                int observed = 0;
                for (Map.Entry<Integer, String> entry : data.entrySet()) {
                    String expected = "v" + entry.getKey();
                    if (!expected.equals(entry.getValue())) {
                        throw new AssertionError("Sai bất biến entry");
                    }
                    observed++;
                }
                return observed;
            });

            start.countDown();
            writer.get(5, TimeUnit.SECONDS);
            int observed = reader.get(5, TimeUnit.SECONDS);
            if (data.size() != 2000) {
                throw new AssertionError("Writer chưa ghi đủ");
            }

            System.out.println("Đã duyệt hợp lệ: " + observed);
            System.out.println("Số phần tử cuối: " + data.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
```

The first output line **does not have a fixed count**; depending on thread scheduling, the reader may observe varying numbers of entries. The second line, printed after `writer.get` returns successfully and with no other writers active, is always:

```text
Số phần tử cuối: 2000
```

What this test verifies is: every entry **actually observed** has a matching key/value pair; the iterator does not fail due to concurrent insertions; and once all writers have finished, the final state can be asserted exactly. You must not treat the number of entries read during concurrent updates as a "snapshot size" or require it to equal `map.size()` measured at the same time.

Important considerations:

- Do not assume that all new modifications **must** appear, nor that all new modifications **must** be hidden.
- Do not use `ConcurrentModificationException` as a "race detector": fail-fast iterators of `ArrayList` or `HashMap` only make a best-effort attempt to detect concurrent modification and are not guaranteed to throw in every case; relying on them under a data race is fundamentally flawed.
- "No exception thrown" is a necessary criterion but not a sufficient one: you must still verify data invariants, domain outcomes, termination, and absence of lost updates.
- `ConcurrentHashMap` does not permit `null` keys or values. Do not carry over null-allowance test assumptions from `HashMap`.
- Each `ConcurrentHashMap` iterator is designed to be used by **one thread at a time**; separate threads may create their own distinct iterators over the same map.

## 6. Designing Test Oracles: Assert What Is Guaranteed, Do Not Guess the Schedule

A *test oracle* is the rule that determines whether an outcome is correct. In concurrent programs, many schedules are valid; the oracle must describe **invariants** or **the set of valid outcomes** rather than hardcoding an arbitrary execution schedule.

| Scenario | Valid Assertion | Common Flawed Assertion |
| --- | --- | --- |
| Two threads call `merge` on the same key, after calling `get()` on all `Future`s | Final value increases by exactly two | The two calls must execute in order: thread 1 then thread 2 |
| `CopyOnWriteArrayList` iterator created before adding `C` | Earlier iterator retains [A, B] | Earlier iterator sees `C` because the current list contains `C` |
| `ConcurrentHashMap` iterator while a writer inserts keys | Every observed entry satisfies its invariant; traversal does not fail due to structural changes | Number of observed entries must equal the final size or any fixed exact count |
| Structural snapshot containing mutable element objects | List of references remains stable | Every internal field inside each element object is automatically frozen |
| `Collections.synchronizedList` | All accesses go through the wrapper; traversal/copy occurs under the same lock | Merely calling `iterator()` through the wrapper without locking is sufficient |
| `ConcurrentHashMap.size()` during active writes | Value reflects a transient observation; assert exact count only after writers stop | `size()` is a linearizable snapshot of the entire map during concurrent writes |

If domain requirements demand a consistent read across the entire map—for example, verifying that "the sum of balances across all accounts equals a constant at a single point in time"—a weakly consistent iterator does not provide that snapshot. You must design a synchronization protocol, publish immutable versions atomically, or use storage-layer transactions. Never "fix" a test by forcing assertions beyond what the API contract guarantees.

## 7. A Reliable Concurrency Testing Workflow

1. **Explicitly define the invariant and atomicity boundary** before running tests. For example: "after all 8 writers finish, the total for a key is 80,000", or "a snapshot iterator created before an append does not see the append".
2. **Choose the collection matching the required contract.** `ArrayList` and `HashMap` require external synchronization for concurrent read-write access; `ConcurrentHashMap` provides concurrent access and weakly consistent iterators; `CopyOnWriteArrayList` provides snapshot iterators; `synchronizedList` wrappers require locking during iteration.
3. **Control contention points explicitly.** Use latches or barriers to synchronize thread startup or enforce deterministic interleavings. `Thread.sleep` is never proof that another thread has reached the expected execution point.
4. **Collect all results and failures.** Use `Future.get(timeout, unit)` and handle `ExecutionException`, `InterruptedException`, and timeouts appropriately. Assert final state only after confirming all writers have completed.
5. **Separate deterministic tests from stress tests.** Latch-driven tests reproduce a specific hazardous interleaving deterministically; stress tests run many schedules to broaden coverage but cannot prove the absence of races. When investigating low-level JVM interleavings, consider OpenJDK's `jcstress` tool.
6. **Guarantee cleanup.** Shut down executors, release barriers on error, and avoid thread leaks that hang the entire test suite. A timeout is a safety net to detect non-terminating tests, not independent proof of correctness.
7. **Keep assertions independent of machine speed.** Avoid relying on wall-clock timing to decide correctness, and never infer execution order from thread `println` log lines.

### Failure Classification Patterns

- **Lost update:** final total is smaller than the expected number of atomic operations → check whether code uses unsynchronized `get`-then-`put` sequences or `x++`.
- **Stale read:** a thread fails to observe an update despite a required happens-before relationship → check publication and synchronization first before suspecting the collection implementation.
- **Torn or inconsistent snapshot:** an aggregate report mixes states from multiple points in time → live traversal is likely being used where the domain requires a synchronized or immutable snapshot.
- **Flaky assertion:** test intermittently passes and fails because it enforces an unguaranteed iteration order or intermediate count → fix the test oracle to match the contract.
- **Unexpected exception:** verify the collection class, concurrent modification rules, comparator/key/value constraints, and whether a synchronized wrapper is being iterated outside its lock.
- **Hang:** barrier missing a party, two-way waiting, forgotten release/cleanup, lock ordering deadlock, or a remapping lambda performing blocking/hazardous work.

## 8. Key Pitfalls in Production Code

**Atomic map methods and side effects:** for `ConcurrentHashMap.compute`, `merge`, or `computeIfAbsent`, the supplied function must be short, simple, free of recursive updates to the same map, free of long-held locks, and must not rely on external side effects to cobble together a larger transaction. If an invariant spans multiple keys, the design itself must protect that multi-key invariant.

**Mutable value references:** a concurrent map only guarantees thread safety for map operations per its contract; mutating fields inside a `MutableValue` stored in the map requires its own synchronization mechanism. Neither a map snapshot nor `List.copyOf` automatically performs a deep copy of element values.

**Synchronized wrappers and backing objects:** once a collection is wrapped via `Collections.synchronizedList(backing)`, never continue mutating `backing` directly from another thread. Every access path must obey the same lock protocol, including copying and iteration.

**Fail-fast is not a thread-safety guarantee:** `ConcurrentModificationException` is a diagnostic indicator of improper collection usage in certain scenarios, not a complete concurrency test oracle or synchronization mechanism.

**Do not confuse weak consistency with snapshot isolation:** weakly consistent traversal is suitable for dashboards, caches, and approximate monitoring where state fluctuates continuously; when an exact consistent snapshot is required for auditing, reconciliation, or transactions, you must build an explicit snapshot boundary.

## 9. Self-Verification Exercises

1. Modify `LostUpdateDemo` to run 8 tasks, each incrementing a key 10,000 times using `merge`. Wait for all `Future`s and assert that the result is exactly 80,000. Replace `merge` with `get` + `put` to observe that failures **can** occur under stress; do not assume a buggy concurrent test will always fail without controlled interleaving.
2. Create an iterator over a `CopyOnWriteArrayList` before calling `remove`. Verify that the old iterator still sees the removed element while a new iterator sees the updated version. Call `oldIterator.remove()` and confirm that it throws `UnsupportedOperationException`.
3. Have a writer continuously insert elements into a `ConcurrentHashMap` while a reader traverses it with its own iterator; log the observed count to illustrate variation across runs, while keeping assertions strictly focused on key/value validity and the final state after joining threads.
4. Create an immutable list published via `AtomicReference`. Have multiple readers capture snapshots at different points and verify that each reader only observes the version it acquired; discuss the copy cost trade-offs.
5. Rewrite a flaky test that uses `Thread.sleep(20)` to wait for a writer. Replace the sleep with a latch or `Future.get` and explicitly state which happens-before edge makes the final assertion valid.

## 10. Summary and Official References

- **Atomicity:** test update operations and invariants strictly within the scope promised by the API; a sequence of individual atomic calls is not itself atomic.
- **Snapshot:** freeze the observed version either at iterator creation time or when publishing an immutable reference; test the exact timing of snapshot acquisition.
- **Weak consistency:** accept multiple valid traversal outcomes and assert invariants on each observed entry; never demand a full-collection snapshot that the API does not guarantee.
- **Good concurrency tests:** control schedules at critical contention points, propagate worker failures, enforce timeouts and resource cleanup, and assert final outcomes only after proper synchronization.

Java SE 17 Documentation:

- [`ConcurrentHashMap` — atomic methods and weakly consistent iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [`CopyOnWriteArrayList` — snapshot iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [`Collections` — synchronized wrappers and locking requirements during iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [`Future` — memory consistency and waiting for results](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
