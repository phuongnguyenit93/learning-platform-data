# Late Binding, Mutable Sources, and Fail-Fast Limits

In the **Java Stream API**, a pipeline is typically described using *lazy* intermediate operations like `filter` or `map` and only actually traverses data when encountering a terminal operation like `collect`, `forEach`, or `reduce`. Beneath many stream sources lies **`Spliterator<T>`**: the object supplying elements via `tryAdvance` and, when possible, partitioning work via `trySplit`.

When the source is a **mutable** collection, three easily confused questions arise:

1. When does the Spliterator **bind to the source's state**?
2. If the source changes after creating the stream, will the new elements be seen?
3. If the source is modified during traversal, is **fail-fast** guaranteed to throw `ConcurrentModificationException`?

The answer depends on the source and Spliterator contract, not solely on the pipeline being lazy. This article belongs to the **Spliterators and Custom Sources** chapter, focusing on *late binding*, the **non-interference** principle, `IMMUTABLE`/`CONCURRENT` characteristics, and the real limits of fail-fast detection.

## 1. Distinguishing Stream Creation, Binding, and Traversal

These three moments are not synonymous:

| Moment | What Happens | What **Cannot** Yet Be Inferred |
| --- | --- | --- |
| **Stream creation** | An object describes the pipeline or data source. | Elements have not necessarily been read, nor has the source been frozen. |
| **Binding** | The Spliterator establishes traversal state tied to the source, e.g., collection size/expected modCount. | Not all elements have been processed yet. |
| **Traversal** | `tryAdvance`, `forEachRemaining`, or a terminal operation actually consumes elements. | Does not mean the source is protected against concurrent modification. |

A **late-binding Spliterator** defers binding to the source until first traversal, first split, or first query of estimated size, depending on its contract and implementation. This property generally narrows the window during which source mutations can cause conflicts.

```text
Create source ---> create Stream/Spliterator ---> binding ---> traversal
                     |                          |
                     | source can still change  | mutating source after this
                     | before binding           | can cause interference
                     v                          v
              not yet a snapshot         fail-fast is only best-effort
```

**Late binding is not a snapshot**, nor is it a multithreaded synchronization mechanism. Pipeline laziness only means many operations are deferred until a result is needed; it does not prescribe the exact moment every source locks in its state.

## 2. Example with `ArrayList`: Mutating Before Terminal Operation

`ArrayList`'s Spliterator in the JDK is **late-binding** and **fail-fast**. When creating a stream and adding an element **before starting the terminal operation**, that change can be included in the subsequent traversal:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BeforeTraversal {
    public static void main(String[] args) {
        List<String> names =
            new ArrayList<>(Arrays.asList("An", "Binh"));

        Stream<String> pipeline = names.stream()
            .filter(name -> !name.isEmpty());

        names.add("Chi"); // Terminal operation has not started yet.

        List<String> result =
            pipeline.collect(Collectors.toList());

        System.out.println(result); // [An, Binh, Chi]
    }
}
```

In this example, `ArrayList` can still change during the phase **before the Spliterator binds**. When the terminal operation starts, it sees the list as of that moment. However, do not generalize this into a rule that "every stream always sees all modifications before `collect`": **early-binding**, snapshot, or specialized sources have different contracts.

A source can lock in its state **earlier than the terminal operation** if someone already used the Spliterator to query size or split work. Always check the specific source's contract rather than treating every collection like `ArrayList`.

## 3. Querying `estimateSize` or `trySplit` Can Trigger Binding

For a late-binding Spliterator, *first traversal* is not the only point that can bind: querying estimated size or calling split can also initialize internal state.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Spliterator;

ArrayList<Integer> values =
    new ArrayList<>(Arrays.asList(10, 20, 30));

Spliterator<Integer> spliterator = values.spliterator();

long sizeBefore = spliterator.estimateSize(); // May bind here.
values.add(40); // Structural modification after Spliterator has bound.

try {
    spliterator.forEachRemaining(System.out::println);
} catch (java.util.ConcurrentModificationException ex) {
    System.out.println("Source modification detected");
}
```

In common `ArrayList` implementations, `estimateSize()` causes the Spliterator to record source state. Adding an element afterward can lead to `ConcurrentModificationException` during traversal. **This snippet is solely to illustrate the risk, not a test permitted to assert that the exception must always occur.**

Similarly, `trySplit()` can bind the source to determine split boundaries. Once splitting begins, branches must uphold the contract over assigned elements; mutating the source then becomes even harder to predict.

Note: calling `estimateSize()` does not necessarily create a **snapshot of all elements**. It merely provides an estimate according to the Spliterator's state and characteristics. For mutable sources, actual sizes and values can diverge if unauthorized interference occurs.

## 4. Fail-Fast Is *Best-Effort* Error Detection, Not a Guard Lock

Some collection iterators and Spliterators like `ArrayList` try to detect **unauthorized structural modifications during traversal** and throw `ConcurrentModificationException`. Structural modifications include adding or removing elements, which changes the `ArrayList`'s element count.

Yet fail-fast has limits:

- It **does not guarantee** catching all modifications when multiple threads access without synchronization.
- Detection may occur after some elements have already been processed; never rely on how many elements are visited before an exception.
- Not seeing `ConcurrentModificationException` **does not prove** access was safe.
- Some mutations like `List.set(index, value)` **do not alter structure** and may go undetected by modification counters, even though traversal output is affected.
- Sources with `CONCURRENT` or `IMMUTABLE` characteristics follow different traversal contracts: they do not default to fail-fast.

`ConcurrentModificationException` does not require **two threads**. A single-threaded sequential program can also trigger it by improperly modifying a collection while an iterator/Spliterator is traversing it. The exception's name is not proof of a multithreaded race condition.

### Wrong example: mutating the source inside the pipeline

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3));

// WRONG EXAMPLE: never run in production code.
numbers.stream().forEach(n -> {
    if (n == 2) {
        numbers.add(99); // Interferes with the traversed source structure.
    }
});
```

In many implementations, this snippet may throw `ConcurrentModificationException`; other unexpected behaviors may also arise. **Never use exceptions as a control-flow mechanism.** Express the transformation as a new collection instead:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3));

List<Integer> expanded = numbers.stream()
    .flatMap(n -> n == 2
        ? java.util.stream.Stream.of(n, 99)
        : java.util.stream.Stream.of(n))
    .collect(Collectors.toList());

System.out.println(expanded); // [1, 2, 99, 3]
```

A Stream must not interfere with its source inside *behavioral parameters* unless the source's contract permits concurrent access. Even when **no exception** is thrown, a pipeline mutating the source inside `map`, `filter`, `peek`, or `forEach` can still be semantically wrong.

## 5. Non-Interference and Statelessness: Two Distinct Principles

The Stream API specification places requirements on behavioral functions:

1. **Non-interfering:** do not modify the data source while the pipeline is executing, except where the source contract explicitly supports concurrent access.
2. **Stateless:** a lambda's result must not depend on external mutable state that can change over time while the pipeline runs.

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", "Binh", "Chi");

// GOOD: lambda only reads its argument.
long count = names.stream()
    .filter(name -> name.length() >= 3)
    .count();

// AVOID: predicate depends on external mutable counter.
final int[] calls = {0};
long unstable = names.stream()
    .filter(name -> ++calls[0] % 2 == 0)
    .count();
```

The second snippet can produce results depending on the count or order of predicate invocations. In a parallel stream, an external counter also suffers from data races. An `AtomicInteger` makes counting atomic, yet still **does not make pairing elements with predicate outcomes deterministic by data**.

For stable tests and clean scaling to parallel execution, depend solely on properties of **the element itself** or immutable parameters, never on execution schedules.

## 6. Spliterator Characteristics Help Identify Source Types

`Spliterator.characteristics()` returns a set of flags describing properties that the implementer **guarantees**. Useful flags for this topic include:

| Flag | Core Meaning | What Must NOT Be Inferred |
| --- | --- | --- |
| `ORDERED` | Has a defined encounter order. | Does not mean every thread processes in that order. |
| `SIZED` | Size is known exactly absent unauthorized structural interference. | Does not mean the source is permanently frozen. |
| `SUBSIZED` | The Spliterator and split parts also have exact contracted sizes. | Not every source splits evenly or easily. |
| `IMMUTABLE` | The source cannot be structurally modified within the Spliterator's traversal scope. | Does not guarantee **deep immutability** of individual element objects. |
| `CONCURRENT` | Source supports safe concurrent modification during traversal per its own contract. | Does not guarantee traversal is an atomic point-in-time snapshot. |
| `NONNULL` | Spliterator guarantees never emitting `null`. | Does not prove external state lacks null values. |
| `DISTINCT` | Elements differ according to the source's equivalence rules. | Does not guarantee sorted traversal order. |
| `SORTED` | Sorted by comparator or natural order. | Does not prove data cannot change. |

The two flags `IMMUTABLE` and `CONCURRENT` target different behaviors: **no structural modifications** versus **allowing concurrent modifications**. They are not switches to toggle fail-fast. When writing a custom Spliterator, **never attach these flags just to skip checking for source changes**; you must genuinely satisfy the contract each flag represents.

Checking flags of a Spliterator:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Spliterator;

Spliterator<String> sp =
    new ArrayList<>(Arrays.asList("A", "B")).spliterator();

System.out.println(sp.hasCharacteristics(Spliterator.ORDERED)); // true
System.out.println(sp.hasCharacteristics(Spliterator.SIZED));   // true
```

Examples of flags for a given collection class should be verified against **the source's API contract**, not extrapolated from seeing a flag appear in one specific JDK build.

## 7. Comparing `ArrayList`, `CopyOnWriteArrayList`, and `ConcurrentHashMap`

All three can serve as stream sources, yet each treats source mutations differently:

| Source | Notable Traversal Style | When Modified |
| --- | --- | --- |
| `ArrayList` | Late-binding, best-effort fail-fast Spliterator | Mistimed structural edits may be detected and throw `ConcurrentModificationException`; no concurrency safety guarantee. |
| `CopyOnWriteArrayList` | **Array-snapshot**-based Spliterator; typically reports `IMMUTABLE` | Changes after snapshot creation do not affect the elements of that captured traversal. |
| `ConcurrentHashMap` | `CONCURRENT` Spliterator, **weakly consistent** traversal | Supports concurrent updates; traversal may see some updates and miss others, not an atomic snapshot. |

### Snapshot with `CopyOnWriteArrayList`

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

CopyOnWriteArrayList<String> source =
    new CopyOnWriteArrayList<>(Arrays.asList("A", "B"));

Spliterator<String> snapshot = source.spliterator();
source.add("C");

List<String> result = StreamSupport.stream(snapshot, false)
    .collect(Collectors.toList());

System.out.println(result); // [A, B]
System.out.println(source); // [A, B, C]
```

The snapshot here is captured when obtaining the Spliterator; element `C` added later is not in the snapshot. `CopyOnWriteArrayList` fits read-heavy, write-rare workloads, because mutations typically copy the underlying array and can become costly in memory/time under continuous updates.

**Element snapshots are not deep copies:** if elements are mutable objects, internal state inside those objects can still change. For example, a snapshot containing `StringBuilder` instances still references the exact same `StringBuilder` objects.

### Weakly consistent traversal of `ConcurrentHashMap`

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

Map<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("A", 1);
counts.put("B", 2);

// Safe to read from concurrent source while system continues updating.
long numberOfKeys = counts.keySet().stream().count();
System.out.println(numberOfKeys); // 2, when no concurrent updates occur
```

When other threads add/remove keys during traversal, **you must not require** `count()` or `collect()` to return the exact key set of a single instant. Weak consistency lets traversal proceed safely per contract **without fail-fast**; business-level consistency must still be designed explicitly.

If you need an exact point-in-time report, design an appropriate snapshot or synchronization mechanism rather than simply swapping `HashMap` for `ConcurrentHashMap`.

## 8. Using `StreamSupport.stream(Supplier, ...)` to Defer Obtaining the Source

When building streams manually from a Spliterator, `StreamSupport` has two commonly used overload groups:

```java
StreamSupport.stream(spliterator, parallel);

StreamSupport.stream(
    spliteratorSupplier,
    characteristics,
    parallel
);
```

The first overload accepts an already-created Spliterator object. The second accepts a **`Supplier<? extends Spliterator<T>>`**, allowing the call that obtains the Spliterator to be deferred until **after the terminal operation begins**. This helps shrink the interference window between obtaining a Spliterator and starting processing.

Example with `ArrayList`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> source =
    new ArrayList<>(Arrays.asList("A", "B"));

Stream<String> lazySource = StreamSupport.stream(
    () -> source.spliterator(),
    Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
    false
);

source.add("C"); // Terminal operation has not started yet.

List<String> result = lazySource.collect(Collectors.toList());
System.out.println(result); // [A, B, C]
```

For `ArrayList.spliterator()`, the flags `ORDERED | SIZED | SUBSIZED` reflect the characteristics that source reports. **The `characteristics` argument to the supplier overload must match the characteristics of the Spliterator produced by the supplier**. Never declare `IMMUTABLE` or `CONCURRENT` if the list remains a mutable `ArrayList`.

**Important limit:** a supplier only defers when the Spliterator is obtained. It **does not make modifications during terminal operation execution safe**, does not create copies, and does not replace synchronization.

## 9. Custom Spliterator Example: Deferring Iterator Creation

Suppose we have a `List<String>` source and want to control `Iterator` creation so it only starts on the first `tryAdvance` call. The example below illustrates a simple sequential Spliterator that does not support splitting:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class DeferredSourceExample {
    static final class DeferredListSpliterator<T>
            implements Spliterator<T> {
        private final List<T> source;
        private Iterator<T> iterator; // Not yet created in constructor.
        private boolean exhausted;

        DeferredListSpliterator(List<T> source) {
            this.source = Objects.requireNonNull(source);
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action);
            if (exhausted) {
                return false;
            }
            if (iterator == null) {
                iterator = source.iterator(); // Begin binding.
            }
            if (!iterator.hasNext()) {
                exhausted = true;
                return false;
            }
            action.accept(iterator.next());
            return true;
        }

        @Override
        public Spliterator<T> trySplit() {
            return null; // Unsplittable: suitable for sequential traversal only.
        }

        @Override
        public long estimateSize() {
            return exhausted ? 0L : Long.MAX_VALUE;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED;
        }
    }

    public static void main(String[] args) {
        List<String> rows =
            new ArrayList<>(Arrays.asList("A", "B"));

        Stream<String> pipeline = StreamSupport.stream(
            () -> new DeferredListSpliterator<String>(rows),
            Spliterator.ORDERED,
            false
        );

        rows.add("C"); // Before terminal operation and before iterator creation.

        List<String> result =
            pipeline.collect(Collectors.toList());
        System.out.println(result); // [A, B, C]
    }
}
```

Key design points to understand:

- `DeferredListSpliterator` does not create the iterator in its constructor. It creates the iterator only when `tryAdvance` is first called.
- `StreamSupport.stream(Supplier, ...)` further defers **Spliterator instantiation** until the terminal operation begins.
- `trySplit()` returns `null`, so the Spliterator **does not support splitting**; adding `parallel()` will not enable effective parallel division.
- `estimateSize()` returns `Long.MAX_VALUE` while not exhausted because the example **does not track exact size**. You must not declare `SIZED` or `SUBSIZED` with this implementation.
- The `Iterator` obtained from `ArrayList` remains best-effort fail-fast. Deferring iterator creation **does not permit mutating the list once traversal has begun**.

This is an educational example of a custom source, not an optimal implementation for `List`: `ArrayList.spliterator()` already provides accurate size estimation and better splitting. When writing a real Spliterator, also design `trySplit`, `estimateSize` accuracy, characteristic flags, and resource lifecycles.

## 10. Caution with `SIZED`, `SUBSIZED`, and Pipeline Optimizations

Declaring characteristics inaccurately can cause the Stream API to optimize based on **assumptions that no longer hold**. For example, on a `SIZED` source with a size-preserving pipeline, the `count()` terminal operation can determine the count without traversing each element or invoking `peek`:

```java
import java.util.Arrays;

long count = Arrays.asList("A", "B", "C")
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// Lines A, B, C are not guaranteed to be printed by peek.
```

Therefore, never put mandatory actions like transaction logging or state updates inside `peek` and rely on `count()` to force them to run. On a custom Spliterator, declaring `SIZED` while the source still grows or shrinks unpredictably also makes the estimated size unreliable.

For a Spliterator with the `SIZED` characteristic, size estimation is expected to equal the exact element count **under the condition of no unauthorized interference**. `SUBSIZED` additionally requires Spliterators produced after splitting to preserve corresponding size properties. Never attach these two flags just "for optimization."

## 11. Choosing a Safe Strategy for Mutable Sources

| Requirement | Appropriate Approach | Limitation |
| --- | --- | --- |
| Source changes **before** processing starts | Use a suitable late-binding source or supplier creating Spliterator on demand | Must not mutate arbitrarily while terminal operation runs. |
| Need stable data for processing and reproducible tests | Copy collection before building pipeline | Copying a collection is typically only a **shallow copy**. |
| Read-heavy, write-rare, convenient snapshot traversal | `CopyOnWriteArrayList` | Copy cost on updates can be high. |
| Need traversal during concurrent updates | `CONCURRENT`-supporting source like `ConcurrentHashMap` | Weak consistency does not guarantee an atomic snapshot. |
| Shared collection synchronized by a lock | Lock properly around the entire traversal phase, if all actors comply | Do not hold locks too long or perform slow I/O inside critical sections. |
| Need to build a custom Stream source | `StreamSupport.stream` with a Spliterator/supplier having a real contract | Must guarantee characteristics, splitting, binding, and resources yourself. |

### Creating a snapshot before running a pipeline

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> live =
    new ArrayList<>(Arrays.asList("A", "B"));

List<String> snapshot = new ArrayList<>(live);
live.add("C");

List<String> result = snapshot.stream()
    .map(String::toLowerCase)
    .collect(Collectors.toList());

System.out.println(result); // [a, b]
```

The result is unaffected by adding `C` **after copying**. However, `new ArrayList<>(live)` is just a copy step; if another thread is mutating `live` concurrently without coordination, **the copy produced is not guaranteed to be a consistent snapshot**. You need synchronization or a source supporting consistent snapshots.

When element data consists of mutable objects, a collection snapshot can still observe internal changes inside those elements. If deep immutability is required, use immutable value types or copy appropriately at the element level.

### With `Collections.synchronizedList`

A `List` wrapped with `Collections.synchronizedList` does not automatically make every Stream pipeline safe. If you need to traverse while other actors are active, you may have to synchronize **for the entire traversal** on the exact monitor per the wrapper's contract:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

List<Integer> shared = Collections.synchronizedList(
    new ArrayList<>(Arrays.asList(1, 2, 3))
);

synchronized (shared) {
    long total = shared.stream()
        .mapToLong(Integer::longValue)
        .sum();
    System.out.println(total); // 6
}
```

This only works if **every source-modifying operation** in the program also follows compatible synchronization. Do not hold locks for long durations to run pipelines involving I/O or unpredictable callbacks if you can safely take a copy and compute outside the lock.

## 12. Common Mistakes When Designing Custom Sources

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Thinking "lazy stream" means "unbound source" | Binding state depends on the Spliterator and prior queries/splits. | Distinguish stream creation, binding, and traversal moments. |
| Mutating `ArrayList` inside stream `forEach`/lambda | Interferes with traversed source, violating non-interference. | Produce a new result or separate the update step. |
| Using `ConcurrentModificationException` as a concurrency check | Fail-fast is only best-effort and no substitute for thread safety. | Use snapshots, synchronization, or a proper concurrent source. |
| Assuming `List.set` is always caught by fail-fast | It is not necessarily a structural change. | Do not mutate source data while a pipeline is running. |
| Declaring `IMMUTABLE` on an add/remove-capable `ArrayList` | Flag does not reflect the source. | Only declare characteristics genuinely guaranteed. |
| Declaring `CONCURRENT` to avoid exceptions | Does not make the underlying structure thread-safe. | Pick a real concurrent source and understand weak consistency. |
| Declaring `SIZED` when `estimateSize` is inaccurate | Stream may optimize based on false information. | Fix estimate/characteristics; when uncertain, omit `SIZED`. |
| `StreamSupport.stream` supplier returning Spliterator with flags differing from declared parameter | Violates supplier-overload contract. | Align actual characteristics accurately. |
| Unsplittable `trySplit` yet expecting fast parallel execution | Framework cannot split work effectively. | Design proper `trySplit` or accept sequential execution. |
| Expecting a concurrent stream to yield an atomic snapshot | Traversal may be weakly consistent. | Build a dedicated snapshot/consistency mechanism per business needs. |

## 13. I/O-Backed Sources and Limits of Late Binding

For example, `Files.lines` creates a Stream reading a file, yet stream creation and consumption still involve **I/O resources**. Laziness does not mean all I/O initialization is deferred until the first line is read, nor does it mean a file being modified externally is guarded by fail-fast.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FirstLines {
    public static List<String> nonEmptyPrefix(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.filter(s -> !s.isEmpty())
                .limit(20)
                .collect(Collectors.toList());
        }
    }
}
```

`try-with-resources` ensures closing the Stream and underlying resource along normal and exceptional paths. Terminal operations like `collect` or `limit` **do not automatically replace `close()`**. When a file changes during reading, behavior follows filesystem and I/O API contracts, **not assuming** `ConcurrentModificationException` as with `ArrayList`.

For custom I/O sources, explicitly specify resource management, the `close` method, termination conditions, error handling, and splitting capability; a custom Spliterator handling only `tryAdvance` is not enough to be production-ready.

## 14. How to Properly Test Late Binding and Fail-Fast

Separate two kinds of tests:

**Testing deterministic contracted behavior:** for a specific source supporting late binding, build the pipeline, mutate the source *before the terminal operation*, and assert the element set per contract. Or with `CopyOnWriteArrayList`, obtain the snapshot Spliterator before adding an element, and assert the snapshot excludes the new element.

**Testing interference detection:** do not write tests expecting `ConcurrentModificationException` to **always** be thrown after every mutation during traversal. Fail-fast is best-effort, and multithreaded scheduling is non-deterministic. Instead, verify code performs no contract-violating interference, or use snapshot/synchronization strategies yielding deterministic outcomes.

Example testing a stable snapshot:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

CopyOnWriteArrayList<String> live =
    new CopyOnWriteArrayList<>(Arrays.asList("A", "B"));

Spliterator<String> fixed = live.spliterator();
live.add("C");

List<String> observed = StreamSupport.stream(fixed, false)
    .collect(Collectors.toList());

if (!observed.equals(Arrays.asList("A", "B"))) {
    throw new AssertionError("Snapshot was modified");
}
```

When testing a custom Spliterator, also test: empty source; single element; `tryAdvance` after exhaustion; `trySplit` (if supported) losing or duplicating no elements; `characteristics` matching behavior; and every element emitted exactly once under **non-interference**.

## 15. Practice Exercises

**Exercise 1 — Three moments.** Given an `ArrayList` containing `[1, 2]`. Create a stream, add `3`, then `collect`. Explain why a late-binding source's result can contain `3`. Next, call `list.spliterator().estimateSize()` before adding the element and explain why mutating after binding is dangerous.

**Exercise 2 — Best-effort fail-fast.** Use an `ArrayList` and try adding an element inside `forEach`. Observe the behavior, but **do not** write a test expecting the exception to always be thrown. Give at least two reasons why fail-fast is not a thread-safety mechanism.

**Exercise 3 — Comparing three sources.** Examine the traversal mechanisms of `ArrayList`, `CopyOnWriteArrayList`, and `ConcurrentHashMap`. Which source fits snapshot reads? Which can traverse alongside concurrent updates and possibly observe partial changes? Which should not be mutated during traversal?

**Exercise 4 — Supplier-based stream.** Use `StreamSupport.stream(() -> list.spliterator(), flags, false)` with a specific `ArrayList`. Explain when the supplier is invoked, why flags must match the Spliterator, and why using a supplier does not permit mutating the source during the terminal operation.

**Exercise 5 — Custom Spliterator.** Based on `DeferredListSpliterator`, explain why `trySplit()` returns `null` and `estimateSize()` returns `Long.MAX_VALUE` before exhaustion. If you want to add `SIZED` and splitting support, what invariants must you maintain regarding remaining element counts?

**Exercise 6 — Safe design.** A system ingests new events while computing reports. Compare three approaches: locking the source and copying, using a weakly consistent source, or taking an immutable snapshot. Pick a solution when the report **must be point-in-time consistent** versus when approximate monitoring metrics suffice.

**Remember:** *Late binding* defers when a Spliterator attaches to its source; it does not create a snapshot automatically and does not permit arbitrary source mutations during traversal. *Fail-fast* merely attempts to detect interference via `ConcurrentModificationException` and is **no concurrency safety guarantee**. When designing custom sources, declare `characteristics` honestly, respect `non-interference`, and choose explicitly among snapshots, synchronization, or concurrent sources based on your application's consistency needs.
