# Converting Iterable, Iterator, and Spliterator to Stream

> **Chapter:** Streams from Existing Data  
> **Module:** JAVA_STREAM_API  
> **Goal:** Properly convert traversal-only data sources into `Stream<T>`, understanding differences in ordering, size, lifecycle, and parallel processing capability.

When working with the Java Stream API, we usually start with `list.stream()`. In real projects, however, a library, legacy API, or data-processing component may only provide an `Iterable<T>`, `Iterator<T>`, or `Spliterator<T>`. These sources can still participate in declarative pipelines with `filter`, `map`, `reduce`, `collect`, and other operations. The key is **converting the traversal mechanism properly** and **not attributing guarantees to a source that it does not actually uphold**.

This lesson belongs to the **JAVA_STREAM_API** module, where lazy pipelines, grouping, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers all depend on how elements flow from the source through operations. Understanding these three source types helps avoid reusing consumed sources, losing order, mismanaging resources, or holding unrealistic parallel performance expectations.

The basic examples use Java 17 or later for `List.of(...)` and `Stream.toList()`. Conversion via `StreamSupport` and `Spliterators` has been available since Java 8; if using Java 8, replace `.toList()` with `.collect(Collectors.toList())` when collecting a list.

## 1. The Big Picture

```text
Collection<T> ───────────────────────────────► collection.stream()
        │
        └── implements Iterable<T>

Iterable<T> ─── iterable.spliterator() ──┐
                                         │
Iterator<T> ─── Spliterators.            ├──► StreamSupport.stream(
                 spliteratorUnknownSize()│         spliterator, false)
                                         │                 │
Spliterator<T> ──────────────────────────┘                 ▼
                                               Stream<T> pipeline
                                           filter → map → collect
```

`Iterable`, `Iterator`, and `Spliterator` all relate to traversing elements, yet they are not identical:

| Type | Primary capability | Has a direct `stream()` method? | Common conversion approach |
| --- | --- | --- | --- |
| `Collection<T>` | Holds elements, provides iterator and spliterator | **Yes** | `collection.stream()` |
| `Iterable<T>` | Has `iterator()`, can usually provide a fresh traversal pass | **No** | `StreamSupport.stream(iterable.spliterator(), false)` |
| `Iterator<T>` | Sequential traversal via `hasNext()` / `next()`; usually a single-use cursor | **No** | Wrap with `Spliterators.spliteratorUnknownSize(...)`, then `StreamSupport.stream(...)` |
| `Spliterator<T>` | Traverses and can split an element range into parts for processing | **No** | `StreamSupport.stream(spliterator, false)` |

**Important distinction:** Every `Collection` is an `Iterable`, but an `Iterable` is not necessarily a `Collection`. If a variable is declared as `Iterable<String>`, the compiler does not allow calling `.stream()` based on that declared type alone, even if the runtime object happens to be a `List`.

## 2. Core APIs: StreamSupport and Spliterators

The main components reside in `java.util` and `java.util.stream`:

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;
```

Two commonly used overloads of `StreamSupport.stream`:

```java
// Create a Stream from an existing Spliterator:
static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
);

// Supply a Spliterator when execution begins:
static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
);
```

Two helper methods for creating a `Spliterator` from an `Iterator`:

```java
// When the exact number of remaining elements is unknown:
static <T> Spliterator<T> spliteratorUnknownSize(
    Iterator<? extends T> iterator,
    int characteristics
);

// When the exact number of elements to traverse is known:
static <T> Spliterator<T> spliterator(
    Iterator<? extends T> iterator,
    long size,
    int characteristics
);
```

These are simplified signatures for learning usage; the corresponding classes provide additional overloads.

Meaning of the main arguments:

- `spliterator`: object describing how to pull elements from the source.
- `parallel=false`: starts as a sequential Stream; `true` requests parallel mode.
- `characteristics`: bitmask of flags describing the source's guarantees; only declare flags true for the data.
- `supplier`: a way to create/obtain the `Spliterator` when the Stream starts executing, useful for deferring binding to the source.
- `size`: exact known count of remaining elements, not an estimate.

In practice, **`StreamSupport.stream(...)` is the bridge**, while `Spliterators` provides utilities to construct a `Spliterator` when a source only exposes an `Iterator`.

## 3. Converting Iterable to Stream

### 3.1. Shortest Approach

`Iterable<T>` has had a `spliterator()` method since Java 8. Therefore:

```java
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class IterableExample {
    public static void main(String[] args) {
        List<String> source = List.of("  Java  ", " ", " Stream ", " API ");

        // Declared as Iterable, as when an API only returns Iterable<T>.
        Iterable<String> items = () -> source.iterator();

        Stream<String> stream = StreamSupport.stream(
            items.spliterator(),
            false
        );

        List<String> result = stream
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();

        System.out.println(result); // [Java, Stream, API]
    }
}
```

Explanation:

1. `items.iterator()` supplies an `Iterator<String>` whenever requested.
2. `items.spliterator()` creates a traversal object compatible with Stream.
3. `StreamSupport.stream(..., false)` turns that traversal mechanism into a sequential `Stream<String>`.
4. `map` and `filter` are intermediate operations; `toList` is the terminal operation that causes the pipeline to execute.

No intermediate collection is created just to move data into a Stream. This conversion is usually better than writing a loop, adding all elements into an `ArrayList`, and only then calling `list.stream()`.

### 3.2. When the Source Is Already a Collection, Use the Direct API

Example:

```java
List<Integer> numbers = List.of(2, 4, 6, 8);

long direct = numbers.stream()
    .filter(n -> n > 4)
    .count(); // 2
```

`List` is a `Collection`, so it has `stream()`. This is clearer than `StreamSupport.stream(numbers.spliterator(), false)` when no custom traversal mechanism is needed.

If an API declares its return type as `Iterable<T>`, do not cast to `Collection<T>` without a guarantee that the object implements that interface:

```java
Iterable<String> items = obtainItems();

// Works for any valid Iterable:
Stream<String> stream = StreamSupport.stream(
    items.spliterator(),
    false
);
```

`obtainItems()` is a hypothetical library method. To run standalone, replace it with a concrete `Iterable` like in the example above.

### 3.3. Can an Iterable Always Be Traversed Again?

You cannot conclude that an arbitrary `Iterable` is repeatable merely from the interface name. The `Iterable` contract only provides `iterator()`; whether each call actually creates a fresh traversal pass depends on the implementation.

Example of a commonly repeatable `Iterable`:

```java
List<String> source = List.of("An", "Bình");
Iterable<String> repeatable = () -> source.iterator();

long count = StreamSupport.stream(
    repeatable.spliterator(), false
).count();

List<String> names = StreamSupport.stream(
    repeatable.spliterator(), false
).toList();

// count = 2; names = [An, Bình]
```

Above, **each pass creates a new Stream** backed by a fresh traversal. Conversely, an adapter that returns the same existing `Iterator` may only work for a single pass:

```java
Iterator<String> cursor = List.of("An", "Bình").iterator();
Iterable<String> oneShot = () -> cursor;

// Do not assume oneShot can be read again after the iterator is exhausted.
```

Even when an `Iterable` is repeatable, **each `Stream` object is still single-use**.

### 3.4. Notes on Ordering in Custom Iterables

The default `Iterable.spliterator()` typically wraps the iterator in a `Spliterator` of unknown size and **does not declare the `ORDERED` flag**. This differs from `List.spliterator()`, which carries clearer information about size and order.

When a custom `Iterable` class has a guaranteed traversal order, you can state the contract explicitly by providing an appropriate `spliterator()`:

```java
List<String> source = List.of("An", "Bình", "Chi");

Iterable<String> orderedItems = new Iterable<>() {
    @Override
    public Iterator<String> iterator() {
        return source.iterator();
    }

    @Override
    public Spliterator<String> spliterator() {
        return source.spliterator();
    }
};

List<String> firstTwo = StreamSupport.stream(
    orderedItems.spliterator(), false
).limit(2).toList(); // [An, Bình]
```

The snippet above requires importing `java.util.Iterator` and `java.util.Spliterator`. Overriding leverages the exact characteristics of `List.spliterator()`. Do not declare `ORDERED` on a source that has no guaranteed order.

## 4. Converting Iterator to Stream

`Iterator<T>` only knows how to traverse via `hasNext()` and `next()`; it has neither `spliterator()` nor `stream()`. We must wrap it:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class IteratorExample {
    public static void main(String[] args) {
        Iterator<String> iterator =
            List.of("java", "stream", "api").iterator();

        Spliterator<String> spliterator =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );

        Stream<String> stream =
            StreamSupport.stream(spliterator, false);

        List<String> result = stream
            .map(String::toUpperCase)
            .filter(s -> s.length() >= 4)
            .toList();

        System.out.println(result); // [JAVA, STREAM]
    }
}
```

`spliteratorUnknownSize` fits because the `Iterator` type does not expose the remaining element count. In the example, we know the iterator draws elements from `List.of` in order and none are `null`, so we can declare `ORDERED | NONNULL`.

If the source is an arbitrary iterator from a third-party library whose characteristics are unverified, passing `0` is the safe choice:

```java
Iterator<String> iterator = getLegacyIterator();

Stream<String> stream = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(iterator, 0),
    false
);
```

`getLegacyIterator()` here represents a legacy application API. Passing `0` means asserting no extra characteristics, not that the data is empty.

### 4.1. An Iterator Is a Traversal Position, Not a Data Store

Consider the example:

```java
Iterator<Integer> iterator = List.of(10, 20, 30).iterator();

Stream<Integer> stream = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED),
    false
);

int sum = stream.mapToInt(Integer::intValue).sum(); // 60

// Do not reuse the same stream:
// long count = stream.count(); // IllegalStateException
```

Once `sum()` completes, the Stream has been consumed. At the same time, the underlying iterator is usually at its end, so **wrapping that same iterator again** will not restore the elements.

```java
// You can create a new iterator if the underlying source is re-traversable:
List<Integer> numbers = List.of(10, 20, 30);

long count = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        numbers.iterator(), Spliterator.ORDERED
    ),
    false
).count(); // 3
```

For an iterator pulling data from a socket, database query, or paginated API, there may be no cheap or safe way to re-traverse. Plan to consume it once.

### 4.2. If the Exact Element Count Is Known

When an API supplies both an iterator **and the exact number of remaining elements**, you can use `Spliterators.spliterator(iterator, size, characteristics)`:

```java
List<String> source = List.of("An", "Bình", "Chi");

Iterator<String> iterator = source.iterator();
long exactSize = source.size();

Spliterator<String> spliterator = Spliterators.spliterator(
    iterator,
    exactSize,
    Spliterator.ORDERED | Spliterator.NONNULL
);

long count = StreamSupport.stream(spliterator, false).count(); // 3
```

This example illustrates the `size` overload; with a real `List`, `source.stream()` remains the simpler choice.

**Only provide `size` if you are certain it is exact.** Some terminal operations such as `count()` can use size metadata to optimize without reading elements. Declaring an inaccurate size can produce wrong results, break API assumptions, or compromise correctness in parallel execution. If the size is uncertain, use `spliteratorUnknownSize`.

## 5. Converting Spliterator to Stream

`Spliterator<T>` is the lower-level interface used by Streams to pull elements and optionally split traversal. If a source already provides a `Spliterator`, there is no need to wrap it again with `Spliterators`:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

class SpliteratorExample {
    public static void main(String[] args) {
        List<String> words = List.of("stream", "lambda", "collect");
        Spliterator<String> cursor = words.spliterator();

        List<Integer> lengths = StreamSupport.stream(cursor, false)
            .map(String::length)
            .toList();

        System.out.println(lengths); // [6, 6, 7]
    }
}
```

In real programs, a `Spliterator` object might be returned by a library, a custom class, or a collection. Calling `StreamSupport.stream(cursor, false)` enables the entire ecosystem of Stream operations on this source.

### 5.1. Key Methods of Spliterator

| Method | Purpose |
| --- | --- |
| `tryAdvance(Consumer<? super T> action)` | Takes at most one next element, returning `true` if one was obtained. |
| `forEachRemaining(Consumer<? super T> action)` | Executes an action on the remaining elements. |
| `trySplit()` | Attempts to partition a portion of the traversal range for independent processing; may return `null`. |
| `estimateSize()` | Estimates the number of unvisited elements; may be `Long.MAX_VALUE`. |
| `characteristics()` | Returns the bitmask of guaranteed characteristics. |
| `hasCharacteristics(int characteristics)` | Checks whether a given set of characteristics is present. |
| `getExactSizeIfKnown()` | Returns exact size when `SIZED` is present, otherwise `-1`. |

Example inspecting a `Spliterator` before passing it into a Stream:

```java
List<Integer> numbers = List.of(10, 20, 30);
Spliterator<Integer> cursor = numbers.spliterator();

System.out.println(cursor.estimateSize()); // 3
System.out.println(cursor.hasCharacteristics(Spliterator.ORDERED)); // true

StreamSupport.stream(cursor, false).forEach(System.out::println);
```

**Do not call `tryAdvance` to peek at data and expect the downstream Stream to still receive the full source.** `tryAdvance` actually advances the traversal position.

```java
Spliterator<Integer> cursor = List.of(10, 20, 30).spliterator();

cursor.tryAdvance(System.out::println); // Prints 10, consuming the first element

List<Integer> rest = StreamSupport.stream(cursor, false)
    .toList(); // [20, 30]
```

`Spliterator` is also a stateful traversal object, similar to `Iterator`. To run the pipeline again from the beginning, you need a way to obtain a fresh Spliterator from an appropriate source.

### 5.2. How Does `trySplit()` Relate to Parallel Processing?

`trySplit()` may return a new `Spliterator` representing a portion of the work while reducing the work remaining for the original `Spliterator`. These portions must not overlap in data. For an `ORDERED` source, splitting must obey the interface's ordering guarantees.

```java
Spliterator<Integer> rest = List.of(1, 2, 3, 4).spliterator();
Spliterator<Integer> part = rest.trySplit();

if (part != null) {
    part.forEachRemaining(System.out::println);
}
rest.forEachRemaining(System.out::println);
```

The example demonstrates splitting and traversing two parts, but **you do not need to call `trySplit` manually when using Streams normally**. When parallel execution is requested, the framework can perform work splitting based on this mechanism.

A `Spliterator` supporting splitting does not automatically mean the pipeline will run faster. Effectiveness also depends on data size, per-element processing cost, source characteristics, ordering, and intermediate operations like `sorted` or `distinct`.

## 6. Spliterator Characteristics: Declaring True Source Guarantees

Characteristic flags are defined in `java.util.Spliterator` and combined with the bitwise OR operator `|`:

```java
int characteristics = Spliterator.ORDERED | Spliterator.NONNULL;
```

| Flag | Meaning of guarantee | When to consider |
| --- | --- | --- |
| `ORDERED` | The source has a defined encounter order. | Iterator traverses in `List` order, data read sequentially. |
| `DISTINCT` | Elements are distinct according to `equals`. | Source guarantees no duplicate elements. |
| `SORTED` | Elements follow a declared sort order. | Source genuinely has an appropriate comparison order. |
| `SIZED` | Remaining size is known accurately. | Collection/Spliterator can provide the exact length. |
| `SUBSIZED` | Every Spliterator obtained via splitting also has an exact size. | Source supports splitting into parts of known size. |
| `NONNULL` | No element is `null`. | Source guarantees no `null` values, like `List.of(...)`. |
| `IMMUTABLE` | Source cannot be structurally modified during traversal under this contract. | Source genuinely guarantees structural immutability. |
| `CONCURRENT` | Source is designed to support appropriate concurrent modification during traversal. | Certain concurrent data structures. |

Inspection example:

```java
Spliterator<String> source =
    List.of("A", "B", "C").spliterator();

boolean ordered = source.hasCharacteristics(Spliterator.ORDERED);
boolean sized = source.hasCharacteristics(Spliterator.SIZED);
long exactSize = source.getExactSizeIfKnown();

System.out.println(ordered);   // true
System.out.println(sized);     // true
System.out.println(exactSize); // 3
```

Not every custom `Iterable` has `SIZED`, even when the underlying data actually has only a few elements. When using `spliteratorUnknownSize`, size is not declared as `SIZED` or `SUBSIZED`.

**Characteristics are not performance hint labels:** the API can rely on them to optimize or preserve semantics. Do not add `DISTINCT`, `SORTED`, `SIZED`, `IMMUTABLE`, or `CONCURRENT` just hoping the Stream runs faster. For instance, setting `DISTINCT` on a source containing duplicates can cause `distinct()` to be optimized away when it was actually needed.

Additional note: `IMMUTABLE` refers to immutability of the *source during traversal*, and does not guarantee that element objects themselves are immutable; `CONCURRENT` also does not make it safe to arbitrarily mutate shared objects inside pipeline lambdas.

## 7. Pipelines Are Lazy, but Source Binding Must Be Distinguished

Intermediate operations like `filter` and `map` are typically **lazy**. Creating a Stream does not mean all elements have been processed yet:

```java
Iterable<String> items = List.of("An", "Bình", "Chi");

var stream = StreamSupport.stream(items.spliterator(), false)
    .filter(name -> {
        System.out.println("Checking: " + name);
        return name.length() >= 3;
    });

System.out.println("Pipeline created");
List<String> names = stream.toList();

// The line "Pipeline created" is printed before filter evaluations.
```

**However, lazy operations differ from late binding of the source.** Some Spliterators bind to data upon creation; others defer binding. A Stream's laziness does not let us infer that all sources reflect modifications made after Stream creation.

### 7.1. Overload Taking a Supplier to Defer Obtaining the Spliterator

`StreamSupport.stream` has an overload taking `Supplier<? extends Spliterator<T>>`. In that case, calling the supplier to obtain the Spliterator is deferred until after the pipeline's terminal operation starts.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class LateBindingExample {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Java"));

        Stream<String> pipeline = StreamSupport.stream(
            () -> source.spliterator(),
            Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
            false
        );

        // Modify data before executing the pipeline, on the same thread:
        source.add("Stream");

        List<String> result = pipeline.toList();
        System.out.println(result); // [Java, Stream]
    }
}
```

Here `ArrayList.spliterator()` provides the `ORDERED`, `SIZED`, and `SUBSIZED` characteristics. **The `characteristics` value passed to the Supplier overload must match the actual characteristics reported by the Spliterator returned by the supplier**. Do not guess a bitmask for an unknown source.

The example only illustrates modifying the source **before** evaluating the terminal operation. Modifying a collection **during traversal** must not be treated as valid; for ordinary sources, obey the *non-interference* rule. If an API only provides a single-use iterator, calling a supplier that returns the same consumed iterator still will not make the source reusable.

### 7.2. Why Do Size and Characteristics Affect Optimization?

Example of a pipeline that only counts elements:

```java
long count = List.of("A", "B", "C").stream()
    .map(String::toLowerCase)
    .count(); // 3
```

With a known-size source and operations that do not alter element count, the Stream implementation can compute `count()` without running `map` on every element. Therefore, do not place mandatory actions inside `map` or `peek` lambdas.

For an unknown-size iterator source, counting generally requires traversal, yet you still should not code assuming a specific number of lambda invocations if the pipeline can short-circuit or be optimized differently.

## 8. Practical Example: Processing Records from Three Source Types

Problem: sales data is exposed through three different APIs. We need to filter transactions with positive revenue, sum total revenue by category, count high-value orders, and find the first valid transaction.

Java 17+ example, which can be saved in `ExistingDataStreamsDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class ExistingDataStreamsDemo {
    record Sale(String category, long amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("Books", 120),
            new Sale("Equipment", 300),
            new Sale("Books", 80),
            new Sale("Equipment", -50)
        );

        // 1) API provides Iterable<Sale>.
        Iterable<Sale> iterable = () -> sales.iterator();

        Map<String, Long> revenueByCategory =
            StreamSupport.stream(iterable.spliterator(), false)
                .filter(sale -> sale.amount() > 0)
                .collect(Collectors.groupingBy(
                    Sale::category,
                    TreeMap::new,
                    Collectors.summingLong(Sale::amount)
                ));

        System.out.println(revenueByCategory);
        // {Books=200, Equipment=300}

        // 2) API provides Iterator<Sale>.
        Iterator<Sale> iterator = sales.iterator();

        long largeSales = StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                    iterator,
                    Spliterator.ORDERED | Spliterator.NONNULL
                ),
                false
            )
            .filter(sale -> sale.amount() >= 100)
            .count();

        System.out.println(largeSales); // 2

        // 3) API provides Spliterator<Sale> directly.
        Spliterator<Sale> spliterator = sales.spliterator();

        Optional<Sale> firstPositive = StreamSupport.stream(
                spliterator, false
            )
            .filter(sale -> sale.amount() > 0)
            .findFirst();

        String firstLabel = firstPositive
            .map(sale -> sale.category() + ": " + sale.amount())
            .orElse("No matching transaction");

        System.out.println(firstLabel); // Books: 120
    }
}
```

These are three **independent** Streams. In the example, the underlying source `sales` is a list capable of producing multiple fresh iterators/spliterators. If all three APIs pointed to **one single iterator**, you must not assume the full data can be read again on the second or third pass.

| Conversion path | Downstream operations | Result |
| --- | --- | --- |
| `Iterable → spliterator() → Stream` | `filter`, `groupingBy`, `summingLong` | Totals by product category |
| `Iterator → spliteratorUnknownSize() → Stream` | `filter`, `count` | Number of transactions with amount >= 100 |
| `Spliterator → Stream` | `filter`, `findFirst` | First valid transaction |

After the conversion step, we use the same ecosystem of Stream operations; the main differences lie in **source guarantees and lifecycle**.

## 9. Single-Use Sources and External Resources

An Iterator may be backed by a database, file, socket, cursor, or paginated service. A Stream is only a processing layer over elements; **terminal operations do not automatically close underlying resources**.

### 9.1. Example: Scanner Is an Iterator and Holds a Closable Resource

`Scanner` implements `Iterator<String>`. We can feed a file's tokens into a Stream via `spliteratorUnknownSize`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class FileTokensExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
            Stream<String> tokens = StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                    scanner,
                    Spliterator.ORDERED | Spliterator.NONNULL
                ),
                false
            );

            long longTokens = tokens
                .filter(token -> token.length() >= 4)
                .count();

            System.out.println(longTokens);
        }
    }
}
```

The example assumes `data.txt` exists and contains text split into tokens according to `Scanner` rules. `try-with-resources` closes `Scanner` upon completion or when an exception occurs.

In modern Java, `Scanner.tokens()` directly provides a token Stream (Java 9+); prefer that API when available. Manual conversion here illustrates integrating an iterator from another library.

Similarly, if the goal is simply reading lines of a file, `Files.lines(path)` is usually more suitable; the returned Stream must still be closed via `try-with-resources`.

### 9.2. Using onClose When Tying Resource Lifecycle to the Stream

With an external API returning an iterator tied to a closable object, you can register a handler:

```java
try (Scanner scanner = new Scanner(Path.of("data.txt"), StandardCharsets.UTF_8);
     Stream<String> tokens = StreamSupport.stream(
         Spliterators.spliteratorUnknownSize(
             scanner,
             Spliterator.ORDERED | Spliterator.NONNULL
         ),
         false
     ).onClose(scanner::close)) {

    long count = tokens.count();
    System.out.println(count);
}
```

In this example, closing the scanner both in the Stream's handler and in `try-with-resources` is redundant, since the scanner is already managed directly. In real API design, usually **choose one clear resource ownership/closing mechanism**; for instance, manage only the Stream (with `onClose` attached) and let it close the resource when exiting the block. `onClose(...)` only registers an action to run when `Stream.close()` is called; it **does not trigger automatically after `count()` or `toList()`**.

### 9.3. Deciding How to Handle Source Exceptions

An I/O-backed iterator can throw exceptions during `hasNext()` or `next()`; once converted to a Stream, errors can surface during terminal operation execution rather than at pipeline creation. For sources like databases or I/O, define error handling and resource closing mechanisms right at the source-access boundary.

Do not handle read errors by silently returning an empty Stream: that behavior easily makes summary reports appear valid even though data is missing.

## 10. Ordering, Parallel Processing, and Performance

### 10.1. Encounter Order Is Not a Property of Every Iterator

If an iterator comes from a `List`, traversal order is meaningful; when wrapping, you can declare `ORDERED`. If an iterator comes from an unordered source, do not infer that the order it happens to emit is stable.

This affects:

- `findFirst()`: finds the first element **in encounter order** if the source is ordered.
- `limit(n)` and `skip(n)`: the meaning of "first" depends on encounter order.
- `forEachOrdered(...)`: maintains encounter order when the Stream is ordered, potentially with higher coordination overhead.
- `sorted(...)`: establishes an order by comparator, but incurs sorting cost.

On an unordered Stream, `findFirst()` does not promise to pick the element that some arbitrary sequential traversal happened to return first. If order is a business requirement, guarantee it at the source or sort explicitly.

### 10.2. Iterator Sources Do Not Split Work Well Naturally

Compare:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Collection has an informative spliterator:
long a = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .count();

// Iterator wrapped with unknown size:
long b = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        numbers.iterator(), Spliterator.ORDERED
    ),
    true
).filter(n -> n % 2 == 0).count();
```

Both results are `2`. However, `a` uses the collection's own Spliterator, which usually knows its size and splits work easily. `b` starts from a sequential iterator; splitting requires batching elements and can incur extra overhead.

`parallel=true` only requests parallel mode for the pipeline; it does not guarantee faster processing. With small data, lightweight tasks, single-use sources, slow I/O, or strict ordering requirements, overhead can outweigh benefits. Measure on realistic workloads before optimizing.

### 10.3. The Non-Interference Rule Still Applies

Whether a source starts from `Iterable`, `Iterator`, or `Spliterator`, lambdas in the pipeline should avoid mutating the source being traversed:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

StreamSupport.stream(numbers.spliterator(), false)
    .forEach(n -> {
        // Do not add/remove elements on numbers here.
        System.out.println(n);
    });
```

The example requires `import java.util.ArrayList;`. Modifying an ordinary collection during traversal can cause `ConcurrentModificationException` or undefined results. The `CONCURRENT` and `IMMUTABLE` flags are only meaningful when the source actually satisfies the contract; they do not automatically make every lambda mutating shared state safe.

### 10.4. Combining with collect, grouping, and Stateful Processing

After conversion, you can use grouping just like with any Stream:

```java
Iterator<String> iterator =
    List.of("Java", "Stream", "Java", "Lambda").iterator();

Map<String, Long> counts = StreamSupport.stream(
        Spliterators.spliteratorUnknownSize(
            iterator, Spliterator.ORDERED | Spliterator.NONNULL
        ),
        false
    )
    .collect(Collectors.groupingBy(
        word -> word,
        Collectors.counting()
    ));

// counts has Java=2, Stream=1, Lambda=1
```

This snippet requires importing `java.util.Iterator`, `java.util.List`, `java.util.Map`, `java.util.Spliterator`, `java.util.Spliterators`, `java.util.stream.Collectors`, and `java.util.stream.StreamSupport`.

Grouping collectors maintain accumulation state, yet are designed to integrate with Streams. When writing custom collectors or Spliterators, preserve contracts for combining results, splitting data, parallel processing, and non-interference. Those topics are extensions of the principles learned here.

## 11. Choosing a Conversion Approach

| What you receive from an API | Recommended approach | Notes |
| --- | --- | --- |
| `List<T>` or `Collection<T>` | `source.stream()` | Simple, preserves supported source characteristics. |
| `Iterable<T>` without `stream()` | `StreamSupport.stream(source.spliterator(), false)` | Check repeatability and ordering characteristics. |
| `Iterator<T>`, unknown size | `StreamSupport.stream(Spliterators.spliteratorUnknownSize(iterator, flags), false)` | Iterator is usually single-use; `flags` must be accurate. |
| `Iterator<T>`, exact size known | `StreamSupport.stream(Spliterators.spliterator(iterator, size, flags), false)` | Do not supply an estimated size. |
| Existing `Spliterator<T>` | `StreamSupport.stream(spliterator, false)` | Do not consume the `Spliterator` beforehand if all data is needed. |
| Source needing Spliterator when terminal operation starts | `StreamSupport.stream(supplier, characteristics, false)` | Declared flags must match the actual Spliterator. |
| Input is a text file | Prefer `Files.lines(path)` | Use `try-with-resources` to close the Stream. |
| Input is a `Scanner` | Prefer `scanner.tokens()` when suitable | Close `Scanner`; convert via Iterator if integrating legacy APIs. |

You can write a helper method when supporting `Iterable` in multiple places:

```java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public static <T> Stream<T> fromIterable(Iterable<T> source) {
    return StreamSupport.stream(source.spliterator(), false);
}
```

This is a **method** to place inside a Java class. In use:

```java
Iterable<String> names = List.of("An", "Bình");
List<String> result = fromIterable(names)
    .map(String::toUpperCase)
    .toList(); // [AN, BÌNH]
```

This helper does not change the properties of the source. If `source` only supports a single traversal pass, the helper does not magically make it repeatable.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `iterable.stream()` when variable type is `Iterable` | Compile error: `Iterable` does not define `stream()`. | Use `StreamSupport.stream(iterable.spliterator(), false)`. |
| Calling `iterator.stream()` | Compile error: `Iterator` has no `stream()`. | Wrap with `Spliterators.spliteratorUnknownSize`. |
| Reusing a Stream after calling a terminal operation | `IllegalStateException`. | Create a new Stream from a re-traversable source. |
| Re-wrapping an already consumed Iterator | Missing data or empty Stream. | Request a fresh iterator from the source if supported. |
| Adding `SIZED`/`DISTINCT` incorrectly | Optimizations can lead to wrong results. | Declare only characteristics guaranteed by the source. |
| Passing an estimated size to `spliterator(iterator, size, ...)` | Inaccurate size metadata. | Use `spliteratorUnknownSize` when exact size is unknown. |
| Thinking a Stream auto-closes a file on `count()` | Resources may fail to be released. | Use `try-with-resources`; understand `onClose`. |
| Peeking at a Spliterator before converting | Consumed elements will not appear again. | Obtain a fresh Spliterator or avoid consuming beforehand. |
| Setting `parallel=true` expecting automatic speedup | Pays work-splitting overhead, may run slower. | Evaluate source and benchmark realistically. |
| Modifying source collection inside `forEach` | Can throw exceptions or cause unreliable results. | Use `collect` or apply mutations outside traversal. |

## 13. Self-Check Questions

1. How do `Iterable<T>` and `Collection<T>` differ with respect to `stream()`?
2. Why is `Spliterators.spliteratorUnknownSize` needed when an API only returns `Iterator<T>`?
3. Can an exhausted iterator be "revived" by passing it to `StreamSupport.stream` again?
4. When is it valid to declare `Spliterator.ORDERED` or `Spliterator.NONNULL`?
5. Do `estimateSize()` and `getExactSizeIfKnown()` mean the same thing in all cases?
6. Does a `tryAdvance` call before creating a Stream affect the result?
7. When is the `StreamSupport.stream(supplier, characteristics, parallel)` overload useful?
8. Why can a `List` source support parallel processing better than an unknown-size `Iterator`?
9. Does a terminal operation automatically close a `Scanner` or source file?
10. Why can't you use the `DISTINCT` flag as a performance trick on data with duplicates?

**Answer guide:** (1) `Collection` has `stream()`, `Iterable` does not; (2) wraps the iterator into a mechanism Stream understands; (3) no; (4) only when the source genuinely guarantees them; (5) no, estimates may be inaccurate; (6) yes, the element is consumed; (7) when you need to defer obtaining the Spliterator until the terminal operation begins; (8) knows its size and can split work properly; (9) no, closing must be managed; (10) because an inaccurate flag can cause the deduplication step to be optimized away.

## 14. Key Takeaways

- **`Iterable<T>` → `iterable.spliterator()` → `StreamSupport.stream(...)`** is the basic bridge when an API does not provide `stream()`.
- **`Iterator<T>` → `Spliterators.spliteratorUnknownSize(...)` → `StreamSupport.stream(...)`** fits single-use or unknown-size traversal sources.
- **`Spliterator<T>` → `StreamSupport.stream(...)`** is used directly when a splittable traversal object is already available.
- **Do not assign inaccurate metadata:** characteristics like `ORDERED`, `SIZED`, `DISTINCT`, `SORTED`, `IMMUTABLE`, and `CONCURRENT` are source contracts, not arbitrary hints.
- **Streams and cursors are consumed according to their lifecycles;** re-traversable sources must provide a new iterator/spliterator for each processing pass.
- **Lazy pipelines do not mean resources close automatically.** Manage I/O and avoid side effects in lambdas, especially when running in parallel.
- Once `Stream<T>` is properly created, `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, along with `Spliterator` techniques and Stream Gatherers can all build on the same pipeline model.
