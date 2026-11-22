# Counting Elements with `count` and Recognizing Traversal-Skipping Optimizations

## 1. Lesson Objectives

In the **Java Stream API**, pipelines typically combine a data source with lazy intermediate operations such as `filter`, `map`, `distinct`, `flatMap`, and a terminal operation. When you only need to know **how many elements are in the result**, you use `count()` instead of creating an intermediate list and calling `size()`.

A common point of confusion is: **`count()` returns the number of elements in the pipeline result, but it does not guarantee traversing each element**. When the exact number of elements is already known and the intermediate steps do not change that count, the Stream implementation can compute the result immediately. Therefore, placing logging or update operations inside `peek` or `map` and then calling `count()` does not guarantee that those logs or operations will execute.

After this lesson, you can:

- Use `count()` with `Stream<T>` and primitive streams such as `IntStream`.
- Explain why `count()` returns `long`, behaves as a terminal operation, and may skip traversing data.
- Recognize sources with a known size (such as `List`) and steps that preserve or can alter the element count.
- Analyze why `peek`/`map` may not be invoked in a pipeline ending with `count()`.
- Write conditional counting, unique element counting, handle potentially infinite streams, and choose the right operation for the problem.

This lesson belongs to the **Traversal, Search, and Matching** chapter of the **`JAVA_STREAM_API`** module. This knowledge about lazy evaluation, source characteristics, and optimization limits is also essential when learning custom collectors, `Spliterator`, parallel processing, or Stream Gatherers.

## 2. `count()`: Syntax, Return Type, and Meaning

The method signature on `Stream<T>`:

```java
long count();
```

`count()` is a **terminal operation**: when called, the pipeline is requested to produce a final result as a `long` number. That number represents **the number of elements in the stream at the point `count()` is called**, that is, after all intermediate operations preceding it.

Complete example, usable from Java 8:

```java
import java.util.Arrays;
import java.util.List;

public class DemKhoaHoc {
    public static void main(String[] args) {
        List<String> khoaHoc = Arrays.asList(
            "Java Core",
            "Python",
            "Java Stream API",
            "Kotlin",
            "Java Spring"
        );

        long tongSo = khoaHoc.stream().count();

        long soKhoaJava = khoaHoc.stream()
            .filter(ten -> ten.startsWith("Java"))
            .count();

        System.out.println("Total: " + tongSo);
        System.out.println("Java courses: " + soKhoaJava);
    }
}
```

Output:

```text
Total: 5
Java courses: 3
```

In the second pipeline, `filter` excludes "Python" and "Kotlin", so `count()` receives the number of elements passing the condition. The result `3` **is not the number of times the `filter` method was called**.

Some other expressions:

| Expression | Result | Meaning |
| --- | ---: | --- |
| `Stream.empty().count()` | `0L` | Empty stream. |
| `Stream.of("A", "B", "C").count()` | `3L` | Three elements. |
| `Stream.of("A", "A", "B").distinct().count()` | `2L` | Two distinct values. |
| `Stream.of(3, 6, 9).filter(n -> n > 5).count()` | `2L` | Two elements matching the condition. |
| `java.util.stream.IntStream.range(0, 100).count()` | `100L` | One hundred numbers, from 0 to 99. |

**Why type `long`?** The API uses `long` to represent counts that can exceed the limit of `int`. If you declare `int n = stream.count();`, the compiler reports an error because it cannot automatically convert from `long` to `int`.

```java
long hopLe = Stream.of(1, 2, 3).count();

// DOES NOT COMPILE: possible lossy conversion from long to int.
// int saiKieu = Stream.of(1, 2, 3).count();
```

A stream can only be **consumed once**. After calling `count()`, do not reuse that same stream object for `collect()`, `findFirst()`, or another `count()`; to compute more, create a new stream from the source.

## 3. Must a Terminal Operation Traverse Elements?

The word "terminal" means **requesting a final result and ending use of the stream**, not **requiring every intermediate step to be invoked on every element**.

### 3.1. Example Where `peek` Prints Nothing Yet `count()` Is Still Correct

Consider the program:

```java
import java.util.Arrays;
import java.util.List;

public class DemKhongDuyet {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList("An", "Binh", "Chi");

        long soLuong = ten.stream()
            .peek(s -> System.out.println("Seen: " + s))
            .count();

        System.out.println("Count: " + soLuong);
    }
}
```

On many modern JDK implementations (especially from Java 9 onward), the output may only be:

```text
Count: 3
```

There are no `Seen: ...` lines. **This is permitted behavior**, not a bug in `peek` or `count()`.

Reason: the `List` source has a known number of elements; `peek` neither adds nor removes elements; therefore `count()` can obtain the exact result `3` without asking the source to supply each element. When not traversing, the action inside `peek` is also not executed.

> Version and implementation note: the API documentation explicitly describes this optimization capability; you must not write code that depends on `peek` definitely running or definitely being skipped. Java 8 and other versions/implementations may behave differently.

### 3.2. `map` Can Also Be Skipped

`map` changes **values** but usually does not change the **number** of elements:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi");

long soLuong = ten.stream()
    .map(s -> s.toUpperCase(java.util.Locale.ROOT))
    .count();

System.out.println(soLuong); // 3
```

To compute the count, `count()` does not need to know what the uppercased names look like. If the implementation has sufficient size information, it can skip invoking the `map` function entirely.

This is especially important if the lambda has **side effects**:

```java
// Unreliable way of writing:
long soLuong = ten.stream()
    .map(s -> {
        ghiLogHoacCapNhatHeThong(s);
        return s.toUpperCase(java.util.Locale.ROOT);
    })
    .count();
```

`ghiLogHoacCapNhatHeThong(s)` **is not guaranteed to run**, even though `count()` returns the correct `3`. The snippet above illustrates a design pattern to avoid; `ghiLogHoacCapNhatHeThong` is a placeholder method name.

**Rule:** Processing functions in `map`, `filter`, and `peek` should be side-effect-free and must not depend on how many times they are called. If the goal is to perform an action for each element, use an appropriate terminal operation such as `forEach`; if the goal is counting, use `count` and rely solely on the count result.

## 4. Why Can the Implementation Know the Count Before Traversing?

### 4.1. Sources with an Exact Size

Many data sources know their element count upfront. In the Stream API, this information is usually tied to the source's **`Spliterator.SIZED`** characteristic.

Example:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi");

long dem = ten.stream().count(); // 3
int kichThuoc = ten.size();      // 3
```

With a stable list as the source, obtaining the count directly from the source can avoid iterating over all elements.

Common sources:

| Source | Size Information | Consequence for `count()` |
| --- | --- | --- |
| `Arrays.asList(...).stream()` | Usually known exactly | Can compute directly if the pipeline does not destroy size information. |
| `Stream.of(a, b, c)` | Known exactly | Can usually optimize counting. |
| `IntStream.range(0, 1000)` | Has an exact element count | Can compute the count without traversing all numbers. |
| `Stream.iterate(seed, next)` | Does not declare a finite count | Usually cannot infer an endpoint automatically. |
| `Stream.generate(supplier)` | May generate infinitely; no known size | Cannot determine total element count automatically. |

The `SIZED` characteristic indicates that the source can provide an exact count of remaining elements at the appropriate time. It does not mean **every pipeline originating from that source** knows its exact size after transformations.

### 4.2. Does an Operation Preserve the Element Count?

Consider the intermediate operations in a pipeline:

| Operation | Effect on Count | Possibility of Counting Without Traversal |
| --- | --- | --- |
| `map` | Each input produces one output | Can preserve size information. |
| `peek` | Intentionally adds/removes no elements | Can preserve size information. |
| `sorted` | Sorts without adding/removing | Can still compute count directly without sorting. |
| `unordered` | Drops ordering requirement, does not change count | Can preserve size information. |
| `filter` | May exclude some elements | Usually must evaluate the predicate to know the count. |
| `distinct` | May remove duplicate elements | Usually must determine distinct values. |
| `flatMap` | Each element may produce 0, 1, or more elements | Usually must inspect the substreams. |
| `mapMulti` (Java 16+) | May produce 0, 1, or more elements | Usually must traverse to know the count. |
| `takeWhile` / `dropWhile` (Java 9+) | May drop elements based on a condition | Usually must check the condition. |
| `limit(n)` / `skip(n)` | Limits/skips elements by position | With a sized source, the count after these steps **can** be computed arithmetically. |

Example:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

long a = ten.stream()
    .map(String::length)
    .count();                          // 4

long b = ten.stream()
    .filter(s -> s.length() >= 4)
    .count();                          // 2

long c = ten.stream()
    .skip(1)
    .limit(2)
    .count();                          // 2
```

- For `a`, `map` changes values, but the element count is guaranteed to remain 4.
- For `b`, it is necessary to determine which names pass the filter; in this example, `Binh` and `Dung`.
- For `c`, the source has four elements; skipping one and taking at most two yields a count of 2.

This is an **optimization possibility**, not a promise that every JDK version or every pipeline shape will apply the exact same strategy. Optimizations are allowed to change which intermediate steps actually get evaluated, while the `count()` result must remain faithful to stream semantics.

### 4.3. `SIZED` and `SUBSIZED` Are Not the Same

The `Spliterator.SIZED` characteristic refers to **the exact size of the remaining portion** represented by the spliterator. `Spliterator.SUBSIZED` adds that child spliterators obtained from splitting also have both `SIZED` and `SUBSIZED` characteristics.

Both characteristics are useful for optimization, especially in parallel processing, but they **do not automatically guarantee** that all intermediate steps are skipped. For instance, `filter` can prevent the result count from being deduced directly from the source size.

When implementing a custom `Spliterator` in advanced lessons, only declare `SIZED` if it genuinely satisfies the exact contract for remaining element count. Declaring it inaccurately can cause incorrect behavior or hard-to-diagnose bugs.

## 5. Counting After `filter`, `distinct`, and `flatMap`

### 5.1. Conditional Counting

If the requirement is **"How many Java courses are there?"**, put the condition inside `filter`:

```java
List<String> khoaHoc = Arrays.asList(
    "Java Core", "Python", "Java Stream API", "Java Spring"
);

long soKhoaJava = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .count();

System.out.println(soKhoaJava); // 3
```

The source has four elements, but 4 alone cannot tell you how many names start with "Java". `count()` needs to account for the filter's outcome.

**Do not confuse `filter` with `map`**:

```java
long saiYeuCau = khoaHoc.stream()
    .map(ten -> ten.startsWith("Java"))
    .count();

System.out.println(saiYeuCau); // 4, not 3
```

Here `map` turns each string into a `Boolean` (both `true` and `false` are elements), so the count remains four.

### 5.2. Counting Unique Values

`distinct` removes duplicate values according to `equals`:

```java
List<String> ngonNgu = Arrays.asList(
    "Java", "Kotlin", "Java", "Go", "Kotlin"
);

long soNgonNgu = ngonNgu.stream()
    .distinct()
    .count();

System.out.println(soNgonNgu); // 3
```

If uniqueness needs to be case-insensitive, normalize beforehand:

```java
import java.util.Locale;

List<String> ten = Arrays.asList("Java", "JAVA", "Go", "go");

long soTenKhacNhau = ten.stream()
    .map(s -> s.toLowerCase(Locale.ROOT))
    .distinct()
    .count();

System.out.println(soTenKhacNhau); // 2
```

The count after `distinct` depends on the concrete values; a sized source is not enough to infer how many unique values exist.

### 5.3. Counting Elements After Flattening

`flatMap` can turn one element into multiple elements:

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("A", "B"),
    Arrays.asList("C"),
    Arrays.<String>asList()
);

long soNhom = nhom.stream().count(); // 3

long soPhanTu = nhom.stream()
    .flatMap(List::stream)
    .count();                       // 3
```

In this example, both results being 3 **is merely a coincidence**. A stream of three sublists does not mean the flattened stream always has three elements.

## 6. `peek` Is Suited for Observation, Not for Business Logic

Although `peek` is often used to observe data between steps, it is **not a guaranteed mechanism for executing tasks**. In particular, `count()` may not evaluate `peek` at all if the count is already known.

Illustrative example:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

long tong = ten.stream()
    .peek(s -> System.out.println("Checking " + s))
    .count();

System.out.println("Total = " + tong);
```

One JDK might print only `Total = 4`, while another JDK might also print the observation lines. A correct program relies only on `tong == 4`.

When adding `filter`:

```java
long hopLe = ten.stream()
    .filter(s -> s.length() >= 4)
    .peek(s -> System.out.println("Valid: " + s))
    .count();

System.out.println("Valid name count = " + hopLe); // 2
```

In a typical pipeline, because the count after `filter` is not known ahead of time, execution must check the elements and `peek` logs may appear. However, **do not use log line counts to verify execution counts** and do not rely on this side effect as a business outcome.

If the actual requirement is **"Record each valid name"**, express the action as an explicit terminal operation:

```java
ten.stream()
    .filter(s -> s.length() >= 4)
    .forEach(s -> System.out.println("Valid: " + s));
```

If you need both to **count** and to **perform an action**, clarify the goal and design explicitly: for instance, collect valid elements into a list if the dataset is small enough, use `size()` on that list, and process the list as required. For large datasets, consider a dedicated processing stream; do not rely on side effects inside a pipeline just to force `count()` to traverse.

You should also avoid inserting artificial operations that alter element counts solely to "force" `peek` to run. That distorts the pipeline's intent and can hurt performance.

## 7. Counting Infinite Streams: You Must Have a Proper Stopping Point

`count()` does not automatically stop a potentially infinite source. With sequences like `Stream.iterate` or `Stream.generate`, you must restrict the number of elements or provide a terminating condition before expecting a count result.

### 7.1. Counting the First 10 Numbers

```java
import java.util.stream.Stream;

long soLuong = Stream.iterate(0, n -> n + 1)
    .limit(10)
    .count();

System.out.println(soLuong); // 10
```

`limit(10)` ensures the pipeline requests at most ten elements. Whether `count()` traverses and invokes intermediate steps depends on the source and implementation; this is how a finite bound is expressed.

### 7.2. Filtering Before Limiting

```java
long soSoChan = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .count();

System.out.println(soSoChan); // 5
```

The pipeline must find five even numbers, corresponding to 2, 4, 6, 8, 10. If you swap the order:

```java
long soChanTrongNamSoDau = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .filter(n -> n % 2 == 0)
    .count();

System.out.println(soChanTrongNamSoDau); // 2
```

The difference is **counting the first five even numbers** versus **counting even numbers within the first five numbers**.

### 7.3. Pipelines You Should Not Run

The following examples may never finish:

```java
// DO NOT RUN: unbounded infinite source.
// Stream.iterate(0, n -> n + 1).count();

// DO NOT RUN: filter never lets any element pass,
// so limit(1) never receives enough elements.
// Stream.iterate(0, n -> n + 1)
//     .filter(n -> false)
//     .limit(1)
//     .count();
```

With Java 9+, you can use `takeWhile` on an ordered sequence or the `Stream.iterate(seed, hasNext, next)` overload to create a state-based stopping point:

```java
long dem = Stream.iterate(0, n -> n < 100, n -> n + 1)
    .count(); // 100 — Java 9+
```

Merely writing `filter(n -> n < 100)` **does not replace** a stopping condition: the filter rejects elements, but it can continue asking the source to generate values forever.

## 8. Choosing `count()`, `size()`, `anyMatch()`, or `Collectors.counting()`

Different needs call for different APIs:

| Need | API to Consider | Example |
| --- | --- | --- |
| Count all elements of an existing `Collection` | `collection.size()` | `ten.size()` |
| Count elements after Stream processing steps | `stream.count()` | `stream.filter(...).count()` |
| Only need to know if at least one element matches | `anyMatch(predicate)` | `stream.anyMatch(s -> s.isEmpty())` |
| Check that no element matches a condition | `noneMatch(predicate)` | `stream.noneMatch(String::isEmpty)` |
| Count per group | `Collectors.groupingBy(..., counting())` | `Map<K, Long>` |
| Need both the count and the list of valid elements | `collect(toList())` then `size()` | Appropriate only when you genuinely need to keep the list |

### 8.1. Why Not Always Use `count() > 0`?

`count()` gives the exact quantity; `anyMatch()` is a **short-circuiting terminal operation** and can stop as soon as it finds a matching element.

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

boolean coTenDai = ten.stream()
    .anyMatch(s -> s.length() >= 4);

System.out.println(coTenDai); // true
```

If you only need a **yes/no** answer, `anyMatch` expresses the intent more clearly and can avoid traversing the entire source. Conversely, if a report asks "**how many** long names are there", use `filter(...).count()`.

### 8.2. `count()` vs `Collectors.counting()`

`count()` returns the total element count of the entire pipeline:

```java
long tong = ten.stream().count();
```

`Collectors.counting()` is usually useful **inside another collector**, such as counting courses per group:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> khoaHoc = Arrays.asList(
    "Java Core", "Java Stream", "Go", "Python", "Java Spring"
);

Map<Boolean, Long> theoNhom = khoaHoc.stream()
    .collect(Collectors.groupingBy(
        s -> s.startsWith("Java"),
        Collectors.counting()
    ));

System.out.println(theoNhom.get(true));  // 3
System.out.println(theoNhom.get(false)); // 2
```

Here `groupingBy` splits elements into two groups and `counting()` counts elements **within each group**. When grouping is not needed, `count()` is usually simpler and clearer.

### 8.3. `count()` Differs from Action Invocation Counts

`count()` describes **the final element count**, not how many times `map`, `peek`, a `sorted` comparator, or any callback is executed. The invocation count and call order of behavioral functions are implementation details, and some operations can short-circuit or be skipped when they do not affect the result.

This also matters when switching to parallel processing: even though the count result is the same, do not infer execution order or invocation counts of side-effecting operations from `count()`'s result.

## 9. How to Verify and Diagnose Optimizations

When you see `peek` printing nothing, check first:

1. **Does the source know its element count?** For example, `List`, arrays, `Stream.of`, and `IntStream.range` usually carry size information.
2. **Which steps can change the count?** `map` and `peek` preserve the count; `filter`, `distinct`, and `flatMap` usually make the result data-dependent.
3. **Does the terminal operation actually need each element's value?** `count()` might not; `collect(toList())` usually has to produce output values.
4. **Are you relying on side effects?** If so, redesign so business actions are expressed explicitly.
5. **Is there an infinite source or a blocking operation before `limit`?** Check whether the pipeline might never terminate.

### Contrasting Illustration

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class KiemTraCount {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList("A", "BB", "CCC");

        long dem = ten.stream()
            .map(String::toLowerCase)
            .peek(s -> System.out.println("peek: " + s))
            .count();

        List<String> danhSach = ten.stream()
            .map(String::toLowerCase)
            .collect(Collectors.toList());

        System.out.println("Count: " + dem);
        System.out.println("List: " + danhSach);
    }
}
```

The logical results to verify are:

```text
Count: 3
List: [a, bb, ccc]
```

The `peek: ...` lines may or may not appear depending on the implementation and optimization. They **are not part of the pass/fail criteria** for the example.

When testing, assert directly on `dem == 3` and `danhSach.equals(Arrays.asList("a", "bb", "ccc"))`. Never write tests assuming `peek` is always called three times, or assuming log lines never appear.

## 10. Common Mistakes

| Mistake or Misconception | Cause | How to Handle |
| --- | --- | --- |
| `peek` prints nothing when using `count()` | The pipeline can be optimized without traversing elements | Use `peek` only for observation; never rely on side effects |
| `map` is skipped, task inside lambda does not run | `map` preserves element count; `count` does not need transformed results | Move business actions to an explicit execution mechanism |
| `map(predicate).count()` returns total element count | `map` converts elements to `Boolean`, rather than filtering | Replace with `filter(predicate).count()` |
| `int n = stream.count()` fails to compile | `count` returns `long` | Declare `long n` |
| Calling `count()` and then reusing the same stream | The stream has already been consumed | Create a new stream from the source |
| `count()` on an infinite stream never finishes | No stopping condition | Add a finite limit or terminating condition |
| `filter(...).limit(n)` runs forever | Never finds `n` matching elements | Consider bounding the source before `filter` |
| Using `collect(toList()).size()` just to count | Creates unnecessary intermediate structure | Use `count()` |
| Using `count() > 0` just to check existence | May require computing the entire count | Use `anyMatch` when checking a condition |
| Seeing a correct count and assuming the lambda surely ran | Optimizations can skip operations that do not affect element count | Write logic that does not depend on side effects |

Misunderstanding optimizations can lead to subtle bugs because **the count is still right** while an expected side effect fails to execute.

## 11. Practice Exercises

### Exercise 1 — Counting Elements by Condition

Given:

```java
List<Integer> diem = Arrays.asList(4, 7, 8, 10, 5, 7, 9);
```

Write a pipeline to count how many scores are **7 or higher**. The result must be a `long`. Explain why `map(d -> d >= 7).count()` does not solve the requirement.

### Exercise 2 — Analyzing `peek` and `map`

```java
List<String> ten = Arrays.asList("A", "BB", "CCC", "DDDD");

long n = ten.stream()
    .map(s -> s + "!")
    .peek(System.out::println)
    .count();
```

What is `n`? Can we assert that the program will print exact four lines `A!`, `BB!`, `CCC!`, `DDDD!`? Why or why not?

### Exercise 3 — Order of `filter` and `limit`

Predict the results:

```java
long a = java.util.stream.IntStream.rangeClosed(1, 20)
    .filter(x -> x % 2 == 0)
    .limit(5)
    .count();

long b = java.util.stream.IntStream.rangeClosed(1, 20)
    .limit(5)
    .filter(x -> x % 2 == 0)
    .count();
```

### Exercise 4 — Choosing the Terminal Operation

In a list of 100,000 products, you only need to know **whether any product is out of stock**. Should you use `filter(p -> p.isOutOfStock()).count() > 0` or `anyMatch(p -> p.isOutOfStock())`? When should you use `count()`?

### Exercise 5 — Spotting a Pipeline That Can Hang

```java
long n = Stream.iterate(1, x -> x + 1)
    .filter(x -> false)
    .limit(2)
    .count();
```

Can this snippet terminate? Write a fix so the count completes finitely without changing the meaning of "no elements satisfy the condition".

### Reference Answers

**Exercise 1:**

```java
long soDiemDat = diem.stream()
    .filter(d -> d >= 7)
    .count();

System.out.println(soDiemDat); // 5
```

The qualifying scores are 7, 8, 10, 7, 9. `map` only produces `true`/`false` values, so the total number of elements remains seven.

**Exercise 2:** `n == 4`. Neither `map` nor `peek` changes the element count. On an implementation with known size, `count` can return four immediately without evaluating them. Therefore, there is no guarantee about printed lines.

**Exercise 3:** `a == 5` because there are at least five even numbers in 1..20; `b == 2` because only 2 and 4 appear in the first five numbers.

**Exercise 4:** Use `anyMatch(p -> p.isOutOfStock())` because it only checks existence and can stop early upon encountering an out-of-stock product. Use `filter(...).count()` when you need the **exact number of out-of-stock products**.

**Exercise 5:** The pipeline can run infinitely because `filter(x -> false)` lets no element pass, so `limit(2)` never receives two elements. If you only want to count results within the **first 100 states**, bound the source first:

```java
long n = Stream.iterate(1, x -> x + 1)
    .limit(100)
    .filter(x -> false)
    .count();

System.out.println(n); // 0
```

In a case where the condition is genuinely always false, `Stream.empty().count()` also yields 0; the general takeaway of the exercise is ensuring a finite source before attempting to compute an exact count.

## 12. Key Takeaways

`count()` is a terminal operation returning **`long`**: the number of remaining elements after processing steps. Because the count can be known from the source and pipeline cardinality information, **`count()` can return a result without traversing elements or invoking intermediate operations such as `map` and `peek`**.

To write correct code:

- Use `filter(predicate).count()` to count elements matching a condition, and `distinct().count()` to count unique values.
- Use `anyMatch` when you only need to know **if at least one matching element exists**, or `Collection.size()` when you only need the size of an existing collection.
- Do not place mandatory tasks inside `peek` or `map` expecting `count()` to trigger them.
- Control stopping points when sources may be infinite, and pay attention to the order of `filter` and `limit`.
- Evaluate correctness based on the **count value**, not on log line counts or function invocation order.

Recognizing traversal-skipping optimizations helps you read lazy pipelines accurately, avoid side-effect bugs, and understand the optimization foundations of the Java Stream API before moving on to grouping, custom collectors, `Spliterator`, and parallel processing.
