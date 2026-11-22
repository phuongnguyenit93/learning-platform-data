# Mapping Zero, One, or Many Results with `mapMulti`

## 1. Why Do We Need `mapMulti` in the Java Stream API?

In the **Filtering and Transforming Elements** chapter of **JAVA_STREAM_API**, we often use `filter` to keep elements matching a condition and `map` to turn each element into a new value. However, there are transformations where **one input element can produce 0, 1, or multiple output elements**:

- A blank line produces **0 keywords**.
- A line with only one valid word produces **1 keyword**.
- A line with multiple valid words produces **multiple keywords**.
- An order line with `quantity = 3` can produce **3 unit item codes**.
- An object that is not of the target type can be skipped; an object of the target type can be converted into one or more values.

Since **Java 16**, `Stream.mapMulti` provides a direct way to express this kind of mapping. Instead of having to return a sub-stream for every element like `flatMap`, the `mapMulti` lambda receives an extra **Consumer**; you send results to the Consumer by calling `accept` **0 to many times**.

~~~text
                   EACH INPUT ELEMENT
                            │
                            ▼
                   mapMulti((x, out) -> ...)
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
          0 accept     1 accept     N accepts
               │            │            │
               ▼            ▼            ▼
              []          [y1]     [y1, y2, ..., yn]
               └────────────┴────────────┘
                            │
                            ▼
                     Output Stream<R>
~~~

The goal of this lesson is to understand the `mapMulti` contract, distinguish it from `map` and `flatMap`, use the primitive-type variants, and apply it safely in **lazy** pipelines chained with `filter`, `reduce`, and `collect`.

## 2. Signature, Parameters, and Contract

Conceptual signature of `Stream<T>.mapMulti`:

~~~java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
);
~~~

The element being processed has type `T`. The `mapper` function takes two arguments:

| Argument | Role |
| --- | --- |
| `T element` | The current input element in the pipeline. |
| `Consumer<R> downstream` | Destination for results of type `R`; call `downstream.accept(value)` to emit one element. |

Example mapping **each odd number to 0 results, and each even number to 2 results**:

~~~java
import java.util.List;

public class MapMultiBasics {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        List<Integer> result = numbers.stream()
            .<Integer>mapMulti((number, out) -> {
                if (number % 2 == 0) {
                    out.accept(number);
                    out.accept(number * 10);
                }
            })
            .toList();

        System.out.println(result); // [2, 20, 4, 40]
    }
}
~~~

Observations:

1. For `1` and `3`, the lambda does not call `accept`, so there are no output elements.
2. For `2`, the lambda calls `accept(2)` then `accept(20)`.
3. For `4`, the lambda calls `accept(4)` then `accept(40)`.
4. `toList()` collects the pipeline's results, preserving the encounter order of the `List` source.

`mapMulti` is an **intermediate operation**: building the pipeline does not run the lambda immediately. Each time an input element is processed, the lambda must emit all results using the supplied Consumer. The lambda **does not return** a value to the Stream (the return type of `BiConsumer.accept` is `void`).

Do not retain the Consumer `out` for use after the callback finishes or pass it to an asynchronous task: the `mapMulti` contract requires using the Consumer within the corresponding mapper invocation.

## 3. Real-World Example: Splitting and Filtering Words Across Lines

Suppose we receive lines of text. Each line may be blank, contain a single long-enough word, or contain multiple words. We want to drop words shorter than 4 characters, normalize to lowercase, and collect the results.

~~~java
import java.util.List;
import java.util.Locale;

public class ExtractWords {
    public static void main(String[] args) {
        List<String> lines = List.of(
            "Java Stream API",
            "   ",
            "mapMulti",
            "filter map reduce"
        );

        List<String> words = lines.stream()
            .<String>mapMulti((line, out) -> {
                if (line.isBlank()) {
                    return; // 0 results
                }

                for (String word : line.strip().split("\\s+")) {
                    if (word.length() >= 4) {
                        out.accept(word.toLowerCase(Locale.ROOT));
                    }
                }
            })
            .toList();

        System.out.println(words);
        // [java, stream, mapmulti, filter, reduce]
    }
}
~~~

Here, the lines produce **2, 0, 1, 2 elements** respectively. We do not have to allocate a temporary `List<String>` for each line and then call `stream()` on that list.

The `return` inside the lambda means **finish processing the current line**; it does not terminate the entire pipeline. Because the lambda has no return value, a blank line is simply represented by **not calling `out.accept`**.

### Workflow Diagram

~~~mermaid
flowchart TD
    A["A line of text"] --> B{"Blank line?"}
    B -->|Yes| C["Emit no elements"]
    B -->|No| D["Split line into words"]
    D --> E{"Word at least 4 chars?"}
    E -->|No| F["Discard current word"]
    E -->|Yes| G["out.accept(normalized word)"]
    G --> H["Element continues down pipeline"]
    F --> I["Check next word"]
    H --> I
~~~

If further filtering is needed, you can continue chaining operations:

~~~java
List<String> distinctWords = lines.stream()
    .<String>mapMulti((line, out) -> {
        for (String word : line.strip().split("\\s+")) {
            if (word.length() >= 4) {
                out.accept(word.toLowerCase(Locale.ROOT));
            }
        }
    })
    .distinct()
    .sorted()
    .toList();

// [filter, java, mapmulti, reduce, stream]
~~~

`distinct()` and `sorted()` are stateful intermediate operations managed by the Stream; they may need to buffer elements and affect performance. The `mapMulti` lambda should remain an independent operation per input element.

## 4. Comparing `map`, `filter`, `flatMap`, and `mapMulti`

| Operation | One input element produces | Common form | Characteristics |
| --- | --- | --- | --- |
| `map` | Exactly **1 element** | `map(x -> transform(x))` | 1-to-1 transformation. |
| `filter` | **0 or 1** of the current element | `filter(x -> predicate(x))` | Keep or discard; does not change element type. |
| `flatMap` | **0 to many** elements | `flatMap(x -> streamOfResults(x))` | Mapper returns a sub-Stream, then Stream flattens it. |
| `mapMulti` | **0 to many** elements | `mapMulti((x, out) -> out.accept(...))` | Mapper emits elements via a Consumer. |

For the even-numbers example in Section 2, the equivalent written with `flatMap`:

~~~java
import java.util.stream.Stream;

List<Integer> result = numbers.stream()
    .flatMap(number -> number % 2 == 0
        ? Stream.of(number, number * 10)
        : Stream.<Integer>empty())
    .toList();

// [2, 20, 4, 40]
~~~

**Key differences:**

- `flatMap` fits when the transformation **naturally returns a Stream**, such as `list.stream()`, `Optional.stream()`, or an API returning `Stream<R>`.
- `mapMulti` fits when you can **directly emit a few results** via `accept`; the author does not need to construct a sub-Stream on every invocation.
- In some cases requiring many small sub-Streams, `mapMulti` **can** reduce allocation overhead and improve performance. Do not assert it is always faster: optimization depends on the JDK, pipeline, and data volume; benchmark if performance is a goal.
- Even though using `mapMulti` avoids manually creating sub-Streams, the API's default implementation may use internal buffering. Therefore, `mapMulti` should not be understood as a guarantee of **zero memory allocation**.

There is no mandatory rule to always choose `mapMulti`. Pick the operation that expresses intent most clearly and measure in practice when optimizing.

## 5. Emitting 0 or 1 Value: Parsing, Validating, and Dropping Bad Data

`mapMulti` can combine transformation and element selection. Suppose only positive integer IDs are accepted; malformed strings or invalid numbers are allowed to be skipped.

~~~java
import java.util.List;

public class ValidIds {
    public static void main(String[] args) {
        List<String> rawIds = List.of(
            "12", "x", " 7 ", "-3", "0", "25"
        );

        List<Integer> validIds = rawIds.stream()
            .<Integer>mapMulti((raw, out) -> {
                try {
                    int value = Integer.parseInt(raw.trim());
                    if (value > 0) {
                        out.accept(value); // Emit exactly 1 valid number.
                    }
                } catch (NumberFormatException ex) {
                    // Invalid input: emit no element.
                }
            })
            .toList();

        System.out.println(validIds); // [12, 7, 25]
    }
}
~~~

The snippet above expresses a policy of **skipping invalid inputs**. In business domains where invalid strings must be reported, logged with a reason, or counted in a data-quality report, do not silently ignore them with `mapMulti`; model both success and error outcomes.

Equivalent using `map` combined with `Optional.stream`:

~~~java
import java.util.Optional;

static Optional<Integer> positiveNumber(String raw) {
    try {
        int value = Integer.parseInt(raw.trim());
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}

// Inside the class containing positiveNumber:
List<Integer> validIds = rawIds.stream()
    .map(YourClass::positiveNumber)
    .flatMap(Optional::stream)
    .toList();
~~~

In the illustration, replace `YourClass` with the actual class name containing `positiveNumber`; `rawIds` is the list from the previous example. Both approaches represent 0–1 results; choose `Optional` if the optional result is also needed elsewhere, or `mapMulti` when you only want to push present values directly down the Stream.

### Note on Type Inference with `mapMulti`

Because the lambda takes a `Consumer<R>` and does not return `R`, Java sometimes **cannot infer a concrete output type**. In particular, when using `var` or chaining further method calls without strong enough target typing, the result may be inferred as `Stream<Object>`.

Specify the type witness when needed:

~~~java
List<Integer> result = List.of("1", "2").stream()
    .<Integer>mapMulti((raw, out) -> out.accept(Integer.parseInt(raw)))
    .toList();

// result has type List<Integer>.
~~~

The `.<Integer>mapMulti(...)` syntax invokes the **generic method `mapMulti` with R = Integer**; this is not a runtime cast.

## 6. Emitting Multiple Results from Nested Data

A list of groups can contain empty groups or multiple elements. `mapMulti` can flatten one level by emitting each element directly:

~~~java
import java.util.List;

List<List<String>> teams = List.of(
    List.of("An", "Bình"),
    List.of(),
    List.of("Chi"),
    List.of("Dung", "Hà")
);

List<String> members = teams.stream()
    .<String>mapMulti((team, out) -> team.forEach(out))
    .toList();

System.out.println(members); // [An, Bình, Chi, Dung, Hà]
~~~

Equivalent with `flatMap`, often shorter when the data already has `stream()`:

~~~java
List<String> members = teams.stream()
    .flatMap(List::stream)
    .toList();
~~~

`mapMulti` is not always clearer. When handling simple nested groups, `flatMap(List::stream)` is usually easier to read; `mapMulti` shines when **a single pass requires conditions, transformations, or emitting multiple elements** without creating intermediate objects.

### Business Example: Expanding Order Lines by Quantity

Each order line has a product code and a quantity. We want a list of product codes per unit to prepare warehouse labels:

~~~java
import java.util.List;

public class ExpandOrderItems {
    record OrderLine(String sku, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 2),
            new OrderLine("PEN", 1),
            new OrderLine("PAD", 0)
        );

        List<String> unitSkus = lines.stream()
            .<String>mapMulti((line, out) -> {
                for (int i = 0; i < line.quantity(); i++) {
                    out.accept(line.sku());
                }
            })
            .toList();

        System.out.println(unitSkus); // [BOOK, BOOK, PEN]
    }
}
~~~

In real systems, validate that `quantity` is non-negative and within a reasonable limit **before expanding data**. If you only want the total quantity, you can use `mapToLong(OrderLine::quantity).sum()` instead of emitting millions of elements. Choosing Streams helps express the problem; it does not replace controlling output size.

## 7. Variants for Primitive Types

`Stream<T>` provides three additional variants when the results are primitives:

| Operation on `Stream<T>` | Consumer inside lambda | Returned Stream |
| --- | --- | --- |
| `mapMultiToInt` | `IntConsumer` | `IntStream` |
| `mapMultiToLong` | `LongConsumer` | `LongStream` |
| `mapMultiToDouble` | `DoubleConsumer` | `DoubleStream` |

Example computing the sum of measurements, where each batch has 0–n `int` values:

~~~java
import java.util.List;

public class SensorSum {
    public static void main(String[] args) {
        List<List<Integer>> batches = List.of(
            List.of(4, 5),
            List.of(),
            List.of(10, 2)
        );

        int sum = batches.stream()
            .mapMultiToInt((batch, out) -> {
                for (int value : batch) {
                    out.accept(value);
                }
            })
            .sum();

        System.out.println(sum); // 21
    }
}
~~~

`mapMultiToInt` produces an `IntStream`, so `sum()` operates directly on `int`, avoiding creating an intermediate `Stream<Integer>` output only to call `mapToInt` later.

With `long` unit prices, you can emit amounts per unit and compute the sum:

~~~java
record Purchase(long unitPrice, int quantity) {}

List<Purchase> purchases = List.of(
    new Purchase(20_000L, 2),
    new Purchase(15_000L, 1)
);

long total = purchases.stream()
    .mapMultiToLong((purchase, out) -> {
        for (int i = 0; i < purchase.quantity(); i++) {
            out.accept(purchase.unitPrice());
        }
    })
    .sum();

System.out.println(total); // 55000
~~~

If you only want the total amount without individual unit entries, `mapToLong(p -> p.unitPrice() * p.quantity()).sum()` is simpler and more efficient. For real monetary values, guard against overflow and enforce rounding rules; the example only illustrates the API and does not replace financial calculation design.

With `double` measurements:

~~~java
List<List<Double>> readings = List.of(
    List.of(1.5, 2.5),
    List.of(),
    List.of(3.0)
);

double total = readings.stream()
    .mapMultiToDouble((batch, out) -> batch.forEach(out::accept))
    .sum();

System.out.println(total); // 7.0
~~~

### Distinguishing from `IntStream.mapMulti`

`Stream<T>.mapMultiToInt` turns a **reference Stream** into an `IntStream`. If the input is already an `IntStream`, use `IntStream.mapMulti` with primitive parameters without converting to `Stream<Integer>`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> doubledPairs = IntStream.rangeClosed(1, 3)
    .mapMulti((number, out) -> {
        out.accept(number);
        out.accept(number * 10);
    })
    .boxed()
    .toList();

System.out.println(doubledPairs); // [1, 10, 2, 20, 3, 30]
~~~

The primitive streams `LongStream` and `DoubleStream` also have corresponding `mapMulti` methods. Depending on the operations needed, choosing the right Stream type helps avoid unnecessary boxing.

## 8. Lazy Pipelines, Ordering, and Parallel Processing

`mapMulti` is a **stateless intermediate operation** under the Stream API contract: the mapping should be independent across elements, must not modify the source being traversed, and must not depend on shared mutable state.

### 8.1. Lambdas Run Only When a Terminal Operation Is Present

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(1, 2, 3).stream()
    .<Integer>mapMulti((n, out) -> {
        System.out.println("Xử lý " + n);
        out.accept(n * 2);
    });

// No terminal operation yet, so elements do not need to be processed yet.
List<Integer> result = pipeline.toList(); // [2, 4, 6]
~~~

The `println` is for **observing execution at runtime**, not a promise that every intermediate operation invokes its callback exactly once for every element. Streams can optimize away steps that do not affect the terminal result or terminate early on short-circuiting terminals. Do not use side effects inside `mapMulti` for mandatory business updates.

### 8.2. Emitting Multiple Values and Encounter Order

With an ordered source such as `List`, a sequential pipeline's output preserves the order of input elements; within a single mapper invocation, values are passed downstream in the order `accept` is called:

~~~java
List<String> output = List.of("A", "B").stream()
    .<String>mapMulti((letter, out) -> {
        out.accept(letter + "1");
        out.accept(letter + "2");
    })
    .toList();

// [A1, A2, B1, B2]
~~~

Do not assume an encounter order from inherently unordered sources. On a parallel stream, `mapMulti` still participates in pipelines with an ordering contract when required by the source and terminal, but **when or which thread calls the mapper** may vary. `forEach` does not guarantee action execution order on a parallel stream.

### 8.3. Short-Circuiting Does Not Guarantee Processing Only the Exact Requested Count

~~~java
List<Integer> firstThree = List.of(1, 2, 3, 4).stream()
    .<Integer>mapMulti((n, out) -> {
        out.accept(n);
        out.accept(n * 100);
    })
    .limit(3)
    .toList();

// [1, 100, 2]
~~~

`limit(3)` only requests **three output elements**, yet it does not guarantee how many input elements `mapMulti` is invoked for or that a loop will stop mid-callback when emitting multiple values. Because a mapper can emit multiple outputs in one call, keep loops inside the mapper bounded and reasonably cheap; do not rely on this mechanism assuming it solves infinite element generation or I/O flow control.

### 8.4. Avoiding Shared Mutable State Across Mappers

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> sideResults = new ArrayList<>();

List<Integer> result = List.of(1, 2, 3).parallelStream()
    .<Integer>mapMulti((n, out) -> {
        sideResults.add(n); // Unsafe when multiple threads write to ArrayList.
        out.accept(n * 2);
    })
    .toList();
~~~

The target value here is `result`; writing to `sideResults` gives the lambda side effects and can cause race conditions. Do not use `synchronizedList` or `AtomicInteger` as a default workaround to force a stateful mapping into the contract; instead, construct results via operations like `collect`, `groupingBy`, or keep state-mutating work outside the pipeline in a controlled step.

**Performance:** `mapMulti` suits 0–n outputs per element, especially when each mapper emits few values. However, if the mapper performs heavy computation, emits huge amounts of data, performs I/O, or contends on state, switching to `parallel()` is not automatically faster. Measure execution time, allocation rate, and memory on representative datasets before optimizing.

## 9. Common Mistakes When Using `mapMulti`

### Mistake 1: Using `mapMulti` Like `map` and Forgetting to Call `accept`

~~~java
List<String> result = List.of("a", "b").stream()
    .<String>mapMulti((value, out) -> {
        value.toUpperCase(); // Emits no results.
    })
    .toList();

// result == []
~~~

To emit a value, you must call `out.accept(value.toUpperCase())`. If you always emit exactly one value, `map(String::toUpperCase)` is usually clearer.

### Mistake 2: Treating `mapMulti` as a Two-Parameter Version of `flatMap`

~~~java
// Wrong idea: mapMulti's mapper does not return a Stream.
// .mapMulti((item, out) -> Stream.of(item, item))

// Correct: emit each value through the Consumer.
List<String> doubled = List.of("a", "b").stream()
    .<String>mapMulti((item, out) -> {
        out.accept(item);
        out.accept(item);
    })
    .toList();

// [a, a, b, b]
~~~

### Mistake 3: Emitting Unchecked Types or `null`

Specify type `R` clearly and only emit valid values for downstream steps. A reference `Stream` can carry `null` in certain operations, but many subsequent operations or methods do not accept it (for example, `findFirst` throws `NullPointerException` if the selected element is `null`). If the goal is to **drop missing data**, check before calling `out.accept`:

~~~java
List<String> results = List.of("alpha", " ", "beta").stream()
    .<String>mapMulti((value, out) -> {
        String cleaned = value.strip();
        if (!cleaned.isEmpty()) {
            out.accept(cleaned);
        }
    })
    .toList();

// [alpha, beta]
~~~

If the source can contain `null`, guard the `strip()` call accordingly. `List.of(...)` does not accept `null` elements, though another collection or external API may supply them.

### Mistake 4: Using `mapMulti` for Stateful Transformations Across Elements

Requirements like sequentially numbering all elements, fixed-size batching, maintaining a sliding window, or updating a shared counter **should not** be implemented by incrementing a mutable variable outside `mapMulti`. That breaks the stateless assumption, is hard to preserve under parallelism, and harms correctness.

Depending on your goal, consider `IntStream.range(...)` for indices, a proper collector, or a dedicated stateful mechanism. **Stream Gatherers** (standard API since Java 24) provide other tools for certain stateful or multi-element transformations, without changing the meaning of `mapMulti`: each mapper processes the current element and emits its corresponding results.

### Mistake 5: Expanding Huge Amounts of Data Just to Compute One Aggregate

~~~java
// No need to expand product quantities into many items just to sum them.
// Use direct calculation:
long totalUnits = lines.stream()
    .mapToLong(OrderLine::quantity)
    .sum();
~~~

The example reuses `OrderLine` and `lines` from Section 6. `mapMulti` solves generating multiple values, while `mapToLong` fits better when the final output is just a sum.

## 10. Practical Criteria for Choosing `mapMulti`

| Problem | Suggested choice | Reason |
| --- | --- | --- |
| One element always becomes one other value | `map` | Concise and accurately expresses a 1–1 transformation. |
| Keep/drop elements without changing type | `filter` | Condition is expressed directly. |
| Mapper already returns a Stream or `List::stream` exists | `flatMap` | Readable when flattening sub-sources. |
| 0–n values emitted via a small loop | `mapMulti` | Avoids manually creating a sub-Stream per input. |
| 0–n primitive values from a reference Stream | `mapMultiToInt/Long/Double` | Convenient for `sum`, `average`, `summaryStatistics`. |
| Need state across multiple elements | Collector, dedicated operation, or suitable Gatherer | Preserves stateful operation contracts. |
| Only need a sum/count instead of expanding results | `mapToLong`, `count`, `sum`, `reduce` | Avoids generating unnecessary elements. |

## 11. Self-Check Questions

1. **How does `mapMulti` differ from `map`?** `map` always produces one result per input; `mapMulti` can produce 0, 1, or more results via `accept` calls.
2. **Why don't you return a Stream in a `mapMulti` lambda?** The mapper receives an output Consumer; each `out.accept(...)` call emits one element into the pipeline.
3. **When is `flatMap` usually clearer than `mapMulti`?** When a method already returns a sub-Stream, such as `List::stream` or `Optional::stream`.
4. **Which operation fits emitting multiple `int` values from a `Stream<Order>`?** `mapMultiToInt`, because the result is an `IntStream`.
5. **Why do we sometimes write `.<String>mapMulti(...)`?** To specify type `R` explicitly when the compiler cannot infer enough type information from the lambda and method chain.
6. **Should you mutate a shared `ArrayList` inside a parallel stream callback?** No; that is unsafe shared mutation and violates the stateless contract.
7. **Does `limit(3)` after `mapMulti` guarantee the mapper processes only three values?** No; the terminal and optimizations may only request a subset of outputs, and a mapper can emit multiple values in a single call.
8. **If you only need the total product quantity, should you replicate SKUs by quantity with `mapMulti`?** Usually no; `mapToLong(...).sum()` expresses it directly and avoids generating intermediate data.

**Takeaway:** `mapMulti` is a **one-input to 0–n outputs** mapping operation in the Java Stream API. Call `out.accept(...)` as many times as needed to emit results, pick primitive variants when appropriate, keep mappers stateless and non-interfering with the source, and use a terminal operation to collect results. Applying these principles keeps pipelines readable while leveraging Stream laziness and optimizations.
