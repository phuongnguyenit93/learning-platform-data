# Why Does a Missing Terminal Operation Prevent Lambdas from Being Called in Java Stream?

## 1. Goal: Distinguishing “Declaring Work” from “Executing Work”

In Java, an expression like:

```java
Stream<String> pipeline = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase);
```

looks as if it is filtering and converting to uppercase immediately. In reality, `filter` and `map` are **intermediate operations**: they describe processing steps and create a new pipeline, but **usually have not traversed the data or invoked the lambda bodies yet**. If the program stops at the declaration line above without a consuming operation, these lambdas will not be called.

When a **terminal operation** is added, for example:

```java
List<String> result = pipeline.toList();
```

only then does the framework begin requesting the required elements from the source, running the corresponding stages, and collecting the result. For ordinary sources and operations, this is the point at which the lambdas in `filter` and `map` are called.

However, we need to understand this more accurately than a common saying: **“Having a terminal operation” is a condition for the pipeline to be evaluated, not a guarantee that every lambda will run, or that each lambda will run exactly once for every element.** Terminal operations can stop early; some stages can be optimized away if doing so does not affect the result according to the API contract.

After this lesson, you should be able to explain:

- Why creating a Stream and calling `map/filter/peek` does not mean the data has been processed.
- When a terminal operation causes the framework to traverse elements.
- The `filter → map → terminal` order on a sequential pipeline.
- Why `count()` or `findFirst()` can cause lambdas not to run for all elements, even when a terminal operation is present.
- Why expressions that **create a source, create a callback, or compute arguments** may be evaluated immediately, unlike **callback bodies**.
- How to write proper tests/debugging instead of relying on side effects in `map` or `peek`.

## 2. Stream Pipeline: Source, Intermediate, Terminal

A Stream pipeline typically consists of three parts:

```text
Data source
    │
    ▼
stream() / Stream.of(...) / IntStream.range(...)
    │
    ▼
filter(predicate)     ┐
    │                 │
    ▼                 ├── intermediate operations
map(mapper)           │    (only describe how to process)
    │                 │
    ▼                 │
sorted()              ┘
    │
    ▼
toList() / collect() / forEach() / count() / findFirst()
    │
    └── terminal operation: requests a final result/effect
```

The **source** determines the set of available elements. **Intermediate operations** transform how elements are emitted through the pipeline. A **terminal operation** requests evaluation of the pipeline for a final purpose.

| Group | Example | What happens when the method is called? |
| --- | --- | --- |
| Source creation | `list.stream()`, `Stream.of(...)` | Creates a Stream from the source; argument expressions creating the source are still evaluated according to Java rules |
| Intermediate | `filter(p)` | Adds a step to keep/discard elements; usually does not call `p.test(...)` yet |
| Intermediate | `map(f)` | Adds a transformation step; usually does not call `f.apply(...)` yet |
| Intermediate | `peek(action)` | Adds an observation step; not a guaranteed logging mechanism |
| Stateful intermediate | `sorted(...)`, `distinct()` | Adds a step that needs to consider multiple elements/state; still does not trigger consumption merely by being declared |
| Terminal | `toList()`, `collect(...)` | Requests the result to be collected; processes the necessary elements |
| Terminal | `forEach(...)`, `forEachOrdered(...)` | Requests executing the action on traversed elements according to the contract |
| Short-circuiting terminal | `findFirst()`, `anyMatch(...)`, `limit(...).findFirst()` | Can finish without traversing the entire source |
| Optimizable terminal | `count()` | Can return the result from a known size without calling some intermediate lambdas |

**Just seeing parentheses `(...)` does not mean it is a terminal operation.** `map(...)` and `filter(...)` are real method calls, but they only continue building the pipeline. The name and contract of the operation determine whether it causes the pipeline to be consumed.

## 3. Complete Java 17+ Example: No Terminal Means No Lambda Execution

Create the file `LazyPipelineDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        System.out.println("before pipeline");

        Stream<String> pipeline = names.stream()
                .filter(name -> {
                    System.out.println("filter: " + name);
                    return name.length() >= 3;
                })
                .map(name -> {
                    System.out.println("map: " + name);
                    return name.toUpperCase();
                });

        System.out.println("pipeline created");
        System.out.println("before terminal");

        List<String> result = pipeline.toList();

        System.out.println("result=" + result);
    }
}
```

Compile and run:

```bash
javac LazyPipelineDemo.java
java LazyPipelineDemo
```

Exact output for a sequential pipeline on Java 17:

```text
before pipeline
pipeline created
before terminal
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
result=[BINH, CHI]
```

Reading the output stage by stage:

1. `"before pipeline"` is printed immediately.
2. The call `names.stream().filter(...).map(...)` builds the pipeline. **No `filter: ...` or `map: ...` lines appear yet.**
3. `"pipeline created"` and `"before terminal"` are printed next.
4. `pipeline.toList()` is the terminal operation. The framework starts pulling elements through the processing chain.
5. For `"An"`, `filter` returns false (length 2), so `map` is not called for this element.
6. For `"Binh"` and `"Chi"`, the filter returns true, so the mapper converts them to uppercase.
7. `toList()` returns the list `[BINH, CHI]`.

If you **delete the line `List<String> result = pipeline.toList();` and the corresponding line printing `result`**, the bodies of both lambdas will not run in this program: you will only have the log lines before/after creating the pipeline.

A second important point: even when a terminal operation is present, the mapper **does not run for An** because `filter` already eliminated that element. Thus, the number of times a lambda is called depends on whether an element **reaches that stage**.

## 4. What “Lazy” Means and What It Does Not Mean

Stream laziness primarily refers to **deferring the execution of intermediate stages until a result is requested**. It does not mean:

- Every expression appearing on the line of code is deferred.
- Every operation processes each element immediately when called.
- Having a terminal operation guarantees the entire source is traversed.
- A lambda is guaranteed to be called exactly once for every element of the source.
- Having `peek(...)` guarantees logs will be printed.
- Once a pipeline exists, it runs automatically in the background when Java is idle.
- A Stream automatically remembers/caches results so one run can be reused multiple times.

In reality, a pipeline like:

```java
Stream<Integer> s = Stream.of(1, 2, 3)
        .map(n -> n * 10);
```

only describes how to obtain the mapped values. It does not create a background task. Subsequent lines of code on the same thread continue running normally. When the program does not consume `s`, the mapper has no reason to execute.

In a typical sequential Stream, processing usually proceeds **element by element through the stages**, rather than necessarily “filtering all data first and then mapping all of it.” However, `sorted()` or `distinct()` are stateful operations and can change how the framework buffers/observes data. Do not assume a fixed execution schedule for every pipeline, especially parallel streams.

## 5. Distinguishing Lambda Creation from Invoking the Lambda Body

Consider:

```java
Predicate<String> valid = s -> s.length() > 2;
Stream<String> pipeline = Stream.of("a", "long")
        .filter(valid);
```

Here:

- The expression `s -> s.length() > 2` creates an object/behavior compatible with `Predicate<String>`.
- `filter(valid)` receives the Predicate and creates a stage.
- The method `Predicate.test(...)` **is not necessarily called yet**.
- Only when the terminal operation consumes elements and needs to decide whether to keep/discard them does the framework call `valid.test(element)`.

Similarly:

```java
Function<String, Integer> length = String::length;
Stream<Integer> lengths = Stream.of("a", "long").map(length);
```

These are declarations inside a method with `Stream`, `Predicate`, and `Function` imported. Creating a method reference is not the same as calling `String.length()` on a specific element; the mapper is called when the stage needs to process an element.

**A further distinction is needed:** expressions used to **create** a callback are still evaluated according to normal Java rules. For example:

```java
Stream<String> pipeline = source.stream()
        .map(makeMapper());
```

If `makeMapper()` logs a message and returns a `Function<String, String>`, the **call to `makeMapper()`** happens when building the pipeline to compute the argument passed to `map`. However, the body of `Function.apply(...)` returned by `makeMapper()` may not be called yet. That call is not automatically deferred just because it is an argument to an intermediate operation.

If you want to defer creating the mapper itself until element processing, in source code you could place the work inside the lambda body, e.g., `map(x -> makeMapper().apply(x))`; however, that creates a mapper **for every element** passing through the stage, which may be undesirable. You should understand callback cost and lifecycle rather than applying mechanical tricks.

## 6. Separate Example on Mapper Creation Time vs. Mapper Execution Time

Save the file `MapperTimingDemo.java`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class MapperTimingDemo {
    private static Function<String, String> makeMapper() {
        System.out.println("makeMapper called");
        return value -> {
            System.out.println("apply: " + value);
            return value.toUpperCase();
        };
    }

    public static void main(String[] args) {
        System.out.println("start");

        Stream<String> pipeline =
                List.of("java", "stream").stream()
                        .map(makeMapper());

        System.out.println("pipeline ready");

        List<String> result = pipeline.toList();

        System.out.println("result=" + result);
    }
}
```

Run:

```bash
javac MapperTimingDemo.java
java MapperTimingDemo
```

Output:

```text
start
makeMapper called
pipeline ready
apply: java
apply: stream
result=[JAVA, STREAM]
```

`makeMapper()` itself is a method call **evaluated immediately when building the pipeline**. Only calling `apply(...)` on the returned mapper is deferred until `toList()` consumes the pipeline. The same principle holds for many expressions that create a predicate, comparator, or data source.

Do not confuse this with:

```java
Stream<String> s = Stream.of(loadNameFromDatabase());
```

In this snippet, `loadNameFromDatabase()` is an argument expression used to produce the **input value** for `Stream.of(...)`, so Java calls it **immediately** to obtain a String to pass to the factory; the laziness of subsequent stages does not defer that I/O.

If you truly need the source to be generated upon consumption, one approach is `Stream.generate(() -> loadNameFromDatabase())` together with an explicit element limit. Then the work is placed inside the Supplier body and occurs only as needed when consuming the source. However, `generate` creates an infinite source by default; do not call `toList()` directly on an infinite Stream without a proper limit or stopping condition.

## 7. Which Terminal Operations Actually Require Data Traversal?

Common operations:

| Terminal operation | Purpose | Thing to remember |
| --- | --- | --- |
| `toList()` | Collects remaining values into a List | Returns the result; does not produce a mutable list |
| `collect(collector)` | Collects into a List, Map, String, statistics, etc. | How traversal occurs depends on the pipeline and collector |
| `forEach(action)` | Calls action when consuming each element | On parallel streams, action order is not guaranteed |
| `forEachOrdered(action)` | Consumes in encounter order when the stream is ordered | May require synchronization/extra overhead |
| `reduce(...)` | Combines elements using an operation | Identity, associativity, and reduction type matter |
| `min/max(...)` | Finds extrema | Does not need to return the entire list |
| `findFirst()` | Finds the first element in encounter order | Can stop once a valid result is found |
| `anyMatch(p)` | Checks if any element matches | Can stop as soon as true is found |
| `allMatch(p)` | Checks if all elements match | Can stop when false is encountered |
| `noneMatch(p)` | Checks if no element matches | Can stop when true is encountered |
| `count()` | Counts the number of result elements | Can compute from source size and skip some stages |
| `iterator()` / `spliterator()` | Obtains an object used for traversal | Classified as terminal, but **stepping through elements happens when the consumer traverses the iterator/spliterator**, not necessarily right at the call that obtains it |

Therefore, a more accurate explanation is: **a terminal operation triggers or sets up pipeline consumption according to its contract**. For `iterator()`, actually stepping through elements may be deferred until calls to `hasNext()`, `next()`, or spliterator traversal methods.

Do not use the definition “a terminal operation always returns a List” or “a terminal operation always runs every lambda”: both are wrong.

## 8. Terminal Present Yet Lambdas Still Not Called: `count()` Optimization

This is a very important exception to debugging with `peek` or using `map` to produce side effects.

For a source with a known size, the framework sometimes knows the number of elements without running intermediate pipelines. For example, `map` transforms **each element into exactly one element**, so it does not change the count. When calling `count()`, running the mapper may be unnecessary to compute the result.

Create `CountOptimizationDemo.java`:

```java
import java.util.List;

public class CountOptimizationDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc");

        System.out.println("before count");

        long count = words.stream()
                .map(word -> {
                    System.out.println("map: " + word);
                    return word.toUpperCase();
                })
                .count();

        System.out.println("count=" + count);
    }
}
```

Run on Java 17:

```bash
javac CountOptimizationDemo.java
java CountOptimizationDemo
```

Output with the standard JDK 17 Stream implementation:

```text
before count
count=3
```

In this case, `count()` knows the source has 3 elements and `map` does not change cardinality, so it **can compute the result without calling the mapper**. This is an optimization permitted by the Stream contract; do not turn the number of log lines printed by `map` into a business requirement. The `Stream.count()` API documentation explicitly notes that if the implementation can compute the total number of elements directly from the source, it may skip executing intermediate operations.

Consequently:

- It is wrong to say “whenever `count()` is present, all lambdas are called.”
- It is wrong to treat `map(x -> { audit(x); return x; })` as a way to guarantee auditing occurs.
- It is wrong to use `peek(System.out::println)` and count log lines to confirm every element was traversed in every pipeline.

If the real goal is to **test the transformation**, call a terminal operation that is meaningful for the transformed values, such as `toList()`, and **assert the resulting contents**. If the goal is a mandatory side effect, design a processing step with its own contract instead of hiding it inside a mapper/peek.

## 9. Terminal Present Yet Only Some Lambdas Called: Short-Circuiting

Terminal operations such as `findFirst()`, `anyMatch()`, `allMatch()`, and `noneMatch()` can stop once there is enough data to conclude. Intermediate operations such as `limit(n)` can also cause the pipeline not to need the entire source.

Create `ShortCircuitDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class ShortCircuitDemo {
    public static void main(String[] args) {
        Optional<Integer> first = List.of(1, 2, 3, 4)
                .stream()
                .filter(n -> {
                    System.out.println("filter: " + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    System.out.println("map: " + n);
                    return n * 10;
                })
                .findFirst();

        System.out.println("first=" + first);
    }
}
```

Run:

```bash
javac ShortCircuitDemo.java
java ShortCircuitDemo
```

Deterministic sequential output:

```text
filter: 1
filter: 2
map: 2
first=Optional[20]
```

Why do we not see 3 and 4?

1. Element 1 is discarded by `filter`, so it does not reach `map`.
2. Element 2 passes `filter` and is mapped to 20.
3. `findFirst()` has already found the first element it needs, so it stops the pipeline without requesting 3 or 4.

With `anyMatch(p)`, the framework can stop as soon as it finds a matching element. With `allMatch(p)`, it can stop when it encounters a non-matching element. With `noneMatch(p)`, it can stop when it encounters a matching element. On a **parallel stream**, elements and callbacks may run across multiple threads, and the number of elements actually processed before stopping may differ from intuition based on a sequential pipeline.

In particular, for an empty stream, `anyMatch` returns false, `allMatch` returns true, and `noneMatch` returns true without needing to call the Predicate; that is the mathematical quantifier rule in the API. Therefore, calling a terminal operation does not always entail a lambda call.

## 10. Intermediate `limit(0)` and Empty Sources

Both of the following cases do not need to run a mapper on any element:

```java
Stream.of("A", "B").limit(0)
        .map(s -> expensiveTransform(s))
        .toList();

Stream.<String>empty()
        .map(s -> expensiveTransform(s))
        .toList();
```

This is **illustrative code**, assuming a method `expensiveTransform(String)` returning `String`. In the first case, `limit(0)` yields no elements; in the second case, the source is inherently empty. Even though `toList()` is called, no element will reach the mapper.

This differs from a missing terminal operation: here there is a terminal operation, but the number of elements to process at the `map` stage is **0**. Always ask two separate questions:

1. Is there a terminal operation or traversal activity requesting data from the pipeline?
2. If so, which elements **actually reach the lambda**, and does the terminal result require calling it?

## 11. Why Is `peek` Misleading When Debugging?

`peek(Consumer<T>)` is often used to observe elements passing through a stage:

```java
List<Integer> values = List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .toList();
```

This snippet is inside a method with `List` imported. With an ordinary `toList()` terminal, logs can help understand elements flowing through the pipeline. However, `peek` is not a mechanism to guarantee an important side effect occurs, because:

- When there is **no terminal operation yet**, no elements are requested.
- With a terminal like `count()` on a sized source and stages that do not change element count, the framework **may skip `peek`**.
- With short-circuiting, some elements may never reach `peek`.
- With parallel streams, logs may appear out of source order; execution count depends on the pipeline.
- When sources/terminals are optimized, side effects of intermediate operations should not be used as behavioral benchmarks.

For testing, compare **the return value of the terminal operation** and the required state. If you want application processing logs, place logging at a location with a clear contract—for example, inside an explicit processing loop, a business method that is guaranteed to be called, or a terminal operation suited to the requirement (with order/concurrency control if needed).

## 12. When Do Exceptions from Lambdas Appear?

If a mapper converts strings to integers:

```java
Stream<Integer> numbers = Stream.of("12", "bad", "7")
        .map(Integer::parseInt);
```

this line can create the pipeline without **throwing `NumberFormatException` yet**: the mapper has not been called.

However:

```java
List<Integer> values = numbers.toList();
```

when the terminal operation needs to convert the string `"bad"`, `Integer.parseInt("bad")` throws an exception. This is an illustrative snippet inside a method with `Stream` and `List` imported.

Do not rely on `count()` or an optimizable terminal operation to “dodge” data errors. If you need to validate all records, design a validation step that genuinely requires traversing the data and has a clear error-handling strategy.

**Checked exceptions:** common functional interfaces such as `Function.apply` and `Predicate.test` do not declare checked exceptions. A lambda calling an API that throws a checked exception must catch/transform the exception according to its contract, or use an appropriate abstraction. Laziness does not change Java’s checked exception compilation rules.

**Timing of an error does not mean the error is gone:** errors in a lambda usually appear when the lambda is actually invoked. Without a terminal operation, the error has not occurred yet; that does not make the pipeline safe if a terminal operation later requires processing the faulty element.

## 13. Do Not Consume a Stream Multiple Times

A Stream is designed to be used for **one processing sequence** and then completed. Once a terminal operation has been called:

```java
Stream<String> s = Stream.of("a", "b");
List<String> result = s.toList();
```

do not reuse `s` to call `s.count()`. The second call typically throws `IllegalStateException` because the stream has already been operated upon/closed. Create a new stream from the source if you need to process it again:

```java
List<String> source = List.of("a", "b");
List<String> upper = source.stream()
        .map(String::toUpperCase)
        .toList();
long count = source.stream().count();
```

The snippets above belong to a method with `List` and `Stream` imported.

Even adding an intermediate operation can cause the original Stream object to be considered linked to a pipeline and no longer reusable in another way. Avoid branching from **the same Stream instance** expecting it to behave like a collection that can be read repeatedly.

If you need to rerun a pipeline with the same logic, a `Supplier<Stream<T>>` can create a **new stream** each time:

```java
Supplier<Stream<String>> sourceFactory =
        () -> names.stream();
```

The snippet above assumes `names` is a collection from which a stream can be obtained multiple times and that `Supplier` and `Stream` are imported. Each call to `sourceFactory.get()` creates a new pipeline; **do not store and reuse a consumed Stream**.

## 14. Statefulness, Infinite Sources, and Why Terminal Operations Must Be Designed Carefully

Laziness does not mean a stream always saves all memory or can produce a result immediately.

For example:

```java
Stream<Integer> natural = Stream.iterate(1, n -> n + 1);
```

This is an infinite source; it does not automatically print or generate infinite integers merely by being created. If you call `natural.sorted().findFirst()`, sorting an entire infinite source **cannot complete to return a result in the usual sense**. When processing is needed, set an appropriate limit:

```java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted()
        .toList();
```

The result is `[1, 2, 3, 4, 5]`.

Stateful operations such as `sorted` and `distinct` may have to observe many elements before emitting results. With `limit`, `takeWhile`, `dropWhile`, and `findFirst`, their position in the pipeline can change **which elements are requested**. For instance, `limit(5).sorted()` means “take five elements then sort,” which is not always the same as `sorted().limit(5)` on every source; with an infinite source, the difference even determines whether the pipeline can finish.

Do not attach a terminal operation like `toList()` to an infinite source without a limit or stopping condition, because the program may keep generating data endlessly and consume resources.

## 15. Parallel Streams: Having a Terminal Operation Does Not Guarantee Log Order

With:

```java
numbers.parallelStream()
        .map(n -> {
            System.out.println("mapped " + n);
            return n * 2;
        })
        .toList();
```

this is an illustrative snippet inside a method with a `numbers` collection. Mappers may run on multiple threads, and log order may not follow encounter order. Even though `toList()` on an ordered stream returns results in encounter order, side effects inside each lambda are not thereby guaranteed to appear sequentially.

For predictable Stream programming:

- Prefer **stateless, non-interfering** lambdas (do not modify the source being traversed by the stream).
- Do not share unsynchronized mutable variables to count how many times a mapper is called.
- If you want statistics, use a collector or a terminal operation with clear semantics.
- Do not assume a terminal operation necessarily executes callbacks exactly once per element. Both optimizations and short-circuiting can affect this.
- If the program requires ordered side-effect processing, design appropriate traversal and synchronization instead of using `peek` or `map` with side effects.

This is the difference between the **final data contract** and the **internal execution trace**.

## 16. Example Comparing an Eager Source and a Lazy Supplier

Create the file `SourceTimingDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class SourceTimingDemo {
    private static String load() {
        System.out.println("load()");
        return "value";
    }

    public static void main(String[] args) {
        System.out.println("before of");
        Stream<String> eagerInput = Stream.of(load());
        System.out.println("after of");

        System.out.println("before eager terminal");
        List<String> eagerResult = eagerInput.toList();
        System.out.println("eager result=" + eagerResult);

        System.out.println("before generate");
        Stream<String> lazySource = Stream.generate(
                () -> load()).limit(2);
        System.out.println("after generate");

        List<String> lazyResult = lazySource.toList();
        System.out.println("lazy result=" + lazyResult);
    }
}
```

Run:

```bash
javac SourceTimingDemo.java
java SourceTimingDemo
```

Output:

```text
before of
load()
after of
before eager terminal
eager result=[value]
before generate
after generate
load()
load()
lazy result=[value, value]
```

Explanation: in `Stream.of(load())`, Java calls `load()` immediately to compute the argument for creating the stream. In `Stream.generate(() -> load())`, the Supplier body is called by the framework when elements are requested—here exactly twice due to `limit(2).toList()`.

**Do not treat `generate` as a default replacement for `of`.** One creates a source via a Supplier on demand, while the other creates a source from already-evaluated values; they serve different use cases, and a `generate` source can be infinite if not bounded.

## 17. Distinguishing Missing-Terminal Bugs from Empty-Data Pipeline Bugs

Read the three snippets below:

```java
// A: No terminal operation.
Stream.of("a", "bb")
      .map(s -> {
          System.out.println("A mapper: " + s);
          return s.toUpperCase();
      });

// B: Has a terminal operation, but filters out all data.
Stream.of("a", "bb")
      .filter(s -> s.length() > 10)
      .map(s -> {
          System.out.println("B mapper: " + s);
          return s.toUpperCase();
      })
      .toList();

// C: Has a terminal operation, but only needs the first result.
Stream.of("a", "bb")
      .map(s -> {
          System.out.println("C mapper: " + s);
          return s.toUpperCase();
      })
      .findFirst();
```

These are snippets inside a method with `Stream` imported, illustrated on a sequential stream.

- **A:** no terminal operation; the mapper does not run.
- **B:** the terminal operation runs, but `filter` lets no elements through; the mapper does not run.
- **C:** the terminal `findFirst()` stops after the first element; the mapper only needs to run for `"a"`, not `"bb"`.

Thus, “no logs” is not enough to conclude that a pipeline **lacks a terminal operation**. A terminal operation may exist while no elements reach the logged stage, or the framework may skip the stage due to a valid optimization.

## 18. Reliable Testing and Debugging Practices

If you want to test a pipeline that converts names to uppercase, check the **result**, rather than requiring the callback to print a specific number of lines:

```java
List<String> actual = List.of("an", "binh", "chi")
        .stream()
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .toList();

if (!actual.equals(List.of("BINH", "CHI"))) {
    throw new AssertionError("Unexpected result: " + actual);
}
```

This code is inside a method with `List` imported. The test uses the Stream’s result contract. Internal details such as the number of lambda objects, scheduling order, or whether an intermediate stage is skipped are not test criteria unless the application’s own API guarantees a specific side effect.

When debugging a pipeline that does not produce the expected result:

1. Check whether there is a terminal operation or actual traversal.
2. Check whether the source is empty; a `Stream.empty()` source will not call the mapper.
3. Check whether `filter` or `limit(0)` prevents elements from reaching the mapper.
4. Check whether the terminal operation short-circuits, such as `findFirst()` / `anyMatch()`.
5. With `count()`, consider whether source-size optimization skips intermediate lambdas.
6. If using a parallel stream, separate result requirements from log order.
7. Check whether the lambda is actually **inside** the callback or if the work ran early to compute an argument/callback.
8. Avoid reusing a consumed stream; create a new stream for each attempt.
9. For Streams backed by files, HTTP, or databases, manage resources and errors according to the source API rather than expecting the pipeline to close resources automatically.

## 19. Self-Check Questions

### Question 1: Find where the lambda starts running

```java
List<Integer> values = List.of(2, 3, 4);

Stream<Integer> pipeline = values.stream()
        .map(n -> {
            System.out.println("map " + n);
            return n * n;
        });

System.out.println("ready");
List<Integer> result = pipeline.toList();
System.out.println(result);
```

Output?

**Answer:**

```text
ready
map 2
map 3
map 4
[4, 9, 16]
```

The `map ...` logs only appear when `toList()` consumes the pipeline. Creating the lambda and calling `map(...)` only appends a stage.

### Question 2: When does the mapper not run?

Consider:

```java
long count = List.of("a", "bb", "ccc")
        .stream()
        .map(s -> {
            System.out.println("visited " + s);
            return s.toUpperCase();
        })
        .count();
```

Why might no `visited` logs appear even though a terminal operation is present?

**Answer:** the list source has a known size and `map` does not change the number of elements. The framework can optimize `count()` to return 3 without evaluating the mapper. Measure the output/contract instead of requiring the mapper to have side effects.

### Question 3: Does a terminal operation process the entire source?

```java
boolean anyEven = List.of(1, 3, 4, 6)
        .stream()
        .anyMatch(n -> {
            System.out.println("check " + n);
            return n % 2 == 0;
        });
```

With a sequential stream, which numbers is the Predicate called on?

**Answer:** checks 1, 3, and then 4; once 4 matches, `anyMatch` returns true and does not need to check 6. With a parallel stream, do not rely on the call count or callback order above.

### Question 4: Distinguish eager from lazy

```java
Stream<String> a = Stream.of(load());
Stream<String> b = Stream.generate(() -> load()).limit(1);
```

Assuming `load()` returns a String and prints a log, when is it called?

**Answer:** the line creating `a` calls `load()` immediately to compute the argument for `Stream.of`. The line creating `b` only creates the Supplier and pipeline; `load()` runs when an element needs to be generated, e.g., when calling `b.toList()`. If `b` is not consumed, there are no calls from the Supplier.

## 20. Rule of Thumb

```text
Pipeline creation calls:
    stream()
      .filter(predicate)
      .map(mapper)
      .peek(observer)
          ↓
    No need to invoke callback bodies yet to produce a result

Terminal operation:
    .toList() / .collect() / .findFirst() / .anyMatch(...)
          ↓
    Requests processing of the necessary elements
          ↓
    Callbacks may run, be skipped due to filter/short-circuit,
    or be optimized away if they do not affect the result
```

**Conclusion:** Missing a terminal operation is the most common reason lambdas in `map/filter/peek` are not called: you have only **described the pipeline**, not yet requested **data consumption**. However, even when a terminal operation is present, there is no general guarantee that every callback runs for every element. Read each stage’s contract, short-circuiting behavior, optimizations like `count()`, argument evaluation timing, and choose result-based testing.

**References:** Java SE API for `java.util.stream.Stream` (intermediate/terminal operations, `map`, `filter`, `peek`, `toList`, `count`, `findFirst`, `anyMatch`), `java.util.stream` package documentation on laziness/side effects, Java Language Specification on method argument evaluation timing.
