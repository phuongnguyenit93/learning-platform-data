# Joining Sources with Stream.concat and Managing Concatenation Chains

In the Java Stream API, data is often scattered across multiple sources: lists of new and old orders, primary and fallback lookup results, daily log segments, or two sets of records that need to pass through the same pipeline. `Stream.concat` lets you create **one unified Stream from two existing Streams**, so you can continue using `filter`, `map`, `reduce`, `collect`, and other operations in a declarative style.

This lesson belongs to the **Streams from Existing Data** chapter of the `JAVA_STREAM_API` module. The goal is to understand element ordering when concatenating, *laziness*, single-use lifecycle, how to close resource-holding sources, and when to switch from `Stream.concat` to organizing multiple sources with `flatMap`. These decisions directly affect correctness, memory, and performance, especially when handling I/O or running in parallel.

## 1. How Does Stream.concat Join Two Sources?

Signature of the static method in `java.util.stream.Stream`:

```java
public static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b
);
```

`Stream.concat(a, b)` creates a new Stream consisting of the elements of `a` followed by the elements of `b`. If **both Streams have an encounter order**, the resulting Stream preserves each source's order and places all elements of `a` before `b`.

```text
Source A: [A1, A2, A3] ─┐
                        ├─ Stream.concat(A, B) → [A1, A2, A3, B1, B2]
Source B: [B1, B2] ─────┘
```

Basic example, usable since Java 8:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> current = Arrays.asList("An", "Binh");
List<String> archived = Arrays.asList("Chi", "Dung");

List<String> all = Stream.concat(
        current.stream(),
        archived.stream()
).collect(Collectors.toList());

System.out.println(all); // [An, Binh, Chi, Dung]
```

Points to remember:

- `concat` takes **two Streams**, not two `List`s directly. For collections, call `stream()` first.
- `concat` creates a **new pipeline**, without copying both sources entirely into a collection at call time. Elements are processed when a terminal operation is invoked.
- Concatenation does not automatically remove duplicates, does not re-sort, and does not interleave the two sources.
- Each argument is a **single-use** Stream. After passing them into the concatenated pipeline, you must not continue using the two source Streams independently.
- If one source is empty, the result carries the elements of the other source. Both sources must be non-`null`; passing `null` causes a `NullPointerException`.

The difference from `Stream.of` is particularly easy to confuse:

```java
Stream<String> a = Stream.of("x", "y");
Stream<String> b = Stream.of("z");

Stream<Stream<String>> nested = Stream.of(a, b); // 2 elements, each element is a Stream
// Only wraps references; a and b have not been consumed at this point.
```

`Stream.of(a, b)` creates a Stream **containing two Stream objects**. `Stream.concat(a, b)` creates a Stream **containing the elements inside** those two Streams. If you want to combine multiple sources, `flatMap` can flatten a nested Stream, though resources and source counts must be considered in later sections.

## 2. Concatenating Pipelines Is Lazy, but Creating Sources May Not Be

Separate two distinct moments in time:

1. **Creating sources and building the pipeline:** Java evaluates the argument expressions to obtain two Streams and then creates the concatenated Stream.
2. **Traversing elements:** Usually happens only when calling a terminal operation such as `count`, `toArray`, `findFirst`, or `collect`.

```java
import java.util.stream.Stream;

Stream<String> left = Stream.of("cat", "dog")
        .peek(s -> System.out.println("A: " + s));
Stream<String> right = Stream.of("bird")
        .peek(s -> System.out.println("B: " + s));

Stream<String> merged = Stream.concat(left, right);
System.out.println("Pipeline created");

merged.forEachOrdered(System.out::println);
```

In a sequential pipeline, the output from `peek` and the elements begin appearing when `forEachOrdered` runs, after the message `Pipeline created`. `peek` only illustrates execution; do not rely on it for mandatory logging or cleanup because some terminal operations can optimize away element traversal.

In particular, **laziness in traversal does not mean laziness in opening resources**:

```java
// Both Files.lines(...) calls are evaluated when creating joined,
// even before any terminal operation on joined.
Stream<String> joined = Stream.concat(
        Files.lines(firstPath),
        Files.lines(secondPath)
);
```

This snippet illustrates when sources are opened, **not a safe resource management pattern**. If opening the second file fails, the first file may remain open; if processing succeeds without closing, both may also remain holding resources. Section 4 shows how to write this safely.

### Concatenating with Short-Circuiting Operations

```java
import java.util.stream.Stream;

Stream<String> joined = Stream.concat(
        Stream.of("A1", "A2", "A3"),
        Stream.of("B1", "B2")
);

joined.limit(2).forEachOrdered(System.out::println);
// A1
// A2
```

With two ordered sources and a sequential pipeline like above, `limit(2)` does not need to pull elements from source B. Similarly, `findFirst()` usually takes from A when A has elements. However, if you add operations that must observe all data, such as `sorted()`, execution cost can increase; and for pipelines without encounter order or when running in parallel, do not infer internal processing order.

**Important consequence:** even if a short-circuiting operation has not read any elements from B, if B has already opened a file or held a connection, B must still be closed.

## 3. Ordering, Duplicates, Data Types, and Parallel Mode

| Property | Behavior on concat | Practical significance |
| --- | --- | --- |
| Encounter order | Ordered if **both A and B** are ordered | Data from A precedes B in encounter order |
| Duplicate elements | Preserved | Use `distinct()` if deduplication is truly needed |
| Sorting | Does not automatically create a global sort order | Two individually sorted sources do not guarantee a sorted result |
| Laziness | Remains a lazy pipeline | No full copy of data when calling `concat` |
| Source reuse | Cannot reuse A/B or the resulting Stream | Create new Streams for subsequent passes |
| Parallelism | Result is parallel if **at least one** source is parallel | Must consider ordering and coordination cost |
| Primitives | Has `IntStream.concat`, `LongStream.concat`, `DoubleStream.concat` | Avoids unnecessary boxing |

### Prioritizing the First Source and Deduplicating

Suppose you prioritize IDs from a primary source, then supplement with IDs not yet present from a fallback source:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> primary = Arrays.asList("u01", "u02", "u02");
List<String> fallback = Arrays.asList("u02", "u03");

List<String> ids = Stream.concat(
        primary.stream(),
        fallback.stream()
).distinct().collect(Collectors.toList());

System.out.println(ids); // [u01, u02, u03]
```

In a pipeline with encounter order, `distinct()` keeps the **first occurrence**, so the priority order of the primary source is preserved. However, `distinct()` determines duplicates via `equals`/`hashCode`, which can consume memory for the set of seen elements; for object records, clarify whether two records are considered duplicates by ID or by the entire object.

### Two Individually Sorted Sources May Still Need sorted()

```java
Stream<Integer> a = Stream.of(1, 4, 7);
Stream<Integer> b = Stream.of(2, 3, 8);

Stream.concat(a, b).forEachOrdered(System.out::println);
// 1, 4, 7, 2, 3, 8  (not globally ascending order)
```

If a globally ascending order is required, use `Stream.concat(a, b).sorted()` on **new Streams**. `sorted()` may need to buffer many elements in memory before emitting results; for two large already-sorted sources, the *merge sorted streams* problem calls for a dedicated merge algorithm rather than merely concatenating and sorting.

### Concatenating Primitive Streams

```java
import java.util.stream.IntStream;

int sum = IntStream.concat(
        IntStream.rangeClosed(1, 3),
        IntStream.of(10, 20)
).sum();

System.out.println(sum); // 36
```

`Stream.concat` works with object Streams. When the sources are `IntStream`, `LongStream`, or `DoubleStream`, use the corresponding `concat` method for a more efficient primitive pipeline, avoiding boxing just to concatenate.

### Notes When Running in Parallel

```java
Stream<Integer> merged = Stream.concat(
        Stream.of(1, 2).parallel(),
        Stream.of(3, 4)
);

System.out.println(merged.isParallel()); // true
merged.forEachOrdered(System.out::println); // 1, 2, 3, 4
```

`forEachOrdered` guarantees encounter order when that order exists; `forEach` on a parallel pipeline does not guarantee print order. Concatenation does not automatically guarantee speedup: work-splitting characteristics of the two sources and ordering constraints can affect performance. Only use parallel when processing is independent, does not rely on shared state, and has a clear performance justification.

## 4. Lifecycle and Properly Closing Concatenated Chains

`Stream.concat` connects **two source Streams into a single-use pipeline**. Terminal operations like `count()` or `collect()` consume the pipeline, but **do not automatically call `close()`**. This is especially important for Streams returned from `Files.lines`, `Files.list`, or I/O sources.

### Closing the Concatenated Stream Closes Both Sources

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> events = new ArrayList<>();

Stream<String> a = Stream.of("A")
        .onClose(() -> events.add("close A"));
Stream<String> b = Stream.of("B")
        .onClose(() -> events.add("close B"));

Stream<String> joined = Stream.concat(a, b);
long count = joined.count();

System.out.println(count);  // 2
System.out.println(events); // []: count() does not close sources automatically

joined.close();
System.out.println(events); // [close A, close B]
```

By contract, closing the Stream returned by `Stream.concat` executes the close handlers of both A and B. Handlers registered with `onClose` run on close, even if the sources were not fully traversed. If a close handler throws an exception, Java still attempts to run the remaining handlers and may attach additional exceptions as *suppressed exceptions*.

If a source Stream were used in multiple independent places, combining and closing it jointly could break the other usages. Do not reuse the same source as in `Stream.concat(s, s)`, nor use `a`/`b` after attaching them to the concatenated pipeline.

### Concatenating Two Files: Open and Close in the Same Scope

This is the recommended pattern when joining yesterday's and today's log lines and counting warnings:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countWarnings(Path yesterday, Path today)
        throws IOException {
    try (Stream<String> oldLines =
                 Files.lines(yesterday, StandardCharsets.UTF_8);
         Stream<String> newLines =
                 Files.lines(today, StandardCharsets.UTF_8);
         Stream<String> joined =
                 Stream.concat(oldLines, newLines)) {

        return joined
                .filter(line -> line.contains("WARN"))
                .count();
    }
}
```

The `try-with-resources` block handles these scenarios simultaneously:

1. Both sources open successfully: once processing finishes, `joined` is closed, and consequently both sources are closed.
2. Opening the second source fails: Java closes `oldLines` that was opened earlier, leaving no dangling first file.
3. The pipeline throws an exception while reading or processing: Java still closes resources upon exiting the block.
4. Closing `joined` closes the sources, and then the `try` block may call `close()` again on each declared Stream. Closing an already-closed Stream is a no-op.

The example above returns a **computed result** (`long`), so the caller does not have to hold I/O resources. When you must return a Stream for the caller to process, design an explicit ownership contract: who opens it, who calls `close()`, and when it can be consumed. Never return a Stream created inside a `try-with-resources` whose `try` block has already exited before the caller uses it.

One note on errors: `Files.lines(...)` can throw `IOException` when opening; read errors occurring during lazy traversal can be wrapped as `UncheckedIOException`. The closing mechanism in `try-with-resources` still applies in both cases.

### Case with Short-Circuiting Operations

```java
public static boolean containsError(Path first, Path second)
        throws IOException {
    try (Stream<String> a = Files.lines(first);
         Stream<String> b = Files.lines(second);
         Stream<String> joined = Stream.concat(a, b)) {
        return joined.anyMatch(line -> line.contains("ERROR"));
    }
}
```

When `ERROR` is found in the first source, `anyMatch` can stop without reading the second source. Even so, **both opened Streams are still closed**. This is why resource lifecycles must be tied to a `try` scope instead of relying on whether the terminal operation reads every element.

## 5. Joining More Than Two Sources

`Stream.concat` accepts only **two arguments**. You can nest calls to join three sources:

```java
Stream<String> three = Stream.concat(
        Stream.concat(
                Stream.of("A1", "A2"),
                Stream.of("B1")
        ),
        Stream.of("C1", "C2")
);
```

For a small, fixed number of sources, this is clear. However, **do not build deeply nested concatenation chains** inside a loop over hundreds or thousands of sources. The Java documentation warns that accessing elements of repeatedly concatenated Streams can produce very deep call chains, potentially even `StackOverflowError`.

### Multiple Collections: Use flatMap to Flatten

```java
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

List<List<String>> batches = Arrays.asList(
        Arrays.asList("a1", "a2"),
        Arrays.asList("b1"),
        Arrays.asList("c1", "c2")
);

List<String> all = batches.stream()
        .flatMap(Collection::stream)
        .collect(Collectors.toList());

System.out.println(all); // [a1, a2, b1, c1, c2]
```

`batches.stream()` creates a Stream of collections; `flatMap(Collection::stream)` turns each collection into a Stream of elements and flattens them in encounter order. This is the natural approach when you have a **variable-length list of sources** and the sources are collections that do not hold closable resources.

You can write `Stream.of(s1, s2, s3).flatMap(Function.identity())` when `s1`/`s2`/`s3` are already Streams. `flatMap` closes the sub-Streams it has processed, but if those sub-Streams were already opened from files beforehand and a short-circuiting operation skips some sources, the unvisited Streams may remain open. Therefore, **do not pre-create a batch of resource-holding Streams and pass them into `flatMap`**.

### Multiple Files: Open Each Source Only When Its Turn Comes

When the number of files varies, you can traverse the list of paths and open each sub-Stream inside `flatMap`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public static long countErrors(List<Path> files) {
    try (Stream<String> lines = files.stream().flatMap(path -> {
        try {
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Failed to open file: " + path, ex
            );
        }
    })) {
        return lines
                .filter(line -> line.contains("ERROR"))
                .count();
    }
}
```

With this approach, `Files.lines` is called **when the `flatMap` mapper reaches that path**, instead of opening all files when constructing the pipeline. `flatMap` is responsible for closing the sub-Stream returned by the mapper after processing it. `try-with-resources` still closes the outer pipeline when done, even if an exception occurs.

Note two points:

- Because `Files.lines` declares `IOException` while the `flatMap` mapper does not declare checked exceptions, the example wraps file-opening errors into `UncheckedIOException`. Callers invoking the method need to account for this exception type.
- Lazy opening reduces how many files are open simultaneously in a sequential pipeline, yet **does not turn file reading into an all-or-nothing transaction**. If one file fails partway through, data from earlier files may have already been processed; if writing externally inside the pipeline, there is no automatic rollback mechanism.

For parallel processing, multiple I/O sources, and resource-backed sources, carefully evaluate open/close ordering and concurrent opening limits before running the pipeline in parallel.

## 6. Designing Functions That Provide Concatenated Sources

A good API should make clear whether it returns a **computed result** or a **live Stream**:

| API shape | Lifecycle and responsibility | Suitable when |
| --- | --- | --- |
| `List<T> combine(List<T>, List<T>)` | Creates a short-lived Stream, returns collected result | Data size fits in memory |
| `Stream<T> concatViews(Collection<T>, Collection<T>)` | Returns a new pipeline; collection sources typically need no closing | Caller wants to continue filtering/mapping |
| `long analyzeFiles(Path, Path)` | Opens, processes, and closes files inside the method | Want resource responsibility kept in one place |
| `Stream<String> openJoinedFiles(Path, Path)` | Caller must close returned Stream; must handle error when opening second source | Caller wants to choose the terminal operation |
| `Stream<T> fromSuppliers(...)` | Each use must create a new pipeline from a factory | Need to analyze sources multiple times |

Example of an API returning a Stream from **two existing collections**, without opening external resources:

```java
import java.util.Collection;
import java.util.stream.Stream;

public static <T> Stream<T> concatViews(
        Collection<? extends T> first,
        Collection<? extends T> second
) {
    return Stream.concat(first.stream(), second.stream());
}
```

The caller can choose the terminal operation:

```java
long count = concatViews(
        Arrays.asList("a", "bb"),
        Arrays.asList("ccc")
).filter(s -> s.length() > 1).count(); // 2
```

Because `concatViews` creates a new Stream on each call, the caller can invoke the method again to analyze data another time. This is very different from storing a shared `Stream` variable across multiple calls.

For an API that opens two files and returns a Stream, handle the case where opening the second source fails **before** joining. A safe pattern is:

```java
public static Stream<String> openJoinedFiles(Path first, Path second)
        throws IOException {
    Stream<String> a = Files.lines(first, StandardCharsets.UTF_8);
    try {
        Stream<String> b = Files.lines(second, StandardCharsets.UTF_8);
        return Stream.concat(a, b);
    } catch (IOException | RuntimeException ex) {
        a.close();
        throw ex;
    }
}

// Caller owns the resulting Stream and must close it:
try (Stream<String> lines = openJoinedFiles(fileA, fileB)) {
    long total = lines.count();
}
```

If opening source B fails, the method closes A before rethrowing the error. Once both are open, responsibility for closing both is transferred via the resulting Stream to the caller. This pattern illustrates the ownership contract; for production APIs, also consider preserving the original exception if `close` throws, handling I/O errors during traversal, and documenting usage guidelines.

## 7. Common Errors and How to Choose

| Situation | Issue | Resolution |
| --- | --- | --- |
| `Stream.concat(listA, listB)` | `concat` expects Streams, not Lists | `listA.stream()` and `listB.stream()` |
| `Stream.of(streamA, streamB)` thinking elements were joined | Creates `Stream<Stream<T>>` | Use `concat` or `flatMap` |
| Reusing `streamA` after `Stream.concat(streamA, streamB)` | Violates single-use lifecycle | Create a new Stream |
| `Stream.concat(s, s)` | Both branches reference the same Stream | Create two independent Streams from the source |
| Concatenating sorted sources and assuming the whole is sorted | Concatenation does not perform a sorted merge | Use an appropriate merge algorithm or global `sorted()` |
| Using parallel `forEach` expecting A to always print before B | `forEach` does not guarantee order in parallel | Use `forEachOrdered` if order is needed |
| Calling `count` on a Stream joining two files without closing | Terminal operation does not auto-close | `try-with-resources` |
| Pre-creating many `Files.lines` then `flatMap` followed by `findFirst` | Unvisited sources may remain open | Open Streams inside the mapper, or manage all sources explicitly |
| Nesting `concat` thousands of levels deep | Pipeline can become very deep, risking `StackOverflowError` | Use `flatMap` with a collection or source factory |
| Using `distinct`/`sorted` on huge data ignoring memory | Stateful operations can consume significant memory | Assess scale, source characteristics, and suitable algorithms |

## 8. Short Practice Exercises

1. Given `A = [4, 1]` and `B = [3, 1]`. Predict the result of `Stream.concat(A.stream(), B.stream()).distinct().collect(toList())`. **Answer:** `[4, 1, 3]` when A/B have encounter order.
2. Concatenate `IntStream.range(0, 3)` with `IntStream.of(10)` and compute the sum. **Answer:** `13`.
3. A Stream concatenated from two `Files.lines` calls `findFirst()` and succeeds. Have both files been released? **No**; `close()` or `try-with-resources` is still required.
4. Why shouldn't you pre-open 500 `Files.lines` Streams and pass them into `flatMap` to fetch the first element? **Because** many files may remain open even though most sub-Streams are never visited.
5. Why might `Stream.concat(sortedA, sortedB)` not be ascending? **Because** concatenation places all of A before B, without comparing to interleave elements between the two sources.
6. When should you choose `flatMap(Collection::stream)`? **When** you have a list of multiple collections and want to traverse them in one flat pipeline, avoiding deeply nested `concat` calls.

**Practical rule:** Use `Stream.concat` for two sources or a small fixed number of sources; keep ordering and the single-use lifecycle clear. When joining I/O sources, manage opening and closing right inside the API structure or transfer closing responsibility to the caller transparently. When the number of sources grows, prefer creating sources on demand and flattening with `flatMap` suited to resource characteristics.
