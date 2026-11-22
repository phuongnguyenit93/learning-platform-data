# Laziness and When a Pipeline Actually Executes

In the Java Stream API, a pipeline typically has three parts: a **data source (source)**, **intermediate operations**, and a **terminal operation**. What determines how a Stream works is **laziness**: most element-by-element processing work is deferred until there is a demand to obtain a result.

This topic belongs to the **Pipeline Contracts and Lifecycle** chapter of **JAVA_STREAM_API**. Understanding execution timing helps us write chains of `filter`, `map`, `reduce`, and `collect` with the right semantics, take advantage of short-circuiting, avoid unpredictable side effects, and manage resources safely.

## 1. Declaring a pipeline is different from running a pipeline

Consider the expression:

```java
Stream<String> pipeline = names.stream()
    .filter(name -> name.length() >= 3)
    .map(String::toUpperCase);
```

At the moment the `pipeline` variable is assigned, Java has already created the objects describing the pipeline. However, **`filter` and `map` have not yet had to process all elements in `names` one by one**. They are intermediate operations that return a Stream so that additional subsequent steps can be chained.

When writing:

```java
List<String> result = pipeline.collect(Collectors.toList());
```

`collect` is a terminal operation, requesting the result and pulling data through the preceding steps. With a typical sequential Stream, this process usually processes each element through combinable steps, rather than creating a temporary list after each `filter` or `map`.

| Component | Example | What happens when called? |
| --- | --- | --- |
| Source | `list.stream()`, `Stream.of(...)`, `Files.lines(...)` | Creates the source for the pipeline; may initialize resources or evaluate arguments right here. |
| Stateless intermediate | `filter`, `map`, `flatMap` | Appends transformation/filtering rules; usually does not traverse elements yet. |
| Stateful intermediate | `sorted`, `distinct` | Appends a step that needs to observe or store information about elements; at runtime it may require a buffer. |
| Stream-limiting intermediate | `limit`, `skip`, `takeWhile` | Describes how to select a range of elements; some can contribute to early termination upon consumption. |
| Terminal | `collect`, `reduce`, `sum`, `forEach`, `findFirst`, `count` | Triggers the evaluation needed to produce the result or effect of the operation. |

> **Important distinction:** "Lazy" does not mean every Java expression at the source-creation step is deferred. For example, in `Stream.of(expensiveCall())`, Java calls `expensiveCall()` to compute the argument *before* creating the Stream. Similarly, `Files.lines(path)` may open the file right when creating the Stream, even though iterating through the lines happens later.

## 2. Observing exact execution timing

The following example runs with Stream APIs available since Java 8:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

        Stream<String> pipeline = names.stream()
            .filter(name -> {
                System.out.println("filter: " + name);
                return name.length() >= 3;
            })
            .map(name -> {
                System.out.println("map: " + name);
                return name.toUpperCase();
            });

        System.out.println("Pipeline declared");
        List<String> result = pipeline.collect(Collectors.toList());
        System.out.println("Result: " + result);
    }
}
```

Output with a sequential pipeline and an ordered list:

```text
Pipeline declared
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
filter: Dung
map: Dung
Result: [BINH, CHI, DUNG]
```

There are two things to note:

1. The line "Pipeline declared" appears **before** any `filter`/`map` lines. Declaring intermediate operations has not traversed the list yet.
2. `filter: Binh` is immediately followed by `map: Binh`, rather than waiting to filter all four names before running `map`. This is how **stateless** steps are typically fused when a sequential Stream is consumed. `map` also does not run for `An` because this element is filtered out at `filter`.

Do not infer that every pipeline has the exact same function-call order as the example. `sorted`, `distinct`, parallel processing, and terminal operation optimizations can change how elements are requested or buffered.

## 3. How much data does a terminal operation request?

A terminal operation **initiates the evaluation process**, but does not necessarily force the Stream to traverse the entire source. The actual demand depends on the operation and the steps preceding it.

| Terminal operation | Typical demand | Notes |
| --- | --- | --- |
| `collect(Collectors.toList())` | Collects all remaining elements | The pipeline may already have been limited using `limit` or `takeWhile`. |
| `reduce(...)`, `sum()`, `max()` | Usually needs to inspect all matching elements | The aggregated result depends on unseen data. |
| `findFirst()` | Stops once the first element in encounter order is determined | May have to read many elements if filtering steps have not yet produced a result. |
| `findAny()` | Can stop as soon as any single element is found | Especially useful with parallel sources; does not promise the first element. |
| `anyMatch(...)`, `allMatch(...)`, `noneMatch(...)` | Capable of short-circuiting once the result is certain | `anyMatch` needs only one matching element; `allMatch` needs only one failing element. |
| `count()` | Returns the number of elements in the pipeline | Can optimize using the source size and skip traversal; see section 5. |

Example:

```java
import java.util.stream.IntStream;

int firstEven = IntStream.rangeClosed(1, 100)
    .peek(n -> System.out.println("Fetched: " + n))
    .filter(n -> n % 2 == 0)
    .findFirst()
    .orElse(-1);

System.out.println("First even number: " + firstEven);
```

With the **sequential** pipeline above, the output consists only of `Fetched: 1`, `Fetched: 2`, and then `First even number: 2`. `findFirst` has its result immediately after encountering `2`, so there is no need to continue checking numbers from `3` to `100`.

`limit` is an **intermediate operation** but can also enable early termination:

```java
List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .limit(2)
    .boxed()
    .collect(Collectors.toList()); // [2, 4]
```

`limit(2)` here takes **two elements that have passed `filter`**, so the pipeline must inspect up to the number `4`. If `limit(2)` is moved before `filter`, only the first two numbers `1` and `2` are passed through the filter, and the result will be `[2]`:

```java
List<Integer> different = IntStream.rangeClosed(1, 10)
    .limit(2)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList()); // [2]
```

**The order of operations is part of the problem's semantics**; swapping steps to "optimize" can change the result.

## 4. Laziness does not eliminate the cost of stateful operations

An intermediate operation can be *declared* lazily, yet when execution starts it still needs to consume a large amount of data before producing the first result.

Example with `sorted`:

```java
List<Integer> smallestTwo = Stream.of(9, 1, 8, 2, 7)
    .sorted()
    .limit(2)
    .collect(Collectors.toList()); // [1, 2]

List<Integer> firstTwoSorted = Stream.of(9, 1, 8, 2, 7)
    .limit(2)
    .sorted()
    .collect(Collectors.toList()); // [1, 9]
```

In the first expression, to know the two smallest elements, the `sorted` step of a sequential Stream must accept all five values before it can emit data in sorted order. In the second expression, `limit` passes only the first two values into `sorted`.

A few consequences:

- `sorted` usually needs to store many elements, so `sorted().findFirst()` cannot short-circuit like `filter().findFirst()` on an ordered source.
- `distinct` needs to record seen values to remove duplicates; depending on the pipeline and encounter order, it may emit results incrementally but still has state cost.
- With an **infinite** source, `Stream.iterate(0, n -> n + 1).sorted().findFirst()` cannot complete under normal evaluation because `sorted` must receive the entire input. Place a finite limit **before** `sorted` when the problem actually considers only a certain number of initial elements.

Since Java 9, `takeWhile` can stop when encountering the first element that **does not satisfy the condition** on a Stream with encounter order; `dropWhile` discards the initial prefix that satisfies the condition and then continues passing the rest. They also need to be placed in the right position in the pipeline.

## 5. Having a terminal operation does not mean every lambda is called

A common source of bugs is assuming that after calling `count()`, every `map` or `peek` will definitely run. This is **not part of the Stream contract**.

```java
long size = Stream.of("A", "BB", "CCC")
    .peek(System.out::println)
    .count();

System.out.println("Element count: " + size); // 3
```

The `Stream.of(...)` source already knows there are three elements; `peek` does not change the count. On JDK versions that optimize `count` (since Java 9), traversing the source and calling `peek` may be skipped entirely. Therefore, **never rely on side effects in `peek`, `map`, or intermediate lambdas to guarantee that an important action has occurred**.

Unlike the example above, `filter` can change the number of elements:

```java
long longerThanOne = Stream.of("A", "BB", "CCC")
    .filter(s -> s.length() > 1)
    .count(); // 2
```

Here, the filter needs to be evaluated to determine the number of remaining elements, unless another semantics-preserving optimization is applied by the implementation.

**Usage rule:** treat `map`, `filter`, and `peek` as steps representing computations. If the goal is to produce a result, use an appropriate terminal operation; if the goal is to perform an action with side effects, make that action explicit at the consumption boundary rather than "hiding" it inside `peek`. `peek` is useful for observing during debugging, but it is not a guaranteed auditing mechanism.

## 6. Lifecycle: a pipeline can only be consumed once

Once a pipeline has been used for a terminal operation, that same Stream cannot be reused to perform another query:

```java
Stream<Integer> values = Stream.of(10, 20, 30);

long count = values.count(); // 3

// Invalid: the Stream has already been consumed.
// int first = values.findFirst().orElse(-1);
```

The second call typically throws `IllegalStateException`. Reuse detection is not guaranteed for every way of constructing a pipeline, so you must always follow the **one pipeline, one consumption** rule.

When you need two independent computations on the same re-traversable data, create two new Streams from the source:

```java
List<Integer> numbers = Arrays.asList(10, 20, 30);

long count = numbers.stream().count();
int total = numbers.stream().mapToInt(Integer::intValue).sum();
```

When a source is backed by a resource, finishing a terminal operation **does not mean the Stream automatically closes the resource**. For example, `Files.lines` opens a file-related resource and must be closed using `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.trim().isEmpty())
            .count();
    }
}
```

The `try` block guarantees calling `close()` even if processing throws an exception. With in-memory sources like `List.stream()`, there is normally no external resource to close.

> **Exception regarding traversal timing:** `iterator()` and `spliterator()` are classified as terminal operations because they terminate the ability to chain further pipeline steps, yet they return an object for traversal; elements may only actually be pulled through intermediate steps when that object is used. Therefore, the accurate statement is that a terminal operation **triggers or sets up consumption**, not that every terminal operation traverses all data immediately within the call.

## 7. When switching to a parallel stream, do not rely on execution schedule

Laziness still exists when calling `parallel()`; assembling the pipeline does not automatically execute it across multiple threads. However, when the terminal operation consumes data, elements may be processed concurrently, with no guarantee that messages from `peek` or operations inside `map` appear in source order.

```java
List<Integer> result = IntStream.rangeClosed(1, 8)
    .parallel()
    .map(n -> n * 2)
    .boxed()
    .collect(Collectors.toList());

// For a source with encounter order, the result is still in order: [2, 4, ..., 16].
// Do not infer that the map calls occurred in the order 1, 2, ..., 8.
```

`findFirst` preserves the concept of "first" on a source with encounter order, whereas `findAny` is allowed to return any element. `forEach` on a parallel Stream does not guarantee order; `forEachOrdered` guarantees encounter order when an order exists, but may reduce the benefit of parallelism. Stateful and order-constrained steps (such as `sorted`, `distinct`, `limit` on an ordered source) can also increase synchronization/buffering overhead.

Therefore, prefer lambdas **without shared state and independent of execution order**. Do not count how many times a lambda runs or write to unsynchronized shared data to infer how many elements were processed.

## 8. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Calling `filter` means the list has already been filtered." | `filter` usually only adds a step to the pipeline; the terminal operation is what requests the data. |
| "`map` runs completely before `filter` runs." | For stateless steps in a sequential pipeline, processing is typically fused element by element in declaration order. |
| "A terminal operation always traverses the entire source." | Terminal operations like `findFirst` and `anyMatch` can short-circuit; the intermediate `limit` can also reduce the number of elements needed. |
| "`sorted` can still get the first result immediately." | Sorting typically must observe the entire finite input before emitting the first element. |
| "Calling `count` guarantees `peek` will print." | `count` can use a known size and skip intermediate steps that do not affect the count. |
| "You can call `count` and then `collect` on the same Stream." | A consumed Stream cannot be reused; create a new Stream from a re-traversable source. |
| "A terminal operation automatically closes a file Stream." | Resource-backed Streams must be closed using `close` or `try-with-resources`. |

## 9. Self-check

**Scenario A.** What does the following code print, and when does the `"map"` line appear?

```java
Stream<Integer> s = Stream.of(1, 2, 3)
    .map(n -> {
        System.out.println("map " + n);
        return n * 10;
    });
System.out.println("ready");
int value = s.findFirst().orElse(-1);
System.out.println(value);
```

**Answer:** With a sequential and ordered Stream, it prints `ready`, `map 1`, `10`. Before `findFirst()`, the `map` step has not processed any elements yet. `findFirst()` only needs the first element, so there is no need to map `2` and `3`.

**Scenario B.** To get the three smallest numbers from a finite list, should `limit(3)` be placed before or after `sorted()`?

**Answer:** Place `sorted().limit(3)` to examine the entire input and then select the three smallest numbers. `limit(3).sorted()` only sorts the first three elements of the source, which can give a different result.

**Scenario C.** Why can `Stream.generate(supplier).limit(5).collect(Collectors.toList())` terminate even though the source has no natural stopping point?

**Answer:** `limit(5)` lets at most five elements pass through; once the terminal operation has taken five elements, the pipeline does not need to call `supplier` anymore. If a step that must consume the entire source, such as `sorted()`, is placed **before** `limit(5)`, this ability to terminate is lost.

## Key takeaway

Laziness enables the Java Stream API to **declare how to process upfront, and execute only what is necessary when consumption is demanded**. To reason about a pipeline, ask yourself in order: when is the source created; which intermediate steps might need state; how much data does the terminal operation need; are there any short-circuiting or step-skipping optimizations; has the Stream already been consumed or does it need resource closing? Answering these questions is the foundation for using `filter`, `map`, `reduce`, and `collect` in accordance with the Stream lifecycle contract.
