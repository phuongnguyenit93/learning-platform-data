# Using reduce with identity and accumulator

In the Java Stream API, **`reduce`** is a *reduction* operation: transforming multiple elements into a single result by combining elements according to a rule. With the `reduce(identity, accumulator)` form, the developer provides a **neutral value** (*identity*) and a **combining rule** (*accumulator*). These two components govern both the result when the Stream is empty and the ability to process correctly when the Stream runs in parallel.

This lesson belongs to the chapter **Reduction with reduce** of the **JAVA_STREAM_API** module. This knowledge continues building lazy pipelines with `filter`, `map`, `reduce`, and `collect`, while laying the foundation for aggregation, data grouping, custom collectors, parallel processing, and evaluating constraints on state, numeric types, resources, and performance.

## 1. Reduction mindset: from many elements to a single value

Suppose we have three numbers `[4, 6, 10]` and need to compute their sum. A familiar loop:

```java
import java.util.List;

List<Integer> numbers = List.of(4, 6, 10);

int total = 0;
for (int number : numbers) {
    total += number;
}

System.out.println(total); // 20
```

The same meaning using a Stream:

```java
int total = numbers.stream()
    .reduce(0, Integer::sum);

System.out.println(total); // 20
```

In the expression `reduce(0, Integer::sum)`:

- **`0` is the identity**: the neutral value of addition. `0 + x = x` and `x + 0 = x`.
- **`Integer::sum` is the accumulator**: the rule that takes two integers and returns their sum.
- **`20` is the result**: a single value produced from the entire Stream.

We can visualize a sequential execution as follows:

```text
identity = 0
0  -- add 4  -->  4
4  -- add 6  --> 10
10 -- add 10 --> 20
                     |
                     v
                 result = 20
```

This diagram helps understand **sequential** reduction, but it does not mean the JVM must always invoke the accumulator following that exact computation tree. Especially in parallel, elements can be reduced into multiple partial results and then combined.

## 2. API signature and roles of the two parameters

For an object Stream, the variant to learn has the form:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

`BinaryOperator<T>` is a functional interface in `java.util.function` that takes **two values of the same type `T`** and returns a value of **the same type `T`**. It is a specialized case of `BiFunction<T, T, T>`.

```java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> add = (left, right) -> left + right;
BinaryOperator<Integer> max = Integer::max;

System.out.println(add.apply(4, 6)); // 10
System.out.println(max.apply(4, 6)); // 6
```

| Component | Type | Role |
| --- | --- | --- |
| Source `Stream<T>` | Elements of type `T` | Supplies the values to reduce |
| `identity` | `T` | Neutral value, and also the result when the Stream is empty |
| `accumulator` | `BinaryOperator<T>` | Combines two values of type `T` into one value of type `T` |
| Result of `reduce` | `T` | Final reduced value |

Primitive Streams also have corresponding forms:

| Source | `reduce` form | Result type |
| --- | --- | --- |
| `IntStream` | `reduce(int identity, IntBinaryOperator accumulator)` | `int` |
| `LongStream` | `reduce(long identity, LongBinaryOperator accumulator)` | `long` |
| `DoubleStream` | `reduce(double identity, DoubleBinaryOperator accumulator)` | `double` |

Example:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int intTotal = IntStream.of(4, 6, 10)
    .reduce(0, Integer::sum);

long longTotal = LongStream.of(4L, 6L, 10L)
    .reduce(0L, Long::sum);

System.out.println(intTotal);  // 20
System.out.println(longTotal); // 20
```

`reduce` is a **terminal operation**: it triggers consumption of the pipeline. A Stream already used by `reduce` cannot be reused for another terminal operation.

## 3. Choosing identity: a neutral value, not an “arbitrary initial number”

The most important condition of `identity` is: for every valid value `x` in the data domain, combining with `identity` must preserve the meaning of `x`.

```text
accumulator(identity, x) = x
```

For common reductions, `identity` is neutral on both sides:

```text
accumulator(identity, x) = x
accumulator(x, identity) = x
```

Examples:

| Goal | Identity | Accumulator | Why |
| --- | --- | --- | --- |
| Compute sum | `0` | `Integer::sum` | Adding 0 does not change a number |
| Compute product | `1` | `(a, b) -> a * b` | Multiplying by 1 does not change a number |
| Concatenate strings | `""` | `String::concat` | Concatenating an empty string adds no content |
| Maximum value in `int` domain | `Integer.MIN_VALUE` | `Integer::max` | Every `int` is greater than or equal to the minimum value |
| Minimum value in `int` domain | `Integer.MAX_VALUE` | `Integer::min` | Every `int` is less than or equal to the maximum value |
| Logical “all true” on `Boolean` | `true` | `(a, b) -> a && b` | `true && x` equals `x` |
| Logical “at least one true” on `Boolean` | `false` | `(a, b) -> a \|\| b` | `false \|\| x` equals `x` |

For `min`/`max` operations, picking a boundary value as above only makes sense when **the entire data domain is known**. The result of an empty Stream will be that boundary value, which can be confused with a real element equal to the boundary value. When you need to distinguish **no data**, the `reduce` form without identity or `min()`/`max()` returning `Optional` is usually more suitable.

### 3.1. Example with product

```java
import java.util.List;

List<Integer> factors = List.of(2, 3, 4);

int product = factors.stream()
    .reduce(1, (left, right) -> left * right);

System.out.println(product); // 24
```

If `0` is used as the identity for multiplication, the result is always `0` in sequential reduction and all input information is completely lost.

### 3.2. Mistake: using a non-neutral initial value

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// Wrong if you want to compute "sum of elements".
int misleading = values.stream()
    .reduce(10, Integer::sum);

System.out.println(misleading); // 16 in a sequential pipeline
```

In addition, `10` is not an identity. With sequential processing, the example above computes `10 + 1 + 2 + 3`, i.e., **the sum plus 10**, rather than the sum of the elements. In parallel, the value `10` may be used for multiple partial results, causing larger discrepancies that depend on how the data is split.

If you genuinely need a **surcharge of 10 after the sum**, express that intent explicitly:

```java
int totalWithSurcharge = values.stream()
    .reduce(0, Integer::sum) + 10;

System.out.println(totalWithSurcharge); // 16
```

Here `reduce(0, Integer::sum)` is a valid reduction; adding the surcharge is performed **after** obtaining the result.

## 4. The accumulator needs associativity

For a reduction to be split into multiple groups while preserving the result, the accumulator must be **associative**:

```text
accumulator(accumulator(a, b), c)
    =
accumulator(a, accumulator(b, c))
```

For integer addition (when the result is interpreted under Java integer semantics), we have:

```text
(2 + 3) + 4 = 2 + (3 + 4) = 9
```

**Subtraction** is not associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Therefore, the following snippet is not a valid reduction design for parallel processing:

```java
import java.util.stream.IntStream;

int sequential = IntStream.of(10, 3, 2)
    .reduce(0, (left, right) -> left - right);

System.out.println(sequential); // -15 under sequential execution
```

The result of reducing with subtraction can change when element grouping changes. Do not use `parallel()` with a non-associative accumulator and expect the same result as sequential execution.

### 4.1. Associativity differs from commutativity

Two concepts often confused:

- **Associative:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Commutative:** `a ⊕ b = b ⊕ a`.

`String::concat` is associative, but not commutative:

```java
import java.util.List;

List<String> letters = List.of("A", "B", "C");

String joined = letters.stream()
    .reduce("", String::concat);

System.out.println(joined); // ABC
```

`"A" + "B"` differs from `"B" + "A"`. With an ordered source and a valid reduction, the Stream can combine parts while preserving encounter order according to the reduction semantics. However, `reduce` is not the most efficient solution for concatenating many strings, because repeated string concatenation can create many temporary objects. When the goal is joining strings, `Collectors.joining()` is usually used.

You should not attach side effects (such as logging or incrementing a shared counter) to the accumulator and rely on the order or number of times the function is called. In parallel execution, grouping and combination counts may differ.

## 5. Empty Stream: the result is the identity itself

An important characteristic of the **two-parameter** variant is that it always returns `T`, even when the source has no elements. In that case, the result is the identity itself.

```java
import java.util.List;

List<Integer> emptyNumbers = List.of();

int sum = emptyNumbers.stream()
    .reduce(0, Integer::sum);

int product = emptyNumbers.stream()
    .reduce(1, (a, b) -> a * b);

System.out.println(sum);     // 0
System.out.println(product); // 1
```

This is valid semantics: **the sum of an empty set is defined as 0**, and **the product of an empty set is defined as 1**, corresponding to the neutral element of each operation.

However, `reduce(identity, accumulator)` does not tell whether the result came from an empty set or from actual elements:

```java
List<Integer> zeroSum = List.of(2, -2);
List<Integer> noData = List.of();

int a = zeroSum.stream().reduce(0, Integer::sum);
int b = noData.stream().reduce(0, Integer::sum);

System.out.println(a); // 0: data exists, and the sum is 0
System.out.println(b); // 0: no data
```

If business requirements need to distinguish the two cases, design the result to include data-presence state or use the `reduce` variant returning `Optional`.

### 5.1. Comparison with `reduce(accumulator)` without identity

`Stream<T>` also provides:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

This is the variant **without identity**. When the Stream is empty, the result is `Optional.empty()`.

```java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of();

Optional<Integer> maxValue = numbers.stream()
    .reduce(Integer::max);

System.out.println(maxValue.isPresent()); // false

Optional<Integer> withData = List.of(-5, -2, -9)
    .stream()
    .reduce(Integer::max);

System.out.println(withData.orElseThrow()); // -2
```

To get the maximum value, `stream.max(Integer::compare)` expresses the intent more clearly; the example above merely illustrates the difference in result on an empty Stream.

| Variant | Empty Stream | When to use |
| --- | --- | --- |
| `reduce(identity, accumulator)` | Returns `identity` | There is a valid neutral element, and you always want a value `T` |
| `reduce(accumulator)` | `Optional.empty()` | No suitable identity or need to know if the set is empty |
| `sum()` on Primitive Stream | Returns `0` in the matching numeric type | Only need to sum primitive values |
| `min()` / `max()` on Primitive Stream | Empty `OptionalInt` / `OptionalLong` / `OptionalDouble` | Finding extrema and need to reflect missing data |

## 6. Combining `filter`, `map`, and `reduce` in a problem

A practical pipeline often looks like this:

```text
Source        Intermediate operations (lazy)       Terminal operation
List<Sale> --> filter(paid) --> map(amount) --> reduce(0, sum)
                   |                |                   |
              pick orders       get amount        total revenue
```

Suppose we only compute revenue of paid orders, with prices and amounts recorded as `long` integers in VND:

```java
import java.util.List;

public class RevenueReduceDemo {
    record Sale(String id, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S-01", 1_500_000L, true),
            new Sale("S-02",   800_000L, false),
            new Sale("S-03", 2_000_000L, true)
        );

        long revenue = sales.stream()
            .filter(Sale::paid)             // Stream<Sale>
            .mapToLong(Sale::amountVnd)     // LongStream
            .reduce(0L, Long::sum);         // long

        System.out.println(revenue);        // 3500000
    }
}
```

Here, `LongStream.reduce(0L, Long::sum)` is a clear reduction. Because the goal is simply a sum, `.sum()` is equivalent in intent and shorter:

```java
long revenue = sales.stream()
    .filter(Sale::paid)
    .mapToLong(Sale::amountVnd)
    .sum();
```

When a reduction rule *other than* built-in operations is needed, `reduce` is more valuable. For example, taking the maximum value while deliberately choosing `Long.MIN_VALUE` as the identity:

```java
long largestAmount = sales.stream()
    .mapToLong(Sale::amountVnd)
    .reduce(Long.MIN_VALUE, Long::max);
```

With an empty list, the example returns `Long.MIN_VALUE`. If you need to represent “no orders”, use `mapToLong(...).max()` and handle `OptionalLong` rather than using a special value that could collide with real data.

## 7. Identity must match the exact type of the elements being reduced

In the two-parameter variant of `Stream<T>`, identity and accumulator use the same `T`. This affects how the pipeline is organized.

For example, `Stream<Order>` cannot be reduced directly to `long` using the **two-parameter variant**:

```java
// Assume Sale is the record defined in the RevenueReduceDemo example.
// Type mismatch: Stream<Sale>.reduce(T identity, BinaryOperator<T>)
// does not accept a long identity to return a long:
//
// long total = sales.stream().reduce(0L,
//     (sum, sale) -> sum + sale.amountVnd());
```

To aggregate money, convert the element type first:

```java
long total = sales.stream()
    .mapToLong(Sale::amountVnd)
    .reduce(0L, Long::sum);
```

Or convert to `BigInteger` objects if the `long` range is insufficient:

```java
import java.math.BigInteger;

BigInteger totalExact = sales.stream()
    .map(sale -> BigInteger.valueOf(sale.amountVnd()))
    .reduce(BigInteger.ZERO, BigInteger::add);
```

Java also provides the **three-parameter** `Stream<U>.reduce(identity, accumulator, combiner)` form, allowing a result type different from the source elements and explicitly defining how partial results are merged. That is a different contract, requiring special attention to compatibility between accumulator and combiner; it should not be confused with the two-parameter variant covered here.

## 8. Accumulator should be a pure combining function without mutating shared state

An accumulator suitable for `reduce` has these characteristics:

1. **Non-interfering with the source**: does not modify the collection being traversed by the Stream.
2. **Stateless** (no dependence on mutable state): the result depends only on the two operands, not on invocation count or timing.
3. **Associative**: how operations are grouped does not alter the result under the chosen semantics.
4. **Uses a valid identity**: combining with identity does not alter the value.

For example, `BigInteger::add` is a suitable combining operation: `BigInteger` is immutable, `add` creates a new result, and it has the neutral element `BigInteger.ZERO`.

Conversely, an accumulator that attempts to mutate an external container easily breaks Stream assumptions:

```java
// Do not do this:
int[] sumOutside = {0};

int result = java.util.stream.IntStream.of(1, 2, 3)
    .reduce(0, (acc, value) -> {
        sumOutside[0] += value;  // Side effect.
        return acc + value;
    });
```

This snippet can produce two different total values across execution paths; `sumOutside` is not the official product of `reduce`. With `parallel()`, unsynchronized updates can also cause race conditions. The right approach is to take the result returned by `reduce`.

### 8.1. Why not use `reduce` instead of `collect` for mutable structures?

Suppose we want to merge multiple lists into one list. The following code is **not safe to use as a reduction**, especially in parallel:

```java
import java.util.ArrayList;
import java.util.List;

List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C")
);

// Do not use: accumulator mutates the left object directly,
// where identity is a mutable ArrayList.
List<String> unsafe = groups.stream()
    .reduce(
        new ArrayList<>(),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Mutating `left` directly can modify the shared identity across parallel processing branches, leading to duplicated results or race conditions. Even if the example might yield the desired output in a single sequential pass, this is still a pattern not to apply to `reduce`.

For this goal, there are two cleaner ways to express it:

```java
List<String> flattened = groups.stream()
    .flatMap(List::stream)
    .toList();

List<String> mutableFlattened = groups.stream()
    .flatMap(List::stream)
    .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
```

`toList()` returns an unmodifiable list; `toCollection(ArrayList::new)` creates a list that permits adding/removing elements. In `collect`, mutable accumulators are managed by **supplier, accumulator, and combiner** under the collector contract. Meanwhile, `reduce` is designed for combining operations where operands are not mutated.

### 8.2. String concatenation: a valid reduction is not necessarily efficient

```java
List<String> words = List.of("Java", "Stream", "API");

String joinedByReduce = words.stream()
    .reduce("", String::concat);

String joinedByCollector = words.stream()
    .collect(java.util.stream.Collectors.joining());

System.out.println(joinedByReduce);    // JavaStreamAPI
System.out.println(joinedByCollector); // JavaStreamAPI
```

Both produce the same content, but `Collectors.joining()` is usually more appropriate when joining many strings because its accumulation avoids creating intermediate strings from repeated concatenation. Choose `reduce` when the goal is to understand or express a meaningful immutable combining operation.

## 9. Parallelism: identity can participate multiple times

In a sequential Stream, an addition example can be understood as left-to-right accumulation. With a parallel Stream, the framework can split the source into multiple groups, reduce each group starting from `identity`, and then combine the results.

Illustrating addition with a valid identity:

```text
Data: [2, 3, 4, 5]

Branch A: identity 0 -> add 2 -> add 3 = 5
Branch B: identity 0 -> add 4 -> add 5 = 9
Combine 5 and 9 = 14

Overall: 2 + 3 + 4 + 5 = 14
```

This is just one grouping for explanation; the actual splitting is decided by the Stream implementation. With identity `0` and `Integer::sum`, the calculation has valid semantics under this grouping.

If `identity = 10` is mistakenly used as “add 10 just once”, each branch can have 10 added, and when combined the result will differ from sequential processing. Thus `identity` must be the **neutral element**, not a parameter carrying a business adjustment.

```java
import java.util.stream.IntStream;

int total = IntStream.rangeClosed(1, 1_000)
    .parallel()
    .reduce(0, Integer::sum);

System.out.println(total); // 500500
```

**Important:** `parallel()` does not automatically make an operation faster or more accurate. Performance depends on element count, accumulator cost, source splittability (`Spliterator`), split/merge overhead, and machine resources. For small additions, sequential execution is usually the simpler choice. An accumulator with side effects or without associativity does not become correct merely because the program uses multiple threads.

## 10. Laziness, short-circuiting, and resources

`filter`, `map`, and `mapToLong` are intermediate operations that are normally evaluated **lazily**; `reduce` is a terminal operation that triggers processing:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

var prepared = numbers.stream()
    .filter(n -> n % 2 == 1)
    .map(n -> n * n); // Sum not yet computed.

int squaredOddTotal = prepared
    .reduce(0, Integer::sum);

System.out.println(squaredOddTotal); // 1 + 9 + 25 = 35
```

`reduce` normally needs to traverse all elements **forwarded by intermediate steps**, unlike `anyMatch` or `findFirst` which can stop early once an answer is found. You should not rely on side effects inside intermediate operations to assert they ran exactly once per element; optimizations and execution strategies can change when the pipeline varies.

If the Stream source is tied to a resource such as `Files.lines(path)`, close the resource properly with `try-with-resources`, even when the terminal operation is `reduce`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Place inside a method declaring throws IOException, or handle the exception.
Path path = Path.of("numbers.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long sum = lines
        .filter(s -> !s.isBlank())
        .mapToLong(Long::parseLong)
        .reduce(0L, Long::sum);

    System.out.println(sum);
}
```

`reduce` itself does not turn every I/O source into a self-closing resource. At the same time, a Stream consumed by `reduce` cannot be reused; if another calculation is needed from the same file, design reading and storing/re-traversing according to resource requirements.

## 11. Precision and performance limits

Even when addition has the right identity and associativity, an integer result can still **overflow**.

```java
import java.util.stream.IntStream;

int overflowed = IntStream.of(Integer.MAX_VALUE, 1)
    .reduce(0, Integer::sum);

long widened = IntStream.of(Integer.MAX_VALUE, 1)
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(overflowed); // -2147483648
System.out.println(widened);    // 2147483648
```

Declaring `long widened = intStream.reduce(0, Integer::sum)` **does not fix overflow**, because `int` addition has already happened before assignment. You must widen **before** reducing.

When an exact integer sum exceeds even `long`, `BigInteger` can be used:

```java
import java.math.BigInteger;
import java.util.stream.LongStream;

BigInteger exact = LongStream.of(Long.MAX_VALUE, 1L)
    .mapToObj(BigInteger::valueOf)
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 9223372036854775808
```

If you want to **detect** overflow when adding a finite type, `Math.addExact` can be used as an accumulator, though it throws an exception when an **intermediate sum** overflows. A final sum within bounds can still have an intermediate sum exceed bounds under a particular grouping. When the requirement is the exact mathematical sum first and then checking whether it fits the target type, use a sufficiently wide type or `BigInteger` and convert back with `intValueExact()`/`longValueExact()`.

For `double` floating-point numbers, floating-point addition is **not strictly associative in computer arithmetic** due to rounding rules. Grouping order in a parallel pipeline can lead to differences in trailing digits. When business logic requires exact decimals (e.g., currency), consider `BigDecimal` with appropriate `scale`/rounding rules.

On performance-sensitive paths, `IntStream.sum()` or `LongStream.sum()` usually expresses the summing intent more directly than `reduce(0, ...)`. Measure with JMH and representative data before concluding about speed differences; avoid boxing or creating unnecessary intermediate objects just to express simple addition.

## 12. When to use `reduce` and when to use `collect`?

| Requirement | Usually suitable approach | Why |
| --- | --- | --- |
| Standard `int`/`long`/`double` sum | `sum()` on Primitive Stream | Dedicated API, clear intent |
| Immutable combining operation with identity and associativity | `reduce(identity, accumulator)` | Directly expresses the combining rule |
| Finding extrema and needing to know if source is empty | `min()`, `max()`, or `reduce(accumulator)` | Returns `Optional` when there are no elements |
| Collecting into `List`/`Set`/`Map` | `collect(...)` or `toList()` | Uses an accumulation mechanism suited for containers |
| Grouping by key and summing per group | `groupingBy` with downstream collector | Preserves keys and per-group results |
| Joining strings with a delimiter | `Collectors.joining(delimiter)` | Purpose-built, more readable than manual concatenation |
| Calculations depending on previous element state, needing multiple intermediate results | A loop or dedicated stateful processing tool | `reduce` yields only one final result, not the entire progression |

In advanced Java Stream API usage, custom collectors, `Spliterator`, and Stream Gatherers can help solve problems requiring complex accumulation, source splitting, or stateful transformation. Nevertheless, when the problem only needs **a single combining operation with a valid identity**, `reduce` is usually a clear enough starting point.

## 13. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Choosing `10` as the identity of addition | Not neutral; parallel execution may add it multiple times | Use `0`, add the surcharge after the reduction |
| Choosing `0` as the identity of multiplication | Product is always 0 in sequential computation | Use `1` |
| Using subtraction or division as an arbitrary accumulator | Not associative; result depends on grouping | Design an associative combining operation or use an appropriate sequential algorithm |
| Using `reduce(Integer.MIN_VALUE, Integer::max)` and treating it as real data | Does not distinguish an empty Stream from the boundary element | Use `max()` returning `Optional` if emptiness must be reflected |
| Using an accumulator with side effects on an external variable | Incorrect computation count, unsafe in parallel | Return results via the accumulator and `reduce`'s return value |
| Mutating an `ArrayList` as the identity of `reduce` | Risk of sharing/mutating state across parallel branches | Use `collect` or `flatMap(...).toList()` |
| Trying to compute `long` directly from `Stream<Order>` with two-parameter `reduce` | Does not match type `T` of the overload | Use `mapToLong` before `reduce` or the appropriate three-parameter overload |
| Using `reduce(0, Integer::sum)` for a sum that can exceed `int` | Silent integer overflow | Widen beforehand with `asLongStream` or use `BigInteger` |
| Calling `reduce` again on the same Stream | Stream has already been consumed | Create a new Stream from the source |
| Assuming `reduce` automatically closes a file-backed Stream | I/O resource leak | Use `try-with-resources` for closeable sources |

## 14. Practice exercises

### Exercise 1: Identity per operation

Given `List<Integer> values = List.of(2, 3, 5)`, write `reduce` to compute the sum, product, and maximum value. Explain why the three operations require three different identities. Then test with an empty list and note the results.

### Exercise 2: Fix a reduction that breaks in parallel

The following snippet is intended to “add a processing fee of 50”:

```java
long amount = java.util.stream.LongStream.rangeClosed(1, 100)
    .parallel()
    .reduce(50L, Long::sum);
```

Why is `50L` not an identity? Rewrite it so the result is the sum of values `1` through `100` **plus `50` exactly once**, regardless of parallelism.

### Exercise 3: Choose overload and handle empty input

Given a possibly empty `List<Integer>`, find the smallest number and distinguish “no data” from a valid minimum equal to `Integer.MAX_VALUE`. Why is `reduce(Integer.MAX_VALUE, Integer::min)` not enough? Use `reduce(Integer::min)` and handle `Optional<Integer>`.

### Exercise 4: Review associativity

Classify the following accumulators by associativity and suitable identity:

```java
Integer::sum
(a, b) -> a * b
(a, b) -> a - b
String::concat
Integer::max
```

In your answer, distinguish associativity from commutativity, and explain why order-preserving string concatenation can still be combined in groups.

### Exercise 5: Total revenue across numeric ranges

Given `List<Order>` with `amountVnd` of type `long` and `paid` of type `boolean`, use `filter`, `mapToLong`, and `reduce(0L, Long::sum)` to compute paid revenue. Test data exceeding `Long.MAX_VALUE`; then rewrite using `BigInteger.ZERO` and `BigInteger::add`. Why must `BigInteger` be applied **before** summing?

### Exercise 6: When should collect be used?

Given a list of text segments, you need to join them with `", "` or gather them into a mutable `List<String>`. Compare `reduce` with `Collectors.joining(", ")` and `Collectors.toCollection(ArrayList::new)`. Explain why using a mutable container as the identity of `reduce` is dangerous.

### Exercise 7: Empty source and business interpretation

A group has no transactions. You need to distinguish “transaction total equals 0” from “no transactions to sum”. Design an appropriate output using `Optional` or a structure holding `count` and `sum`; do not assume that a `0` result from `reduce(0, Long::sum)` sufficiently describes the business state.

## 15. Knowledge self-check

- What data types does `reduce(identity, accumulator)` take and what does it return?
- What condition must hold for a value to be a valid identity?
- Why is subtraction not a suitable accumulator for parallel reduce?
- Does “associative” mean the same thing as “commutative”?
- Why does an empty Stream return the identity in the two-parameter `reduce` variant?
- What is the difference of `reduce(accumulator)` returning `Optional`?
- Why should an initial fee/surcharge not be put into `identity`?
- Why should `collect` be used to create a mutable list?
- Why does `reduce(0, Integer::sum)` still risk integer overflow?
- When should you use `sum()`, `reduce`, or `Collectors.joining()`?

**Key takeaway:** With `reduce(identity, accumulator)`, **the identity must be a neutral element** and **the accumulator must be an associative combining operation that does not depend on external state**. Those two conditions ensure the reduction has valid semantics when the Stream is empty or split for parallel execution. Choose `sum()` for simple arithmetic sums, `reduce` for a single immutable aggregated value, and `collect` when building a result container.
