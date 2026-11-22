# Creating a New Stream from a Source or Supplier for Multiple Passes

In Java, **a `Stream` object can only be consumed once**. After calling a terminal operation such as `count()`, `toList()`, `collect()`, `findFirst()`, or `forEach()`, you must not reuse that same stream object for another pipeline. If you want to run multiple queries on the same data source, the right approach is to **create a new Stream for each processing pass**, either directly from a re-traversable source or via a **`Supplier<Stream<T>>`** acting as a factory.

Conceptual example:

~~~java
// source is a re-traversable List<String>:
long count = source.stream().count();       // First stream
List<String> names = source.stream().toList(); // Second stream
~~~

It is not the `List` that is consumed; **it is the Stream object returned by `source.stream()` that is consumed**. The source remains intact and can produce other streams if the source itself supports re-traversal.

**Core warning:** A Supplier is only useful if each call to `get()` actually returns **a new Stream pipeline over a re-readable source**. If the Supplier always returns the same previously created Stream, or returns a new Stream that still reads from the same one-shot `Iterator`/data channel, it **does not make the data replayable**.

## 1. Distinguishing source, pipeline, and consumption

There are three objects/concepts that should be kept separate:

1. **Source**: `List`, `Set`, array, number sequence, file, generator, cursor, etc. A source may support repeated reads or only a single pass depending on its type.
2. **Stream/pipeline**: an object describing processing operations from the source, consisting of intermediate operations such as `filter`, `map`, `sorted`. These operations are typically lazy.
3. **Terminal operation**: triggers stream consumption and returns a result or performs an action, for example `count()`, `sum()`, `toList()`, `collect()`.

Correct model for a re-traversable collection:

~~~text
                 ┌─ stream() → filter(...) → count()
List<String> ────┤
                 ├─ stream() → map(...)    → toList()
                 └─ stream() → sorted()    → findFirst()
~~~

Each branch starts with **a different `stream()` call**, because each terminal operation terminates a separate pipeline.

Incorrect model:

~~~text
List<String> → stream() ── count()
                     └── toList()   ✗ reusing a consumed Stream
~~~

A stream may throw `IllegalStateException` when reused (with a message similar to “stream has already been operated upon or closed”). **You should not rely on the specific exception message**, nor assume that every invalid reuse is detected at the same point; the API contract itself forbids reuse.

## 2. Executable example: reusing the same Stream is wrong

Create the file `StreamReuseFailureDemo.java`:

~~~java
import java.util.stream.Stream;

public class StreamReuseFailureDemo {
    public static void main(String[] args) {
        Stream<Integer> numbers = Stream.of(2, 4, 6);

        System.out.println("first count=" + numbers.count());

        try {
            System.out.println("second count=" + numbers.count());
        } catch (IllegalStateException ex) {
            System.out.println("second=IllegalStateException");
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 StreamReuseFailureDemo.java
java StreamReuseFailureDemo
~~~

Output:

~~~text
first count=3
second=IllegalStateException
~~~

After the first `count()`, the stream has been consumed. The second call cannot turn the old `Stream<Integer>` into a “fresh” object just by calling `count()` again.

This **still holds for an empty Stream**: `Stream.empty().count()` returns 0, but that stream has also been used. Do not use `count() == 0` as a sign that a stream can still be reused.

It is not only terminal operations that matter: **linking pipeline operations to a stream that has already been linked/closed can also be rejected**. Therefore, the safest rule is to treat a stream as a single-use pipeline and never store it in a field for arbitrary reuse.

## 3. Creating a new Stream directly from a `Collection`

With `List<T>`, `Set<T>`, and other re-traversable collections, you can call `stream()` multiple times to create separate pipelines.

Create the file `FreshStreamFromListDemo.java`:

~~~java
import java.util.List;

public class FreshStreamFromListDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");

        long longNames = names.stream()
                .filter(name -> name.length() >= 3)
                .count();

        List<String> uppercase = names.stream()
                .map(String::toUpperCase)
                .toList();

        String first = names.stream()
                .sorted()
                .findFirst()
                .orElse("Không có");

        System.out.println("longNames=" + longNames);
        System.out.println("uppercase=" + uppercase);
        System.out.println("first=" + first);
    }
}
~~~

~~~bash
javac --release 17 FreshStreamFromListDemo.java
java FreshStreamFromListDemo
~~~

Output:

~~~text
longNames=2
uppercase=[AN, BÌNH, CHI]
first=An
~~~

Explanation: `"Bình"` has 4 UTF-16 characters, `"Chi"` has 3, `"An"` has 2, so `longNames == 2`. `String::toUpperCase` transforms each string; the original list is not consumed. `sorted()` selects `"An"` as the first string in natural order for this data.

With a `Set` that has no defined encounter order (such as `HashSet`), each new stream is still usable, but **the processing order/result may not be guaranteed**. Creating a new pipeline does not mean making the source ordered or turning unstable data into a snapshot.

## 4. `Supplier<Stream<T>>`: encapsulating how to create a new pipeline

`java.util.function.Supplier<R>` is an interface with the method `R get()`. With `R = Stream<T>`, we have a **stream factory**:

~~~java
Supplier<Stream<String>> factory = () -> names.stream();
~~~

This is an illustrative snippet inside a method that has `names: List<String>`. Each `factory.get()` calls `names.stream()` again and creates a new pipeline.

It can be written more concisely with a method reference:

~~~java
Supplier<Stream<String>> factory = names::stream;
~~~

The two forms above are equivalent in purpose. The Supplier **does not pre-hold the stream's results**; `get()` only creates a new stream, while the results are computed when the new pipeline has a terminal operation.

Create the file `StreamSupplierDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamSupplierDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 6);

        Supplier<Stream<Integer>> factory = values::stream;

        long count = factory.get()
                .filter(n -> n >= 4)
                .count();

        int sum = factory.get()
                .mapToInt(Integer::intValue)
                .sum();

        List<Integer> descending = factory.get()
                .sorted(Comparator.reverseOrder())
                .toList();

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);
        System.out.println("descending=" + descending);
    }
}
~~~

~~~bash
javac --release 17 StreamSupplierDemo.java
java StreamSupplierDemo
~~~

Output:

~~~text
count=2
sum=12
descending=[6, 4, 2]
~~~

**Three calls to `factory.get()`** create three different streams. If you write `Stream<Integer> s = factory.get()` once and then use `s` three times, the reuse problem still occurs. Remember to place `get()` **inside each processing pass**.

## 5. A factory can create intermediate pipelines too, not just the source

A Supplier can encapsulate common processing operations so that multiple terminal operations reuse **the pipeline definition**, rather than reusing the stream object.

Create the file `ReusablePipelineFactoryDemo.java`:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class ReusablePipelineFactoryDemo {
    public static void main(String[] args) {
        List<String> raw = List.of(" Ana ", "Bo", "Chi", " An ");

        Supplier<Stream<String>> validNames = () -> raw.stream()
                .map(String::trim)
                .filter(s -> s.length() >= 3);

        long count = validNames.get().count();
        List<String> names = validNames.get().sorted().toList();

        System.out.println("count=" + count);
        System.out.println("names=" + names);
    }
}
~~~

~~~bash
javac --release 17 ReusablePipelineFactoryDemo.java
java ReusablePipelineFactoryDemo
~~~

Output:

~~~text
count=2
names=[Ana, Chi]
~~~

When `validNames.get()` is called, the lambda creates a **new pipeline** from `raw.stream()`, then attaches `map` and `filter`. The pipeline only actually processes data when `count()` or `toList()` is called.

This approach is useful when multiple queries share common filtering/transformation steps, but keep in mind:

- Intermediate steps must be **stateless/non-interfering**, especially if the factory is called multiple times or used in parallel.
- If the source list changes between two calls, the two pipelines **may produce different results**. A factory does not automatically guarantee an immutable snapshot.
- Do not instantiate a `Stream` object outside the supplier and chain from it on each `get()`; that still attaches to the old pipeline.

## 6. Two Supplier styles that look similar, but one is wrong

**Correct — create the Stream inside `get()`:**

~~~java
// Correct: each call to get() executes numbers.stream().
Supplier<Stream<Integer>> correct = numbers::stream;
~~~

**Wrong — create the Stream beforehand and always return the old object:**

~~~java
// Wrong: sourceStream is created only ONCE.
Stream<Integer> sourceStream = numbers.stream();
Supplier<Stream<Integer>> broken = () -> sourceStream;
~~~

Example program `BrokenStreamSupplierDemo.java`:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class BrokenStreamSupplierDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3);
        Stream<Integer> original = numbers.stream();

        Supplier<Stream<Integer>> broken = () -> original;

        System.out.println("first=" + broken.get().count());

        try {
            System.out.println("second=" + broken.get().count());
        } catch (IllegalStateException ex) {
            System.out.println("second=IllegalStateException");
        }
    }
}
~~~

~~~bash
javac --release 17 BrokenStreamSupplierDemo.java
java BrokenStreamSupplierDemo
~~~

Output:

~~~text
first=3
second=IllegalStateException
~~~

A lambda `() -> original` only returns **the captured reference**; the lambda does not turn that object into a new one. During code review, check the expression that runs on each `get()`: does it actually recreate the stream from a source that allows re-traversal?

Similarly, do not use:

~~~java
// Wrong if the getter returns the same old stream instance:
Supplier<Stream<String>> factory = () -> cachedStream;
~~~

If caching is needed for multiple passes, it is usually better to **cache the materialized data** in a `List`/collection (if size and update rules allow), and then create `list.stream()` on each pass.

## 7. A new Stream does not mean the source is read from the beginning again

A subtle trap: a Supplier can create **new Stream objects** while reusing **the same `Iterator` that has already advanced**.

Create the file `OneShotIteratorDemo.java`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class OneShotIteratorDemo {
    public static void main(String[] args) {
        Iterator<Integer> sharedIterator =
                List.of(1, 2, 3).iterator();

        Supplier<Stream<Integer>> wrong = () -> StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                        sharedIterator, Spliterator.ORDERED),
                false);

        System.out.println("first=" + wrong.get().toList());
        System.out.println("second=" + wrong.get().toList());
    }
}
~~~

~~~bash
javac --release 17 OneShotIteratorDemo.java
java OneShotIteratorDemo
~~~

Output:

~~~text
first=[1, 2, 3]
second=[]
~~~

**Why?** The two calls to `wrong.get()` do indeed create two different `Stream` instances, but both use one `Iterator` that was already consumed in the first pass. `Iterator` has no API to automatically rewind to the beginning.

The right approach when the source is a collection:

~~~java
// Illustration: values is a re-traversable List<Integer>.
Supplier<Stream<Integer>> correct = values::stream;
~~~

If data truly comes from a network socket, cursor, or single-read source, you must **reopen the source according to its contract**, **materialize/cache the data** when appropriate, or **design a single processing pass**. A Supplier is only a way to encapsulate stream creation behavior; **it does not create replay capability when the source does not support it**.

## 8. File sources: each pass must open anew and close properly

`Files.lines(Path, Charset)` returns a `Stream<String>` that reads lines from a file. Unlike `List.stream()`, this stream holds I/O resources; it must be **closed** after processing. A Supplier can open a new file stream for each pass, but because `Supplier.get()` does not declare checked exceptions, you must decide how to handle `IOException`.

Create the file `FileStreamFactoryDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class FileStreamFactoryDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("stream-factory-", ".txt");
        try {
            Files.write(path, List.of("An", "Bình", "Chi"),
                    StandardCharsets.UTF_8);

            Supplier<Stream<String>> lines = () -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            };

            try (Stream<String> first = lines.get()) {
                long count = first.filter(s -> s.length() >= 3).count();
                System.out.println("count=" + count);
            }

            try (Stream<String> second = lines.get()) {
                System.out.println("lines=" + second.toList());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac --release 17 FileStreamFactoryDemo.java
java FileStreamFactoryDemo
~~~

Output:

~~~text
count=2
lines=[An, Bình, Chi]
~~~

Explanation:

1. `Files.write(...)` creates deterministic content without needing an external file prepared by the learner.
2. Each `lines.get()` calls `Files.lines` again and opens **a new read stream**.
3. `try (Stream<String> first = ...)` guarantees `close()` is called even if the terminal operation throws an exception.
4. `UncheckedIOException` wraps the checked `IOException` occurring at the open step, because `Supplier.get()` does not declare `throws IOException`.
5. `finally` deletes the temporary file after both streams have closed; a successful run prints the exact two lines above.

**Note:** file read errors during consumption can also surface as `UncheckedIOException`. The path/file may change or be deleted between `get()` calls, so results are not automatically identical. Opening multiple times incurs I/O cost; you should not do so casually for very large files.

**Do not** write `Stream<String> s = Files.lines(path)` once and reuse `s` after `close()`: a closed stream can no longer be used. Do not assume that terminal operations like `count()` automatically close resource streams; `try-with-resources` or explicit closing responsibility is what handles closing the underlying resource.

## 9. Single-read sources: alternative approaches

Some sources are inherently *one-shot* or expensive to reopen:

- an `Iterator` that has reached the end;
- `BufferedReader.lines()` attached to the same reader;
- data from a socket or a single-pass streaming API;
- an open database cursor or `ResultSet`;
- a file source reading from a shifted position/offset that does not support reset.

A `Supplier<Stream<T>>` factory is only valid if it **can recreate the appropriate source** on each `get()`, or makes clear that each pass gets **fresh data** rather than the same snapshot.

| Need | Usually suitable option | Trade-off |
| --- | --- | --- |
| Source is a small, re-traversable collection | Call `collection.stream()` each pass | Simple, no extra caching; data may change if the collection is mutable. |
| Want to reuse `filter/map` logic | `Supplier<Stream<T>>` creating a new pipeline | Must ensure each `get()` actually creates a stream from a valid source. |
| Re-openable I/O source | Supplier reopens and caller closes each stream | Incurs multiple open/read costs; I/O errors and snapshots must be handled. |
| One-shot source, data fits in memory | Collect into a collection once, then take `list.stream()` | Uses memory; must consider freshness and sensitive data. |
| One-shot source, cannot cache | Aggregate multiple results in **a single pass** | Can use a custom collector, `teeing`, or an aggregated processing pipeline. |
| Want identical results across passes | Create an immutable snapshot or versioned data | Must define snapshot timing and cost level. |

**Do not confuse `supplier.get()` with “restarting” an I/O source**. Creating a new `Stream` over the same consumed cursor may return empty or incorrect content. Reopening a database query may return **new** data if the database changes; if the same snapshot is required, an appropriate data consistency strategy is needed.

## 10. Caching data when appropriate: `toList()` and new streams

If a source can only be read once and the dataset is small enough to fit in memory, you can materialize it into a list:

~~~java
// Illustration: original is a one-shot Stream<String>, containing no nulls
List<String> snapshot = original.toList();

long count = snapshot.stream().count();
List<String> sorted = snapshot.stream().sorted().toList();
~~~

`Stream.toList()` returns a list that does not support modification via `add/remove`, but **does not deep-copy mutable objects** contained inside. To have a truly content-immutable snapshot, you need to design immutable element types or copy appropriately.

If the source contains mutable objects and they are modified between two reads, two pipelines on the same `List` can still observe different data. If the source is large or infinite, you should not use `toList()` unconditionally because it can exhaust memory or fail to terminate.

Create the file `SnapshotAndStreamsDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class SnapshotAndStreamsDemo {
    public static void main(String[] args) {
        Stream<Integer> once = Stream.of(9, 2, 7);

        List<Integer> snapshot = once.toList();

        System.out.println("count=" + snapshot.stream().count());
        System.out.println("ascending="
                + snapshot.stream().sorted().toList());
        System.out.println("maximum="
                + snapshot.stream()
                        .max(Comparator.naturalOrder())
                        .orElseThrow());
    }
}
~~~

~~~bash
javac --release 17 SnapshotAndStreamsDemo.java
java SnapshotAndStreamsDemo
~~~

Output:

~~~text
count=3
ascending=[2, 7, 9]
maximum=9
~~~

The stream `once` was consumed **once** to create `snapshot`; the three subsequent processing passes create new streams from the list, without “reviving” `once`.

## 11. Avoiding multiple source reads when a single pass is enough

Sometimes you do not need a `Supplier` because the results can be computed in **a single collect pass**.

For example, instead of `stream.count()` and then running the stream again to sum string lengths, in Java 12+ you can use `Collectors.teeing`:

Create the file `OnePassTeeingDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class OnePassTeeingDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");

        String report = names.stream().collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(s -> s.length()),
                (count, total) ->
                        "count=" + count + ", totalLength=" + total));

        System.out.println(report);
    }
}
~~~

~~~bash
javac --release 17 OnePassTeeingDemo.java
java OnePassTeeingDemo
~~~

Output:

~~~text
count=3, totalLength=9
~~~

`teeing` takes two collectors and a merger function, so there is no need to create multiple independent streams just to gather two metrics. Similarly, `IntStream.summaryStatistics()` or `Collectors.summarizingInt(...)` can compute count, sum, min, max, and average in a single pass.

Keep the distinction clear:

- **Two independent queries at two points in time**: a fresh stream factory is the natural choice if the source is replayable.
- **Two metrics on the same source traversal**: an aggregating collector is a good choice when the source is one-shot or re-reading is expensive.
- **Queries requiring the same snapshot**: materialize or ensure a consistent data version; do not assume two stream openings are equivalent.

## 12. `Supplier<Stream<T>>` is not `Stream.generate(Supplier<T>)`

Both APIs have the word `Supplier`, but **their roles are completely different**:

~~~java
// Stream factory: each get creates a new Stream.
Supplier<Stream<Integer>> factory =
        () -> Stream.of(1, 2, 3);

// Supplier creating each ELEMENT:
Stream<Integer> generated =
        Stream.generate(() -> 7);
~~~

In the first case, `factory.get()` returns a `Stream<Integer>` for you to consume independently; `get()` can be called multiple times.

In the latter case, `Stream.generate(() -> 7)` returns **a potentially infinite Stream**, emitting elements of 7 as requested by the terminal operation. `generated` itself is still **a single-use stream**.

If you mistakenly pass a `Supplier<Stream<Integer>>` to `Stream.generate`, the result will have type `Stream<Stream<Integer>>`, rather than automatically becoming a mechanism to rerun a pipeline or flatten data.

The `Supplier` used in `Collector.supplier()` has yet another role: creating **an accumulation container** such as `ArrayList`, not recreating the source stream. Read the full generic type to avoid confusing similar-sounding terms.

## 13. Mutable sources: each new Stream may see a different version of the data

`Supplier<Stream<T>>` typically **captures a reference to the collection**, rather than creating a snapshot. Two calls to `get()` can yield different results if the collection changes between the two passes.

Create the file `ChangingSourceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class ChangingSourceDemo {
    public static void main(String[] args) {
        ArrayList<String> names =
                new ArrayList<>(List.of("An", "Bình"));

        Supplier<Stream<String>> factory = names::stream;

        System.out.println("first=" + factory.get().toList());

        names.add("Chi"); // Modified BETWEEN two processing passes.

        System.out.println("second=" + factory.get().toList());
    }
}
~~~

~~~bash
javac --release 17 ChangingSourceDemo.java
java ChangingSourceDemo
~~~

Output:

~~~text
first=[An, Bình]
second=[An, Bình, Chi]
~~~

The case above is valid because the modification happens **after the first stream finishes, and before creating/consuming the second stream**. Conversely, you should not modify an `ArrayList` while a stream is traversing it; doing so can cause unpredictable results or `ConcurrentModificationException`.

Do not interpret “each `get()` is a new Stream” as “each `get()` reads the exact same data”. If you need to repeat over immutable data, use `List.copyOf`, immutable element types, and appropriate snapshot rules (note that `List.copyOf` does not accept null elements).

## 14. Thread-safety and parallel Streams

There are two distinct scenarios:

1. **One stream using `.parallel()`**: the framework splits the execution of a single pipeline across multiple threads; intermediate/terminal functions must satisfy stateless, non-interfering rules and be safe with parallel execution.
2. **Multiple threads concurrently calling `factory.get()`**: each call needs to create an independent pipeline, but **the source** they all read from must also have an appropriate concurrent access policy.

A factory like `() -> sharedList.stream()` creates a new pipeline, but **does not automatically make `ArrayList` thread-safe** when another thread is modifying the list. With an immutable read-only source, creating independent streams is usually easier to reason about; with a mutable source, a synchronization/snapshot strategy or an appropriate collection type is needed.

Do not use out-of-band side effects in `filter`, `map`, or terminal operations as if each new stream guaranteed callback ordering or invocation counts. Streams have optimizations, short-circuiting, and multiple execution strategies; creating a new stream does not turn side effects into a reliable contract.

If the factory calls an external stateful source, sharing a single cursor/reader across multiple threads can be even more dangerous: each `get()` must open **a truly independent resource**, or the system must clearly define access coordination.

## 15. When to use method references, lambdas, caching, or a single pass?

| Scenario | Option to consider |
| --- | --- |
| A few straightforward queries from `List<T>` | Write `list.stream()` directly at each query to keep code simple. |
| Same `filter/map` pipeline called multiple times | `Supplier<Stream<R>>` returning a new pipeline on each `get()`. |
| API accepting a factory to allow custom terminal operations | Pass `Supplier<Stream<T>>` or a query abstraction with a clear contract; define resource closing responsibility. |
| Re-openable I/O source | Supplier opens a new Stream, each caller uses `try-with-resources`. |
| One-shot source and small result | Materialize into a `List`, then create new streams from the list; consider memory. |
| One-shot source needing two metrics in the same pass | Use `teeing`, `summarizing...`, a custom collector, or single-pass sequential processing. |
| Results must be completely consistent across passes | Immutable snapshot, transaction snapshot, or an appropriate versioning mechanism. |

An **API design** needs to distinguish `Stream<T>` from `Supplier<Stream<T>>`:

~~~java
// Accepts a Stream: should normally be consumed only once.
static long countMatches(Stream<String> source) {
    return source.filter(s -> s.length() >= 3).count();
}

// Accepts a factory: can create two independent pipelines, if the factory is valid.
static String analyze(Supplier<Stream<String>> sourceFactory) {
    long count = sourceFactory.get().count();
    String first = sourceFactory.get()
            .sorted()
            .findFirst()
            .orElse("(empty)");
    return "count=" + count + ", first=" + first;
}
~~~

This snippet illustrates static methods inside a class that has imported `Stream` and `Supplier`. If `sourceFactory` creates streams that hold resources, the `analyze` implementation above **does not yet manage closing the source**; the design/implementation must be changed to close each stream with `try-with-resources` and clearly document ownership. Do not apply it verbatim to I/O resources.

## 16. Common mistakes and how to fix them

1. **Reusing the same Stream after a terminal operation:** create a new stream from the source; do not call `count()` or `toList()` again on the old object.
2. **Writing a supplier that returns a cached Stream:** `() -> stream` does not make a new Stream; use `() -> source.stream()` or `source::stream`.
3. **Creating a new Stream but using the same Iterator/cursor:** still does not replay data; create a new iterator/source or cache the data.
4. **Calling `factory.get()` once and reusing the variable:** you must call `get()` for each independent processing pass.
5. **Assuming `Supplier` guarantees identical results:** mutable/I/O sources can change between passes.
6. **Forgetting to close `Files.lines`:** use `try-with-resources` for every stream that holds I/O resources.
7. **Mistakenly thinking a terminal operation automatically closes the Stream:** consumption does not mean releasing resources under the `AutoCloseable` contract; close explicitly when appropriate.
8. **Reusing an empty Stream:** an empty Stream is also single-use; call a new `Stream.empty()` when needed.
9. **Using `Stream.generate` instead of a factory:** `generate` creates individual elements within one stream, rather than providing a pipeline for calling terminal operations multiple times.
10. **Calling `count()` to check data and then reusing the stream:** `count()` has already consumed the stream; use collection `isEmpty()` if available, or process in a single pass.
11. **Caching with `toList()` on very large/infinite data:** may run out of memory or fail to terminate.
12. **Mixing I/O logic with `Supplier.get()` while ignoring exceptions:** file sources have checked `IOException`; define how errors are wrapped/handled and how streams are closed.
13. **Assuming a new stream is always ordered:** unordered sources like `HashSet` have no defined encounter order.
14. **Modifying the source collection while a terminal operation is traversing it:** may violate non-interference and cause errors or different results.
15. **Running a pipeline with side effects multiple times and expecting the effect to happen only once:** each use of the factory runs a new processing pass, so side effects may repeat.
16. **Thinking a parallel stream solves a one-shot source:** parallel is only an execution strategy; it does not make an already consumed source re-readable.

## 17. Checklist before designing multi-pass processing

- Is the object I am holding a **`Collection` source** or **an already created `Stream`**?
- Which terminal operation has already used the current Stream? Am I attaching more operations onto an old Stream?
- If using `Supplier<Stream<T>>`, does each `get()` create **a genuinely new Stream**?
- Does the source behind the Stream allow re-traversal, or is it a single-use Iterator/reader/cursor?
- Can the data change between passes? Is a snapshot or identical result required?
- Does the Stream open resources? Who is responsible for closing each `get()` call?
- Is there a risk of `IOException`, `UncheckedIOException`, or resources being closed/deleted between passes?
- If only multiple metrics are needed in one pass, is an aggregating collector clearer/more economical?
- Will the factory be called concurrently from multiple threads or run in parallel on a mutable source?
- Is the data large or infinite, making materialization into a List unreasonable?

**Key takeaway:** **A Stream is a single-use pipeline; the source can be what creates multiple new Streams** if it supports repeated reads. Use `source.stream()` for simple independent queries, or `Supplier<Stream<T>>` to encapsulate creating new pipelines. A Supplier does not automatically reset an Iterator, does not make I/O replayable, does not cache a snapshot, and does not replace the responsibility of closing resources.