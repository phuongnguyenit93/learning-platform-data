# When to Use a Custom Stream Source Instead of Built-in JDK Sources?

## 1. The Problem: Do You Need to Build Your Own Stream Source?

In Java, a Stream pipeline consists of an **element source**, **intermediate operations** such as `filter` / `map`, and a **terminal operation** such as `toList` / `collect`. Many problems only need to create a source with built-in APIs:

```java
List<String> names = List.of("Lan", "An");
Stream<String> a = names.stream();
Stream<String> b = Stream.of("Java", "Stream");
IntStream c = IntStream.range(1, 5);
```

These are declarations inside a method with corresponding imports; each source already knows how to produce elements, so **there is no need to write a separate Spliterator**.

However, there are specialized sources: paginated APIs, record-reading cursors, sequential generators following a custom protocol, data readable only in batches, or resources that must be closed. In those cases, the question "should we use a custom source?" must start from real requirements, **not from wanting to write more advanced Java code**.

**Priority rule:** choose the simplest standard JDK source that satisfies the contract. Only create a custom adapter or Spliterator when a concrete difference in how elements are fetched, lazy fetching, resource ownership, ordering, size, or work-splitting mechanism makes standard APIs insufficiently direct.

This lesson focuses on **source selection decisions** and the responsibilities that arise when building custom sources for Java Streams 17+.

## 2. What Is a Stream Source?

The source is where a Stream receives its elements. It does not have to be a `Collection` already sitting in memory.

Example:

```text
Collection / Array / File / Iterator / Paginated API
                    |
                    v
              Stream Source
                    |
                    v
            filter → map → limit
                    |
                    v
              toList / reduce
```

A Stream describes the process of handling elements; the Stream itself **is not a data storage structure that can be reused arbitrarily**. A Stream object is usually used for one pipeline and one terminal operation, not reused for a second pass.

Typical JDK sources:

| Data Source | Common Creation Way | When Suitable |
| --- | --- | --- |
| `Collection<T>` | `collection.stream()` / `parallelStream()` | Already have a collection |
| Reference array | `Arrays.stream(array)` | Traversing array elements |
| Primitive array | `Arrays.stream(intArray)` → `IntStream` | Unboxed integer computations |
| A few values | `Stream.of(a, b, c)` | Creating a small, explicit source |
| A possibly null value | `Stream.ofNullable(value)` | Null corresponds to 0 elements (Java 9+) |
| Integer sequence | `IntStream.range(start, end)` | Regular sequence with clear end bound |
| Function-generated sequence | `Stream.iterate(...)`, `Stream.generate(...)` | Simple generation rules |
| Text lines of a file | `Files.lines(path)` | Reading a file line by line; Stream must be closed |
| Lines from `BufferedReader` | `reader.lines()` | Already have a reader whose lifecycle needs managing |
| Splitting a string by pattern | `Pattern.splitAsStream(text)` | Tokens by regex |
| Specialized Iterator | `Spliterators.spliteratorUnknownSize(...)` + `StreamSupport.stream(...)` | Adapter from an iterator without a Stream |
| Fully custom source | `Spliterator<T>` + `StreamSupport.stream(...)` | Need full control over how elements are received |

For data already sitting in a List, rebuilding a Spliterator source usually adds no value. For a file source where `Files.lines` already exists, rewriting file open/read logic usually only increases risk.

## 3. Decision Flowchart Before Creating a Custom Source

```text
Already have Collection / Array?
    ├─ Yes → collection.stream() / Arrays.stream()
    └─ No
         |
         v
Is there a directly suitable JDK API?
(Stream.of, ofNullable, range, iterate, generate, Files.lines...)
    ├─ Yes → use built-in API, manage resources per contract
    └─ No
         |
         v
Does the source already provide Iterator or Iterable?
    ├─ Yes → consider adapter via spliteratorUnknownSize
    └─ No
         |
         v
Is there a specialized element-fetching protocol?
(cursor, paging, state decoder, batch-received data)
    ├─ No → reconsider how the source is modeled
    └─ Yes → write a custom Spliterator/adapter when the benefit is large enough
                 |
                 v
     Define ORDERED, size, null, close, exception,
     cancellation, split/parallel, and testing approach
```

**"Custom" does not always mean implementing `Spliterator` yourself.** Often you only need an adapter function returning a Stream from an iterator or a bounded `Stream.generate` usage. A custom Spliterator is a choice with higher design and maintenance cost.

## 4. When Standard Sources Suffice: Do Not Reinvent Them

### 4.1. Data is already in a Collection or array

Example:

```java
List<Integer> numbers = List.of(4, 1, 3, 2);

List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();
```

This is a snippet inside a method with `List` imported. The result is `[2, 4]`. There is no need to create another source: List already provides size, element encounter order, and an appropriate spliterator.

For primitive arrays:

```java
int[] scores = {8, 4, 9};
int total = Arrays.stream(scores).sum();
```

This snippet requires importing `java.util.Arrays`; `total == 21`. Using `IntStream` is more convenient than manually building `Stream<Integer>` because it avoids boxing each element.

### 4.2. Data has a simple generation rule

`IntStream.range(0, n)` already solves index sequences. `Stream.iterate(seed, next)` or the three-argument overload `Stream.iterate(seed, hasNext, next)` is used for regular state sequences. `Stream.generate(supplier)` is used when each element is produced by a Supplier without needing information from the previous element.

Example:

```java
List<Integer> odds = Stream.iterate(
        1, n -> n <= 9, n -> n + 2)
        .toList();
```

Inside a method with `Stream` and `List` imported, the result is `[1, 3, 5, 7, 9]`. The three-parameter overload has existed since Java 9; it stops by predicate before emitting a non-matching element.

If the need is simply generating a sequence like that, writing a separate Spliterator is usually overkill. You must properly bound infinite sources from `generate` or the two-argument overload of `iterate` before calling terminal operations that collect all elements.

### 4.3. File sources already exist in the JDK

Use `Files.lines(path, charset)` for text lines. This is an API creating a Stream from a closeable resource, already handling reading, charset, and terminal operation coordination. Writing a new Stream source just to read ordinary file lines will increase the state you have to manage yourself without necessarily helping.

## 5. Java 17+ Example: Three Standard Sources Covering Most Needs

Save file `JdkSourcesDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class JdkSourcesDemo {
    public static void main(String[] args) {
        List<Integer> fromList = List.of(5, 1, 4, 2)
                .stream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .toList();

        int sum = Arrays.stream(new int[] {2, 3, 4}).sum();

        List<Integer> fromRange = IntStream.range(1, 5)
                .boxed()
                .toList();

        List<Integer> fromIterate = Stream.iterate(
                1, n -> n <= 7, n -> n + 2)
                .toList();

        List<String> fromGenerate = Stream.generate(() -> "x")
                .limit(3)
                .toList();

        System.out.println("list=" + fromList);
        System.out.println("sum=" + sum);
        System.out.println("range=" + fromRange);
        System.out.println("iterate=" + fromIterate);
        System.out.println("generate=" + fromGenerate);
    }
}
```

Run:

```bash
javac JdkSourcesDemo.java
java JdkSourcesDemo
```

Output:

```text
list=[2, 4]
sum=9
range=[1, 2, 3, 4]
iterate=[1, 3, 5, 7]
generate=[x, x, x]
```

Here, every requirement is solved with standard sources. `Stream.generate` has an unbounded source by default, yet `limit(3)` lets the pipeline collect exactly three elements. This style fits when the Supplier source only needs to return a value on demand without holding a page cursor.

**Do not turn an element-transformation need into a custom-source need.** Requirements like "filter," "convert to DTO," "join strings," or "group by key" normally belong to `filter`, `map`, `flatMap`, and collectors, not reasons to write your own Spliterator.

## 6. Genuine Reasons to Consider a Custom Source

A custom source is valuable when you need one or more capabilities that standard adapters struggle to express directly:

1. **Lazy fetching by page or cursor.** Instead of loading all pages from an API into a List first and then using a Stream, the source can fetch a new page only when old elements are exhausted.
2. **Turning a proprietary record-fetching protocol into a Stream.** A driver, SDK, or parser only provides calls like `nextRecord()`, `readNextBatch()`, or `fetchPage(cursor)`.
3. **Single-pass source consumption.** Data read from a socket, parser, or non-rewindable cursor; the adapter must clearly define ownership and lifecycle.
4. **Generating elements from a state machine** with a specialized termination condition not cleanly expressed by `iterate` or `generate`.
5. **Managing Spliterator metadata**: encounter order, size estimation, work-splitting capability, and other characteristics must be described accurately.
6. **Integrating resource cleanup**: returning a Stream with `onClose(...)` or wrapping results in a closeable abstraction so callers do not leak resources.
7. **Reducing memory for large sources**: holding only the data slice currently needed instead of materializing all data into RAM upfront; the benefit still depends on the terminal operation and stateful stages.

Unconvincing reasons: "wanting code to look more functional," "just needing to add a `filter`," "needing to sort an array," "needing to convert Integer to String," "wanting Stream to run asynchronously," or "wanting it to automatically be faster."

**Stream is a data-processing abstraction, not automatically a reactive stream or backpressure/asynchronous I/O system.** A blocking custom source can still block the consuming thread when fetching the next element.

## 7. Adapter from Iterator: A Less Complex Step Before Writing Your Own Spliterator

Many legacy APIs already provide `Iterator<T>` without providing `Stream<T>`. Java can create a Spliterator wrapping an iterator:

```java
Spliterator<String> sp = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

Stream<String> stream = StreamSupport.stream(sp, false);
```

This is a snippet inside a method that already has `Iterator<String> iterator`, with `Spliterator`, `Spliterators`, and `StreamSupport` imported. The `false` argument requests a **sequential Stream**. Avoid marking `NONNULL` if the iterator can actually return null.

Save file `IteratorAdapterDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class IteratorAdapterDemo {
    static <T> Stream<T> fromIterator(Iterator<T> iterator) {
        Spliterator<T> spliterator =
                Spliterators.spliteratorUnknownSize(
                        iterator, Spliterator.ORDERED);
        return StreamSupport.stream(spliterator, false);
    }

    public static void main(String[] args) {
        Iterator<String> legacy = List.of(
                "Lan", "An", "Binh").iterator();

        String result = fromIterator(legacy)
                .filter(name -> name.length() >= 3)
                .collect(Collectors.joining(", "));

        System.out.println(result);
    }
}
```

Compile/run:

```bash
javac IteratorAdapterDemo.java
java IteratorAdapterDemo
```

Output:

```text
Lan, Binh
```

This is an adapter for **a single-use iterator**. If you already have a `List` from the start as in the simulated example, using `list.stream()` is simpler. When the iterator comes from a real SDK, database cursor, or parser, the adapter helps bring downstream processing into the Stream API without loading all data.

**Do not reuse an already consumed iterator** expecting to create a Stream that traverses the same data from the beginning. The right to reset/reopen belongs to the source data API, not the Stream.

## 8. When You Need to Define a Custom Spliterator

`Spliterator<T>` is both an element-traversal abstraction and a descriptor of source-splitting capability. Two core methods:

```java
boolean tryAdvance(Consumer<? super T> action);
Spliterator<T> trySplit();
```

These are core method signatures to explain the API, not a custom Java interface.

- `tryAdvance(action)`: if a next element exists, executes action on that element and returns `true`; when the source is exhausted, returns `false`. **Must not return true without passing an element**.
- `trySplit()`: may return another Spliterator managing **a disjoint set of elements** from the remainder, supporting parallelism; if unsplittable, returns `null`.
- `estimateSize()`: estimates remaining elements; must not assert exactness if unknown.
- `characteristics()`: bit flags like `ORDERED`, `SIZED`, `NONNULL`, and `IMMUTABLE` must reflect **the truth of the source**.

The utility class `Spliterators.AbstractSpliterator<T>` reduces boilerplate: it has default implementations for parts like `estimateSize()`, `characteristics()`, and `trySplit()`. We can override `trySplit()` to return `null` to indicate a stateful source supporting only sequential traversal, rather than promising splitting capability it cannot deliver.

Creating a Stream from a Spliterator:

```java
Stream<T> result = StreamSupport.stream(spliterator, false);
```

This is a generic pattern in a context where `Spliterator<T> spliterator` already exists. `StreamSupport.stream` connects the custom source to the Stream pipeline. The boolean argument is the parallel request flag; it **does not guarantee speedup**, especially when trySplit cannot split the source.

## 9. Complete Java 17 Example: On-Demand Paginated Source

Suppose an API returns pages of integers, with an empty page signaling the end of data. We want to create a Stream that only calls the API to fetch a new page when the current page is exhausted.

The example intentionally uses a mock function instead of a network call so output is deterministic and runnable immediately. Connecting to a real API only requires replacing the `fetch.apply(pageNumber)` logic per the corresponding contract.

Save file `PagedSourceDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Consumer;
import java.util.function.IntFunction;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class PagedSourceDemo {
    static Stream<Integer> fromPages(
            IntFunction<List<Integer>> fetch) {

        Objects.requireNonNull(fetch);

        Spliterator<Integer> spliterator =
                new Spliterators.AbstractSpliterator<>(
                        Long.MAX_VALUE,
                        Spliterator.ORDERED | Spliterator.NONNULL) {

                    int pageNumber = 0;
                    int position = 0;
                    List<Integer> page = List.of();
                    boolean done = false;

                    @Override
                    public boolean tryAdvance(
                            Consumer<? super Integer> action) {
                        Objects.requireNonNull(action);

                        while (!done) {
                            if (position < page.size()) {
                                action.accept(page.get(position++));
                                return true;
                            }

                            page = Objects.requireNonNull(
                                    fetch.apply(pageNumber++));
                            position = 0;

                            if (page.isEmpty()) {
                                done = true;
                            }
                        }
                        return false;
                    }

                    @Override
                    public Spliterator<Integer> trySplit() {
                        return null; // Single-cursor source, sequential traversal.
                    }
                };

        return StreamSupport.stream(spliterator, false);
    }

    static List<Integer> fetchPage(int pageNumber) {
        System.out.println("fetch page " + pageNumber);

        return switch (pageNumber) {
            case 0 -> List.of(7, 2);
            case 1 -> List.of(9, 4);
            default -> List.of();
        };
    }

    public static void main(String[] args) {
        Stream<Integer> firstStream =
                fromPages(PagedSourceDemo::fetchPage);

        System.out.println("stream created");

        List<Integer> firstTwoAboveFive = firstStream
                .filter(n -> n > 5)
                .limit(2)
                .toList();

        System.out.println("selected=" + firstTwoAboveFive);

        int total = fromPages(PagedSourceDemo::fetchPage)
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println("sum=" + total);
    }
}
```

Compile/run:

```bash
javac PagedSourceDemo.java
java PagedSourceDemo
```

Deterministic output for the sequential example:

```text
stream created
fetch page 0
fetch page 1
selected=[7, 9]
fetch page 0
fetch page 1
fetch page 2
sum=22
```

Step-by-step explanation:

1. `fromPages(...)` creates the Spliterator and Stream; it **has not called the page-fetching function yet**. Hence `stream created` is printed before `fetch page 0`.
2. Terminal `toList()` on the pipeline with `filter(n -> n > 5).limit(2)` starts requesting elements.
3. Page 0 has `[7,2]`: 7 is accepted, 2 is filtered out. Page 1 has `[9,4]`: 9 is the second matching value, enough for `limit(2)`; there is no need to fetch page 2.
4. To sum the entire source, we create a **new Stream**, with fresh page state. It calls page 0, 1, then empty page 2 to recognize exhaustion; sum 7 + 2 + 9 + 4 = 22.
5. `trySplit()` returns `null` because the example uses a single ordered paging cursor. This is an honest choice: there is no safe independent page-splitting strategy for parallelism.

**Example limitation:** the "empty page means end" rule is only a mock API contract. A real API may use a cursor/token/hasMore or return a temporarily empty page while more data exists; in that case **you must implement per the real contract**, not treat an empty page as a stopping condition on your own.

You also need to think through timeouts, retries, network errors, consumption cancellation, and resource closing before putting a network adapter into production. Do not automatically retry a call with side effects without considering idempotency.

## 10. Why Not Just Use `Stream.generate()` for Paging?

You can write a Supplier holding page state and combine it with `Stream.generate`. However, `generate` creates an **unbounded** source by contract, with no direct way to signal "end of elements" by having the Supplier return null: null is an **element value**, not a Stream termination signal. You could use a sentinel + `takeWhile` or a wrapper, yet you must consider valid null data cases, short-circuiting, and thread safety.

For example, a source with a fixed page count can be written more simply with `IntStream.range(0, numberOfPages).mapToObj(fetchPage).flatMap(List::stream)`. If the total page count is known upfront and pages are independent, this approach may **not need a custom Spliterator**.

Choices:

| Problem | Preferred Approach |
| --- | --- |
| Generating unbounded independent values | `Stream.generate(supplier)` combined with appropriate bound/terminal |
| State sequence with next rule and stopping condition | `Stream.iterate(seed, hasNext, next)` |
| API with fixed page count | `IntStream.range(...).mapToObj(fetch).flatMap(...)` |
| API with only a single-use `Iterator` | `spliteratorUnknownSize + StreamSupport.stream` |
| Paging API with cursor and custom termination point | Can use a custom Spliterator |
| API already returning an accurate `Stream<T>` | Use the existing Stream, do not wrap it unnecessarily |

**A custom source can be better if termination and existing state do not express cleanly with standard factories.** However, that does not remove Stream rules on single consumption, short-circuiting, resources, and thread safety.

## 11. Important Detail: Source Laziness Differs from Side Effects During Source Construction

Look again:

```java
Stream<String> stream = Stream.of(loadData());
```

Here, `loadData()` is an argument to the method call, so Java evaluates it **right when creating the source**. Even though downstream stages are lazy, the I/O in `loadData()` is not deferred.

Whereas:

```java
Stream<String> stream = Stream.generate(() -> loadData())
        .limit(1);
```

The `loadData()` call is inside the Supplier body, so it is requested when consuming the element. These two snippets are not equivalent in I/O timing, even though if `loadData()` returns the same value, the single-element result may look the same.

With `StreamSupport.stream(spliterator, false)`, laziness mainly comes from `tryAdvance`. However, **the constructor and Spliterator creation statements still run when creating the object**. If code calls an API in the constructor to fetch the first page, I/O still runs early.

When you specifically need to **defer binding the source** until the terminal starts, `StreamSupport` has an overload taking a `Supplier<? extends Spliterator<T>>` along with characteristics and the parallel flag:

```java
Stream<T> stream = StreamSupport.stream(
        spliteratorSupplier,
        characteristics,
        false
);
```

This is a generic pattern for understanding the API; it requires an appropriate supplier variable, characteristics accurately reflecting the Spliterator the supplier creates, and full imports. This overload can defer calling the supplier until the terminal operation begins, and is beneficial when the source can mutate between pipeline construction and consumption. However, **the expression creating the supplier** is still evaluated normally, and the source may bind resources when the supplier is called. Use it only when genuinely needed, rather than assuming every source needs this overload.

## 12. Spliterator Characteristics: Only Declare What You Can Prove

Characteristic flags help the Stream framework understand the source. False declarations can produce wrong results or skip necessary processing.

| Flag | Meaning | Typical Mistake |
| --- | --- | --- |
| `ORDERED` | Source has a defined encounter order | Declaring it for an inherently unordered source |
| `DISTINCT` | Elements are unique in equality sense | Declaring it even though the API can emit duplicates |
| `SORTED` | Elements are sorted per appropriate comparator/natural order | Declaring it even though the source is not truly sorted |
| `SIZED` | Exact remaining element count is known | Declaring it for a paginated source with unknown record count |
| `SUBSIZED` | Every Spliterator produced on split also has exact size | Declaring it when splitting cannot count accurately |
| `NONNULL` | Source guarantees not returning null elements | Declaring it even though cursor can return null |
| `IMMUTABLE` | Element source undergoes no structural modification per contract | Declaring it for a mutable collection modified mid-traversal |
| `CONCURRENT` | Source supports concurrent modification per appropriate contract | Attaching the flag just because multiple threads use the source |

In the paging example above, the source has page order and non-null boxed int elements, so `ORDERED | NONNULL` makes sense. However, **the total size is unknown**, so `SIZED` is not declared. Returning `Long.MAX_VALUE` as the initial estimate is an "unknown" placeholder estimate per the AbstractSpliterator pattern; it **does not mean there will be Long.MAX_VALUE records**.

Note on `IMMUTABLE`: immutable characteristics refer to structural stability of the source during traversal, not that element objects themselves are immutable. Every flag must correspond to an actual guarantee of the data source, not wishful thinking.

## 13. Custom Sources and Parallel: Should You Enable `true`?

`StreamSupport.stream(spliterator, true)` requests a parallel pipeline, yet to genuinely split the source effectively, `trySplit()` must supply independent, non-overlapping data chunks that can be processed concurrently.

For a forward-only cursor or a page API that must wait for the previous page's token, forcing a source split can break ordering, duplicate records, or lose records. In that case, return `null` from `trySplit()` and use a sequential stream.

If data can be split by independent index/partition, a splittable Spliterator can be considered. When writing it yourself, ensure:

1. Every element belongs to **exactly one** branch after splitting, never duplicated or lost.
2. No races between branches over shared cursor/state.
3. `ORDERED`, `SIZED`, `SUBSIZED`, and size estimates remain accurate after splitting.
4. Result ordering, if required, is preserved per the Stream contract; callback order does not automatically equal encounter order.
5. Split/merge cost is worthwhile; parallel is not faster by default.

If the source is already a List or array, the JDK's standard Spliterator usually supports splitting better than a simple custom implementation. Therefore, only write a parallel Spliterator when there is a clear reason and thorough testing.

## 14. Resources: Terminal Operations Do Not Auto-Close Streams

When a source reads a file, database cursor, socket, or external JVM handle, the most important part is **who owns the resource and when is it closed?**

A dangerous misconception: calling `toList()` or `count()` makes the Stream automatically close every resource. Per the API, **a Stream is not automatically closed by a terminal operation**. For Streams with closeable I/O sources, the application should use `try-with-resources` and close explicitly.

Standard JDK sources set the right pattern:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> selected = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();
    System.out.println(selected);
}
```

This is code inside a method with `Path path`, imports `Files`, `StandardCharsets`, `Stream`, `List`, and `IOException` handling/declaration. `Files.lines` opens a file resource; closing the Stream releases the associated resource.

For custom sources, cleanup actions can be attached:

```java
Stream<Record> stream = StreamSupport
        .stream(spliterator, false)
        .onClose(() -> cursor.close());
```

This is an **illustrative design pattern**, assuming `cursor.close()` does not throw a checked exception or has been handled appropriately. You must use `try (Stream<Record> stream = ...)` on the consumer side to ensure `close()` is called. `onClose` does not mean the terminal operation calls cleanup automatically.

**Think about when the source is opened:** if the cursor opens right when calling the factory yet the caller does not close the Stream, there is a leak risk; if opened lazily on the first `tryAdvance`, ensure open/read errors and cleanup on early termination are handled. For multiple complex resources, a clearer `AutoCloseable` abstraction may be needed rather than just returning a Stream.

## 15. Java 17 Example: Using a Standard File Source and Closing Properly

Save `FileLinesSourceDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FileLinesSourceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("stream-source-", ".txt");

        try {
            Files.write(file, List.of(
                    "  Lan  ", "", "An", "  Binh"),
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {

                List<String> names = lines
                        .map(String::trim)
                        .filter(s -> !s.isBlank())
                        .toList();

                System.out.println(names);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac FileLinesSourceDemo.java
java FileLinesSourceDemo
```

Output:

```text
[Lan, An, Binh]
```

This example creates a temporary file to run standalone; it does not need a custom Spliterator. File handling is managed inside `try-with-resources` and the temp file is deleted in `finally`. If an I/O error occurs while traversing `Files.lines`, the implementation may wrap it into `UncheckedIOException`; you still need proper error handling and cleanup paths.

Whether a file already exists in practice does not change the principle: **when a JDK line-reading source already exists, prefer using it**, only creating a custom source when the format or protocol goes beyond current capabilities.

## 16. Streams from External Sources Are Not Automatically Asynchronous

When calling `terminalOperation` on a sequential Stream, the framework pulls elements through the source on demand. For a network-accessing source, a single `tryAdvance` may have to wait on HTTP/API/database. Thus a Stream pipeline can often **block the calling thread** during retrieval.

Do not equate:

- Java Stream = an element-processing API supporting lazy intermediate operations and parallelism in suitable scenarios.
- Reactive Streams/Flow API = a producer-consumer coordination model with subscription, demand/backpressure, and asynchronous protocols by specific design.
- Asynchronous I/O = non-blocking I/O or returning results via futures/callbacks/events.

A custom Stream source does not automatically turn server pagination into full backpressure or accurate retry/resilience. If an application needs continuous processing, multiple consumers, demand-based cancellation, or async protocols, evaluate an appropriate API model instead of forcing everything into `StreamSupport.stream`.

## 17. Nulls, Error Data, and Termination Rules

When building your own source, three situations must be separated:

1. **Valid null elements exist:** if the API allows them, do not declare `NONNULL`; decide how downstream stages handle null.
2. **No elements remain:** `tryAdvance` returns `false`; that is the Spliterator's termination signal, **not** an `action.accept(null)` call.
3. **Source error:** throw an appropriate exception, avoiding returning `false` to hide data-reading errors and silently drop records.

If a paginated API can return an **empty page while not yet finished**, use the `hasMore` field or next cursor from the response. If the API can return duplicates after retry or change order between pages, define idempotency and consistency; Spliterator does not fix the source protocol for you.

Do not promise that a stream from an external source can always be re-run. If a cursor is single-use, re-running requires opening a new cursor or providing a factory that creates a fresh source with resource management for each pass.

## 18. Custom Sources Can Be Harder to Test Than JDK Sources

A custom adapter should be tested at **the element-fetching boundary**, not just at a single terminal operation.

Testing checklist:

- **Completeness:** every element is emitted exactly once, with the right value, no omissions/duplicates.
- **Ordering:** if the source has ORDERED, order matches the source contract, even with empty pages or duplicate data.
- **Termination:** source exhausted → `tryAdvance` returns false; does not keep calling the API after done.
- **Short-circuiting:** `limit(n)` / `findFirst()` does not fetch unnecessary extra pages when avoidable.
- **Nulls:** do not falsely declare NONNULL; do not turn null into termination if null is valid data.
- **Errors:** exceptions from fetch are propagated/translated per contract, cleanup is not forgotten.
- **Close:** is `onClose` called when the consumer closes and in exception cases?
- **Single use:** Stream cannot be consumed twice; adapter does not accidentally share a cursor across passes.
- **Parallel:** if splittable, branches do not overlap and metadata is accurate.
- **Size:** do not declare SIZED when only an estimate is known.
- **Timeout/cancellation:** external source may be blocking; a realistic cancellation strategy is needed if required by the system.
- **Performance:** measure fetching, API call count, memory, and combining overhead rather than just looking at code style.

For a real custom source, test with a **fake fetcher** that counts invocations to verify lazy fetching, then use integration tests against the real API.

## 19. Common Design Mistakes

1. **Creating a Spliterator just to filter a List.** Use `list.stream().filter(...)`; do not turn data transformation into a source-creation problem.
2. **Assuming every external API needs a custom source.** If the SDK already has a good Stream or Iterator, use or minimally wrap it.
3. **Thinking `generate` returning null ends the source.** Null is not a Stream termination signal; an explicit stopping condition is needed.
4. **Marking `SIZED` when record count is unknown.** Violates truth about element count and can cause the framework to optimize wrongly.
5. **Declaring `NONNULL` even though the API sometimes returns null.** Produces dishonest metadata.
6. **Using parallel with an unsplittable cursor.** Easy to race or break order; if safe splitting is impossible, use sequential.
7. **Believing terminal operations auto-close files/cursors.** Use `try-with-resources`, `close()`, and `onClose` per contract.
8. **Calling the API during Stream construction while advertising the source as lazy.** Distinguish constructor/callback creation from `tryAdvance` and Supplier.
9. **Materializing all pages into a List first even though only two elements are needed.** Loses lazy-fetching advantage; consider an on-demand adapter.
10. **Returning null as a sentinel in a source with valid null data.** Must distinguish valid values from termination signals via explicit protocol/types.
11. **Assuming `StreamSupport.stream(..., true)` is always fast.** Parallelism has overhead and requires a genuinely splittable Spliterator.
12. **Writing an iterator/spliterator with shared state and sharing it across multiple Streams.** Causes consumption bugs, races, and lost/duplicate data.
13. **Swallowing API exceptions inside `tryAdvance`.** Easily produces missing results without reporting errors.
14. **Believing `onClose` runs automatically upon reaching end of source.** Stream or resource must be closed per caller responsibility.
15. **Relying on log order to infer data order in parallel.** Callbacks may not run in encounter order.
16. **Rewriting standard JDK file-reading sources.** Unless special parsing/protocol is needed, `Files.lines` is usually safer.
17. **Assuming every stream can re-fetch all data by calling a terminal operation a second time.** Streams are single-use; cursors also usually do not rewind.
18. **Trying to use Stream for unbounded reactive data without a stopping strategy.** Consider backpressure/cancellation models and choose an appropriate API.

## 20. Self-Check Exercises

### Exercise 1: Choosing the right source

Choose the most appropriate API for each case:

A. You have an in-memory `List<Product>` and want to filter in-stock products.

B. You have an `int[]` array and want to compute the sum.

C. You have an index sequence from 0 to n-1.

D. You have an `Iterator<Record>` from a legacy library, forward-only, with no Stream.

E. You have a paginated API that only receives the next cursor after calling the current page; you want to load only enough records for `limit(5)`.

F. You have a text file to traverse line by line and close the handle.

**Suggested answers:**

- A: `list.stream().filter(...)`.
- B: `Arrays.stream(array).sum()`.
- C: `IntStream.range(0, n)`.
- D: Adapter via `spliteratorUnknownSize(iterator, characteristics)` then `StreamSupport.stream(..., false)`, considering source cleanup.
- E: Custom paging/cursor source or suitable lazy adapter if simple JDK APIs are insufficient; clearly design stopping/close/exception handling.
- F: `try (Stream<String> lines = Files.lines(path)) { ... }`.

### Exercise 2: Understanding paginated source output

In the `PagedSourceDemo` example, if we only use:

```java
List<Integer> values = fromPages(PagedSourceDemo::fetchPage)
        .filter(n -> n > 5)
        .limit(1)
        .toList();
```

what is printed?

**Answer:** only page 0 is fetched because that page already has 7 matching the condition; the result is `[7]`. Creating the Stream does not load page 0 before the terminal operation.

### Exercise 3: Characteristic flags

An API can return null, does not know the record count upfront, yet returns records in cursor order. Can `SIZED | NONNULL | ORDERED` be declared?

**Answer:** No. Only `ORDERED` is grounded in the description; `SIZED` and `NONNULL` are wrong. Returning an "unknown" estimate does not turn the source into SIZED.

### Exercise 4: Why must Streams be closed?

A file-backed Stream returns the right List after `toList()`. Can `try-with-resources` be omitted?

**Answer:** No. A terminal operation does not mean external resources will be closed automatically. `Files.lines` requires closing the Stream per contract to release the handle.

### Exercise 5: Is a custom Spliterator needed for an API with a known total page count?

There are 10 independent pages, and `fetch(pageNo)` can be called by page number. Can writing your own Spliterator be avoided?

**Answer:** You can use `IntStream.range(0, 10).mapToObj(fetch::apply).flatMap(List::stream)`, with appropriate error handling and resource limits. When the API has a cursor depending on the previous page's result or needs complex cleanup, a custom adapter can be more beneficial.

## 21. Project Adoption Decision Checklist

Before creating a custom Stream source, write a brief contract:

1. **Origin:** collection, array, file, iterator, database cursor, paging API, or generator?
2. **Which JDK factory already suffices?** Check `stream`, `Arrays.stream`, `of`, `range`, `iterate`, `generate`, and `Files.lines`.
3. **Specific reason for difference:** lazy fetching, stopping protocol, metadata, resources, splitting, or another set of requirements?
4. **Elements:** type, nulls, mutable state, and equality rules.
5. **Termination:** known size, EOF received, next cursor, or end-of-source marker?
6. **Ordering:** is there a true encounter order, or only incidental observation?
7. **Resources:** who opens, who closes, how are errors or short-circuits closed?
8. **Concurrency:** can the source be split safely, or must it be sequential?
9. **Reusability:** must a fresh stream/cursor be created each time?
10. **Cost:** API call count, page size, memory, and terminal operation.
11. **Testing:** empty case, single element, multiple pages, errors, cancellation, and close.
12. **Documentation:** what `try-with-resources` usage and limitations must callers know?

**Conclusion:** if data already comes from a List, array, numeric sequence, file lines, or Iterator, **prefer standard JDK sources or adapters**. Only write a custom source when you need to accurately model an element-emitting protocol that standard APIs do not express reasonably, such as a paginated cursor or specialized stateful parser. Once you create your own source, the responsibility is not only to emit values, but also to be truthful about **laziness, ordering, size, resources, errors, and work-splitting capability**.

**References:** Java SE 17 API `java.util.stream.StreamSupport`, `java.util.Spliterator`, `java.util.Spliterators`, `java.util.stream.Stream`, `java.util.stream.IntStream`, `java.nio.file.Files.lines`; Java Stream package specification on lazy evaluation, non-interference, and resource handling.