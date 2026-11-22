# Stream.builder() and Stream.concat() in Java

## Lesson Objectives

The Java Stream API provides several ways to create data sources for a pipeline. **`Stream.builder()`** is used when you need to add elements one by one during the source-building phase, while **`Stream.concat(a, b)`** concatenates two Streams into one Stream for further processing. Both belong to `java.util.stream.Stream`, but they solve two different problems: one **builds a source from elements**, while the other **combines two existing sources**.

After this lesson, you will be able to:

- Declare a `Stream.Builder<T>`, add elements using `add`/`accept`, and call `build()`.
- Understand the builder lifecycle: data-addition phase → `build` → the Stream can only be consumed once; do not continue modifying the builder after `build`.
- Distinguish between **creating a Stream/pipeline** and the moment a **terminal operation** actually requests element traversal.
- Concatenate two Streams using `concat`, preserving encounter order when both sources are ordered.
- Understand the effects of parallel sources, short-circuiting, resource closing, and concatenating multiple Streams.
- Choose `builder`, `concat`, or another solution based on the data structure and processing workload.
- Compile and run Java 17 examples, verify exact output, and avoid common mistakes.

## 1. Problem Statement: Creating Streams Is Not Just Stream.of()

For known elements, the simplest way is:

```java
Stream<String> names = Stream.of("An", "Bình", "Chi");
```

If you already have a `List<String>`, you can use `names.stream()`. However, there are situations where the data source is not fixed at the time you write the expression: you only add elements when a condition is met, or data is selected across multiple branches of an algorithm. `Stream.builder()` is suitable for building a finite source whose elements are added sequentially.

Another situation: you already have **two Streams** (for example, data from two computation stages) and want to process them using **a single pipeline**. `Stream.concat(first, second)` provides a concatenated Stream without requiring you to manually collect both sources into two lists and join them before processing.

These two APIs **do not replace each other**:

| Question | `Stream.builder()` | `Stream.concat(a,b)` |
| --- | --- | --- |
| What is the primary input? | Elements of type `T` added during construction | Two source Streams of compatible types |
| Result | A `Stream<T>` when `build()` is called | A `Stream<T>` concatenating two sources |
| Flexibility | Add 0, 1, or more elements conditionally | Combine all elements from two sources |
| When elements are provided | Elements are fed into the builder before `build` | Source elements are traversed when the pipeline demands them |
| Lifecycle concerns | Builder is only used to create one Stream | Both input Streams and the concatenated Stream are single-use |
| Need to close I/O sources? | Depends on how data and sources are provided | Closing the concatenated Stream closes both input Streams |

**Note:** A Stream is a model of operations on a data source, not a collection that allows arbitrary updates after processing has started. Both a Stream created from a builder and a concatenated Stream follow the **single-use** rule of the Stream API.

## 2. Stream.builder(): Building a Source Element by Element

### 2.1. Signature and Lifecycle

Primary API:

```java
public static <T> Stream.Builder<T> builder()
```

`Stream.Builder<T>` is an interface nested inside `Stream`; it extends `Consumer<T>` and has the key members:

```java
void accept(T element);
Stream.Builder<T> add(T element);
Stream<T> build();
```

This is an **abbreviated API signature for explanation**, not a class you need to define yourself. Meaning:

- `accept(element)` adds an element and returns `void`. Because Builder implements `Consumer<T>`, you can use it anywhere a Consumer is expected while the building phase is still open.
- `add(element)` also adds an element, but **returns the Builder** so you can chain calls like `builder.add(a).add(b)`.
- `build()` ends the element-addition phase and returns a `Stream<T>` containing the added elements in the builder's encounter order.

Example:

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("Java");
builder.accept("Lambda");

Stream<String> words = builder.build();
List<String> result = words.toList(); // [Java, Lambda]
```

In Java 17, `Stream.toList()` returns a structurally unmodifiable list and preserves encounter order if the Stream is ordered. Do not confuse this resulting list with an `ArrayList` on which you can call `add`.

### 2.2. add() for Chaining; accept() When You Don't Need the Builder Returned

```java
Stream<Integer> numbers = Stream.<Integer>builder()
        .add(10)
        .add(20)
        .add(30)
        .build();
```

`Stream.<Integer>builder()` explicitly specifies the type parameter so the compiler knows the elements are `Integer`. You can also use an explicitly typed variable and let the compiler infer the type:

```java
Stream.Builder<Integer> builder = Stream.builder();
builder.add(10).add(20);
Stream<Integer> numbers = builder.build();
```

These two snippets are **two separate illustrative options**; do not place them in the same scope with the same `numbers` variable name. `add` is convenient for chaining, while `accept` is often handy when passing the Builder into an API with a `Consumer<T>` contract. There is no difference in the element values added.

Example of a Consumer receiving data:

```java
Stream.Builder<String> builder = Stream.builder();
Consumer<String> sink = builder;

sink.accept("first");
sink.accept("second");

Stream<String> result = builder.build();
```

The snippet above illustrates the type relationship; you need to import `java.util.stream.Stream` and `java.util.function.Consumer`. Only pass the builder as a Consumer during the **building phase**; after `build`, you must not continue calling `accept`.

### 2.3. Building a Source Conditionally

A practical case:

```java
Stream.Builder<String> builder = Stream.builder();

builder.add("header");
if (includeDetails) {
    builder.add("details");
}
if (includeFooter) {
    builder.add("footer");
}

Stream<String> sections = builder.build();
```

This is an illustrative snippet; `includeDetails` and `includeFooter` need to be declared. If both flags are `false`, the result only has `header`; if both are `true`, the Stream has three elements in the order `header`, `details`, `footer`.

When elements are only decided across a few conditional branches, a builder makes the code more readable than creating multiple small Streams and concatenating them repeatedly. However, if you already have a collection built for another purpose, `collection.stream()` is usually simpler than copying every element into a builder.

### 2.4. Builder Can Create an Empty or Single-Element Stream

```java
Stream<String> empty = Stream.<String>builder().build();
Stream<String> one = Stream.<String>builder()
        .add("only")
        .build();
```

These are finite Streams with 0 and 1 element respectively. When there is no conditional data construction, `Stream.empty()` and `Stream.of("only")` are usually shorter and more expressive.

## 3. Lifecycle Limitations of Stream.Builder

After calling `build()`, the builder transitions to a built state. Calling `add`, `accept`, or `build` again on the same builder **throws `IllegalStateException`** per the API contract.

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("A");
Stream<String> source = builder.build();

// Do not do this: the builder has already been built.
builder.add("B"); // IllegalStateException
```

Do not think of a builder as a reusable list. If you need to create a new Stream, instantiate a new builder or store the data in a collection and create Streams from that collection.

In addition, **the Stream returned by `build` itself can only be consumed once**. Example:

```java
Stream<String> source = Stream.of("A", "B");
long count = source.count();

// Do not continue using source to run another terminal operation.
// source.toList() may throw IllegalStateException.
```

This is an illustrative snippet. A Stream does not allow forking or resetting like a list. If you need both counting and listing, you can store an appropriate intermediate result and continue working with the collection, or create a **new Stream** from a repeatable source.

**A Builder is not a structure meant for concurrent writes by multiple threads.** Do not share a Builder and concurrently call `add` from multiple threads without a proper synchronization contract. If data is produced concurrently, collect it using a thread-safe mechanism by design and then create a Stream after completion.

## 4. Stream.concat(): Concatenating Two Existing Sources

### 4.1. Signature

```java
public static <T> Stream<T> concat(
        Stream<? extends T> a,
        Stream<? extends T> b)
```

This is an abbreviated signature. `concat` creates a Stream consisting of the elements from `a`, followed by the elements from `b` in encounter order if both sources are ordered.

```java
Stream<String> left = Stream.of("A", "B");
Stream<String> right = Stream.of("C", "D");

Stream<String> combined = Stream.concat(left, right);

System.out.println(combined.toList()); // [A, B, C, D]
```

`concat` **does not mutate or add elements to `left` or `right`**. It creates a new Stream that depends on the two sources. After creating the concatenated Stream, you should not use `left` or `right` separately to execute another pipeline: they have already joined a concatenated pipeline and must not be treated as two independent sources that can be consumed arbitrarily.

Because the sources contain `String`, the output can be used as `Stream<String>`. With generics, Java can infer a suitable supertype when the two sources have different element types, but declare the type explicitly if type inference becomes too broad and loses domain type safety.

### 4.2. Empty Sources

```java
Stream<Integer> all = Stream.concat(
        Stream.<Integer>empty(),
        Stream.of(1, 2)
); // When collected: [1, 2]
```

If both sources are empty, the resulting Stream is empty. If you only need one Stream without a second source, there is no need to call `concat` unnecessarily.

### 4.3. concat Is Not a Key-Based Merge or Sort

`Stream.concat(a,b)` concatenates two sequences of elements; **it does not automatically sort, deduplicate, match keys, or interleave elements in ascending order**.

```java
Stream<Integer> left = Stream.of(1, 5);
Stream<Integer> right = Stream.of(2, 3);

List<Integer> joined = Stream.concat(left, right).toList();
// [1, 5, 2, 3]
```

If you need to sort the whole result, you can add `sorted()` after `concat`; if you need to remove duplicates, add `distinct()`. Both are pipeline operations with their own costs. In cases where two sources are individually sorted and you need a **linear ordered merge**, plain `concat` does not fulfill that task.

## 5. Lazy Traversal: When Does a Stream Actually Process Data?

Intermediate operations such as `filter` and `map` are typically lazy: they build a pipeline describing the work, but do not traverse elements until a terminal operation demands it.

```java
AtomicInteger examined = new AtomicInteger();

Stream<String> first = Stream.of("A", "B")
        .filter(s -> {
            examined.incrementAndGet();
            return true;
        });
Stream<String> second = Stream.of("C", "D")
        .filter(s -> {
            examined.incrementAndGet();
            return true;
        });

Stream<String> combined = Stream.concat(first, second);

System.out.println(examined.get());     // 0
System.out.println(combined.toList());  // [A, B, C, D]
System.out.println(examined.get());     // 4
```

In the illustration, `AtomicInteger` is used to observe how many elements have passed through `filter`. Right after `concat`, there is no terminal operation yet, so `examined` is still `0`. When `toList()` traverses the pipeline, four elements pass through the filters and the count becomes `4`.

**Distinction:** the fact that a Stream **has not traversed elements yet** does not mean all source-creation expressions are lazy. Java evaluates arguments before invoking a method:

```java
Stream<String> combined = Stream.concat(
        loadLeftStream(),
        loadRightStream()
);
```

If `loadLeftStream()` and `loadRightStream()` write logs or open resources when **creating the Stream objects**, those side effects have already occurred during argument evaluation, before the terminal operation. Only the data traversal inside the pipeline can be deferred.

Therefore, when you want to defer expensive source creation as well, do not assume `concat` automatically defers factory calls. Design an appropriate factory, Supplier, or orchestration layer instead; do not use ad-hoc tricks that keep resources open arbitrarily.

### Short-Circuiting May Not Traverse Everything

```java
Optional<Integer> first = Stream.concat(
        Stream.of(1, 2),
        Stream.of(3, 4)
).findFirst(); // Optional[1]
```

`findFirst` only needs the first element of a Stream with encounter order and can complete before traversing the remaining elements. In this sequential example, there is no need to process the entire input to find the result. However, when using a parallel Stream, an unordered source, or an intermediate operation with side effects, do not treat the number of callback invocations as a stable business contract.

In particular, **`peek`, `filter`, or `map` with side effects** is not a reliable mechanism for producing a business effect exactly once across every pipeline: some terminal operations may optimize traversal, and short-circuiting may skip elements. Keep callbacks pure whenever possible.

## 6. Complete Java 17 Program

The following example combines builder, concat, builder lifecycle verification, lazy filter, close handlers, and parallel state. It uses fixed values so stdout can be verified exactly.

Create the file **`StreamBuilderConcatDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamBuilderConcatDemo {
    public static void main(String[] args) {
        Stream.Builder<String> builder = Stream.builder();
        builder.add("Java");
        builder.accept("Lambda");
        Stream<String> built = builder.build();
        System.out.println("Builder: " + built.toList());

        try {
            builder.add("Later");
        } catch (IllegalStateException ex) {
            System.out.println("Builder reused: IllegalStateException");
        }

        AtomicInteger examined = new AtomicInteger();
        Stream<String> left = Stream.of("A", "B")
                .filter(s -> {
                    examined.incrementAndGet();
                    return true;
                });
        Stream<String> right = Stream.of("C", "D")
                .filter(s -> {
                    examined.incrementAndGet();
                    return true;
                });
        Stream<String> combined = Stream.concat(left, right);
        System.out.println("Before terminal: " + examined.get());
        System.out.println("Concat: " + combined.toList());
        System.out.println("After terminal: " + examined.get());

        List<Integer> numbers = Stream.concat(
                Stream.of(1, 2),
                Stream.<Integer>builder().add(3).add(4).build()
        ).toList();
        System.out.println("Numbers: " + numbers);

        try (Stream<String> joined = Stream.concat(
                Stream.of("L").onClose(
                        () -> System.out.println("close left")),
                Stream.of("R").onClose(
                        () -> System.out.println("close right"))
        )) {
            System.out.println("Joined: " + joined.toList());
        }

        boolean parallel = Stream.concat(
                Stream.of(1, 2).parallel(),
                Stream.of(3, 4)
        ).isParallel();
        System.out.println("Parallel flag: " + parallel);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StreamBuilderConcatDemo.java
java StreamBuilderConcatDemo
```

**Exact stdout:**

```text
Builder: [Java, Lambda]
Builder reused: IllegalStateException
Before terminal: 0
Concat: [A, B, C, D]
After terminal: 4
Numbers: [1, 2, 3, 4]
Joined: [L, R]
close left
close right
Parallel flag: true
```

**Order explanation:**

1. `builder.add` and `builder.accept` insert two strings. `build().toList()` produces a list in the order `Java`, `Lambda`.
2. The builder is already in the built state. `builder.add("Later")` throws `IllegalStateException`, which is caught so the program continues.
3. Two `filter` pipelines are created but not yet consumed; `examined` is `0` when the `Before terminal` line is printed.
4. `combined.toList()` triggers traversal of both sources. With filters always returning `true` and no short-circuiting, `examined` increments to `4`; the list is `[A, B, C, D]`.
5. `Stream.concat` can take a Stream directly from `Stream.of` and a Stream built with Builder. The result is `[1, 2, 3, 4]`.
6. `joined.toList()` prints the list `[L, R]`. Upon exiting `try-with-resources`, `joined.close()` is called and runs both `onClose` handlers in the order associated with the two sources, printing `close left` then `close right`.
7. By the `Stream.concat` contract, the resulting Stream is parallel if **either** of the two input Streams is parallel; `isParallel()` returns `true`. This does not mean every terminal operation is guaranteed to use multiple threads or always run faster.

The example has been verified with the compiler using **`--release 17`** compatibility; the methods `Stream.toList()`, `Stream.Builder`, and `Stream.concat` are all available in Java 17.

## 7. Resource Management and onClose()

A Stream from `List.stream()` or `Stream.of(...)` typically does not hold I/O resources that need closing. However, a Stream from `Files.lines(path)` can hold an open resource. For this kind of Stream, **a terminal operation does not automatically close the Stream**. You should use `try-with-resources`.

```java
// Illustration: pathA, pathB are valid java.nio.file.Path instances;
// the enclosing method must handle or declare IOException.
try (Stream<String> all = Stream.concat(
        java.nio.file.Files.lines(pathA),
        java.nio.file.Files.lines(pathB)
)) {
    all.forEach(System.out::println);
}
```

This illustrative snippet is not standalone: you need to declare `pathA`, `pathB` and handle `IOException`. When `all.close()` runs, the concatenated Stream closes both source Streams. `Stream.concat` does not mean "each source closes itself as soon as traversal finishes".

### 7.1. Closing the Concatenated Stream Closes Both Sources

By the API contract, closing the Stream returned by `concat(a,b)` calls `close` on both `a` and `b`. The complete sample code already demonstrated this with two `onClose` handlers.

Manage resources **at the proper point of ownership**. Do not rely on the garbage collector cleaning up the Stream to close files; nor should you close a source Stream too early while still expecting to process the concatenated Stream.

### 7.2. Exception When Creating the Second Source

With the expression:

```java
Stream<String> all = Stream.concat(
        Files.lines(pathA),
        Files.lines(pathB)
);
```

Java evaluates the two arguments from left to right. If opening source A succeeds but opening source B throws `IOException` **before the `concat` call takes place**, the concatenated Stream object has not yet been created to manage closing A. To avoid leaks when opening multiple sources can fail, manage resources right at the moment of opening:

```java
// Illustration inside a method that throws IOException, with pathA/pathB.
try (Stream<String> first = Files.lines(pathA)) {
    try (Stream<String> second = Files.lines(pathB)) {
        Stream.concat(first, second).forEach(System.out::println);
    }
}
```

The two `try` blocks ensure that if opening B fails, A is still closed. With a concatenated Stream managed at an outer `try`, there can be other resource-ownership designs; the important thing is to ensure **every opened source has a closing path**, even if creating the next source fails.

When a `close` handler throws an exception, Java applies its corresponding exception and suppressed-exception rules. Do not rely on side effects of a close handler to perform mandatory business updates in situations where the system may encounter resource-closing errors.

## 8. Concatenating Streams in Sequential and Parallel Processing

`Stream.concat(a,b)` returns a parallel Stream if either of the two input Streams is parallel:

```java
boolean parallel = Stream.concat(
        Stream.of(1, 2).parallel(),
        Stream.of(3, 4)
).isParallel(); // true
```

`isParallel()` only indicates the mode of the pipeline; it does not prove that execution time will be faster. With two imbalanced sources, overhead and work-splitting characteristics can make parallel performance fall short of expectations.

**Encounter order:** if both sources are ordered, the concatenated result is ordered, containing elements of source A first and then source B. In a parallel pipeline, elements may be processed on different threads, and observing side effects in `forEach` may not follow encounter order. If you must process side effects in order on an ordered Stream, consider `forEachOrdered` and understand the serialization cost.

**Size and spliterator characteristics:** the `concat` API does not guarantee preserving all optimization characteristics of both sources; in particular, `DISTINCT` and `SORTED` on each individual Stream do not mean the entire concatenated Stream is distinct/sorted. When the estimated total size risks overflowing `long`, the `SIZED` characteristic may be lost. Do not rely on spliterator metadata as a business contract.

**Repeated concatenation:** a small tree like `Stream.concat(Stream.concat(a,b),c)` usually works fine. However, nesting many Streams too deeply can lead to long call chains or a `StackOverflowError` when accessing/traversing; the Stream API documentation also warns against deep concatenation. If you have many sources, consider a solution suited to the source structure and resource lifecycle instead of calling `concat` tens of thousands of times in a loop.

## 9. When There Are More Than Two Sources

Suppose you need to combine three sources:

```java
Stream<Integer> first = Stream.of(1);
Stream<Integer> second = Stream.of(2);
Stream<Integer> third = Stream.of(3);

List<Integer> result = Stream.concat(
        Stream.concat(first, second),
        third
).toList(); // [1, 2, 3]
```

This style is reasonable for a small, fixed number of sources. However, if the sources are a **collection of Streams**, you can use `flatMap`:

```java
List<Stream<Integer>> sources = List.of(
        Stream.of(1, 2),
        Stream.of(3),
        Stream.of(4, 5)
);

List<Integer> result = sources.stream()
        .flatMap(s -> s)
        .toList(); // [1, 2, 3, 4, 5]
```

In a pipeline following encounter order, `flatMap` flattens the existing sources without building a deeply nested chain of `concat` calls. `flatMap` processes/closes each mapped Stream according to the operation's contract; if the sources involve I/O, you must still clearly design ownership, error handling during source creation, and overall resource closing.

If you do not actually need to keep each source as a separate Stream, you can create a single Stream from the elements right away using `Stream.builder()` or directly from a collection. Do not build multiple Streams and concatenate them just to avoid a simple element-addition loop.

## 10. Null Values and Type Safety

### 10.1. Stream.Builder Can Accept Null Elements

For reference Streams, a builder can add `null`:

```java
Stream<String> values = Stream.<String>builder()
        .add("A")
        .add(null)
        .build();
```

The code above creates a Stream containing a `null` element. Whether a terminal operation accepts null depends on the subsequent operations. For example, `.map(String::length)` on a Stream containing null can throw a `NullPointerException` when it reaches the null element. Do not confuse this with `List.of(...)`, which forbids null elements when creating a list.

### 10.2. The Stream Arguments to concat Themselves Must Not Be Null

```java
Stream<String> all = Stream.concat(
        null,
        Stream.of("A")
); // NullPointerException
```

This snippet illustrates the error. An **empty** Stream should be represented by `Stream.empty()`, not a `null` Stream reference.

If a source might not exist, decide at the source-creation layer:

```java
Stream<String> left = available
        ? obtainStream()
        : Stream.empty();
Stream<String> all = Stream.concat(left, Stream.of("fallback"));
```

The snippet above assumes `available` and `obtainStream()` already exist. If `obtainStream()` can return `null`, you need to fix the source contract or check explicitly before calling `concat`; `available == true` does not automatically guarantee non-null.

### 10.3. Generics and Element Types

`Stream.concat` accepts two `Stream<? extends T>`. If you accidentally mix sources whose element types are incompatible with the desired result type, the compiler may reject it or infer an overly broad supertype. Declare the type argument, use mapping to normalize to the domain type, or choose a common collection with the same `T`.

Example:

```java
Stream<Number> values = Stream.concat(
        Stream.of(1, 2),
        Stream.of(3.5, 4.5)
);
```

`Integer` and `Double` are both subtypes of `Number`, so using `Stream<Number>` here makes sense. However, if downstream logic requires operations specific to `Integer`, you should convert the data intentionally rather than casting during traversal.

## 11. Builder, concat, or Another API?

| Case | Preferred | Reason |
| --- | --- | --- |
| A few fixed elements | `Stream.of(a,b,c)` | Concise, no builder needed |
| No elements | `Stream.empty()` | Expresses emptiness directly |
| A single potentially null element | `Stream.ofNullable(value)` | Explicitly returns 0 or 1 element |
| Elements added across conditional branches | `Stream.builder()` | Builds the source before processing |
| Already have a collection | `collection.stream()` | Avoids copying data into a builder |
| Two existing Streams to traverse sequentially | `Stream.concat(a,b)` | Concatenates two sources directly |
| A list of Streams | `streamOfStreams.flatMap(...)` | Avoids deeply nested concat chains |
| Generating a regular, finite sequence of numbers | `IntStream.range / rangeClosed` | Avoids mutable counters in Builder |
| Generating data via a Supplier | `Stream.generate(supplier)` with a stopping condition | Suitable for on-demand generation |
| Iterative computation via state transition | `Stream.iterate(...)` | Expresses value evolution |

Evaluate the data structure and semantics before choosing. A source that must hold an open resource is different from `String` elements in memory, even though both are called a Stream.

## 12. Common Mistakes

1. **Calling `add` after `build`:** The builder is already finalized and will throw `IllegalStateException`.
2. **Using one Stream for multiple terminal operations:** A Stream is single-use; you must create a new one or store the result.
3. **Thinking `concat` executes the entire pipeline immediately:** No; intermediate operations are generally lazy until a terminal operation is invoked.
4. **Thinking `concat` also defers factory calls that create its arguments:** Java still evaluates argument expressions immediately when calling `concat`.
5. **Believing `concat` automatically sorts or deduplicates:** The result is just concatenation; use `sorted` and `distinct` if the contract requires them.
6. **Calling `Stream.concat` with either argument being null:** Throws `NullPointerException`; use `Stream.empty()` when empty.
7. **Forgetting to close a Stream containing I/O:** Terminal operations do not close automatically; use `try-with-resources`.
8. **Opening two sources directly in arguments without handling failure of the second:** If the second source throws an error, the first source may be leaked; manage each opened source individually.
9. **Nesting `concat` too deeply for a large number of Streams:** Can create a deep pipeline tree and risk stack overflow; choose `flatMap` or another source design.
10. **Assuming all operations run sequentially:** `concat` will be parallel if either input is parallel; pay attention to order and side effects.
11. **Adding mutable data while forgetting the source is not concurrency-safe:** Builders and mutable collections are not thread-safe on their own.
12. **Confusing Builder with an accumulator for parallel reduction:** Builder is primarily for the source-creation phase; do not use a shared Builder to collect elements from a parallel Stream.
13. **Thinking close handlers are called after `toList` without calling `close`:** Close handlers are only invoked when the Stream is closed (directly or via try-with-resources).
14. **Keeping source Streams after concat for further use:** Those Streams are already linked to the pipeline; do not treat them as independent sources that can be re-consumed.

## 13. Practice Exercises

**Exercise 1.** Write a `Stream.Builder<String>` that adds `"core"`, adds `"optional"` only if a flag is `true`, and then calls `build().toList()`. Predict the result when the flag is `true` and `false` respectively.

**Exercise 2.** Create an integer Stream using `Stream.<Integer>builder().add(1).add(2).build()`. Explain why you cannot add `3` after `build()`.

**Exercise 3.** For `Stream.concat(Stream.of(2,4), Stream.of(1,3))`, what is the result of `toList()`? Is it automatically sorted?

**Exercise 4.** Explain the difference between creating `Stream.concat(openA(), openB())` and calling `toList()` afterward. If `openA()` and `openB()` log when creating the source, when are the log lines printed?

**Exercise 5.** Use `AtomicInteger` to count the elements that actually pass through `filter` on two concatenated sources; why is the counter value still `0` before the terminal operation?

**Exercise 6.** If source A involves file I/O and source B involves file I/O, why is `try-with-resources` needed? How do you prevent a leak if opening file B fails after opening A succeeds?

**Exercise 7.** Concatenate three Streams using `concat`; then rewrite it using `Stream.of(s1,s2,s3).flatMap(s -> s)`. State the benefit of the second approach when the number of sources grows large.

**Exercise 8.** What does `Stream.concat(Stream.of(1).parallel(), Stream.of(2)).isParallel()` return? Does that guarantee the program will process across multiple threads?

**Exercise 9.** Distinguish between `Stream.<String>builder().add(null).build()` and `Stream.concat(null, Stream.empty())`: which case can create a Stream, and which case throws an error?

**Exercise 10.** A pipeline uses `peek` to record a payment event for each element. Why should you not rely on `peek` to perform critical business side effects?

### Answer Hints

1. Flag true → `[core, optional]`; false → `[core]`.
2. The builder transitions to the built state and rejects further element-addition operations.
3. `[2, 4, 1, 3]`; concat does not sort.
4. The `openA/openB` calls happen during argument evaluation to create the sources; element traversal happens when the terminal operation requests it.
5. `filter` is an intermediate operation; without traversal, the body is not executed on elements.
6. A Stream may hold resources; manage each source in a try scope or equivalent closing mechanism to handle failures when opening subsequent sources as well.
7. The `flatMap` approach avoids a deeply nested `concat` tree.
8. `true`, but it is only the parallel mode; it does not guarantee thread count or speed.
9. Builder can contain null elements; concat requires the input Stream objects themselves to be non-null.
10. Optimizations and short-circuiting may cause the callback not to execute as expected; use a dedicated orchestration layer for mandatory business operations.

## Conclusion

**`Stream.builder()` creates a source from elements fed in before `build()`; `Stream.concat(a,b)` combines two existing Streams to form a concatenated pipeline.** Both are used in Java 17 and share the rule that a Stream can only be consumed once.

In practical application, clearly distinguish between **source-building time** and **source-traversal time**, preserve order if required, manage closing for I/O sources, and avoid uncontrolled side effects in pipelines. If a problem only involves a few elements or already has a collection, choose a more concise API instead of using Builder or concat merely for form's sake.
