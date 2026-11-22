# Associativity of Operations and Why Subtraction Is Usually Unsuitable for reduce() in Java

## 1. Problem Statement: reduce Is Not Just a Shorthand for a Loop

`reduce()` is a **terminal operation** in the Java Stream API: it combines multiple elements into a single summary value, such as a sum, a product, a maximum value, or a concatenated string. The idea sounds like “iterating through elements and updating a result variable,” but the contract of `Stream.reduce` is stricter: the combining operation must be **associative** (*associativity*) so that Java can group the computations in different ways, especially in a parallel stream, and still produce the correct result.

Compare two familiar operations:

~~~text
Addition:    (10 + 3) + 2 = 10 + (3 + 2) = 15
Subtraction: (10 - 3) - 2 = 5
             10 - (3 - 2) = 9
~~~

Addition satisfies associativity on integers in the appropriate arithmetic sense. Subtraction **does not**: merely changing where the parentheses are placed changes the result from `5` to `9`.

That is why `(a, b) -> a - b` is usually **unsuitable** as the combining operation for `reduce()`. The code may **compile and sometimes produce the expected result in a sequential stream**, yet fail to satisfy the conditions required to reliably merge partial results when Java splits the work into chunks.

**Key takeaway:** To use `reduce()` correctly, check both the **combining operation** and the **identity value** (*identity*), not just the lambda's type and a few test inputs.

## 2. What Is Associativity?

A binary operation `⊕` is associative if for all valid values `a`, `b`, `c`:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

This means we can **change how elements are grouped** while preserving the order of the elements and without changing the result.

Examples:

~~~text
Addition:             (2 + 3) + 4 = 2 + (3 + 4) = 9
Multiplication:       (2 × 3) × 4 = 2 × (3 × 4) = 24
String concatenation: ("a" + "b") + "c" = "a" + ("b" + "c") = "abc"
Subtraction:          (10 - 3) - 2 = 5 ≠ 9 = 10 - (3 - 2)
Division:             (24 / 4) / 2 = 3 ≠ 12 = 24 / (4 / 2)
~~~

**Associativity is not the same as commutativity.**

- *Associative*: `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)` — allows changing **parentheses**.
- *Commutative*: `a ⊕ b = b ⊕ a` — allows changing **the order of two elements**.

For example, **string concatenation is associative but not commutative**: `"a" + "b"` differs from `"b" + "a"`. Therefore, you must not claim that `reduce()` always requires a commutative operation. With a stream source that has an **encounter order** and an associative reduction, Java can still preserve the logical element order when combining strings; if you intentionally make the operation unordered or depend on side effects, you must check the contract of each API.

### 2.1. Characteristics of Subtraction

Subtraction clearly demonstrates:

~~~text
a - (b - c) = a - b + c
(a - b) - c = a - b - c
~~~

The two expressions differ in the sign of `c`. Except for a few special cases, they cannot be treated as equivalent.

For example, with `a = 10`, `b = 3`, `c = 2`:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

A test suite that only uses `0` or special coincidental cases may miss the problem. To test associativity, always try at least **three elements** and two different groupings.

## 3. Two Common reduce Variants and Their Requirements

On `Stream<T>`, Java provides these overloads:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);

Optional<T> reduce(BinaryOperator<T> accumulator);
~~~

These are **abbreviated signatures from the Stream API**, not interface declarations meant to be run standalone.

### 3.1. `reduce(identity, accumulator)`

Example:

~~~java
int sum = List.of(1, 2, 3, 4).stream()
        .reduce(0, Integer::sum);
~~~

The result is `10`. `Integer::sum` describes adding two `Integer` values and is a compatible `BinaryOperator<Integer>`; `0` is the appropriate identity for addition.

Contract to remember:

1. **`accumulator` must be associative**: it must satisfy associativity.
2. **`identity` must be the identity element** of the operation: `accumulator(identity, x) = x` and, for a properly typed reduction, `accumulator(x, identity) = x`.
3. Lambdas used in stream reduction must satisfy **non-interfering** and **stateless** requirements (do not modify the source, and do not depend on external state that changes across invocation order).

The API may split the source into multiple chunks, reduce each chunk, and then combine the results. If `identity` and `accumulator` satisfy the contract, different groupings remain valid.

### 3.2. `reduce(accumulator)` Without Passing an Identity

~~~java
Optional<Integer> sum = List.of(1, 2, 3, 4).stream()
        .reduce(Integer::sum);
~~~

The result is `Optional.of(10)`. For an **empty** stream, this overload returns `Optional.empty()` because there is no initial element to use as the result.

For an empty stream, `reduce(0, Integer::sum)` directly returns `0`, whereas `reduce(Integer::sum)` returns an empty Optional. **Omitting `identity` does not eliminate the associativity requirement**. In the overload without an identity, `accumulator` must still be an associative operation.

### 3.3. Brief Comparison

| Property | `reduce(identity, accumulator)` | `reduce(accumulator)` |
|---|---|---|
| Arguments | Initial value and combining operation | Combining operation only |
| Return type | `T` | `Optional<T>` |
| Empty stream | Returns `identity` | Returns `Optional.empty()` |
| Operation requirements | Associative, valid identity | Associative |
| Typical usage | Summing starting from `0`, product from `1` | Finding min/max when no default value is desired |
| Fixes non-associativity of subtraction? | No | No |

**Do not be misled:** omitting `identity` can make the sequential result look like a traditional subtraction expression starting from the first element, but it does not turn subtraction into an associative operation.

## 4. Why an Identity of 0 Does Not Fix Subtraction

An **identity** `e` must hold on **both sides**:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

For addition, `0` satisfies:

~~~text
0 + x = x
x + 0 = x
~~~

For multiplication, `1` satisfies:

~~~text
1 × x = x
x × 1 = x
~~~

However, for subtraction:

~~~text
0 - 5 = -5    (not equal to 5)
5 - 0 = 5
~~~

`0` is only a **right identity** for subtraction, **not** a left identity. Therefore:

~~~java
int value = List.of(10, 3, 2).stream()
        .reduce(0, (a, b) -> a - b);
~~~

On a sequential pipeline like the snippet shown, the steps correspond to `((0 - 10) - 3) - 2`, producing `-15`. If the author only expected `(10 - 3) - 2 = 5`, then even setting `identity` to `0` already produces a different result than expected.

Even without passing an identity:

~~~java
int value = List.of(10, 3, 2).stream()
        .reduce((a, b) -> a - b)
        .orElseThrow();
~~~

A sequential pipeline executes like subtraction from the first element and may return `5`, but under the **reduce contract**, the accumulator is still not associative. When split into chunks, combining intermediate results can yield a different answer.

## 5. Complete Java 17 Example: Addition Is Stable, Subtraction Changes When Regrouped

Save as **`AssociativityDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class AssociativityDemo {
    public static void main(String[] args) {
        int leftSubtract = (10 - 3) - 2;
        int rightSubtract = 10 - (3 - 2);

        int leftAdd = (10 + 3) + 2;
        int rightAdd = 10 + (3 + 2);

        List<Integer> values = List.of(10, 3, 2);
        int sum = values.stream().reduce(0, Integer::sum);
        int subtractWithIdentity = values.stream()
                .reduce(0, (a, b) -> a - b);
        int subtractWithoutIdentity = values.stream()
                .reduce((a, b) -> a - b)
                .orElseThrow();
        int parallelAddition = IntStream.rangeClosed(1, 10)
                .parallel()
                .reduce(0, Integer::sum);

        System.out.println("subtractLeft=" + leftSubtract);
        System.out.println("subtractRight=" + rightSubtract);
        System.out.println("addLeft=" + leftAdd);
        System.out.println("addRight=" + rightAdd);
        System.out.println("sum=" + sum);
        System.out.println("subtractIdentity=" + subtractWithIdentity);
        System.out.println("subtractNoIdentity=" + subtractWithoutIdentity);
        System.out.println("parallelAddition=" + parallelAddition);
    }
}
~~~

Run commands (JDK 17+):

~~~bash
javac AssociativityDemo.java
java AssociativityDemo
~~~

Expected stdout:

~~~text
subtractLeft=5
subtractRight=9
addLeft=15
addRight=15
sum=15
subtractIdentity=-15
subtractNoIdentity=5
parallelAddition=55
~~~

**Analysis:**

- The first two lines demonstrate that subtraction is **not associative**: changing the parentheses changes the result.
- Addition gives `15` under both groupings because within the demonstrated value range, addition obeys associativity.
- `reduce(0, Integer::sum)` uses a valid identity and associative addition, so it produces `15`.
- `reduce(0, (a,b) -> a-b)` is an **anti-pattern for general-purpose reductions**; the sequential result `-15` is not the difference `10-3-2`.
- `reduce((a,b)->a-b)` produces `5` in the demonstrated sequential pipeline, but **still violates the associativity requirement** of a reduction.
- `IntStream.rangeClosed(1,10).parallel().reduce(0,Integer::sum)` returns `55` because `int` addition with identity `0` satisfies the reduction contract; it does not depend on thread execution order.

This program **intentionally** runs the subtractions on sequential streams to produce verifiable output; it does not imply that using subtraction with `reduce()` is a sound design in all cases.

## 6. How Can Parallel reduce Regroup Operations?

The core idea of parallel reduction is that elements can be split into **sub-chunks**. Each chunk produces an intermediate result, and then the intermediate results are combined. With an associative operation and a valid identity, regrouping does not change the logical result.

Consider four values `1, 2, 3, 4` and identity `0`.

**One sequential evaluation:**

~~~text
(((0 - 1) - 2) - 3) - 4 = -10
~~~

**Splitting into two chunks:**

~~~text
Left group:  (0 - 1) - 2 = -3
Right group: (0 - 3) - 4 = -7
Combine:     -3 - (-7) = 4
~~~

The results `-10` and `4` differ. This is a **valid work-splitting grouping model** but **invalid in business semantics** when left-to-right subtraction is expected. Because Java does not guarantee a specific grouping order for an accumulator that violates the contract, you should not claim that `parallel().reduce(0,(a,b)->a-b)` will always return `4` or always return `-10`. The result can depend on the source, splitting strategy, JDK, and execution.

With **addition**:

~~~text
Sequential: (((0 + 1) + 2) + 3) + 4 = 10
Grouped:    (0 + 1 + 2) + (0 + 3 + 4) = 10
~~~

Both groupings still produce `10`.

### 6.1. Java Example Verifying Another Subtraction Grouping

Save as **`RegroupingDemo.java`**:

~~~java
import java.util.List;

public class RegroupingDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 4);

        int sequential = values.stream()
                .reduce(0, (a, b) -> a - b);

        int leftChunk = List.of(1, 2).stream()
                .reduce(0, (a, b) -> a - b);
        int rightChunk = List.of(3, 4).stream()
                .reduce(0, (a, b) -> a - b);
        int regrouped = leftChunk - rightChunk;

        System.out.println("sequential=" + sequential);
        System.out.println("leftChunk=" + leftChunk);
        System.out.println("rightChunk=" + rightChunk);
        System.out.println("regrouped=" + regrouped);
        System.out.println("same=" + (sequential == regrouped));
        System.out.println("zeroMinusFive=" + (0 - 5));
        System.out.println("fiveMinusZero=" + (5 - 0));
    }
}
~~~

Compile and run:

~~~bash
javac RegroupingDemo.java
java RegroupingDemo
~~~

Stdout:

~~~text
sequential=-10
leftChunk=-3
rightChunk=-7
regrouped=4
same=false
zeroMinusFive=-5
fiveMinusZero=5
~~~

The program **does not rely on parallel scheduling or the JVM fork/join pool** to force a specific answer. It manually splits the data into two segments, performs the chosen subtraction, and combines them manually; as a result, every line of stdout is deterministic and verifiable.

**Conclusion:** For an operation where merely changing the grouping changes the result, we cannot treat it as a safe reduction under the Stream contract. It is not that the parallel stream “computes incorrectly”; it is the accumulator itself that fails to satisfy the constraints of `reduce()`.

## 7. Three-Parameter Overload: accumulator and combiner Must Coordinate Consistently

`Stream<T>` also has an overload for cases where the result type `U` **differs** from the element type `T`:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

For example, summing **string lengths** from a `Stream<String>` and returning an `Integer`:

~~~java
int totalLength = List.of("java", "fp", "stream")
        .parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
        );
~~~

The result is `12`. Here:

- `identity = 0`: the identity element of the **combiner**.
- `accumulator`: takes the current `Integer` sum and a `String` to update the total length.
- `combiner = Integer::sum`: merges two partial sums when the parallel stream splits the work.
- `combiner` is associative, `0` is a valid identity, and `accumulator` is consistent with `combiner`.

An important requirement of the three-parameter contract is **compatibility**:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

In the example: `u + (0 + length(t)) = u + length(t)`, so the condition is satisfied.

### 7.1. Mistake: Using Subtraction as the combiner

~~~java
// WRONG per the reduce contract, even though the syntax compiles:
int result = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        (left, right) -> left - right
);
~~~

`combiner` subtracts two chunk sums. Compared to the sequential version (which does not need to merge chunks), the result can differ; the identity `0` is also not a two-sided identity for subtraction. The right solution is `Integer::sum` if the goal is **summing counts**.

### 7.2. Do Not Use reduce as a Contract-Violating Replacement for a Mutable Collector

Avoid this pattern:

~~~java
// NOT RECOMMENDED: mutating StringBuilder via reduce.
StringBuilder all = words.parallelStream().reduce(
        new StringBuilder(),
        (builder, word) -> builder.append(word),
        (left, right) -> left.append(right)
);
~~~

Problem: a mutable identity can be shared and mutated across branches; the accumulator/combiner no longer expresses a safe reduction with an immutable identity. For string concatenation, use `Collectors.joining()`. For collecting into a list, use `toList()` or `collect(Collectors.toList())` when appropriate. **`collect` is designed for mutable accumulation**, whereas `reduce` should express combining values according to its contract.

## 8. Complete Java 17 Program: Keep Addition Inside, Subtract Afterward

This is the **semantically correct** design pattern when you want to compute “initial budget minus total expenses.”

Suppose the expenses are `12, 25, 8`, and the budget is `100`:

~~~text
Total expenses: 12 + 25 + 8 = 45
Remaining: 100 - 45 = 55
~~~

**Do not** reduce directly with subtraction `reduce(100,(a,b)->a-b)`. `100` is not an identity for subtraction, and the operation is not associative. Sum the expenses using addition, then perform **a single subtraction after the reduction**.

Save file **`SafeReductionDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class SafeReductionDemo {
    record Stats(long total, long count) {
        Stats combine(Stats other) {
            return new Stats(total + other.total, count + other.count);
        }
    }

    public static void main(String[] args) {
        List<String> words = List.of("java", "fp", "stream");

        Stats stats = words.parallelStream()
                .map(s -> new Stats(s.length(), 1))
                .reduce(new Stats(0, 0), Stats::combine);

        int letters = words.parallelStream().reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
        );

        int budget = 100;
        int remaining = budget - letters;
        double average = (double) stats.total() / stats.count();

        System.out.println("stats=" +
                stats.total() + "," + stats.count());
        System.out.println("average=" + average);
        System.out.println("letters=" + letters);
        System.out.println("remaining=" + remaining);
    }
}
~~~

Compile and run:

~~~bash
javac SafeReductionDemo.java
java SafeReductionDemo
~~~

Stdout:

~~~text
stats=12,3
average=4.0
letters=12
remaining=88
~~~

**Explanation:**

1. `Stats` is an immutable record holding the total length and element count. `combine` adds each corresponding field.
2. `new Stats(0, 0)` is a valid identity; the combining operation `Stats::combine` is associative via field-wise addition (within the demonstrated number range where no overflow occurs).
3. `words.parallelStream().map(...).reduce(...)` allows `Stats` objects to be grouped in many ways while still yielding `total=12` and `count=3`.
4. The three-argument overload sums lengths directly from `String` to `Integer`, with `Integer::sum` as the proper combiner.
5. `remaining = budget - letters` is **a single subtraction after the sum is computed**. This is where subtraction genuinely reflects the business formula.
6. `average` is calculated from the two reduced values. For empty data, `stats.count()` is `0`, so real-world applications must check the count before dividing. The example uses a three-element list, so `4.0` is valid.

Record and `Stream.toList()` are stable APIs/features in Java 17. This code pattern does not create shared mutable state across parallel branches.

## 9. What If the Business Logic Truly Requires Sequential Subtraction in Order?

Some problems require the exact calculation:

~~~text
Start with 100
Subtract 10, 20, 5 in order
Result: 65
~~~

If **the order of updates is part of the requirement**, an explicit loop makes the intent clear:

~~~java
int balance = 100;
for (int charge : new int[] {10, 20, 5}) {
    balance -= charge;
}
System.out.println(balance); // 65
~~~

This is an **illustrative snippet** inside a method, without its own `main`. This style is explicit: `balance` is updated sequentially exactly three times. If the requirement is simply “budget minus total charges,” you can compute `100 - IntStream.of(10,20,5).sum()`; in that case you reduce with **addition** and subtract once at the end.

On an ordered stream executed sequentially, `reduce((a,b)->a-b)` is often observed to behave like a left fold. **However**, because subtraction does not satisfy the associative accumulator contract, it should not be considered a valid *reduction* for parallel optimization or as a foundation for code that needs long-term guarantees. An explicit loop or remodeling the problem with addition is easier to reason about and test.

### 9.1. Do Not Confuse Subtraction with Adding Negative Numbers

The calculation:

~~~text
100 - 10 - 20 - 5 = 100 + (-10) + (-20) + (-5) = 65
~~~

When the data represents “amounts to be deducted,” you can convert each amount into a **signed value** and sum them:

~~~java
int balance = 100 + java.util.stream.IntStream.of(10, 20, 5)
        .map(charge -> -charge)
        .sum();
~~~

This form uses **`sum`** on signed numbers rather than using **subtraction** as the combining operation. However, note that `-Integer.MIN_VALUE` is still `Integer.MIN_VALUE` due to `int` overflow; in financial problems with large numeric ranges, guard against overflow and consider `long` or `BigDecimal` as appropriate.

## 10. Associativity Is Not Always Obvious in Java

### 10.1. Integers and Overflow

Java's `int` addition is associative under **32-bit modular arithmetic**: different groupings do not change the bit-pattern of the final sum in pure `int` addition, but the result can still be **semantically wrong** when the sum exceeds the `int` range.

Example:

~~~java
int unexpected = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1
).sum();
// Result overflows to Integer.MIN_VALUE.
~~~

This is an illustrative snippet; if overflow detection is needed, consider `Math.addExact` in addition. However, **`Math.addExact` may throw an exception at different grouping points** if an intermediate sum exceeds the representable range, even if the final mathematical sum would fit in range; when designing a parallel reduction, you must specify how overflow is handled. If sums can be very large, switch to `long` or `BigInteger` and validate the value range.

### 10.2. Floating-Point Numbers Are Not Strictly Associative

Even `double` addition **is not strictly associative** due to IEEE 754 rounding:

~~~text
(a + b) + c may differ from a + (b + c)
~~~

A common example: `a=1e16`, `b=-1e16`, `c=1`:

~~~java
double left = (1e16 + -1e16) + 1.0;   // 1.0
double right = 1e16 + (-1e16 + 1.0); // 0.0
~~~

Because `-1e16 + 1.0` rounds back to `-1e16`, the final results differ. Therefore, a parallel reduction on `double` can alter the low-order bits of the result depending on grouping order. If an application requires strictly reproducible results or monetary precision, choose an appropriate numerical method and data type. For decimal currency amounts, `BigDecimal` or the smallest integer unit with clear bounds is usually preferred.

### 10.3. String Concatenation Is Associative but Not Commutative

~~~java
String joined = List.of("a", "b", "c").parallelStream()
        .reduce("", String::concat);
~~~

The logical result on an ordered stream is `"abc"`. Since `("a"+"b")+"c" = "a"+("b"+"c")`, regrouping concatenation segments does not change the final string as long as **element order is preserved**. But `"ab" != "ba"`, so concatenation is not commutative.

On large datasets, concatenating strings one by one with `String::concat` can incur high allocation overhead; `Collectors.joining()` is usually a more suitable API for joining many strings. **Algebraic correctness does not automatically guarantee good performance.**

### 10.4. Max/min and Identity

`Integer::max` or `Integer::min` are associative operations. However, the identity must be chosen carefully:

~~~java
int maximum = List.of(-10, -5, -7).stream()
        .reduce(Integer.MIN_VALUE, Integer::max); // -5
~~~

Choosing `0` as the identity in a problem with all negative numbers would make the maximum wrong: `max(0,-10,-5,-7)=0` even though `0` does not appear. When there is no sensible identity for the data domain, use the `reduce(BinaryOperator)` overload returning `Optional<T>` or Stream's built-in `max()`/`min()`.

## 11. Good Pattern: Avoid Mutating a Mutable Object Inside reduce

A subtle bug is using `reduce` to accumulate into **the same mutable object**:

~~~java
// Example NOT recommended for use in a parallel Stream:
List<Integer> result = numbers.parallelStream()
        .reduce(
                new ArrayList<>(),
                (list, n) -> {
                    list.add(n);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Aside from type inference/generics issues when written in real contexts, this code can **violate the reduction contract** because the mutable identity can be modified and shared across tasks, causing duplicate elements or race conditions. It is only a cautionary example, not recommended to copy and run.

If the goal is to collect elements into a collection, use:

~~~java
List<Integer> result = numbers.stream().toList();
~~~

Or when a mutable `ArrayList` is needed afterward:

~~~java
List<Integer> result = numbers.stream()
        .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
~~~

These snippets require `numbers` to be declared and appropriate imports. `collect` has the right semantics for mutable accumulation and can coordinate intermediate containers according to the collector contract. `reduce` is better suited for combining **values** or immutable accumulators.

## 12. Checklist for Designing a Parallelizable Reduction

Before writing `reduce`, ask these questions:

1. **What output value is needed?** Sum, product, max/min, a statistics object, or a sequential difference?
2. **What is the binary operation?** Addition, multiplication, max, string concatenation, or a domain function?
3. **Is it associative?** Test `(a ⊕ b) ⊕ c` and `a ⊕ (b ⊕ c)` with three arbitrary values and boundary data.
4. **Is the identity truly neutral on both sides?** `0` for addition, `1` for multiplication; `0` is **not** a two-sided identity for subtraction.
5. **If using the three-argument overload, are accumulator and combiner compatible?** Check the rule `combiner(u, accumulator(identity, t)) == accumulator(u, t)`.
6. **Are you mutating an object used as the identity?** If so, consider `collect` or an immutable accumulator.
7. **Does it depend on call order, call count, side effects, or external state?** General reductions must not depend on those.
8. **Is an empty stream possible?** Choose a valid identity or handle `Optional.empty()`.
9. **Are there overflow, floating-point precision, or value-domain issues?** Choose an appropriate type and arithmetic strategy.
10. **Does encounter order need to be preserved?** For non-commutative operations like string concatenation, source ordering must be well understood.
11. **Is the dataset large or running with `parallel()`?** Ensure the combining operation is correct before considering performance.
12. **Is there a built-in specialized operation?** `IntStream.sum()`, `max()`, `min()`, and `Collectors.joining()` are often clearer than a hand-written accumulator.

In particular, **do not treat the fact that Java compiles a lambda as proof that the operation is suitable for reduction**. The compiler only checks the types of `BinaryOperator`/`BiFunction`; it does not prove associativity or a valid identity.

## 13. Common Mistakes and How to Fix Them

| Mistake | Why is it a problem? | What to use instead? |
|---|---|---|
| `reduce(0, (a,b)->a-b)` to compute “sequential difference” | Wrong identity and subtraction is not associative | Explicit ordered loop or `initial - sum(charges)` |
| `parallel().reduce((a,b)->a-b)` | Regrouping changes the result | Reformulate using addition or reduce sequentially with a different algorithm |
| Assuming omitting identity fixes subtraction | `reduce(BinaryOperator)` still requires associativity | Do not use subtraction as a general accumulator |
| Choosing `0` for `reduce(max)` on all-negative numbers | `0` corrupts the maximum result | `Integer.MIN_VALUE` or `max()` returning Optional |
| Testing only a two-element example | Fails to detect parenthesization changes | Use three elements and two different groupings |
| Using `StringBuilder.append` in `reduce` with a mutable identity | Can break parallel merging | `Collectors.joining()` |
| Using `double` addition and expecting bit-for-bit invariant results | Floating point has rounding | Controlled summation techniques / more precise data types |
| Mixing an addition accumulator with a subtraction combiner | Incompatible in the three-argument overload | Use an addition combiner |
| Thinking associative means commutative | String concatenation is associative but not commutative | Distinguish changing parentheses from changing order |
| Expecting `parallel()` to always be faster | Splitting, coordination, and combining have overhead | Measure performance; prioritize correctness |
| Modifying mutable external state inside accumulator | Violates non-interference/statelessness | Combine immutable values or use `collect` |
| Failing to handle empty streams | Result may be `identity` or `Optional.empty()` | Check business requirements for empty data |

## 14. Self-Check Questions

**Question 1.** What is the exact definition of associativity? How does it differ from commutativity?

**Question 2.** Given three numbers `10,3,2`, compute `(10-3)-2` and `10-(3-2)`. What does this tell us about subtraction?

**Question 3.** Why is `0` an identity for addition but not a two-sided identity for subtraction?

**Question 4.** What result does `Stream.of(10,3,2).reduce(0, (a,b)->a-b)` produce in the demonstrated sequential pipeline? Should it be used in a parallel reduction?

**Question 5.** Does `Stream.of(10,3,2).reduce((a,b)->a-b)` satisfy the associativity contract once `identity` is omitted?

**Question 6.** Why can string concatenation be used with `reduce` even though `"ab" != "ba"`?

**Question 7.** In the overload `reduce(identity, accumulator, combiner)`, why must `combiner` be compatible with `accumulator`?

**Question 8.** To compute `budget - total expenses`, which operation should you reduce with?

**Question 9.** What do `reduce(0,Integer::sum)` and `reduce(Integer::sum)` return on an empty stream?

**Question 10.** Why can `double` addition differ in the low-order bits of the result when the grouping changes?

**Answers:**

1. Associativity is `(a⊕b)⊕c = a⊕(b⊕c)`; commutativity is `a⊕b = b⊕a`.
2. `5` and `9`, respectively; subtraction is not associative.
3. `0+x=x` and `x+0=x`, but `0-x=-x` differs from `x` when `x≠0`.
4. `-15` in the sequential example; do not use it as an associative accumulator for parallel reduction.
5. No; the associativity requirement still applies.
6. String concatenation preserves element order while allowing regrouping; it is associative, not commutative.
7. So that merging separately computed parts produces the same logical result as sequential accumulation.
8. Sum the expenses using `sum/reduce(Integer::sum)` and then subtract the total from the budget.
9. `0` and `Optional.empty()`, respectively.
10. Because of IEEE 754 rounding after each addition; changing parentheses can change intermediate results and the final result.

## 15. Official References

- [Java SE 17 API — Stream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `reduce` contract, associativity requirement, identity, and the overload with a combiner.
- [Java SE 17 API — IntStream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): primitive `int` reduction variants.
- [Java SE 17 API — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html): functional type taking two parameters of the same type as the result.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): collectors such as `joining` and `toCollection` when mutable accumulation is needed.
- [Java SE 17 API — Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): reduction properties, callback independence, and notes on parallel streams.

**Remember:** An operation passed to `reduce` must be **associative**; overloads with an identity also require a **valid identity**. Subtraction `a-b` is usually **not associative** and `0` is not a two-sided identity, so `reduce` calls using subtraction are unsuitable for arbitrary regrouping or parallel execution. If the problem is **an initial value minus the sum of items**, **sum the items first and subtract once afterward**; if the problem requires step-by-step sequential updates, use a loop that explicitly expresses the order.
