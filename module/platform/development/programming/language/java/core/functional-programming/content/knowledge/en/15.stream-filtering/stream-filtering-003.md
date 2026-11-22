# `limit()` and `skip()` in Java Stream

`limit(long maxSize)` and `skip(long n)` are two **intermediate operations** used to select a slice of elements from a stream. Both are declared on `java.util.stream.Stream` (and have corresponding versions on `IntStream`, `LongStream`, and `DoubleStream`). They commonly appear in problems such as **taking the first N elements**, **skipping the first N elements**, **paginating data**, or **bounding a continuous data-generating source**.

The key point is: "first" is understood according to the **encounter order** if the stream has an element encounter order; the result also depends on where `limit`/`skip` is placed in the pipeline and how the stream is executed.

## 1. Understanding the two methods accurately

| Method | Meaning | Number of elements that can be emitted | Return value |
| --- | --- | --- | --- |
| `limit(n)` | Keeps at most the first `n` elements of the stream at the operation's position | From 0 to `n` (if upstream terminates) | A new stream containing at most `n` elements |
| `skip(n)` | Skips the first `n` elements of the stream at the operation's position, taking the remaining ones | 0 if the source does not have enough elements; if the source is finite, at most `size - n` | A new stream with the prefix skipped |

Both take a `long` parameter, which must be **non-negative**; passing a negative number throws `IllegalArgumentException`. `limit(0)` creates an empty stream, while `skip(0)` logically keeps all elements. The value `n` can be greater than the number of source elements; `skip` then returns an empty stream, while `limit` only returns the number of elements that actually exist.

Visual example with an ordered stream `[10, 20, 30, 40, 50]`:

```text
Input:        10   20   30   40   50
limit(3):     10   20   30
skip(2):                30   40   50
skip(2)
  .limit(2):             30   40
```

`limit` and `skip` **do not modify the source collection**. They create pipeline processing steps; element consumption only begins when a terminal operation such as `toList()`, `count()`, or `forEach()` is called. A stream that has already passed through a terminal operation cannot be reused.

### Both operations are stateful intermediate operations

To know when `n` elements have been taken or `n` elements have been skipped, the system must track the number of elements that have passed through a segment of the pipeline. Therefore, they are considered **stateful intermediate operations**. This matters for parallel streams, especially when encounter order must be preserved.

`limit` is also a *short-circuiting* operation: in many pipelines, it can cause source consumption to stop once enough results are obtained. However, you should not assume that every upstream callback is always invoked exactly `n` times: `filter`, `distinct`, parallel execution, and optimizations can affect the number of evaluations.

## 2. Runnable Java 17+ example

Create the file `LimitSkipDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class LimitSkipDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6, 7, 8);

        System.out.println("first3 = " + numbers.stream()
                .limit(3)
                .toList());

        System.out.println("after5 = " + numbers.stream()
                .skip(5)
                .toList());

        System.out.println("page = " + numbers.stream()
                .skip(2)
                .limit(3)
                .toList());

        System.out.println("evenPage = " + numbers.stream()
                .filter(n -> n % 2 == 0)
                .skip(1)
                .limit(2)
                .toList());

        System.out.println("empty = " + numbers.stream()
                .limit(0)
                .toList());

        System.out.println("tooFar = " + numbers.stream()
                .skip(100)
                .toList());

        System.out.println("infiniteSlice = " + Stream.iterate(1, n -> n + 1)
                .skip(5)
                .limit(3)
                .toList());
    }
}
```

Run with JDK 17 or later:

```bash
javac LimitSkipDemo.java
java LimitSkipDemo
```

Exact stdout:

```text
first3 = [1, 2, 3]
after5 = [6, 7, 8]
page = [3, 4, 5]
evenPage = [4, 6]
empty = []
tooFar = []
infiniteSlice = [6, 7, 8]
```

Explanation:

1. `limit(3)` takes the first three elements in list order: `1, 2, 3`.
2. `skip(5)` skips `1, 2, 3, 4, 5` and keeps `6, 7, 8`.
3. `skip(2).limit(3)` skips the first two elements, then takes at most the next three elements.
4. `filter` keeps the even numbers `2, 4, 6, 8`; `skip(1)` skips `2`, and `limit(2)` keeps `4, 6`.
5. `limit(0)` is empty; `skip(100)` skips past the number of elements in the list, so it is also empty.
6. `Stream.iterate(1, n -> n + 1)` generates a stream with no end from the source itself. `skip(5).limit(3)` makes the pipeline finite for the terminal `toList()`: it takes `6, 7, 8`.

The program creates a new stream from `numbers.stream()` each time. This is the right approach; **do not** reuse a `Stream` object after a terminal operation has been called on it.

## 3. Operation order changes the result

In a pipeline, operations run with **left-to-right compositional semantics**, even though actual evaluation is lazy and may be optimized.

Example from the same list:

```java
List<Integer> values = List.of(1, 2, 3, 4, 5, 6, 7, 8);

List<Integer> a = values.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();  // [2, 4]

List<Integer> b = values.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();  // [2]
```

This snippet requires `import java.util.List;`. In `a`, the stream **filters first**, so `limit(2)` takes the first two even numbers. In `b`, the stream **limits first** to `[1, 2]`, so the filter step only keeps `[2]`.

Similarly:

```java
List<Integer> c = values.stream()
        .skip(2)
        .limit(3)
        .toList();  // [3, 4, 5]

List<Integer> d = values.stream()
        .limit(3)
        .skip(2)
        .toList();  // [3]
```

- `skip(2).limit(3)`: skips the first two elements, then selects the next three elements.
- `limit(3).skip(2)`: takes the first three elements, then skips two of the three elements just taken.

Do not arbitrarily reorder `filter`, `sorted`, `distinct`, `skip`, and `limit` because doing so can change the dataset or logical order:

```java
List<Integer> values = List.of(8, 2, 7, 1, 9);

List<Integer> smallestTwo = values.stream()
        .sorted()
        .limit(2)
        .toList();  // [1, 2]

List<Integer> firstTwoSorted = values.stream()
        .limit(2)
        .sorted()
        .toList();  // [2, 8]
```

This snippet also requires `java.util.List`. `sorted().limit(2)` finds the two smallest elements **across the entire source**, whereas `limit(2).sorted()` only sorts the first two elements.

### `distinct` also affects counts and boundaries

```java
List<Integer> values = List.of(1, 1, 2, 2, 3);

List<Integer> uniqueFirstTwo = values.stream()
        .distinct()
        .limit(2)
        .toList(); // [1, 2]

List<Integer> dedupFirstTwo = values.stream()
        .limit(2)
        .distinct()
        .toList(); // [1]
```

If the requirement is "the first two distinct values", `distinct` must appear **before** `limit(2)`.

## 4. Pagination with `skip` and `limit`

A common formula for **0-based** page indices:

```text
offset = pageIndex * pageSize
page   = stream.skip(offset).limit(pageSize)
```

Example with an eight-element list, three elements per page:

| `pageIndex` | `offset` | Result |
| --- | ---: | --- |
| 0 | 0 | `[1, 2, 3]` |
| 1 | 3 | `[4, 5, 6]` |
| 2 | 6 | `[7, 8]` |
| 3 | 9 | `[]` |

A basic pagination helper in Java 17:

```java
import java.util.List;

public class Pages {
    public static <T> List<T> page(List<T> source,
                                   long pageIndex,
                                   long pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Trang hoặc kích thước không hợp lệ");
        }

        long offset = Math.multiplyExact(pageIndex, pageSize);
        return source.stream()
                .skip(offset)
                .limit(pageSize)
                .toList();
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi", "Dung", "Em");
        System.out.println(page(names, 0, 2));
        System.out.println(page(names, 1, 2));
        System.out.println(page(names, 2, 2));
    }
}
```

This is a **standalone program** saved as `Pages.java`, which can be compiled and run:

```bash
javac -encoding UTF-8 Pages.java
java Pages
```

Stdout:

```text
[An, Bình]
[Chi, Dung]
[Em]
```

Notes:

- `pageSize > 0` gives a meaningful definition of a page; from an API standpoint, `limit(0)` is still valid, but in this example a page size of 0 is rejected by policy.
- `Math.multiplyExact(pageIndex, pageSize)` detects `long` overflow with `ArithmeticException`. With an unchecked `long offset = pageIndex * pageSize`, the multiplication can overflow and produce an incorrect value.
- `Stream.toList()` creates an **unmodifiable** list since Java 16. When a modifiable list is needed, use `new ArrayList<>(...)` or an appropriately chosen collector.
- If the data source can change between two pagination calls, `offset`-based pages may skip or duplicate elements. For stable results, a deterministic sort order and a snapshot/cursor policy are needed when appropriate.
- The helper above is suitable for data **already in memory**. For large database tables, let the database perform pagination with an appropriate query; calling `stream().skip(n)` after loading the entire table usually wastes memory, bandwidth, and CPU.

## 5. Encounter order determines the meaning of "first"

With a `List`, element order is already defined. Therefore:

```java
List<String> first = List.of("A", "B", "C", "D")
        .parallelStream()
        .skip(1)
        .limit(2)
        .toList();
// first == [B, C]
```

Even though elements may be processed in parallel, `skip(1).limit(2)` on an ordered stream takes the exact prefix slice after skipping one element. This **does not mean intermediate callbacks are necessarily executed in order**.

However, for a source **without a guaranteed encounter order**, such as `HashSet`, "the first two elements" has no stable business meaning:

```java
Set<Integer> numbers = new HashSet<>(List.of(10, 20, 30, 40));
List<Integer> chosen = numbers.stream()
        .limit(2)
        .toList();
```

This snippet requires importing `java.util.HashSet`, `java.util.List`, and `java.util.Set`. `chosen` has two elements when the source has at least two elements, but there is **no guarantee** which pair or in what order.

When the problem asks for "the N smallest elements", establish the order using `sorted()`:

```java
List<Integer> smallest = numbers.stream()
        .sorted()
        .limit(2)
        .toList();
// smallest == [10, 20]
```

Having `sorted()` sort or coordinate all data may incur a cost; ensuring correct semantics is more important than guessing which numbers will appear first from a `HashSet`.

## 6. `limit` on infinite streams and early termination

With a source that generates indefinitely, `limit` is often the bounding condition required for collection to complete.

```java
List<Long> powers = java.util.stream.Stream.iterate(1L, n -> n * 2)
        .limit(5)
        .toList();
// [1, 2, 4, 8, 16]
```

This snippet requires `import java.util.List;`. The two-argument `Stream.iterate(seed, next)` produces a stream with no natural endpoint, but `limit(5)` allows `toList()` to return five values.

Conversely:

```java
// DO NOT call toList() on an infinite stream without a bounding step:
java.util.stream.Stream.iterate(1L, n -> n + 1)
        .skip(100)
        .toList();
```

The snippet above is **broken-by-design illustrative code** that can keep consuming elements indefinitely and exhaust memory. `skip(100)` only discards the first 100 elements; it **does not bound** the remaining elements. Use `skip(100).limit(10)` when you need the next ten elements.

### `limit(n)` does not mean "every function only runs n times"

For example, `filter` must inspect data until it finds enough matching elements:

```java
List<Integer> a = java.util.stream.IntStream.rangeClosed(1, 20)
        .boxed()
        .filter(n -> n % 5 == 0)
        .limit(2)
        .toList();
// [5, 10]
```

In this example, `filter` cannot look only at the first two numbers `1, 2` and know two results. Therefore, do not use `limit(2)` as a guarantee that the entire pipeline processes only two upstream elements.

With parallel streams, out-of-order element processing and result coordination make callback invocation counts even less suitable as a business contract.

## 7. `skip` and `limit` on parallel streams: correct but potentially expensive

An **ordered parallel stream** can still return the exact requested slice, for example:

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .skip(3)
        .limit(4)
        .boxed()
        .toList();
// [4, 5, 6, 7]
```

However, to know which are the first three elements to skip and the next four elements to keep, the runtime may have to coordinate across processing branches. For large sources, `skip`, `limit`, and other stateful operations **can reduce the benefits of parallel processing** due to the requirement to preserve encounter order. The actual impact depends on the source, spliterator, data size, pipeline, and JVM.

If **order does not matter for business logic**, `unordered()` can relax the constraint:

```java
List<Integer> anyFour = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .unordered()
        .limit(4)
        .boxed()
        .toList();
```

`anyFour` contains four elements from the source, but you **must not assume** it will always be `[1, 2, 3, 4]`. `unordered()` does not mean random shuffling; it simply allows the pipeline to ignore encounter order constraints if any exist.

When you want deterministic pagination, especially in a UI or public API, **do not** use `unordered()` just in hopes of making it faster.

## 8. Common pitfalls

1. **Passing negative arguments:** `stream.limit(-1)` or `stream.skip(-1)` throws `IllegalArgumentException`. Validate pagination inputs beforehand.
2. **Misplacing `filter`:** `limit(3).filter(p)` can return fewer than three matching results, even when the source has many valid matches. If you need at most three elements matching a condition, usually place `filter(p).limit(3)`.
3. **Swapping `skip` and `limit`:** `skip(10).limit(5)` gets the page starting at index 10; `limit(5).skip(10)` is guaranteed to be empty for a finite stream because it already capped the stream at five elements.
4. **Using an unordered stream for pagination:** `HashSet.stream().skip(...).limit(...)` has no stable starting order for users to navigate across pages.
5. **Putting side effects into `peek` or `map`:** `limit` can short-circuit early; the JVM can also optimize the pipeline. Do not rely on callbacks to write to a DB, send emails, or increment required counters.
6. **Assuming `skip(n)` provides instant random access:** on many sources, the pipeline must traverse or coordinate skipping a number of elements. Do not assume `skip(1_000_000)` is cheap.
7. **Forgetting to bound an infinite stream:** `skip` does not make an infinite source finite; to collect a finite slice, add `limit`.
8. **Reusing a `Stream`:** after `toList()`, `count()`, or another terminal operation, you must create a new stream. Attempting to reuse it may throw `IllegalStateException`.
9. **Overflow when computing offset:** `pageIndex * pageSize` in `int` can overflow before being assigned to `long`; consider `Math.multiplyExact` with `long` arguments.
10. **Assuming `toList()` results are always modifiable:** since Java 16, the list returned by `Stream.toList()` is unmodifiable; if further modification is needed, create an appropriate copy.

### Why is `peek` sometimes not called as expected?

```java
long count = List.of(1, 2, 3, 4)
        .stream()
        .limit(2)
        .peek(System.out::println)
        .count();
// count == 2, but there is no guarantee that two lines will be printed.
```

This is a snippet inside a method with `import java.util.List;`. When the source has a known size and the pipeline preserves size information, an implementation can compute `count()` without running `peek`. Therefore, `peek` is not suitable for required side effects. If you need to perform an action on the selected results, build the result first and then iterate over it with an explicit policy.

## 9. Choosing the right way to write it

| Requirement | Pipeline |
| --- | --- |
| Take at most the first 10 elements from an ordered stream | `stream.limit(10)` |
| Skip the first 10 elements | `stream.skip(10)` |
| Take elements at positions 10 through 19 (0-based index) | `stream.skip(10).limit(10)` |
| Find the first three elements **matching** a predicate | `stream.filter(p).limit(3)` |
| Get the three smallest elements from the source | `stream.sorted().limit(3)` |
| Select the first 10 distinct values | `stream.distinct().limit(10)` |
| Pick any five elements when order is not needed | `stream.unordered().limit(5)` |
| Take a finite slice from an infinite stream | `stream.skip(offset).limit(size)` |

The pipelines above describe the **semantics** of the result; whether they are fast or slow must be evaluated against the actual source. For small in-memory lists, `skip/limit` is easy to read. For very large datasets, consider operating directly on indices/lists (when needed and possible) or pushing pagination down to the data source.

## 10. Knowledge check

1. What does `List.of(1,2,3,4,5).stream().skip(2).limit(2).toList()` return? **`[3,4]`**, because it skips two elements and then selects the next two.
2. What does `List.of(1,2,3,4).stream().limit(2).skip(2).toList()` return? **`[]`**, because initially only two elements remain and then both are skipped.
3. How does `filter(n -> n % 2 == 0).limit(2)` differ from `limit(2).filter(n -> n % 2 == 0)`? The former finds **at most the first two even numbers**, while the latter only filters within **the first two elements of the source**.
4. Can `skip(50)` alone be used to terminate an infinite stream? **No**, because there are still infinitely many elements after skipping 50 elements.
5. Does `parallelStream().skip(2).limit(3).toList()` keep the three elements in their exact positions on a `List`? **Yes**, because a list source has an encounter order and the pipeline remains ordered; however, callbacks may execute in parallel.
6. Does `unordered().limit(3)` guarantee taking the first three elements? **No**, because the ordering constraint has been removed.

## Key takeaways

- **`limit(n)` = keep at most the first n elements of the stream at the operation's position.**
- **`skip(n)` = skip the first n elements, keep the rest.**
- Both are **lazy intermediate operations**, require `n >= 0`, do not modify the source, and depend on encounter order to define "first".
- `filter`, `distinct`, `sorted`, `skip`, and `limit` **cannot be arbitrarily swapped** because pipeline order changes the result.
- In pagination: `skip(offset).limit(pageSize)`, validate the offset and maintain a stable data ordering.
- With infinite streams, `limit` bounds the result; with parallel streams, preserving order may incur coordination overhead.
