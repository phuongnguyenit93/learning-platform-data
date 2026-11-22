# Why Does a Wrong Identity Value Make Parallel `reduce()` Results Wrong?

In Java Streams, `reduce()` combines multiple elements into a single result: computing a sum, product, min/max, concatenating strings, or building an aggregated value. With a **parallel** reduction, Java can split the source into multiple parts, reduce each part, and then combine those intermediate results. Therefore, the **identity value** (*identity*) must be the neutral element of the combining operation, not just a "convenient starting value".

A `reduce` operation can appear to work correctly when run sequentially yet produce a different result when run in parallel if the wrong identity is chosen. This is not a random JVM bug: the code has violated the contract required for Java to be allowed to split and combine groups of elements.

## 1. What Does `reduce()` Do?

The two-argument form on `Stream<T>` has the signature:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

This is an abbreviated API signature, not a standalone Java program.

- `identity` is the identity value for the operation used to combine elements.
- `accumulator` takes two values of type `T` and returns one value of type `T`.
- The result is `T`; for an empty stream, the result is `identity` itself.
- The operator must be **associative**, non-interfering with the source, and independent of any mutable external state.

Example of summing integers:

```java
int total = List.of(1, 2, 3, 4)
        .stream()
        .reduce(0, Integer::sum);
// total == 10
```

This is an illustrative snippet inside a method and requires `import java.util.List;`. The identity value for addition is `0` because `0 + x == x` and `x + 0 == x`.

Common identities:

| Combining operation | Correct identity | Why |
| --- | --- | --- |
| Integer or floating-point addition | `0` or `0.0` respectively | `0 + x = x = x + 0` |
| Number multiplication | `1` | `1 * x = x = x * 1` |
| `String` concatenation with `concat` | `""` | An empty string adds no characters |
| `Math.min` on `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| `Math.max` on `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Boolean AND | `true` | `true && x = x` |
| Boolean OR | `false` | `false || x = x` |

For `min/max`, if you need to distinguish an **empty source** from a real result whose value equals the type's extreme bound, prefer `stream.min(...)`, `IntStream.min()`, `IntStream.max()`, or the `reduce` overload without an identity that returns `Optional`.

## 2. The Identity Value Is a Mathematical Law, Not an "Initial Value"

Given an operation `⊕` and an identity element `e`, two conditions must hold for every value `x` in the domain being processed:

```text
e ⊕ x = x       (left identity)
x ⊕ e = x       (right identity)
```

At the same time, the operation must be associative:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

A **wrong identity** means a group of elements being reduced can have an unwanted value added, multiplied, or appended to it. In a sequential stream, the identity typically appears only once at the start of the computation. In a parallel stream, each subgroup can start from the same identity. When the group results are combined, the wrong value is **repeated multiple times**.

Example of choosing `10` as the identity for addition:

```java
int wrongSequential = List.of(1, 2, 3, 4)
        .stream()
        .reduce(10, Integer::sum);
// wrongSequential == 20, not the sum 10.
```

Here, even the sequential run is wrong if the business requirement asks for the sum `10`. However, some programs genuinely **want to add a fixed fee of 10**, so `20` can look right in the sequential case. The trap lies in confusing "add 10 exactly once" with "the identity of addition".

If we split into groups `[1, 2]` and `[3, 4]` and reduce each group with `10`:

```text
Left group:  reduce(10, +) on [1, 2] = 10 + 1 + 2 = 13
Right group: reduce(10, +) on [3, 4] = 10 + 3 + 4 = 17
Combine:     13 + 17 = 30

Without splitting into groups:
             10 + 1 + 2 + 3 + 4 = 20

True sum:    1 + 2 + 3 + 4 = 10
Sum + fee:   10 + 10 = 20
```

**A parallel stream does not promise to always split into exactly two groups.** The number of groups and how they are combined are implementation details, so do not rely on a specific number from a broken `reduce` when running `.parallel()`. The verifiable point here is: if the identity is not neutral, two valid ways of grouping can produce **different results**, causing the reduction to violate the parallel reduction contract.

## 3. Complete Runnable Java 17+ Example with Deterministic Results

Create the file `ReduceIdentityDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ReduceIdentityDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 4);

        int correctSequential = values.stream()
                .reduce(0, Integer::sum);
        int correctParallel = values.parallelStream()
                .reduce(0, Integer::sum);

        int wrongSequential = values.stream()
                .reduce(10, Integer::sum);

        // Simulate two valid branches, producing a deterministic wrong result.
        int left = List.of(1, 2).stream()
                .reduce(10, Integer::sum);
        int right = List.of(3, 4).stream()
                .reduce(10, Integer::sum);
        int combined = Integer.sum(left, right);

        int sumPlusOneFee = 10 + values.parallelStream()
                .reduce(0, Integer::sum);

        int product = IntStream.of(2, 3, 4)
                .parallel()
                .reduce(1, (a, b) -> a * b);

        String letters = List.of("A", "B", "C")
                .parallelStream()
                .reduce("", String::concat);

        System.out.println("correctSequential = " + correctSequential);
        System.out.println("correctParallel = " + correctParallel);
        System.out.println("wrongSequential = " + wrongSequential);
        System.out.println("left = " + left);
        System.out.println("right = " + right);
        System.out.println("combined = " + combined);
        System.out.println("sumPlusOneFee = " + sumPlusOneFee);
        System.out.println("product = " + product);
        System.out.println("letters = " + letters);
    }
}
```

Run with JDK 17 or later:

```bash
javac ReduceIdentityDemo.java
java ReduceIdentityDemo
```

Exact stdout:

```text
correctSequential = 10
correctParallel = 10
wrongSequential = 20
left = 13
right = 17
combined = 30
sumPlusOneFee = 20
product = 24
letters = ABC
```

The key point of the example: the **correct** reduction uses identity `0`, so the sum is `10` whether executed sequentially or in parallel. If you need to add an amount of `10` exactly once, **add it after the reduction**: `10 + stream.reduce(0, Integer::sum)`.

The program intentionally **does not print `values.parallelStream().reduce(10, Integer::sum)`** with a fixed expected output. That computation violates the identity condition; its result can depend on how the JVM splits and combines tasks. The two explicit groups in the program are only used to demonstrate the cause, so the values `13`, `17`, and `30` are completely deterministic.

## 4. Why Does a Parallel Reduction Need an Identity for Each Branch?

Conceptual model of a parallel reduction:

```text
                     [1, 2, 3, 4]
                          |
                   Split into groups
                      /       \
                   [1,2]     [3,4]
                    |           |
              reduce(e, op)  reduce(e, op)
                    |           |
                  left        right
                      \       /
                   combine(op)
                          |
                        result
```

This is only an illustrative diagram. Java may split into many groups, use different splitting thresholds, and combine in various ways. If `e` is a true identity, the result is unaffected by inserting `e` into any branch. If `e` is not neutral, each branch can introduce additional bias.

With standard addition:

```text
left  = 0 + 1 + 2 = 3
right = 0 + 3 + 4 = 7
result = 3 + 7 = 10
```

With `e = 10`, each branch carries an extra `10`, causing the result to depend on the number of branches. Therefore, a valid `reduce` operation must produce a result consistent with splitting and combining data, rather than relying on how a single test run happens to execute.

## 5. Choosing the Right Identity Is Not Enough: The Accumulator Must Also Be Associative

The next condition is that the operation must be **associative**. Integer addition (within range) has no semantic issue when regrouping, whereas subtraction is not associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Using `reduce(0, (a, b) -> a - b)` to "accumulate subtractions" is not a valid reduction for a parallel stream: `0 - x != x`, so the identity is wrong too, and subtraction is also not associative. A sequential stream may return one result depending on traversal order, whereas a parallel stream is permitted to change the grouping.

If you want to compute `initialAmount - sum(deductions)`, separate the expression:

```java
int initialAmount = 100;
int remaining = initialAmount
        - List.of(10, 20, 5).parallelStream()
                .reduce(0, Integer::sum);
// remaining == 65
```

This illustrative snippet requires `import java.util.List;`. The `reduce` operation only performs addition with identity `0`; subtraction is applied **once** after the sum is obtained.

### Special Note on `double`

Floating-point addition on computers may not be strictly associative due to IEEE 754 rounding:

```text
(a + b) + c  may differ from  a + (b + c)
```

For example, with values of vastly different magnitudes, different combination schedules can produce slightly different `double` results. This is a **numerical precision** issue, distinct from the bug of choosing identity `10` instead of `0`. When business logic requires decimal precision, consider `BigDecimal` and rounding rules; when testing parallel computations on `double`, do not assume bit-by-bit equality if the algorithm does not guarantee summation order.

## 6. The Contract `reduce(identity, accumulator)` Must Satisfy

For the `T reduce(T identity, BinaryOperator<T> accumulator)` overload, a correct design must satisfy:

1. **Identity:** for all `t`, `accumulator(identity, t)` must yield `t`; for valid combinations across partitions, `identity` must also be neutral when combined on both sides.
2. **Associativity:** `accumulator(accumulator(a, b), c)` equals `accumulator(a, accumulator(b, c))` according to the intended semantics.
3. **Stateless:** the lambda must not rely on mutable external state; calls with the same arguments produce the same logical result.
4. **Non-interfering:** do not modify the data source being consumed by the stream.
5. **Parallel-safe:** if external mutable state were used, you would have to deal with race conditions; the best design is a reducer that returns a new value or uses a contract-compliant primitive reduction/collector.

**Distinguish identity from seed:** in a hand-written sequential loop, you can initialize an accumulator with any value and update it step by step, such as `sum = 10`. However, `reduce` in parallel mode interprets the `identity` parameter according to the identity-element contract. You cannot pass an arbitrary "seed" and expect Java to apply it only once.

## 7. The Three-Argument `reduce`: An Additional Compatibility Requirement

General form:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
)
```

This is an abbreviated API signature, not a standalone program.

This overload is used when source elements have type `T`, while the aggregated result has type `U`. For example, a stream contains `Sale` records, but the result is a `long`.

```java
record Sale(String sku, int units) {}

List<Sale> sales = List.of(
        new Sale("A", 2),
        new Sale("B", 3),
        new Sale("C", 4)
);

long totalUnits = sales.parallelStream().reduce(
        0L,
        (sum, sale) -> sum + sale.units(),
        Long::sum
);
// totalUnits == 9
```

This illustrative snippet belongs inside a class and a method, and requires `import java.util.List;`. `Sale` is a Java 16+ record (valid in Java 17).

In the three-argument form:

- `identity` must be the identity element of the **combiner**.
- `combiner` must be associative.
- `accumulator` and `combiner` must be **compatible** according to the rule:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

for all valid `u` and `t` (where `u` is an intermediate result of type `U`, and `t` is a source element of type `T`).

In the example above: `combiner` is `long` addition; `identity=0L`; `accumulator(sum, sale)=sum+sale.units()`. Thus:

```text
combiner(u, accumulator(0L, sale)) = u + (0 + units)
                                    = u + units
                                    = accumulator(u, sale)
```

If you pass `100L` as the identity to add a fixed fee, each group could add `100` before `Long::sum` combines the groups. The right way is:

```java
long withFixedFee = 100L + sales.parallelStream()
        .reduce(0L, (sum, sale) -> sum + sale.units(), Long::sum);
// 109
```

The fee is applied **once after the reduction**, regardless of how many groups the stream splits into.

## 8. Why Can a Wrong Identity "Look Right" Sequentially?

Let's distinguish two requirements:

**Requirement A — sum the elements:** `[1,2,3,4]` must return `10`.

```java
int total = values.stream().reduce(0, Integer::sum);
```

**Requirement B — sum the elements and add a fixed fee of 10:** must return `20`.

```java
int withFee = 10 + values.stream().reduce(0, Integer::sum);
```

If you write `values.stream().reduce(10, Integer::sum)`, the result **coincidentally matches** Requirement B when executed as a single sequential chain starting from identity `10`. With a parallel stream, however, applying the identity across multiple branches causes the fee to appear multiple times.

This bug can be hard to spot when the test suite only checks sequential streams, or when the input is too small for parallel execution to actually split the work. **There is no guarantee that a `reduce` with a wrong identity will always expose the bug on every parallel run.** You must verify the identity/associativity contract, not just observe a single run.

## 9. `reduce` Without an Identity: When Is It Useful?

`Stream<T>` also has the form:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

Because there is no identity, this API returns **`Optional<T>`**: an empty stream yields `Optional.empty()`, while a non-empty stream returns the reduction result if the operator is valid.

```java
Optional<Integer> maximum = List.of(4, 1, 9)
        .parallelStream()
        .reduce(Integer::max);
// Optional[9]

Optional<Integer> empty = List.<Integer>of()
        .stream()
        .reduce(Integer::max);
// Optional.empty()
```

This is an illustrative snippet inside a method and requires `import java.util.List;` and `java.util.Optional;`.

Omitting the identity makes it explicit that there is no max/min of an empty set with the same semantics as a real value. Still, **the operator must remain associative** for a reliable parallel reduction. Dropping the identity does not fix a broken accumulator like subtraction.

For primitive streams, Java provides built-in `IntStream.sum()`, `LongStream.sum()`, `IntStream.min()`, `IntStream.max()`, `DoubleStream.average()`, and corresponding APIs. These APIs are usually more readable than writing a custom `reduce` for common statistical operations.

## 10. Do Not Use a Shared Mutable Identity in `reduce`

Another common mistake occurs when turning the identity into a mutable object:

```java
// Bad design example, DO NOT use in a parallel stream:
StringBuilder sb = new StringBuilder();
StringBuilder result = List.of("A", "B", "C")
        .parallelStream()
        .reduce(
                sb,
                (builder, part) -> builder.append(part),
                (left, right) -> left.append(right)
        );
```

This illustrative snippet requires `import java.util.List;`. `StringBuilder` is mutable and can be shared during the reduction. The accumulator/combiner above mutates the passed-in object directly. Reusing the same identity object, especially across parallel branches, breaks the neutrality and independence assumptions; it can cause data races, duplicated data, or erratic results.

If you need to join strings:

```java
String combined = List.of("A", "B", "C")
        .parallelStream()
        .collect(java.util.stream.Collectors.joining());
// "ABC"
```

Or use `reduce("", String::concat)` when the data is small and straightforward. When accumulating mutable state is needed, `collect` is usually the right choice because it has a **supplier that creates a new container** for each branch, an accumulator that updates that container, and a combiner that merges containers. Whichever approach you choose, you must obey the API contract and avoid unsafe shared mutable state.

## 11. How to Test Identity and Associativity

When writing your own reducer, you can check the laws using representative examples from your data domain. For addition:

```java
int e = 0;
int a = 3, b = 5, c = 7;

boolean leftIdentity = Integer.sum(e, a) == a;
boolean rightIdentity = Integer.sum(a, e) == a;
boolean associative =
        Integer.sum(Integer.sum(a, b), c)
        == Integer.sum(a, Integer.sum(b, c));

System.out.println(leftIdentity);
System.out.println(rightIdentity);
System.out.println(associative);
```

This is an illustrative snippet placed inside a method. All three output lines are `true`.

However, testing a few inputs **is not a mathematical proof for all values**, especially with complex types, overflow, `double`, comparators, or custom aggregators. When designing a new reducer, explicitly write down the operation, the identity, and a proof or argument for why they hold over the actual data domain.

A practical test checklist:

1. Return the right result for an **empty stream**, a single-element stream, and multi-element streams.
2. Compare sequential against parallel on sufficiently large datasets and varied distribution patterns.
3. Manually split the list into multiple groups; reduce each group, combine them, and compare against reducing the whole list.
4. Test cases with negative numbers, zero, duplicate data, boundary values, or special values if the application needs them.
5. If results differ, trace the cause to identity, associativity, stateful side effects, or numerical precision; do not "fix" it by forcing the stream to sequential while ignoring the contract.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| `reduce(10, Integer::sum)` to add a fee of 10 once | Identity `10` is not neutral; each branch can add another 10 | `10 + stream.reduce(0, Integer::sum)` |
| `reduce(0, (a,b) -> a*b)` for multiplication | `0` is not the identity of multiplication; turns the product into 0 | `reduce(1, (a,b) -> a*b)` |
| `reduce(0, (a,b) -> a-b)` on a parallel stream | Subtraction is not associative; identity is also wrong on the left | Sum the amounts to subtract, then subtract once outside |
| Using `new StringBuilder()` as identity and calling `append` on it | Mutable identity can be shared across branches; violates contract | Use `Collectors.joining()` or `collect` properly |
| Mimicking sequential loop `total = 100` with identity `100` in parallel `reduce` | Confuses seed with identity | `100 + parallelReduceWithIdentityZero` |
| Comparing sequential vs. parallel only once | One splitting schedule can hide the bug | Verify identity and associativity laws with examples/proofs |
| Assuming output must always be bit-identical to sequential `double` addition | Floating-point rounding can change when regrouping | Choose appropriate precision and summation strategy |

## Self-Check

**Question 1.** What is the identity of `Integer::sum`? Why?

**Answer:** `0`, because adding `0` on either side does not change the value.

**Question 2.** What does `List.of(1,2,3).stream().reduce(5, Integer::sum)` return? Can it be used as a parallel `reduce` if the intent is "add a fee of 5 once"?

**Answer:** Sequentially it returns `11`. It should not be used as a parallel reduction with that intent because identity `5` is not neutral; write `5 + stream.reduce(0, Integer::sum)`.

**Question 3.** Given two groups `[1,2]` and `[3,4]`, what do you get by reducing each group with `reduce(10, Integer::sum)` and adding the results?

**Answer:** `13 + 17 = 30`, different from `20` of a sequential reduction with seed `10`.

**Question 4.** Can `reduce(0, (a,b) -> a-b)` be used on a parallel stream for cumulative subtraction?

**Answer:** No: subtraction is not associative and `0 - x != x`. Express the operation using reductions with valid contracts.

**Question 5.** In the three-argument form, besides the combiner's identity, what other law is required?

**Answer:** `combiner(u, accumulator(identity, t)) == accumulator(u,t)`; plus associativity of the combiner and stateless/non-interfering functions.

**Question 6.** Why does a broken `reduce` sometimes still look "right" when run in parallel on a small dataset?

**Answer:** The JVM may not actually split into multiple groups, or the execution schedule happens not to expose the bug. Observed results do not replace verifying the contract.

## Key Takeaways

- **Identity is the neutral element** of the operation, not an arbitrary initial value.
- **Parallel `reduce` can apply the identity to multiple groups**, so a wrong identity causes groups to carry extra bias.
- **Accumulator/combiner must be associative** and independent of mutable shared state.
- When you need to add an amount **exactly once**, reduce with the proper identity and add that amount **after the reduction**.
- For three-argument `reduce`, preserve both the **combiner's identity** and **compatibility** between accumulator and combiner.
- Verify results across multiple groupings; do not rely on a single parallel execution schedule.
