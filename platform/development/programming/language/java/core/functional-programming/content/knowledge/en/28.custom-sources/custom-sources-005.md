# `IMMUTABLE`, `CONCURRENT`, and `NONNULL` in `Spliterator` — Custom Stream Sources

## 1. What Are These Three Characteristics Used For?

A `Stream` can pull elements from a `List`, array, queue, or an application-defined source. When creating a Stream from a custom source, you typically build a `Spliterator<T>` and pass it to `StreamSupport.stream(...)`.

A `Spliterator` not only knows **how to traverse and split elements**; it also declares the source's *characteristics*. Among them, three flags that are easy to confuse are:

- **`Spliterator.IMMUTABLE`**: the source cannot be **structurally modified** during traversal per the source's contract.
- **`Spliterator.CONCURRENT`**: the source allows **concurrent structural modification** during traversal without external synchronization.
- **`Spliterator.NONNULL`**: the elements the spliterator delivers to the consumer **are all non-`null`**.

Key point: these are **commitments about the source and traversal**, not extra toggle options to automatically speed things up. Declaring a flag does not turn a mutable array into an immutable one, does not turn an `ArrayList` into a thread-safe structure, and does not automatically filter out `null` elements.

Short example:

```java
int flags = Spliterator.ORDERED
        | Spliterator.IMMUTABLE
        | Spliterator.NONNULL;

Spliterator<String> sp = Spliterators.spliterator(
        new String[]{"red", "green", "blue"}, flags);
```

The snippet above illustrates how to declare with imports `java.util.Spliterator` and `java.util.Spliterators`. **Only declare `IMMUTABLE` when the application genuinely guarantees the source array is not structurally modified during traversal.** A Java array can still be modified (`array[i] = ...`) if a writable reference remains; `final` on the array variable does not make the elements immutable. Therefore, this lesson will use a private snapshot and prevent other code from modifying it.

After this lesson, you will be able to distinguish these three characteristics, choose the right flags for a custom `Spliterator`, build a standalone runnable Java 17 example, understand the semantics of concurrent/weakly consistent sources, and test **actual behavior** rather than just checking flag bits.

## 2. Position of `Spliterator` in the Pipeline

A custom Stream source typically follows this model:

```text
Source data (T)
    │
    ▼
Spliterator<T>
    ├── tryAdvance(action): passes one element to action
    ├── forEachRemaining(action): traverses remaining elements
    ├── trySplit(): splits work into two parts if possible
    ├── estimateSize(): estimates remaining element count
    └── characteristics(): declares source properties
    │
    ▼
StreamSupport.stream(spliterator, parallel)
    │
    ▼
filter → map → sorted → ...
    │
    ▼
terminal operation: toList, count, reduce, collect, ...
```

`StreamSupport.stream(sp, false)` creates a sequential Stream; the `true` parameter allows the Stream to operate in parallel when the operations and source are suitable. Enabling parallel **does not fix** a spliterator with inaccurately declared characteristics, nor does it guarantee the program will always use multiple threads or run faster.

A few important methods:

```java
boolean has = sp.hasCharacteristics(Spliterator.NONNULL);

int flags = sp.characteristics();

long estimate = sp.estimateSize();

long exact = sp.getExactSizeIfKnown();
```

`hasCharacteristics(mask)` checks the bits specified in mask; `getExactSizeIfKnown()` only returns the exact size when the spliterator has `SIZED`, otherwise returning `-1`. When building a Stream from a dynamic source, do not assume the estimated size is always the final number of consumed elements.

## 3. `IMMUTABLE`: no structural modification of the source during traversal

`IMMUTABLE` states that **the element source cannot be structurally modified** (per the source's contract) during traversal. Examples of structural modification: adding or removing elements, or replacing elements in an array/sequence when the source considers that operation a structural modification.

It **does not state** that:

- Every traversed object must be an immutable object.
- Every field of the object is always `final`.
- Spliterator automatically copies data into a snapshot.
- No other threads are active on the machine.
- You can mark the flag on an `ArrayList` that is still being modified just because the reference variable is declared `final`.

For example, a `List<Box>` might not change the count or positions of elements during traversal, while the `Box` instances contain mutable fields. `IMMUTABLE` refers to **the source structure**, not claiming those `Box` objects are deeply immutable.

### Easy-to-verify design: encapsulated snapshot

Suppose a custom source class copies strings from input into a **private** array, does not expose the array, and provides no mutating methods:

```java
final class SnapshotWords {
    private final String[] values;

    SnapshotWords(List<String> input) {
        values = List.copyOf(input).toArray(String[]::new);
    }

    Spliterator<String> spliterator() {
        return Spliterators.spliterator(
                values,
                Spliterator.ORDERED
                        | Spliterator.IMMUTABLE
                        | Spliterator.NONNULL);
    }
}
```

This is an excerpt; the standalone program below has full imports and tests. `List.copyOf(input)` creates an unmodifiable list that rejects `null` elements; we copy the strings into a private array so the spliterator operates on stable data. No method directly returns the private array; the class does not modify the array after construction. Because the elements are immutable `String`s, this example is even easier to verify than when elements are mutable objects.

Note that `Spliterators.spliterator(array, additionalCharacteristics)` **trusts the passed flags**; it does not automatically verify all immutability and non-null conditions of the data. If your design still lets other code hold a reference to the array and change values while the Stream traverses, you have declared the flags inaccurately.

### `IMMUTABLE` does not mean "always creates a snapshot"

A spliterator can pull data directly from a genuinely immutable structure. Or it can pull from an immutable snapshot that you proactively created beforehand. **You** yourself must ensure the actual source satisfies what is declared. The flag does not automatically turn source data into a snapshot.

`List.copyOf` helps prevent structural modification through the returned list, but for a List containing mutable elements, the objects inside can still be modified. Meanwhile, `Collections.unmodifiableList(backingList)` only creates **a view that disallows modification through the view**; if other code still holds `backingList` and modifies it, the underlying data still changes. You should not treat every unmodifiable view as equivalent to an independent snapshot.

## 4. `CONCURRENT`: source allows concurrent structural modification

`CONCURRENT` describes a source designed to allow **structural modification while being traversed**, without the user having to lock the entire source with external synchronization.

An example in the Java Collections Framework is `ConcurrentLinkedQueue`:

```java
ConcurrentLinkedQueue<String> queue =
        new ConcurrentLinkedQueue<>(List.of("red", "green"));

Spliterator<String> sp = queue.spliterator();

System.out.println(
        sp.hasCharacteristics(Spliterator.CONCURRENT)); // true
```

`ConcurrentLinkedQueue` supports concurrent additions/removals, and its spliterator is **weakly consistent**: it does not fail due to concurrent modifications in a fail-fast manner like some regular collections; it may reflect some (or not all) changes occurring during traversal. Do not treat the result as a consistent snapshot at a fixed point in time.

### Concurrent does not mean "every element appears once in a snapshot"

If thread A traverses a `ConcurrentLinkedQueue` and thread B adds/removes elements, you **must not** infer that the result list equals the exact set of elements at the start or end time. The result may depend on the timing of interactions between threads. If business logic needs a stable snapshot or transactional accuracy, design an appropriate snapshot/synchronization mechanism rather than relying solely on the `CONCURRENT` flag.

A concurrent source also does not mean:

- Every traversed object is thread-safe.
- Every `Consumer`/lambda or collector updating shared state is thread-safe.
- You can arbitrarily call `tryAdvance` concurrently on **the exact same spliterator instance**. Per Spliterator design, you must follow the splitting and traversal-ownership contract; this flag speaks about **the source**, not a license to share a single spliterator object across multiple threads.
- Whether the created Stream has an encounter order or not. `CONCURRENT` and `ORDERED` are two separate characteristics.
- Every type of concurrent collection has the same traversal, size, or ordering policy.

### Do not declare `CONCURRENT` to "save" an `ArrayList`

Wrong example:

```java
List<String> data = new ArrayList<>(List.of("a", "b"));
Spliterator<String> wrong = Spliterators.spliterator(
        data, Spliterator.CONCURRENT);
```

This line may successfully create a spliterator, yet it **does not turn `ArrayList` into a source that safely allows concurrent structural modification**. If another thread adds/removes elements, behavior and consistency will not meet the flag's promise. Use a genuinely concurrent structure or design a snapshot. Do not take code running once without throwing an error as proof of correctness.

## 5. `NONNULL`: every element passed to the consumer is non-null

The `NONNULL` characteristic commits that elements passed through `tryAdvance` or `forEachRemaining` will **not have a `null` value**.

It does not mean:

- The `Spliterator` object is non-null (of course the API already requires a valid object).
- A `List` used as a source cannot contain null just because its generic is `List<String>`.
- After calling an arbitrary `map` lambda, the Stream result is still guaranteed non-null.
- `Spliterators.spliterator(...)` will automatically detect and throw an error if you lie about the flag.

**Contractually invalid** example:

```java
String[] values = {"ok", null};

Spliterator<String> incorrect =
        Spliterators.spliterator(
                values, Spliterator.NONNULL);
```

The call may succeed, yet the spliterator emits a `null` element during traversal, contradicting the flag just declared. The `String` type parameter does not replace validation.

### Making a NONNULL source intentionally

For an input list, `List.copyOf` rejects null right when creating the snapshot:

```java
List<String> safe = List.copyOf(userInput);
```

`safe` does not allow null elements; when that snapshot is encapsulated and only exposed through an appropriate spliterator, declaring `NONNULL` has a solid basis. If null is meaningful input data, you must choose another policy:

1. **Reject**: throw a validation error with position.
2. **Normalize**: convert null to a replacement value, while avoiding business ambiguity.
3. **Allow null**: do not declare `NONNULL`, and require subsequent lambdas to handle null explicitly.
4. **Filter null**: only when the contract permits dropping those elements; do not use filtering to hide input errors.

For example, a source that may contain null can still use Stream, as long as subsequent operations are appropriate:

```java
List<String> input = Arrays.asList("a", null, "b");

List<String> safe = input.stream()
        .filter(Objects::nonNull)
        .toList();
```

`Stream` does not forbid all null elements as a general rule; however, some terminal operations and collectors (such as `findFirst`, `findAny`, and certain result collectors) have their own rules regarding null. Choosing the policy must be clear before use.

### `map` can produce null from a NONNULL source

```java
List<String> words = List.of("a", "b");

List<String> mapped = words.stream()
        .map(word -> word.equals("b") ? null : word)
        .toList();

// [a, null]
```

The result still contains a `null` element even though the initial source had two non-null strings. Therefore, you should not claim an initial `NONNULL` flag guarantees the entire pipeline remains null-free after every transformation. If you need to maintain the guarantee, validate at the transformation step, or design the mapper to always return non-null values.

## 6. How Do the Three Flags Differ?

| Flag | Primary Commitment | Does Not Commit |
| --- | --- | --- |
| `IMMUTABLE` | Source structure cannot be modified during traversal | Deep immutability of elements; automatic snapshot |
| `CONCURRENT` | Source structure can be modified concurrently without external locking | Result is a snapshot; exact capture of every newly added element; thread-safe lambdas/collectors |
| `NONNULL` | Each element emitted by the spliterator is non-null | Subsequent mappers do not produce null; nulls are automatically filtered |

`IMMUTABLE` and `CONCURRENT` state two **fundamentally different** structural modification models. For a real source, you typically choose one or the other: a source that does not change structurally during traversal, or a source that allows concurrent modification. **Do not attach both just to "have more flags,"** because it obscures the actual modification policy. `NONNULL` is an independent characteristic: an immutable source can still contain null if the API allows it; a concurrent source may forbid null or not, depending on its contract.

Other characteristics such as `ORDERED`, `SIZED`, `SUBSIZED`, `DISTINCT`, and `SORTED` must be evaluated separately. Do not infer `IMMUTABLE` implies `SIZED`, or `CONCURRENT` implies `UNORDERED`. An ordered Stream can still be supplied from a concurrent source supporting traversal order per its own contract.

## 7. Complete Java 17 Example: Custom Snapshot and Concurrent Queue

The following program defines a `SnapshotWords` source that controls its own data, creates a spliterator with `IMMUTABLE | NONNULL | ORDERED`, compares both sequential/parallel Streams, checks splitting behavior, and compares with `ConcurrentLinkedQueue`'s spliterator.

Save as **`SpliteratorCharacteristicsDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class SpliteratorCharacteristicsDemo {
    static final class SnapshotWords {
        private final String[] values;

        SnapshotWords(List<String> input) {
            Objects.requireNonNull(input, "input");
            // Create an independent copy; forbid null elements.
            values = List.copyOf(input).toArray(String[]::new);
        }

        Spliterator<String> spliterator() {
            return Spliterators.spliterator(
                    values,
                    Spliterator.ORDERED
                            | Spliterator.IMMUTABLE
                            | Spliterator.NONNULL);
        }

        Stream<String> stream(boolean parallel) {
            return StreamSupport.stream(spliterator(), parallel);
        }
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Failed: " + label);
        }
    }

    static void expect(Object wanted, Object actual, String label) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    label + ": expected=" + wanted
                            + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        SnapshotWords snapshot =
                new SnapshotWords(List.of("red", "green", "blue", "gold"));

        Spliterator<String> sp = snapshot.spliterator();
        require(sp.hasCharacteristics(Spliterator.IMMUTABLE),
                "snapshot immutable");
        require(sp.hasCharacteristics(Spliterator.NONNULL),
                "snapshot nonnull");
        require(sp.hasCharacteristics(Spliterator.ORDERED),
                "snapshot ordered");
        require(sp.hasCharacteristics(Spliterator.SIZED),
                "array source sized");
        require(sp.hasCharacteristics(Spliterator.SUBSIZED),
                "array source subsized");
        require(!sp.hasCharacteristics(Spliterator.CONCURRENT),
                "snapshot not concurrent");
        expect(4L, sp.getExactSizeIfKnown(), "snapshot size");

        // Create two fresh spliterators to test sequential and parallel processing.
        List<String> sequential = snapshot.stream(false).toList();
        List<String> parallel = snapshot.stream(true).toList();

        expect(List.of("red", "green", "blue", "gold"),
                sequential, "sequential contents");
        expect(sequential, parallel, "parallel preserves order");

        // Array spliterator supports splitting remaining elements.
        Spliterator<String> root = snapshot.spliterator();
        Spliterator<String> part = root.trySplit();
        require(part != null, "array can split");
        require(part.hasCharacteristics(Spliterator.NONNULL),
                "split retains nonnull");
        require(part.hasCharacteristics(Spliterator.IMMUTABLE),
                "split retains immutable");

        long totalRemaining =
                part.getExactSizeIfKnown() + root.getExactSizeIfKnown();
        expect(4L, totalRemaining, "split partitions size");

        // ConcurrentLinkedQueue is an example source allowing concurrent modification.
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>(
                        List.of("alpha", "beta", "gamma"));

        Spliterator<String> concurrent = queue.spliterator();
        require(concurrent.hasCharacteristics(Spliterator.CONCURRENT),
                "queue concurrent");
        require(concurrent.hasCharacteristics(Spliterator.NONNULL),
                "queue nonnull");
        require(concurrent.hasCharacteristics(Spliterator.ORDERED),
                "queue ordered");
        require(!concurrent.hasCharacteristics(Spliterator.IMMUTABLE),
                "queue is not immutable");
        require(!concurrent.hasCharacteristics(Spliterator.SIZED),
                "queue traversal not sized");

        // No other writers: traversal content is fixed here.
        List<String> queueValues =
                StreamSupport.stream(queue.spliterator(), false).toList();
        expect(List.of("alpha", "beta", "gamma"),
                queueValues, "queue values without concurrent writes");

        // Queue forbids null; NONNULL is grounded in the queue's contract.
        boolean nullRejected = false;
        try {
            queue.add(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        require(nullRejected, "queue rejects null");

        // Snapshot is validated at creation time, not auto-filtered by the flag.
        boolean snapshotNullRejected = false;
        try {
            new SnapshotWords(java.util.Arrays.asList("ok", null));
        } catch (NullPointerException expected) {
            snapshotNullRejected = true;
        }
        require(snapshotNullRejected, "snapshot rejects null");

        // Even though source has NONNULL, map can still produce null.
        List<String> mapped = snapshot.stream(false)
                .map(s -> s.equals("blue") ? null : s)
                .toList();
        expect(java.util.Arrays.asList(
                "red", "green", null, "gold"),
                mapped, "mapper may produce null");

        System.out.println("snapshotImmutable="
                + sp.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("snapshotConcurrent="
                + sp.hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("snapshotNonnull="
                + sp.hasCharacteristics(Spliterator.NONNULL));
        System.out.println("snapshotSized="
                + sp.hasCharacteristics(Spliterator.SIZED));
        System.out.println("snapshotSize=" + sp.getExactSizeIfKnown());
        System.out.println("snapshotValues=" + sequential);
        System.out.println("parallelValues=" + parallel);
        System.out.println("splitTotalRemaining=" + totalRemaining);
        System.out.println("queueConcurrent="
                + concurrent.hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("queueImmutable="
                + concurrent.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("queueNonnull="
                + concurrent.hasCharacteristics(Spliterator.NONNULL));
        System.out.println("queueSized="
                + concurrent.hasCharacteristics(Spliterator.SIZED));
        System.out.println("queueValues=" + queueValues);
        System.out.println("nullRejected=" + nullRejected);
        System.out.println("snapshotNullRejected=" + snapshotNullRejected);
        System.out.println("mapped=" + mapped);
        System.out.println("tests=PASS");
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac SpliteratorCharacteristicsDemo.java
java SpliteratorCharacteristicsDemo
```

Expected stdout:

```text
snapshotImmutable=true
snapshotConcurrent=false
snapshotNonnull=true
snapshotSized=true
snapshotSize=4
snapshotValues=[red, green, blue, gold]
parallelValues=[red, green, blue, gold]
splitTotalRemaining=4
queueConcurrent=true
queueImmutable=false
queueNonnull=true
queueSized=false
queueValues=[alpha, beta, gamma]
nullRejected=true
snapshotNullRejected=true
mapped=[red, green, null, gold]
tests=PASS
```

### Output Explanation

- `snapshotImmutable=true`: the flag is reasonably declared because the snapshot is a private array with no way to modify data after creation.
- `snapshotNonnull=true`: the constructor uses `List.copyOf` to reject null before creating the array.
- `snapshotSized=true`, `snapshotSize=4`: `Spliterators.spliterator(array, flags)` adds `SIZED` and `SUBSIZED` characteristics, with the exact size of the array.
- `parallelValues` still follows encounter order because the spliterator declares `ORDERED` and the `toList()` collection preserves the order of an ordered source.
- `splitTotalRemaining=4`: `trySplit()` divides the remaining element region into two non-overlapping parts. Without depending on the exact size of each part, we just verify the sum is unchanged.
- `queueConcurrent=true`: this characteristic belongs to the spliterator from `ConcurrentLinkedQueue`, a source designed for concurrent modification.
- `queueSized=false`: the queue can change during traversal, not promising that the estimate is an exact size per `SIZED`.
- `queueValues` is fixed because the demo program **does not** spawn another thread modifying the queue concurrently. If concurrent mutations exist, you must not apply a snapshot expectation on this line.
- `mapped` contains `null` produced by the mapper, proving `NONNULL` is a commitment of the source spliterator, not validation for the entire pipeline.
- Checks throw `AssertionError` immediately if a condition fails; no need to enable `java -ea`.

## 8. Why Do Snapshots and Concurrent Sources Have Different Contracts?

Suppose an application exports a report of an ID list at the start of a job. If the ID list must not change throughout the run, a snapshot is an appropriate design:

```text
Input List may be modified later
         │
         ▼
Copy into private snapshot
         │
         ▼
Spliterator IMMUTABLE | NONNULL | ORDERED
         │
         ▼
Stream processes snapshot data
```

The purpose of a snapshot is **stability**: the same snapshot will have the same set of elements, unless the mapper/external source itself has other state.

For a queue receiving events:

```text
Producer thread ──add/remove──► ConcurrentLinkedQueue
                                   │
                                   ▼
                           Spliterator CONCURRENT
                                   │
                                   ▼
                            Consumer traversal
```

The purpose is **to allow producer and consumer to operate simultaneously**. The traversal result can be a dynamic slice, not a transactional snapshot. A typical concurrent spliterator is unsuitable for generating a report of "every exact element at exact time T" without an additional data-capturing mechanism.

You should not mark a queue `IMMUTABLE` just because no producer happened to write during one test run. Flags describe **the general contract of the source**, not an incidental state at one moment.

## 9. How Do `IMMUTABLE` and `CONCURRENT` Relate to Source Modification?

When a spliterator lacks one of the appropriate guarantee mechanisms, modifying the source during traversal can cause undefined results per the source's contract. Many non-concurrent collections use a **fail-fast** mechanism to detect some structural changes, yet fail-fast is typically best-effort, not something an application is allowed to use for synchronization or safety checks.

Example to avoid:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

numbers.stream().forEach(x -> {
    if (x == 2) {
        numbers.add(10); // Modifying the source during traversal.
    }
});
```

This is an anti-pattern, not code to run in the demo. It may throw `ConcurrentModificationException`, but an application must not rely on the exception always occurring at the right time. The right way is to put results into **another** collection or use pure Stream transformations:

```java
List<Integer> extended = Stream.concat(
        numbers.stream(),
        Stream.of(10))
        .toList();
```

Here `numbers` is a list not modified while the Stream is traversing. If multiple threads need to modify the source, design an appropriate concurrent structure or create a snapshot on demand.

### Does the `IMMUTABLE` flag replace locking?

It is not a locking mechanism. It is a commitment of the source. If the source is genuinely immutable, no lock is needed to protect against structural changes **because those changes cannot happen**. If the source is still mutable and you merely "hope" nobody modifies it, the `IMMUTABLE` flag does not protect against race conditions. The guarantee must come from data ownership design, copying, or access constraints, not from setting a bit.

### Does the `CONCURRENT` flag replace business synchronization?

No either. It only states that traversal can coexist with structural modification per the source policy. Multi-step business operations like "check existence then delete" may require higher-level atomicity. `CONCURRENT` does not automatically provide transactions, snapshots, or synchronization across network sends, database writes, or multi-structure updates.

## 10. Designing a Custom `Spliterator` and Preserving Characteristics After Splitting

When implementing the `Spliterator<T>` interface yourself instead of using `Spliterators.spliterator(...)`, you are responsible for implementing:

```java
boolean tryAdvance(Consumer<? super T> action);

Spliterator<T> trySplit();

long estimateSize();

int characteristics();
```

A proper implementation must keep the declared promises on **both the original spliterator and the parts returned by `trySplit`**. If the root promises `NONNULL`, a child branch must not emit `null`. If the root promises `IMMUTABLE`, a child branch must not depend on a source that can be structurally modified contrary to contract. If the root declares `SIZED`/`SUBSIZED`, estimates and split sizes must obey the rules of those characteristics.

Sketch example creating branches from an array snapshot:

```java
final class RangeWords implements Spliterator<String> {
    private final String[] values;
    private int index;
    private final int fence;

    RangeWords(String[] values, int start, int end) {
        this.values = values;
        this.index = start;
        this.fence = end;
    }

    @Override
    public boolean tryAdvance(
            java.util.function.Consumer<? super String> action) {
        Objects.requireNonNull(action);
        if (index >= fence) {
            return false;
        }
        action.accept(values[index++]);
        return true;
    }

    @Override
    public Spliterator<String> trySplit() {
        int lo = index;
        int mid = (lo + fence) >>> 1;
        if (lo >= mid) {
            return null;
        }
        index = mid;
        return new RangeWords(values, lo, mid);
    }

    @Override
    public long estimateSize() {
        return fence - index;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
    }
}
```

This is an **additional illustrative snippet**, not a standalone working class: `RangeWords` needs `Spliterator`, `Objects`, `Consumer`, and a source array **protected from modification** as in `SnapshotWords`. The constructor signature does not stop callers from passing an array that can still be modified or contain null; to declare `IMMUTABLE`/`NONNULL` safely, this class must be integrated with an owner that controls the snapshot or copies/validates input itself.

The `trySplit` mechanism: takes `[lo,mid)` for the new branch, while the original branch keeps `[mid,fence)`. They do not overlap, and their estimated sizes sum to the pre-split size. Both use the same array solely for **reading**. If the array is genuinely unmodified and elements are non-null, both branches can declare the same flags.

Do not force `trySplit` to always return a child branch. For small sources, hard-to-partition sources, or specific internal policies, returning `null` is valid. However, having `trySplit` only return `null` limits the ability to exploit parallelism.

### Avoiding overflow when computing midpoint

In the illustrative snippet, `mid = (lo + fence) >>> 1` is a common midpoint pattern for non-negative indices, similar to array midpoint calculation. You can use `lo + ((fence - lo) >>> 1)` to clearly express the non-negative difference and avoid directly adding two large index values. In production code, validate `0 <= start <= end <= values.length` and prevent external code from modifying the array.

## 11. Ordering and Size Are Independent Characteristics

A spliterator can declare multiple bits:

```java
Spliterator.ORDERED
Spliterator.SIZED
Spliterator.SUBSIZED
Spliterator.IMMUTABLE
Spliterator.NONNULL
```

For an array snapshot, these flags make sense if data is controlled:

- `ORDERED`: has a fixed encounter order by array position.
- `SIZED`: remaining element count can be determined accurately.
- `SUBSIZED`: upon splitting, each branch continues to meet exact size requirements.
- `IMMUTABLE`: snapshot structure is not modified.
- `NONNULL`: no `null` elements.

`ConcurrentLinkedQueue` can declare `ORDERED`, `CONCURRENT`, `NONNULL` yet **not** `SIZED`, because when concurrent modification occurs, there is no exact-count contract via the spliterator at traversal time.

Do not infer `NONNULL => SIZED`, `IMMUTABLE => SORTED`, or `CONCURRENT => UNORDERED`: these are distinct properties. A snapshot containing `["z", "a"]` is immutable/non-null yet **not sorted** in lexicographical order. A concurrent queue can still state its own ordering characteristic.

### `getExactSizeIfKnown()` vs. `estimateSize()`

For a `SIZED` source, `getExactSizeIfKnown()` can return the exact remaining element count. For a non-`SIZED` source, it returns `-1`, even when `estimateSize()` still has an estimate or bound. Do not use the estimate as a verification contract that every element was processed exactly once when concurrent mutation exists.

## 12. Impact on the Stream API and Optimizations

`Spliterator` flags let the Stream library **understand more about the source**. They are not directives to "force fast execution." The JDK can use certain characteristics to optimize splitting, order preservation, or pipeline planning, depending on the operations and implementation.

Things to avoid:

1. **Do not rely on side effects in intermediate operations.** A terminal operation like `count()` can be optimized if the source/pipeline provides enough information; `map`/`peek` callbacks are not guaranteed to run just to execute side effects.
2. **Do not modify a source marked IMMUTABLE.** If this promise is broken, results can be wrong with no mandatory warning mechanism.
3. **Do not treat CONCURRENT as proof of stable results.** Data can appear/disappear during traversal, depending on source policy.
4. **Do not treat NONNULL as a filter.** Emitting null from a spliterator declaring NONNULL is a contract bug, not a situation Stream is supposed to fix for you.
5. **Do not treat parallel as a mandatory goal.** For small data or hard-to-split sources, overhead can be large; source structure, mapper cost, and downstream operations determine actual performance.

A pipeline with a `map` returning null can produce a result Stream containing null even when the source spliterator is `NONNULL`. A pipeline with `filter` can change the element count, so the source's sized characteristic does not mean every pipeline knows its result size upfront. You should not guess internal flags of the resulting spliterator after a pipeline without reading the corresponding operation's contract.

## 13. Common Mistakes When Declaring Characteristics

**Mistake 1 — marking `IMMUTABLE` on an array still being modified.** Only declare when ownership/snapshot guarantees the structure does not change. Having a `final` reference variable is not enough.

**Mistake 2 — confusing an unmodifiable view with a snapshot.** `Collections.unmodifiableList` prevents modification through the view, not through the backing list held by another object.

**Mistake 3 — marking `CONCURRENT` on a regular `ArrayList` or `HashMap`.** Setting a bit does not make a container concurrent-safe. Choose an appropriate structure and traversal policy.

**Mistake 4 — assuming `CONCURRENT` means every consumer is thread-safe.** The source may be concurrent, yet side effects in a lambda updating an external `ArrayList` can still cause data races.

**Mistake 5 — confusing `CONCURRENT` with a point-in-time snapshot.** Weakly consistent traversal does not mean a transactional snapshot.

**Mistake 6 — declaring `NONNULL` when data might contain null.** Generic `String` does not forbid null; validate or design data types that guarantee it.

**Mistake 7 — trusting the flag to validate data for you.** `Spliterators.spliterator(array, flags)` relies on characteristics supplied by the caller. You must prove them via source invariants and tests.

**Mistake 8 — thinking `IMMUTABLE` means every element is immutable.** A structurally unmodifiable list can still contain mutable objects.

**Mistake 9 — thinking `NONNULL` is preserved after every `map`.** A mapper can intentionally return null; downstream must have a policy.

**Mistake 10 — using `getExactSizeIfKnown()` as if every source is always SIZED.** For dynamic sources, it can return `-1`; check `SIZED` first.

**Mistake 11 — splitting in a way that loses or duplicates elements.** A custom `trySplit()` must partition non-overlappingly, preserve declared commitments, and keep accurate sizes if `SIZED`/`SUBSIZED` is present.

**Mistake 12 — attaching both `IMMUTABLE` and `CONCURRENT` out of habit.** The two flags state different structural modification policies; do not use them like an "enable all" option group.

**Mistake 13 — relying on fail-fast to catch every race.** `ConcurrentModificationException` is usually only a best-effort attempt to detect source modification bugs, not a synchronization mechanism.

**Mistake 14 — failing to test parallel execution behavior.** A spliterator with a broken `trySplit` can produce correct sequential results while losing/duplicating elements in parallel; test splitting, compare elements, and check total sizes.

## 14. Process for Designing a Safe Custom Source

Before implementing `Spliterator<T>`, answer these questions in order:

1. **Can the data source change structure during traversal?** If it cannot change, `IMMUTABLE` may fit. If it can be modified concurrently without external locking, a genuinely concurrent design is needed and `CONCURRENT` may be considered.
2. **Can the data contain null?** If so, do not declare `NONNULL` unless the spliterator itself filters/rejects null per a clear contract.
3. **Does the source have an encounter order?** If so, consider `ORDERED`. If not, do not promise an order the data lacks.
4. **Is the remaining element count known accurately?** Only when contractually true should you declare `SIZED` and possibly `SUBSIZED`.
5. **Can the source be split into independent ranges?** Design `trySplit` to neither lose nor duplicate elements, avoiding shared mutable cursor state.
6. **Who owns the data?** Are mutable references exposed externally? If so, defensive copying or clear synchronization/ownership is needed.
7. **What is the contract when concurrent changes occur?** Weak consistency, snapshot, visibility of added/removed elements, and error behavior must be clearly documented.
8. **Have tests verified actual behavior?** Do not just assert flag bits; compare sequential output, parallel output, sizes, splits, nulls, and the effects of data modification.
9. **Is writing a manual spliterator really necessary?** For arrays/snapshots or standard collections, prefer built-in JDK spliterators instead of increasing bug surface area.
10. **Are there side effects in mappers/consumers?** Design pipelines to be stateless/non-interfering, or control I/O, thread safety, and errors per requirements.

## 15. Practice Exercises

1. Modify `SnapshotWords` to accept a mutable `List<String>`, then modify the original List after creating the snapshot. Prove the snapshot Stream still returns the data from initialization time.
2. Try passing `null` in the list given to `SnapshotWords`. Explain why the exception comes from validation before the spliterator runs, not because the `NONNULL` flag auto-filters.
3. Write a `SnapshotWords` version using `List<Box>` where `Box` has a mutable field. Prove that modifying the field is not equivalent to adding/removing elements in the source, and note the risks when processing concurrently with Boxes being modified.
4. Obtain `ConcurrentLinkedQueue.spliterator()` and inspect the `CONCURRENT`, `NONNULL`, `ORDERED`, and `SIZED` flags. Explain why `SIZED` is not guaranteed for this dynamic source.
5. With a 100-element snapshot, call `trySplit()` repeatedly and traverse each branch. Verify every element appears exactly once, with no omissions or duplicates.
6. Suppose a custom `Spliterator` declares `NONNULL`, yet `tryAdvance` occasionally receives `null`. State the broken contract and two ways to fix it: validate at the source or drop the flag (when null is permitted).
7. Given mapper `s -> s.equals("x") ? null : s`, apply it to a NONNULL source Stream. Explain why the result can contain null.
8. Design a log source that continuously receives concurrent lines. Decide whether `CONCURRENT` with weakly consistent traversal fits an end-of-day report or if a consistent snapshot is needed.
9. Create a `SIZED`/`SUBSIZED` spliterator over an index range, checking the sizes of both branches after each split and after partial consumption.
10. Write a test comparing `StreamSupport.stream(sp, false)` and `StreamSupport.stream(newSp, true)` from two **fresh** spliterators of the same snapshot and compare results. Do not reuse a consumed spliterator.
11. Describe why a concurrency bug cannot be fixed merely by OR-ing `Spliterator.CONCURRENT` into the bitmask.
12. Give an example of immutable data that contractually contains null, and an example of concurrent data without null; explain why `NONNULL` is independent of the other two flags.

## 16. Summary

`IMMUTABLE`, `CONCURRENT`, and `NONNULL` are three characteristics **of the source described by the spliterator**, not transformations or automatic synchronization mechanisms:

- `IMMUTABLE`: the source is not structurally modified during traversal; does not mean elements are deeply immutable, nor does it create a snapshot automatically.
- `CONCURRENT`: the source allows concurrent structural modification without external locking; does not mean results are a snapshot, lambdas are thread-safe, or the same spliterator can be called arbitrarily from multiple threads.
- `NONNULL`: every source element emitted is non-null; does not forbid mappers from producing null or filter input data automatically.

When building custom sources, accurate flag declaration must stem from **ownership, mutability, concurrency contracts, and data validity**. If you control a non-null private snapshot, you can declare `IMMUTABLE | NONNULL`; if the source is genuinely concurrent like `ConcurrentLinkedQueue`, you can declare `CONCURRENT | NONNULL` per that source's contract. Test empty sources, parallel execution, splits, nulls, and intentional concurrent modifications, and do not turn thread-schedule-dependent output into fixed expectations.

An accurately declared spliterator helps Stream operate on true assumptions. A falsely declared flag bit can produce bugs harder to explain and detect than a clear exception.