# Data Reduction Mindset and Choosing reduce

When processing data with the Java Stream API, many problems do not require returning the entire set of elements. We only want **a single aggregated result**: a total amount, the highest score, a descriptive string, a value combined by business rules, or a combinable state. This mindset is called **reduction**: transforming a sequence of multiple elements into a single result value.

This lesson belongs to the chapter **Reduction with reduce** of the `JAVA_STREAM_API` module. The goal is to understand the meaning of the combining operation, how to choose an initial value, associativity for running correctly on a parallel stream, and especially **when to use `reduce` instead of `collect` or a specialized terminal operation**. This knowledge connects directly to lazy pipelines, `filter`, `map`, `collect`, and constraints on state, arithmetic precision, resources, and performance.

## 1. What is reduction?

Suppose we have the values `[3, 5, 7, 9]` and want to compute their sum. We can visualize combining them step by step:

```text
Input data: 3, 5, 7, 9

Initial value = 0
       │
       ├─ combine 3 → 3
       ├─ combine 5 → 8
       ├─ combine 7 → 15
       └─ combine 9 → 24

Result: 24
```

With the Java Stream API:

```java
import java.util.stream.Stream;

int total = Stream.of(3, 5, 7, 9)
        .reduce(0, Integer::sum);

System.out.println(total); // 24
```

In the example above, `0` is the **identity value** (*identity*) of addition; `Integer::sum` is the **combining operation** (*accumulator*) between the intermediate result and the next element. `reduce` is a terminal operation: it **consumes** the pipeline, returns a value, and does not allow reusing the same Stream instance.

It can be illustrated visually as:

```text
Stream<T> ── filter / map / ... ── reduce(identity, operator) ──► T
                    intermediate          terminal
```

However, the model of “going from left to right, adding one by one” is only an **intuitive explanation**. With a parallel stream, Java can split the data into multiple branches, reduce each branch, and then combine the branch results. Therefore, you must not rely on the actual invocation order of the lambda when writing a reduction.

## 2. Three common reduce variants of Stream<T>

`Stream<T>` defines three main overloads:

| Call form | Result type | Use when |
| --- | --- | --- |
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | There is no natural identity, and an empty Stream must be distinguished |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | The combining operation has an identity and the output has the same type as the elements |
| `reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)` | `U` | The result has a different type from the elements; a way to merge branch results is needed |

All three have existed since **Java 8**. The following examples separate each form to avoid confusion about empty-input cases and parallel execution characteristics.

### 2.1. reduce without identity: returns Optional<T>

Finding the maximum number without arbitrarily picking an “assumed minimum value”:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> scores = Arrays.asList(5, 12, 8);

Optional<Integer> highest = scores.stream()
        .reduce(Integer::max);

System.out.println(highest); // Optional[12]
```

If the source is empty, the result is `Optional.empty()`, because there are no elements to reduce:

```java
Optional<Integer> absent = java.util.stream.Stream
        .<Integer>empty()
        .reduce(Integer::max);

System.out.println(absent.isPresent()); // false
```

You should not call `get()` without checking for presence. You can use `orElse`, `orElseThrow`, or handle it with `ifPresent` depending on the business contract.

### 2.2. reduce with identity: always returns T

```java
int sum = Arrays.asList(5, 12, 8).stream()
        .reduce(0, Integer::sum);

int emptySum = java.util.stream.Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(sum);      // 25
System.out.println(emptySum); // 0
```

`identity` is not necessarily “the first element”, but must be the **true neutral value** of the combining operation: combining it with any result keeps that result unchanged. For integer addition, that is `0`; for multiplication, that is `1`; for string concatenation, that is the empty string `""`.

### 2.3. Three-parameter reduce: result of type U

When the input elements have type `T`, but the reduced result has type `U`, Java provides the overload:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
)
```

For example, computing the total **string length** as a `long`:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", "Stream", "API");

long totalLength = words.stream()
        .reduce(
                0L,
                (length, word) -> length + word.length(),
                Long::sum
        );

System.out.println(totalLength); // 13
```

Here:

- `identity = 0L` is a neutral result of type `Long`.
- `accumulator` combines a `Long` result with a `String` element.
- `combiner` merges **two `Long` results**; it is necessary to merge parallel branches.

To compute the total length, a way that is usually **more readable and data-type efficient** is mapping to `IntStream` and using `sum`:

```java
int lengthSum = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(lengthSum); // 13
```

The three-parameter example helps understand the contract of `reduce`; it does not mean this is the best choice for every cross-type calculation.

## 3. Right mindset: choose the combining operation before choosing the API

The most important step is not memorizing `reduce` syntax, but identifying the operation:

1. **What is the output?** A number, a string, an optimal value, or a structure with multiple fields?
2. **Can two partial results be combined into an equivalent result?**
3. **Is there an appropriate neutral value?**
4. **What should an empty source produce?** A default value or “absent”?
5. **Is there a more suitable specialized API or Collector?**

Some sample operations:

| Requirement | Combining operation | Identity if using reduce with identity | API usually considered first |
| --- | --- | --- | --- |
| Sum of integers | Addition | `0` | `IntStream.sum()` |
| Product of integers | Multiplication | `1` | `reduce(1, (a,b) -> a*b)` |
| Maximum value | `max` | No need to choose manually | `max(Comparator)` / `IntStream.max()` |
| All conditions true | Logical AND | `true` | `allMatch(predicate)` |
| At least one condition true | Logical OR | `false` | `anyMatch(predicate)` |
| Joining strings | Concatenation | `""` | `Collectors.joining(...)` |
| Collecting elements into a List | Adding elements | Mutable container | `collect(Collectors.toList())` |
| Grouping by key | Grouping | Mutable Map | `collect(Collectors.groupingBy(...))` |

The two logical-condition rows highlight an important distinction: you can reduce `Boolean` values using AND/OR, but `allMatch` and `anyMatch` are usually better because they **short-circuit** as soon as enough information is available.

## 4. Identity must be truly neutral

For a combining operation denoted `⊕`, the identity `e` must satisfy:

```text
e ⊕ x = x
x ⊕ e = x
```

If this does not hold, the result can be wrong even with a sequential Stream, and is even more likely to be wrong when Java creates multiple parallel branches.

### Wrong example: using 0 as the identity for the maximum value

```java
List<Integer> temperatures = Arrays.asList(-7, -3, -11);

int wrongMax = temperatures.stream()
        .reduce(0, Integer::max);

System.out.println(wrongMax); // 0, which does not appear in the source!
```

`0` is **not** neutral for taking the maximum over the entire integer domain, because `max(0, -7) = 0` instead of `-7`. To represent “no value if the source is empty”, use:

```java
Optional<Integer> correctMax = temperatures.stream()
        .reduce(Integer::max);

System.out.println(correctMax); // Optional[-3]
```

If you are certain all numbers are `int` and want a valid identity for `max` over the entire `int` range, you could choose `Integer.MIN_VALUE`, but then an empty source also returns `Integer.MIN_VALUE`. That can cause callers to confuse a real value with the default value; in many cases, `OptionalInt` or `Optional<Integer>` is more appropriate.

### Example with multiplication

```java
int product = Arrays.asList(2, 3, 4).stream()
        .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
```

The right identity is `1`, because `1 * x = x`. If `0` is used, every result becomes 0. Note that `int` can still overflow when the product is too large.

## 5. Associativity: the condition for combining across multiple branches

A combining operation is **associative** if:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

This is the core condition enabling Java to partition a Stream, reduce each part, and combine them without changing the meaning of the result.

Integer addition is associative in integer arithmetic (considering results within the numeric type's representable range); string concatenation is also associative:

```text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
```

Conversely, subtraction is **not associative**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Therefore:

```java
// NOT suitable for a reduction requiring consistent results in parallel.
int result = Arrays.asList(10, 3, 2).stream()
        .reduce(0, (a, b) -> a - b);
```

With a sequential pipeline, this snippet may produce a specific value from sequential traversal, but it does not satisfy the mathematical contract to allow changing how branches are split; it should not be used as a parallelizable `reduce`.

**Associativity is different from commutativity**. String concatenation is associative, yet `"AB"` differs from `"BA"`, so it is not commutative. `reduce` does not require the combining operation to be commutative in every case; for Streams with an encounter order, logical order must still be preserved to achieve the right result under the contract. If you want to allow reordering, the combining operation must also fit that requirement.

### Floating-point numbers and precision error

`double` does not guarantee strict associativity due to rounding:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

When using `reduce` to sum floating-point numbers, the grouping order can alter low-order digits, especially with parallel streams. This is an arithmetic limitation, not merely an API issue. If handling currency requiring exact decimals, consider `BigDecimal` with explicit scale/rounding rules; if computing floating-point statistics, consider numerically stable summation algorithms or `DoubleStream.sum()` with an appropriate precision contract.

## 6. reduce and collect: immutable or mutating state?

An important distinction in the Java Stream API:

- `reduce` is usually suited for **immutable reduction**: each step creates/returns a **new result value**, without modifying a shared result object.
- `collect` is suited for **mutable reduction**: elements are added to a dedicated container (list, map, statistics accumulator), and containers are merged when needed.

### Anti-pattern: using reduce to mutate an ArrayList

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

// WRONG: turning a mutable list into the identity of reduce.
List<String> bad = Arrays.asList("A", "B", "C").parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

The code above violates how `reduce` is meant to be used: the identity is **the same mutable instance** that can be mutated by multiple branches; the accumulator mutates the very object passed in; the combiner could merge an object with itself. The result can be wrong or suffer concurrency issues. Do not assume that adding `parallel()` just makes this code “faster”.

Use `collect`:

```java
List<String> good = Arrays.asList("A", "B", "C").parallelStream()
        .collect(java.util.stream.Collectors.toList());
```

If you need to build a list from a primitive Stream, use `boxed().collect(...)` or `IntStream.collect(supplier, accumulator, combiner)` with an appropriate dedicated container. Choose the aggregation mechanism according to the shape of the result.

### Comparing the two API styles

| Aspect | `reduce` | `collect` |
| --- | --- | --- |
| Nature | Combines values into a single result | Accumulates into a container |
| Intermediate state | Should be an immutable result or not mutated while shared | Mutable container provided by the supplier |
| Merging branches | `BinaryOperator` returning a result value | Collector with a combiner that merges containers |
| Used for | Sums, products, business-value aggregation, selecting extrema | List, Set, Map, grouping, partitioning, stateful statistics |
| Caution | Identity, associativity, purity | Distinct supplier, accumulator/combiner contract |

`Collectors.counting()`, `summingInt()`, or `reducing()` are also collectors, often useful when nested inside `groupingBy`. This is why you can sometimes “reduce” inside a collector without directly calling the terminal `Stream.reduce`.

## 7. Choices with primitive Streams

When the result is a common arithmetic calculation, prefer `IntStream`, `LongStream`, or `DoubleStream`:

```java
import java.util.Arrays;

int[] values = {3, 5, 7, 9};

int sum = Arrays.stream(values).sum();
long count = Arrays.stream(values).count();
double average = Arrays.stream(values)
        .average()
        .orElse(Double.NaN);

System.out.println(sum);     // 24
System.out.println(count);   // 4
System.out.println(average); // 6.0
```

`sum()` is usually easier to read than `reduce(0, Integer::sum)`. Primitive streams avoid boxing/unboxing for many operations, and provide appropriate `min`, `max`, and `summaryStatistics` APIs.

To compute a sum that may exceed `int`, widen the type before adding:

```java
long saferSum = java.util.stream.IntStream.of(
        2_000_000_000, 2_000_000_000
).asLongStream().sum();

System.out.println(saferSum); // 4000000000
```

`asLongStream()` converts each `int` into a `long` before addition. Using `IntStream.sum()` on the same source risks 32-bit overflow; `long` also has its own limit.

For summing decimal monetary amounts, a clear example of `reduce`:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

List<BigDecimal> amounts = Arrays.asList(
        new BigDecimal("12.50"),
        new BigDecimal("7.25"),
        new BigDecimal("0.25")
);

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 20.00
```

`BigDecimal` is immutable; `add` returns a new value. You should construct `BigDecimal` from strings or controlled sources to avoid representation discrepancies caused by constructing directly from `double` literals.

## 8. A custom business reducer

Suppose each order has a `BigDecimal` amount and we need to get the **total amount of paid orders**. To focus on the reduction, use a simple class:

```java
import java.math.BigDecimal;

final class Order {
    private final BigDecimal amount;
    private final boolean paid;

    Order(String amount, boolean paid) {
        this.amount = new BigDecimal(amount);
        this.paid = paid;
    }

    BigDecimal amount() {
        return amount;
    }

    boolean isPaid() {
        return paid;
    }
}
```

Pipeline:

```java
import java.util.Arrays;
import java.util.List;

List<Order> orders = Arrays.asList(
        new Order("100.50", true),
        new Order("200.00", false),
        new Order("30.25", true)
);

BigDecimal paidTotal = orders.stream()
        .filter(Order::isPaid)
        .map(Order::amount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(paidTotal); // 130.75
```

The steps keep clear responsibilities: `filter` selects paid orders, `map` transforms each element to its amount, and `reduce` combines those amounts. Since `BigDecimal::add` creates a new value and addition with `ZERO` is neutral, the example satisfies the `reduce` contract with exact decimal addition.

If you need the **total amount per status, per store, or per customer**, the problem becomes **grouping**. In that case, `Collectors.groupingBy` combined with a downstream collector usually expresses the intent better than a complex `reduce`.

## 9. Three-parameter reduce and compatibility between accumulator and combiner

With the overload `reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)`, it is not enough for the accumulator and combiner to “look reasonable”. They must be **compatible with each other**.

Consider the total length example from section 2:

```java
long total = words.parallelStream()
        .reduce(
                0L,
                (partial, word) -> partial + word.length(),
                Long::sum
        );
```

Consider an element `"Java"`, the total length increases by 4. If a branch has a local sum of 6, incorporating the result of this word must be equivalent:

```text
accumulator(6, "Java") = 10
combiner(6, accumulator(0, "Java")) = combiner(6, 4) = 10
```

The contract can be summarized as:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

At the same time, `identity` must be neutral with respect to `combiner`, and `combiner` must be associative. The behavioral functions must be stateless, must not modify the source, and must not depend on side effects that could alter the result depending on how Java partitions the work.

If the combiner is written incorrectly, a sequential pipeline may still “look right” because branch merging is not yet needed, while a parallel stream produces a different result. This is why when defining a three-parameter reducer you need to verify **both** the accumulation path and the combining path.

## 10. Does reduce stop early? Cost and infinite sources

`reduce` normally needs to process all elements allowed to reach it; it is **not** a short-circuit terminal operation like `findFirst`, `anyMatch`, or `allMatch`.

For example, wanting to know whether there is a negative number:

```java
import java.util.stream.IntStream;

boolean hasNegative = IntStream.of(5, 4, -1, 8)
        .anyMatch(n -> n < 0);

System.out.println(hasNegative); // true
```

Mathematically, one could also reduce Boolean values with OR, but `anyMatch` expresses the intent better and can stop as soon as a negative number is seen. With an infinite Stream, a `reduce` over the entire source may never complete; only place `reduce` after an appropriate bounding step if you want it to terminate.

```java
long sumFirstTen = java.util.stream.LongStream.iterate(1L, n -> n + 1)
        .limit(10)
        .sum();

System.out.println(sumFirstTen); // 55
```

In the case above, `limit(10)` creates a finite segment before summing. Do not run `LongStream.iterate(1L, n -> n + 1).reduce(0L, Long::sum)` without another stopping condition: an infinite source will prevent the reduction from terminating normally.

### Boxing and object-creation overhead

`Stream<Integer>.reduce(...)` can incur boxing and unboxing whereas `IntStream.sum()` or `IntStream.reduce(...)` operates on primitive values. Reducing strings with `reduce("", String::concat)` can create many intermediate strings and increase memory allocation cost; if the goal is text concatenation, `Collectors.joining` or `StringBuilder` inside `collect` is usually more suitable.

There is no guarantee that “reduce is always faster than collect”. Choose the API based on the data and combining operation first; when performance truly matters, measure against actual source sizes, JDK, and parallel conditions.

## 11. Parallel reduce: what to assume and what not to assume

Suppose a Stream needs to sum numbers:

```java
long parallelSum = java.util.stream.LongStream.rangeClosed(1, 1_000_000)
        .parallel()
        .sum();

System.out.println(parallelSum); // 500000500000
```

Here, the `long` addition result fits within the representable range, so branches can be combined in many ways and still yield the same sum. However, a parallel stream is not automatically faster; splitting the source, scheduling, and merging branches also incur overhead.

Design principles:

- **Do not share mutable state** via variables outside the lambda as an “accumulator” for `reduce`. External state can be updated concurrently or cause nondeterministic results.
- **Do not depend on the invocation count or call order of the accumulator/combiner**. Java is permitted to partition the data differently.
- **Ensure identity and associativity**. If the result depends on grouping, the combining operation is unsuitable for general-purpose `reduce`.
- **Consider encounter order**. For non-commutative combining operations, the logical order of the source may matter; do not add `unordered()` if the business logic requires order.
- **Consider resources**. Terminal `reduce` does not automatically close Streams holding files/connections; I/O sources still require `try-with-resources`.

Example of reading values from a file and summing with proper resource lifecycle:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long sumLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(String::trim)
                .filter(text -> !text.isEmpty())
                .mapToLong(Long::parseLong)
                .sum();
    }
}
```

The example assumes non-empty lines are valid integers. Malformed data can cause `Long.parseLong` to throw `NumberFormatException`, yet `try-with-resources` still closes the file. If a read error occurs during lazy traversal, Java can wrap the I/O error in an `UncheckedIOException`. With resource-backed sources, proper release is a separate responsibility, independent of choosing `reduce`, `sum`, or `collect`.

## 12. Common mistakes when choosing reduce

| Usage pattern or assumption | Issue | How to handle |
| --- | --- | --- |
| `reduce(0, Integer::max)` on negative numbers | Identity is not neutral | Use `max` or `reduce(Integer::max)` returning Optional |
| `reduce(0, (a,b) -> a-b)` | Subtraction is not associative | Express the problem differently or process sequentially according to specific requirements |
| `reduce(new ArrayList<>(), (list,x) -> {list.add(x); return list;}, ...)` | Mutates mutable identity, breaks contract in parallel | Use `collect` |
| `reduce("", String::concat)` to concatenate very large text | Creates many temporary strings | Use `Collectors.joining` |
| `reduce(...)` to check if an element satisfies a condition | May process the entire source | Use `anyMatch` |
| `reduce(...)` to find maximum/minimum | Verbose and easy to pick wrong identity | Use `max`/`min` |
| `Stream<Integer>` then very large arithmetic reduction | Boxing, integer limits | Use primitive streams or an appropriate numeric type |
| Choosing `Integer.MIN_VALUE` as identity without accounting for empty source | Default value may be mistaken for real data | Use Optional if absence must be distinguished |
| Using the same reducer for sequential/parallel without associativity | Result differs when grouping changes | Prove the combining operation is associative |
| Closing the file right after terminal operation finishes | `reduce` does not call `close` automatically | Use `try-with-resources` |

## 13. Decision process for choosing a reduction tool

When facing a data aggregation requirement, you can decide in this order:

1. **Is there a specialized terminal operation?** If you need `sum`, `count`, `min`, `max`, `average`, `summaryStatistics`, prefer the matching method.
2. **Can it stop early?** If finding an element or checking a condition, consider `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`.
3. **Is a mutable container needed?** If you want a `List`, `Map`, grouping, partitioning, or long strings, look at `collect` and standard `Collector`s.
4. **If it truly is a single reduced value, is there a valid combining operation?** Determine the identity, associativity, empty-source semantics, and result type.
5. **Do you need a result type different from the element type?** You can map before `reduce`, use a primitive stream, or use the three-parameter overload if appropriate.
6. **Is parallel execution needed?** Verify compatibility between accumulator and combiner, purity, and source splittability.
7. **What is the actual cost?** Consider boxing, temporary object creation, numeric overflow, floating-point error, and data reading cost.

### Quick decision examples

| Requirement | Suggested expression |
| --- | --- |
| Sum of integers from a List | `numbers.stream().mapToInt(Integer::intValue).sum()` |
| Maximum in a possibly empty List | `numbers.stream().max(Integer::compareTo)` |
| Product of integers | `numbers.stream().reduce(1, (a,b) -> a*b)` |
| Join a list of words with commas | `words.stream().collect(Collectors.joining(", "))` |
| Group orders by status | `orders.stream().collect(Collectors.groupingBy(Order::status))` |
| Total BigDecimal amount | `amounts.stream().reduce(BigDecimal.ZERO, BigDecimal::add)` |
| Check if an invalid record exists | `records.stream().anyMatch(this::isInvalid)` |

The examples above illustrate API selection; they do not by themselves solve additional business rules such as duplicates, rounding, access permissions, or source data stability.

## 14. Self-check

1. What does `reduce(0, Integer::sum)` return on an empty Stream? **0**, because that is the identity of addition.
2. What does `reduce(Integer::max)` return on an empty Stream? **Optional.empty()**, because there are no elements.
3. Why is `reduce(0, Integer::max)` incorrect for a source of all negative numbers? **0 is not the identity of max** on that domain.
4. Can subtraction be used as a reducer to guarantee the same result across parallel branch splits? **No**, because subtraction is not associative.
5. When should you choose `collect` instead of `reduce`? **When building a mutable container** such as a List, Set, Map, or an updatable statistics accumulator.
6. Why can `String::concat` inside `reduce` be slow when the result is very long? **Because** it creates many intermediate immutable Strings.
7. If you only want to know whether there is a negative number, is `reduce` or `anyMatch` more appropriate? **anyMatch**, because it expresses the condition clearly and can stop early.
8. In the three-parameter `reduce`, what types must the combiner accept? **Two results of type U**, returning a result of type U.
9. Does calling `reduce` on a Stream from `Files.lines` automatically close the file? **No**, the Stream still needs to be closed within the resource-owning scope.
10. Why can a `double` sum differ slightly between sequential and parallel execution? **Because** floating-point addition suffers rounding error and is not strictly associative.

**Application principle:** `reduce` is suitable when the problem is genuinely **combining values into a single result using an associative operation**. Determine the right identity and empty-source handling first, keep the accumulator pure, and only then consider parallelism. For aggregations with specialized APIs or mutable state, choosing `sum`, `max`, `anyMatch`, or `collect` is usually clearer, safer, and easier to optimize.
