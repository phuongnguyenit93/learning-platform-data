# Associativity and the Identity Element in Reduction

In the Java Stream API, `reduce` aggregates multiple elements of a stream into a single result: a sum, a product, a joined string, a maximum value, or a composite structure. However, for the result to remain meaningful when Java changes how it splits data and merges intermediate results, the reduction must satisfy **associativity** and use the right **identity element**.

This lesson belongs to the chapter **Reduction with reduce** of the **JAVA_STREAM_API** module. The lesson focuses on the mathematical and execution contract of `reduce`, from sequential streams to `parallelStream()`, designing accumulators/combiners, and constraints around shared state, numeric precision, and performance. After completing it, you will be able to explain *why a `reduce` expression can work on a few elements yet fail in parallel*, and know when to choose `collect` for accumulating into a mutable object.

## 1. What does a reduction express?

Consider a list of numbers:

```java
import java.util.List;

List<Integer> values = List.of(2, 4, 6);

int sum = values.stream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 12
```

`reduce(0, Integer::sum)` describes a calculation with two components:

- **Identity**: `0`, the neutral value and also the result when the stream is empty.
- **Accumulator**: `Integer::sum`, the operation combining two values into one value of the same type.

Conceptually, sequential left-to-right addition is:

```text
Initially: acc = 0
Element 2: acc = 0 + 2 = 2
Element 4: acc = 2 + 4 = 6
Element 6: acc = 6 + 6 = 12
```

That is a helpful mental model for learning, but **not an execution constraint on `reduce`**. The framework can group elements differently, especially in a parallel pipeline. The two mathematical rules below explain when regrouping still produces the same result.

## 2. Associativity

A binary operation `⊕` is called **associative** if for all valid `a`, `b`, `c`:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

The operation can be grouped in different ways without changing the result. This is the core condition because a stream can be split into segments to compute partial sums and then combined.

For example, integer addition in a non-overflowing range:

```text
(2 + 4) + 6 = 12
2 + (4 + 6) = 12
```

String concatenation is also associative:

```text
("Ja" + "v") + "a" = "Java"
"Ja" + ("v" + "a") = "Java"
```

But subtraction is **not**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Therefore, using subtraction as a parallel reduction fails to satisfy the associative accumulator contract.

### 2.1. Associativity differs from commutativity

**Commutativity** is a different rule:

```text
a ⊕ b = b ⊕ a
```

String concatenation is associative, yet **not commutative**: `"ab"` differs from `"ba"`. Do not confuse `reduce`'s associativity requirement with requiring commutativity.

```java
String word = List.of("Ja", "v", "a").parallelStream()
        .reduce("", String::concat);

System.out.println(word); // Java
```

A `List` source has an encounter order, string concatenation is associative, and the empty string is the identity. Hence, combining contiguous segments can yield `"Java"` without performing every concatenation on a single thread. If you use a source **without an encounter order** or drop ordering constraints, do not expect the same character concatenation order.

### 2.2. Some common operations

| Operation | Associative in which domain? | Notes |
|---|---|---|
| Adding `int`, `long` | Yes under Java's modulo integer arithmetic; under ordinary arithmetic when not overflowing | Overflow can break business meaning |
| Multiplying `int`, `long` | Yes under modulo integer arithmetic; under ordinary arithmetic when not overflowing | Must choose identity `1` |
| `Math.min`, `Math.max` | Yes for appropriate integer domains | Identity must be genuinely neutral over the entire domain |
| Concatenating `String` | Yes | Not commutative; preserve source order if needed |
| Adding `BigDecimal` without `MathContext` rounding | Yes by numeric value | Suitable when exact decimals are required |
| Subtraction, division | Not associative in general | Do not use as an arbitrary parallel accumulator |
| Adding `double` | Not strictly due to rounding | Addition grouping order can change result bits |
| Averaging directly from two averages | Invalid if element counts are omitted | Must track both sum and count |

**Note:** the rule for `reduce` is a contract over the **entire real data domain**, not just a few test samples that happen to match.

## 3. Identity element

An element `e` is the identity of operation `⊕` if for all valid `x`:

```text
e ⊕ x = x
x ⊕ e = x
```

For certain `reduce` overloads, Java requires the identity to be the neutral element of the combining operation. Because a parallel pipeline can create partial segment results starting from the identity, picking the wrong identity causes numeric errors or extra values.

| Combining operation | Correct identity | Illustration |
|---|---|---|
| Integer sum | `0` | `0 + x = x` |
| Integer product | `1` | `1 * x = x` |
| String concatenation | `""` | `"" + s = s` |
| Union of immutable sets | Empty set | `∅ ∪ S = S` |
| Maximum value in `int` domain | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Minimum value in `int` domain | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

Sum and product examples:

```java
List<Integer> numbers = List.of(2, 3, 4);

int sum = numbers.stream().reduce(0, Integer::sum);
int product = numbers.stream().reduce(1, (a, b) -> a * b);

System.out.println(sum);     // 9
System.out.println(product); // 24
```

### 3.1. Wrong identity: the program can run yet return the wrong answer

```java
int wrongSum = List.of(2, 3, 4).stream()
        .reduce(10, Integer::sum);

System.out.println(wrongSum); // 19, because 10 was added in
```

`10` is not the identity of addition. In a sequential pipeline, it adds `10` once to the sum; in a parallel pipeline, multiple tasks may use the identity for different segments, so the discrepancy can differ even further. Do not assume the identity is applied only once across all implementations.

A similar mistake when finding the minimum:

```java
int wrongMin = List.of(4, 8, 6).stream()
        .reduce(0, Integer::min);

System.out.println(wrongMin); // 0, not present in the source data!
```

`0` is not the identity of `min` over all integers. `Integer.MAX_VALUE` can serve as an identity for `min` on `int`, but when you do not want to pick an assumed identity element, use `reduce(BinaryOperator)` or `min` to receive an `Optional`.

### 3.2. Identity determines the result on an empty stream

```java
import java.util.stream.Stream;

System.out.println(Stream.<Integer>empty()
        .reduce(0, Integer::sum)); // 0

System.out.println(Stream.<Integer>empty()
        .reduce(1, (a, b) -> a * b)); // 1

System.out.println(Stream.<String>empty()
        .reduce("", String::concat)); // ""
```

This is a characteristic of overloads with an identity: they return the identity itself when the source has no elements. If `0` or an empty string could cause confusion between “real result is 0” and “no data”, consider the overload returning `Optional`.

## 4. Three `reduce` overloads to distinguish

| Conceptual signature | Return value | Characteristics |
|---|---|---|
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | No identity needed; empty returns `Optional.empty()` |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | Neutral element must be valid |
| `reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` | `U` | Can reduce from `T` to type `U`; accumulator and combiner must be compatible |

Primitive streams such as `IntStream`, `LongStream`, and `DoubleStream` have corresponding primitive reduction overloads; `sum()`, `min()`, and `max()` are also specialized terminal operations.

### 4.1. `reduce(BinaryOperator)`: no identity needed

```java
import java.util.Optional;

Optional<Integer> max = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // 9
```

If the source is empty:

```java
Optional<Integer> missing = Stream.<Integer>empty()
        .reduce(Integer::max);

System.out.println(missing.isEmpty()); // true
```

This overload avoids an unsuitable or unnatural identity. When you only need an extremum, `stream.max(Integer::compareTo)` or `stream.min(Integer::compareTo)` is usually more direct. `Optional` describes the case of no elements; do not call `get()` without checking if the stream could be empty.

### 4.2. `reduce(identity, accumulator)`: same type

```java
int totalLength = List.of("Java", "API").stream()
        .map(String::length)
        .reduce(0, Integer::sum);

System.out.println(totalLength); // 7
```

Here `map` converts each string to an integer, so `reduce` works homogeneously with `Integer`. With `IntStream`, it can be expressed more concisely:

```java
int length = List.of("Java", "API").stream()
        .mapToInt(String::length)
        .sum();

System.out.println(length); // 7
```

`IntStream.sum()` states the summing goal clearly and avoids unnecessary boxing during the aggregation phase.

### 4.3. `reduce(identity, accumulator, combiner)`: different input and result types

For example, an order has quantities and unit prices in cents, and we want total revenue as a `long`:

```java
record Line(String sku, int quantity, long unitPriceCents) {}

List<Line> lines = List.of(
        new Line("A", 2, 150L),
        new Line("B", 1, 425L),
        new Line("C", 3, 100L)
);

long revenueCents = lines.parallelStream().reduce(
        0L,
        (subtotal, line) -> subtotal
                + line.quantity() * line.unitPriceCents(),
        Long::sum
);

System.out.println(revenueCents); // 1025
```

In the three-argument overload:

- `T` is `Line`, the source element.
- `U` is `Long`, the intermediate and final result type.
- `identity = 0L` is the neutral element of the combiner `Long::sum`.
- Accumulator converts a `Line` into its contribution and adds it to the partial total.
- Combiner merges two partial totals; especially required when running in parallel.

In the example, `2 * 150 + 1 * 425 + 3 * 100 = 1025`. Integer arithmetic in the smallest currency unit is used to avoid decimal rounding errors; real data must guard against `long` overflow.

## 5. Compatibility between accumulator and combiner

The three-argument overload requires more than each lambda simply “looking right”. By the Stream API contract:

1. Combiner must be associative.
2. Identity must be the neutral element of the combiner.
3. Accumulator and combiner must be **compatible**: a source element contributes the same way whether added directly to a partial total or accumulated into its own partial total and then merged.

Expressed with `u` of result type `U`, `t` of input type `T`, and `e` as identity:

```text
combiner(u, accumulator(e, t)) = accumulator(u, t)
```

With the string-length summation example:

```java
int characterCount = List.of("ab", "cde", "f").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                Integer::sum
        );

System.out.println(characterCount); // 6
```

Suppose `u = 5`, `t = "abc"`, `e = 0`:

```text
accumulator(0, "abc") = 3
combiner(5, 3) = 8
accumulator(5, "abc") = 8
```

Both sides are equal, so the operations are compatible. If you replace the combiner with multiplication, the expression may still compile but no longer obeys the contract:

```java
// Semantically wrong: combiner is incompatible with summing lengths.
int wrong = List.of("ab", "cde", "f").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                (left, right) -> left * right
        );
// No guarantee of producing the desired character count.
```

`0` is also not the identity of multiplication; this bug violates both requirements. In subtle cases, a sequential pipeline may accidentally return the right result because the combiner is not invoked in the way you observe, and then fail in parallel.

## 6. Why does associativity matter in parallel execution?

With a finite source `[2, 4, 6, 8]`, one possible aggregation grouping is:

```text
Source:      [ 2, 4, 6, 8 ]
                  /     \
Group 1:       [2,4]   [6,8]
                 |       |
Partial sum:     6      14
                  \    /
                 Combine
                    |
                   20
```

Associativity allows the framework to partition work as appropriate. Java does not promise that every parallel run will split into exactly two groups as shown. When the operator is non-associative, different groupings can produce different results.

### 6.1. Subtraction: counterexample

```java
List<Integer> values = List.of(10, 3, 2);

int difference = values.stream()
        .reduce(0, (a, b) -> a - b);

System.out.println(difference); // Under ordinary sequential reduction: -15
```

A sequential example can mislead us into thinking `reduce(0, (a, b) -> a - b)` means “subtract every element in sequence”. Yet `0` is not a **two-sided** neutral element of subtraction and subtraction is not associative. Do not use this reduction to express a parallel aggregation.

If the goal is **negate and sum**, express it using associative addition:

```java
int negativeSum = values.parallelStream()
        .mapToInt(n -> -n)
        .sum();

System.out.println(negativeSum); // -15
```

Switching from subtraction to summing negated numbers satisfies the associativity contract for `int` under Java arithmetic; for integer data that might exceed the representable range, check for overflow separately.

### 6.2. Division and naive averaging

Consecutive divisions are likewise non-associative:

```text
(100 / 10) / 2 = 5
100 / (10 / 2) = 20
```

Similarly, the formula `(a + b) / 2` to “merge two averages” is usually wrong when the two groups have different element counts. For instance, `[10, 20]` has average `15`, `[90]` has average `90`; `(15 + 90) / 2 = 52.5` is not the average of the three numbers, which is `40`.

If an average is needed, you must retain **both sum and count** and divide at the end, or use `IntStream.average()`, `DoubleStream.average()`, or `Collectors.averagingInt(...)` depending on the goal.

## 7. A valid reduction for sum and count statistics

We can design an immutable result type to accumulate two pieces of information simultaneously. For example, using `long` for the count and sum of small integer inputs:

```java
record Stats(long count, long sum) {
    Stats combine(Stats other) {
        return new Stats(
                this.count + other.count,
                this.sum + other.sum
        );
    }
}

Stats identity = new Stats(0, 0);

Stats result = List.of(10, 20, 90).parallelStream()
        .map(n -> new Stats(1, n))
        .reduce(identity, Stats::combine);

double average = (double) result.sum() / result.count();

System.out.println(result);  // Stats[count=3, sum=120]
System.out.println(average); // 40.0
```

`combine` adds counts and sums **component-wise**, so it is associative under Java integer arithmetic; `Stats(0, 0)` is the identity. `Stats` instances are immutable records, with no shared mutable accumulator object across branches.

Two concerns should be kept distinct:

- **The reduce contract:** merging two statistics results is associative, allowing partial sums to be combined.
- **Precision and data domain limits:** `long` sums can overflow. With real data, select appropriate numeric types and overflow/precision handling.

This example illustrates the laws of `reduce`; in simple applications, `Collectors.summarizingInt(...)`, `IntStream.summaryStatistics()`, or `average()` are usually more convenient APIs.

## 8. Why do mutable accumulators easily go wrong with `reduce`?

Do not use a mutable `ArrayList`, `StringBuilder`, or `HashMap` as the identity and mutate it directly inside `reduce`'s accumulator, especially in parallel execution:

```java
import java.util.ArrayList;

// Example not to use:
// List<String> bad = List.of("A", "B", "C").parallelStream()
//         .reduce(
//                 new ArrayList<String>(),
//                 (list, text) -> {
//                     list.add(text);
//                     return list;
//                 },
//                 (left, right) -> {
//                     left.addAll(right);
//                     return left;
//                 }
//         );
```

Reasons:

1. A mutable identity may be reused as the starting value across branches. Multiple branches mutating one object can cause a **data race**.
2. Calling `add` on the identity itself mutates what is supposed to be a neutral element, breaking the reduction conditions.
3. During merging, `left` and `right` may refer to the exact same object; `addAll` can duplicate elements or lead to invalid results.

If the goal is collecting elements into a list, use **mutable reduction** via `collect`:

```java
List<String> result = List.of("A", "B", "C").parallelStream()
        .collect(java.util.stream.Collectors.toList());

System.out.println(result); // [A, B, C]
```

Or if you want to build a string with `StringBuilder`, let the collector create a separate container per accumulation segment and merge them:

```java
StringBuilder joined = List.of("Ja", "v", "a").parallelStream()
        .collect(
                StringBuilder::new,
                (builder, part) -> builder.append(part),
                (left, right) -> left.append(right)
        );

System.out.println(joined); // Java
```

For strings with a delimiter, `Collectors.joining(", ")` is usually simpler. `collect` is the natural choice when the result is a mutable container; `reduce` suits value-combining operations that do not mutate shared objects.

## 9. `reduce` does not mean every operation is strictly exact

API associativity requirements and numeric type precision are not entirely identical. Additions on `double` can differ by grouping due to binary rounding:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Consequently:

```java
List<Double> values = List.of(1e16, -1e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println("Sequential: " + sequential);
System.out.println("Parallel: " + parallel);
// The two results are not required to be bitwise identical.
```

In many numerical applications, rounding error within a tolerance defined by business requirements is acceptable. `DoubleStream.sum()` allows implementations to use compensated summation algorithms and is usually more appropriate than `reduce(0.0, Double::sum)` if the sole goal is summing `double`s. When exact decimal addition is required, consider `BigDecimal` created from decimal strings:

```java
import java.math.BigDecimal;

BigDecimal amount = List.of("0.10", "0.20", "0.30").stream()
        .map(BigDecimal::new)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(amount); // 0.60
```

`BigDecimal` addition without `MathContext` is exact in decimal value; do not construct with `new BigDecimal(0.1)` when the goal is exact decimal `0.1`. For integers, `Integer::sum` and `Long::sum` can overflow; problems with strict bounds may require `BigInteger` or overflow detection via `Math.addExact` using an appropriate algorithm.

## 10. Connection to lifecycle, infinite sources, and performance

`reduce` is a **terminal operation**: it consumes the stream and returns the final result. Another terminal operation cannot be called on the same consumed stream object.

```java
var stream = List.of(1, 2, 3).stream();
int total = stream.reduce(0, Integer::sum);
System.out.println(total); // 6

// stream.count(); // Wrong: the stream has already been consumed.
```

With an infinite source lacking a stopping condition, `reduce` normally cannot finish because it must traverse all elements. Bound the source with `limit` if the requirement is to process a finite count:

```java
import java.util.stream.Stream;

int sampleTotal = Stream.generate(() -> 2)
        .limit(5)
        .reduce(0, Integer::sum);

System.out.println(sampleTotal); // 10
```

Do not place `reduce` on an infinite `Stream.generate(...)` without controlling the termination point. For resource-backed sources like `Files.lines(path)`, use `try-with-resources` to close the stream even on exceptions; `reduce` does not automatically release resources opened by the source provider.

Regarding performance, `parallelStream()` incurs task-splitting and result-merging overhead. A simple reduction over a few hundred elements can be faster sequentially. Choose parallel execution only when the operation obeys the contract, the data is sufficiently large, and real benchmarks prove a benefit. Do not introduce side effects in the accumulator/combiner to “count invocations”: the framework does not commit to a fixed order or structure of combinations.

## 11. Runnable comprehensive example (Java 17+)

The following program brings together the rules above: proper identities for sum/product, `Optional` without identity, associative string concatenation, three-argument overload, and immutable statistics.

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ReduceLawsDemo {
    record Line(String code, int quantity, long unitPriceCents) {}

    record Stats(long count, long sum) {
        Stats combine(Stats other) {
            return new Stats(count + other.count, sum + other.sum);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 4);

        int sum = numbers.parallelStream().reduce(0, Integer::sum);
        int product = numbers.parallelStream()
                .reduce(1, (a, b) -> a * b);
        System.out.println(sum);     // 9
        System.out.println(product); // 24

        Optional<Integer> max = numbers.stream().reduce(Integer::max);
        System.out.println(max.orElseThrow()); // 4
        System.out.println(Stream.<Integer>empty()
                .reduce(Integer::max).isEmpty()); // true

        String word = List.of("Ja", "v", "a").parallelStream()
                .reduce("", String::concat);
        System.out.println(word); // Java

        List<Line> lines = List.of(
                new Line("A", 2, 150L),
                new Line("B", 1, 425L),
                new Line("C", 3, 100L)
        );
        long revenue = lines.parallelStream().reduce(
                0L,
                (subtotal, line) -> subtotal
                        + line.quantity() * line.unitPriceCents(),
                Long::sum
        );
        System.out.println(revenue); // 1025

        Stats stats = numbers.parallelStream()
                .map(n -> new Stats(1, n))
                .reduce(new Stats(0, 0), Stats::combine);
        System.out.println(stats); // Stats[count=3, sum=9]
        System.out.println((double) stats.sum() / stats.count());
        // 3.0

        List<Integer> doubled = numbers.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.toList());
        System.out.println(doubled); // [4, 6, 8]
    }
}
```

In the example, values are small enough that no overflow occurs. When designing real business logic, determine the data range, empty-data policy, and reproducibility requirements before picking numeric types and execution modes.

## 12. Common mistakes

| Mindset or code pattern | Issue | How to handle |
|---|---|---|
| “Any binary operator works for parallel reduce” | Subtraction/division are not associative | Use an associative operation obeying the contract or a specialized algorithm |
| “Identity is only used once” | Parallel execution can use identity across multiple branches | Pick a true neutral element |
| “`reduce(10, Integer::sum)` computes a normal sum” | `10` is an added value, not the identity | Use `0` for addition |
| “`reduce(0, Integer::min)` returns the min of positive numbers” | `0` can corrupt the result | Use the `Optional` overload or a valid identity |
| “String concatenation is not commutative so it cannot be reduced” | Confusing associativity and commutativity | Can be reduced with a source having encounter order and identity `""` |
| “Accumulator sums lengths and combiner multiplies is fine” | Violates compatibility between accumulator and combiner | Choose a combiner that adds partial sums |
| “You can use `new ArrayList<>()` as identity and `add` inside reduce” | Mutable identity is shared and mutated | Use `collect` for mutable containers |
| “Parallel execution with `double` is always bitwise identical to sequential” | Floating-point addition is not strictly associative | Use a tolerance or an appropriate numerical strategy |
| “`reduce` stops on its own on an infinite source” | Terminal operation must consume the entire source | Limit the source or pick an approach with a stopping condition |
| “Enabling `parallel()` always makes it faster” | Splitting and combining incur overhead | Benchmark on real data |

## 13. Self-check

1. **What are the two fundamental conditions of `reduce(identity, accumulator)`?** The accumulator is associative; the identity is the neutral element of the combining operation.
2. **Why does `reduce(1, (a, b) -> a * b)` use `1`?** Because `1 * x = x * 1 = x`.
3. **For the list `[2, 3]`, what does `reduce(5, Integer::sum)` return if added sequentially?** It returns `10`; it added the wrong identity `5`.
4. **Does associativity mean the same thing as commutativity?** No. String concatenation is associative, yet `"ab"` differs from `"ba"`.
5. **Why is `reduce(0, (a, b) -> a - b)` unsuitable for parallel execution?** Subtraction is not associative and `0` is not two-sided neutral.
6. **What does the `reduce(BinaryOperator)` overload return when the stream is empty?** `Optional.empty()`, allowing absence to be handled without fabricating an identity.
7. **In the three-argument overload, what is the role of the combiner?** Merging intermediate results of type `U`; it must be associative and compatible with the accumulator.
8. **Why not use a mutable `StringBuilder` or `ArrayList` as the identity in `reduce`?** Because the identity can be shared and mutated, breaking the contract and causing races; use `collect` to create separate accumulation containers.
9. **Why can sequential and parallel `double` sums differ?** Different addition grouping changes rounding error; `double` addition is not strictly associative.
10. **To compute an average from partial sums, what must be stored?** Both sum and count; taking the average of averages alone is insufficient when group sizes differ.

**Key takeaway:** Check **whether the combining operation is associative**, **whether the identity is neutral on both sides**, and for the three-argument overload, **whether the accumulator is compatible with the combiner**. When those conditions hold, Java can split and combine data safely under the contract. When mutable state accumulation is needed, choose `collect`; when working with floating-point numbers, evaluate rounding error and precision requirements separately.
