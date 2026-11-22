# `mapMulti()`: Transforming One Element into Zero, One, or Many Elements in Java Stream

In Java Stream, `map()` transforms **each input element into exactly one result**, whereas `flatMap()` transforms each element into a stream of results and then concatenates the streams. Since **Java 16**, `Stream.mapMulti()` provides another way to express this: for each element, the lambda can **emit 0, 1, or many results** through a provided `Consumer`.

As a result, you can filter and transform at the same time, flatten multi-level data, or discard unsuitable values without having to create an intermediate `Stream` for each element. The focus of this article is the contract of `mapMulti()`, data types, result ordering, how to write the lambda correctly, and when to choose `flatMap()`.

## 1. Thinking About the Number of Results

For the same input element `x`:

| Operation | What does the lambda receive and return? | Number of output elements per `x` |
| --- | --- | --- |
| `map(f)` | `Function<T,R>`: returns **one `R`** | Exactly 1 (even if that value is `null`) |
| `filter(p)` | `Predicate<T>`: decides whether to keep or discard `T` itself | 0 or 1, without changing the element type |
| `flatMap(f)` | `Function<T,Stream<R>>`: returns a stream that is then flattened | 0, 1, or many |
| `mapMulti(mapper)` | `BiConsumer<T,Consumer<R>>`: calls `accept(result)` for each result to emit | 0, 1, or many |

A `mapMulti()` callback is invoked with **two arguments**: the source element and the "output" (`downstream`, `emit`, or `out`, depending on the name chosen by the author). This output has an `accept(R)` method. As many times as you call `accept`, that many results are produced for that source element.

```text
Source:              -2       0        3          5
                         |       |        |          |
mapMulti:            (skip)  emit(0)  emit(3,9)  emit(5,25)
                         |       |        |          |
Result:                        [0,       3, 9,     5, 25]
                         0 results   1       2          2
```

This is a logical illustration, not a thread scheduling diagram. `mapMulti()` is a **lazy intermediate operation**: the callback is only evaluated when a terminal operation (such as `toList()`, `count()`, `sum()`) consumes the pipeline, and optimizations may affect the number of invocations in specific pipelines.

## 2. Signature and Lifecycle of `downstream`

General signature on `Stream<T>`:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

This is an abbreviated API signature from `java.util.stream.Stream`, **not a standalone Java program**. Meaning:

- `T`: the existing element type of the stream.
- `R`: the desired output element type.
- `mapper`: receives a `T` and a `Consumer<R>`.
- `downstream.accept(r)`: pushes an `R` value into the result stream; calling it 0 times drops the element, calling it 1 time performs a one-to-one mapping, and calling it multiple times expands it.
- `mapper` itself returns `void`. A `return;` inside the lambda only **ends the processing of the current element**, not returning a stream or an element.

`downstream` is a callback provided by the Stream during the processing turn. According to the API contract, results must be emitted **while the lambda is being invoked**. **Do not store `downstream` in a field/list to call later**, and do not pass it to an asynchronous task and return immediately; that lifecycle is not supported and may cause incorrect behavior.

Basic pattern:

```java
Stream<Integer> source = Stream.of(-1, 0, 3);
List<Integer> result = source.<Integer>mapMulti((n, out) -> {
    if (n < 0) {
        return;             // Emit 0 results for -1.
    }

    out.accept(n);          // Emit at least 1 result.
    if (n > 0) {
        out.accept(n * n);  // Emit an additional result.
    }
}).toList();
// result == [0, 3, 9]
```

This illustrative snippet is placed inside a method and requires `import java.util.List;` and `import java.util.stream.Stream;`. At `n = -1`, `out.accept` is not called; `n = 0` emits exactly one result; `n = 3` emits two results, `3` and `9`.

## 3. Complete Runnable Java 17+ Example

Save as `MapMultiDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class MapMultiDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(-2, 0, 3, 5);

        List<Integer> expanded = numbers.stream()
                .<Integer>mapMulti((n, out) -> {
                    if (n < 0) {
                        return;            // 0 results.
                    }
                    out.accept(n);        // 1 result.
                    if (n % 2 != 0) {
                        out.accept(n * n); // 1 more result.
                    }
                })
                .toList();
        System.out.println("expanded = " + expanded);

        List<String> lines = List.of(" Java 17 ", "", "map multi");

        List<String> words = lines.stream()
                .<String>mapMulti((line, out) -> {
                    for (String word : line.trim().split("\\s+")) {
                        if (!word.isBlank()) {
                            out.accept(word.toLowerCase(Locale.ROOT));
                        }
                    }
                })
                .toList();
        System.out.println("words = " + words);

        List<Object> mixed = List.of("text", 12, 3.5, 7, true);
        List<Integer> integers = mixed.stream()
                .<Integer>mapMulti((value, out) -> {
                    if (value instanceof Integer n) {
                        out.accept(n);
                    }
                })
                .toList();
        System.out.println("integers = " + integers);

        int sum = Stream.of("2,3", "7", "")
                .mapMultiToInt((field, out) -> {
                    if (field.isBlank()) {
                        return;
                    }
                    for (String token : field.split(",")) {
                        out.accept(Integer.parseInt(token));
                    }
                })
                .sum();
        System.out.println("sum = " + sum);
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 MapMultiDemo.java
java MapMultiDemo
```

Expected stdout:

```text
expanded = [0, 3, 9, 5, 25]
words = [java, 17, map, multi]
integers = [12, 7]
sum = 12
```

Step-by-step explanation:

1. Sequence `[-2, 0, 3, 5]`: `-2` emits nothing; `0` emits `0`; `3` emits `3` and `9`; `5` emits `5` and `25`.
2. For each line of text, the `for` loop splits words by whitespace; blank lines emit no values. Each valid word is converted to lowercase and emitted. Because the source is an ordered `List` and the `accept` calls are also ordered, the result is `[java, 17, map, multi]`.
3. `instanceof Integer n` uses *pattern matching for instanceof* (supported since Java 16). Elements of types other than `Integer` are skipped; `mapMulti()` simultaneously **filters by type** and **transforms to `Stream<Integer>`**.
4. `mapMultiToInt` emits primitive integers directly into an `IntStream`; `sum()` computes the sum `2 + 3 + 7 = 12`. No boxing to `Integer` is needed to compute the sum.

The example does not use side effects in the mapper: the lambdas only transform input data into emitted values. `System.out.println` is executed **after** the stream has produced the results.

## 4. Distinguishing `map()`, `filter()`, `flatMap()`, and `mapMulti()`

### `map()`: One Input to Exactly One Output

```java
List<String> result = List.of("a", "bb").stream()
        .map(String::toUpperCase)
        .toList();
// [A, BB]
```

`map()` is appropriate when every element produces **one result**. There is no need to use `mapMulti()` just to uppercase each string: doing so would make the code harder to read.

### `filter().map()`: Filter Then Map

```java
List<Integer> result = List.of(-1, 2, -3, 4).stream()
        .filter(n -> n > 0)
        .map(n -> n * 10)
        .toList();
// [20, 40]
```

For a simple filtering condition, `filter().map()` is usually the clearest. It can be written with `mapMulti()`, though it is not necessary:

```java
List<Integer> result = List.of(-1, 2, -3, 4).stream()
        .<Integer>mapMulti((n, out) -> {
            if (n > 0) {
                out.accept(n * 10);
            }
        })
        .toList();
// [20, 40]
```

The illustrative snippets in this section require `import java.util.List;` and must be placed inside a method; they are not standalone Java programs.

### `flatMap()`: Create Sub-streams Then Flatten

```java
List<String> result = List.of(
        List.of("a", "b"),
        List.of(),
        List.of("c")
).stream()
        .flatMap(List::stream)
        .toList();
// [a, b, c]
```

`flatMap` takes a function that returns a `Stream<R>` for each element. It is suitable when you already have sub-streams or APIs that naturally return a `Stream`, or when you want to express a complex transformation using independent sub-pipelines.

The same problem with `mapMulti`:

```java
List<String> result = List.of(
        List.of("a", "b"),
        List.of(),
        List.of("c")
).stream()
        .<String>mapMulti((group, out) -> group.forEach(out))
        .toList();
// [a, b, c]
```

For each `group`, the mapper iterates through the elements and emits them directly. There is no need to call `group.stream()` to create a sub-stream for each group. However, **do not claim that `mapMulti` is always faster than `flatMap`**: any benefit depends on the JDK, the source implementation, the data size, subsequent operations, and JVM optimizations. Only benchmark when performance truly matters.

### When Should You Prefer `mapMulti()`?

- Each input has **0 or a few results** and emitting results fits naturally in a `for` loop or conditional statement.
- You need to combine an `instanceof` type check with emitting the right output type.
- You want to expand an element into multiple values without having to represent a sub-`Stream` for each input.
- You need a primitive variant like `mapMultiToInt` to avoid boxing when creating an `IntStream`.

If the conditions become too tangled or the callback emits a very large number of results from a single element, consider extracting the logic into a separate method or using `flatMap()` to keep the code structure easy to understand.

## 5. Paying Attention to Java Type Inference

Unlike `map`, which returns an `R` value that the compiler can see directly, `mapMulti` takes a callback used to **push values out**. In some forms, especially when chained directly with `toList()`, Java may infer `R` as `Object` instead of the desired type.

This is a clear and reliable way:

```java
List<String> names = List.of("An", "", "Chi").stream()
        .<String>mapMulti((name, out) -> {
            if (!name.isBlank()) {
                out.accept(name);
            }
        })
        .toList();
// [An, Chi]
```

The expression `.<String>mapMulti(...)` is a **type witness**: it requires the output element type `R` to be `String`. If the callback emits an `Integer`, the compiler will report a type mismatch, as expected.

Another approach is to write the lambda with explicit parameter types, for example:

```java
Stream<Integer> stream = Stream.of(1, -1, 3)
        .mapMulti((Integer n, java.util.function.Consumer<Integer> out) -> {
            if (n > 0) {
                out.accept(n);
            }
        });
```

This is an illustrative snippet that requires `import java.util.stream.Stream;`. With `BiConsumer`, if you declare an explicit type for one lambda parameter, you must also declare it for the other parameter. Usually, using `.<Integer>mapMulti(...)` is shorter and easier to read.

## 6. Primitive Specializations: Avoiding Boxing When Possible

In addition to `Stream<T>.mapMulti(...)`, the Stream API supports creating primitive streams:

| API called from `Stream<T>` | Mapper receives | Result |
| --- | --- | --- |
| `mapMultiToInt` | `T` and `IntConsumer` | `IntStream` |
| `mapMultiToLong` | `T` and `LongConsumer` | `LongStream` |
| `mapMultiToDouble` | `T` and `DoubleConsumer` | `DoubleStream` |

Primitive streams also have related APIs. For example, `IntStream.mapMulti(IntStream.IntMapMultiConsumer)` receives an `int` and an `IntConsumer`, emitting 0, 1, or many `int` values.

Example:

```java
int[] values = java.util.stream.IntStream.of(2, -1, 4)
        .mapMulti((n, out) -> {
            if (n > 0) {
                out.accept(n);
                out.accept(n * 2);
            }
        })
        .toArray();
// [2, 4, 4, 8]
```

This is an illustrative snippet inside a method. Negative values are dropped; positive numbers emit themselves and their double. The `IntStream.mapMulti` version uses a specialized mapper, **not** the generic `BiConsumer<T,Consumer<R>>`.

For aggregations such as `sum()`, `average()`, and `max()`, `mapMultiToInt` and the primitive stream types help avoid part of the boxing/unboxing overhead compared to `Stream<Integer>`.

## 7. Result Ordering, Parallel Streams, and Side Effects

If the source has an encounter order (such as `List.stream()`) and each mapper emits results sequentially via `out.accept`, the results are viewed in logical order: **the order of the source elements, followed by the emission order of each element's results**.

```java
List<String> result = List.of("A", "B").parallelStream()
        .<String>mapMulti((value, out) -> {
            out.accept(value + "1");
            out.accept(value + "2");
        })
        .toList();
// [A1, A2, B1, B2]
```

This is an illustrative snippet that requires `java.util.List`. `parallelStream` may invoke the mapper on different threads and execution schedules, but `toList()` on an ordered stream still preserves encounter order. That does **not** mean the mapper invocations execute in A-then-B order in real time.

Guidelines for callbacks:

- **Non-interfering:** do not modify the stream source while it is being traversed, for example, do not call `list.add(...)` from the mapper on the source list itself.
- **Stateless:** do not rely on shared mutable state between callback invocations, especially in parallel streams.
- Do not call `out.accept` from a background thread after the mapper has returned; emitting results must stay within the callback's lifecycle.
- Do not rely on the number of times the mapper runs to perform mandatory actions (writing to a DB, sending emails, incrementing business counters). Stream operations can short-circuit or optimize traversal.
- If a mapper throws an exception, the terminal operation may terminate with an error. Streams do not roll back side effects that already occurred in earlier callbacks.

If you need to write results to an external system, it is usually better to **transform the data first** and let an orchestration layer handle I/O and errors with an explicit policy, rather than mixing I/O into `mapMulti`.

## 8. Notes on `null`, Empty Collections, and Data Errors

`mapMulti` allows dropping an element by **not calling `accept`**. This is often a clean way to filter out `null` or invalid values:

```java
List<String> result = Stream.of("A", null, "B")
        .<String>mapMulti((s, out) -> {
            if (s != null) {
                out.accept(s.toLowerCase(java.util.Locale.ROOT));
            }
        })
        .toList();
// [a, b]
```

This is an illustrative snippet that requires `import java.util.List;` and `import java.util.stream.Stream;`. Do not use `List.of("A", null, "B")` because `List.of` **does not allow null elements**.

Technically, an object `Stream` can contain `null`, and some terminal operations accept null elements; however, this depends on the downstream operation. For example, `findFirst` or `findAny` may throw a `NullPointerException` when the selected element is null. It is best to decide on a null policy early and express it clearly in the mapper.

If invalid data needs to **report an error**, do not silently drop it by not calling `accept`. For example, processing an order with an invalid quantity might require an `IllegalArgumentException` or a result type representing an error; "emitting 0 results" is appropriate when the correct business behavior is to **skip** it.

## 9. Common Pitfalls

1. **Confusing `mapMulti` with `map`:** a `mapMulti` callback does not return a result; it calls `downstream.accept`. Writing `return n * 2;` inside a `mapMulti` lambda is wrong; call `out.accept(n * 2)` instead.
2. **Forgetting to emit results:** a mapper that does not call `out.accept` completely removes that source element from the result, even if the lambda computes a value without emitting it.
3. **Emitting multiple times when only one is intended:** each `accept` call adds another element. Make sure the conditions and emission counts match the requirements.
4. **Type inference falling back to `Object`:** if the compiler reports `List<Object> cannot be converted to List<String>`, try `.<String>mapMulti(...)`.
5. **Storing or passing `downstream` outside:** do not keep a reference to emit data after the mapper returns; the contract only allows emitting during the mapper's execution turn.
6. **Relying on side effects in the mapper:** do not use the callback invocation count or parallel execution schedule as a business contract; choose an appropriate terminal operation instead.
7. **Assuming `mapMulti` is always faster than `flatMap`:** there is no universal guarantee. Choose the clearer expression and benchmark with real data if optimization is needed.
8. **Ignoring checked exceptions:** the standard `BiConsumer` does not declare `throws IOException` or any other checked exception. If I/O is involved, handle it intentionally at an adapter or boundary; avoid hiding file-writing logic inside callbacks.
9. **Forgetting the Java version:** `mapMulti` was added in Java 16; Java 8–15 codebases do not have this API. For those versions, `flatMap` or `filter().map()` are the alternatives.
10. **Not distinguishing input/output element types:** the callback allows emitting a type `R` different from `T`, so `mapMulti` is not just `filter`; it can also transform types and expand the number of elements.

## 10. When to Use Which Approach?

| Problem | Usually appropriate approach |
| --- | --- |
| Each `T` transforms into exactly one `R` | `map(f)` |
| Keep only `T` elements satisfying a condition | `filter(predicate)` |
| Simple filter followed by transformation | `filter(predicate).map(f)` |
| Each input emits 0, 1, or a few results via conditions/loops | `mapMulti((item,out) -> ...)` |
| Each input already has or naturally produces a `Stream<R>` | `flatMap(item -> streamOfResults)` |
| Each input emits multiple integers and arithmetic aggregation is needed | `mapMultiToInt(...).sum()` |
| Multi-level parsing where sub-steps should stay clearly separated | Choose a helper method or `flatMap` to preserve readability |

## Self-Check

**Question 1.** What does `Stream.of(1, 2, 3).<Integer>mapMulti((n, out) -> { if (n % 2 == 1) { out.accept(n); out.accept(-n); } }).toList()` return?

**Answer:** `[1, -1, 3, -3]`. The even number `2` emits no elements, and each of the two odd numbers emits two results.

**Question 2.** What is the core difference between `flatMap` and `mapMulti`?

**Answer:** `flatMap` takes a function that returns **a stream for each element**; `mapMulti` takes a mapper that calls **`Consumer.accept` 0 or more times** during the callback turn itself. Both can produce 0, 1, or many result elements.

**Question 3.** With `parallelStream().<String>mapMulti(...).toList()` on a `List`, can the result still preserve logical order?

**Answer:** Yes. For an ordered stream, `toList` preserves encounter order, even though the mapper may execute on different threads and on a non-fixed schedule.

## Key Takeaways

- `mapMulti()` emits **0, 1, or many elements** using `out.accept(value)`.
- It avoids creating a sub-`Stream` for each element like `flatMap()`; it is a useful option when the number of outputs is typically small or emitted via conditions/loops.
- With generic `mapMulti`, you can specify the type using `.<R>mapMulti(...)` to avoid inference to `Object`.
- `mapMultiToInt`, `mapMultiToLong`, `mapMultiToDouble`, and variants on primitive streams are available.
- Keep the mapper non-interfering with the source and independent of shared state; do not retain `downstream` to call outside the mapper lifecycle.
