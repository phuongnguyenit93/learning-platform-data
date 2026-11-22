# Single-Use Nature and Stream Reuse Errors

In the **Pipeline Contracts and Lifecycle** chapter, a foundational rule of the **Java Stream API** is: **each `Stream` instance may only be used to set up and execute a single pipeline**. This rule applies whether the pipeline uses `filter`, `map`, `reduce`, `collect`, grouping with collectors, parallel processing, or advanced operations such as Stream Gatherers. Understanding the rule properly helps write declarative data-processing programs without lifecycle errors, while choosing computation strategies suited to the data source and processing cost.

## 1. Distinguishing a Stream from the data source

`Stream<T>` represents a computational flow over elements from a **data source** (collection, array, file, generator, ...). A `Stream` itself is not a collection for arbitrary re-traversal.

- **Data source**: for example, a `List<String>`. With a re-traversable source like a list, we can usually create multiple new Streams by calling `list.stream()` multiple times.
- **Pipeline**: a chain of intermediate operations such as `filter` and `map`, ending with a terminal operation such as `count`, `findFirst`, `reduce`, `collect`, or `forEach`.
- **Specific Stream instance**: belongs to **one** pipeline only. Calling an operation on a Stream that has already been linked to another pipeline or has already terminated violates the usage contract.

For example, the following two `names.stream()` calls create **two distinct Streams** over the same list. The list is not "consumed" just because we traversed it with a Stream.

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Linh", "Minh");

long total = names.stream().count();               // 3
long startsWithL = names.stream()
        .filter(name -> name.startsWith("L"))
        .count();                                   // 2
~~~

The example uses `List.of` (Java 9+); the single-use principle has existed since the Stream API was introduced in Java 8.

## 2. Pipeline lifecycle and when it becomes "used"

| Stage | Example | Lifecycle meaning |
| --- | --- | --- |
| Creating a Stream | `names.stream()`, `Stream.of(...)` | Receives a new Stream, with no operations attached yet. |
| Chaining an intermediate operation | `filter`, `map`, `sorted`, `distinct` | Creates a **lazy** pipeline: typically has not traversed elements yet, but the input Stream is already **linked** to the newly created pipeline and is no longer available for a second branch. |
| Running a terminal operation | `count`, `findFirst`, `anyMatch`, `reduce`, `collect`, `forEach` | Terminates the pipeline. The pipeline's Stream cannot be reused, even if the operation reads only part of the data or does not need to traverse all elements. |
| Closing the Stream | `close()` | Closes the Stream and runs handlers registered via `onClose`; a closed Stream cannot continue to be used. This is a distinct concept from running a terminal operation. |

The fact that an intermediate operation is **lazy** does not mean the input Stream can still be used to chain another branch. "Has not processed elements yet" and "has not been linked into a pipeline" are two different states.

### Example A: Reusing after a terminal operation

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Stream<String> selected = names.stream()
        .filter(name -> name.startsWith("L"));

long count = selected.count(); // Valid: first terminal operation
List<String> items = selected.toList(); // Invalid: reusing Stream
~~~

On common JDKs, the last line typically throws:

~~~text
java.lang.IllegalStateException: stream has already been operated upon or closed
~~~

`toList()` is a terminal operation available since Java 16. Replacing it with `collect(Collectors.toList())` on Java 8–15 does not make reusing the Stream valid either. The message string and timing of throwing the exception may vary across JDK implementations.

### Example B: Branching before running a terminal operation

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Stream<String> source = names.stream();
Stream<String> uppercase = source.map(String::toUpperCase);

// Invalid: source has already been linked to the uppercase pipeline.
Stream<String> shortNames = source.filter(name -> name.length() <= 3);
~~~

The error can occur right at `source.filter(...)`, **before** calling any terminal operation on `uppercase`. Therefore, do not misunderstand the rule as "you are only disallowed from reusing it after calling `count` or `collect`".

### Example C: Short-circuiting still terminates the pipeline

~~~java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.of(10, 20, 30, 40);

boolean found = numbers.anyMatch(n -> n == 10); // Short-circuits once found
long total = numbers.count();                   // Invalid: Stream has terminated
~~~

`anyMatch`, `allMatch`, `noneMatch`, `findFirst`, and `findAny` are terminal operations. The ability to stop early does not turn the remaining elements into a Stream that can continue to be used. Likewise, an empty result from `findFirst` does not allow reusing the Stream.

> **Note on the API contract:** Not every case of reuse is detected and throws `IllegalStateException`. Some operations may return the receiver object itself, making detection harder. **Not seeing an exception does not mean a program is permitted to reuse a Stream.**

## 3. Three ways to handle needing to read or compute multiple times

### Approach 1: Create a new Stream from a re-traversable source

When the data is a collection that can be read again, initialize a new pipeline for **each** terminal result.

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Linh", "Minh");

long count = names.stream()
        .filter(name -> name.startsWith("L"))
        .count();

List<String> upperNames = names.stream()
        .filter(name -> name.startsWith("L"))
        .map(String::toUpperCase)
        .toList();

System.out.println(count);      // 2
System.out.println(upperNames); // [LAN, LINH]
~~~

This approach is easy to read and avoids storing intermediate results, though the `filter` part will execute again when creating the new pipeline. For expensive data sources or transformations, consider the cost of re-traversing.

### Approach 2: Use a factory or `Supplier` to create a **new Stream**

When multiple places need the same processing chain, abstract **how to create** the pipeline rather than storing a Stream instance to share.

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Linh", "Minh");

Supplier<Stream<String>> selected = () -> names.stream()
        .filter(name -> name.startsWith("L"))
        .map(String::toUpperCase);

long count = selected.get().count();       // First Stream
List<String> items = selected.get().toList(); // Second Stream
~~~

Each call to `selected.get()` must return a **new Stream**. The following pattern is **still invalid** because the factory only returns the same instance:

~~~java
Stream<String> oneStream = names.stream();
Supplier<Stream<String>> wrong = () -> oneStream;

long first = wrong.get().count();
long second = wrong.get().count(); // Invalid: receives an already-used Stream
~~~

In API design, a method that needs repeated computations should usually accept a `Collection<T>` or a `Supplier<Stream<T>>` capable of creating new Streams; a `Stream<T>` parameter better expresses a bounded single-pass traversal.

### Approach 3: Compute multiple metrics in **one traversal**

If two results can both be aggregated from the same elements, a single terminal operation with an appropriate collector saves re-reading. For example, `summarizingInt` computes the count, sum, minimum, maximum, and average of name lengths at the same time:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("Lan", "Linh", "Minh");

IntSummaryStatistics stats = names.stream()
        .collect(Collectors.summarizingInt(String::length));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 11
System.out.println(stats.getAverage()); // 3.6666666666666665
~~~

`collect` is **one** terminal operation; a collector can accumulate multiple kinds of information during that processing pass. The same idea applies to `groupingBy`, custom collectors, and aggregations that need to run on a parallel Stream, provided the corresponding collector's contract is respected.

If subsequent processing steps need to re-read **the output elements themselves**, you can materialize the data:

~~~java
List<String> selectedNames = names.stream()
        .filter(name -> name.startsWith("L"))
        .toList();

long count = selectedNames.size();
List<Integer> lengths = selectedNames.stream()
        .map(String::length)
        .toList();
~~~

This stores a **collection result** for reuse, not reusing the old Stream. In return, the application must keep the elements in memory; consider this carefully for very large or infinite data.

## 4. Single-read sources and resource management

Not every source behaves like a `List`. Data streams from connections, file readers, one-way iterators, or event emitters may not be able to restore their initial state. **Creating a new Stream** is only a solution when the data source itself can be reopened or re-traversed.

Example reading a file with `Files.lines`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("users.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> nonBlank = lines
            .filter(line -> !line.isBlank())
            .toList();
    System.out.println(nonBlank.size());
} // Automatically calls close() even if processing encounters an exception
~~~

`Files.lines` creates a Stream backed by an I/O resource and thus requires `try-with-resources`. A terminal operation **does not automatically close** all resource-backed Streams. If you need to read the file a second time, open a new `Files.lines(path, ...)` inside a new `try-with-resources` block, provided the file is still available and readable.

It is also necessary to separate:

- **Executed a terminal operation**: the pipeline has exhausted its right to be used, even if `close()` has not been called on the Stream.
- **Called `close()`**: the Stream can no longer operate, even if no terminal operation ran beforehand.
- **Closed an I/O Stream**: does not mean the external source can rewind to the beginning by itself; re-readability depends on how a new source is created.

If a one-way source cannot be reopened, there are two approaches: design a collector to obtain all needed results in one pass, or store the data needing reuse in an appropriate collection/buffer. You cannot "reset" an already-used `Stream` by calling `sequential()`, `parallel()`, or `unordered()`.

## 5. Identifying and fixing bugs in real-world code

| Situation | Cause | Fix |
| --- | --- | --- |
| Calling `count()` then `collect()` on the same Stream variable | Two terminal operations on one pipeline | Create two Streams from a re-traversable source or combine results into one collector. |
| Using one Stream variable to create two branches `map` and `filter` | The source Stream is already linked to the first branch | Create a new Stream for each branch or build a unified pipeline. |
| Storing a `Stream` as a field and using it across multiple requests/methods | A Stream instance has a single-use lifecycle | Store the data source or a factory that creates a new Stream each time. |
| Reusing after `findFirst()` / `anyMatch()` | Short-circuiting operations are still terminal operations | Create a new pipeline; if the source is one-way, design processing in a single pass. |
| Accessing a Stream after `close()` or outside `try-with-resources` | The Stream is closed | Process while the Stream is open; open a new source if another read pass is needed. |
| Re-running a pipeline on data whose source has changed | Two new Streams may observe two different states | Create a snapshot if consistent results are required, while accepting the storage cost. |

When encountering a message like `stream has already been operated upon or closed`:

1. Identify **which Stream instance** appears on the failing line, not just looking at the source collection.
2. Find all intermediate operations, terminal operations, and `close` calls using that same instance.
3. Check whether the Stream is stored in a field, cache, shared variable, or a factory returning the same instance.
4. Choose a fix based on the **re-readability of the source**: a new pipeline, a collector combining results, or storing a snapshot.
5. Re-run the use case multiple times or invoke both branches to confirm each pipeline has only one terminal operation.

Do not use `try/catch (IllegalStateException)` and continue traversing the Stream as a recovery mechanism; an already-used Stream has no API-guaranteed reset operation.

## 6. Connection to laziness, parallelism, and performance

- **Laziness does not allow reuse.** `filter`/`map` usually have not processed elements at declaration time, yet the input Stream already belongs to the new pipeline. When a terminal operation starts, the required steps execute according to the pipeline's strategy.
- **Terminal operations can optimize traversal.** For instance, some pipelines can answer `count()` from a known size without running every observation action in `peek`. Even so, the Stream has still terminated and cannot be reused.
- **Parallel streams do not create reusable copies.** `parallel()` only configures execution mode; it does not turn a Stream into a collection or allow multiple terminal operations. State and thread-safety constraints of functions/collectors must still be respected.
- **Repeated sources have a cost.** Two `list.stream()` calls can traverse the same elements twice; for heavy operations or I/O, merging into one pass or caching intermediate results may make more sense.
- **Advanced operations do not change the lifecycle.** `Spliterator` describes how to split/traverse a source and Stream Gatherers add pipeline transformation capabilities, yet they do not make a Stream instance reusable.

## 7. Self-check

**Question 1.** What is wrong with the snippet below?

~~~java
Stream<Integer> s = Stream.of(1, 2, 3);
Stream<Integer> even = s.filter(n -> n % 2 == 0);
long a = even.count();
long b = s.count();
~~~

**Answer:** `s` was already linked to the `even` pipeline right after the `filter` call. `s.count()` attempts to operate on the input Stream again; the fact that `even.count()` already ran further confirms the pipeline has terminated. Create a new Stream from the source if independent results are needed.

**Question 2.** Is this snippet valid?

~~~java
List<Integer> source = List.of(1, 2, 3);
int sum = source.stream().mapToInt(Integer::intValue).sum();
long count = source.stream().count();
~~~

**Answer:** Yes. The two `source.stream()` calls create two separate Stream instances; each instance is used in exactly one pipeline. `source` remains the same list.

**Question 3.** Why is the following snippet still invalid if `findFirst()` only takes one element?

~~~java
Stream<Integer> s = Stream.of(7, 8, 9);
int first = s.findFirst().orElseThrow();
long count = s.count();
~~~

**Answer:** `findFirst` is a terminal operation and has already terminated the pipeline, even though it only needed to read part of the data. `s.count()` is a second operation on the same Stream.

**Key takeaway:** Reusing a **re-traversable data source** is valid; reusing the **same Stream instance** violates the contract. Each pipeline has one path through intermediate operations and one endpoint via a terminal operation; I/O resources must be closed according to their lifecycle.
