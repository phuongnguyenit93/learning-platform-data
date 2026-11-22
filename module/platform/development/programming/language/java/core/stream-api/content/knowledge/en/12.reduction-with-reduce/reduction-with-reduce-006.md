# Compatibility Between Accumulator and Combiner

In the Java Stream API, `reduce` turns multiple elements into a single result value. With the three-parameter form, a program can **accumulate each element** using `accumulator`, and then **merge partial results** using `combiner`. These two functions must work together properly: otherwise, a sequential pipeline may produce a plausible result while `parallelStream()` returns the wrong value.

This lesson belongs to the chapter **Reduction with reduce** of the **JAVA_STREAM_API** module. It serves as the bridge between declarative data processing (`map`, `filter`, `reduce`, `collect`) and pipeline laziness, data splitting via `Spliterator`, parallel processing, as well as constraints on state and performance. The focus is the **compatibility contract between `accumulator` and `combiner`**, rather than merely knowing the syntax to call `reduce`.

## 1. Why does reduce need a combiner?

Imagine needing to compute the total length of strings:

```java
List<String> words = Arrays.asList("Java", "Stream", "API");
```

If processed sequentially, we can add them one by one:

```text
0 -- + length("Java") = 4 --> 4
4 -- + length("Stream") = 6 --> 10
10 -- + length("API") = 3 --> 13
```

When processed in parallel, Java can split the source into independent parts:

```text
              ["Java", "Stream", "API"]
                     /           \
             ["Java", "Stream"]   ["API"]
                   |                 |
             accumulator          accumulator
                   |                 |
                  10                 3
                     \             /
                         combiner
                            |
                           13
```

The diagram only illustrates one possible data split. Java does not promise a fixed number of branches, branch sizes, or thread execution order. However, **no matter how it splits**, the logical result must remain consistent with the reduction contract.

`accumulator` processes each element **within a partial result**. `combiner` merges **two partial results**. Therefore, the same mathematical rule must be preserved whether everything is computed in one branch or split across multiple branches.

## 2. Three-parameter reduce syntax

The method on `Stream<T>` has the signature:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Meaning of each parameter:

| Component | Role | Inputs and output |
| --- | --- | --- |
| `identity` | Neutral value to start a partial result | Type `U` |
| `accumulator` | Takes an existing result and a source element, producing a new result | `(U, T) -> U` |
| `combiner` | Takes two partial results, producing a merged result | `(U, U) -> U` |

The source element type `T` **can differ** from the result type `U`. For example, the source is `String` while the result is `Integer`:

```java
int totalLength = words.stream().reduce(
    0,
    (subtotal, word) -> subtotal + word.length(),
    Integer::sum
);
// totalLength = 13
```

Here, `identity = 0`; `accumulator` converts each `String` into its length contribution and adds it to `Integer`; `combiner` adds two `Integer`s.

Do not confuse the two functions by their names: `accumulator` **does not take two Stream elements**, it takes **one partial result of type U** and **one element of type T**. `combiner` does not take source elements; it only takes **two result values of type U**.

## 3. Three requirements for a reduction to work properly

The `reduce(identity, accumulator, combiner)` contract requires the reducing functions to be **non-interfering** with the source and **stateless** (not dependent on external mutable state). Mathematically, pay special attention to the three relationships below.

### 3.1. Identity is a neutral element for the combiner

For any partial result `u`, the contract requires:

\[
\operatorname{combiner}(\operatorname{identity},u)=u
\]

For example, with addition:

```java
Integer identity = 0;
int u = 7;
int combined = Integer.sum(identity, u); // 7
```

`0` is the neutral value for addition. For multiplication, the neutral value is `1`; for string concatenation, it is `""`. In common combining operations, `identity` is neutral on **both sides**, allowing independent grouping without changing the result.

Passing a **non-neutral** initial value into `reduce` can cause it to be added multiple times when the source is split into multiple parts.

### 3.2. Combiner must be associative

For partial results `a`, `b`, `c`, we need:

\[
\operatorname{combiner}(\operatorname{combiner}(a,b),c)
=\operatorname{combiner}(a,\operatorname{combiner}(b,c))
\]

*Associative* **differs from *commutative***. String concatenation is associative:

```text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
```

But in general it is not commutative: `"A" + "B"` differs from `"B" + "A"`. With a source having an encounter order, a properly written `reduce` still preserves order when merging partial results. You must not arbitrarily use `unordered()` when order is part of the result's meaning.

Subtraction is not associative: `(10 - 5) - 2 = 3`, whereas `10 - (5 - 2) = 7`. Therefore, subtraction should not be used as a `combiner` for a parallel reduction intended as sequential subtraction.

### 3.3. Accumulator and combiner must be compatible

This is the central constraint of the lesson. For every partial result value `u` and source element `t`, the contract requires:

\[
\boxed{
\operatorname{combiner}
\big(u,\operatorname{accumulator}(\operatorname{identity},t)\big)
=\operatorname{accumulator}(u,t)
}
\]

Stated in words:

> **Directly accumulating element `t` into `u` must be equivalent to accumulating `t` from `identity` to produce a separate result, and then using `combiner` to merge that result into `u`.**

This condition guarantees the computation does not change meaning when Java **splits an element (or a group of elements) onto another branch** and merges it back. Checking only that `combiner` is associative is **not enough**.

For the total string length problem, set:

```text
identity                 = 0
accumulator(u, t)        = u + length(t)
combiner(left, right)    = left + right
```

Take `u = 4`, `t = "Stream"` (length 6):

```text
combiner(4, accumulator(0, "Stream"))
= combiner(4, 6)
= 10

accumulator(4, "Stream")
= 4 + 6
= 10
```

Both sides are equal; the rule also holds for all `u` and strings `t` within the value domain where addition is defined as intended by the problem.

## 4. Correct example: total string length in both modes

The complete program below uses Java 8 or later:

```java
import java.util.Arrays;
import java.util.List;

public class CompatibleReductionDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "Stream", "API");

        int sequential = words.stream().reduce(
            0,
            (sum, word) -> sum + word.length(),
            Integer::sum
        );

        int parallel = words.parallelStream().reduce(
            0,
            (sum, word) -> sum + word.length(),
            Integer::sum
        );

        System.out.println(sequential); // 13
        System.out.println(parallel);   // 13
    }
}
```

With this small dataset, `parallelStream()` may be slower due to splitting and merging overhead. The goal of the example is **correctness**, not demonstrating speedup. None of the lambdas mutate external state; the combining operation uses integer addition with identity `0` and is compatible with summing each string's length.

If only the total length is needed, the following expression is usually shorter and clearer:

```java
int totalLength = words.stream()
    .mapToInt(String::length)
    .sum(); // 13
```

Three-parameter `reduce` is especially worth learning when `T` and `U` differ or when the accumulation step differs from the merge step. It is not necessarily the best tool for every summation.

## 5. Subtle bug: an associative combiner that is not compatible

Suppose a developer wants to sum string lengths but chooses `Math.max` to merge partial results:

```java
List<String> words = Arrays.asList("Java", "Stream", "API");

int wrong = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Math::max                         // WRONG: merging with max, not addition
);
```

`Math.max` is associative and `0` is neutral with respect to `max` on the domain of **non-negative** lengths. However, it is **not compatible** with an accumulator using addition:

```text
u = 4, t = "Stream"

combiner(4, accumulator(0, "Stream"))
= max(4, 6)
= 6

accumulator(4, "Stream")
= 4 + 6
= 10
```

The two sides are unequal. With a single branch, the result might still be `13` because only the accumulator is needed. If the data is split into branches, the `max` combiner only keeps the largest partial result instead of adding them. **Do not predict a single fixed wrong result**: the degree and strategy of parallel splitting can vary by environment.

Fix it with the proper combining function:

```java
int correct = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
); // 13
```

Lesson learned: **associativity and identity do not replace compatibility**. All three conditions must be verified, especially when `accumulator` and `combiner` differ in parameter types and purpose.

## 6. Identity error: the same value gets added multiple times

Another mistake is using initial number `5` while the combining operation is addition:

```java
int wrongIdentity = words.parallelStream().reduce(
    5,
    (sum, word) -> sum + word.length(),
    Integer::sum
);
```

`5` is not neutral with respect to addition. If the source is processed in one branch, the accumulated result will be `5 + 13 = 18`. If split into two branches where each starts at `5`, merging can count `5` **twice**, yielding `23`. The exact partitioning is not guaranteed.

The identity condition was already broken:

```text
combiner(identity, u) = 5 + u != u
```

To add an offset of `5` per business requirements, keep the proper identity and add `5` **after `reduce` finishes**:

```java
int totalPlusFive = 5 + words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
); // 18
```

This makes the intent explicit: `5` is an addition at the end, not the identity used for every combining step.

## 7. Do not use three-parameter reduce to mutate a shared container

`reduce` is designed for **stateless, non-interfering reduction**. Using a mutable object as the identity and mutating it directly from accumulator/combiner easily violates the contract and causes race conditions in parallel execution.

**Wrong** example, solely to recognize the mistake:

```java
List<String> unsafe = words.parallelStream().reduce(
    new ArrayList<String>(),
    (list, word) -> {
        list.add(word);      // WRONG: mutating the partial result object
        return list;
    },
    (left, right) -> {
        left.addAll(right);  // WRONG: mutating inside reduce
        return left;
    }
);
```

The problem is not just that `ArrayList` lacks synchronization. Here `identity` is **a reference to a single mutable object**; operations on that object can affect multiple processing branches. Even if `ArrayList` were replaced with a synchronized structure, mutating objects inside `reduce` still fails to express a pure reduction contract and can produce duplicated or incorrect data.

### Use collect when the goal is mutable accumulation

`collect` provides a dedicated model for building mutable results using a supplier, accumulator, and combiner:

```java
ArrayList<String> safe = words.parallelStream().collect(
    ArrayList::new,
    ArrayList::add,
    ArrayList::addAll
);

System.out.println(safe); // [Java, Stream, API]
```

Roles of the three parameters of `collect`:

| Component of collect | Role |
| --- | --- |
| `supplier` | Creates a **new container** for each accumulation segment |
| `accumulator` | Adds an element to the container of the segment being processed |
| `combiner` | Merges data from another branch's container into the current container |

This is **mutable reduction** supported by the API. The combiner of this `collect` form returns `void`, whereas the combiner of three-parameter `reduce` returns a `U` value. For collecting a simple list, you can also write:

```java
List<String> safeList = words.parallelStream()
    .collect(Collectors.toList());
```

When grouping or custom collectors are needed, prefer `collect` and design according to the `Collector` contract. That is the natural next step in the `JAVA_STREAM_API` learning path.

## 8. Differences among the three reduce overloads

`reduce` has three common forms:

| Form | Meaning | When to use? |
| --- | --- | --- |
| `Optional<T> reduce(BinaryOperator<T> accumulator)` | No identity needed; result is empty when source is empty | Finding a combined value without a reasonable neutral element, e.g., maximum value |
| `T reduce(T identity, BinaryOperator<T> accumulator)` | Result type matches element type; operator also merges in parallel | Sums, products, combining elements of the same type |
| `U reduce(U identity, BiFunction<U,? super T,U> accumulator, BinaryOperator<U> combiner)` | Result type can differ from element type; separates accumulation and merging | Total string length, immutable result structures, custom transformations and reductions |

Examples:

```java
Optional<Integer> largest = Stream.of(7, 3, 9)
    .reduce(Integer::max); // Optional[9]

int sum = Stream.of(7, 3, 9)
    .reduce(0, Integer::sum); // 19

int lengthSum = Stream.of("Hi", "Java")
    .reduce(0, (length, text) -> length + text.length(), Integer::sum);
// 6
```

With an empty Stream:

```java
int zero = Stream.<Integer>empty()
    .reduce(0, Integer::sum); // 0

Optional<Integer> none = Stream.<Integer>empty()
    .reduce(Integer::sum); // Optional.empty()

int total = Stream.<String>empty()
    .reduce(0, (n, text) -> n + text.length(), Integer::sum); // 0
```

With no elements to accumulate, the two forms with an identity return the identity, whereas the form without an identity returns `Optional.empty()`.

## 9. When a non-commutative combiner is still valid

Not every reduction problem is numeric addition. Strings can be concatenated using operations that are **associative yet non-commutative**:

```java
String joined = Stream.of("A", "B", "C")
    .parallel()
    .reduce(
        "",
        (prefix, text) -> prefix + text,
        String::concat
    );

System.out.println(joined); // ABC
```

Here:

- Identity `""` is the neutral element for string concatenation.
- `String::concat` is associative on string values.
- `concat(u, concat("", t))` equals `concat(u, t)`, so it is compatible with the accumulator.
- The source `Stream.of("A", "B", "C")` has an encounter order; a valid reduction preserves that concatenation order even when split for parallel execution.

**Repeatedly concatenating strings with `+` can create many intermediate objects** and incur heavy cost. If the goal is practical string joining, `Collectors.joining()` is usually more appropriate:

```java
String joinedEfficiently = Stream.of("A", "B", "C")
    .parallel()
    .collect(Collectors.joining()); // "ABC"
```

Do not replace `String::concat` with an order-reversing combiner `(a, b) -> b + a`: it violates compatibility with an append-to-end accumulator, even if a sequential observation sometimes appears plausible.

## 10. Floating-point numbers, overflow, and result reproducibility

Associativity in the `reduce` contract is a requirement **according to the semantics of the operation**. With `double`, floating-point addition suffers rounding error; in machine arithmetic, `(a + b) + c` can differ from `a + (b + c)`:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Therefore, floating-point sums in sequential and parallel execution can differ in the trailing bits. For summing `double` values, `mapToDouble(...).sum()` is usually clearer and may use accuracy-enhancing techniques, though it does not promise exact decimal results or identical bits across all branch splits.

If the application requires exact decimals for currency, consider `BigDecimal` and explicit rounding rules. If integer arithmetic is needed without tolerating overflow, `Math.addExact` can be used to detect errors; for `int`/`long`, regular addition can overflow in machine representation. Choosing the right data type is part of correctness when reducing.

## 11. Checklist when designing a parallel reduce

| Question to verify | How to test or prove |
| --- | --- |
| Is `identity` genuinely neutral? | Check `combiner(identity, u) == u` across representative `u` values |
| Is `combiner` associative? | Compare results of `combine(combine(a,b),c)` and `combine(a,combine(b,c))` |
| Are `accumulator` and `combiner` compatible? | Verify `combine(u, accumulate(identity,t)) == accumulate(u,t)` |
| Do the functions mutate the source or shared state? | Remove mutations outside the pipeline; avoid reusing a mutable identity |
| Does the result depend on order? | Check encounter order; do not arbitrarily use `unordered()` |
| Is a mutable structure or an immutable value needed? | Mutable: prefer `collect`; reduced value: consider `reduce` |
| Is there a risk of overflow or floating-point error? | Choose an appropriate data type and validation criteria |
| Have multiple data splits been tested? | Compare logical results of `stream()` and `parallelStream()`, including empty and single-element sources |

When verifying results, do not run just once on a three-element list: the runtime may choose an execution plan where `combiner` is called rarely or not at all. First **prove the three relationships in the contract**, and then use tests with varied inputs to catch implementation bugs.

## 12. Self-check exercises

**Exercise 1 — Determine compatibility.** Given:

```java
int value = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::max
);
```

**Answer:** Violates the contract. For `u = 4`, `t = "Stream"`, `max(4, 6)` equals `6`, whereas `4 + 6` equals `10`. `max` is associative but incompatible with a length-summing accumulator.

**Exercise 2 — Find the right identity.** Fill in the identity and combiner to compute the product of positive integers:

```java
int product = Stream.of(2, 3, 4).parallel().reduce(
    1,
    (acc, n) -> acc * n,
    (left, right) -> left * right
); // 24
```

**Answer:** The identity is `1` and the combiner is multiplication. `1` is neutral for multiplication; multiplication is associative under non-overflowing integer arithmetic and compatible with the accumulator. For `int`, check for overflow if the value domain is large.

**Exercise 3 — Choose reduce or collect.** To place all strings from a Stream into an `ArrayList`, should you use `reduce` with identity `new ArrayList<>()` and `add`, or `collect`?

```java
ArrayList<String> result = words.parallelStream()
    .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

**Answer:** Use `collect`; the API provides separate containers for mutable accumulation and an appropriate merging mechanism. A mutable identity in `reduce` can cause multiple branches to share a single object.

**Exercise 4 — Is commutativity required?** Is `String::concat` a valid combiner for an append-to-end string accumulator on a Stream with an encounter order?

**Answer:** Yes, when the identity is `""` and the accumulator appends to the end. Concatenation is associative and compatible, even though it is not commutative. If the ordering requirement is dropped, the concatenated result may no longer match the original intent.

**Exercise 5 — Empty Stream.** What is the result of the following three-parameter reduction?

```java
int result = Stream.<String>empty().reduce(
    0,
    (sum, s) -> sum + s.length(),
    Integer::sum
); // 0
```

**Answer:** `0`. There are no elements to pass to the accumulator, so the identity is the result.

## Key takeaways

When using `reduce(identity, accumulator, combiner)` in **JAVA_STREAM_API**, view `accumulator` as folding **one `T` element** into a **`U` result**, and `combiner` as merging **two `U` results**. The trio must satisfy **neutral identity, associative combiner, and compatibility between accumulator/combiner**. A combining function that is valid on its own can still be the wrong combiner if it fails to reproduce the exact meaning of the accumulator. To accumulate into a mutable container, use `collect`; in parallel execution, avoid shared state and pay attention to ordering, numeric precision, and merging cost. That is the foundation for writing reductions that are correct and scale cleanly from sequential to parallel.
