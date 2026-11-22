# What Is the Stream API and What Problem Does It Solve?

In Java applications, data often passes through a sequence of operations: retrieving a list of orders, removing unpaid orders, selecting the amounts, calculating the total, or grouping by category. **Java Stream API** helps express that processing chain as a *pipeline* (a data-processing pipeline) with composable transformation and aggregation operations.

The Stream API was introduced in **Java 8**, residing primarily in the `java.util.stream` package. It provides a **declarative** style: describing *what result you want from the data*, rather than manually controlling every iteration step with loops and accumulator variables. A Stream is not a new storage structure, nor does it automatically make a program faster.

After this lesson, you will be able to identify problems well-suited for the Stream API, read a pipeline from source to result, distinguish between intermediate and terminal operations, and understand the important limitations before applying it.

## 1. A practical problem: from raw data to results

Suppose a sales system needs to:

- Keep only **paid** orders.
- Calculate the **total amount** of those orders.
- Count the number of paid orders **by product category**.

With traditional loops, the developer manually manages iteration, conditions, total variables, and counting maps. With the Stream API, each requirement is represented by an operation in a pipeline.

The complete example below runs on **JDK 17 or later** (using `record` to represent sample data). The core Stream operations in the example have been available since Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class StreamOverviewDemo {
    record Order(String id, String category, int amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "Books", 120_000, true),
            new Order("DH02", "Books",  90_000, false),
            new Order("DH03", "Pens",   30_000, true),
            new Order("DH04", "Books",  50_000, true)
        );

        // Imperative style: manually iterate and update a variable.
        int totalWithLoop = 0;
        for (Order order : orders) {
            if (order.paid()) {
                totalWithLoop += order.amount();
            }
        }

        // Declarative style: describe the data-processing pipeline.
        int totalWithStream = orders.stream()
            .filter(Order::paid)
            .mapToInt(Order::amount)
            .sum();

        // Another problem on the same source: group and count.
        Map<String, Long> paidCountByCategory = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::category,
                Collectors.counting()
            ));

        System.out.println(totalWithLoop);                  // 200000
        System.out.println(totalWithStream);                // 200000
        System.out.println(paidCountByCategory.get("Books")); // 2
        System.out.println(paidCountByCategory.get("Pens"));  // 1
    }
}
~~~

The notable point is not that Stream lets you write fewer lines in every situation, but that **the meaning of each step is clearly expressed**:

1. `orders.stream()`: creates a Stream from the list of orders.
2. `filter(Order::paid)`: keeps paid orders.
3. `mapToInt(Order::amount)`: extracts the amount as a primitive integer stream (`IntStream`).
4. `sum()`: computes the total and returns an `int` value.
5. In the second pipeline, `collect(groupingBy(..., counting()))` builds a map of order counts by category.

The two pipelines create **two independent Streams** from the same `List`. The original list is not modified by these operations. The resulting `Map` from `groupingBy` provides no guarantee on key iteration order; the example checks each key individually to avoid depending on display order.

> **Note on currency:** `int` is used only for a concise and readable example. In real systems, you must clearly define the currency unit, overflow potential, and rounding rules; `BigDecimal` or an integer representing the smallest currency unit is usually more appropriate depending on requirements.

## 2. What is a Stream, really?

`Stream<T>` represents **a sequence of elements for processing** (not necessarily a pre-stored list). A Stream connects a data source to operations and typically traverses the source only when a result is needed.

A typical pipeline has three parts:

~~~mermaid
flowchart LR
    A["Source: List<Order>"] --> B["Intermediate: filter(paid)"]
    B --> C["Intermediate: mapToInt(amount)"]
    C --> D["Terminal: sum()"]
    D --> E["Result: 200000"]
~~~

| Component | Role | Examples |
|---|---|---|
| **Source** | Supplies elements to the pipeline | `list.stream()`, `Arrays.stream(array)`, `Stream.of(...)` |
| **Intermediate operation** | Returns a new Stream to continue describing the processing | `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit` |
| **Terminal operation** | Triggers the necessary computation and produces the final result or side effect | `sum`, `count`, `collect`, `reduce`, `findFirst`, `forEach` |

A few points to remember:

- A Stream **does not own data** in the sense that a `List` or `Set` does. The source can be a collection, an array, a generated sequence, or lazily read data.
- Operations such as `filter` and `map` are generally **lazy**: building a pipeline does not mean all elements have already been traversed.
- Each Stream can only be **consumed once**. After a terminal operation, to run a new pipeline you must create a new Stream from the source.
- A Stream processes elements according to each operation's contract; it **does not inherently modify the data source** and does not guarantee that every operation requires no intermediate memory.

### How does a Stream differ from a Collection?

| `Collection` (e.g., `List`) | `Stream` |
|---|---|
| Manages a group of elements | Describes a processing pipeline over elements |
| Can be read or traversed multiple times | Typically consumed only once |
| Supports storage operations such as add and remove | Provides transformation, filtering, and aggregation operations |
| Elements are currently held in the collection | Elements may be fetched or generated when the pipeline runs |

You can think of it this way: **a collection is where data is kept; a stream is how work on the data is expressed**. One list can create many different Streams, while the result of a Stream can be a number, an `Optional`, a `Map`, a `List`, or another type.

## 3. How a pipeline works: declare first, process when needed

This is the characteristic that distinguishes the Stream API from chaining functions that always allocate intermediate lists.

~~~java
import java.util.Optional;
import java.util.stream.Stream;

Stream<Integer> evenNumbers = Stream.of(1, 2, 3, 4)
    .filter(n -> {
        System.out.println("Checking: " + n);
        return n % 2 == 0;
    });

System.out.println("Pipeline declared");

Optional<Integer> firstEven = evenNumbers.findFirst();
System.out.println(firstEven.orElse(-1));
~~~

Observed output in this case:

~~~text
Pipeline declared
Checking: 1
Checking: 2
2
~~~

When `filter` is declared, no elements have been checked yet. `findFirst()` is a terminal operation; it asks for the first even element, so traversal **stops immediately upon finding 2**. This is the *short-circuit* mechanism of certain operations, including `findFirst`, `anyMatch`, and `limit` when applicable conditions allow.

Printing logs inside `filter` is only for illustration. In production code, keep filtering and transformation functions **side-effect-free** so results are easier to understand, easier to test, and safer when changing execution strategies.

### Why can't the same Stream be reused?

~~~java
Stream<Integer> numbers = Stream.of(1, 2, 3);
long quantity = numbers.count(); // 3

// numbers.filter(n -> n > 1).count();
// Invalid: Stream has already been consumed; typically throws IllegalStateException.

// Correct way: create another Stream from a reusable source.
List<Integer> source = List.of(1, 2, 3);
long all = source.stream().count();
long greaterThanOne = source.stream().filter(n -> n > 1).count();
~~~

In practice, there are also terminal operations that validly yield an empty result. For example, `findFirst()` returns `Optional<T>` because the source may contain no matching element. Use `orElse`, `orElseGet`, `ifPresent`, or handle the empty case explicitly instead of calling `get()` by default.

## 4. What kinds of problems does the Stream API solve?

| Need type | Business question | Common operations |
|---|---|---|
| **Filtering** | Which orders are paid? | `filter` |
| **Projection/transformation** | Extract emails from a customer list? | `map` |
| **Flattening** | Combine items from multiple orders into one stream? | `flatMap` |
| **Searching/checking** | Are there any overdue orders? | `findFirst`, `anyMatch`, `allMatch` |
| **Limiting/sorting/deduplicating** | Get 10 distinct product codes in order? | `distinct`, `sorted`, `limit` |
| **Aggregation** | What is the total revenue or order count? | `mapToInt`, `sum`, `count`, `reduce` |
| **Grouping** | How many orders are in each category? | `collect`, `Collectors.groupingBy` |
| **Result creation** | Which `List`, `Set`, or `Map` is produced? | `toList`, `collect` |

A pipeline often combines multiple operations to answer a complete question. For example: "Get the unique names of paid customers, sorted alphabetically" can be expressed as `filter → map → distinct → sorted → toList`.

### Common data sources

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Chi");
Stream<String> fromList = names.stream();

Stream<String> fromArray = Arrays.stream(new String[] {"An", "Bình"});
Stream<String> fromValues = Stream.of("An", "Bình");

// Not all Streams contain objects:
IntStream numbers = IntStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5

System.out.println(fromList.count());           // 3
System.out.println(fromArray.count());          // 2
System.out.println(fromValues.count());         // 2
System.out.println(numbers.sum());              // 15
~~~

`IntStream`, `LongStream`, and `DoubleStream` avoid boxing overhead in many arithmetic operations, and provide operations such as `sum`, `average`, and `max`. With object Streams, `mapToInt` or `mapToLong` is often the right conversion step before numeric aggregation.

Sources do not have to be finite: `Stream.generate(...)` or `Stream.iterate(...)` can produce unbounded sequences. You must design appropriate terminal operations and stopping conditions; for example, use `limit` when you want a finite number of elements.

## 5. Why is the declarative style useful?

### Expresses requirements closely

`filter` reads like "keep elements matching a condition", `map` reads like "transform each element", and `collect` reads like "gather the result". When the chain of operations is small, well-separated, and well-named, readers can follow the data flow without having to track counter variables or temporary state as much.

### Easy to compose and change rules

The same order source can produce different results:

~~~java
long paidOrders = orders.stream()
    .filter(Order::paid)
    .count();

boolean hasUnpaidOrders = orders.stream()
    .anyMatch(order -> !order.paid());

List<String> paidCategories = orders.stream()
    .filter(Order::paid)
    .map(Order::category)
    .distinct()
    .sorted()
    .toList(); // JDK 16+: the resulting List cannot be modified.
~~~

The snippets above are placed in the context of the class and `orders` variable from the opening example. Each snippet calls `orders.stream()` separately to ensure a valid Stream lifecycle.

### Clearly expresses aggregations

Instead of manually maintaining a temporary data structure, `Collectors` can express grouping, counting, string joining, or combining multiple results. This is why Streams are especially useful for processing reports, lists, API responses, and data normalization steps.

However, **shorter syntax does not automatically mean more readable code**. A pipeline that is too long, nests multiple lambdas, or hides side effects can be harder to read than a clear loop.

## 6. Rules and limitations you must know from the start

### 6.1. Do not modify the source while traversing

Functions passed to `filter`, `map`, or `reduce` generally need to be **non-interfering** and, in typical operations, should not depend on mutable external state (**stateless**).

Do not do the following:

~~~java
List<Integer> values = new java.util.ArrayList<>(List.of(1, 2, 3));

// Bad design: modifying the source itself while the Stream is traversing it.
values.stream().forEach(values::remove);
~~~

This can produce unexpected behavior, skip elements, or throw exceptions depending on the source and traversal method. When you want to filter out elements, **create a new result** or use a dedicated collection update operation such as `removeIf` when you genuinely want to mutate the collection.

Also avoid accumulating results by calling `forEach(result::add)` on an external `ArrayList`, especially when running in parallel; prefer `collect` or `toList`.

### 6.2. Order is not always guaranteed

Sources like `List` typically have an *encounter order*; some sources like `HashSet` do not commit to an order. `sorted` establishes an order using a comparator, whereas `findAny` may return any element, especially when running in parallel.

If the output needs a deterministic order, choose an appropriate source and operation. Do not infer the order of a `Map` created by `groupingBy` solely from the order of the input elements.

### 6.3. Lazy does not always mean low memory

Some stateful operations like `sorted` or `distinct` may need to store information about elements already seen, whereas operations like `filter` and `map` typically process element by element. Therefore, you cannot conclude that every Stream operates in constant memory.

In terms of time, a simple pipeline over `n` elements still typically has linear complexity similar to a loop. Streams can incur overhead from pipeline creation, lambda invocation, or boxing. Measure on realistic data and configuration if performance is a critical requirement.

### 6.4. Parallel Streams are only suitable under certain conditions

`parallelStream()` or `stream().parallel()` allows the framework to distribute processing across multiple threads, but **does not guarantee faster execution**. Data splitting, result combining, resource contention, ordering, and side effects all affect performance and correctness.

Only consider parallel processing when the task is large enough, operations are independent, the source is easy to split, and the aggregation obeys the contract. Do not enable parallelism by default for blocking I/O operations, very small pipelines, or code that uses shared mutable state.

### 6.5. Some Streams need to be closed

Most Streams created from collections do not hold external resources. By contrast, a Stream opened by `Files.lines(...)` may own I/O resources; you should use `try-with-resources`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data.txt");
try (Stream<String> lines = Files.lines(path)) {
    long nonBlankLines = lines
        .filter(line -> !line.isBlank())
        .count();
    System.out.println(nonBlankLines);
}
~~~

The example uses `Path.of` and `String.isBlank` (JDK 11+), assuming the file `data.txt` exists. A terminal operation **does not replace** closing the I/O source; the `try` block ensures resource release.

### 6.6. The Stream API is not every kind of "stream" in Java

- `java.util.stream.Stream`: a model for processing elements through a pipeline.
- `java.io.InputStream` and `OutputStream`: byte streams for I/O.
- Reactive/`Flow.Publisher` models: concerned with asynchronous data emission and regulating consumer demand (*backpressure*).

The names are similar, but the purposes and programming contracts are different. Do not use the Stream API as an asynchronous event-delivery system just because it has "Stream" in its name.

## 7. Relation to advanced Stream topics

Once you understand a basic pipeline, you will see that advanced topics arise from very specific needs:

| Development need | Next topic |
|---|---|
| Combining multiple elements into a single value | `reduce`, identity and associativity rules |
| Collecting data into custom structures | `collect`, `Collector`, `groupingBy`, `partitioningBy` |
| Controlling how a source is split and traversed | `Spliterator` |
| Properly utilizing multiple CPU cores | Parallel Streams, concurrent collectors, performance measurement |
| Complex stateful stream transformations or changing element counts | **Stream Gatherers** (standardized API in JDK 24) |

These tools extend the same source → operations → result model. You do not need to use them in the very first lesson; what matters is understanding the contracts around Stream lifecycle, ordering, state, and resources before going deeper.

## 8. Short practice exercise

**Requirement:** From a list of programming language names with whitespace, mixed casing, and empty elements, normalize, deduplicate, sort, and build a result list. Do not modify the input list.

~~~java
import java.util.List;
import java.util.Locale;

List<String> raw = List.of("Java", " java ", "Kotlin", "", "Go");

List<String> result = raw.stream()
    .map(String::trim)
    .filter(value -> !value.isEmpty())
    .map(value -> value.toUpperCase(Locale.ROOT))
    .distinct()
    .sorted()
    .toList();

System.out.println(result); // [GO, JAVA, KOTLIN]
System.out.println(raw.size()); // 5: the source remains unchanged
~~~

Try answering for yourself before looking at the hints:

1. What is the **source** of the pipeline? — The list `raw`, fed into the pipeline via `raw.stream()`.
2. Which **intermediate operations** change the values? — The two `map` operations trim whitespace and convert to uppercase, respectively.
3. Which **operations** remove elements or duplicates? — `filter` drops empty strings; `distinct` drops duplicate values.
4. **When is the pipeline actually consumed?** — When `toList()`, the terminal operation, is called.
5. **Can you then call `count()` on the Stream already used for `toList()`?** — No; you must create a new Stream from `raw`.

`toList()` was introduced in **Java 16** and returns an unmodifiable `List`. If you need Java 8 compatibility, use `collect(Collectors.toList())`; however, this collector's contract does not guarantee the mutability of the returned list. Choose the result-creation approach according to your JDK version and actual usage needs.

## 9. When should you choose the Stream API?

**Prefer Stream** when data needs to be filtered, projected, searched, grouped, or aggregated; the process can be written as independent operations; and the result can be determined from the inputs with minimal dependence on external state.

**Consider loops or other control structures** when the algorithm requires multiple complex state updates, detailed per-step error handling, sequential I/O interactions with many side effects, or when a pipeline would make the business intent hard to read. Performance optimization should be based on measurement, not on whether a Stream is used.

Before writing a pipeline, identify four things: **the data source**, **the transformation/filtering rules**, **the final result type**, and **constraints on ordering, state, and resources**. This is the foundation for using the Stream API correctly and expanding to custom collectors, parallel processing, or Stream Gatherers later.

**Remember:** The Stream API expresses how to transform data from a source into a result using a pipeline. Its main strength lies in clear operation organization and composability; laziness, single-use lifecycle, and execution contracts are mandatory to understand in order to write correct code.
