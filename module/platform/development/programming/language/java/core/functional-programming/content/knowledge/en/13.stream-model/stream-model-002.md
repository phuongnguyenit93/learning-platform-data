# Data Sources, Intermediate Operations, and Terminal Operations in Java Stream

The Java Stream API allows you to describe the processing of a sequence of elements as a **pipeline**: taking elements from a source, applying transformations or filters, and then using a terminal operation to produce the desired result or effect. This is an important model in functional programming with Java: we pass **behaviors** such as `Predicate`, `Function`, `Comparator`, and `Consumer` into the API, instead of manually writing loops for each stage.

A typical Stream pipeline has the form:

~~~text
Data source
   |
   v
Intermediate operations: filter → map → sorted → ...
   |
   v
Terminal operation: toList / collect / count / reduce / forEach / ...
   |
   v
Result or effect
~~~

Example:

~~~java
List<String> names = List.of("An", "Binh", "Chi", "Anh");
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .map(String::toUpperCase)
        .toList();
// selected == [AN, ANH]
~~~

The code snippet requires `import java.util.List;` and must be inside a method. `names.stream()` creates a Stream from the source; `filter` and `map` are intermediate operations; `toList()` is a terminal operation. Each of these concepts has its own contract, and their differences determine how the pipeline is executed.

## 1. Data source: where does a Stream get its elements?

A **source** is where the pipeline obtains its initial elements. A Stream does not necessarily hold a pre-existing copy of all elements; it usually describes how to **traverse the source when the pipeline is executed**.

Common sources in Java 17+:

| Source | Example | Notes |
| --- | --- | --- |
| Collection | `list.stream()` | Traverses the elements in the collection |
| Parallel collection | `list.parallelStream()` | Capable of parallel processing; effectiveness should be considered |
| Object array | `Arrays.stream(array)` | Creates a stream over array elements |
| Primitive array | `Arrays.stream(intArray)` | Returns `IntStream` instead of `Stream<Integer>` |
| Explicit values | `Stream.of("A", "B")` | Creates a stream from an argument list |
| Nullable value | `Stream.ofNullable(value)` | Stream of 0 or 1 element |
| Numeric range | `IntStream.range(1, 4)` | Numbers 1, 2, 3; end is exclusive |
| Element generation | `Stream.generate(supplier)` | Usually infinite, so it needs a stopping condition |
| Iterative sequence | `Stream.iterate(seed, next)` | Usually infinite in the two-argument overload |
| Text file | `Files.lines(path)` | Stream backed by an I/O resource; must be closed |

The corresponding classes from `java.util`, `java.util.stream`, and `java.nio.file` must be imported. The examples in the table are standalone expressions, not complete programs.

### A Stream is not a Collection

- A **Collection** stores and organizes elements; it may allow adding/removing and traversing multiple times.
- A **Stream** expresses a computation over a source and can only be **consumed once**. It does not provide operations for storing, adding, or removing elements.
- Stream processing usually **does not modify the source collection**. However, this is not a guarantee that side effects are forbidden by the type system; a mutating lambda can still break correctness. `List.sort(...)` is a Collection API that mutates the list, whereas `stream.sorted(...)` describes the order of the Stream's result.
- A Stream can produce a new collection result using `toList()` or `collect(...)`. That result is a separate object; it does not turn the Stream into a re-traversable container.

For example, creating a stream is not the same as creating a copy of a list:

~~~java
List<String> data = new ArrayList<>(List.of("a", "b"));
Stream<String> stream = data.stream(); // Build source
// Do not structurally modify data while the pipeline is being traversed.
List<String> copy = stream.toList();
~~~

The code snippet requires importing `List`, `ArrayList`, and `Stream`. Interfering with the source while the pipeline is running violates the *non-interference* principle (except in cases where the source supports concurrency by contract). If a fixed snapshot of the data is needed, proactively create a copy of the input before using it.

### Finite and infinite sources

`IntStream.range(0, 10)` is finite; `Stream.generate(Math::random)` is usually infinite. A pipeline on an infinite source needs an operation that can stop, such as `limit(n)` (under appropriate conditions) or a short-circuiting terminal like `findFirst()`. Ending with `count()` on an infinitely generating pipeline with no stopping bound will not complete.

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();
// [1, 2, 3, 4, 5]
~~~

You should not arbitrarily use an infinite source with `sorted()`, because sorting all data requires seeing all elements before returning a result.

## 2. Intermediate operations

Intermediate methods return **a new Stream**, so multiple steps can be chained together. Calling them to build a pipeline usually **does not traverse the source or execute lambdas yet**. Actual work is deferred until a terminal operation demands a result.

Common intermediate operations:

| Operation | Role | Example |
| --- | --- | --- |
| `filter(predicate)` | Keeps only elements matching the condition | `filter(n -> n > 0)` |
| `map(mapper)` | Transforms each element into another element | `map(String::length)` |
| `mapToInt / mapToLong / mapToDouble` | Converts into a primitive stream | `mapToInt(String::length)` |
| `flatMap(mapper)` | Flattens sub-streams created from each element | `flatMap(List::stream)` |
| `distinct()` | Removes duplicates based on `equals` | `distinct()` |
| `sorted()` / `sorted(comparator)` | Sorts according to an order | `sorted(Comparator.reverseOrder())` |
| `peek(action)` | Observes elements being processed; mainly used for diagnostics | `peek(System.out::println)` |
| `limit(n)` | Keeps at most the first `n` elements in a determinable order | `limit(10)` |
| `skip(n)` | Skips the first `n` elements | `skip(5)` |
| `takeWhile(predicate)` | Takes the prefix while the condition holds on an ordered stream | `takeWhile(n -> n < 10)` |
| `dropWhile(predicate)` | Drops the prefix while the condition holds on an ordered stream | `dropWhile(n -> n < 10)` |

Each intermediate operation accepts and returns an appropriate stream type: `Stream<T>`, `IntStream`, `LongStream`, or `DoubleStream`. For example:

~~~java
IntStream numbers = Stream.of("10", "20", "30")
        .mapToInt(Integer::parseInt);
int total = numbers.sum(); // 60
~~~

`sum()` is a terminal operation of `IntStream`. With regular `map`, the pipeline remains a `Stream<Integer>`, and to sum the elements you can use `mapToInt(Integer::intValue).sum()` or `reduce(...)`.

### Stateless and stateful intermediate operations

**Stateless**: `map` and `filter` usually process each element without needing to retain many other elements; they are suitable for fusing and processing element-by-element when the terminal is called.

**Stateful**: `sorted`, `distinct`, or certain limiting/prefix operations need to observe or remember state across elements. For example, `sorted` must have global information to produce a sorted order on a finite source, even though each call to `sorted()` when building the pipeline is still lazy.

This difference affects performance, memory, and short-circuiting behavior. `sorted()` on a large dataset usually consumes extra memory; `distinct()` needs to track seen values; `limit()` and `skip()` on an ordered parallel stream can incur coordination overhead.

## 3. Terminal operations: when the pipeline is requested to compute

A terminal operation is the step that **consumes the stream**, usually producing a final result, returning `void`, or performing an effect. After a terminal operation, the stream cannot be reused.

| Terminal | Result / purpose | Notes |
| --- | --- | --- |
| `toList()` | Resulting `List<T>` | Java 16+; the list does not support structural modification operations |
| `collect(collector)` | Collects into a collection/map/other summary | Structure and mutability depend on the collector |
| `count()` | `long` count of elements | May be optimized without running every intermediate step |
| `forEach(action)` | Executes an action, returns `void` | Order is not guaranteed for parallel streams |
| `forEachOrdered(action)` | Executes an action in encounter order when present | Parallel execution may incur overhead to preserve order |
| `reduce(...)` | Combines elements using an associative operator | Requires an associative function, especially in parallel |
| `min(...)` / `max(...)` | `Optional<T>` extreme element | Empty stream returns empty |
| `findFirst()` | `Optional<T>` first element in encounter order | Can short-circuit |
| `findAny()` | `Optional<T>` any element | Useful when order is not needed, especially in parallel |
| `anyMatch / allMatch / noneMatch` | `boolean` condition check | Can short-circuit |

Some terminals return new data, while others only print/send/save results. The key point is that **it triggers evaluation of the pipeline as needed** and marks the stream as consumed.

Example:

~~~java
long count = List.of("Java", "Stream", "API").stream()
        .filter(s -> s.length() >= 4)
        .count(); // 2: "Java", "Stream"
~~~

`count()` requires the number of elements remaining after filtering, so the filter must affect the result. However, you should not rely on how many times an intermediate lambda runs if its only job is a side effect; Java is allowed to optimize the pipeline as long as the result remains equivalent.

### Returning a list with two APIs

`stream.toList()` (Java 16+) returns a List that does not support methods that modify its contents or structure. `stream.collect(Collectors.toList())` returns a list whose implementation type and mutability are **not guaranteed by the API**. If a mutable list is needed, state the intent explicitly:

~~~java
List<String> mutableCopy = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
mutableCopy.add("new");
~~~

This snippet requires importing `List`, `Collectors`, and `ArrayList`, and a `source` variable of an appropriate type. Do not assume every collector result is always mutable if the contract does not promise it.

## 4. Lazy evaluation: intermediate operations do not run when only building the pipeline

The following example shows only a fragment of a valid Java program:

~~~java
Stream<String> pipeline = List.of("a", "bb", "ccc").stream()
        .filter(s -> {
            System.out.println("checking " + s);
            return s.length() > 1;
        });
System.out.println("built");
List<String> result = pipeline.toList();
~~~

When `filter(...)` is called to build the pipeline, `System.out.println("checking ...")` **does not run yet**. The line `built` is printed first; only when `toList()` is reached is the source traversed. `filter` takes a `Predicate<String>`, which runs when elements are needed. The complete program in section 6 clearly illustrates this along with verified output.

**Lazy does not mean "automatically runs in the future"**. A pipeline without a terminal operation may do nothing other than construct a structure describing the computation. To get a result, a terminal is needed; to keep the result for repeated use, materialize it with `toList()` or an appropriate collection.

### Fusion: processing each element through multiple steps

Given the pipeline:

~~~java
source.stream()
        .filter(this::eligible)
        .map(this::normalize)
        .forEach(this::save);
~~~

This is an illustrative snippet inside an instance method that has `source` and the corresponding methods. When the terminal runs, stateless steps are typically fused into **a single pass**: the first element goes through filter, then map, then terminal, followed by the next element. You should not picture it as necessarily creating a full intermediate list for each `filter` or `map`.

Stateful operations such as `sorted()` act as boundaries that may need to gather/buffer data before forwarding it. Moreover, Stream has the right to organize and optimize execution according to its contract; you should not treat the order of every side effect inside lambdas as invariant, especially on parallel streams.

## 5. Short-circuit: not every terminal needs to read the entire source

Some operations can determine the result without traversing every element:

~~~java
boolean hasEven = IntStream.range(1, 1_000_000)
        .anyMatch(n -> n % 2 == 0); // true
~~~

`anyMatch` can stop as soon as it sees a matching element (`2`). `findFirst` can stop when it finds the first element; `findAny` can pick any matching element; `limit(5)` is an intermediate operation that **limits** the number of elements passed downstream. However, some operations placed before `limit`, such as `sorted()`, may still need to inspect the entire source to determine the order, so do not assume `limit(5)` always reads only 5 elements from the source.

Match-style terminals follow these rules for an empty Stream:

- `anyMatch(...)` returns `false`.
- `allMatch(...)` returns `true`.
- `noneMatch(...)` returns `true`.

These are the logical rules of quantifiers over an empty set; the predicate is not invoked when there are no elements.

### Do not confuse `limit` and `filter`

~~~java
List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .limit(2)
        .boxed()
        .toList();
// [2, 4]
~~~

`limit(2)` takes at most two elements **after filtering**, rather than taking two source elements first and then filtering. If you swap the order to `limit(2).filter(...)`, only 1 and 2 are considered, so the result is `[2]`. The position of operations affects both the result and performance.

## 6. Complete Java 17+ example: source → intermediate → terminal

Save the source code to the file **`StreamPipelineDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamPipelineDemo {
    record Order(String id, int total, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 100, true),
                new Order("B", 30, false),
                new Order("C", 150, true),
                new Order("D", 80, true)
        );

        Stream<String> pipeline = orders.stream()
                .filter(o -> {
                    System.out.println("filter: " + o.id());
                    return o.paid();
                })
                .map(o -> o.id() + "=" + o.total())
                .sorted();

        System.out.println("before terminal");
        List<String> result = pipeline.toList();
        System.out.println("result=" + result);

        int paidTotal = orders.stream()
                .filter(Order::paid)
                .mapToInt(Order::total)
                .sum();
        System.out.println("paidTotal=" + paidTotal);

        boolean highPaid = orders.stream()
                .anyMatch(o -> o.paid() && o.total() >= 150);
        System.out.println("highPaid=" + highPaid);

        List<String> top2 = orders.stream()
                .filter(Order::paid)
                .sorted(Comparator.comparingInt(Order::total).reversed())
                .limit(2)
                .map(Order::id)
                .toList();
        System.out.println("top2=" + top2);

        Map<Boolean, Long> counts = orders.stream()
                .collect(Collectors.groupingBy(Order::paid, Collectors.counting()));
        System.out.println("paidCount=" + counts.get(true)
                + ", unpaidCount=" + counts.get(false));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac StreamPipelineDemo.java
java StreamPipelineDemo
~~~

Exact output:

~~~text
before terminal
filter: A
filter: B
filter: C
filter: D
result=[A=100, C=150, D=80]
paidTotal=330
highPaid=true
top2=[C, A]
paidCount=3, unpaidCount=1
~~~

Explanation across the three layers:

1. **Source:** `orders` is a `List<Order>` with 4 elements; each call to `orders.stream()` creates a **new** pipeline on the same source.
2. **Intermediate:** the first pipeline runs `filter` to keep only paid orders, `map` into `id=total` strings, and then `sorted()` to sort the strings. Because the strings start with the alphabetical IDs A, C, D, the result is in that order.
3. **Terminal:** Before `toList()`, the program prints `before terminal`; only after that do the `filter: ...` lines appear. `toList()` creates the result list. `sum()` adds 100+150+80=330, `anyMatch` finds order C, `toList()` gives the top 2 as C and A, and `collect(groupingBy(..., counting()))` counts 3 paid orders and 1 unpaid order.

The program places print statements inside the filter **for learning observation**, not to use that side effect to produce business results. With parallel streams or optimizations, relying on the call count or print order of an intermediate lambda is unsafe. The example uses a `List` source with encounter order and a sequential pipeline, so the stdout shown above is deterministic.

`Collectors.groupingBy` returns a `Map` whose key iteration order is not guaranteed; the example directly accesses `counts.get(true)` and `counts.get(false)` to display stable output.

## 7. Lifecycle: build, consume once, create a new pipeline

After calling a terminal operation, the stream has been used. You must not reuse **the same Stream instance** to run another terminal operation:

~~~java
Stream<String> once = Stream.of("a", "b");
long count = once.count(); // 2
// Wrong: once has already been consumed.
// List<String> all = once.toList();
~~~

The second line, if uncommented, will throw `IllegalStateException` (stream has already been operated upon or closed). In some cases, reusing a pipeline can be detected even earlier, so the proper contract is **one-time use per Stream**.

To perform two independent computations on the same collection source:

~~~java
List<String> items = List.of("Java", "Stream", "API");

long count = items.stream().count();
List<String> sorted = items.stream().sorted().toList();
~~~

Each `items.stream()` creates a new Stream. If the source can only be read once, such as certain I/O streams, you must decide to compute within the same traversal, or store the data in an appropriate structure before reusing it. Do not try to hold onto and restart a consumed Stream.

If a pipeline is stored in a variable for logical reuse, you can use `Supplier<Stream<T>>` to create a new Stream each time:

~~~java
Supplier<Stream<String>> supplier =
        () -> List.of("Java", "Stream", "API").stream();

long count = supplier.get().count();
List<String> sorted = supplier.get().sorted().toList();
~~~

This is an illustrative snippet and requires importing `java.util.function.Supplier`, `java.util.stream.Stream`, and `java.util.List`.

## 8. Encounter order and parallel execution

**Encounter order** is the order in which an ordered source provides elements: `List` and arrays usually have an order; `HashSet` does not guarantee a fixed traversal order. Intermediate operations like `sorted` can establish an order; `unordered()` can relax the ordering requirement to allow optimizations.

When a sequential pipeline has a List source, `toList()` preserves the encounter order of the result after intermediate operations. With `parallelStream()`, Java can compute elements across multiple threads, but operations that must preserve encounter order by contract still have to do so. **`forEach` does not guarantee execution order**, whereas `forEachOrdered` executes the action in encounter order if one exists.

Example:

~~~java
List<Integer> values = List.of(1, 2, 3, 4);
List<Integer> doubled = values.parallelStream()
        .map(n -> n * 2)
        .toList();
// doubled == [2, 4, 6, 8]
~~~

Do not assume every parallel pipeline will be faster than a sequential one: small tasks, stateful operations (`sorted`, `distinct`), ordering requirements, and thread coordination overhead can degrade performance. If computation relies on `reduce`, the accumulator must be compatible with parallel combination (associativity), and avoid relying on shared state that could suffer from races.

Distinguish between:

- **`map` on Stream** transforms each element and returns a new Stream.
- **`forEach` terminal** takes a `Consumer`, only performs an action, and does not return a Stream for further chaining.
- **`collect` terminal** gathers data into a result; it is usually preferable to calling `forEach` and adding to a shared `ArrayList` when running in parallel.

## 9. Side effects, errors, and performance issues

### Do not rely on side effects in intermediate operations

The following code is very easy to misunderstand:

~~~java
List<String> data = List.of("a", "b", "c");
long count = data.stream()
        .peek(System.out::println)
        .count();
~~~

Even though `peek` takes a `Consumer`, Java can optimize the `count()` terminal on a source of known size, so **there is no guarantee that all three lines will be printed**. The purpose of `peek` is mainly for observation/diagnostics; do not treat it as a mandatory logging or database-writing mechanism.

Similarly, avoid writing `map(x -> {sendMail(x); return x;})` with the intent that sending email is the effect of the pipeline. For business logic with side effects, separate the decision-making part using Stream from the action-executing part, or use an appropriate terminal after determining ordering and error requirements.

### Exceptions do not automatically turn into empty results

~~~java
List<Integer> parsed = List.of("1", "oops", "3").stream()
        .map(Integer::parseInt)
        .toList();
~~~

When the terminal runs, the element `"oops"` causes `Integer.parseInt` to throw `NumberFormatException`; Stream does not automatically skip errors. If the requirement is to discard invalid values, you must design a safe parsing operation and filter according to clear rules. Do not overuse `filter(s -> s.matches("\\d+"))` if the application also has negative signs, locale formatting, or complex input rules.

### Non-interference and stateless lambdas

Functions in `filter`/`map` should produce results dependent only on their input, should not modify the source being traversed, and should not depend on shared variables that change across invocations. With parallel streams, unsynchronized side effects can cause race conditions and unstable results. Even on sequential streams, mutating the source during traversal can cause `ConcurrentModificationException` or unreliable behavior.

### Large sources, resources, and stateful operations

- `sorted()` needs to process the order of many elements and usually has to buffer; avoid applying it directly on an infinite stream.
- `distinct()` retains the set of seen values, so it consumes memory, especially with very large sources.
- `limit()`/`findFirst()` can short-circuit, but actual effectiveness depends on the order of operations and the source.
- `mapToInt(...).sum()` avoids boxing for integer summation.
- When using `Files.lines(path)`, the stream holds an open resource and needs to be closed with *try-with-resources*. Most pure collection Streams do not need `close()` called.

Example of closing a resource-backed stream:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

This snippet requires `import java.nio.file.Files;`, `import java.nio.file.Path;`, `import java.util.stream.Stream;`, a valid `Path` variable `path`, and an enclosing method that declares/handles `IOException`. This is a contextual snippet, not a standalone program. `try-with-resources` ensures `close()` is called even if an error occurs while reading.

## 10. Designing readable and contract-compliant pipelines

A good way to read a pipeline is to ask in order:

1. **Which source?** What are the `T` elements? Is the source ordered, finite or infinite, and does it need to be closed?
2. **Which intermediate transformations?** What does `filter` keep, how does `map` change types, what comparator does `sorted` need, and how many elements does `flatMap` expand? Do the operations change ordering or storage cost?
3. **Which terminal?** Do we need a `List`, count, sum, `Optional`, grouping map, or side effect? Does it require traversing everything?
4. **Does it need to run again?** If so, create a new stream from the source or store the result; do not reuse a consumed instance.
5. **Are there side effects or mutable data?** Ensure functions in the pipeline do not corrupt the source and keep logic stable, especially in parallel.

Quick reference table:

| Scenario | Choice |
| --- | --- |
| Select matching elements | `filter(predicate)` — intermediate |
| Transform one element into another value | `map(mapper)` — intermediate |
| Transform one element into multiple elements | `flatMap(mapper)` — intermediate |
| Reorder by a criterion | `sorted(comparator)` — intermediate |
| Take at most `n` elements | `limit(n)` — intermediate |
| Get a result list | `toList()` — terminal |
| Sum `int` values | `mapToInt(...).sum()` — terminal is `sum` |
| Group into a Map or another structure | `collect(collector)` — terminal |
| Check if any element matches | `anyMatch(predicate)` — terminal, can short-circuit |
| Execute an action for each result | `forEach(action)` — terminal |
| Sort an existing List in place | `list.sort(comparator)` — Collection API, not Stream |

When you clearly understand the three roles **data source → intermediate operations → terminal operation**, you will see that Stream is a model of *composable computation description* that is executed when a result is needed. The principles **lazy, single-use, short-circuit, encounter order, and non-interference** are the foundation for pipelines that are correct, maintainable, and have reasonable performance.