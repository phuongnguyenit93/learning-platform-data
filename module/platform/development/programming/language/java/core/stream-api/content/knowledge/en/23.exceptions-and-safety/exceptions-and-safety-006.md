# Handling Source Mutation and `ConcurrentModificationException`

In the **Java Stream API**, writing `filter`, `map`, `reduce`, or `collect` relies on a key assumption: **the data source is not interfered with while the pipeline is traversing it**. If a lambda removes elements from an `ArrayList` while reading it, or another thread modifies a `HashMap` while a stream runs, the result can be `ConcurrentModificationException` (CME), missing data, inconsistent results, or a hard-to-reproduce bug.

This lesson belongs to the **Exceptions and Safety** chapter. The goal is not to “dodge the exception” with `try/catch`, but to understand the *non-interference* contract, distinguish source types, take snapshots at the right moment, and test results safely across mutable, snapshot, and concurrent sources.

## 1. Opening Example: Mutating a List While Traversing It

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4, 5));

// WRONG: mutating the very source that Stream is traversing.
values.stream().forEach(n -> {
    if (n % 2 == 0) {
        values.remove(n);
    }
});
```

One run may throw `ConcurrentModificationException`, yet there is no guarantee it throws on **every** run or at the same point. The root problem is that the code **modifies a collection while a pipeline is traversing that same collection**.

Two correct fixes depending on the goal:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5));

// Approach A: do not mutate source; return a new list (Java 16+).
List<Integer> odds = source.stream()
    .filter(n -> n % 2 != 0)
    .toList();

System.out.println(source); // [1, 2, 3, 4, 5]
System.out.println(odds);   // [1, 3, 5]

// Approach B: genuinely want in-place removal, outside a Stream traversal.
source.removeIf(n -> n % 2 == 0);
System.out.println(source); // [1, 3, 5]
```

**First design question:** must the source data stay intact for further use, or does the application actually want to mutate the original collection? Choose the API for this requirement before thinking about threads and performance.

## 2. What Does CME Signal, and What Does It Not Guarantee?

`java.util.ConcurrentModificationException` is a runtime exception indicating a collection or data structure detected an improper modification while being traversed. For many standard collections, iterators/spliterators are *fail-fast*: they detect structural changes based on the source's modification tracking state.

Key points to understand:

1. CME **can happen in a single thread**. The word “Concurrent” does not prove multiple threads are involved.
2. Fail-fast detection is generally **best-effort**, not a contract that every unauthorized modification is caught.
3. **Not throwing CME does not mean code is correct or thread-safe**. Races and inconsistent data can still occur.
4. CME **does not roll back** side effects already performed in the pipeline, such as database updates, file writes, or HTTP calls.
5. Catching CME and retrying **is not a substitute** for locks, snapshots, or immutable data design.

| Observation | What to examine |
| --- | --- |
| CME when using `ArrayList.stream()` | Structural modification likely happened during traversal. |
| CME when using `HashMap.entrySet().stream()` | Improper entry insertion/removal likely happened. |
| No CME yet wrong results | Possible data race, side effects, stateful mapper, or weakly consistent source. |
| `IllegalStateException` when reusing a Stream | The Stream was already consumed; a different issue from CME. |
| `UnsupportedOperationException` mutating result list | The list may be unmodifiable; do not confuse with CME. |

**Rule:** treat CME as **a signal to investigate a bug**, not as a consistency check or synchronization mechanism.

## 3. Structural Modification Differs from Changing Element Data

In `ArrayList`, `add` and `remove` alter list structure. `set(index, value)` usually replaces an existing slot without incrementing the structural modification counter.

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

names.add("Dung");    // Structural modification.
names.remove("An");   // Structural modification.
names.set(0, "Bao");  // Replaces value at an existing index.
```

With `ArrayList`, `set` usually **does not trigger fail-fast structural detection**, yet that **does not grant permission** for one thread to modify elements while another stream reads them. Readers can see a mix of old and new values, and without proper synchronization a data race can occur.

Mutating a field of a mutable object inside a `List` can also make `map`, `filter`, and `sorted` results unstable even though the list size never changes.

| Modification | Guaranteed to trigger CME? | Conclusion |
| --- | --- | --- |
| `ArrayList.add/remove` during traversal | Not guaranteed; often detected | Unsafe without coordinated design. |
| `ArrayList.set` during traversal | Usually not detected as structural | Can still produce wrong results or races. |
| Mutating an element's mutable field | Not necessarily | Still alters pipeline function semantics. |
| Adding/removing `HashMap` entries | May be detected | Do not use with unsynchronized concurrent writers. |
| `ConcurrentHashMap.put/remove` | Traversal supports concurrent changes per contract | May see partial updates, not a snapshot. |

## 4. The `non-interference` and `stateless` Contracts

Functions passed to most Stream operations must satisfy:

- **Non-interfering:** never mutate a non-concurrent data source while the pipeline runs.
- **Stateless:** never depend on shared mutable state that makes results vary with execution order/scheduling.
- **Semantically sound:** never use side effects to substitute for the result a terminal operation is meant to return.

```java
import java.util.List;
import java.util.Locale;

List<String> raw = List.of(" an ", " binh ");

List<String> normalized = raw.stream()
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .toList(); // Java 16+

System.out.println(normalized); // [AN, BINH]
```

`String` is immutable; these steps do not modify the source. This is the kind of pipeline that is easy to test and suitable for parallel execution when computation is large enough.

A **different** bug to distinguish is mutating a **shared result variable**:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 4);
List<Integer> output = new ArrayList<>();

// WRONG in parallel: multiple workers add concurrently to an un-thread-safe ArrayList.
input.parallelStream().forEach(output::add);
```

`output` is not the pipeline source, so this snippet does not necessarily throw CME. It is still wrong because mutating shared state unsafely breaks thread safety. Replace with:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> output = input.parallelStream()
    .map(n -> n * 2)
    .collect(Collectors.toList());
```

`collect` manages accumulators and combiners per contract, though **the returned list does not automatically become thread-safe** for subsequent concurrent updates.

## 5. Lazy Execution and Late Binding: Mutating Before the Terminal Operation

Intermediate operations like `filter` and `map` are normally **lazy**: building the pipeline does not necessarily traverse data yet. Many Spliterators, including `ArrayList`'s, are **late-binding**: binding to source state can be deferred until traversal starts.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> source = new ArrayList<>(List.of("A", "B"));

Stream<String> pipeline = source.stream()
    .filter(s -> !s.isEmpty());

source.add("C"); // Happens before the terminal operation.

System.out.println(pipeline.toList()); // [A, B, C] for this ArrayList.
```

For the `ArrayList` above, the addition before traversal is observed due to late binding. **Do not generalize** this to every source: a snapshot source or custom Spliterator may “lock in” its data at a different time.

What **must not be inferred**: “because Stream is lazy, I can mutate the source whenever I want.” Once traversal starts, mutating the source usually violates non-interference. And even though a collection can be traversed again, **a Stream object cannot be reused after a terminal operation**:

```java
Stream<String> once = source.stream();
long count = once.count();
// once.findFirst(); // Invalid: Stream has already been consumed.
```

## 6. Why Is Mutating the Source in `forEach`, `peek`, or `filter` Dangerous?

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// WRONG: mutating source inside consumer.
// numbers.stream().forEach(n -> numbers.remove(n));

// WRONG: mutating source inside predicate.
// numbers.stream().filter(n -> {
//     numbers.add(99);
//     return n > 0;
// }).toList();

// WRONG: side effect inside peek.
// numbers.stream().peek(n -> numbers.remove(n)).count();
```

The last example also touches **optimization**: for a sized source, `count()` can run without **calling `peek` per element**. Thus, a run “not hitting CME” may simply mean the callback never executed.

Choose the solution matching your goal:

| Goal | Appropriate API |
| --- | --- |
| Select matching elements, keep source unchanged | `stream().filter(...).toList()` or `collect(toList())` |
| Remove elements in place | `list.removeIf(...)` without competing Stream traversals |
| Replace elements in place | `list.replaceAll(...)` under proper access rules |
| Remove via sequential iterator | `Iterator.remove()` per iterator contract |
| Transform into a new version | `stream().map(...).toList()` |
| Process a stable snapshot | Take a safe snapshot, then stream over the snapshot |

Those collection-updating APIs also **do not make an `ArrayList` thread-safe** if another concurrent writer operates without coordination.

## 7. Multiple Threads and `parallelStream()`

A `parallelStream()` only lets the framework split work; it does not lock the source, create a transaction, or turn a mutable collection immutable.

```text
Reader Thread                      Writer Thread
-------------                      -------------
shared.stream().map(...)
      |
reads element A                    shared.add(newValue)
      |
continues reading or fails
```

If `shared` is an uncoordinated `ArrayList`, the result can be CME, unexpected read values, or other race symptoms. Trial runs and thread scheduling order do not prove correctness.

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();
for (int i = 0; i < 10_000; i++) {
    shared.add(i);
}

// Never run concurrently with an uncoordinated writer mutating shared:
// long sum = shared.parallelStream()
//     .mapToLong(Integer::longValue)
//     .sum();
```

Specifically, if a mapper has side effects such as sending an HTTP request, a later CME **does not undo already-sent requests**. Safe retries require idempotency, transactions, or compensation mechanisms, not merely `catch` and retry.

## 8. Different Source Types Have Different Traversal Semantics

Not every collection shares the same fail-fast behavior:

| Source | Behavior on modification during traversal | What must not be assumed |
| --- | --- | --- |
| `ArrayList` | Iterator/spliterator is usually *best-effort* fail-fast for illegal structural edits | CME is not a guaranteed race detector |
| `HashMap` | Iterator/spliterator can detect structural modifications | Not thread-safe against external writers |
| `List.of` / `List.copyOf` | Structure cannot be changed via list API | Mutable elements inside may still mutate |
| `CopyOnWriteArrayList` | Traverses a snapshot of the backing array | Misses new edits made after the snapshot |
| `ConcurrentHashMap` | Iterator/spliterator is **weakly consistent** | No multi-key atomic snapshot |
| Custom collection | Follows its published iterator/spliterator characteristics | Do not infer from class name or `parallel()` |

Two useful terms:

- **Snapshot traversal:** traverses a data version fixed at an API-defined point; writers can continue, yet that traversal sees an unchanging snapshot structure.
- **Weakly consistent traversal:** traversal may observe some concurrent updates and does not promise a single point-in-time view.

Never use the term “fail-safe” as a vague promise that a collection returns exact results under concurrent mutation.

## 9. Snapshots: The Default Path When Reports Need Consistency

When computation needs **a fixed dataset**, the straightforward path is making a structural copy and streaming over the copy.

```java
import java.util.ArrayList;
import java.util.List;

List<String> mutable = new ArrayList<>(List.of("A", "B", "C"));
List<String> snapshot = new ArrayList<>(mutable);

mutable.add("D");

System.out.println(snapshot.stream().toList()); // [A, B, C]
System.out.println(mutable); // [A, B, C, D]
```

If you do not need to mutate the snapshot and the source contains no `null`s, Java 10+ provides `List.copyOf`:

```java
import java.util.List;

List<String> snapshot = List.copyOf(mutable);
// snapshot.add("E"); // UnsupportedOperationException
```

**Important limitations:**

1. **Copying is itself a read.** Never copy from an `ArrayList` while a writer is mutating it without coordination.
2. **A list snapshot is usually a shallow copy.** If elements are mutable objects and another thread mutates an object, reading its fields can still observe changes.
3. `List.copyOf` **rejects null elements**; define a null-handling policy if the source allows them.
4. A snapshot of one Java list **does not automatically ensure** transactional consistency across multiple tables or systems.

When multiple threads can write, choose: locking during snapshot, pausing writers temporarily, a snapshot-based structure, or storage-layer snapshots/versioning.

## 10. `Collections.synchronizedList`: Synchronizing Traversal and Snapshotting

`Collections.synchronizedList` synchronizes individual wrapper methods, yet for iterators, spliterators, or Streams, traversal under concurrent writers still requires **external synchronization** per its contract.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<Integer> shared = Collections.synchronizedList(
    new ArrayList<>(List.of(10, 20, 30))
);

// All writers must update through the shared wrapper / same lock protocol.
List<Integer> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

// Run processing outside the lock so the lock is not held for long.
long sum = snapshot.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(sum); // 60
```

This pattern is safe only when **every writer follows the same lock/convention**, without holding a direct reference to the backing `ArrayList` and mutating it directly. You could hold `synchronized (shared)` across the whole terminal operation, yet a CPU- or I/O-heavy pipeline can **hold the lock too long** and block writers.

Taking a short snapshot under the lock and processing outside is usually better. Synchronizing a single operation does not make a chain of Stream operations **atomic**.

## 11. `CopyOnWriteArrayList`: Safe for Many Reads, Few Writes

`CopyOnWriteArrayList` creates a fresh backing array on writes and provides iterators/spliterators with **snapshot semantics**. With this source, an active traversal owns a snapshot unaffected by later adds/removes.

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Stream;

CopyOnWriteArrayList<String> events =
    new CopyOnWriteArrayList<>(List.of("E1", "E2"));

Stream<String> captured = events.stream();
events.add("E3");

System.out.println(captured.toList()); // [E1, E2]
System.out.println(events);           // [E1, E2, E3]
```

In return, writes via `add`/`remove`/`set` copy the array, costing CPU and memory when lists are large or write rates are high. Therefore, **do not replace every `ArrayList` with `CopyOnWriteArrayList` merely to avoid CME**.

This snapshot holds **element references**, without deep-copying mutable objects. When full immutability is needed, element types and publication workflows must also be designed appropriately.

## 12. `ConcurrentHashMap`: Concurrent Updates Allowed, No Multi-Key Snapshot

`ConcurrentHashMap` is designed for concurrent read/write access. Its iterators/spliterators are **weakly consistent**: they may observe some in-flight updates without throwing CME for normal concurrent operations.

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

ConcurrentHashMap<String, Long> balances =
    new ConcurrentHashMap<>();
balances.put("A", 100L);
balances.put("B", 200L);

// Another thread may be mutating balances.
Map<String, Long> observed = balances.entrySet().stream()
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue
    ));
```

In this example, `observed` contains what traversal **observed**, with no guarantee of reflecting balances at a single instant in time.

```text
At T1: A=100, B=200
Writer updates A then updates B
Reader may observe new A and old B
```

A sum from `balances.values().parallelStream().mapToLong(...).sum()` can reflect mixed points in time. When business logic requires a point-in-time closeout report, use proper snapshots/versioning/transactions.

`ConcurrentHashMap` also **disallows null keys and null values**. And using `Collectors.groupingByConcurrent` or `Collectors.toConcurrentMap` at the terminal **does not make a mutable `ArrayList` source safe**: the collector handles **how results are built**, not source mutation.

## 13. An Unmodifiable View Is Not a Snapshot

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> mutable = new ArrayList<>(List.of("A", "B"));

List<String> view = Collections.unmodifiableList(mutable);
List<String> snapshot = List.copyOf(mutable);

mutable.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`Collections.unmodifiableList(mutable)` only blocks mutation through **the view**, while the underlying list can still change and the view reflects those changes. `List.copyOf(mutable)` produces a **structural** snapshot unaffected by changes to the underlying list.

Likewise, `Stream.toList()` (Java 16+) returns an unmodifiable list **after the stream completes**; it does not prevent races occurring **while reading the source**.

## 14. Complete Java Example: Separating Updates, Snapshots, and Traversal

This Java 17+ program illustrates three distinct operations: producing a new result, mutating the source in place, and taking a snapshot for stable reads.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class SourceMutationSafetyDemo {
    private SourceMutationSafetyDemo() {}

    static List<Integer> positives(List<Integer> source) {
        return source.stream()
            .filter(n -> n > 0)
            .toList();
    }

    static void removeNonPositive(List<Integer> source) {
        source.removeIf(n -> n <= 0);
    }

    static List<Integer> safeSnapshot(List<Integer> synchronizedSource) {
        synchronized (synchronizedSource) {
            return List.copyOf(synchronizedSource);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers =
            new ArrayList<>(List.of(-2, -1, 0, 1, 2, 3));

        System.out.println(positives(numbers)); // [1, 2, 3]
        System.out.println(numbers); // [-2, -1, 0, 1, 2, 3]

        removeNonPositive(numbers);
        System.out.println(numbers); // [1, 2, 3]

        List<Integer> shared = Collections.synchronizedList(
            new ArrayList<>(List.of(10, 20, 30))
        );

        List<Integer> snapshot = safeSnapshot(shared);
        shared.add(40);

        System.out.println(snapshot); // [10, 20, 30]
        System.out.println(shared);   // [10, 20, 30, 40]

        long sum = snapshot.stream()
            .mapToLong(Integer::longValue)
            .sum();
        System.out.println(sum); // 60
    }
}
```

**Usage conditions:**

- `positives` does not mutate its input, yet **does not lock** it either. Callers must ensure the source stays stable during processing.
- `removeNonPositive` should run only when no competing traversal is active or under proper coordination.
- `safeSnapshot` is valid when the shared source follows **the same synchronization protocol**; every writer must use the proper wrapper/lock.
- `List.copyOf` requires no null elements and copies only structure/references.

## 15. Testing via Invariants, Not CME Timing

A test like “have two threads read/write an `ArrayList` and assert CME always occurs” is usually **flaky**: results depend on scheduling and best-effort fail-fast checks. Test **the safe design's contract** rather than relying on an exception being triggered.

JUnit Jupiter 5 example; place in the same package as `SourceMutationSafetyDemo` or add the appropriate imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class SourceMutationSafetyDemoTest {
    @Test
    void streamFilterDoesNotMutateSource() {
        List<Integer> input = new ArrayList<>(List.of(-1, 0, 1, 2));
        List<Integer> result = SourceMutationSafetyDemo.positives(input);

        assertEquals(List.of(1, 2), result);
        assertEquals(List.of(-1, 0, 1, 2), input);
    }

    @Test
    void removeIfMutatesOnlyWhenRequested() {
        List<Integer> input = new ArrayList<>(List.of(-1, 0, 1, 2));
        SourceMutationSafetyDemo.removeNonPositive(input);

        assertEquals(List.of(1, 2), input);
    }

    @Test
    void snapshotStructureRemainsStable() {
        List<Integer> shared = Collections.synchronizedList(
            new ArrayList<>(List.of(10, 20))
        );
        List<Integer> snapshot =
            SourceMutationSafetyDemo.safeSnapshot(shared);

        shared.add(30);

        assertEquals(List.of(10, 20), snapshot);
        assertEquals(List.of(10, 20, 30), shared);
        assertThrows(UnsupportedOperationException.class,
            () -> snapshot.add(40));
    }
}
```

These tests verify **deterministic** properties: filtered data is accurate, updates happen at the intended time, and snapshots stay unchanged when the source mutates structurally. In real concurrent apps, add multi-threaded tests with explicit synchronization protocols and stress tests; **never use CME count as the sole criterion**.

## 16. Performance and Memory Cost of Each Option

| Approach | Typical cost | When appropriate |
| --- | --- | --- |
| `filter(...).toList()` | Allocates result list holding selected elements. | Want a new result without mutating source. |
| `removeIf` on `ArrayList` | Iterates and updates structure per implementation. | Intentional in-place removal without competing traversals. |
| `new ArrayList<>(source)` | O(n) reference copy and memory allocation. | Want to isolate processing from later structural edits. |
| `List.copyOf(source)` | Creates unmodifiable list; may copy elements/references. | No nulls; want structural snapshot. |
| `Collections.synchronizedList` | Locking and contention between readers/writers. | Consistent single lock protocol exists. |
| `CopyOnWriteArrayList` | Writers may copy the whole array per update. | Read-heavy, write-rare workloads. |
| `ConcurrentHashMap` | Concurrent structure and update overhead. | Map needs concurrent reads/writes, weak consistency acceptable. |

Cost profiles are guidelines only; measure on real workloads. If the goal is **accurate reporting**, performance comparisons must include consistency costs such as snapshotting or locking. Never compare a snapshotted version against an unsynchronized version reading a mutating source while ignoring correctness and conclude the buggy version is “faster.”

With JMH benchmarks, measure snapshot cost and processing cost separately to understand components, alongside **end-to-end** measurements for system design decisions. Never state speedup numbers without real measurements.

## 17. Common Pitfalls

| Claim or practice | Why it is wrong | Fix |
| --- | --- | --- |
| “CME always happens if a list is modified.” | Fail-fast is best-effort only. | Design proper access, never rely on exceptions. |
| “With one thread, CME cannot occur.” | One thread can still mutate a source mid-traversal. | Separate mutation steps from Stream steps. |
| “`set` doesn't bump modCount so it's completely safe.” | Read data can change mid-pipeline. | Keep state stable or coordinate access. |
| “Catching CME and retrying is enough.” | Side effects may have run, races remain. | Snapshots/locks/transactions/idempotency. |
| “`parallelStream` handles thread safety.” | Parallel only splits work, never protects source. | Pick source and collector per contract. |
| “Concurrent collectors fix mutable sources.” | Collectors protect accumulation only, not sources. | Fix source read/write design. |
| “An unmodifiable view is a snapshot.” | Views can reflect underlying list changes. | Copy safely. |
| “ConcurrentHashMap gives a point-in-time report.” | Traversal is weakly consistent, not a multi-key snapshot. | Snapshots/versioning at business layer. |
| “CopyOnWriteArrayList has no cost.” | Every write can copy the array. | Choose based on read/write ratio. |
| “List.copyOf freezes every object.” | Only prevents list edits; mutable elements still change. | Use immutable values or deep copy when needed. |

## 18. Practice Exercises

**Exercise 1 — Non-interference.** Given an `ArrayList` with `[1,2,3,4]`, pinpoint the bug in `list.stream().forEach(n -> list.remove(n))`. Rewrite two versions: returning a new list and removing in place with `removeIf`.

**Exercise 2 — Lazy and late-binding.** Create a stream from an `ArrayList`, add an element before the terminal operation, and observe the result. Explain why this does not allow adding/removing **while traversal is running**.

**Exercise 3 — Replacing values.** Call `set(0, ...)` while another thread reads the list. Why might no CME occur while the data being read is still inconsistent?

**Exercise 4 — View vs. snapshot.** Create `Collections.unmodifiableList(source)` and `List.copyOf(source)`, then add an element to `source`. Predict both outputs and explain the difference.

**Exercise 5 — Synchronized snapshot.** Write a helper taking a snapshot from `Collections.synchronizedList` inside `synchronized (shared)`, then run statistics outside the lock. When does this pattern become unsafe?

**Exercise 6 — Copy-on-write.** Obtain a Stream from `CopyOnWriteArrayList`, add an element, then run the terminal operation. Compare with `ArrayList` and explain the cost under heavy writes.

**Exercise 7 — Concurrent map.** Observe a `ConcurrentHashMap` while a writer updates multiple keys. Why might a stream not throw CME yet still fail to produce a transactional snapshot?

**Exercise 8 — Testing.** Replace a timing-dependent `assertThrows(ConcurrentModificationException.class, ...)` test with deterministic tests checking accurate filtering, stable snapshots, and properly timed updates.

**Exercise 9 — Transactions and side effects.** If a Stream writes to a DB while traversing a mutable source and hits CME mid-way, do previous DB writes roll back automatically? Propose a transaction/idempotency design.

**Exercise 10 — Performance comparison.** Design a benchmark comparing a stable `ArrayList`, snapshots from a list with writers, and `CopyOnWriteArrayList` across multiple read/write ratios. Draw conclusions only after all variants meet identical consistency requirements.

## 19. Pre-Use Checklist

- [ ] Know whether the source is immutable, fail-fast, snapshot, or weakly consistent.
- [ ] Never mutate the source inside `map`, `filter`, `peek`, or `forEach` lambdas.
- [ ] Distinguish structural changes, element slot replacements, and object-internal mutations.
- [ ] Never use CME as a synchronization mechanism or correctness test.
- [ ] Never depend on CME reliably firing in a test.
- [ ] Have an explicit policy when multiple threads read/write a source.
- [ ] If creating a snapshot, coordinate the copy step safely as well.
- [ ] With `synchronizedList`, ensure every writer obeys the same lock protocol.
- [ ] Understand `CopyOnWriteArrayList` snapshots and write/copy overhead.
- [ ] Understand `ConcurrentHashMap` weak consistency does not mean multi-key consistency.
- [ ] Never confuse unmodifiable views with structural snapshots.
- [ ] Never treat concurrent collectors as protection for mutable sources.
- [ ] Never reuse a Stream after a terminal operation.
- [ ] Never rely on `peek` for mandatory side effects.
- [ ] Test empty sources, nulls, and mutations before and during traversal.
- [ ] Where side effects or I/O exist, design transactions/retries/idempotency separately.
- [ ] Verify results against the business contract before optimizing performance.

**Key Takeaway:** `ConcurrentModificationException` is only a *best-effort* signal for certain illegal source mutations; it is **not** a guarantee of thread safety. With the Stream API, keep lambdas non-interfering, separate update phases from traversal phases, take coordinated snapshots when reports need stability, and choose concurrent collections only when their exact semantics fit. **Correct, consistent results matter far more than merely avoiding an exception.**

**References:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ConcurrentModificationException.html), [ArrayList](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ArrayList.html), [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html), [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).
