# Core Stream API Map in Java 8

> **Chapter:** JDK Compatibility  
> **Module:** JAVA_STREAM_API  
> **Scope:** Components of the Java Stream API **already available in Java 8**: Stream types, source creation, intermediate operations, terminal operations, primitive streams, Optional, Collector, Spliterator, and safety rules for parallel execution. This lesson also draws a clear boundary with APIs added **after Java 8** so you can write code compatible with legacy projects.

## Learning Objectives

After this lesson, you will be able to:

1. Locate the exact core packages, classes, and interfaces of the Stream API when the deployment target is **Java 8**.
2. Distinguish `Stream<T>` from `IntStream`, `LongStream`, and `DoubleStream`.
3. Choose Stream creation sources from `Collection`, arrays, numeric ranges, files, generators, and `Spliterator`.
4. Classify **intermediate** and **terminal** operations, and recognize lazy and short-circuiting operations.
5. Use `filter`, `map`, `flatMap`, `distinct`, `sorted`, `skip`, and `limit` with accurate semantics.
6. Use `reduce` and `collect` according to their contracts, including `Collectors.groupingBy` and multi-level collectors.
7. Work with `Optional`/`OptionalInt`/`OptionalLong`/`OptionalDouble` when results may be absent.
8. Evaluate encounter order, shared state, resources, and correctness when calling `parallelStream()`.
9. Recognize methods that **do not exist in Java 8** such as `Stream.toList()`, `takeWhile()`, and `mapMulti()`, and know appropriate alternatives.
10. Write, read, and verify a complete Java 8 program with a practical data processing pipeline.

**Version principle:** Examples labeled *Java 8* only use APIs and syntax already available in Java 8. Newer APIs are presented separately in the comparison table and must not be placed directly into code that needs to compile on JDK 8. These examples form the foundational knowledge for lazy pipelines, grouping, custom collectors, Spliterators, parallel processing, and Stream features introduced in subsequent JDKs.

---

## 1. Overview Map: Where Does Java 8 Place the Stream API?

The Stream API was introduced into Java with **Java 8**. The core types reside in `java.util.stream`; several supporting types reside in `java.util`, `java.util.function`, and packages providing data sources.

~~~text
Java 8 Stream API
│
├── java.util.stream
│   ├── BaseStream<T, S>
│   ├── Stream<T>
│   ├── IntStream / LongStream / DoubleStream
│   ├── Collectors
│   ├── Collector<T, A, R>
│   └── StreamSupport
│
├── java.util
│   ├── Optional<T>
│   ├── OptionalInt / OptionalLong / OptionalDouble
│   ├── Spliterator<T> / Spliterators
│   ├── Collection.stream() / parallelStream()
│   ├── Arrays.stream(...)
│   ├── Comparator
│   └── IntSummaryStatistics / LongSummaryStatistics /
│       DoubleSummaryStatistics
│
├── java.util.function
│   ├── Predicate<T> / Function<T,R>
│   ├── Consumer<T> / Supplier<T>
│   ├── UnaryOperator<T> / BinaryOperator<T>
│   ├── BiFunction<T,U,R> / BiConsumer<T,U>
│   └── IntPredicate / IntFunction / IntUnaryOperator / ...
│
└── Data Sources
    ├── java.nio.file.Files.lines(Path, Charset)
    ├── java.io.BufferedReader.lines()
    ├── java.util.regex.Pattern.splitAsStream(...)
    └── java.util.Random.ints() / longs() / doubles()
~~~

**This map describes roles**, rather than claiming every type belongs exclusively to the Stream module. For example, `java.util.function` contains *functional interfaces* used across many Java 8 APIs, not just Streams.

### 1.1. A Stream Is Not a Collection

| Criterion | `Collection<E>` | `Stream<T>` |
|---|---|---|
| Nature | Stores/manages elements | Describes a sequence of processing operations over a source |
| Re-traversal | Can be traversed again when the collection permits | A Stream cannot be reused after a terminal operation |
| Lazy operations | Not a primary characteristic of Collection | Most intermediate operations are lazy |
| Add/remove elements | Depends on collection type | Stream has no `add`/`remove` to mutate the source |
| Parallelism | Requires separate algorithms or corresponding APIs | Has `parallel()` and `parallelStream()` sources |
| Result | Usually the collection itself or an iterator | Terminal operation produces a number, Optional, List, Map, etc. |

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Arrays.asList(2, 4, 6);

Stream<Integer> stream = values.stream();
long count = stream.count(); // 3

// Do not continue using the same stream after a terminal operation:
// stream.findFirst(); // typically throws IllegalStateException

// A NEW Stream can be created from the same collection:
int sum = values.stream().mapToInt(Integer::intValue).sum();
System.out.println(sum); // 12
~~~

A Stream may reference a source that **does not store all data upfront**, such as an infinite generator, so do not assume every Stream has a `size()` or can be traversed again.

---

## 2. Core Types and the Meaning of Type Parameters

### 2.1. Stream<T> and BaseStream

`Stream<T>` represents elements of reference type `T`. It extends `BaseStream<T, Stream<T>>`, which defines common operations such as `iterator`, `spliterator`, `sequential`, `parallel`, `unordered`, `onClose`, and `close`.

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<String> names = Arrays.asList("An", "Binh").stream();

Stream<String> normalized = names
        .map(String::trim)
        .filter(s -> !s.isEmpty());

System.out.println(normalized.count()); // 2
~~~

In this example, `map`/`filter` return another Stream in the same pipeline. A pipeline is constructed and then consumed by the terminal operation `count`.

### 2.2. Three Primitive Streams

| Type | Element | Example Terminal Operation |
|---|---|---|
| `IntStream` | `int` | `sum()`, `average()`, `summaryStatistics()` |
| `LongStream` | `long` | `sum()`, `min()`, `max()` |
| `DoubleStream` | `double` | `sum()`, `average()`, `summaryStatistics()` |

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

int sum = IntStream.range(1, 5).sum();         // 10
long max = LongStream.of(3L, 8L, 5L)
        .max().getAsLong();                    // 8
double average = DoubleStream.of(2.0, 4.0, 9.0)
        .average().getAsDouble();              // 5.0

System.out.println(sum);
System.out.println(max);
System.out.println(average);
~~~

`IntStream` is not `Stream<Integer>`. Primitive Streams avoid creating boxed objects for each element in many numeric operations.

### 2.3. Optional Types Accompanying Terminal Operations

| Possibly Absent Result | Wrapper Type |
|---|---|
| Object `T` | `Optional<T>` |
| `int` | `OptionalInt` |
| `long` | `OptionalLong` |
| `double` | `OptionalDouble` |

For example, `findFirst()` on an empty source returns `Optional.empty()`; `IntStream.average()` on an empty source returns `OptionalDouble.empty()`. Do not call `get()`/`getAsInt()` when data may be absent without a clear error policy.

---

## 3. Creating Stream Sources from Collections and Arrays

### 3.1. Collection.stream() and parallelStream()

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Arrays.asList("An", "Binh", "Chi");

Stream<String> sequential = names.stream();
Stream<String> parallel = names.parallelStream();

System.out.println(sequential.count()); // 3
System.out.println(parallel.count());   // 3
~~~

Both methods have existed since Java 8. `parallelStream` only requests that the pipeline be capable of parallel processing; it does not guarantee faster execution and does not make lambdas with side effects thread-safe.

**`Map` does not have a `map.stream()` method in Java 8.** To process each entry, start from a view of the Map:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> stock = new HashMap<String, Integer>();
stock.put("PEN", 5);
stock.put("BOOK", 3);

int total = stock.entrySet().stream()
        .mapToInt(entry -> entry.getValue())
        .sum();

System.out.println(total); // 8
~~~

### 3.2. Arrays.stream(...)

~~~java
import java.util.Arrays;

String[] words = {"java", "stream", "api"};
int[] numbers = {3, 5, 7};

long wordsCount = Arrays.stream(words).count();
int numericTotal = Arrays.stream(numbers).sum();

System.out.println(wordsCount);  // 3
System.out.println(numericTotal); // 15
~~~

`Arrays.stream(int[])` returns `IntStream`, whereas `Arrays.stream(String[])` returns `Stream<String>`. Array overloads also support selecting a slice via start/end indices.

~~~java
int[] data = {10, 20, 30, 40};
int middle = Arrays.stream(data, 1, 3).sum(); // 20 + 30
System.out.println(middle); // 50
~~~

The end index `toIndex` is **exclusive**, following the standard convention used for ranges in Java.

### 3.3. Stream.of() and Stream.empty()

~~~java
import java.util.stream.Stream;

long count = Stream.of("A", "B", "C").count(); // 3
long emptyCount = Stream.<String>empty().count(); // 0

System.out.println(count);
System.out.println(emptyCount);
~~~

**Primitive array warning:**

~~~java
int[] values = {1, 2, 3};

// Stream.of(values) receives 1 object of type int[]:
long oneArray = Stream.of(values).count(); // 1

// Arrays.stream(values) emits 3 int values:
long threeNumbers = java.util.Arrays.stream(values).count(); // 3

System.out.println(oneArray + " / " + threeNumbers); // 1 / 3
~~~

When you want to operate on individual integers, use `Arrays.stream(int[])` or `IntStream.of(int...)`.

### 3.4. Stream.Builder and Stream.concat

~~~java
import java.util.stream.Stream;

Stream.Builder<String> builder = Stream.builder();
builder.add("A");
builder.add("B");

Stream<String> built = builder.build();

Stream<String> joined = Stream.concat(
        built,
        Stream.of("C")
);

System.out.println(joined.count()); // 3
~~~

Both `Stream.builder()` and `Stream.concat(...)` have existed since Java 8. The Builder should only be used according to its contract: add elements **before** `build()`, and do not reuse the builder afterward. The two input Streams to `concat` must also not be consumed by a terminal operation before creating/consuming the concatenated result.

---

## 4. Creating Numeric Sequences and Data Generators

### 4.1. IntStream.range and rangeClosed

~~~java
import java.util.stream.IntStream;

int leftClosedRightOpen = IntStream.range(1, 5).sum();
// 1 + 2 + 3 + 4 = 10

int bothClosed = IntStream.rangeClosed(1, 5).sum();
// 1 + 2 + 3 + 4 + 5 = 15

System.out.println(leftClosedRightOpen); // 10
System.out.println(bothClosed);           // 15
~~~

- `range(start, endExclusive)` excludes `endExclusive`.
- `rangeClosed(start, endInclusive)` includes the end value.

`LongStream` also has `range` and `rangeClosed` in Java 8. `DoubleStream` does not have an equivalent `range` factory.

### 4.2. Stream.iterate(seed, next) — Java 8

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> powers = Stream.iterate(
        1,
        n -> n * 2
).limit(5).collect(Collectors.toList());

System.out.println(powers); // [1, 2, 4, 8, 16]
~~~

The **two-parameter** overload `Stream.iterate(seed, UnaryOperator)` is present in Java 8 and can create an **infinite source**. An appropriate stopping operation such as `limit` or a short-circuiting terminal operation is needed if you want it to terminate.

**Do not confuse** this with the three-parameter overload `Stream.iterate(seed, hasNext, next)`: it appeared **in Java 9** and cannot be used when compiling Java 8 code.

### 4.3. Stream.generate(Supplier)

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> repeated = Stream.generate(() -> "OK")
        .limit(3)
        .collect(Collectors.toList());

System.out.println(repeated); // [OK, OK, OK]
~~~

`generate` pulls elements from a `Supplier` and typically produces an unbounded source. Do not rely on supplier call order or shared counters for business logic during parallel processing.

### 4.4. Random Number Sources

~~~java
import java.util.Random;

Random random = new Random(123L);

long count = random.ints(20, 0, 100)
        .count();

System.out.println(count); // 20
~~~

`Random.ints/longs/doubles` were added in Java 8. This example generates 20 integers from 0 (inclusive) to 100 (exclusive). A fixed seed helps reproduce sequences in appropriate contexts, though controlling consumption order of random sources in parallel processing requires separate consideration if strict reproducibility is required.

---

## 5. I/O Sources: Files.lines and BufferedReader.lines

A Stream can read data lazily from a text file. This differs from loading the entire file into a `List` before processing.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

Path path = Paths.get("orders.txt");

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmpty = lines
            .filter(line -> !line.trim().isEmpty())
            .count();

    System.out.println(nonEmpty);
} catch (IOException ex) {
    System.err.println("Cannot open file: " + ex.getMessage());
}
~~~

The example uses `Paths.get(...)` because that is the **Java 8**-compatible way to create a `Path`. `Path.of(...)` only exists since Java 11.

**Important:**

- `Files.lines(...)` can hold open resources; use `try-with-resources` to close the Stream.
- I/O exceptions occurring during reading/iteration can be wrapped into `UncheckedIOException`, not just `IOException` when opening the file.
- Closing a Stream does not mean every Stream necessarily holds resources; most Streams backed by collections do not need closing.
- Do not run multiple terminal operations on the same file-reading Stream.

`BufferedReader.lines()` is also available in Java 8:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

try (BufferedReader reader = Files.newBufferedReader(
        Paths.get("orders.txt"), StandardCharsets.UTF_8)) {
    long lineCount = reader.lines().count();
    System.out.println(lineCount);
} catch (IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

Here, closing `BufferedReader` with `try-with-resources` releases the reading source. Do not assume `Stream.count()` or `collect` automatically closes the file source upon completion.

### 5.1. Pattern.splitAsStream()

~~~java
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

List<String> tokens = Pattern.compile(",")
        .splitAsStream("A,B,C")
        .collect(Collectors.toList());

System.out.println(tokens); // [A, B, C]
~~~

`Pattern.splitAsStream` is another Java 8 API for creating a Stream from string data using a regular expression.

---

## 6. Intermediate Operations Map — Stateless

Intermediate operations generally return a new Stream in the same pipeline. They are **lazy**: they do not consume the source immediately when declared.

| Java 8 Method | Role | Typical Return Type |
|---|---|---|
| `filter(Predicate<T>)` | Keeps elements matching the condition | `Stream<T>` |
| `map(Function<T,R>)` | Transforms each element | `Stream<R>` |
| `mapToInt(ToIntFunction<T>)` | Converts object to `int` | `IntStream` |
| `mapToLong(ToLongFunction<T>)` | Converts object to `long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<T>)` | Converts object to `double` | `DoubleStream` |
| `flatMap(Function<T,Stream<R>>)` | Each element emits 0..n elements, flattens | `Stream<R>` |
| `flatMapToInt` / `flatMapToLong` / `flatMapToDouble` | Flattens to a primitive stream | Primitive Stream |
| `peek(Consumer<T>)` | Runs an observing action when an element is consumed | `Stream<T>` |

### 6.1. filter and map

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList(
        " An ", "", " Binh ", "  ", " Chi "
);

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [An, Binh, Chi]
~~~

`String.trim()` exists in Java 8. `String.strip()` and `String.isBlank()` are **Java 11** APIs, so do not substitute them into examples that must run on Java 8 without upgrading the runtime/API.

### 6.2. map vs. flatMap

Given a list containing multiple lists:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<List<String>> groups = Arrays.asList(
        Arrays.asList("A", "B"),
        Arrays.asList("C")
);

// map creates a Stream<Stream<String>> (sub-streams):
Stream<Stream<String>> nested = groups.stream()
        .map(List::stream);

// flatMap flattens into Stream<String>:
List<String> flat = groups.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());

System.out.println(flat); // [A, B, C]

// nested is not consumed in this illustration.
nested.close();
~~~

`flatMap` takes a mapper from each element to a sub-stream, then concatenates the elements of those sub-streams into the pipeline. By contract, the sub-streams are closed when no longer needed.

`mapMulti` does not exist in Java 8; when encountering code using `mapMulti` in newer documentation, the familiar replacement for Java 8 is `flatMap`, depending on the element-emission problem.

### 6.3. peek Is Not for Core Business Logic

~~~java
import java.util.Arrays;

long count = Arrays.asList("A", "B", "C").stream()
        .peek(System.out::println)
        .filter(s -> !s.isEmpty())
        .count();
~~~

`peek` is suitable for certain observation/diagnostic situations, but you should **not** place mandatory data writes or business-state mutations in it. Streams may optimize the pipeline, short-circuiting operations may cause only some elements to be processed, and the order of side effects in parallel streams is not part of the result contract.

---

## 7. Intermediate Operations Map — Stateful and Slicing

| Java 8 Method | Semantics | Notes |
|---|---|---|
| `distinct()` | Removes duplicate elements by `equals` | Stateful, can be memory-intensive |
| `sorted()` | Sorts by natural order | Stateful |
| `sorted(Comparator)` | Sorts by comparator | Used with `Stream<T>` |
| `limit(long n)` | Takes at most the first n elements | Short-circuiting, stateful |
| `skip(long n)` | Skips the first n elements | Stateful, generally non-short-circuiting |
| `unordered()` | Drops the encounter order constraint | Does not actively shuffle |
| `sequential()` / `parallel()` | Switches execution mode | Not a per-element transformation |

### 7.1. distinct, sorted, skip, limit

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(4, 2, 4, 1, 3);

List<Integer> result = source.stream()
        .distinct()                 // [4, 2, 1, 3]
        .sorted()                   // [1, 2, 3, 4]
        .skip(1)                   // [2, 3, 4]
        .limit(2)                  // [2, 3]
        .collect(Collectors.toList());

System.out.println(result); // [2, 3]
~~~

`limit` and `skip` accept **non-negative** counts; a negative value throws `IllegalArgumentException`. On ordered sources, they operate on the **prefix** in encounter order.

### 7.2. Swapping Operations Can Change the Problem

~~~java
import java.util.Arrays;
import java.util.Comparator;

List<Integer> nums = Arrays.asList(2, 9, 4, 7);

System.out.println(nums.stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .collect(java.util.stream.Collectors.toList()));
// [9, 7]

System.out.println(nums.stream()
        .limit(2)
        .sorted(Comparator.reverseOrder())
        .collect(java.util.stream.Collectors.toList()));
// [9, 2]
~~~

The two pipelines are **not equivalent**. The first pipeline takes the global top 2; the second only sorts the first two elements of the source.

### 7.3. Operations Not Yet Available in Java 8

- `takeWhile(Predicate)`: since **Java 9**.
- `dropWhile(Predicate)`: since **Java 9**.
- `mapMulti(...)`: since **Java 16**.
- `Stream.gather(...)` and standard Gatherers: appeared in newer JDKs, not available in Java 8.

If the problem genuinely requires **taking/dropping a prefix up to a boundary**, do not simply replace `takeWhile`/`dropWhile` with `filter`: `filter` inspects all elements and **does not** preserve the first-boundary semantics. For Java 8 code, you can use an explicit sequential loop or a contract-compliant custom `Spliterator` when you need to emit a Stream.

---

## 8. Terminal Operations Map

A terminal operation triggers source processing and completes the pipeline.

| Group | Java 8 Method | Result |
|---|---|---|
| Iteration | `forEach`, `forEachOrdered` | `void` |
| Counting | `count` | `long` |
| Finding | `findFirst`, `findAny` | `Optional<T>` |
| Matching | `anyMatch`, `allMatch`, `noneMatch` | `boolean` |
| Min/max | `min(Comparator)`, `max(Comparator)` | `Optional<T>` |
| Array | `toArray()`, `toArray(generator)` | Array |
| Reduction | `reduce` overloads | `Optional<T>` or value |
| Collection | `collect(Collector)` or `collect(supplier,accumulator,combiner)` | `R` |
| Primitive | `sum`, `average`, `summaryStatistics` | Number or statistics type |

**`Stream<T>` does not have a general `sum()` method.** To sum numeric fields in `Stream<Order>`, convert to a primitive stream via `mapToInt`/`mapToLong` or use `reduce`/`Collectors.summing...`.

### 8.1. findFirst, findAny, and Match

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> values = Arrays.asList(4, 7, 8, 10);

Optional<Integer> firstEven = values.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

boolean hasNegative = values.stream().anyMatch(n -> n < 0);
boolean allPositive = values.stream().allMatch(n -> n > 0);
boolean noneZero = values.stream().noneMatch(n -> n == 0);

System.out.println(firstEven.orElse(-1)); // 4
System.out.println(hasNegative);          // false
System.out.println(allPositive);          // true
System.out.println(noneZero);             // true
~~~

For a Stream with encounter order, `findFirst` picks the first element in that order. `findAny` may pick **any valid element** and is appropriate when position does not matter, especially in parallel processing.

### 8.2. Short-Circuiting Terminals

`findFirst`, `findAny`, `anyMatch`, `allMatch`, and `noneMatch` can stop once the result is determined. That does not mean upstream lambdas are invoked a fixed number of times, especially when the pipeline runs in parallel.

On an empty source:

~~~java
import java.util.stream.Stream;

boolean any = Stream.<Integer>empty().anyMatch(n -> n > 0);
boolean all = Stream.<Integer>empty().allMatch(n -> n > 0);
boolean none = Stream.<Integer>empty().noneMatch(n -> n > 0);

System.out.println(any);  // false
System.out.println(all);  // true
System.out.println(none); // true
~~~

This is the logical semantics of match operations on an empty set; it is not a bug.

### 8.3. toArray

~~~java
import java.util.Arrays;

String[] result = Arrays.asList("A", "B", "C")
        .stream()
        .filter(s -> !"B".equals(s))
        .toArray(String[]::new);

System.out.println(Arrays.toString(result)); // [A, C]
~~~

`toArray(String[]::new)` has existed since Java 8. Calling no-arg `toArray()` on `Stream<T>` yields a result type of `Object[]`.

---

## 9. Primitive Streams: Type Conversion and Aggregation

### 9.1. mapToInt, mapToLong, mapToDouble

~~~java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("java", "api", "stream");

int totalCharacters = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(totalCharacters); // 13
~~~

`mapToInt` does not create a `Stream<Integer>`; it returns an `IntStream`, which directly supports `sum()`.

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> amounts = Arrays.asList(
        1500000000, 1500000000
);

long total = amounts.stream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 3000000000
~~~

Use `mapToLong` **before summing** to avoid `int` overflow. However, a `long` sum can still overflow if the data domain is large enough; in that case consider `BigInteger`.

### 9.2. boxed and mapToObj

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.rangeClosed(1, 3)
        .boxed()
        .collect(Collectors.toList());

List<String> labels = IntStream.range(1, 4)
        .mapToObj(n -> "ID-" + n)
        .collect(Collectors.toList());

System.out.println(ids);    // [1, 2, 3]
System.out.println(labels); // [ID-1, ID-2, ID-3]
~~~

`boxed()` converts a primitive stream to a wrapper object Stream. `mapToObj` transforms a primitive into an object according to a mapper function.

### 9.3. average and summaryStatistics

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;

int[] scores = {10, 20, 30};

OptionalDouble average = Arrays.stream(scores).average();
IntSummaryStatistics stats = Arrays.stream(scores)
        .summaryStatistics();

System.out.println(average.orElse(0.0)); // 20.0
System.out.println(stats.getCount());    // 3
System.out.println(stats.getSum());      // 60
System.out.println(stats.getMin());      // 10
System.out.println(stats.getMax());      // 30
~~~

On an empty source, `average()` returns `OptionalDouble.empty()`. The min/max fields of `IntSummaryStatistics` when there are no elements are **sentinel values** and must not be interpreted as actual minimum/maximum scores; always check `getCount()` first.

### 9.4. When Precision Is Needed

`DoubleStream.sum()`/`average()` perform floating-point arithmetic; parallel combining can alter calculation order and rounding error. For currency requiring exactness, integer cents or `BigDecimal` is typically used instead of defaulting to `double`.

---

## 10. Optional in Java 8: Receiving and Handling Absent Results

`Optional<T>` has existed since Java 8 and appears in many terminal operations.

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<String> firstLong = Arrays.asList(
        "An", "Binh", "Chi"
).stream()
 .filter(name -> name.length() > 10)
 .findFirst();

String display = firstLong.orElse("Not found");

System.out.println(display); // Not found
~~~

`Optional` operations available in Java 8:

| API | Role |
|---|---|
| `Optional.of(value)` | Wraps a non-null value |
| `Optional.ofNullable(value)` | Present if non-null |
| `Optional.empty()` | No value |
| `isPresent()` | Is a value present? |
| `get()` | Gets the value; throws if empty |
| `ifPresent(Consumer)` | Executes when a value is present |
| `orElse(default)` | Default value |
| `orElseGet(Supplier)` | Lazily creates a default value when needed |
| `orElseThrow(Supplier)` | Throws the supplied exception when empty |
| `filter(Predicate)` | Keeps the Optional if the predicate matches |
| `map(Function)` / `flatMap(Function)` | Transforms the Optional |

Java 8 API example:

~~~java
import java.util.Optional;

Optional<Integer> maybeScore = Optional.of(90);

int score = maybeScore
        .filter(n -> n >= 0)
        .orElseThrow(() ->
                new IllegalStateException("Invalid score")
        );

System.out.println(score); // 90
~~~

**Version notes:**

- `optional.isEmpty()` is not in Java 8 (since Java 11).
- `optional.stream()` is not in Java 8 (since Java 9).
- `optional.ifPresentOrElse(...)` is not in Java 8 (since Java 9).
- No-argument `optional.orElseThrow()` is not in Java 8 (since Java 10); use the overload accepting a Supplier as shown above.
- `OptionalInt` has `getAsInt`, `orElse`, and specialized APIs; do not confuse it with `Optional<Integer>`.

### 10.1. Flattening Optional in Java 8

A modern pipeline often uses `Optional.stream()` to drop empty Optionals. In Java 8, the equivalent can be done with `flatMap`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Optional<String>> options = Arrays.asList(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("C")
);

List<String> present = options.stream()
        .flatMap(o -> o.isPresent()
                ? Stream.of(o.get())
                : Stream.<String>empty())
        .collect(Collectors.toList());

System.out.println(present); // [A, C]
~~~

This is the **Java 8-compatible way**. Do not try to use the `Optional::stream` method reference because that method does not yet exist in this version.

---

## 11. reduce in Java 8: Three Overloads and Algebraic Contracts

### 11.1. Without Identity

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> max = Arrays.asList(2, 9, 5)
        .stream()
        .reduce(Integer::max);

System.out.println(max.orElse(-1)); // 9
~~~

`reduce(BinaryOperator<T>)` returns `Optional<T>` to represent an empty source without inventing an identity value for the problem.

### 11.2. With Identity

~~~java
import java.util.Arrays;

int total = Arrays.asList(2, 9, 5)
        .stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 16
~~~

Important conditions:

- Identity `0` is neutral for addition.
- The operator is **associative**: `(a+b)+c = a+(b+c)` under the arithmetic rules in effect.
- The lambda must be **stateless** and **non-interfering**.

A wrong identity such as `reduce(10, Integer::sum)` can cause a parallel result to add `10` multiple times, because each partition may start from the identity.

### 11.3. Three-Parameter Form: U Differs from T

~~~java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("java", "api");

long lengthSum = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(lengthSum); // 7
~~~

Three components:

1. `identity` of type `U` (here `Long`).
2. `accumulator(U,T) -> U`.
3. `combiner(U,U) -> U`.

For this overload, the combiner must also be compatible with the accumulator. An important verification expression:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

If the accumulator sums lengths while the combiner takes `max`, the reduction may succeed sequentially and then fail when split into two branches. Do not use a shared mutable `ArrayList` as the identity and mutate it inside the reducer: use `collect` to create mutable containers.

### 11.4. Floating-Point Addition and Changing Grouping Order

`double` addition is not strictly associative due to IEEE 754 rounding:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Therefore, parallel `reduce(0.0, Double::sum)` can differ from a sequential grouping on error-sensitive data. When exact financial results are required, choose the appropriate type and aggregation rules before enabling parallel execution.

---

## 12. collect: Results as List, Set, Map, or Custom Structures

Java 8 has two groups of `collect` APIs:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector)

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
)
~~~

In practice, the overload taking a `Collector` is very common because `Collectors` provides many built-in collectors.

### 12.1. Collectors.toList, toSet, toCollection

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> list = Arrays.asList("A", "B", "A")
        .stream()
        .collect(Collectors.toList());

Set<String> set = Arrays.asList("A", "B", "A")
        .stream()
        .collect(Collectors.toSet());

ArrayList<String> explicitArrayList = Arrays.asList("A", "B")
        .stream()
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(list); // [A, B, A]
System.out.println(set.size()); // 2
System.out.println(explicitArrayList); // [A, B]
~~~

**Java 8's `Collectors.toList()` makes no guarantees on the implementation type, mutability, thread-safety, or serializability of the returned List.** If a specific `ArrayList` is needed, use `toCollection(ArrayList::new)`.

`Collectors.toSet()` does not guarantee encounter order or Set type. If you want a specific `LinkedHashSet`:

~~~java
import java.util.LinkedHashSet;

LinkedHashSet<String> orderedUnique = Arrays
        .asList("B", "A", "B")
        .stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(orderedUnique); // [B, A]
~~~

### 12.2. Collectors.joining

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

String csv = Arrays.asList("A", "B", "C")
        .stream()
        .collect(Collectors.joining(","));

System.out.println(csv); // A,B,C
~~~

`joining()`, `joining(delimiter)`, and `joining(delimiter, prefix, suffix)` are all Java 8 APIs. This is generally a better choice than repeated String concatenation in a reducer when the number of elements is large.

### 12.3. Three-Parameter collect for Mutable Containers

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<String> result = Arrays.asList("A", "B", "C")
        .parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(result); // [A, B, C]
~~~

`supplier` creates a new container for each processing partition when needed; `accumulator` receives one element; `combiner` merges two containers. Do not use a shared List created outside the pipeline in place of a contract-compliant supplier.

---

## 13. Map of Built-in Collectors in Java 8

| Group | Java 8 API | Result |
|---|---|---|
| Collections | `toList`, `toSet`, `toCollection` | List/Set/Collection |
| Strings | `joining` | String |
| Maps | `toMap`, `toConcurrentMap` | Map/ConcurrentMap |
| Grouping | `groupingBy`, `groupingByConcurrent` | Map<K, ...> |
| Two-way split | `partitioningBy` | Map<Boolean, ...> |
| Downstream | `mapping`, `collectingAndThen` | Transformed/finished result |
| Counting | `counting` | Long |
| Numeric | `summingInt/Long/Double` | Sum |
| Averaging | `averagingInt/Long/Double` | Double |
| Statistics | `summarizingInt/Long/Double` | SummaryStatistics |
| Extrema | `minBy`, `maxBy` | Optional<T> |
| Reduction | `reducing` overloads | Value or Optional |

### 13.1. groupingBy and counting

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(
        "java", "stream", "java", "api"
);

Map<String, Long> frequency = words.stream()
        .collect(Collectors.groupingBy(
                word -> word,
                Collectors.counting()
        ));

System.out.println(frequency.get("java")); // 2
System.out.println(frequency.get("api"));  // 1
~~~

`groupingBy(classifier)` defaults to collecting a list of values for each key. Downstream `counting()` replaces the List with a count.

### 13.2. groupingBy + mapping

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

class Sale {
    final String category;
    final long cents;

    Sale(String category, long cents) {
        this.category = category;
        this.cents = cents;
    }
}

List<Sale> sales = Arrays.asList(
        new Sale("BOOK", 100),
        new Sale("PEN", 40),
        new Sale("BOOK", 200)
);

Map<String, List<Long>> centsByCategory =
        sales.stream().collect(Collectors.groupingBy(
                sale -> sale.category,
                Collectors.mapping(
                        sale -> sale.cents,
                        Collectors.toList()
                )
        ));

System.out.println(centsByCategory.get("BOOK")); // [100, 200]
~~~

`mapping` has existed since **Java 8**. Do not confuse it with `Collectors.flatMapping` (Java 9) or `Collectors.filtering` (Java 9), even though all three are downstream adapters.

### 13.3. toMap and the Merge Function

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("a", "bb", "ccc");

Map<Integer, String> byLength = values.stream()
        .collect(Collectors.toMap(
                String::length,
                Function.identity()
        ));

System.out.println(byLength.get(2)); // bb
~~~

If two elements produce the same key, the overload `toMap(keyMapper, valueMapper)` throws `IllegalStateException`. You must choose an explicit policy when keys may collide:

~~~java
List<String> duplicates = Arrays.asList(
        "an", "bo", "chi"
);

Map<Integer, String> firstPerLength = duplicates.stream()
        .collect(Collectors.toMap(
                String::length,
                Function.identity(),
                (first, later) -> first
        ));

System.out.println(firstPerLength.get(2)); // an
~~~

In an ordered Stream, the policy of choosing the first record matches the requirement "first in encounter order" when using a standard collector. If business logic wants the **latest** record, do not treat "first/last in source" as a timestamp unless there is a data ordering guarantee; merge by version/time with an appropriate tie-breaker.

### 13.4. collectingAndThen Has Existed Since Java 8

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

List<String> readOnly = Arrays.asList("A", "B")
        .stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> Collections.unmodifiableList(
                        new ArrayList<String>(list)
                )
        ));

// readOnly.add("C"); // UnsupportedOperationException.
~~~

`collectingAndThen` is not a Java 9+ feature: it has been available since Java 8. We use `Collections.unmodifiableList(new ArrayList<>(list))` to create a structurally read-only copy in Java 8. `List.copyOf` is a **Java 10** API and cannot be used when compiling for Java 8.

### 13.5. partitioningBy

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> partitioned =
        Arrays.asList(1, 2, 3, 4)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0
                ));

System.out.println(partitioned.get(true));  // [2, 4]
System.out.println(partitioned.get(false)); // [1, 3]
~~~

`partitioningBy` creates two Boolean key branches. It is a predicate-based collector, unlike grouping by an arbitrary key.

---

## 14. Custom Collectors: Also Java 8

`Collector<T, A, R>` defines five components:

1. `supplier`: creates the accumulation state `A`.
2. `accumulator`: folds element `T` into `A`.
3. `combiner`: merges two states `A`.
4. `finisher`: transforms state `A` into result `R`.
5. `characteristics`: describes the collector's guarantees.

A collector that counts elements using a mutable container:

~~~java
import java.util.Arrays;
import java.util.stream.Collector;

Collector<String, long[], Long> countCollector =
        Collector.of(
                () -> new long[] {0L},
                (acc, value) -> acc[0]++,
                (left, right) -> {
                    left[0] += right[0];
                    return left;
                },
                acc -> acc[0]
        );

long count = Arrays.asList("A", "B", "C")
        .parallelStream()
        .collect(countCollector);

System.out.println(count); // 3
~~~

In this example:

- Each `supplier` creates a **new array**.
- `accumulator` only mutates the state of its assigned container.
- `combiner` merges two counters via addition.
- `finisher` returns the `Long` count.
- `CONCURRENT` is not declared because `long[]` is not thread-safe when mutated by multiple threads simultaneously.

When the business requirement is only counting elements, `count()` or `Collectors.counting()` is simpler; the goal of this example is to show collector structure.

### 14.1. Three Collector Characteristics

| Characteristic | Meaning |
|---|---|
| `CONCURRENT` | Allows threads to accumulate concurrently into the same container under the appropriate contract conditions |
| `UNORDERED` | The collector does not require preserving encounter order |
| `IDENTITY_FINISH` | The finisher step can be treated as identity and may be skipped |

These names belong to `Collector.Characteristics`, **distinct** from `Spliterator.ORDERED/SORTED/SIZED` flags. Do not confuse collector characteristics with source characteristics.

A collector must preserve `combiner` identity/associativity and compatibility with `accumulator`. A collector that works sequentially is **not necessarily correct when run in parallel** if the combiner is written incorrectly.

---

## 15. Spliterator and StreamSupport: Custom Source Foundation Since Java 8

`Spliterator<T>` has the following main methods:

| Method | Role |
|---|---|
| `tryAdvance(Consumer)` | Emits at most one element |
| `forEachRemaining(Consumer)` | Emits remaining elements |
| `trySplit()` | Splits off a portion of remaining data |
| `estimateSize()` | Estimates remaining element count |
| `characteristics()` | Returns characteristic bitmask |
| `getComparator()` | Comparator if source has `SORTED` |

Some flags already available in Java 8:

- `ORDERED`: the source has an encounter order.
- `DISTINCT`: no duplicate elements by `equals`.
- `SORTED`: the source is sorted by natural order or a comparator; implies `ORDERED`.
- `NONNULL`: the source does not emit `null`.
- `SIZED` and `SUBSIZED`: guarantees regarding size.
- `IMMUTABLE` and `CONCURRENT`: structural/mutation characteristics of the source.

### 15.1. Obtaining a Spliterator from a Collection

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

List<Integer> values = Arrays.asList(3, 1, 2);
Spliterator<Integer> source = values.spliterator();

System.out.println(
        source.hasCharacteristics(Spliterator.ORDERED)
); // true, List has an encounter order.

System.out.println(source.estimateSize()); // 3
~~~

If writing a custom `Spliterator` for a parallel Stream and declaring `ORDERED`, `trySplit()` must return a **prefix** of the remaining elements. Falsely declaring `DISTINCT` or `SORTED` can cause Stream optimizations to trust inaccurate data assumptions.

### 15.2. Creating a Stream from a Spliterator

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

List<Integer> values = Arrays.asList(3, 1, 2);
Spliterator<Integer> source = values.spliterator();

int sum = StreamSupport.stream(source, false)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 6
~~~

The parameter `false` requests a sequential pipeline; `true` requests parallel. `StreamSupport.stream(...)` exists in Java 8, so there is no need to build a new `Stream` implementation to work with custom sources.

### 15.3. Do Not Reuse a Consumed Spliterator

A Spliterator typically holds traversal position state. Once a source has been consumed to compute a sum, do not reuse that same Spliterator to read data from the beginning. Create a new Spliterator or create a new Stream from a re-traversable collection.

---

## 16. Built-in Functional Interfaces in Java 8

Lambdas and method references are the foundation that make the Stream API concise.

| Interface | Abstract Method | Example |
|---|---|---|
| `Predicate<T>` | `boolean test(T)` | `n -> n > 0` |
| `Function<T,R>` | `R apply(T)` | `String::length` |
| `Consumer<T>` | `void accept(T)` | `System.out::println` |
| `Supplier<T>` | `T get()` | `ArrayList::new` |
| `UnaryOperator<T>` | `T apply(T)` | `n -> n + 1` |
| `BinaryOperator<T>` | `T apply(T,T)` | `Integer::sum` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | `(sum, item) -> ...` |
| `BiConsumer<T,U>` | `void accept(T,U)` | `List::add` in a collector |
| `ToIntFunction<T>` | `int applyAsInt(T)` | `String::length` |
| `IntPredicate` | `boolean test(int)` | `n -> n % 2 == 0` |
| `IntUnaryOperator` | `int applyAsInt(int)` | `n -> n * n` |

### 16.1. Lambdas and Method References

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("a", "bb", "ccc");

List<Integer> lengths1 = names.stream()
        .map(name -> name.length())
        .collect(Collectors.toList());

List<Integer> lengths2 = names.stream()
        .map(String::length)
        .collect(Collectors.toList());

System.out.println(lengths1.equals(lengths2)); // true
~~~

`String::length` is a method reference that can replace the corresponding lambda.

### 16.2. Effectively Final and Side Effects

~~~java
int minLength = 2; // Not reassigned after initialization.

long count = Arrays.asList("a", "bb", "ccc")
        .stream()
        .filter(s -> s.length() >= minLength)
        .count();

System.out.println(count); // 2
~~~

Local variables captured by a lambda must be `final` or **effectively final**. However, this **does not mean the captured object is immutable**:

~~~java
import java.util.ArrayList;
import java.util.List;

// Avoid shared side effects in a parallel stream:
List<String> shared = new ArrayList<String>();

// Arrays.asList("A", "B", "C")
//         .parallelStream()
//         .forEach(shared::add);
~~~

`ArrayList` is not thread-safe when multiple threads call `add` concurrently. Use `collect(Collectors.toList())` or an appropriate collector instead of mutating a shared List in `forEach`.

---

## 17. Lazy Evaluation and a Stream's Lifecycle

### 17.1. Intermediate Operations Do Not Traverse the Source Immediately

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> pipeline = Arrays.asList(1, 2, 3)
        .stream()
        .filter(n -> {
            System.out.println("test " + n);
            return n > 1;
        });

System.out.println("Pipeline created");
// Elements are not traversed merely by calling filter().

long count = pipeline.count(); // terminal triggers the pipeline
System.out.println(count); // 2
~~~

The log output of this example demonstrates laziness when the terminal operation is called. However, do not turn logs/side effects into required outcomes: certain optimizations are permitted to elide lambda calls if doing so does not change the **specified result**.

### 17.2. Short-Circuiting

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> found = Arrays.asList(2, 4, 7, 8)
        .stream()
        .filter(n -> n % 2 != 0)
        .findFirst();

System.out.println(found.orElse(-1)); // 7
~~~

`findFirst` can stop once the first matching element is determined. On an ordered parallel stream, guaranteeing "first" can incur additional coordination compared to `findAny`.

### 17.3. A Stream Is Not Reusable After a Terminal Operation

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> once = Arrays.asList(1, 2, 3).stream();

System.out.println(once.count()); // 3

// Do not subsequently call once.reduce(...) or once.findAny().
// Create a new Stream if you want to evaluate again.
~~~

A Stream can be consumed or closed only once. For re-traversable sources like List, call `list.stream()` again; for file/I/O sources, manage reopening the source.

---

## 18. Encounter Order, Parallelism, Unordered, and Correctness

### 18.1. Both Sequential and Parallel Modes Have Existed Since Java 8

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> nums = Arrays.asList(1, 2, 3, 4);

long sequential = nums.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallel = nums.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

Enabling parallelism changes the **execution plan**, without automatically inventing a different business algorithm. Lambdas must obey stateless/non-interfering requirements, and reduction operations must have valid identity/associativity.

### 18.2. forEach vs. forEachOrdered

~~~java
import java.util.Arrays;

Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .forEach(System.out::println);
// Print order is not guaranteed.

Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .forEachOrdered(System.out::println);
// In encounter order: A, B, C, D.
~~~

`forEachOrdered` guarantees applying the action in encounter order for ordered Streams, but may reduce parallel speedup.

### 18.3. unordered() Is Not shuffle()

~~~java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

Set<Integer> unique = Arrays.asList(2, 1, 2, 3)
        .parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

System.out.println(unique.size()); // 3
~~~

`unordered` drops the encounter order constraint; it **does not promise to reorder data**. Use it only when ordering **does not matter** under the problem contract.

### 18.4. reduce and Collectors Must Combine Correctly

With reduce:

~~~java
// Valid identity and valid combining operation:
int sum = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);
~~~

With a mutable collector:

~~~java
// Each supplier creates a new container, combiner merges results:
List<Integer> result = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .collect(
                java.util.ArrayList::new,
                List::add,
                List::addAll
        );
~~~

The two forms solve **two different kinds of problems**. Do not try to use `reduce` with a shared mutable `ArrayList` instead of `collect`.

**Accuracy:** Parallelism does not recover results that overflowed or drifted due to rounding. Numeric ranges, ranking order, tie stability, and combiner correctness must be verified before evaluating performance.

---

## 19. Compatibility Milestone Table: What Java 8 Has vs. Does Not Have

This table helps you read modern documentation while still writing code that runs on Java 8.

| API / Syntax | Available Since | In Java 8, What Replaces It? |
|---|---:|---|
| `Stream.of`, `Stream.empty` | 8 | Use directly |
| `Collection.stream/parallelStream` | 8 | Use directly |
| `filter/map/flatMap/distinct/sorted/skip/limit` | 8 | Use directly |
| `reduce`, `collect`, `Collectors.groupingBy` | 8 | Use directly |
| `Collectors.mapping/collectingAndThen` | 8 | Use directly |
| `StreamSupport.stream`, `Spliterator` | 8 | Use directly |
| `Stream.ofNullable` | 9 | Check null then `Stream.empty()` or `Stream.of(value)` |
| `takeWhile`, `dropWhile` | 9 | Loop or custom `Spliterator` at the boundary |
| `Stream.iterate(seed, hasNext, next)` | 9 | `iterate(seed, next).limit(n)` if n is known, or conditional loop |
| `Optional.stream` | 9 | `flatMap(o -> o.isPresent() ? Stream.of(o.get()) : Stream.empty())` |
| `Collectors.flatMapping` | 9 | `flatMap` before grouping if preserving exact semantics, or custom collector |
| `Collectors.filtering` | 9 | `filter` before grouping **if losing empty group keys is acceptable**; otherwise custom collector |
| `Collectors.toUnmodifiableList/Set/Map` | 10 | `collectingAndThen` + defensive copy + `Collections.unmodifiable...` |
| `List.copyOf`, `Map.copyOf`, `Set.copyOf` | 10 | `new ArrayList<>(...)`/`new HashMap<>(...)` + unmodifiable view |
| No-arg `Optional.orElseThrow()` | 10 | `orElseThrow(() -> new NoSuchElementException())` |
| `String.isBlank`, `String.strip`, `Path.of` | 11 | `trim`, string check, `Paths.get` depending on semantics |
| `Optional.isEmpty` | 11 | `!optional.isPresent()` |
| `Collectors.teeing` | 12 | Custom collector or two separate aggregations |
| `Stream.toList` | 16 | `collect(Collectors.toList())`; if read-only is needed, copy + unmodifiable view |
| `Stream.mapMulti` | 16 | `flatMap` or custom collector/source |
| `record` (language) | 16 | Regular class with fields/constructor/getters |
| `Stream.gather` / Stream Gatherers | 24 | Build Java 8 pipeline using `map`/`flatMap`/collector or appropriate custom `Spliterator` |

**Read the table along three independent dimensions:**

1. **Java version of syntax:** `record`, `var`, switch expressions, and text blocks are not Java 8 syntax.
2. **Version of library API:** `Stream.toList()` does not exist on Java 8 even though the method call syntax looks ordinary.
3. **Runtime version:** running newer bytecode on Java 8 can fail due to class-file version, even if the code uses no new Streams.

### 19.1. Note That Not Every Replacement Shares Identical Semantics

- `String.trim` does not handle Unicode whitespace identically to `String.strip`.
- `filter(P)` is **not** equivalent to `takeWhile(P)`/`dropWhile(P)` on an arbitrary ordered source.
- Filtering before `groupingBy` can **drop groups with no remaining elements**, unlike downstream `Collectors.filtering`.
- `Collectors.toList` does not guarantee an unmodifiable result like `Stream.toList`.
- A replacement loop may yield the right result without the laziness or parallel capability of the original pipeline.

Do not swap APIs merely because their names look similar. Determine the **result contract** and behavior for empty sources, nulls, ordering, and duplicates before migrating versions.

---

## 20. Four Recipes for Porting Modern Code Back to Java 8

### 20.1. Stream.toList → Collectors.toList

Newer code:

~~~java
// Java 16+:
// List<String> names = source.stream()
//         .map(String::trim)
//         .toList();
~~~

Java 8 code:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = source.stream()
        .map(String::trim)
        .collect(Collectors.toList());
~~~

The two results may have the same **contents**, but differ in mutability contract. If the API requires a read-only List in Java 8:

~~~java
import java.util.ArrayList;
import java.util.Collections;

List<String> readOnly = Collections.unmodifiableList(
        new ArrayList<String>(names)
);
~~~

This creates a **shallow** structural snapshot; if the elements are mutable, the element objects themselves can still be modified through other references.

### 20.2. Stream.ofNullable → Null Check

Newer code:

~~~java
// Java 9+:
// Stream<String> s = Stream.ofNullable(maybeName);
~~~

Java 8:

~~~java
import java.util.stream.Stream;

String maybeName = null;

Stream<String> s = maybeName == null
        ? Stream.<String>empty()
        : Stream.of(maybeName);

System.out.println(s.count()); // 0
~~~

If `null` must be preserved as **a real element**, this is no longer a valid replacement; `Stream.ofNullable` intentionally drops null values.

### 20.3. takeWhile → Loop Stopping at the First Non-Matching Element

Java 9+ code:

~~~java
// List<Integer> prefix = values.stream()
//         .takeWhile(n -> n < 5)
//         .collect(Collectors.toList());
~~~

Java 8:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, 3, 8, 2, 4);
List<Integer> prefix = new ArrayList<Integer>();

for (Integer n : values) {
    if (n >= 5) {
        break;
    }
    prefix.add(n);
}

System.out.println(prefix); // [1, 3]
~~~

This loop keeps the **longest prefix** in List order. Replacing it with `filter(n -> n < 5)` would return `[1,3,2,4]`, **different** from the expected result.

### 20.4. mapMulti → flatMap

Java 16+ code:

~~~java
// Stream<Integer> expanded = values.stream()
//         .<Integer>mapMulti((n, output) -> {
//             if (n > 0) {
//                 output.accept(n);
//                 output.accept(n * 2);
//             }
//         });
~~~

Java 8:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> values = Arrays.asList(-1, 2, 3);

List<Integer> expanded = values.stream()
        .flatMap(n -> n > 0
                ? Stream.of(n, n * 2)
                : Stream.<Integer>empty())
        .collect(Collectors.toList());

System.out.println(expanded); // [2, 4, 3, 6]
~~~

`flatMap` can create a sub-stream per element, whereas `mapMulti` emits elements directly through a consumer. The demonstrated results are equivalent, though allocation characteristics and programming model may differ; do not draw performance conclusions from API names alone.

---

## 21. Compiling and Running Correctly Targeting Java 8

### 21.1. Choosing the Right Tool

When using **JDK 8** directly, commands to compile and run a standalone program:

~~~text
javac StreamApi8Demo.java
java StreamApi8Demo
~~~

When using **JDK 9 or later** but needing to produce Java 8-compatible code, use the option:

~~~text
javac --release 8 StreamApi8Demo.java
~~~

`--release 8` controls both the bytecode version and the set of Java APIs allowed for the target Java version; it is **not available in JDK 8's javac**.

Using only `-source 8 -target 8` with a newer JDK can restrict syntax and bytecode, but is **not sufficient to prevent references to library APIs added after Java 8**. This is a common cause of compatibility errors: code compiles on a newer JDK, then fails at runtime on Java 8 because the method/class cannot be found.

### 21.2. Recognizing Common Errors

| Symptom | Cause Worth Checking |
|---|---|
| `cannot find symbol: method toList()` on Stream | `Stream.toList` only exists since Java 16 |
| `cannot find symbol: takeWhile(...)` | Not in Java 8; introduced in Java 9 |
| `cannot find symbol: mapMulti(...)` | Not in Java 8; introduced in Java 16 |
| `cannot find symbol: method of(...)` with `List.of` | `List.of` collection factory is from Java 9 |
| `UnsupportedClassVersionError` | Bytecode was compiled for a newer runtime |
| `NoSuchMethodError` at runtime | Code references a method missing from the running library/runtime or has a version mismatch |
| `Cannot infer type` in collector/lambda | Inspect generic inference, overloads, and lambda types; not every error is from a missing API |

Read the stack trace and error line carefully. Do not see a `toList` error and simply swap in `Collectors.toList` without checking the **immutability contract** at the call site.

---

## 22. Complete Java 8 Example: Transaction Analysis

The following program **uses no post-Java 8 APIs**. It filters valid transactions, computes totals, groups revenue by category, finds the largest transaction, and collects the list of transaction IDs.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class StreamApi8Demo {

    static final class Transaction {
        private final String id;
        private final String category;
        private final long cents;
        private final boolean paid;

        Transaction(String id, String category,
                    long cents, boolean paid) {
            this.id = id;
            this.category = category;
            this.cents = cents;
            this.paid = paid;
        }

        String getId() { return id; }
        String getCategory() { return category; }
        long getCents() { return cents; }
        boolean isPaid() { return paid; }
    }

    public static void main(String[] args) {
        List<Transaction> txs = Arrays.asList(
                new Transaction("T1", "BOOK", 100L, true),
                new Transaction("T2", "PEN", 50L, true),
                new Transaction("T3", "BOOK", 300L, false),
                new Transaction("T4", "BOOK", 400L, true),
                new Transaction("T5", "PEN", 70L, true)
        );

        List<Transaction> paid = txs.stream()
                .filter(Transaction::isPaid)
                .collect(Collectors.toList());

        long paidCount = paid.stream().count();

        BigInteger total = paid.stream()
                .map(tx -> BigInteger.valueOf(tx.getCents()))
                .reduce(BigInteger.ZERO, BigInteger::add);

        Map<String, BigInteger> totalsByCategory = paid.stream()
                .collect(Collectors.groupingBy(
                        Transaction::getCategory,
                        Collectors.mapping(
                                tx -> BigInteger.valueOf(tx.getCents()),
                                Collectors.reducing(
                                        BigInteger.ZERO,
                                        BigInteger::add
                                )
                        )
                ));

        Optional<Transaction> biggest = paid.stream()
                .max(Comparator.comparingLong(
                        Transaction::getCents
                ));

        List<String> ids = paid.stream()
                .map(Transaction::getId)
                .sorted()
                .collect(Collectors.toList());

        System.out.println("paidCount=" + paidCount);
        System.out.println("total=" + total);
        System.out.println(
                "BOOK=" + totalsByCategory.get("BOOK")
        );
        System.out.println(
                "PEN=" + totalsByCategory.get("PEN")
        );
        System.out.println(
                "biggest=" + biggest.get().getId()
        );
        System.out.println("ids=" + ids);
    }
}
~~~

Expected output:

~~~text
paidCount=4
total=620
BOOK=500
PEN=120
biggest=T4
ids=[T1, T2, T4, T5]
~~~

**Explanation of compatibility aspects:**

- A regular `Transaction` class instead of `record` (not yet in Java 8).
- `Arrays.asList` instead of `List.of`.
- `Collectors.toList` instead of `Stream.toList`.
- `Collectors.groupingBy`, `mapping`, and `reducing` all already exist in Java 8.
- `BigInteger::add` sums integers accurately without overflowing a `long` total the way `summingLong` could.
- `Optional<Transaction>` from `max` represents the possibility of having no transactions; `biggest.get()` is only safe in this example because the `paid` list is known to be non-empty. In production systems, use `orElseThrow(Supplier)` or an explicit empty policy.

### 22.1. Data Flow of the Program

~~~text
List<Transaction>
        |
        +-- filter(paid)
               |
               +-- count()                   -> 4
               |
               +-- map(BigInteger cents)
               |      reduce(BigInteger::add) -> 620
               |
               +-- groupingBy(category,
               |       mapping(cents,
               |           reducing(add)))   -> {BOOK=500, PEN=120}
               |
               +-- max(byCents)              -> Optional(T4)
               |
               +-- map(id).sorted().collect  -> [T1, T2, T4, T5]
~~~

Each branch in the diagram starts from a **new Stream** on the `paid` list, because a consumed Stream cannot be reused. When optimizing source passes is necessary, you can design a collector that aggregates multiple fields, provided the combiner contract is preserved.

---

## 23. Common JDK Compatibility Mistakes

| Mistake | Why Is It Wrong on Java 8? | How to Fix |
|---|---|---|
| Using `stream.toList()` | Method added in Java 16 | `collect(Collectors.toList())`, check mutable/read-only requirements |
| Using `List.of(...)` | Factory introduced in Java 9 | `Arrays.asList(...)` or a concrete list |
| Using `Stream.ofNullable` | API from Java 9 | `value == null ? Stream.empty() : Stream.of(value)` |
| Using `Optional.stream` | API from Java 9 | `flatMap` using `isPresent/get` |
| Using `takeWhile/dropWhile` | API from Java 9 | Loop stopping at the boundary or custom source |
| Using `mapMulti` | API from Java 16 | `flatMap` if appropriate |
| Using `Collectors.filtering/flatMapping` | Downstream adapters from Java 9 | Custom collector or adjust pipeline after checking semantics |
| Using `Collectors.teeing` | API from Java 12 | Collector holding multiple fields or separate aggregations |
| Using `String.isBlank/strip` | API from Java 11 | `trim/isEmpty` depending on Unicode requirements |
| Using `Path.of` | API from Java 11 | `Paths.get` |
| Using `record` or `var` | Syntax not yet in Java 8 | Regular class / explicit type declarations |
| Using `optional.isEmpty()` | API from Java 11 | `!optional.isPresent()` |
| Assuming `Collectors.toList` is always immutable | Not guaranteed by the Collector | Copy and wrap with unmodifiable view if needed |
| Using `Stream.of(intArray)` to iterate numbers | Produces one element of type `int[]` | `Arrays.stream(intArray)` or `IntStream.of(...)` |
| Assuming `Stream<T>` has `sum()` | `sum()` lives on primitive streams | `mapToInt/mapToLong` or `reduce` |
| Reusing a Stream after `count` | Stream is already consumed | Create a new Stream from the source |
| Assuming parallel is always faster | Split/merge overhead and stateful operations | Verify correctness first, benchmark later |

---

## 24. API Selection Checklist for Java 8 Projects

Before submitting a pipeline, answer these questions:

1. **Is the target runtime truly Java 8?** Do not just look at the development machine's JDK version.
2. **Is the syntax valid in Java 8?** Do not use `record`, `var`, text blocks, or new `switch` expressions.
3. **Do all library methods exist since Java 8?** Check the milestone table, especially `Stream.toList` and `takeWhile`.
4. **Where does the source come from?** Collection, array, file, iterator, generator, or custom Spliterator?
5. **Is the Stream object or primitive?** If aggregating numbers, can you use `mapToInt/mapToLong`?
6. **Does the pipeline have a terminal operation?** `filter/map` operations by themselves do not consume the source.
7. **Is the Stream reused?** Each terminal operation needs an appropriate Stream; never reuse a closed/consumed one.
8. **Can it be empty?** Handle `Optional`/`OptionalDouble` according to an explicit policy.
9. **Can the source contain nulls?** Do not rely on `Optional.get` or mappers without checking.
10. **Are there ordering requirements?** `findFirst`, `limit`, and `forEachOrdered` require checking encounter order.
11. **Is parallelism used?** Verify stateless/non-interfering behavior, combiner, and separate containers.
12. **Does the result need a specific type or immutability?** `Collectors.toList` does not guarantee type or immutability.
13. **Are there I/O resources?** Use `try-with-resources` for file sources.
14. **Are numeric types wide enough?** Check for overflow and floating-point rounding error.
15. **Are there boundary tests and compilation for the target release?** Java 8 on JDK 8 or `--release 8` on JDK 9+.

### 24.1. Decision Diagram

~~~text
Need to process a dataset with Java 8?
                |
                v
        Create Stream Source
                |
                +---- Collection.stream / Arrays.stream
                +---- Stream.of / IntStream.range
                +---- Files.lines / StreamSupport.stream
                |
                v
       Choose Appropriate Type
           |              |
       Stream<T>       Primitive Stream
           |              |
           +------+-------+
                  |
                  v
         Intermediate Operations
        filter / map / flatMap
     distinct / sorted / skip / limit
                  |
                  v
       Choose Terminal Operation
       |         |          |
   Find/Count  reduce     collect
       |         |          |
   Optional    Value     List/Map/...
       \         |          /
        \        |         /
         v       v        v
    Check null/empty/order/overflow
                  |
                  v
     Compile Against Java 8 API
                  |
                  v
       Test and Benchmark
~~~

---

## 25. Self-Check Exercises (With Solutions)

### Exercise 1. Classifying Java 8 APIs

**Prompt:** Which methods in this list are available in Java 8: `filter`, `takeWhile`, `flatMap`, `mapMulti`, `Collectors.groupingBy`, `Stream.toList`, `Collectors.collectingAndThen`?

**Answer:** Available in Java 8: `filter`, `flatMap`, `Collectors.groupingBy`, `Collectors.collectingAndThen`. Not available: `takeWhile` (9), `mapMulti` (16), `Stream.toList` (16).

### Exercise 2. Fixing Stream.toList

**Prompt:** Convert `names.stream().map(String::trim).toList()` to Java 8 code.

**Answer:**

~~~java
List<String> result = names.stream()
        .map(String::trim)
        .collect(Collectors.toList());
~~~

If the result must be a structurally unmodifiable List, also add a defensive copy and `Collections.unmodifiableList` in Java 8.

### Exercise 3. Summing with a Primitive Stream

**Prompt:** `List<String> words = Arrays.asList("a", "bb", "ccc")`. Compute the total length using Java 8.

**Answer:**

~~~java
int total = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(total); // 6
~~~

### Exercise 4. Stream.of on a Primitive Array

**Prompt:** Why does `Stream.of(new int[]{1,2,3}).count()` return `1`?

**Answer:** This Stream contains one element of type `int[]`. To get three integers, use `Arrays.stream(new int[]{1,2,3})` or `IntStream.of(1,2,3)`.

### Exercise 5. range and rangeClosed

**Prompt:** How does `IntStream.range(1,4).sum()` differ from `IntStream.rangeClosed(1,4).sum()`?

**Answer:** `range(1,4)` iterates 1,2,3 for a sum of 6; `rangeClosed(1,4)` iterates 1,2,3,4 for a sum of 10.

### Exercise 6. Optional in Java 8

**Prompt:** `Optional<String> result` may be empty. Write how to return `"N/A"` if missing and how to throw an error if missing.

**Answer:**

~~~java
String shown = result.orElse("N/A");

String required = result.orElseThrow(
        () -> new IllegalStateException("Missing data")
);
~~~

Both approaches exist in Java 8. No-argument `result.orElseThrow()` does not exist in Java 8.

### Exercise 7. toMap with Duplicate Keys

**Prompt:** Data contains two strings `"an"` and `"bo"`. What happens with `Collectors.toMap(String::length, Function.identity())`?

**Answer:** With the same key `2`, the two-parameter overload throws `IllegalStateException`. If business logic allows duplicates, add an explicit merge function or use `groupingBy`.

### Exercise 8. Is FlatMapping from Java 9 Needed?

**Prompt:** Use Java 8 to flatten `List<List<Integer>>`.

**Answer:**

~~~java
List<Integer> flat = nested.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());
~~~

`Stream.flatMap` already exists in Java 8. `Collectors.flatMapping` is a newer downstream adapter.

### Exercise 9. Can takeWhile Be Replaced by filter?

**Prompt:** An ordered source is `[1,3,8,2,4]`, needing elements **before the first number ≥ 5**. Is using `filter(n -> n < 5)` correct?

**Answer:** No. `filter` returns `[1,3,2,4]`; the correct prefix is `[1,3]`. In Java 8, use a loop with `break` or a custom source with a stopping condition.

### Exercise 10. Why Is a Stream Not Reusable?

**Prompt:** Can you call `Stream<Integer> s = list.stream(); s.count(); s.findFirst();`?

**Answer:** No. `count()` is a terminal operation that already consumed the Stream. Creating `list.stream()` again allows finding.

### Exercise 11. reduce with Wrong Identity

**Prompt:** Why is `reduce(10, Integer::sum)` incorrect for a normal sum, especially on a parallel stream?

**Answer:** The identity for addition is `0`, not 10. Multiple partitions may each add 10. Use `reduce(0, Integer::sum)`; if business logic has an added fee of 10, apply it once after reduction.

### Exercise 12. Can a Shared ArrayList Be Used with parallel forEach?

**Prompt:** Is calling `parallelStream().forEach(sharedList::add)` safe when `sharedList` is an `ArrayList`?

**Answer:** No. `ArrayList` is not thread-safe for concurrent writes. Use `collect(Collectors.toList())` or a collector with contract-compliant supplier/combiner.

### Exercise 13. Does Collectors.toList Guarantee Read-Only?

**Prompt:** Can you rely on `Collectors.toList()` returning an unmodifiable list?

**Answer:** No. The Collector does not guarantee List type or immutability. If a structurally unmodifiable snapshot is needed in Java 8, use `Collections.unmodifiableList(new ArrayList<>(list))`.

### Exercise 14. Handling I/O with Streams

**Prompt:** Why must `try-with-resources` be used with `Files.lines(...)`?

**Answer:** A file Stream may hold open file handles/resources. Terminal operations do not automatically close the source; ensure `close()` is called on completion or error.

### Exercise 15. Compiling on a Newer JDK for Java 8

**Prompt:** Using JDK 17's javac and needing to release a program for Java 8. Which option should be chosen?

**Answer:** Use `javac --release 8 ...` to block post-Java 8 API references and emit appropriate bytecode. `--release` exists since JDK 9, not in JDK 8's javac.

### Exercise 16. Not Confusing Collector and Spliterator

**Prompt:** Does `Collector.Characteristics.CONCURRENT` have the same meaning as `Spliterator.CONCURRENT`?

**Answer:** No. One flag describes the collector's accumulation capability, while the other describes whether the source supports concurrent modification. The two contracts pertain to different layers of a Stream pipeline.

---

## Summary

Java 8 already provides **most of the Java Stream API foundation**: sources from collections/arrays/generators/I/O, `Stream<T>` and primitive streams, pipelines with `filter`/`map`/`flatMap`/`distinct`/`sorted`/`skip`/`limit`, terminal operations, `Optional`, `reduce`, `collect`, `Collectors`, `Spliterator`, and `StreamSupport`. Advanced topics such as grouping, custom collectors, and parallel processing all have their starting point right in Java 8.

Features such as `Stream.ofNullable`, `takeWhile/dropWhile`, `Optional.stream`, `Collectors.filtering`, `Collectors.teeing`, `Stream.toList`, `mapMulti`, and Stream Gatherers are **extensions from later JDKs**. When maintaining Java 8 projects, distinguish API names, added versions, and the contract of replacement approaches, especially for empty cases, ordering, immutability, and parallel correctness.

**Key takeaway:** Learning the **Java 8 API map** before learning newer Stream features helps you choose the right tool, read legacy code, and migrate versions safely. A short pipeline is only truly good when it **compiles on the target runtime**, **preserves exact business semantics**, and **does not rely on guarantees the API does not promise**.

