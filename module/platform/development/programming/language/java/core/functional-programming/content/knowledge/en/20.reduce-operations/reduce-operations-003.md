# Identity Element and `reduce()` with an Initial Value in Java Stream

## 1. Why Does Reduction Need an Identity Element?

In the Java Stream API, `reduce` (*reduction*) is a terminal operation that combines multiple elements into **a single aggregate value**, such as a sum, product, concatenated string, maximum value, or an incrementally computed result.

~~~java
List<Integer> numbers = List.of(2, 3, 4);

int total = numbers.stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 9
~~~

The two components of the statement above are:

- **`0`**: the initial value, which must also be the **identity element** for addition.
- **`Integer::sum`**: the function that combines two `Integer` values into one `Integer`, which here is addition.

For a sequential stream, we can read it according to the diagram:

~~~text
identity = 0
0 + 2  = 2
2 + 3  = 5
5 + 4  = 9
result = 9
~~~

Key point: `0` is not chosen simply because we "want to start from 0". It is valid because **adding 0 on either the left or the right does not change the value**. In multiplication, the identity element is `1`; in string concatenation, it is the empty string `""`. Using the wrong identity element can cause incorrect results, especially when running in parallel.

This lesson focuses on the two `reduce` overloads that take an **initial value (identity)** and the conditions that must be satisfied to use them correctly in Java 17+.

## 2. Signatures of the Two `reduce` Forms to Understand

### 2.1. Two-Parameter Form — `reduce(identity, accumulator)`

On `Stream<T>`:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

`BinaryOperator<T>` is a functional interface with the behavior:

~~~java
T apply(T left, T right);
~~~

It takes two values of the same type `T` and produces a result of the same type. Therefore, with `Stream<Integer>`:

~~~java
int sum = Stream.of(1, 2, 3)
        .reduce(0, (a, b) -> a + b);

int product = Stream.of(1, 2, 3)
        .reduce(1, (a, b) -> a * b);
~~~

The results are `6` and `6`, respectively. Although the example numbers happen to be equal, **the identity elements are different**: addition uses 0, multiplication uses 1.

- `identity` has type `T`, which is the element type of the stream.
- `accumulator` combines the current aggregated state with the next element, returning a new `T`.
- This form returns **`T`** directly, not `Optional<T>`.
- When the stream is empty, the result is **the identity itself**.

### 2.2. Three-Parameter Form — `reduce(identity, accumulator, combiner)`

On `Stream<T>`:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

This form allows **the result type `U` to differ from the element type `T`**:

- `identity` has type `U`.
- `accumulator` takes the accumulated value `U` and a source element `T`, and returns `U`.
- `combiner` combines two accumulated `U` results, typically needed to merge partitioned results in a parallel stream.

Example: the source consists of strings, and the result is the total length as an integer.

~~~java
int totalLength = Stream.of("Java", "API", "Stream")
        .reduce(
                0,
                (lengthSoFar, word) -> lengthSoFar + word.length(),
                Integer::sum);

System.out.println(totalLength); // 13
~~~

`Stream<String>` has been reduced to `Integer`. For this problem, `mapToInt(String::length).sum()` is usually shorter and clearer; however, the three-parameter example illustrates the mechanism where `accumulator` differs from `combiner`.

## 3. Mathematical Definition: What Is an Identity Element?

Given a binary operation `⊕` on type `T`. A value `e` is a **two-sided identity element** if for all `x` in the valid data domain:

\[
e \oplus x = x \quad \text{and} \quad x \oplus e = x.
\]

This condition is especially important when the algorithm splits the source into multiple parts and combines them back. For `reduce(identity, accumulator)`, the contract requires the accumulator to be **associative** (*associativity*) and the identity to be the identity element of that operation.

Associativity:

\[
(a \oplus b) \oplus c = a \oplus (b \oplus c).
\]

Associativity is not the same as commutativity: string concatenation is associative but not commutative because `"A" + "B"` differs from `"B" + "A"`. Therefore, **the combining operation is not required to be commutative** to use `reduce`, but it must obey the associativity contract and not interfere with external state.

Table of common cases:

| Goal | Combining Operation | Correct Identity | Why Is It Neutral? |
| --- | --- | --- | --- |
| Sum of integers | `a + b` | `0` | `0 + x = x + 0 = x` |
| Product of integers | `a * b` | `1` | `1 * x = x * 1 = x` |
| String concatenation | `String::concat` | `""` | Concatenating an empty string on either side does not change the content |
| Boolean AND | `a && b` | `true` | `true && x = x && true = x` |
| Boolean OR | `a \|\| b` | `false` | `false \|\| x = x \|\| false = x` |
| Max of `int` | `Integer::max` | `Integer.MIN_VALUE` | Every `int` value is greater than or equal to `MIN_VALUE` |
| Min of `int` | `Integer::min` | `Integer.MAX_VALUE` | Every `int` value is less than or equal to `MAX_VALUE` |

The max/min identities in the table rely on the **full `int` value range**, where `MIN_VALUE` and `MAX_VALUE` actually belong to the domain. If you do not want to treat a sentinel as a valid result for an empty stream, using the `reduce(BinaryOperator)` overload that returns `Optional` or the corresponding `min`/`max` terminal operations expresses "no result" more clearly.

For subtraction, `0 - x = -x` whereas `x - 0 = x`, so 0 **is not a two-sided identity element**. Subtraction is also not associative: `(10 - 3) - 2 = 5`, whereas `10 - (3 - 2) = 9`. Therefore, do not use `reduce(0, (a,b) -> a-b)` as a valid parallel reduction just because the result looks predictable sequentially.

## 4. Behavior on an Empty Stream

An important benefit of overloads with an identity is that **there is always a return value of type T/U**, even when there are no elements:

~~~java
int emptySum = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

int emptyProduct = Stream.<Integer>empty()
        .reduce(1, (a, b) -> a * b);

String emptyConcat = Stream.<String>empty()
        .reduce("", String::concat);

System.out.println(emptySum);                // 0
System.out.println(emptyProduct);            // 1
System.out.println(emptyConcat.isEmpty());   // true
~~~

The result of an empty stream is not an "implicit null", not an exception, and not a value generated by the accumulator. It is **the provided identity**.

If you want to clearly distinguish "no data" from "an aggregate value of 0", the overload without an identity is more appropriate:

~~~java
Optional<Integer> noResult = Stream.<Integer>empty()
        .reduce(Integer::sum);

System.out.println(noResult.isEmpty()); // true
~~~

The sum of an empty set may be defined as 0 by convention in mathematics and many statistical domains; however, if the system needs to report "no records yet", returning an empty Optional may be the better choice.

## 5. Distinguishing the Three `reduce` Overloads

Java provides three common forms on reference streams:

| Syntax | Return Type | When Source Is Empty | When to Use |
| --- | --- | --- | --- |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | `Optional.empty()` | No suitable identity exists or missing data needs to be represented |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Identity | Source and result have the same type, and the operation has an identity |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Identity | A different result type is needed or separate accumulation/combining logic is required |

Example of a sum without an identity:

~~~java
Optional<Integer> sumMaybe = Stream.of(2, 3, 4)
        .reduce(Integer::sum);

System.out.println(sumMaybe.orElseThrow()); // 9
~~~

Example with the same source but with an identity:

~~~java
int sumAlways = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum);

System.out.println(sumAlways); // 9
~~~

Both results have the same numerical meaning for a non-empty source, but **the type signature and empty-stream behavior differ**.

`IntStream`, `LongStream`, and `DoubleStream` also have corresponding `reduce(identity, operator)` overloads, as well as identity-free overloads returning `OptionalInt`, `OptionalLong`, and `OptionalDouble`. However, primitive streams have dedicated terminal operations such as `sum()`, `min()`, and `max()`, which are usually clearer and may be better optimized.

## 6. The Initial Value Is Not an "Arbitrary Add-On"

This is the most common mistake:

~~~java
int result = Stream.of(1, 2, 3)
        .reduce(10, Integer::sum);

System.out.println(result); // 16 when running sequentially
~~~

If we only consider sequential execution, the progression is `10 + 1 + 2 + 3 = 16`. However, `10` **is not the identity of addition**. The `reduce` contract requires `0` as the identity, so the code above **is not a valid reduction to rely on when switching to parallel**.

With a parallel stream, data partitions can be reduced separately, each initialized with the identity, and then merged using the accumulator/combiner. Consequently, the result using "identity = 10" **can depend on how the stream is split** and is not guaranteed to be `16`:

~~~java
// Do not use this approach to express "10 plus the sum of elements":
int wrongInParallel = Stream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

If the business logic truly needs "adding a fixed amount of 10 once to the sum", write:

~~~java
int correct = 10 + Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(correct); // 16
~~~

**Rule:** only pass a true identity element for the combining operation into the `identity` parameter. Any fixed add-on, processing fee, offset, or other business factor should be applied **after the reduction** or expressed using a different combining design that preserves algebraic laws.

Similarly, for multiplication:

~~~java
int product = Stream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b); // 24
~~~

Do not use `0` as the multiplicative identity: `0 * x = 0`, so the reduction will miss the intended goal. `0` is the *annihilator* of multiplication, **not** its identity element.

## 7. Parallel Reduction: Associativity Matters More Than Execution Order

In a sequential pipeline, we often picture the combining operation running from left to right. However, the Stream API is designed for parallel streams as well, where intermediate results can be computed on different branches and then combined.

With integer addition and identity 0:

~~~java
int total = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(total); // 5050
~~~

`Integer::sum` is associative under Java integer semantics, and 0 is the identity. Regardless of how the source is partitioned, the result of summing the numbers from 1 to 100 remains 5050 (with no overflow in this example).

Mental model:

~~~text
Source: [1,2,3,4]

Branch A: reduce(0, +) on [1,2] -> 3
Branch B: reduce(0, +) on [3,4] -> 7
Combine results: 3 + 7 -> 10

Equivalent to sequential addition:
(((0 + 1) + 2) + 3) + 4 -> 10
~~~

The diagram only illustrates one valid way of splitting, **not a fixed scheduling plan** of the JVM.

### 7.1. Associativity Does Not Mean Commutativity

~~~java
String combined = Stream.of("A", "B", "C")
        .reduce("", String::concat);

System.out.println(combined); // ABC
~~~

String concatenation is associative and `""` is the identity, but the order of strings matters. For a source with an encounter order, an ordered reduction can preserve the logical combining order to produce the corresponding result. Do not assume parallel execution will arbitrarily turn `ABC` into `CBA` when the operation and source carry the appropriate ordering contract.

### 7.2. Floating-Point Operations May Not Be Strictly Associative

Adding `double` floating-point numbers is not strictly associative at the bit level due to IEEE 754 rounding rules:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

// (a + b) + c can be 1.0.
// a + (b + c) can be 0.0 under double arithmetic.
~~~

Therefore, floating-point reductions can yield slightly different results depending on the combining order, especially in parallel. For high-precision problems, you must choose an appropriate algorithm/data type and error tolerance, rather than assuming `double` addition is perfectly associative mathematically.

## 8. Three-Parameter Form: Identity Belongs to the Result Type U

Scenario: compute the total `Integer` length from a `Stream<String>`.

~~~java
List<String> words = List.of("Java", "API", "Stream");

int totalLength = words.stream()
        .reduce(
                0,
                (lengthSoFar, word) -> lengthSoFar + word.length(),
                Integer::sum);

System.out.println(totalLength); // 13
~~~

Reading by signature:

~~~text
T = String
U = Integer

identity:     Integer = 0
accumulator:  (Integer, String) -> Integer
combiner:     (Integer, Integer) -> Integer
result:       Integer
~~~

When running in parallel, each partition can produce an `Integer`, and then `combiner` merges those parts. Because the identity is 0 for adding `Integer` results, it does not alter the result of any branch.

### 8.1. Accumulator/Combiner Compatibility Condition

The three-parameter form does not just require an associative combiner and a neutral identity. Java also requires the **accumulator to be compatible with the combiner**:

\[
\text{combiner}(u,\ \text{accumulator}(identity,t))
=
\text{accumulator}(u,t).
\]

The equality must hold for valid values `u` (accumulated result) and `t` (source element). For the length calculation:

~~~text
combiner(u, accumulator(0, word))
= u + (0 + word.length())
= u + word.length()
= accumulator(u, word)
~~~

Thanks to this, accumulating per branch and then combining is equivalent to accumulating directly. If the accumulator produces different values depending on how many times or where it is called, such as prepending a delimiter at the start of each branch, it can violate this rule.

### 8.2. Example: Counting Elements Matching a Condition

~~~java
long countLongWords = Stream.of("a", "java", "stream", "io")
        .reduce(
                0L,
                (count, word) -> count + (word.length() >= 4 ? 1L : 0L),
                Long::sum);

System.out.println(countLongWords); // 2
~~~

This is a valid reduction: the accumulator produces a count from a `String`, the combiner sums the counts, and the identity is `0L`. Even so, if you only need to count, `filter(...).count()` usually expresses the intent more simply:

~~~java
long count = Stream.of("a", "java", "stream", "io")
        .filter(word -> word.length() >= 4)
        .count();
~~~

A powerful API does not mean it has to be used everywhere. Choose a specialized terminal operation if it expresses the intent more clearly.

## 9. When Should You Not Use `reduce` for Mutable Accumulation?

The contract of `reduce` requires the accumulation function to be non-interfering with the source data, stateless, and suitable for splitting/combining. In particular, **never use a mutable object as the identity and mutate it directly** as a shared container:

~~~java
// WRONG example of reduction design; do not use in practice:
// StringBuilder joined = words.parallelStream().reduce(
//         new StringBuilder(),
//         (builder, word) -> builder.append(word),
//         (left, right) -> left.append(right));
// Mutable identity is shared and the accumulator mutates the object directly.
~~~

With a parallel stream, multiple branches can reference the same mutable identity and perform unsafe mutations. Even sequentially, that design does not follow the immutable value-combining semantics that `reduce` requires.

If you need to join multiple strings, use a specialized collector:

~~~java
String joined = Stream.of("A", "B", "C")
        .collect(Collectors.joining(","));

System.out.println(joined); // A,B,C
~~~

If you need to build a `List`:

~~~java
List<String> collected = Stream.of("A", "B", "C")
        .collect(Collectors.toList());
~~~

`collect` is a **mutable reduction** operation with a supplier that creates containers, an accumulator that updates a container, and a combiner that merges containers. It has its own contract to support mutable containers safely, rather than forcing mutation into `reduce`. For numeric streams, `sum`, `summaryStatistics`, or statistical collectors can be clear choices.

### 9.1. Must the Identity Be Immutable or Just Unmodified?

The core point is not that Java forbids any mutable object from appearing in a reduction operator, but that the reduction design **must not mutate a shared identity or external state in a way that breaks associativity, non-interference, and parallel compatibility**. In practice, prefer accumulators that produce new results, and use `collect` if you need to mutate a mutable container.

If you use `String` or `Integer` as the identity, these immutable types help reduce the risk of shared state. For custom types, define the operation and identity according to a clear algebraic model.

## 10. Nulls, Overflow, and Cases Without a Natural Identity

### 10.1. Null Is Not a Default Identity

~~~java
// Do not arbitrarily treat null as an "empty start":
Stream<String> words = Stream.of("A", "B");
// String joined = words.reduce(null, String::concat);
// May cause NullPointerException when the accumulator applies String::concat.
~~~

If you want to concatenate strings, use `""` as the identity. If you want to represent the absence of elements, consider `Optional`, not null. In reference streams, some steps may contain null values, so the accumulator must still be designed to handle them safely with an appropriate result contract.

### 10.2. Integer Overflow

A correct identity element does not automatically prevent overflow:

~~~java
int sum = IntStream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Integer::sum);

System.out.println(sum); // -2147483648 (int overflow)
~~~

Java `int` addition uses 32-bit arithmetic and wraps around on overflow; if data can exceed the range, consider converting to `long` before adding or using `Math.addExact` to detect overflow according to your error policy. Note that `Math.addExact` can throw `ArithmeticException` depending on the data and execution order.

### 10.3. No Natural Identity for Every Problem

For "pick the best element" problems, if the data domain has no true global minimum or maximum value, do not invent a sentinel:

~~~java
Optional<Integer> max = Stream.of(-7, -3, -9)
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // -3
~~~

Writing `reduce(0, Integer::max)` will incorrectly return `0` when all numbers are negative because 0 is not the identity of `max` over the full integer domain. You can use `Integer.MIN_VALUE` for `int`, but when the stream is empty that sentinel becomes the result; if you need to distinguish "no data" from "the value MIN_VALUE", `Optional` expresses it more accurately.

### 10.4. Errors in the Accumulator Do Not Become Empty

If the accumulator throws an exception (such as a parse or validation error), `reduce` does not substitute the identity and continue. The terminal operation normally terminates with the thrown error. Therefore, the identity is not an **error-handling or fallback** mechanism; it is the neutral element of the combining operator.

## 11. Complete Java 17+ Program with Deterministic Stdout

Create the file **`ReduceIdentityDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.Collectors;

public class ReduceIdentityDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        int sum = numbers.stream()
                .reduce(0, Integer::sum);
        int product = numbers.stream()
                .reduce(1, (a, b) -> a * b);
        System.out.println("sum=" + sum);
        System.out.println("product=" + product);

        int emptySum = Stream.<Integer>empty()
                .reduce(0, Integer::sum);
        int emptyProduct = Stream.<Integer>empty()
                .reduce(1, (a, b) -> a * b);
        System.out.println("emptySum=" + emptySum);
        System.out.println("emptyProduct=" + emptyProduct);

        Optional<Integer> emptyWithoutIdentity =
                Stream.<Integer>empty().reduce(Integer::sum);
        System.out.println("emptyOptional="
                + emptyWithoutIdentity.isEmpty());

        int withOffsetSequential = numbers.stream()
                .reduce(10, Integer::sum);
        int correctOffsetParallel = 10 + numbers.parallelStream()
                .reduce(0, Integer::sum);
        System.out.println("offsetSequential=" + withOffsetSequential);
        System.out.println("offsetParallelCorrect=" + correctOffsetParallel);

        String joined = Stream.of("A", "B", "C")
                .reduce("", String::concat);
        System.out.println("joined=" + joined);

        int totalLength = Stream.of("Java", "API", "Stream")
                .reduce(
                        0,
                        (current, word) -> current + word.length(),
                        Integer::sum);
        System.out.println("totalLength=" + totalLength);

        long longWords = Stream.of("a", "java", "stream", "io")
                .parallel()
                .reduce(
                        0L,
                        (count, word) ->
                                count + (word.length() >= 4 ? 1L : 0L),
                        Long::sum);
        System.out.println("longWords=" + longWords);

        int parallelSum = IntStream.rangeClosed(1, 100)
                .parallel()
                .reduce(0, Integer::sum);
        System.out.println("parallelSum=" + parallelSum);

        OptionalInt max = IntStream.of(-7, -3, -9)
                .reduce(Integer::max);
        System.out.println("max=" + max.orElseThrow());

        String collected = Stream.of("A", "B", "C")
                .collect(Collectors.joining(","));
        System.out.println("collected=" + collected);
    }
}
~~~

Compile and run:

~~~bash
javac ReduceIdentityDemo.java
java ReduceIdentityDemo
~~~

**Stdout:**

~~~text
sum=10
product=24
emptySum=0
emptyProduct=1
emptyOptional=true
offsetSequential=20
offsetParallelCorrect=20
joined=ABC
totalLength=13
longWords=2
parallelSum=5050
max=-3
collected=A,B,C
~~~

Explanation:

1. `sum=10` because `0+1+2+3+4=10`; `product=24` because `1×1×2×3×4=24`.
2. The two empty streams return the identities `0` and `1`, respectively, with no accumulator calls needed on source elements.
3. The overload without an identity on an empty stream returns `Optional.empty()`.
4. `offsetSequential=20` only illustrates the observed result when running **sequentially** with "initial value 10"; that is not a valid identity for addition. `offsetParallelCorrect=20` computes the sum with identity 0, then adds the offset 10 once outside.
5. `joined=ABC` because the empty string is the identity for string concatenation.
6. `totalLength=13` because `"Java"` has length 4, `"API"` has length 3, and `"Stream"` has length 6.
7. `longWords=2` counts `"java"` and `"stream"`, using a compatible accumulator/combiner on a parallel stream.
8. `parallelSum=5050` with addition having the proper identity and associativity.
9. `max=-3` uses the overload returning `OptionalInt`, without needing to choose a sentinel.
10. `collected=A,B,C` illustrates the appropriate collector when building a delimited string.

The examples are designed so that stdout does not depend on the scheduling order of the parallel stream. They only aggregate using functions that satisfy associativity and identity requirements, without printing individual callbacks from parallel workers.

## 12. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Using `reduce(1, Integer::sum)` for addition | `1` is not the additive identity | Use `0` |
| Using `reduce(0, (a,b)->a*b)` for multiplication | `0` annihilates every number | Use `1` |
| Using `reduce(10, sum)` to add a fee of 10 once | Parallel execution may apply the identity to multiple branches | `10 + stream.reduce(0, sum)` |
| Using subtraction in `reduce` and then running in parallel | Subtraction is not associative, and 0 is not a two-sided identity | Choose an associative combining operation and the right identity |
| Using `reduce(0, Integer::max)` for negative numbers | Identity 0 is not neutral for max on negative numbers | Use `max()`/`reduce(Integer::max)` returning Optional |
| Thinking `reduce(identity, op)` returns Optional | Overloads with an identity return `T` directly | Check the exact signature |
| Thinking an empty stream returns null | Forms with an identity return the identity | Design the identity explicitly |
| Using a mutable identity and calling append/add | Mutation and shared state break the reduce contract | Use `collect` |
| Using `reduce` to join strings with commas by adding a comma to every element | Can produce wrong results when splitting and merging branches | Use `Collectors.joining(",")` |
| Using `double` addition and expecting bitwise-identical results across all groupings | Doubles have rounding errors and are not strictly associative | Choose an appropriate algorithm/precision |
| Thinking the identity is an error handler or fallback value | Identity only neutralizes the combining operation | Handle errors separately, use Optional when needed |
| Mutating the source collection inside the accumulator | Violates non-interference and risks parallel bugs | Keep the combining operation free of side effects |

## 13. Exercises and Solutions

**Question 1.** What is the identity of `Integer::sum`? If the stream is empty, what does `Stream.<Integer>empty().reduce(0, Integer::sum)` return?

**Solution:** The identity is `0`. An empty stream returns `0`.

**Question 2.** Why is `1` the identity for multiplication while `0` is not?

**Solution:** `1*x = x*1 = x`, whereas `0*x=0`. `0` is the annihilator for multiplication.

**Question 3.** What does `Stream.of(2,3,4).reduce(10, Integer::sum)` produce sequentially? Should that expression be used in parallel if you want to add 10 once?

**Solution:** Sequentially it produces `19`. You should not use it: `10` is not the identity of addition, and parallel execution may initialize multiple branches with 10. Use `10 + Stream.of(2,3,4).parallel().reduce(0,Integer::sum)`.

**Question 4.** To compute the total length of strings using the three-parameter `reduce` form, what are the types `T` and `U`, respectively?

**Solution:** `T=String`, `U=Integer`. The identity is `0`, the accumulator is `(sum,s)->sum+s.length()`, and the combiner is `Integer::sum`.

**Question 5.** Why must the three-parameter accumulator be compatible with the combiner?

**Solution:** So that reducing each branch and then merging is equivalent to accumulating directly. Rule: `combiner(u, accumulator(identity,t)) == accumulator(u,t)` in terms of value equivalence for the operation.

**Question 6.** Given the source `[-7,-3,-9]`, what does `reduce(0,Integer::max)` return and what is wrong with it?

**Solution:** The result is `0`, whereas the actual max is `-3`. Identity 0 is not neutral for max on negative numbers. Use `stream.max()` or the `reduce(Integer::max)` overload.

**Question 7.** On an empty source, how do `reduce(BinaryOperator)` and `reduce(identity, BinaryOperator)` differ?

**Solution:** The form without an identity returns an empty Optional. The form with an identity returns the provided identity value itself.

**Question 8.** To join strings with a delimiter while supporting parallel streams, should you use `reduce(new StringBuilder(), StringBuilder::append, ...)`?

**Solution:** No. Mutating a mutable identity violates the safe reduction contract. Use `Collectors.joining(delimiter)`, or `collect` with an appropriate collector.

## 14. Key Takeaways

**An identity element is not just a "starting value"**. It must satisfy the neutrality law with the combining operation: `e ⊕ x = x ⊕ e = x`. Together with **associativity** of the accumulator, that condition allows `reduce(identity, accumulator)` to return the right result when the stream is empty and when the pipeline splits and merges for parallel execution.

- `reduce(T identity, BinaryOperator<T>)` returns `T` directly, and an empty stream returns the identity.
- `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` allows the source `T` and result `U` to have different types, while requiring the accumulator to be compatible with the combiner.
- Do not put a business add-on into the identity if it is not neutral for the operation; apply that add-on **after the reduction**.
- Do not use a mutable object as the identity and mutate it in the accumulator; use `collect` for mutable reduction.
- When no suitable identity exists or you need to distinguish the absence of data, use the `reduce(BinaryOperator)` overload returning `Optional` or a specialized terminal operation.
- Numeric operations, especially floating-point ones, require considering overflow, rounding error, and associativity.

Understanding the algebraic laws of the identity helps you write reductions that are not only "correct sequentially", but also contractually sound, clearer, and safer when switching to parallel streams.
