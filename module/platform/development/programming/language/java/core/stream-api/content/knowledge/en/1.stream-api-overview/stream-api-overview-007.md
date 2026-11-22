# Reading API Signatures and `java.util.stream` Documentation

## 1. Goal and approach

The Java Stream API lets you express data processing declaratively: create a stream of elements from a source, chain transformations into a **pipeline**, and trigger execution with a terminal operation. To use the API correctly, you need to know how to read **method signatures** and the contracts in **Javadoc**, rather than merely memorizing names like `filter`, `map`, or `collect`.

After this lesson, you will be able to:

- Locate the right classes, interfaces, and Javadoc version for `java.util.stream`.
- Read return types, parameters, type parameters (`<T>`, `<R>`), and wildcards (`? super`, `? extends`) in API signatures.
- Identify intermediate, terminal, lazy, and short-circuiting operations, as well as ordering, statefulness, and resource requirements.
- Look up and choose `Stream`, `IntStream`/`LongStream`/`DoubleStream`, `Collectors`, `Collector`, `Spliterator`, and `Gatherer` when solving real problems.
- Evaluate the conditions for a pipeline to be correct and appropriately performant before using `parallel()`.

Opening example:

```java
List<String> names = List.of("An", "Bình", "Anh", "Chi");

List<String> result = names.stream()  // Source: Stream<String>
    .filter(name -> name.startsWith("A")) // Intermediate: Stream<String>
    .map(String::toUpperCase)               // Intermediate: Stream<String>
    .toList();                              // Terminal: List<String>

System.out.println(result); // [AN, ANH]
```

`filter` and `map` build the pipeline description; `toList()` is what triggers data traversal. A `Stream` is **not** a collection storing pre-transformed elements. It is an interface describing computations over a data source, typically consumed only once.

## 2. Finding and reading the official documentation

### 2.1. API reference map

Open the Javadoc for the exact JDK version you are using and navigate from **Package `java.util.stream`** to related types:

| Documentation | When to use? | What to watch for |
| --- | --- | --- |
| [`java.util.stream` — package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html) | Understand the pipeline overview and type list | Principles of non-interference, stateless behavior, side effects, reduction, parallelism |
| [`Stream<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html) | Browse methods for object processing | `filter`, `map`, `flatMap`, `reduce`, `collect`, `toList`, `findFirst` |
| [`BaseStream<T, S>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html) | Control stream mode and lifecycle | `sequential`, `parallel`, `unordered`, `onClose`, `close` |
| [`IntStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html), `LongStream`, `DoubleStream` | Numeric computations avoiding boxing | `sum`, `average`, `summaryStatistics`, `boxed` |
| [`Collectors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html) | Combine elements into collections, maps, groups, statistics | Factory methods creating `Collector`, especially downstream collectors |
| [`Collector<T,A,R>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html) | Understand accumulation and custom collectors | `supplier`, `accumulator`, `combiner`, `finisher`, `characteristics` |
| [`Spliterator<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html) | Understand sources, ordering, and work splitting | `tryAdvance`, `trySplit`, `estimateSize`, `characteristics` |
| [`Gatherer<T,A,R>`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [`Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) | Stateful intermediate transformations, windowing, sequence scanning | Standard API from **JDK 24**; not present in JDK 21 |

**Remember package boundaries:** `Collection.stream()` is a method on `java.util.Collection`; `Files.lines()` belongs to `java.nio.file.Files`; `Predicate`, `Function`, `BiFunction`, and `Consumer` belong to `java.util.function`; `Optional` belongs to `java.util`. They frequently appear in pipelines even though they are not declared in `java.util.stream`.

### 2.2. What to read on a Javadoc page?

An API page typically has an overview section, a **Method Summary**, and **Method Details**. When selecting a method, read in order:

1. **Name, return type, and parameters:** what does the method accept and what result type does it produce?
2. **Type Parameters / Parameters / Returns:** the generic symbols and meaning of each parameter.
3. **Semantic description:** is the method intermediate or terminal, is it short-circuiting, and is element order guaranteed?
4. **API Note / Implementation Requirements / Implementation Note:** usage guidance and implementation commitments if any; do not mistake an implementation example for a guarantee across every JDK.
5. **Throws / Since / See Also:** exceptions, the version it was introduced in, and related APIs.
6. **Interface and package overview:** many crucial rules like non-interference, statelessness, or side-effect limits are documented here rather than repeated under every method.

For example, when encountering `Stream.toList()`, read that it is a **terminal operation**, the returned list is **unmodifiable**, and note **Since: 16**. Do not assume from the name `toList()` that the result is an `ArrayList` you can add elements to.

**Choose the right version:** JDK 21 Javadoc does not document `Stream.gather` because that method only became a standard API in JDK 24. When copying examples, check your project's JDK and each API's `Since` tag; newer JDK documentation may show methods your project cannot yet compile.

## 3. Decoding generic signatures

Consider a signature taken from `Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Read from the outside in:

- `T`: the **input** element type of the current `Stream<T>`; for example, in `Stream<String>`, `T` is `String`.
- `<R>` before the return type: the method declares a **new type parameter** named `R`. The compiler usually infers it from `mapper`.
- `Stream<R>`: the result is still a stream, but with elements of type `R`.
- `Function<X,Y>`: a function taking a value of type `X` and returning a value of type `Y`.
- `? super T`: `mapper` can accept `T` **or a supertype of `T`** (flexibility on the input side).
- `? extends R`: `mapper` can return `R` **or a subtype of `R`** (flexibility on the output side).

Therefore, `map` transforms **each element** using a function; it does not remove elements or execute the pipeline immediately.

```java
Stream<String> source = Stream.of("java", "stream");
Stream<Integer> lengths = source.map(String::length);
// T = String; R = Integer; mapper: String -> Integer
List<Integer> values = lengths.toList(); // [4, 6]
```

Frequently seen symbols:

| Symbol | How to read it | Example meaning |
| --- | --- | --- |
| `T` | Element type of the stream | `Stream<Order>` has `T = Order` |
| `<R>` | New type declared by the method | `map` converts `Order` to `String` |
| `<K, V>` | Key and value types, typically when collecting into a map | `Map<String, Long>` |
| `? super T` | Allows `T` or a supertype on the data-consuming side | `Predicate<Object>` can test a `String` |
| `? extends R` | Allows `R` or a subtype on the data-producing side | A mapper returning `Integer` where `Number` is expected |
| `A` in `Collector<T,A,R>` | Intermediate accumulation container type | May be an internal object hidden from callers |
| `Optional<T>` | Result may or may not be present | `findFirst()` on an empty stream returns `Optional.empty()` |

**Distinguish two generic scopes:** in `Stream<T>`, `T` belongs to the interface; in `<R> Stream<R> map(...)`, `R` is declared specifically for that method invocation. Read both to know how data types change.

## 4. Reading the contracts of key operations

### 4.1. Intermediate operations

These methods return a new stream and usually execute only when a terminal operation runs:

| Abbreviated signature from `Stream<T>` | How to understand it |
| --- | --- |
| `Stream<T> filter(Predicate<? super T> predicate)` | Keeps elements for which the predicate returns `true` |
| `<R> Stream<R> map(Function<? super T, ? extends R> mapper)` | Transforms one element into one value |
| `<R> Stream<R> flatMap(Function<? super T, ? extends Stream<? extends R>> mapper)` | Each element produces a sub-stream, then flattens into the result stream |
| `<R> Stream<R> mapMulti(BiConsumer<? super T, ? super Consumer<R>> mapper)` | Each element can emit 0, 1, or more values via `Consumer<R>`; since JDK 16 |
| `Stream<T> distinct()` | Removes duplicate elements according to `equals` |
| `Stream<T> sorted(Comparator<? super T> comparator)` | Sorts using a comparator; a stateful operation |
| `Stream<T> limit(long maxSize)` | Takes at most `maxSize` elements; can short-circuit the pipeline |
| `Stream<T> takeWhile(Predicate<? super T> predicate)` | For ordered streams, takes the contiguous prefix matching the predicate; since JDK 9 |
| `Stream<T> peek(Consumer<? super T> action)` | Observes elements during traversal, usually for diagnostics; does not guarantee `action` runs for every element |

Two easily confused examples:

```java
List<List<String>> groups = List.of(
    List.of("Java", "Kotlin"),
    List.of("Python")
);

List<String> wrongShape = groups.stream()
    .map(group -> group.toString())
    .toList(); // ["[Java, Kotlin]", "[Python]"]

List<String> flattened = groups.stream()
    .flatMap(List::stream)
    .toList(); // ["Java", "Kotlin", "Python"]
```

`map` produces **one output per input**, whereas `flatMap` lets each input produce **an arbitrary number** of outputs via a sub-stream. When using `flatMap`, the sub-streams created by the mapper are closed after their contents have been consumed.

Note that **stateful** and **short-circuiting** are two distinct properties: `sorted` needs to examine many elements before emitting results; `limit` can stop early. With ordered sources, `distinct`, `sorted`, or `limit` can increase parallel execution cost.

### 4.2. Terminal operations

| Abbreviated signature from `Stream<T>` | Result type and semantics |
| --- | --- |
| `long count()` | Counts elements; implementations may optimize without traversing every element |
| `boolean anyMatch(Predicate<? super T> predicate)` | At least one element matches; short-circuiting |
| `boolean allMatch(Predicate<? super T> predicate)` | All elements match; short-circuiting |
| `Optional<T> findFirst()` | First element if present, in encounter order |
| `Optional<T> findAny()` | Any element if present; suitable when order is not needed |
| `Optional<T> reduce(BinaryOperator<T> accumulator)` | Combines elements into one value; may be empty |
| `T reduce(T identity, BinaryOperator<T> accumulator)` | Combines with an initial value (`identity`) |
| `<R, A> R collect(Collector<? super T, A, R> collector)` | Collects using an accumulation strategy encapsulated in a `Collector` |
| `List<T> toList()` | Creates an unmodifiable list; since JDK 16 |
| `void forEach(Consumer<? super T> action)` | Performs an action; does not guarantee encounter order in parallel mode |

`findFirst`, `findAny`, and `reduce` without an identity return `Optional`, because no result may exist. For instance:

```java
String first = Stream.of("A", "B")
    .filter(s -> s.startsWith("Z"))
    .findFirst()
    .orElse("Not found");

System.out.println(first); // Not found
```

Do not call `get()` on an `Optional` without checking presence. For `IntStream`, `LongStream`, and `DoubleStream`, methods like `findFirst()` return `OptionalInt`, `OptionalLong`, and `OptionalDouble`, respectively.

### 4.3. Read `reduce` before deciding to use it

The three overloads of `reduce` serve different problems:

```java
Optional<Integer> optionalSum = Stream.of(1, 2, 3)
    .reduce(Integer::sum); // Optional[6]

int sum = Stream.of(1, 2, 3)
    .reduce(0, Integer::sum); // 6

int totalLength = Stream.of("A", "BB", "CCC")
    .reduce(0, (sumSoFar, s) -> sumSoFar + s.length(), Integer::sum); // 6
```

In the third overload, `U` (in this example `Integer`) can differ from `T` (in this example `String`). `identity` must be a neutral identity value; `combiner` must be compatible with `accumulator`; the reduction operation must be **associative** to work properly when the stream is partitioned or run in parallel. Do not use `reduce` to mutate a mutable accumulator object like `ArrayList`: that job belongs to `collect`.

For sums, averages, or numeric statistics, prefer dedicated primitive stream operations whenever they express the problem more clearly:

```java
long sum = Stream.of("10", "20", "30")
    .mapToLong(Long::parseLong)
    .sum(); // 60
```

## 5. Reading `collect`, `Collectors`, and `Collector` signatures

An important method is:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

`T` is the input element type; `A` is the internal accumulator type; `R` is the final result type. `Collectors` provides *factory methods* to construct suitable `Collector`s, such as `toList()`, `toSet()`, `joining()`, `counting()`, `mapping()`, `groupingBy()`, `partitioningBy()`, `summingLong()`, and `toMap()`.

Example reading an overloaded signature of `groupingBy`:

```java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
```

We read it as: `classifier` produces a key `K` for each element `T`, `downstream` processes elements within each group to produce a value `D`, and the overall result is `Map<K,D>`. The wildcard `?` in the accumulator position of `Collector<T, ?, Map<K,D>>` indicates that callers do not need to know the internal accumulator type.

Complete example, running on **JDK 17 or later**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class StreamApiReading {
    record Order(String region, String product, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("HN", "Book", 120),
            new Order("HCM", "Pen", 50),
            new Order("HN", "Monitor", 300),
            new Order("HCM", "Desk", 180)
        );

        Map<String, Long> revenueByRegion = orders.stream()
            .filter(order -> order.amount() >= 100)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amount)
            ));

        System.out.println(revenueByRegion.get("HN"));  // 420
        System.out.println(revenueByRegion.get("HCM")); // 180

        long allRevenue = orders.stream()
            .mapToLong(Order::amount)
            .sum();
        System.out.println(allRevenue); // 650

        List<String> productNames = orders.stream()
            .map(Order::product)
            .distinct()
            .toList();
        System.out.println(productNames); // [Book, Pen, Monitor, Desk]
    }
}
```

Type analysis step by step:

| Expression | Inferred type | Reason |
| --- | --- | --- |
| `orders.stream()` | `Stream<Order>` | Source contains `Order` |
| `.filter(...)` | `Stream<Order>` | Does not change element type |
| `Order::region` | Compatible `Function<Order,String>` | Selects group key as `String` |
| `Collectors.summingLong(Order::amount)` | Collector producing `Long` | Sums `long` values for each group |
| `.collect(groupingBy(...))` | `Map<String,Long>` | Result has region keys, summed values |
| `.mapToLong(Order::amount)` | `LongStream` | Uses primitive stream |

**Two caveats when reading collector documentation:**

- `Stream.toList()` guarantees an unmodifiable result; `Collectors.toList()` **makes no guarantees** on the exact type, mutability, serializability, or thread-safety. If you explicitly want a mutable list, use `collect(Collectors.toCollection(ArrayList::new))` with `import java.util.ArrayList`.
- `groupingBy` by default does not guarantee `Map` implementation or key order. If ordering is required, check the overload taking a `mapFactory`, or sort the output explicitly. For duplicate keys, `Collectors.toMap(keyMapper, valueMapper)` can throw an exception: check the overload taking a `mergeFunction`.

### 5.1. When is a custom `Collector` needed?

`Collector<T,A,R>` describes five components: `supplier` creates the accumulator, `accumulator` folds an element into it, `combiner` merges two accumulators, `finisher` produces the result, and `characteristics` describes properties. The API provides `Collector.of(...)` to construct a collector manually.

When reading `Collector.Characteristics`, distinguish:

- `CONCURRENT`: the accumulator can be updated concurrently by multiple threads per the collector contract.
- `UNORDERED`: the result does not depend on encounter order.
- `IDENTITY_FINISH`: the accumulator can be used directly as the final result with no actual conversion step.

Do not attach characteristics unless your accumulator and algorithm satisfy their requirements. In many problems, composing built-in collectors (`mapping`, `filtering`, `collectingAndThen`, `groupingBy`) is more maintainable than writing a new collector.

## 6. Reading descriptions of ordering, laziness, and side effects

The Javadoc for `Stream` and the package are the primary source for understanding the following:

**Encounter order.** A source like `List` typically has an encounter order; a source like `HashSet` does not guarantee a stable order. `forEach` may process out of order when running in parallel; `forEachOrdered` respects encounter order if the stream is ordered, though it may be more expensive. `findFirst` prioritizes the first element; `findAny` may return any element.

**Laziness and optimization.** A terminal operation can short-circuit work or skip intermediate steps if doing so does not change the guaranteed result. Therefore, do not use `peek` or `map` solely to log or update counters that the program relies on:

```java
long count = List.of("a", "b", "c").stream()
    .peek(System.out::println)
    .count();
// count == 3; must not rely on peek definitely printing three lines.
```

**Non-interference and statelessness.** Functions passed to a stream should not modify the source being traversed and should not depend on state that changes between invocations. When using `parallel()`, updating an external `ArrayList`, `HashMap`, or counter from a lambda can cause race conditions or errors. Express accumulation using `collect`/`reduce` or statistical operations instead of shared side effects.

**Reusability.** A stream that has executed a terminal operation cannot be reused; if you need two results, create two new streams from a re-traversable source:

```java
List<Integer> data = List.of(1, 2, 3);
long count = data.stream().count();
int total = data.stream().mapToInt(Integer::intValue).sum();
```

**Resources.** Streams created from `List.stream()` generally do not need to be closed. Streams tied to I/O such as `Files.lines(path)` must be closed to release handles:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

`Stream` extends `BaseStream` and has `close()` via `AutoCloseable`; try-with-resources is the right approach for sources requiring resource cleanup. Do not keep a stream open longer than its usage scope.

## 7. Reading advanced APIs and version limits

### 7.1. Primitive streams and type conversion

`Stream<Integer>` holds `Integer` objects; `IntStream` works directly on primitive `int` values. Signatures to recognize:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper) // on Stream<T>
LongStream mapToLong(ToLongFunction<? super T> mapper) // on Stream<T>
Stream<Integer> boxed()                            // on IntStream
OptionalDouble average()                           // on IntStream
```

`mapToInt` and `mapToLong` avoid unnecessary boxing in numeric calculations. `boxed()` should only be used when converting back to an object stream, such as before collecting into a `List<Integer>`.

### 7.2. `Spliterator` and parallel processing

A stream can use `Spliterator<T>` to traverse and split a source. When reading `boolean tryAdvance(Consumer<? super T> action)` and `Spliterator<T> trySplit()`, understand that the first attempts to consume one element, while the second may return a split-off spliterator or `null` if it cannot split. Characteristics `ORDERED`, `SIZED`, `SUBSIZED`, `SORTED`, `DISTINCT`, `NONNULL`, `IMMUTABLE`, and `CONCURRENT` describe the source and enable optimizations.

`parallel()` is only a request to execute the pipeline in parallel mode; it does not guarantee faster execution. Data splitting, result combining, ordering, stateful operations, and per-element cost all affect performance. Use associative combining operations, avoid shared mutable state, and benchmark on real data before drawing conclusions.

### 7.3. `Stream.gather` and Stream Gatherers (JDK 24+)

JDK 24 made Stream Gatherers a standard API. Signature to read:

```java
<R> Stream<R> gather(Gatherer<? super T, ?, R> gatherer)
```

`Gatherer<T,A,R>` represents an intermediate operation that can maintain state `A`, consume input `T`, and emit output `R`. It adds transformations like windowing, running scans, or constrained transformations that simple `map`/`filter` chains struggle to express.

Example specific to **JDK 24 or later**:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

When reading a custom Gatherer, examine `initializer`, `integrator`, `combiner`, `finisher`, and any constraints on ordering/parallelizability. Do not add `gather` to code targeting JDK 17 or 21; use a compatible alternative or upgrade versions after evaluation.

## 8. Lookup workflow when encountering an unfamiliar method

Example problem: "From `Stream<Order>`, obtain `Map<String,Long>` of total revenue by region." Instead of guessing methods at random:

1. **Identify input/output:** `T = Order`; need key `K = String` and value `D = Long`.
2. **Find a terminal operation:** `Stream.collect` produces an arbitrary result type `R`, more fitting than `toList()`.
3. **Find a collector factory:** `Collectors.groupingBy(classifier, downstream)` returns `Map<K,D>`; `summingLong` computes `Long` per group.
4. **Check the contract:** map order is not guaranteed; handle `null`, empty data, and business-dependent conditions before writing the pipeline.
5. **Check `Since` and JDK version:** the APIs used in the example have been available since before JDK 17.
6. **Test with small data:** test regions with multiple orders, regions with a single order, orders filtered out, and an empty source; measure performance before considering `parallel()`.

### Self-check on reading signatures

**Question 1.** What does `boolean noneMatch(Predicate<? super T> predicate)` accept and can it short-circuit?

Answer: it accepts a predicate testing each `T`, returning `true` when no element matches; it can stop immediately as soon as one matching element is found. On an empty stream, the result is `true`.

**Question 2.** How does `Optional<T> min(Comparator<? super T> comparator)` differ from `Stream<T> sorted(Comparator<? super T>)`?

Answer: `min` is a terminal operation returning an optional value, whereas `sorted` is an intermediate operation returning a stream described to be sorted. When you only need the smallest element, `min` expresses the goal more directly.

**Question 3.** Why does `Stream<T>.mapToLong(...)` return `LongStream`, whereas `map(...)` returns `Stream<R>`?

Answer: `mapToLong` is specialized for primitive `long` data and directly supports `sum`, `average`, and `summaryStatistics`; `map` keeps object representation and can incur boxing.

**Question 4.** Should you use `stream.parallel().forEach(x -> sharedList.add(x))`?

Answer: no; a shared `ArrayList` is not safe when multiple threads update it concurrently. Use an appropriate terminal collection such as `toList()`/`collect` so the library coordinates results; only use `forEach` with actions that satisfy concurrency requirements and do not depend on order.

## 9. Quick reference table when reading Stream API Javadoc

| Question to answer | Where to find it in Javadoc |
| --- | --- |
| What are the input and output element types? | Method signature; Type Parameters; Parameters; Returns |
| Does it run immediately, and can it short-circuit? | Intermediate/terminal/short-circuiting description |
| Is the result stable with respect to source order? | Encounter order and method-specific description |
| Does it work with empty/null streams? | Returns, Throws, Optional and collector contracts |
| Can lambdas read/mutate external state? | Package summary; non-interference; statelessness; side effects |
| Is parallel execution correct and beneficial? | Reduction, parallelism, Collector characteristics, Spliterator characteristics |
| When should a stream be closed? | `BaseStream.close`, `onClose`, documentation of the I/O source |
| Which versions does the project support? | `Since`, Javadoc of the exact target JDK |

When reading the API, inspect **the signature to determine the type contract**, read **the Javadoc description to determine behavior**, and verify **the data source and JDK version** to select the right pipeline. This is the foundation for expanding from `filter`/`map` to `reduce`, custom collectors, Spliterator, parallel processing, and Stream Gatherers while keeping control over state, resources, and performance.
