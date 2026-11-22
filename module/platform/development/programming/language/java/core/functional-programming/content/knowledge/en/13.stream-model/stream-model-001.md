# A Stream Is a Data Processing Pipeline and Not a Storage Structure in Java

## 1. Understanding the True Nature of a Stream

`java.util.stream.Stream<T>` describes **a sequence of elements on which computations are performed**. A Stream typically takes elements from a *source*, passes them through intermediate operations, and computes only when a *terminal operation* is invoked. A Stream itself **is not a data storage structure** like `List`, `Set`, or an array.

Example:

```java
List<String> names = List.of("Lan", "Minh", "An");

List<String> shortNames = names.stream()
        .filter(name -> name.length() <= 3)
        .map(String::toUpperCase)
        .toList();

// shortNames: [LAN, AN]
// names is still [Lan, Minh, An]
```

`names` is a collection containing elements; `names.stream()` creates a Stream used to process data from that collection. `filter` and `map` describe what needs to be done, while `toList()` executes the pipeline and returns a **new List object** holding the result. It is this resulting list that stores the elements, not the Stream before termination.

A Stream may have internal buffers to perform certain operations such as `sorted` or `distinct`, but that is a processing detail and **does not turn a Stream into a long-term storage container**. A Stream can also process non-collection sources, such as generated sequences of numbers or lines read from a file.

## 2. Pipeline Structure: Source → Intermediate → Terminal

A typical Stream pipeline consists of three components:

```text
Source
  List / Set / array / generator / file ...
        │
        ▼
   Stream<T>
        │
        ▼
Intermediate operations
  filter → map → distinct → sorted → limit ...
        │
        ▼
Terminal operations
  toList / collect / forEach / count / reduce / findFirst ...
        │
        ▼
Result / side effect / Optional / scalar / new collection
```

### Source

The source provides elements for the Stream to process. Common ways to create one:

```java
List<String> words = List.of("a", "bb", "ccc");
Stream<String> fromList = words.stream();

Stream<String> fromValues = Stream.of("a", "bb", "ccc");

int[] numbers = {1, 2, 3};
java.util.stream.IntStream fromArray = java.util.Arrays.stream(numbers);

java.util.stream.IntStream fromRange =
        java.util.stream.IntStream.range(0, 3); // 0, 1, 2
```

These are standalone illustrative snippets; `java.util.List`, `java.util.stream.Stream` (and `Arrays` if not written with its fully qualified name) must be imported. Creating a Stream does not mean all elements have been copied into a new collection. For a collection source, a Stream typically accesses the source data when the pipeline is consumed.

### Intermediate Operation

Intermediate operations such as `filter`, `map`, `flatMap`, `peek`, `sorted`, `distinct`, `skip`, and `limit` return a Stream that continues describing the processing chain. Most of them do not traverse the source when declared.

```java
Stream<String> pipeline = Stream.of("A", "BB", "CCC")
        .filter(s -> s.length() >= 2)
        .map(String::toLowerCase);

// No terminal operation yet; the pipeline is still only a processing description.
```

There are **stateless** operations like `map` and `filter`, which process each element without needing to retain state from other elements. There are **stateful** operations like `sorted` and `distinct` that may need to remember/buffer elements to produce the correct result. Therefore, "lazy" must not be understood as "never storing any intermediate data."

### Terminal Operation

A terminal operation triggers evaluation of the pipeline, usually producing a result or side effect:

```java
List<String> result = pipeline.toList(); // [bb, ccc]
```

After a terminal operation, **do not reuse the same Stream instance** to perform further operations. If you want to run it again, create a new Stream from the source or create a function/supplier that generates a new Stream.

Some terminal operations are *short-circuiting*, such as `findFirst`, `findAny`, `anyMatch`, `allMatch`, and `noneMatch`: they can stop early once the result is determined. `limit` is a short-circuiting intermediate operation, so it can also restrict how much data is pulled from the source.

## 3. How Does a Stream Differ from a Collection?

| Characteristic | `Collection` / `List` | `Stream` |
| --- | --- | --- |
| Primary purpose | Manage a group of elements | Express and execute computations on a sequence of elements |
| Storage | Has a structure holding elements | Not a long-term result storage container |
| Repeated use | Can be traversed multiple times (depending on the collection and source mutations) | A pipeline is single-use only |
| Index access | `List` has `get(index)` | No random-access API like `get(index)` |
| Element mutation | Depends on whether the collection allows mutation | No `add`/`remove` to update the source like a collection |
| Evaluation | Collection operations have method-specific semantics | Intermediate steps are typically lazy; terminal triggers computation |
| Output | Elements remain in the collection | Can return a `List`, `Optional`, a single value, or nothing |
| Data source | The collection itself owns the structure holding elements | Can come from a collection, array, generator, file, or other source |

**Do not confuse `Stream` with `InputStream`/`OutputStream` in `java.io`.** `Stream<T>` in the `java.util.stream` package is an API for processing elements; `InputStream`/`OutputStream` work with bytes of an I/O stream. Both use the word "stream" but have different semantics, APIs, and lifecycles.

A `List` can be the **source** of many different Streams. Conversely, calling `toList()` on a Stream produces a resulting `List`; this step does not make the Stream itself a `List`.

## 4. Complete Java 17+ Example: Seeing Non-Storage, Laziness, and Single-Use Clearly

Create the file `StreamIsNotStorageDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamIsNotStorageDemo {
    private static void check(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("  Lan  ", "", "Minh", " An "));

        // Counter used only to illustrate when filter is called.
        AtomicInteger inspected = new AtomicInteger();

        Stream<String> pipeline = source.stream()
                .filter(s -> {
                    inspected.incrementAndGet();
                    return !s.isBlank();
                })
                .map(String::strip)
                .map(s -> s.toUpperCase(Locale.ROOT));

        check(0, inspected.get(), "intermediate operations are lazy");
        System.out.println("beforeTerminal=" + inspected.get());

        // Terminal operation: the pipeline actually traverses and processes the source.
        List<String> result = pipeline.toList();

        check(4, inspected.get(), "all source elements inspected");
        check(List.of("LAN", "MINH", "AN"), result, "stream result");
        check(4, source.size(), "source still has four elements");
        check("  Lan  ", source.get(0), "source was not transformed");

        System.out.println("afterTerminal=" + inspected.get());
        System.out.println("result=" + result);
        System.out.println("sourceSize=" + source.size());
        System.out.println("sourceFirstUnchanged="
                + source.get(0).equals("  Lan  "));

        // The source collection can continue to exist and be updated.
        source.add("Bao");
        check(5, source.size(), "source updated");
        check(3, result.size(), "existing result stays separate");

        System.out.println("sourceSizeAfterAdd=" + source.size());
        System.out.println("resultSizeAfterAdd=" + result.size());

        // Create a NEW Stream from the same source after the source data changes.
        long freshCount = source.stream()
                .filter(s -> !s.isBlank())
                .count();
        check(4L, freshCount, "fresh stream sees updated source");
        System.out.println("freshCount=" + freshCount);

        boolean unmodifiable = false;
        try {
            result.add("EXTRA");
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        check(true, unmodifiable, "Stream.toList result is unmodifiable");
        System.out.println("resultUnmodifiable=" + unmodifiable);

        boolean reusedRejected = false;
        try {
            pipeline.count();
        } catch (IllegalStateException expected) {
            reusedRejected = true;
        }
        check(true, reusedRejected, "stream cannot be reused");
        System.out.println("streamReusedRejected=" + reusedRejected);

        List<Integer> range = IntStream.rangeClosed(1, 3)
                .boxed()
                .toList();
        check(List.of(1, 2, 3), range, "generated source");
        System.out.println("range=" + range);

        System.out.println("tests=PASS");
    }
}
```

Compile and run:

```bash
javac StreamIsNotStorageDemo.java
java StreamIsNotStorageDemo
```

Stdout output in exact order:

```text
beforeTerminal=0
afterTerminal=4
result=[LAN, MINH, AN]
sourceSize=4
sourceFirstUnchanged=true
sourceSizeAfterAdd=5
resultSizeAfterAdd=3
freshCount=4
resultUnmodifiable=true
streamReusedRejected=true
range=[1, 2, 3]
tests=PASS
```

**What to observe:**

1. `beforeTerminal=0`: declaring `filter` and `map` has not caused the lambda in `filter` to run yet. When `toList()` consumes the pipeline sequentially, all four elements of the source are inspected.
2. `result` contains three new transformed strings; the `source` collection still retains the original four elements (including the empty string). Thus `filter` does not remove items from the source list, and `map` does not replace values in that list.
3. After adding `"Bao"` to `source`, the size of `result` remains 3; `result` is the result list obtained before the source changed. A **new** Stream from `source` sees the current data, yielding `freshCount=4`.
4. `Stream.toList()` since Java 16 returns an **unmodifiable** list; attempting `add` throws `UnsupportedOperationException`. This is a property of **the list returned by the terminal operation**, not a storage capability of the Stream.
5. Once `pipeline.toList()` has been called, `pipeline.count()` cannot be called on the same instance. The second call in the program uses `try/catch` solely to demonstrate the `IllegalStateException` error.
6. `IntStream.rangeClosed(1, 3)` generates a sequence of numbers for computation without building an input list beforehand; only at `.boxed().toList()` does the program collect the values into `List<Integer>`.

The `AtomicInteger` counter in the demo is only for observing when `filter` is executed. In business logic code, avoid relying on side effects in intermediate operations; Java is allowed to optimize certain pipelines and skip steps that do not affect the result. A classic example: `list.stream().map(...).count()` can determine the size from the source without invoking `map` on every element.

## 5. Laziness Does Not Mean Doing No Work

Consider two pipelines:

```java
List<String> items = List.of("a", "bb", "ccc");
Stream<String> selected = items.stream()
        .filter(s -> s.length() >= 2);

// selected only describes the filtering operation so far.
List<String> copied = selected.toList(); // [bb, ccc]
```

Benefits of laziness:

- Operations can be composed into a pipeline before choosing how to consume the result.
- Only the necessary number of elements can be processed when combined with short-circuiting operations.
- Processing can be pipelined step by step without forcing the creation of an intermediate collection after every `filter` or `map`.

However, Java does not guarantee that every intermediate lambda is always called once per element regardless of the terminal operation. A Stream can optimize as long as it does not change the result. Therefore, lambdas in `map`, `filter`, and `peek` should **not have side effects required for correctness**.

A short example of short-circuiting:

```java
List<Integer> firstThreeEven = Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();

// [2, 4, 6]
```

`Stream.iterate(1, n -> n + 1)` is a source generating a potentially infinite sequence; `limit(3)` limits the number of output elements. There is no need to store the entire infinite sequence. Conversely, demanding evaluation of an entire infinite source with non-terminating operations, such as an unbounded `.count()` on an endless increasing sequence, is inappropriate.

**Be careful with `sorted`, `distinct`, and stateful steps:** they may need memory/computation over many elements before returning results. Laziness does not mean memory cost is always constant, especially with large or infinite sources.

## 6. A Stream Is a Single-Use Processing Chain

An important design rule: **each Stream instance can only be linked to one pipeline and consumed once**. You can write:

```java
long count = numbers.stream().filter(n -> n > 0).count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
```

If `numbers` is a `List<Integer>`, each call to `numbers.stream()` returns a new instance. This is valid because the source list can still be traversed again.

Incorrect example:

```java
// Wrong: do not reuse a Stream after a terminal operation.
Stream<Integer> oneShot = Stream.of(1, 2, 3);
long count = oneShot.count();
List<Integer> values = oneShot.toList(); // IllegalStateException
```

Even without a terminal operation, **reusing a Stream branch** to create multiple pipeline branches is also not proper usage. Many operations already link the original Stream to another pipeline; reuse cases can be detected and throw `IllegalStateException`. When you want multiple computations, create a new Stream from the source or aggregate metrics in an appropriate terminal/collector.

You can use `Supplier<Stream<T>>` to describe how to create a **fresh pipeline on each call**:

```java
List<String> data = List.of("a", "bbb", "cc");

java.util.function.Supplier<Stream<String>> pipeline =
        () -> data.stream().filter(s -> s.length() > 1);

long count = pipeline.get().count();         // 2
List<String> values = pipeline.get().toList(); // [bbb, cc]
```

Each `pipeline.get()` creates an independent Stream. If the source is I/O, a stateful generator, or a one-shot source, calling the supplier multiple times **does not automatically guarantee** the data can be replayed; you must understand the lifecycle and reopenability of the source.

## 7. Producing a Result Does Not Mean the Stream Stores the Result

A Stream can terminate in many forms:

```java
List<String> values = Stream.of("a", "bb").toList();
long size = Stream.of("a", "bb").count();
boolean exists = Stream.of("a", "bb").anyMatch(s -> s.length() == 2);
java.util.Optional<String> first = Stream.of("a", "bb").findFirst();
String joined = Stream.of("a", "bb").collect(
        java.util.stream.Collectors.joining(","));
```

Corresponding results: `[a, bb]`, `2`, `true`, `Optional[a]`, `"a,bb"`. On each line there is **a new Stream**, so this is completely valid.

`Stream.toList()` returns an unmodifiable List (Java 16+). `Collectors.toList()` **makes no guarantees** about the type, mutability, implementation, or thread-safety of the returned List. If you need a mutable `ArrayList`, request it explicitly:

```java
List<String> editable = Stream.of("a", "bb")
        .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
editable.add("ccc"); // Valid.
```

This snippet assumes `java.util.List`, `java.util.ArrayList`, and `java.util.stream.Stream` are imported. Whether the final result is a `List`, `Set`, `Map`, or an aggregate value, they are **the result of the computation**, not proof that the Stream is a collection. Do not use a Stream as a cache or a long-lived owner of a list.

## 8. Relationship with the Source and Limits to Respect

### A Stream Does Not Automatically Copy Source Data

If you call `list.stream()` on an `ArrayList`, the Stream may hold a reference to the source's traversal mechanism. You should not assume the Stream takes a snapshot of all elements at the time `stream()` is called.

An important property of Streams is **non-interference**: while the pipeline is evaluating, you generally must not modify a data source that is not designed for concurrent modification. For example, modifying an `ArrayList` from a `map`/`forEach` lambda while traversing that same list can lead to unpredictable results or `ConcurrentModificationException` and is not considered a safe way to modify a list.

Distinguish two situations:

- In the demo, `source.add("Bao")` was called **after** the pipeline finished, so it did not affect the already created result list.
- Modifying the source **while** the pipeline is processing is a different matter, which should be avoided or handled with an allowed concurrent structure/design.

For sources that support concurrent modification or late binding, specific data visibility rules depend on the source; do not assume every Stream will see new data the same way. When a stable snapshot is needed, make a copy at the appropriate time (for example `List.copyOf(original)` when elements and null constraints allow), and process that copy.

### Order Is Not Guaranteed

A Stream may or may not have an *encounter order*, depending on the source and operations. `List.stream()` usually preserves the List's order; `HashSet.stream()` makes no ordering guarantees. Operations like `unordered()` can relax ordering constraints when appropriate. For a parallel Stream, `forEach` does not guarantee encounter order, whereas `forEachOrdered` preserves encounter order when the source is ordered (at a coordination cost).

`parallel()` does not turn a Stream into parallel storage; it only requests that the pipeline may be executed in parallel. Avoid shared mutable state inside lambdas. Actual performance depends on data size, operation types, source splitting, synchronization overhead, and side effects.

### Sources with Resources That Must Be Closed

For a Stream obtained from `Files.lines(path)`, you must close the Stream to release file resources. An illustrative example inside a method declared with `throws IOException`:

```java
try (Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    long nonBlankLines = lines
            .filter(s -> !s.isBlank())
            .count();
    System.out.println(nonBlankLines);
}
```

Here `path` is a `java.nio.file.Path` variable and `Stream` must be imported or written with its fully qualified name. This is **not** a standalone source program. `try-with-resources` calls `close()` upon completion or error. A terminal operation by itself does not imply closing all resources. Streams from ordinary collections do not need manual closing because they do not hold external resources like file handles.

## 9. Common Conceptual and Programming Mistakes

**1. Calling `stream()` and thinking a copy was created.**

```java
Stream<String> view = names.stream();
```

This is a processing pipeline declaration; there is no resulting `List`. To copy/collect, you need a terminal operation like `toList()` or an appropriate collector. Pay attention to the mutability of the created list.

**2. Thinking `filter` removes elements from the collection.**

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
List<Integer> even = source.stream()
        .filter(n -> n % 2 == 0)
        .toList();
// even = [2, 4]; source is still [1, 2, 3, 4].
```

`filter` only decides which elements proceed down the pipeline; it does not call `source.remove(...)`.

**3. Calling a terminal operation twice on one Stream.**

```java
Stream<String> s = Stream.of("a", "b");
s.count();
s.findFirst(); // Invalid: the Stream has already been consumed.
```

To get two results, create two Streams from a re-traversable source or use a suitable aggregation.

**4. Relying on side effects in `peek`/`map`.**

```java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println(n);
            return n * 2;
        })
        .count();
```

Do not expect `println` to definitely run three times: `count` optimization may exist without applying `map` to each element. Use an appropriate terminal operation if the goal is a side effect, and avoid requiring side effects for correctness.

**5. Assuming Streams always save RAM.** `sorted()` may have to gather many elements before emitting output; calling `toList()` explicitly builds a result list in memory. For huge files, `Files.lines` can read as a stream, but ending with `toList()` can still consume a very large amount of memory.

**6. Using an infinite Stream with an unbounded terminal operation.** `Stream.iterate(...)` or `Stream.generate(...)` may not terminate. Use `limit`, a terminating predicate, or appropriate stopping mechanisms when needed. With an infinite source and stateful operations like `sorted`, consider both termination and memory.

**7. Forgetting to close I/O Streams.** `Files.lines` holds OS resources; use `try-with-resources`. Ordinary Streams from a `List` do not need to be closed.

**8. Attaching `List` behavior to every source.** A Stream from a `HashSet` has no ordering guarantee like a `List`; a source may be mutable, single-use, or generate elements on demand. Always read the contract of the specific source.

**9. Confusing `Stream<T>` and `IntStream`.** `Stream<Integer>` holds `Integer` reference-type values; `IntStream` is a specialized stream for `int`, providing `sum` and `average` while avoiding unnecessary boxing in many operations. `boxed()` converts an `IntStream` to `Stream<Integer>` when the generic API is needed.

## 10. Decision Process: Choosing Stream or Collection

Choose a **collection** when you need to:

- Keep elements for lookup, repeated access, or addition/removal according to a contract.
- Store long-term data state in memory.
- Use structural APIs such as `List.get(index)` or `Map.get(key)`.

Choose a **Stream** when you need to:

- Express a single pass of processing: filtering, transforming, grouping, aggregating, or searching.
- Combine multiple steps without manually creating intermediate Lists after each step.
- Process part of a source or generate elements on demand when operations allow early termination.
- Use a clear pipeline with stateless functions and minimal side effects.

The two approaches are not opposed: a collection can be a Stream source; a Stream can return a resulting collection. Depending on the need for error handling, `break`/`continue`, I/O, and complex state updates, a traditional `for` loop is sometimes clearer than a Stream.

## 11. Self-Check Exercises

1. Given `List.of(1, 2, 3, 4, 5)`, use a Stream to create a List of squares of the odd numbers. Explain whether the original list changes.
2. Create a `Stream<String>` and call only `map(String::toUpperCase)`. When can the lambda actually be executed? Add the `toList()` terminal operation.
3. Why does `Stream.of(1, 2, 3).count()` not turn the Stream into a storage structure? What type is the result?
4. Write a `Supplier<Stream<Integer>>` that creates an even-number Stream from a `List<Integer>` and call it twice to get the sum and count, creating a new Stream each time.
5. Using `Stream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0).limit(3).toList()`, predict the result and explain why the operation terminates even though the source is not finite.
6. Read a file using `Files.lines`, count the non-blank lines, and ensure the resource is closed using `try-with-resources`.

**Hints:** (1) `source.stream().filter(n -> n % 2 != 0).map(n -> n * n).toList()` gives `[1, 9, 25]`, `source` is unchanged. (2) Intermediate operations are typically lazy and run when the terminal operation demands elements. (3) `count()` returns `long` and the Stream is consumed. (4) `() -> source.stream().filter(n -> n % 2 == 0)` creates a new pipeline for each `get()`. (5) `[2, 4, 6]` because `limit(3)` restricts the number of output elements. (6) Place `Files.lines(path)` in the `try` header and the `count()` terminal operation inside.

Key takeaway: **A Collection holds data; a Stream describes processing data from a source**. Intermediate operations are typically lazy, terminal operations trigger computation, the same Stream instance is single-use only, and the source collection is not mutated by `filter`/`map`. Understanding this distinction helps you choose the right API, avoid reusing Streams, avoid false assumptions about memory, and control the lifecycle of data sources.
