# Designing a Spliterator from an Iterator with Known or Unknown Size

In the **Spliterators and Custom Sources** chapter of the **Java Stream API**, not every data source already provides a `Stream` or `Spliterator`. A legacy library might only return an `Iterator<T>`; a pagination system might fetch elements sequentially; a file reader might yield records without knowing the total record count upfront. To combine these sources with `filter`, `map`, `reduce`, `collect`, or parallel processing, you can **wrap the Iterator into a Spliterator** and pass it to `StreamSupport.stream(...)`.

The most critical choice is: **do you know the exact remaining element count or not?**

- **Known exactly**: use `Spliterators.spliterator(iterator, size, characteristics)`.
- **Not known exactly**: use `Spliterators.spliteratorUnknownSize(iterator, characteristics)`.

Both factories share the same wrapping goal yet carry different contracts regarding **size, `SIZED`/`SUBSIZED` characteristics, and optimization opportunities**. This lesson explains how to pick the right factory, declare characteristics honestly, understand `tryAdvance`/`trySplit`, and avoid pitfalls with counts, ordering, resources, or Iterator state.

**Java version:** `Spliterators`, `Spliterator`, and `StreamSupport` have existed since Java 8. Some examples use `List.of(...)` (Java 9+), `Path.of(...)` (Java 11+), and `Stream.toList()` (Java 16+). If studying on Java 8, substitute `Arrays.asList(...)`, `Paths.get(...)`, and `collect(Collectors.toList())` respectively; for anonymous classes `new Iterator<>()`, Java 8 requires explicit type arguments such as `new Iterator<Integer>()`.

## 1. How Do Iterator and Spliterator Differ?

`Iterator<T>` provides a basic sequential traversal interface:

~~~java
import java.util.Iterator;

Iterator<String> iterator = source.iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    // Process one element.
}
~~~

The two methods `hasNext()` and `next()` retrieve elements one by one. However, `Iterator` has no standard method to publish remaining element counts, split a source into sub-parts, or describe properties like `DISTINCT` or `ORDERED`.

`Spliterator<T>` extends the traversal model in a way better suited to the Stream API:

| Capability | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Request one element | `hasNext()` then `next()` | `tryAdvance(Consumer)` |
| Traverse remaining elements | `forEachRemaining(Consumer)` | `forEachRemaining(Consumer)` |
| Estimate remaining count | No common API | `estimateSize()` |
| Declare exact size | No common API | `SIZED` characteristic |
| Split work units | No common API | `trySplit()` |
| Declare order / source properties | No common API | `characteristics()`, `hasCharacteristics(...)` |

Example invoking a `Spliterator`:

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> split = List.of("A", "B", "C").spliterator();

split.tryAdvance(System.out::println);       // Prints A, returns true.
split.forEachRemaining(System.out::println);  // Prints B then C.
~~~

Both Iterator and Spliterator are **forward-only traversal** tools; neither automatically rewinds to the start once consumed. `Spliterator` also does not magically turn a sequential-only source into an efficiently splittable source merely by having a `trySplit()` method.

## 2. Two Iterator Factories to Distinguish

The `java.util.Spliterators` utility class provides two methods directly for `Iterator`:

~~~java
// Exact remaining element count known:
static <T> Spliterator<T> spliterator(
        Iterator<? extends T> iterator,
        long size,
        int characteristics);

// Exact remaining element count unknown:
static <T> Spliterator<T> spliteratorUnknownSize(
        Iterator<? extends T> iterator,
        int characteristics);
~~~

Once you have a `Spliterator<T>`, create a Stream via:

~~~java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Stream<T> stream = StreamSupport.stream(spliterator, false);
~~~

`false` requests a sequential pipeline; `true` requests parallel mode. Here `T` stands for the source's actual element type; these snippets illustrate generic signatures, while full examples below use concrete `String` and `Integer`.

### Comparison table

| Criterion | `spliterator(iterator, size, flags)` | `spliteratorUnknownSize(iterator, flags)` |
| --- | --- | --- |
| Length information | Caller provides **exact remaining element count** | No length information needed |
| Initial `estimateSize()` | Based on the supplied `size` | Uses unknown-size estimate, typically `Long.MAX_VALUE` |
| `SIZED` / `SUBSIZED` | Added per factory contract, except when `CONCURRENT` is declared | Does not declare `SIZED` or `SUBSIZED` |
| Usable with finite sources | Yes, when exact count is known | Yes, including finite sources |
| Usable with unbounded sources | Inappropriate without exact finite count | Can wrap, though terminal operation needs a stopping point |
| Work splitting capability | Can split in batches by buffering Iterator into arrays | Can also split in batches without knowing total count upfront |
| Main risk | Passing wrong `size` violates source contract | No optimizations based on exact size |

**Unknown size ≠ infinite source.** An Iterator might terminate after five elements yet expose no method revealing the number five beforehand. That is precisely when `spliteratorUnknownSize` should be used.

## 3. Case 1: Exact Size Known

Suppose you have an Iterator and independent metadata confirming the remaining element count. The simplest example is an Iterator freshly obtained from a list that will not be mutated during processing.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class KnownSizeIteratorDemo {
    public static void main(String[] args) {
        List<String> events = List.of(
                "INFO started",
                "ERROR timeout",
                "WARN slow",
                "ERROR denied"
        );

        Iterator<String> iterator = events.iterator();
        long remaining = events.size(); // Accurate when Iterator is created.

        Spliterator<String> split = Spliterators.spliterator(
                iterator,
                remaining,
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        System.out.println(split.hasCharacteristics(Spliterator.SIZED));
        // true

        System.out.println(split.hasCharacteristics(Spliterator.SUBSIZED));
        // true

        System.out.println(split.getExactSizeIfKnown()); // 4

        List<String> errors = StreamSupport.stream(split, false)
                .filter(line -> line.startsWith("ERROR"))
                .toList();

        System.out.println(errors);
        // [ERROR timeout, ERROR denied]
    }
}
~~~

Explanation of each factory argument:

1. `iterator` is the **traversal source**, consumed as the Spliterator or Stream requests elements.
2. `remaining = 4` is the **remaining element count**, not container capacity or previously generated totals.
3. `Spliterator.ORDERED` asserts the source has a list-based *encounter order*.
4. `Spliterator.NONNULL` fits because `List.of(...)` disallows `null`.
5. The known-size factory normally declares `SIZED` and `SUBSIZED`, giving downstream stages extra planning metadata.

This example illustrates the factory; in real programs, when you already hold a `List`, calling `events.stream()` or `events.spliterator()` directly is more natural. Wrapping an Iterator adds value when a source exposes only an Iterator API.

### Size must be the **remaining** element count

Suppose a list has five elements, yet the Iterator has already yielded two:

~~~java
List<Integer> values = List.of(10, 20, 30, 40, 50);
Iterator<Integer> it = values.iterator();

it.next(); // Already took 10.
it.next(); // Already took 20.

// Iterator now only has 30, 40, 50 left.
Spliterator<Integer> rest = Spliterators.spliterator(
        it,
        3L,
        Spliterator.ORDERED | Spliterator.NONNULL
);
~~~

Passing `5L` to the factory at this point is a **false declaration**. If you no longer know the exact untraversed count, using `spliteratorUnknownSize` is safer than guessing.

> **Rule:** "Known size" holds only when the supplied count accurately reflects remaining elements per source contract, not an estimate or stale metadata.

## 4. Why Is Reporting a Wrong Size Dangerous?

A `SIZED` `Spliterator` guarantees its size under the API contract; a Stream is entitled to use this information for optimizations.

Example **to avoid**:

~~~java
// Wrong: Iterator actually contains only three elements.
Iterator<Integer> it = List.of(1, 2, 3).iterator();

Spliterator<Integer> wrong = Spliterators.spliterator(
        it,
        100L, // Incorrect remaining element count.
        Spliterator.ORDERED
);
~~~

If you build a Stream from `wrong` and call `count()`, some JDK implementations or versions may rely on `SIZED` metadata instead of traversing every element, so results or behavior may diverge from the actual source. Combined with `limit`, `skip`, parallel execution, or array-backed collection, a wrong size can also invalidate internal assumptions.

You do not need to assert which specific method *always* returns wrong values across every JDK to see the flaw: **the Spliterator specification itself has been violated**.

Situations prone to producing wrong counts:

- Passing the initial size after already calling `next()` several times.
- Sources that can add/remove items during traversal.
- Reading a "total record count" metadata field when the Iterator only returns records passing an internal filter.
- Pagination API counts that are approximations rather than exact final totals.
- Treating buffer allocation limits as remaining element counts.

When you only know an **upper bound** or expected count, never pass that number as an exact size to a `SIZED`-reporting factory.

## 5. Case 2: Element Count Unknown Upfront

Suppose an Iterator emits odd numbers until exhausted. The Iterator consumer does not need to know the total count upfront to begin traversing.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class UnknownSizeIteratorDemo {
    public static void main(String[] args) {
        Iterator<Integer> odds = new Iterator<>() {
            private int current = 1;

            @Override
            public boolean hasNext() {
                return current <= 9;
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                int value = current;
                current += 2;
                return value;
            }
        };

        Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
                odds,
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        System.out.println(split.hasCharacteristics(Spliterator.SIZED));
        // false

        System.out.println(split.getExactSizeIfKnown());
        // -1

        List<Integer> result = StreamSupport.stream(split, false).toList();

        System.out.println(result); // [1, 3, 5, 7, 9]
    }
}
~~~

The factory requires no `size`. Even though the sample source actually stops after **five** elements, the Spliterator **does not publish an exact count in advance**. The Stream still consumes elements one by one until the Iterator reports `hasNext() == false`.

If the source can block while fetching the next element, `spliteratorUnknownSize` does not add timeouts or read limits automatically. Similarly, if the Iterator is truly infinite, `collect` or `toList` cannot terminate by exhausting it. Add a finite stopping condition like `limit(n)` when appropriate for the problem.

### Do not attach SIZED to an unknown-size source

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        odds,
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
);
~~~

The `spliteratorUnknownSize` factory strips any `SIZED` and `SUBSIZED` flags that a caller might pass in. Passing those two flags does not turn the source into a known-size source.

Clearer code:

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        odds,
        Spliterator.ORDERED | Spliterator.NONNULL
);
~~~

Only publish characteristics genuinely guaranteed by the source.

## 6. How Do SIZED, SUBSIZED, and estimateSize Differ?

`SIZED` and `SUBSIZED` are **characteristics**, whereas `estimateSize()` is a method on `Spliterator`.

| Concept | Meaning |
| --- | --- |
| `estimateSize()` | Estimates remaining elements; may be approximate or `Long.MAX_VALUE` when unknown or no finite bound is known. |
| `SIZED` | Declares that the size estimate is exact per contract absent structural source changes. |
| `SUBSIZED` | Declares that this Spliterator and all Spliterators split from it also have `SIZED`. |
| `getExactSizeIfKnown()` | Returns the size if `SIZED` is present; otherwise returns `-1`. |

For the factory wrapping a **known-size** Iterator, `SIZED` and `SUBSIZED` are generally added automatically, except when `CONCURRENT` is supplied per factory contract. For the **unknown-size** factory, `SIZED`/`SUBSIZED` are never declared.

For an unknown-size Spliterator, `Long.MAX_VALUE` typically acts as a *sentinel* for undetermined size, **not proof that the source literally contains 9.22 × 10¹⁸ elements** or is infinite.

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        List.of(1, 2, 3).iterator(),
        Spliterator.ORDERED
);

System.out.println(split.estimateSize() == Long.MAX_VALUE); // true
System.out.println(split.getExactSizeIfKnown());             // -1
~~~

In the example above, the Iterator has only three elements. `estimateSize()` is undetermined because the factory was not given a size, not because the source never ends.

Never write business logic like "allocate an array of exact length `estimateSize()`" when `SIZED` is absent. For large sources, even with `SIZED`, evaluate array length limits and memory capacity before materializing an entire Stream.

## 7. Choosing Characteristics Honestly

The `characteristics` argument is a bit-flag combination, such as `Spliterator.ORDERED | Spliterator.NONNULL`. Do not pile on as many flags as possible; **every flag is a commitment made by the source**.

| Characteristic | Declare Only When | Note |
| --- | --- | --- |
| `ORDERED` | Source has a defined encounter order | A `List` Iterator is ordered; a `HashSet` Iterator has no guaranteed traversal order. |
| `NONNULL` | No element is `null` | If `null` can appear, omit this flag. |
| `DISTINCT` | No two elements are duplicates per source equality rules | Do not attach to event logs that may repeat values. |
| `IMMUTABLE` | Source cannot be structurally modified during traversal per contract | Not equivalent to "caller promises not to edit" if the source itself is mutable without guarantees. |
| `CONCURRENT` | Source is designed to accept concurrent edits during traversal | Do not set merely because the Stream will call `parallel()`. |
| `SORTED` | Source follows a sort order per Spliterator contract | Must pair with `getComparator()`; do not attach just because data looks sorted. |
| `SIZED` | Exact remaining element count is known | Known-size factory manages this per contract; never attach to estimates. |
| `SUBSIZED` | Every split part also reports exact size | Cannot be inferred if splitting is arbitrary without preserving exact sizes. |

Example of an ordered event-code source that may contain `null` and duplicate records:

~~~java
int characteristics = Spliterator.ORDERED;
// Do not declare NONNULL, DISTINCT, or SORTED unless guaranteed.
~~~

If each element is guaranteed never to be `null`:

~~~java
int characteristics = Spliterator.ORDERED | Spliterator.NONNULL;
~~~

### Note on mutable sources

A Spliterator wrapped around an `Iterator` inherits that Iterator's constraints. If the underlying collection is modified while the Stream is traversing it, behavior depends on the collection/iterator contract: `ConcurrentModificationException` may be thrown, weakly consistent data may be observed, or results may become undefined.

**There is no thread-safety "magic" from `Spliterators`.** Only declare `CONCURRENT` if the source genuinely upholds those semantics. For ordinary sources, avoid modifying the collection during traversal and avoid concurrent access from multiple threads to the same Iterator.

## 8. tryAdvance: Bridging from Iterator to Pull-Based Elements

`Spliterator.tryAdvance(action)` invokes `action` for the next element if one exists and returns `true`; when data is exhausted, it returns `false`.

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

List<Integer> values = List.of(10, 20, 30);

Spliterator<Integer> split = Spliterators.spliterator(
        values.iterator(),
        values.size(),
        Spliterator.ORDERED | Spliterator.NONNULL
);

boolean firstFound = split.tryAdvance(System.out::println);
// Prints 10, firstFound == true.

split.forEachRemaining(System.out::println);
// Prints 20 and 30.

boolean more = split.tryAdvance(System.out::println);
// false
~~~

`tryAdvance` does not synthesize a new element; it pulls the next element from the wrapped Iterator. Once called one or more times, the Iterator **has been consumed** accordingly. Creating a Stream afterward from the same Spliterator only sees the untraversed remainder—it cannot "replay" from the start.

The reason the Stream API is pull-based is so terminal operations can request data on demand and stop at appropriate conditions, such as `findFirst` or `limit`. Still, stateful operations like `sorted` may need to inspect many elements before emitting output.

## 9. trySplit: Batch Splitting Without Reversing the Iterator

`trySplit()` attempts to split off a portion of data into a new Spliterator for independent processing. It may return `null` when splitting is impossible or not worthwhile.

Factories wrapping an Iterator typically must **sequentially read a batch of elements from the Iterator into an array** to construct a splittable chunk. Because an Iterator lacks random access, this split is not equivalent to index-range splitting.

~~~text
Original Iterator:
  A -> B -> C -> D -> E -> F -> ...

trySplit():
  Reads a batch from Iterator into an array: [A, B, C]
  Returns split Spliterator for batch [A, B, C]
  Original Spliterator keeps unread part: D -> E -> F -> ...
~~~

Actual batch sizes and splitting strategies are implementation-defined; the diagram above is illustrative. Never write business logic dependent on chunk sizes or the number of `trySplit()` calls.

~~~java
Spliterator<Integer> original = Spliterators.spliterator(
        List.of(1, 2, 3, 4, 5, 6).iterator(),
        6,
        Spliterator.ORDERED | Spliterator.NONNULL
);

Spliterator<Integer> prefix = original.trySplit();

if (prefix != null) {
    prefix.forEachRemaining(System.out::println);
}
original.forEachRemaining(System.out::println);
~~~

If the Spliterator has an encounter order, the part returned by `trySplit()` is a **prefix** of the split data. Traversing the prefix before the remainder, as shown, reconstructs element order. However, `trySplit` is **not required** to return a split in every situation.

### Impact on parallel streams

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        sourceIterator,
        Spliterator.ORDERED
);

long sum = StreamSupport.stream(split, true)
        .mapToLong(Integer::longValue)
        .sum();
~~~

`true` requests a parallel Stream, yet **does not guarantee higher speed**. Splitting an Iterator may require sequential reads to build batches, incurring array allocations and task synchronization. If the source is mostly slow I/O or per-element processing is trivial, this overhead can exceed any benefit.

If a source permits chunked or indexed access, a custom Spliterator whose `trySplit()` divides index ranges may perform better. That is a separate source-design problem, though; do not over-engineer a custom Spliterator when a standard wrapper suffices.

## 10. Near-Real-World Example: Unknown-Size File Token Source

Suppose an application receives a text file with an undetermined number of tokens. `Scanner` implements `Iterator<String>` and also needs to be closed when backed by a file. We can wrap `Scanner` into an unknown-size Spliterator and filter tokens.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class ScannerIteratorSourceDemo {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("events.txt");

        try (Scanner scanner = new Scanner(
                input, StandardCharsets.UTF_8.name())) {

            Spliterator<String> split =
                    Spliterators.spliteratorUnknownSize(
                            scanner,
                            Spliterator.ORDERED | Spliterator.NONNULL
                    );

            long errors = StreamSupport.stream(split, false)
                    .filter(token -> token.equalsIgnoreCase("ERROR"))
                    .count();

            System.out.println("ERROR token count: " + errors);
        }
    }
}
~~~

Key points in this example:

- `Scanner` does not know how many tokens exist until traversal finishes.
- `spliteratorUnknownSize` avoids fabricating a non-existent exact size.
- `StreamSupport.stream(split, false)` enables Stream API operations on the Iterator source.
- `try-with-resources` closes the **file-owning `Scanner`** when processing finishes or throws an exception.
- `Scanner` splits tokens by its default delimiter (typically whitespace); the example **counts tokens**, not lines. To process lines, use `Files.lines` with `try-with-resources`.

Closing a Stream created from an arbitrary Iterator **does not automatically close the underlying resource** without an appropriate close handler. Here `Scanner` is closed explicitly because `Scanner` owns the I/O resource.

If the source is an HTTP cursor or database cursor, the same principle holds: **lifecycle ownership** must be explicit; merely converting to a Spliterator does not ensure the cursor is released.

## 11. Known Size Does Not Mean Materializing All Data

Knowing `size` upfront only supplies metadata; wrapping an Iterator does not mean all elements are immediately loaded into a List.

~~~java
Spliterator<String> split = Spliterators.spliterator(
        iterator,
        exactRemainingCount,
        Spliterator.ORDERED
);

long matches = StreamSupport.stream(split, false)
        .filter(value -> value.startsWith("A"))
        .count();
~~~

In this example, `iterator` must be an `Iterator<String>` source and `exactRemainingCount` must be a `long` representing the exact remaining element count. The Stream can pull elements lazily; `filter` processes data only as the terminal operation demands.

However, if parallelism is enabled, `trySplit` may allocate **batch buffer arrays** to split the Iterator. Operations like `sorted` or `toList` can also retain many elements in memory. Never assume an "Iterator-backed source" guarantees constant memory usage.

If you already hold a `Collection<T>`, prefer `collection.stream()` or `collection.spliterator()`. A Collection can provide a Spliterator tailored to its data structure, avoiding the Iterator wrapping layer.

## 12. One Source, Single Pass, and State Management

An Iterator is typically a **stateful** object. Each `next()` call advances the source by one step. A Spliterator wrapping an Iterator inherits that property:

~~~java
Iterator<String> it = List.of("a", "b", "c").iterator();

Spliterator<String> split = Spliterators.spliteratorUnknownSize(
        it, Spliterator.ORDERED
);

List<String> first = StreamSupport.stream(split, false).toList();
// [a, b, c]

// Never build a new Stream from the same consumed Spliterator expecting to re-read.
~~~

A Stream itself also supports only one terminal operation. When you need two independent aggregations, you can:

1. Read once into a finite list (if memory permits), then create new Streams from that list.
2. Use a single collector combining multiple metrics in one pass.
3. If the source can be reopened, **create a new Iterator** for the second pass and manage closing each source properly.

Do not use one Iterator to "pre-count" and then "traverse later" if the Iterator cannot be recreated. Doing so can leave the Stream seeing only the tail, or invalidate the declared size.

## 13. Invariants to Verify When Designing Custom Sources

Even when using standard factories, the application author remains responsible for the input data and declared flags.

### 13.1. Iterator invariants

A normal Iterator must satisfy:

- `hasNext()` indicates whether `next()` can return another element.
- `next()` returns an element if available; once exhausted, it must throw `NoSuchElementException`.
- If `remove()` is supported, never call it arbitrarily while a Stream is processing the same source.
- Never mutate the source externally in ways that violate the Iterator contract, especially under parallel execution.
- If backed by I/O or a cursor, manage resources independently of traversal.

### 13.2. Spliterator invariants

For a known-size Spliterator:

- `size` describes **the exact remaining element count at wrap time**, per the source's contract.
- `SIZED`/`SUBSIZED` must align with how the source is traversed and split.
- `ORDERED`, `NONNULL`, and other flags are declared only when genuinely true.
- `trySplit` may return `null`; Spliterator callers must not treat that as an error.
- Reading remaining parts must supply **the exact set of elements to traverse**, without duplicating or skipping items across splits.
- There is no guarantee that the Stream will call `tryAdvance`, `trySplit`, or mappers a specific number of times expected by the application if those side effects are unspecified.

For an unknown-size Spliterator, the same rules apply, except you must not assume an exact count for optimization.

## 14. Decision Table: Choosing How to Adapt a Source

| Situation | Choice | Reason |
| --- | --- | --- |
| Already have `List<T>` or `Collection<T>` | `collection.stream()` | Source already supports Stream; no Iterator wrapping needed. |
| Legacy API returns only Iterator, with exact metadata for remaining count | `spliterator(iterator, size, flags)` | Exact size can be safely declared. |
| API returns only Iterator, remaining count unknown upfront | `spliteratorUnknownSize(iterator, flags)` | Avoids making false `SIZED` promises. |
| Only an upper bound or forecast count is known | `spliteratorUnknownSize(iterator, flags)` | An estimate is not an exact size. |
| Iterator partially consumed while only initial size is known | `spliteratorUnknownSize(...)` or recompute exact remaining count | Never pass stale initial count as `size`. |
| Need efficient parallel processing on an index-splittable source | Consider a custom Spliterator | Iterator wrappers usually batch-buffer elements. |
| Source backed by file, Scanner, socket, or cursor | Wrap appropriately **and** manage AutoCloseable resource | `StreamSupport` does not auto-release arbitrary Iterator resources. |
| Unbounded source where only N elements are needed | `spliteratorUnknownSize(...)`, then `limit(N)` | Establishes a finite boundary for the terminal operation. |

## 15. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Strange `count()` results or pipeline skips elements | Used `spliterator(iterator, size, ...)` with inaccurate `size` | Pass exact remaining count only; if unsure, use `spliteratorUnknownSize`. |
| `getExactSizeIfKnown()` returns `-1` even though source is finite | Factory was not supplied an exact size | Expected behavior; do not force `SIZED`. |
| `estimateSize()` returns `Long.MAX_VALUE` | Size is unknown | Do not treat as actual count or necessarily infinite. |
| Some elements missing after creating Stream | Iterator had `next()` called prior to wrapping | Wrap from current position with updated remaining count. |
| Output changes after modifying source collection | Violates source stability or Iterator semantics | Avoid mutating source during traversal; snapshot when needed. |
| Output order breaks assumptions | Misdeclared `ORDERED` or used unordered source | Declare order only when guaranteed by source, or call `sorted` as needed. |
| Slower with `parallel()` | Iterator Spliterator splits via batch reads and array allocation | Benchmark; prefer direct Collection Stream or index-splitting Spliterator if needed. |
| File/cursor left open after collecting results | Only closed the Iterator-wrapping Stream, not the I/O source | Put original resource in `try-with-resources` or define explicit close handler/ownership. |
| Terminal operation hangs | Non-terminating Iterator or blocking pull operation | Bound input and configure timeouts/cancellation at the source layer. |
| `null` appears despite `NONNULL` | Characteristic flag mismatched data | Remove flag or validate/sanitize source per contract. |

## 16. Self-Check Exercises

### Exercise 1 — Choosing the right factory

An API returns `Iterator<Event>`. The API explicitly reports 2,500 remaining records, none consumed yet, and the source will not mutate during reading. Which factory should you choose?

**Answer:** `Spliterators.spliterator(iterator, 2_500L, characteristics)`, where `characteristics` includes only properties genuinely guaranteed by the API. If the Iterator has a fixed encounter order, `Spliterator.ORDERED` can be supplied. Do not add `NONNULL` if the source can still return `null`.

### Exercise 2 — Does Long.MAX_VALUE prove infinity?

~~~java
var split = Spliterators.spliteratorUnknownSize(
        List.of("A", "B").iterator(), Spliterator.ORDERED
);

System.out.println(split.estimateSize());
~~~

**Answer:** No. The Spliterator has unknown size so it can report `Long.MAX_VALUE`, yet this source clearly has only two elements. That value represents **lack of size information**, not the actual element count.

### Exercise 3 — Partially consumed Iterator

~~~java
List<String> values = List.of("a", "b", "c", "d");
Iterator<String> iterator = values.iterator();

iterator.next();
iterator.next();
~~~

**Question:** If wrapping this Iterator with a known size, what value should be passed?

**Answer:** Pass `2L` because only `"c"` and `"d"` remain. If the application cannot compute the exact remaining count, use `spliteratorUnknownSize`.

### Exercise 4 — Declaring characteristics

An Iterator reads IDs that may repeat, may contain `null`, and have no guaranteed order. May you attach `ORDERED | DISTINCT | NONNULL`?

**Answer:** No. All three flags violate the source contract. Use `0` if no other characteristic is proven. A single run returning data in some order is not enough to make that order a contract.

### Exercise 5 — Processing data with a Stream

~~~java
Iterator<Integer> iterator = List.of(1, 2, 3).iterator();

Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        iterator, Spliterator.ORDERED | Spliterator.NONNULL
);

int sum = StreamSupport.stream(split, false)
        .mapToInt(Integer::intValue)
        .sum();
~~~

**Question:** What is the result? Is `SIZED` required for `sum` to be correct?

**Answer:** `sum = 6`. `SIZED` is not required for accurate summation. `SIZED` is size metadata for contracts and potential optimizations, not a prerequisite for addition.

### Exercise 6 — Why isn't parallel automatically faster?

**Question:** An Iterator reads network data sequentially. Will wrapping it with `spliteratorUnknownSize` and running a parallel Stream definitely be faster?

**Answer:** No. Splitting an Iterator may require sequential reads to form batches; blocking network I/O and lightweight lambdas can cause parallelism to merely add overhead. Improving throughput requires examining source splittability, I/O costs, connection limits, and benchmarking on real data.

### Exercise 7 — Who closes the source?

A file-reading `Scanner` is wrapped into a Spliterator and then into a Stream. After `count()`, is the file guaranteed to be closed?

**Answer:** No. `count()` is only a terminal operation; `StreamSupport.stream(...)` does not establish a closing contract for the Scanner. Place the Scanner in `try-with-resources` and execute the entire pipeline while the Scanner remains open.

## 17. Remember

- `Spliterators.spliterator(iterator, size, characteristics)` is for an Iterator with an **exact remaining element count**; the factory normally adds `SIZED` and `SUBSIZED` when `CONCURRENT` is absent.
- `Spliterators.spliteratorUnknownSize(iterator, characteristics)` is for sources with an **unknown element count**; it never declares `SIZED`/`SUBSIZED`, even when the source is actually finite.
- `estimateSize() == Long.MAX_VALUE` does not mean the source is necessarily infinite; `getExactSizeIfKnown() == -1` means the Spliterator does not guarantee an exact size.
- Declare `ORDERED`, `NONNULL`, `DISTINCT`, `IMMUTABLE`, or `CONCURRENT` **only when true to the source's contract**. False flags can cause unreliable optimizations and results.
- `tryAdvance` pulls further from the Iterator; `trySplit` on an Iterator wrapper may pre-read and buffer batches into arrays to split work.
- `StreamSupport.stream(split, parallel)` connects a Spliterator to the Stream API; `parallel = true` does not automatically guarantee performance or thread safety.
- Streams and Iterators are normally single-pass; I/O-backed sources require explicit closing mechanisms such as `try-with-resources`.
- When the source is already a Collection with a suitable Stream/Spliterator, **prefer using it directly** rather than wrapping an Iterator.

**Key takeaway:** Designing a Spliterator from an Iterator is not just picking a factory. You must **know whether you truly know the remaining count, declare characteristics accurately, understand batch-splitting limits, and take responsibility for source lifecycle management**. When those contracts hold, the Stream API can apply lazy pipelines, filtering, mapping, reduction, and collection even to Iterator-only sources.
