# Comparing `flatMap` and `mapMulti` by Contract and Usage

> **Chapter:** Filtering and Transforming Elements  
> **Module:** JAVA_STREAM_API  
> **Scope:** The Java Stream API supports declarative data processing pipelines, lazy evaluation, `filter`/`map` operations, and aggregation via `reduce`/`collect`. This lesson focuses on two intermediate operations that *transform one input element into zero, one, or many output elements*: `flatMap` and `mapMulti`.

## Learning Objectives

After this lesson, you will be able to:

1. Accurately explain the input/output contract and differences between `map`, `flatMap`, and `mapMulti`.
2. Write two pipelines for the same problem using `flatMap` or `mapMulti`, and explain why they produce the same result.
3. Know that `flatMap` has been available since Java 8, while `mapMulti` and related variants were added in Java 16.
4. Handle cases emitting **0, 1, or many values**, conditional filtering, and nested data.
5. Understand sub-stream creation and closing, the lifecycle of the result `Consumer`, lazy evaluation, and short-circuiting.
6. Handle generic types, primitive streams, encounter order, parallelism, and performance costs that need measurement.

The main examples use Java 17+, as `mapMulti` and `Stream.toList()` require Java 16+. On Java 8–15, use `flatMap` and `collect(Collectors.toList())` according to your JDK version.

## 1. Why Do We Need `flatMap` or `mapMulti`?

`map` turns each input element into exactly **one** output value. If each element itself contains a sublist, `map` normally produces a Stream of lists rather than a Stream of the inner elements.

~~~java
import java.util.List;

List<List<String>> groups = List.of(
        List.of("An", "Bình"),
        List.of("Chi"),
        List.of("Dũng", "Hà")
);

List<List<String>> nested = groups.stream()
        .map(group -> group) // Each sublist remains a single element
        .toList();

System.out.println(nested);
// [[An, Bình], [Chi], [Dũng, Hà]]
~~~

If we need a single list of names in order, we need to **expand/flatten** the data.

~~~text
Source:
    [ ["An", "Bình"], ["Chi"], ["Dũng", "Hà"] ]

map(List::stream):
    Stream<Stream<String>>      (still has nested structure)

flatMap(List::stream):
    Stream<String>              "An", "Bình", "Chi", "Dũng", "Hà"

mapMulti((group, out) -> group.forEach(out)):
    Stream<String>              "An", "Bình", "Chi", "Dũng", "Hà"
~~~

Easy to remember by element cardinality:

| Transformation | One input element produces | Primary function shape |
|---|---|---|
| `map` | One element | `T -> R` |
| `filter` | Keeps or discards the input element | `T -> boolean` |
| `flatMap` | Zero, one, or many elements | `T -> Stream<R>` |
| `mapMulti` | Zero, one, or many elements | `(T, Consumer<R>) -> void` |

Both `flatMap` and `mapMulti` suit **one-to-many** problems, but the way the mapper supplies results differs.

## 2. API Contract: The Most Important Differences

### 2.1. `flatMap` Returns a Sub-Stream

Abbreviated signature on `Stream<T>`:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper
);
~~~

Each time the mapper is invoked with an element `T`, it supplies a **sub-Stream** containing elements of type `R`. The Stream library feeds elements from those sub-Streams into the resulting pipeline. Conceptually:

~~~text
             mapper(T) returns Stream<R>
 T1 ───────────────> [R1, R2]
 T2 ───────────────> []
 T3 ───────────────> [R3]
                         │
                     flatten
                         ▼
                     R1, R2, R3
~~~

Contract points:

- `flatMap` is an **intermediate operation** and is lazy like standard Stream intermediate operations.
- The mapper must be **non-interfering** (does not modify the source being traversed) and **stateless** (does not depend on mutable state while running).
- The mapper can return `Stream.empty()` to emit **zero elements**. By `flatMap`'s contract, if the mapper returns `null`, the result is treated as an empty Stream; however, using `Stream.empty()` expresses intent more clearly.
- **Each sub-Stream is closed** after its elements are placed into the result pipeline per `flatMap`'s contract. This matters if the sub-Stream holds resources such as files.
- Sub-Streams can be built from collections, arrays, `Stream.of(...)`, generator sources, or an appropriate I/O source.

### 2.2. `mapMulti` Emits Values Directly to a Consumer

Abbreviated signature on `Stream<T>`:

~~~java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper
);
~~~

Unlike `flatMap`, `mapMulti`'s mapper **does not return a sub-Stream**. The library calls the mapper with:

1. The input element `T`.
2. A `Consumer<R>` provided by the pipeline, used to **emit** output values.

The mapper calls `downstream.accept(value)` **0, 1, or more times**.

~~~text
             mapper(T, downstream)
 T1 ───────> downstream.accept(R1)
             downstream.accept(R2)

 T2 ───────> (no accept calls)

 T3 ───────> downstream.accept(R3)
                           │
                           ▼
                        R1, R2, R3
~~~

Contract points:

- `mapMulti` is an **intermediate operation**, processing data along the pipeline without creating a new terminal operation.
- The mapper must be **non-interfering** and **stateless**, matching the requirements of standard Stream pipelines.
- The mapper receives a `Consumer` scoped to **that invocation**. By contract, the provided `Consumer` is **only valid within the current mapper call**; do not store it in a field, list, deferred callback, or another thread.
- The mapper does not use its return value to emit results. **Each call to `accept`** submits a candidate value to the rest of the pipeline.
- `mapMulti` does not require the caller to construct a sub-`Stream`, making it convenient when emitting a few values or when expansion logic uses loops and conditions.

In terms of JDK versions, `Stream.mapMulti` was introduced in **Java 16**. `flatMap` has been present since **Java 8**, so JDK compatibility is a clear selection criterion.

### 2.3. Two Syntaxes, One Result

~~~java
import java.util.List;

List<List<String>> groups = List.of(
        List.of("An", "Bình"),
        List.of(),
        List.of("Chi", "Dũng")
);

List<String> withFlatMap = groups.stream()
        .flatMap(List::stream)
        .toList();

List<String> withMapMulti = groups.stream()
        .<String>mapMulti((group, downstream) -> {
            group.forEach(downstream);
        })
        .toList();

System.out.println(withFlatMap);  // [An, Bình, Chi, Dũng]
System.out.println(withMapMulti); // [An, Bình, Chi, Dũng]
~~~

In the `flatMap` approach, each `List` is turned into a sub-Stream via `List::stream`. In the `mapMulti` approach, each element of the sublist is passed to `downstream.accept(...)` (inside `List.forEach`).

The `.<String>mapMulti(...)` notation is a **type witness**, helping Java infer the output type `R` as `String`. This will be explained in detail in Section 7.

## 3. When to Use `map`, `filter`, `flatMap`, or `mapMulti`?

You do not need `flatMap` or `mapMulti` for every transformation.

~~~java
import java.util.List;

List<String> names = List.of(" An ", "", " Bình ", " ");

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();

System.out.println(cleaned); // [An, Bình]
~~~

This is the clearest way to transform each name and filter out empty names. An equivalent `mapMulti` can be written:

~~~java
import java.util.List;

List<String> names = List.of(" An ", "", " Bình ", " ");

List<String> cleaned = names.stream()
        .<String>mapMulti((rawName, out) -> {
            String name = rawName.trim();
            if (!name.isEmpty()) {
                out.accept(name);
            }
        })
        .toList();

System.out.println(cleaned); // [An, Bình]
~~~

This emits **0 or 1** element per input. It is useful when multiple conditions depend on each other or when the transformation can emit multiple results. For the simple case above, `map` + `filter` is usually easier to read.

To understand the difference, do not just look at line count. Ask: **does each element naturally yield a sub-Stream structure, or does it involve step-by-step logic that emits multiple values?**

## 4. Real-World Example: Turning One Order into Multiple Product Lines

Suppose each order contains multiple items. We want to get the SKUs of items with quantity greater than 0, and skip orders with no valid lines.

Data definition:

~~~java
import java.util.List;

record Item(String sku, int quantity) {}
record Order(String id, List<Item> items) {}

List<Order> orders = List.of(
        new Order("O-01", List.of(
                new Item("BOOK", 2),
                new Item("PEN", 0))),
        new Order("O-02", List.of(
                new Item("BAG", 1),
                new Item("PEN", 3))),
        new Order("O-03", List.of())
);
~~~

### 4.1. Solution with `flatMap`

~~~java
import java.util.List;

List<String> skus = orders.stream()
        .flatMap(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .map(Item::sku))
        .toList();

System.out.println(skus); // [BOOK, BAG, PEN]
~~~

The `flatMap` mapper builds a sub-Stream pipeline from the items in **each** order. The sub-Stream is filtered and mapped before results are flattened.

### 4.2. Solution with `mapMulti`

~~~java
import java.util.List;

List<String> skus = orders.stream()
        .<String>mapMulti((order, out) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    out.accept(item.sku());
                }
            }
        })
        .toList();

System.out.println(skus); // [BOOK, BAG, PEN]
~~~

This snippet **avoids creating a sub-Stream object for each order inside the mapper code**. Conditional and emission logic is written explicitly inside the lambda. If an order is empty, the mapper never calls `out.accept`, so that order contributes 0 results.

Both results are equivalent assuming identical inputs and side-effect-free mappers. Which to choose depends on how natural the sub-source is, clarity, JDK compatibility, and runtime performance characteristics.

## 5. Cases of 0, 1, and Many Outputs

### 5.1. Emitting Nothing: Expressing Filtering

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> source = List.of(3, 6, 9, 12);

List<Integer> viaFlatMap = source.stream()
        .flatMap(n -> n % 2 == 0 ? Stream.of(n) : Stream.empty())
        .toList();

List<Integer> viaMapMulti = source.stream()
        .<Integer>mapMulti((n, out) -> {
            if (n % 2 == 0) {
                out.accept(n);
            }
        })
        .toList();

System.out.println(viaFlatMap);  // [6, 12]
System.out.println(viaMapMulti); // [6, 12]
~~~

For logic that only checks a condition, writing `source.stream().filter(n -> n % 2 == 0)` is simpler. This example only illustrates how a mapper **emits no** elements.

### 5.2. Emitting Exactly One Element: Transformation Form

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(1, 2, 3);

List<Integer> viaFlatMap = values.stream()
        .flatMap(n -> Stream.of(n * n))
        .toList();

List<Integer> viaMapMulti = values.stream()
        .<Integer>mapMulti((n, out) -> out.accept(n * n))
        .toList();

System.out.println(viaFlatMap);  // [1, 4, 9]
System.out.println(viaMapMulti); // [1, 4, 9]
~~~

In the **1 input → 1 output** case, `map(n -> n * n)` is clearer than either of these.

### 5.3. Emitting Multiple Elements: Expansion

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> quantities = List.of(1, 3, 2);

// Each number n is repeated n times.
List<Integer> viaFlatMap = quantities.stream()
        .flatMap(n -> IntStream.range(0, n).mapToObj(i -> n))
        .toList();

List<Integer> viaMapMulti = quantities.stream()
        .<Integer>mapMulti((n, out) -> {
            for (int i = 0; i < n; i++) {
                out.accept(n);
            }
        })
        .toList();

System.out.println(viaFlatMap);  // [1, 3, 3, 3, 2, 2]
System.out.println(viaMapMulti); // [1, 3, 3, 3, 2, 2]
~~~

With small expansion counts and simple loops, `mapMulti` is often a concise and direct choice. When the sub-source already exists as a Stream or requires composing operations on the sub-source, `flatMap` is usually more convenient.

## 6. Nested Data, `Optional`, and Hierarchical Structures

### 6.1. Flattening `Optional`

`Optional.stream()` (Java 9+) returns a Stream with 0 elements if `Optional.empty()`, or 1 element if a value is present.

~~~java
import java.util.List;
import java.util.Optional;

List<Optional<Integer>> options = List.of(
        Optional.of(7),
        Optional.empty(),
        Optional.of(11)
);

List<Integer> withFlatMap = options.stream()
        .flatMap(Optional::stream)
        .toList();

List<Integer> withMapMulti = options.stream()
        .<Integer>mapMulti((option, out) -> option.ifPresent(out))
        .toList();

System.out.println(withFlatMap);  // [7, 11]
System.out.println(withMapMulti); // [7, 11]
~~~

This is a very clear comparison: in `flatMap`, `Optional` supplies a sub-Stream; in `mapMulti`, `ifPresent` decides whether to call `accept`.

### 6.2. Multi-Level Nested Structures

Suppose a catalog can contain sub-catalogs or a product code. We want to collect all product codes in *depth-first* traversal order.

~~~java
import java.util.List;
import java.util.function.Consumer;
import java.util.stream.Stream;

class TreeExample {
    static void emitLeaves(Object node, Consumer<String> out) {
        if (node instanceof String text) {
            out.accept(text);
        } else if (node instanceof List<?> children) {
            for (Object child : children) {
                emitLeaves(child, out);
            }
        }
    }

    public static void main(String[] args) {
        List<Object> source = List.of(
                "A",
                List.of("B", List.of("C", "D")),
                "E"
        );

        List<String> leaves = source.stream()
                .<String>mapMulti(TreeExample::emitLeaves)
                .toList();

        System.out.println(leaves); // [A, B, C, D, E]
    }
}
~~~

`emitLeaves` handles recursion: each node can emit 0 or more strings. This pattern works well when the expansion algorithm already follows the **emit results to a Consumer** style.

With `flatMap`, you can write a recursive Stream-producing function and `flatMap` over child nodes. That approach makes sense if you want to maintain the **each node is a result Stream** model. For extremely deep trees, both recursive approaches must account for stack limits; `mapMulti` does not automatically solve stack overflow.

## 7. Generic Type Inference: Why Does `mapMulti` Sometimes Need a Type Witness?

In `flatMap`, the mapper **returns a `Stream<R>`**, so the compiler usually has enough information to infer `R`. In `mapMulti`, the mapper returns `void` and only passes values to a `Consumer<R>`; sometimes Java infers `R` too broadly, such as `Object`.

### 7.1. Safe, Readable Syntax

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            if (n > 1) {
                out.accept(n * 10);
            }
        })
        .toList();

System.out.println(values); // [20, 30]
~~~

`.<Integer>mapMulti(...)` explicitly states the type argument `R`. Without the type witness, the compiler may infer `Stream<Object>`; assigning the `toList()` result to `List<Integer>` will then fail type-checking.

### 7.2. Alternative Approaches

You can assign the result of `mapMulti` to a specifically typed variable before calling `toList()`:

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3)
        .mapMulti((n, out) -> out.accept(n));

List<Integer> values = stream.toList();
System.out.println(values); // [1, 2, 3]
~~~

The `Stream<Integer>` target context helps the compiler determine `R`. In long method chains, a type witness right on `mapMulti` is usually easier to understand.

You can also write the lambda with explicit parameter types matching the functional interface, though types must be declared consistently. Generally, a **type witness** is the most concise and less risky than casting `(Integer) value` at every `accept` call.

### 7.3. Do Not Confuse with the Input Type

In this pipeline:

~~~java
List<String> names = List.of("An", "Bình");

List<Integer> lengths = names.stream()
        .<Integer>mapMulti((name, out) -> out.accept(name.length()))
        .toList();
~~~

`T` is `String` from the source, while `R` is the `Integer` emitted. The type witness on `mapMulti` only specifies the **output** type; it does not change the input type.

## 8. Primitive Variants: Avoiding Boxing When Appropriate

`Stream<T>` has the following variants:

| API | Output | When suitable |
|---|---|---|
| `flatMap(Function<T, Stream<R>>)` | `Stream<R>` | Sub-source is an object Stream |
| `flatMapToInt` / `flatMapToLong` / `flatMapToDouble` | `IntStream` / `LongStream` / `DoubleStream` | Mapper returns a primitive sub-stream |
| `mapMulti(BiConsumer<T, Consumer<R>>)` | `Stream<R>` | Emitting objects directly |
| `mapMultiToInt` / `mapMultiToLong` / `mapMultiToDouble` | Corresponding primitive stream | Emitting integers/floats directly via a primitive consumer |

The signatures in the table are illustrative: actual signatures include generic wildcards `? super` and `? extends`.

### 8.1. Splitting and Summing Numbers in Strings

~~~java
import java.util.Arrays;
import java.util.List;

List<String> lines = List.of("4,7", "3", "2, 6");

int viaFlatMap = lines.stream()
        .flatMapToInt(line -> Arrays.stream(line.split(","))
                .map(String::trim)
                .filter(part -> !part.isEmpty())
                .mapToInt(Integer::parseInt))
        .sum();

int viaMapMulti = lines.stream()
        .mapMultiToInt((line, out) -> {
            for (String part : line.split(",")) {
                String token = part.trim();
                if (!token.isEmpty()) {
                    out.accept(Integer.parseInt(token));
                }
            }
        })
        .sum();

System.out.println(viaFlatMap);  // 22
System.out.println(viaMapMulti); // 22
~~~

These are two ways to produce an `IntStream` from a `Stream<String>`, then apply the `sum()` terminal operation.

The data assumes every non-empty token is a valid integer; `Integer.parseInt` can throw `NumberFormatException` if a token is malformed or out of `int` range. With external data, define an explicit policy: reject the record, log the error, or allow skipping. Do not silently swallow errors unless that is a business requirement.

### 8.2. `IntStream.mapMulti`

Primitive streams also have their own `mapMulti` operation. For example, `IntStream.mapMulti(IntStream.IntMapMultiConsumer)` emits multiple `int` values:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] expanded = IntStream.of(1, 3, 2)
        .mapMulti((value, out) -> {
            for (int i = 0; i < value; i++) {
                out.accept(value);
            }
        })
        .toArray();

System.out.println(Arrays.toString(expanded));
// [1, 3, 3, 3, 2, 2]
~~~

This is `IntStream.mapMulti`, **different from** `Stream<T>.mapMultiToInt`:

- `Stream<T>.mapMultiToInt`: source contains objects `T`, result is `IntStream`.
- `IntStream.mapMulti`: source is already `IntStream`, result remains `IntStream`.

When processing large volumes of numbers, avoiding boxing/unboxing can help. Still, do not assume one variant is always faster without measuring in the real context.

## 9. Resources and Sub-Stream Lifecycle

Lifecycle differences are a key reason for choosing an API.

### 9.1. `flatMap` Has a Sub-Stream Closing Contract

When `flatMap` receives a sub-Stream from the mapper, the Stream API is responsible for closing that sub-Stream per `flatMap`'s contract once its contents have been processed.

Example: combining multiple text files into one pipeline:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

List<Path> paths = List.of(
        Path.of("application-1.log"),
        Path.of("application-2.log")
);

try (Stream<String> allLines = paths.stream()
        .flatMap(path -> {
            try {
                return Files.lines(path, StandardCharsets.UTF_8);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })) {

    long errors = allLines
            .filter(line -> line.contains("ERROR"))
            .count();

    System.out.println("Số dòng ERROR: " + errors);
} catch (UncheckedIOException ex) {
    System.err.println("Đọc log thất bại: " + ex.getMessage());
}
~~~

Notes:

1. `Files.lines` returns a Stream reading from a file and holding resources that must be closed.
2. `flatMap` flattens the sub-Streams and is responsible for closing them under its contract.
3. `try-with-resources` closes the **resulting Stream** when leaving scope, which is especially important if the pipeline itself owns resources or has close handlers.
4. `IOException` when opening a file is wrapped into `UncheckedIOException` to cross the lambda boundary; I/O errors while consuming the Stream can also arise as `UncheckedIOException`.
5. Even though `count()` is a terminal operation, **do not assume terminal operations automatically close the outer Stream**. Actively manage lifecycle for I/O-backed Streams.

Do not take this example as a reason to open arbitrarily many files concurrently: in a sequential pipeline, sub-Streams can be opened and processed one by one; in a parallel pipeline, resource usage must be evaluated in practice.

### 9.2. `mapMulti` Has No Sub-Stream to Close Automatically

`mapMulti` only supplies a `Consumer` to emit values. If you open a `Reader`, connection, or I/O `Stream` inside the mapper, **the mapper code itself must manage that resource**; there is no returned sub-Stream for `mapMulti` to apply `flatMap`'s closing contract to.

Illustrative code — **only** appropriate when intentionally reading the entire sub-source per mapper invocation:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

List<Path> files = List.of(Path.of("application-1.log"));

List<String> nonBlankLines = files.stream()
        .<String>mapMulti((path, out) -> {
            try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (!line.isBlank()) {
                        out.accept(line);
                    }
                }
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();
~~~

Here `try-with-resources` closes `reader`, yet the manual read loop inside the mapper may keep reading the entire file even when downstream already has enough results to stop early. If you need an on-demand line-processing pipeline with `limit` or `findFirst`, **`flatMap` returning a sub-Stream from `Files.lines` is usually more natural**. This leads to the next difference.

## 10. Lazy Evaluation and Short-Circuiting: What Is Not Guaranteed?

Both `flatMap` and `mapMulti` are lazy at the **intermediate operation** level: calling them to build a pipeline does not automatically process the whole source. When a terminal operation such as `toList`, `count`, `findFirst`, or `anyMatch` starts, the library consumes the pipeline on demand and applies valid optimizations.

With `flatMap`, the mapper supplies a sub-Stream capable of element-by-element traversal. A pipeline with `limit(2)` may not need to pull every element from the sub-Stream.

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<String> firstTwo = Stream.of("x")
        .flatMap(prefix ->
                IntStream.range(0, 1_000)
                        .mapToObj(i -> prefix + i))
        .limit(2)
        .toList();

System.out.println(firstTwo); // [x0, x1]
~~~

With `mapMulti`, the mapper receives a `Consumer` with an `accept` method, but **there is no standard stop signal** for the mapper to ask downstream whether more elements are still needed.

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> firstTwo = Stream.of("x")
        .<String>mapMulti((prefix, out) -> {
            for (int i = 0; i < 1_000; i++) {
                out.accept(prefix + i);
            }
        })
        .limit(2)
        .toList();

System.out.println(firstTwo); // [x0, x1]
~~~

The final output still has two elements, yet **do not infer that the mapper only ran two loop iterations**: the mapper may emit more values than downstream consumes, and `mapMulti`'s default implementation may buffer results internally.

Design consequences:

- For **small, finite** expansions, `mapMulti` fits very well.
- For **very large, lazily computed, or infinite** sub-sources, `flatMap` with a lazy sub-Stream generally takes better advantage of short-circuiting.
- Do not place an infinite loop inside a `mapMulti` mapper expecting `limit` to break the inner loop; the mapper has no cancellation API on `Consumer`.
- Do not write business logic depending on how many times an intermediate lambda was invoked: the Stream API is permitted to optimize execution while preserving specified results.

## 11. Element Order, Parallelism, and Side Effects

### 11.1. Encounter Order

If the source has an **encounter order** (such as `List.stream()`) and the pipeline does not discard order via `unordered()`, both `flatMap` and `mapMulti` preserve element encounter order along with emission order within each input.

~~~java
import java.util.List;

List<String> rows = List.of("A,B", "C,D");

List<String> tokens = rows.stream()
        .<String>mapMulti((row, out) -> {
            for (String token : row.split(",")) {
                out.accept(token);
            }
        })
        .toList();

System.out.println(tokens); // [A, B, C, D]
~~~

Not all sources have an encounter order: for example, a `HashSet` guarantees no specific traversal order. `forEach` on a parallel Stream also does not guarantee execution order; if output order is truly required when performing side effects, consider `forEachOrdered` and its performance impact.

### 11.2. Parallel Streams Do Not Change Behavioral Contracts

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(
        List.of(1, 2),
        List.of(3),
        List.of(4, 5)
);

List<Integer> result = groups.parallelStream()
        .<Integer>mapMulti((group, out) -> {
            for (int number : group) {
                out.accept(number * 10);
            }
        })
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
~~~

This is an independent transformation of each group. The pipeline has an ordered source and `toList()` preserves encounter order. However, the **execution** order of lambdas across threads may differ from the **result** order.

A common mistake is pushing results into a shared collection:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

// Not recommended: multiple threads may mutate ArrayList concurrently.
// groups.parallelStream().forEach(group -> shared.addAll(group));
~~~

A regular `ArrayList` is not thread-safe. Replace it with `flatMap` or `mapMulti` to build the result pipeline, then use `toList` or an appropriate collector.

Do not retain `out` in `mapMulti` to invoke it on another thread:

~~~java
// Violates mapMulti's contract:
// Stream.of(1, 2).<Integer>mapMulti((n, out) -> {
//     new Thread(() -> out.accept(n)).start();
// });
~~~

The `Consumer` supplied by `mapMulti` may only be used **within that mapper invocation itself**, never handed off to asynchronous work running after the mapper returns.

### 11.3. Counting and Aggregating with Terminal Operations

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(
        List.of(2, 4),
        List.of(1, 3, 5)
);

int sum = groups.stream()
        .flatMap(List::stream)
        .mapToInt(Integer::intValue)
        .sum();

long count = groups.stream()
        .<Integer>mapMulti((group, out) -> group.forEach(out))
        .count();

System.out.println(sum);   // 15
System.out.println(count); // 5
~~~

Aggregations should be handled by `sum`, `count`, `reduce`, or `collect` rather than mutating a shared accumulator variable from inside a mapper. This is especially important with parallel streams and pipelines with short-circuiting.

## 12. Performance: Is `mapMulti` Always Faster Than `flatMap`?

**There is no general guarantee** that `mapMulti` is always faster than `flatMap`. The API documentation describes `mapMulti` as a useful alternative when each input produces a **small** number of elements, avoiding creating a new Stream inside the mapper per input and suiting push-based emission algorithms.

However, distinguish **API intent** from **implementation**:

- `flatMap` directly expresses processing sub-Streams, incurring construction and management overhead depending on the pipeline and JDK optimizations.
- `mapMulti` does not force mapper code to allocate sub-Streams, yet **the contract does not promise zero memory allocation or no buffering**. The default implementation described in the Javadoc may collect emitted values into an internal buffer and then execute `flatMap`.
- Pipeline-level laziness **does not guarantee** every expansion produces results on the fly without buffering.
- When emitting huge numbers of outputs from one element, buffering/memory costs and early-termination capability can matter more than avoiding sub-Stream allocation.
- When using primitive streams, boxing/unboxing, string parsing, object allocation, or I/O operations may dominate total runtime far more than the difference between `flatMap` and `mapMulti`.
- In parallel runs, efficiency also depends on whether the source splits well (related to `Spliterator`), thread coordination overhead, associativity of reductions, and resource contention.

| Workload pattern | What to observe when benchmarking |
|---|---|
| Many inputs, each emitting 0–2 elements | Sub-Stream creation cost, allocation, GC |
| Many inputs, each emitting thousands of elements | Buffer memory, incremental consumption capability |
| `limit` or `findFirst` present | How much work on sub-sources can be avoided? |
| Processing large volumes of `int` or `long` | Primitive streams and boxing/unboxing |
| Reading files or network data | I/O, number of open resources, resource closing |
| `parallel()` / `parallelStream()` | Problem size, `Spliterator` splitting, ordering, overhead |

If you need performance conclusions for an application, measure with real data and your target JDK, using proper warm-up/JMH, consuming outputs to prevent dead-code elimination, and tracking allocations or GC. **Choose the API first by contract and clarity**, then optimize based on measurements.

## 13. Common Mistakes and Fixes

### Mistake 1: Assuming `map` Flattens Elements

~~~java
import java.util.List;

List<List<Integer>> groups = List.of(List.of(1, 2), List.of(3));

var nested = groups.stream()
        .map(List::stream)
        .toList(); // List<Stream<Integer>>, not yet List<Integer>
~~~

Fix with `flatMap(List::stream)` or `.<Integer>mapMulti((group, out) -> group.forEach(out))`.

### Mistake 2: Trying to Return a Stream from `mapMulti`'s Mapper

~~~java
// Wrong signature: mapMulti expects a BiConsumer, which returns void.
// groups.stream().mapMulti(group -> group.stream());
~~~

`mapMulti` takes **two parameters** in its lambda: the input element and the output `Consumer`. If you need to return a sub-Stream, use `flatMap`.

### Mistake 3: Not Pinning the Output Type When Generic Inference Is Insufficient

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> result = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> out.accept(n))
        .toList();
~~~

The type witness `<Integer>` fixes `R` for `mapMulti` and avoids `List<Object>` errors in certain inference contexts.

### Mistake 4: Retaining the Downstream `Consumer`

~~~java
// Contract violation:
// Consumer<Integer>[] holder = ...
// stream.<Integer>mapMulti((n, out) -> holder[0] = out);
// holder[0].accept(10); // Used outside the mapper invocation
~~~

Fix by calling `accept` **directly inside the mapper**, or choose another asynchronous mechanism with its own lifecycle contract. Never treat this `Consumer` as a callback to be invoked later.

### Mistake 5: Thinking `mapMulti` Auto-Closes Resources Opened in the Mapper

If the mapper opens a `Reader` or sub-Stream without closing it, `mapMulti` has no way to know what to release. Use `try-with-resources` inside the mapper, or switch to `flatMap` when returning a sub-Stream so its closing contract applies.

### Mistake 6: Relying on Mapper Side Effects

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger calls = new AtomicInteger();

long count = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            calls.incrementAndGet(); // Do not use to drive business logic
            out.accept(n);
        })
        .count();
~~~

In this specific pipeline, `count` returns `3` and the mapper actually needs to emit values to determine output count. However, `calls` is an unnecessary **side effect**: changing the pipeline to a short-circuiting operation or parallel execution can alter call counts and order from what the author assumed. Other pipelines may also be optimized by the Stream API without invoking some intermediate functions. Use the **terminal operation result**—here `count`—instead of side-effect counters in business logic.

### Mistake 7: Using `mapMulti` for an Infinite Sub-Source and Expecting `limit` to Break the Mapper

~~~java
// Dangerous: this loop has no natural termination point.
// Stream.of("x").<String>mapMulti((x, out) -> {
//     for (;;) {
//         out.accept(x);
//     }
// }).limit(1).toList();
~~~

`limit(1)` is **downstream**, not a cancellation signal propagated back as a boolean to loops inside the mapper. If the sub-source is infinite or huge, prefer a lazy Stream model like `flatMap` with an appropriate sub-Stream and a bounded terminal operation.

## 14. API Selection Decision Table

| Need | Preferred reference | Reason |
|---|---|---|
| One input → exactly one result | `map` | Concise, matches contract |
| Only keep/drop elements | `filter` | Expresses predicate directly |
| Flatten `List<List<T>>` or `Stream<Stream<T>>` | `flatMap` | Sub-source is already naturally a Stream |
| Each element emits 0–few values via loop/conditions | `mapMulti` (Java 16+) | Mapper emits values directly without creating sub-Streams |
| Have `Optional<T>` | `flatMap(Optional::stream)` or `mapMulti(...ifPresent...)` | Both express 0/1 values |
| Sub-source needs effective lazy/short-circuit handling | Usually prefer `flatMap` | Sub-Stream allows incremental traversal; consider resources |
| Sub-Stream tied to I/O | Usually prefer `flatMap` plus outer lifecycle management | `flatMap` contract closes sub-Streams |
| Primitive integer/floating-point output | `flatMapToInt`, `mapMultiToInt`, `IntStream.mapMulti`... | Avoids boxing when beneficial |
| Must run on Java 8–15 | `flatMap` | `mapMulti` does not exist in these JDKs |
| Expected to run in parallel | Whichever API is clearer, with stateless/non-interfering functions | Avoid shared state, measure real performance |

When answering "Does `mapMulti` completely replace `flatMap`?", the answer is **no**. Both can express the same 0–N transformation at the value level, but `flatMap` models **returning a sub-Stream** with sub-Stream lifecycle and natural incremental traversal; `mapMulti` models **emitting values during mapper invocation**, suited for small, finite direct expansions.

## 15. Reinforcement Exercises (with Answers)

### Exercise 1. Predict the Output

~~~java
import java.util.List;

List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(),
        List.of(3)
);

List<Integer> result = batches.stream()
        .<Integer>mapMulti((batch, out) -> batch.forEach(out))
        .toList();

System.out.println(result);
~~~

**Answer:** `[1, 2, 3]`. The empty batch makes no `accept` calls; the remaining batches emit elements in order.

### Exercise 2. Convert `flatMap` to `mapMulti`

Original snippet:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> source = List.of("A", "BC", "D");

List<Character> letters = source.stream()
        .flatMap(s -> s.chars().mapToObj(c -> (char) c))
        .toList();
~~~

**Reference answer:**

~~~java
List<Character> letters = source.stream()
        .<Character>mapMulti((s, out) -> {
            for (int i = 0; i < s.length(); i++) {
                out.accept(s.charAt(i));
            }
        })
        .toList();

System.out.println(letters); // [A, B, C, D]
~~~

In this example, all characters are in BMP/ASCII so `charAt` gives the expected result. For Unicode outside the BMP, a `char` may only hold half of a surrogate pair; if code points are needed, use `String.codePoints()` and work with `int`.

### Exercise 3. When Is `flatMap` More Natural?

**Prompt:** You have a `List<Path>`, each file can contain millions of lines, and you only need the first 10 lines matching a condition. Which API would you prefer?

**Answer:** Usually prefer `flatMap(path -> Files.lines(path))` combined with `filter` and `limit(10)`, handling exceptions and I/O lifecycle properly. Because sub-Streams supply lines lazily, the pipeline has a chance to stop early. Avoid writing `mapMulti` with a `while(reader.readLine())` loop scanning each entire file when downstream only needs a few lines.

### Exercise 4. Explain the Type Witness

~~~java
List<Integer> result = Stream.of(1, 2, 3)
        .<Integer>mapMulti((n, out) -> {
            if (n > 1) out.accept(n);
        })
        .toList();
~~~

**Answer:** `<Integer>` fixes the output type `R` of `mapMulti`. Because the mapper does not return `Stream<R>` and instead emits via `Consumer<R>`, the compiler sometimes needs extra context to infer `R`.

### Exercise 5. Emit Multiple Elements Without a Sub-Stream

**Prompt:** From `List.of("x:1", "y:2", "z:3")`, extract the value after the colon as a `List<String>` using `mapMulti`.

**Reference answer:**

~~~java
import java.util.List;

List<String> source = List.of("x:1", "y:2", "z:3");

List<String> values = source.stream()
        .<String>mapMulti((record, out) -> {
            int separator = record.indexOf(':');
            if (separator >= 0 && separator + 1 < record.length()) {
                out.accept(record.substring(separator + 1));
            }
        })
        .toList();

System.out.println(values); // [1, 2, 3]
~~~

This is a **0 or 1 result** example. In production code, if the input is guaranteed well-formed with a single value, `map` combined with validation can also be clearer.

### Exercise 6. Identify Risks with Parallel Streams

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();

List<List<Integer>> batches = List.of(
        List.of(1, 2),
        List.of(3, 4)
);

// Not recommended:
// batches.parallelStream()
//         .forEach(batch -> shared.addAll(batch));
~~~

**Answer:** Writing to a shared `ArrayList` from multiple threads is unsafe and can lose data or throw errors. Replace with:

~~~java
List<Integer> result = batches.parallelStream()
        .flatMap(List::stream)
        .toList();

System.out.println(result); // [1, 2, 3, 4]
~~~

Because the source has an encounter order and `toList()` preserves order, the output follows encounter order even though processing may happen in parallel.

---

**Takeaway:** `flatMap` requires the mapper to return **a sub-Stream for each input element**; `mapMulti` requires the mapper to **emit 0–N values directly to a Consumer within the scope of the call**. Use `flatMap` when the sub-source is naturally a Stream, needs lazy evaluation, or holds resources that must be closed; consider `mapMulti` on Java 16+ when an element emits only a few values via conditions and loops. For both, keep mappers stateless/non-interfering, specify output types clearly, and measure performance before optimizing.

