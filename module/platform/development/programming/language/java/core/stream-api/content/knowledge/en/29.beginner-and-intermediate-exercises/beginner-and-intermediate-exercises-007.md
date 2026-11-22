# Writing Contract-Compliant `reduce` Operations and Finding Counterexamples

> **Chapter:** Beginner and Intermediate Exercises  
> **Module:** JAVA_STREAM_API  
> **Practice topic:** Designing contract-compliant `reduce` operations, finding the smallest dataset that breaks a faulty reduction, and fixing it with an appropriate operation. The exercises connect `filter`, `map`, `collect`, grouping, parallel processing, and state/precision issues in the Java Stream API.

## Learning Objectives

By the end of this lesson, you will be able to:

1. Distinguish the three overloads `reduce(BinaryOperator)`, `reduce(identity, accumulator)`, and `reduce(identity, accumulator, combiner)`.
2. Verify the **identity** and **associativity** laws of a reduction.
3. Verify **compatibility** between the accumulator and combiner in the three-argument overload.
4. Prove with a counterexample that a `reduce` can succeed sequentially yet fail when splitting and merging partitions.
5. Distinguish **associativity** from **commutativity**, and understand the role of encounter order.
6. Avoid accumulating into a shared mutable object or a variable outside the lambda.
7. Identify arithmetic pitfalls: `int`/`long` overflow, non-associativity of `double`, and intermediate `BigDecimal` rounding.
8. Choose `collect` over `reduce` when gathering elements into a mutable container.
9. Write automated checks for identity, associativity, compatibility, empty sources, boundary inputs, and an independent reference oracle.
10. Explain **why** a fix works, rather than tweaking code until one parallel run happens to return the expected answer.

**Version:** Examples use Java 17 or later, where `record` and `List.of` keep code concise. Most `reduce` operations have been available since Java 8. Standalone snippets can be placed inside a Java method with appropriate `import`s; full class programs can be run directly.

**Study method:** Every exercise follows **predict → find counterexample → analyze contract → fix → verify**. You do not need to run parallel threads to *prove* an operation is broken; merely exhibiting one valid intermediate grouping that produces a different result is already a valid counterexample.

---

## 1. Visualizing How `reduce` Can Partition Data

`reduce` is a **terminal operation**: it takes Stream elements and combines them into a single result. With a parallel Stream, work can be split into sub-ranges and intermediate results merged in a tree.

~~~text
Source with encounter order: [a, b, c, d]

One sequential evaluation:
  (((identity ⊕ a) ⊕ b) ⊕ c) ⊕ d

One partitioned evaluation:
       [a, b]                [c, d]
          |                     |
    identity ⊕ a ⊕ b       identity ⊕ c ⊕ d
          |                     |
        left                  right
          \                     /
           \--- combiner ------/
                     |
                  result
~~~

The `⊕` symbol in the diagram is a general notation; in the three-argument overload, **accumulator and combiner can have different parameter types**, but must carry compatible mathematical semantics.

**Do not try to predict the exact number of splits a Stream will create.** The diagram merely illustrates evaluation trees that any valid reduction must tolerate.

If correctness holds **only** when every element is fed into one accumulator strictly from left to right, the algorithm may be unsuitable for parallel `reduce`.

### 1.1. Three API Forms

| Form | Return Type | When to Use |
|---|---|---|
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Combining elements of the same type without inventing a default for empty sources |
| `reduce(T identity, BinaryOperator<T>)` | `T` | When a valid identity exists and the operation is associative |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Result type `U` differs from element type `T`, requiring compatible accumulator/combiner |

Basic example:

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(4, 7, 2);

int sum = values.stream().reduce(0, Integer::sum);

Optional<Integer> max = values.stream()
        .reduce(Integer::max);

long sumAsLong = values.stream()
        .reduce(
                0L,
                (acc, n) -> acc + n.longValue(),
                Long::sum
        );

System.out.println(sum);               // 13
System.out.println(max.orElseThrow()); // 7
System.out.println(sumAsLong);         // 13
~~~

Here each terminal operation opens a **fresh Stream** from `values`. Never reuse a `Stream` instance after calling `reduce`.

---

## 2. Two Core Laws of `reduce` with Identity

For the overload:

~~~java
T result = stream.reduce(identity, accumulator);
~~~

The contract requires `accumulator` to be **associative**, **stateless**, and **non-interfering**; `identity` must be the **identity element** of that operation.

### 2.1. The Identity Law

Let `e` be the identity and `f` be the accumulator:

~~~text
f(e, x) = x
f(x, e) = x
~~~

This two-sided property must hold for the operation used to combine values, since the framework may insert the identity into different accumulation branches. Even for a non-commutative associative operator, a two-sided identity is required.

Examples:

| Operation | Valid Identity | Verification |
|---|---|---|
| Integer addition | `0` | `0 + x = x + 0 = x` |
| Integer multiplication | `1` | `1 * x = x * 1 = x` |
| String concatenation | `""` | `"" + x = x + "" = x` |
| Immutable list concatenation | Empty list | `[] ++ xs = xs ++ [] = xs` |
| Maximum over full `int` domain | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Minimum over full `int` domain | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

An identity can **depend on the value domain**. `0` is an identity for `max` only if every value in the domain is **non-negative**; it fails for negative integers.

### 2.2. The Associativity Law

For all valid `a`, `b`, `c`:

~~~text
f(f(a, b), c) = f(a, f(b, c))
~~~

Mathematical integer addition and multiplication are associative; subtraction and division are not.

~~~java
int a = 10;
int b = 3;
int c = 2;

System.out.println((a - b) - c); // 5
System.out.println(a - (b - c)); // 9
~~~

This is a **counterexample** disproving the claim that subtraction is associative. Exhibiting a single triple where the two sides differ is enough to refute the law.

### 2.3. Commutativity Is Not Generally Required

**Associativity** regroups parentheses without changing operand order:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

**Commutativity** swaps operand positions:

~~~text
a ⊕ b = b ⊕ a
~~~

String concatenation is a key example:

~~~java
String a = "A";
String b = "B";
String c = "C";

System.out.println((a + b) + c); // ABC
System.out.println(a + (b + c)); // ABC

System.out.println(a + b); // AB
System.out.println(b + a); // BA
~~~

String concatenation is **associative** yet **non-commutative**. It works safely with `reduce("", String::concat)` on an ordered source and preserves result order by contract. Do not assume that "parallel requires every operation to be commutative".

---

## 3. Worked Example A — Integer Sum: Correct Version and Quick Check

~~~java
import java.util.List;

List<Integer> values = List.of(2, 5, 7);

int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sequential); // 14
System.out.println(parallel);   // 14
~~~

Contract check:

1. `0` is the additive identity.
2. `Integer::sum` performs `int` addition, which is associative **modulo** \(2^{32}\).
3. The addition function neither writes external variables nor mutates the source.
4. For inputs small enough not to overflow, the result also matches true mathematical integer addition.

**Limitation:** `reduce(0, Integer::sum)` does not guarantee a mathematically exact sum if values exceed `int` bounds. Correctness **in Java types** and correctness **in business semantics** are two separate questions.

When the total may exceed `Integer.MAX_VALUE` while fitting in `long`:

~~~java
long sum = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

When totals can exceed `long`, use `BigInteger` or an arithmetic model suited to the problem domain.

---

## 4. Counterexample 1 — Non-Zero Identity for Addition

Someone writes:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// Contract violation:
int total = values.parallelStream()
        .reduce(10, Integer::sum);
~~~

**Predict:** Why is `10` not an additive identity? What can happen with two partitions?

In a sequential left-to-right fold:

~~~text
((10 + 1) + 2) + 3 = 16
~~~

If split into `[1]` and `[2,3]`, each partition starts from `10`:

~~~text
Left partition:   10 + 1 = 11
Right partition:  10 + 2 + 3 = 15
Merge results:    11 + 15 = 26
~~~

`16 != 26`. This is a counterexample for a broken identity. We do not need to guess whether the JDK picks these exact two splits; **the existence of one valid split yielding a different result** proves the reduction violates the parallel contract.

Fix:

~~~java
int correct = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(correct); // 6
~~~

If business rules genuinely require **adding a fixed fee of 10 once**:

~~~java
int totalWithFee = Math.addExact(
        10,
        values.parallelStream().reduce(0, Integer::sum)
);

System.out.println(totalWithFee); // 16
~~~

Even though `Math.addExact` catches overflow on the final addition here, the inner `reduce` still uses `int` and could already overflow on large data. When overflow is possible, widen the type **before** accumulating.

**Rule:** A fixed business offset is not an identity. Reduce using the mathematical identity, then apply the adjustment **once outside**.

---

## 5. Counterexample 2 — Subtraction Is Not Associative

~~~java
import java.util.List;

List<Integer> numbers = List.of(10, 3, 2);

// WRONG if expecting a partition-independent reduction result:
int reduced = numbers.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Two ways to parenthesize:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

`5 != 9`, so subtraction is not associative.

Using `0` as an identity also **fails the two-sided rule**: `0 - x = -x`, which does not equal `x`. Thus this snippet violates **both identity and associativity**.

If the requirement is **subtracting sequentially from an initial amount**, use a sequential loop:

~~~java
int balance = 10;
for (int cost : List.of(3, 2)) {
    balance = Math.subtractExact(balance, cost);
}
System.out.println(balance); // 5
~~~

If the requirement is "opening balance minus the sum of all costs":

~~~java
import java.util.List;

int openingBalance = 10;
List<Integer> costs = List.of(3, 2);

long spent = costs.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

long closingBalance = openingBalance - spent;
System.out.println(closingBalance); // 5
~~~

The second version **rewrites the intermediate reduction** into addition, which has identity `0` and is associative. Subtraction happens **once after summing**. If you must rule out `long` overflow, consider `BigInteger`.

---

## 6. Counterexample 3 — Using `0` as Identity for `max` on All-Negative Numbers

~~~java
import java.util.List;

List<Integer> scores = List.of(-7, -2, -9);

// Wrong if you want the true maximum of the source:
int wrong = scores.parallelStream()
        .reduce(0, Integer::max);

System.out.println(wrong); // 0
~~~

No element equals `0`, yet the result is `0`. Reason:

~~~text
max(0, -7) = 0
max(0, -2) = 0
max(0, -9) = 0
~~~

`0` is not an identity for `max` over the **full `int` domain**.

Two fixes:

~~~java
import java.util.Optional;

Optional<Integer> max = scores.parallelStream()
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // -2
~~~

Or, when the domain is `int` and a valid identity is desired:

~~~java
int maxWithIdentity = scores.parallelStream()
        .reduce(Integer.MIN_VALUE, Integer::max);

System.out.println(maxWithIdentity); // -2
~~~

**Empty-source warning:** With `reduce(Integer.MIN_VALUE, Integer::max)`, an empty Stream returns `Integer.MIN_VALUE` even with no real elements. When you must distinguish "no data" from "an element equal to MIN_VALUE", prefer the `Optional<Integer>` overload.

### 6.1. Lesson on Data Domains

An identity is valid only if it works for **every value that can enter the reduction**. Never treat an accidental property of sample data ("all values happen to be non-negative this time") as a general law unless input validation enforces that domain.

---

## 7. Counterexample 4 — Associative Concatenation with a Reversed Combiner

String concatenation has identity `""`, and `String::concat` is associative:

~~~java
import java.util.List;

List<String> words = List.of("A", "B", "C");

String correct = words.parallelStream()
        .reduce("", String::concat);

System.out.println(correct); // ABC
~~~

This is a valid two-argument reduction for `String` on an ordered source.

Trouble arises when writing a custom combiner that **concatenates partitions in reverse order**:

~~~java
List<String> pieces = List.of("A", "B", "C");

String wrong = pieces.parallelStream()
        .reduce(
                "",
                (result, value) -> result + value,
                (left, right) -> right + left // WRONG with an ORDERED source
        );
~~~

Manual trace:

~~~text
Left partition:  [A]    -> "A"
Right partition: [B, C] -> "BC"

Correct combiner: "A" + "BC" = "ABC"
Wrong combiner  : "BC" + "A" = "BCA"
~~~

Even though `String` concatenation is associative, **swapping partition results** violates encounter order. That is a combiner bug, not a bug in `parallelStream`.

Fix:

~~~java
String fixed = pieces.parallelStream()
        .reduce(
                "",
                (result, value) -> result + value,
                (left, right) -> left + right
        );
System.out.println(fixed); // ABC
~~~

**Performance note:** Repeatedly concatenating strings with `String::concat` allocates many intermediate strings. When joining strings with a delimiter, `Collectors.joining(delimiter)` is usually cleaner:

~~~java
import java.util.stream.Collectors;

String csv = words.parallelStream()
        .collect(Collectors.joining(","));

System.out.println(csv); // A,B,C
~~~

A contract-compliant combiner is not necessarily the most memory- or CPU-efficient algorithm.

---

## 8. Three-Argument Overload: Adding a Compatibility Law

Signature:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
);
~~~

Here:

- `T` is the Stream element type.
- `U` is the accumulated/result type.
- `identity` has type `U`.
- `accumulator` combines `(U, T)` into `U`.
- `combiner` merges two `U` states.

To run accurately across partitions, we require:

1. **Identity for combiner:** `combiner(identity, u) = u` for valid states; in standard reduction designs, identity is also two-sided.
2. **Associativity of combiner:** `combine(combine(a,b),c) = combine(a,combine(b,c))`.
3. **Compatibility of accumulator and combiner:**

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

where `u` is a valid accumulated state and `t` is an input element.

This third law says: "merging state `u` with the partial result produced from a single element" must mean the exact same thing as "folding that element directly into state `u`".

### 8.1. Worked Example B — Summing String Lengths as `Long`

~~~java
import java.util.List;

List<String> words = List.of("java", "stream", "api");

long sequential = words.stream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

long parallel = words.parallelStream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(sequential); // 13
System.out.println(parallel);   // 13
~~~

Check with `u=4` and `t="api"`:

~~~text
accumulator(identity, "api") = 0 + 3 = 3
combiner(4, 3) = 4 + 3 = 7
accumulator(4, "api") = 4 + 3 = 7

=> compatibility holds
~~~

Furthermore, `Long::sum` has identity `0L` and is associative modulo \(2^{64}\). In a theoretical extreme where total length could exceed `long`, pick a wider counter type. For normal finite inputs within `long` bounds, the integer result is exact.

---

## 9. Counterexample 5 — Adding Accumulator, Max Combiner

~~~java
import java.util.List;

List<String> words = List.of("ab", "cde");

// WRONG:
long result = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::max
        );
~~~

Running sequentially on two elements may return `5` because sequential folding only invokes the accumulator:

~~~text
0 + len("ab") = 2
2 + len("cde") = 5
~~~

When split into two partitions:

~~~text
Left partition:  0 + 2 = 2
Right partition: 0 + 3 = 3
Combiner: max(2, 3) = 3
~~~

`3 != 5`. Compatibility is violated:

~~~text
u = 2
t = "cde"
identity = 0

combiner(2, accumulator(0, t)) = max(2, 3) = 3
accumulator(2, t)             = 2 + 3    = 5
~~~

Fix the combiner to use addition:

~~~java
long correct = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(correct); // 5
~~~

**This is the single most important counterexample for the three-argument overload:** `combiner` cannot be just "any valid operation on type U"; it must be **semantically compatible with what the accumulator builds**.

---

## 10. Counterexample 6 — Combiner Drops One Partition

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

// WRONG:
int wrong = numbers.parallelStream()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left
        );
~~~

Consider two partitions:

~~~text
[1,2] -> 3
[3,4] -> 7

combiner(3,7) = 3  (right partition dropped)
Correct result is 10
~~~

Regardless of whether a lucky run happens to return 10, the combiner is broken because it discards data from the right branch.

Fix with:

~~~java
int correct = numbers.parallelStream()
        .reduce(0, Integer::sum, Integer::sum);

System.out.println(correct); // 10
~~~

For integer Streams, an even cleaner option is:

~~~java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

**Testing mindset:** Deliberately construct **two non-empty partitions** and verify that merging them matches processing the whole source. Never test only single-element or empty lists, since those may never exercise the combiner.

---

## 11. Counterexample 7 — Using `reduce` to Mutate a Shared `List`

`reduce` is designed for **value reduction via an associative operation**, not for assembling a shared mutable container.

~~~java
import java.util.ArrayList;
import java.util.List;

// WRONG: sharing a mutable List identity and mutating it in the accumulator:
List<Integer> wrong = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(
                new ArrayList<Integer>(),
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

Problems:

- Identity is **a mutable `ArrayList` instance**, not an immutable empty value.
- Multiple partitions can receive the same identity reference, sharing mutable state.
- Both accumulator and combiner mutate their inputs, breaking the `reduce` contract that requires values to be combined safely.
- When a merge runs `left.addAll(right)` and `left` and `right` alias the same list, elements can be duplicated; under concurrent updates, `ArrayList` is also not thread-safe.

### 11.1. Fix with `collect`

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(result); // [1, 2, 3, 4]
~~~

This is the mutable reduction form `Stream.collect(supplier, accumulator, combiner)`. `supplier` allocates a **fresh container** per branch as needed, and `combiner` merges containers safely.

Or use a standard collector:

~~~java
import java.util.stream.Collectors;

List<Integer> collected = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(Collectors.toList());
~~~

If you only need a structurally unmodifiable List on Java 16+:

~~~java
List<Integer> immutable = List.of(1, 2, 3, 4)
        .parallelStream()
        .toList();
~~~

**Never try to fix a contract-broken reducer by adding `synchronized`.** Synchronization may eliminate data races, yet it still cannot turn a shared mutable identity into a semantically valid reduction.

### 11.2. Can You Reduce Immutable Lists?

In principle, you can use a concatenation operator that **returns a new list** without mutating inputs, with an empty list as identity. However, copying lists on every element is prohibitively expensive. `collect` is the right tool when building collections.

---

## 12. Counterexample 8 — External State Variables Inside Lambdas

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<Integer> values = List.of(1, 2, 3, 4);
AtomicInteger calls = new AtomicInteger();

int sum = values.parallelStream()
        .reduce(0, (acc, n) -> {
            calls.incrementAndGet(); // Side effect outside the reduction
            return acc + n;
        });
~~~

`AtomicInteger` makes increments atomic, yet **does not make the lambda stateless**. If business logic depends on how many times the accumulator ran, the design is flawed: a Stream may split work and build reduction trees freely; pipeline changes—especially short-circuiting or optimizations—can alter intermediate callback counts and execution patterns.

In a simple reduction over a finite source, the elements processed are dictated by the reduction, yet **you must never rely on invocation counts or callback order from a side-effect counter** as a general contract.

Worse still is making the computed value **depend** on a shared variable:

~~~java
int[] factor = {1};

int broken = values.parallelStream()
        .reduce(0, (acc, n) -> {
            factor[0]++; // Unsynchronized read/write
            return acc + n * factor[0];
        });
~~~

The result depends on thread scheduling and mutated state, so the accumulator is no longer a pure function of its two arguments. Making the `factor` array reference effectively final **does not** make its contents immutable or thread-safe.

The proper solution if you want to sum numbers after multiplying by constant 2:

~~~java
int correct = values.parallelStream()
        .mapToInt(n -> n * 2)
        .sum();

System.out.println(correct); // 20
~~~

When a calculation needs an index or timestamp per element, embed that field in the **input element or a contract-compliant aggregate state**, never in a counter outside the pipeline.

---

## 13. Arithmetic Is Part of the Contract: Overflow and Precision

### 13.1. `int` Adds Modulo \(2^{32}\), but Business Rules Often Need Exact Sums

~~~java
import java.util.List;

List<Integer> amounts = List.of(
        1_500_000_000,
        1_500_000_000
);

int wrapped = amounts.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(wrapped); // -1294967296
~~~

`Integer::sum` is still associative modulo `2^32`; this is a **numeric domain mistake**, not a counterexample to `int` addition associativity. The mathematical sum is `3_000_000_000`, which does not fit in `int`.

Fix by widening to `long` before summing:

~~~java
long exactInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(exactInLong); // 3000000000
~~~

If the total can exceed `long`:

~~~java
import java.math.BigInteger;

BigInteger exact = amounts.parallelStream()
        .map(n -> BigInteger.valueOf(n.longValue()))
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 3000000000
~~~

### 13.2. `Math.addExact` Detects Intermediate Overflow

~~~java
import java.util.List;

List<Long> values = List.of(Long.MAX_VALUE, 1L, -1L);

// May throw ArithmeticException under some groupings:
// values.parallelStream().reduce(0L, Math::addExact);
~~~

The **final mathematical sum** is `Long.MAX_VALUE`, which fits in `long`. Yet if one branch evaluates `Long.MAX_VALUE + 1` first, `Math.addExact` throws. Another grouping might add `1 + (-1) = 0` first and then add `Long.MAX_VALUE` without throwing.

Thus `Math.addExact` is useful when you want to **reject any intermediate overflow**; when considering exception behavior, it is not a total associative operator across all `long` sequences.

To compute the exact mathematical sum regardless of grouping and check bounds only at the end:

~~~java
BigInteger total = values.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

long result = total.longValueExact();
System.out.println(result); // 9223372036854775807
~~~

### 13.3. `double` Is Not Associative in Binary Floating-Point Arithmetic

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

`1.0` is lost when added to `-1.0e16` due to floating-point rounding. Therefore:

~~~java
import java.util.List;

List<Double> values = List.of(1.0e16, -1.0e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

// Do not assume a fixed parallel result across all configs/JDKs.
System.out.println(sequential);
System.out.println(parallel);
~~~

`DoubleStream.sum()` may use compensated summation and is not guaranteed to match the grouping of `reduce(0.0, Double::sum)`. Never treat one floating-point run as an exact canonical oracle for every pipeline.

For scientific or statistical apps, specify acceptable absolute/relative tolerances and compare against a suitable oracle. For currency requiring exact decimal precision, `BigDecimal` or integer minor units are usually preferable to `double`.

---

## 14. Counterexample 9 — Rounding `BigDecimal` Inside the Combiner

`BigDecimal` addition **without a `MathContext`** is exact decimal addition. However, rounding after **each addition** can break associativity.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("9.9");
BigDecimal b = new BigDecimal("0.2");
BigDecimal c = new BigDecimal("-9.9");

BigDecimal left  = a.add(b, mc).add(c, mc);
BigDecimal right = a.add(b.add(c, mc), mc);

System.out.println(left);  // 0.1
System.out.println(right); // 0.2
~~~

Two parenthesizations give **different results**. Hence:

~~~java
import java.util.List;

List<BigDecimal> amounts = List.of(a, b, c);

// Unsuitable if you want grouping-independent results:
// BigDecimal total = amounts.parallelStream()
//         .reduce(BigDecimal.ZERO, (x, y) -> x.add(y, mc));
~~~

Fix when business rules require **exact summation followed by rounding once at the end**:

~~~java
BigDecimal exactTotal = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = exactTotal.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 0.20
~~~

If business rules instead require rounding **each transaction line before summing**, normalize each line per policy first and sum the normalized values exactly. Never alter when rounding occurs casually, because the two approaches can yield different totals.

### 14.1. `BigDecimal` `equals` vs. `compareTo`

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
~~~

`equals` checks scale as well, whereas `compareTo` compares numeric value. When writing an oracle and tests, clarify whether you are checking **numeric value** or **value plus formatting/scale**.

---

## 15. Worked Example C — Keeping `sum` and `count` Immutable, Dividing Once at the End

To compute an arithmetic mean, never average partition averages when partition sizes can differ. Instead, store **sum** and **count** in an immutable state and merge them properly.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;

record SumCount(BigInteger sum, long count) {

    SumCount add(Integer n) {
        return new SumCount(
                sum.add(BigInteger.valueOf(n.longValue())),
                Math.addExact(count, 1L)
        );
    }

    SumCount merge(SumCount other) {
        return new SumCount(
                sum.add(other.sum),
                Math.addExact(count, other.count)
        );
    }

    BigDecimal average(int scale) {
        if (count == 0L) {
            throw new IllegalStateException("Empty source");
        }
        return new BigDecimal(sum).divide(
                BigDecimal.valueOf(count),
                scale,
                RoundingMode.HALF_UP
        );
    }
}

List<Integer> values = List.of(10, 20, 100);

SumCount stats = values.parallelStream()
        .reduce(
                new SumCount(BigInteger.ZERO, 0L),
                SumCount::add,
                SumCount::merge
        );

System.out.println(stats.sum());       // 130
System.out.println(stats.count());     // 3
System.out.println(stats.average(4));  // 43.3333
~~~

Why does this three-argument form work?

- `identity = SumCount(0,0)`.
- `add(n)` increments sum by `n` and count by 1, **returning a new state** without mutating the old one.
- `merge` adds sums together and counts together.
- Both sum and count combine additively; no partition-size information is lost.
- Division happens **after** reduction completes, never inside the combiner.

**Limitation:** `Math.addExact` on count will throw if the element count exceeds `long`. For ordinary datasets `count` stays within bounds, though if a theoretical requirement allows unbounded element counts, switch count to `BigInteger`. Average formatting must specify scale and rounding mode upfront.

### 15.1. Counterexample: Average of Two Averages

~~~text
Partition A = [10, 20] => average(A) = 15, count(A) = 2
Partition B = [100]    => average(B) = 100, count(B) = 1

Wrong:   (15 + 100) / 2 = 57.5
Correct: (10 + 20 + 100) / 3 = 43.333...
~~~

When a reducer keeps only a single `average` number, the combiner loses track of **how many** elements produced each average. You must preserve count (or corresponding weights) in the state.

---

## 16. Writing Algebraic Law Checks in Java

One passing `parallelStream()` run **does not prove** an operator is associative. Tests should actively exercise values likely to expose broken laws.

### 16.1. Checking Identity and Associativity of a `BinaryOperator`

The sample verification helper below applies to **immutable values** whose `equals` reflects the equivalence being tested:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.BinaryOperator;

public final class ReduceLawChecks {

    static <T> void verifyLaws(
            T identity,
            BinaryOperator<T> op,
            List<T> candidates) {

        for (T a : candidates) {
            if (!Objects.equals(op.apply(identity, a), a)
                    || !Objects.equals(op.apply(a, identity), a)) {
                throw new AssertionError(
                        "Identity violation at a=" + a
                );
            }

            for (T b : candidates) {
                for (T c : candidates) {
                    T left = op.apply(op.apply(a, b), c);
                    T right = op.apply(a, op.apply(b, c));

                    if (!Objects.equals(left, right)) {
                        throw new AssertionError(
                                "Associativity violation: "
                                + a + ", " + b + ", " + c
                                + " => " + left + " != " + right
                        );
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        verifyLaws(
                0,
                Integer::sum,
                List.of(-3, 0, 2, 7)
        );
        System.out.println("ADD_PASS");

        try {
            verifyLaws(
                    0,
                    (Integer a, Integer b) -> a - b,
                    List.of(2, 3, 7)
            );
            throw new AssertionError("Subtraction should have failed");
        } catch (AssertionError expected) {
            System.out.println("SUBTRACT_FAILED_AS_EXPECTED");
        }

        try {
            verifyLaws(
                    10,
                    Integer::sum,
                    List.of(1, 2, 3)
            );
            throw new AssertionError("Bad identity should have failed");
        } catch (AssertionError expected) {
            System.out.println("IDENTITY_FAILED_AS_EXPECTED");
        }
    }
}
~~~

This is **sample-based testing**, not a mathematical proof for all possible inputs. Include boundary cases such as `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, and values near overflow thresholds when the domain requires it.

### 16.2. Checking Compatibility of a Three-Argument `reduce`

A simple check for immutable `Long` states:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;

static <T, U> void verifyCompatibility(
        U identity,
        BiFunction<U, T, U> accumulator,
        BinaryOperator<U> combiner,
        List<U> states,
        List<T> elements) {

    for (U u : states) {
        for (T t : elements) {
            U left = combiner.apply(
                    u, accumulator.apply(identity, t)
            );
            U right = accumulator.apply(u, t);

            if (!Objects.equals(left, right)) {
                throw new AssertionError(
                        "Compatibility violation with u=" + u
                        + ", element=" + t
                );
            }
        }
    }
}
~~~

Place this static helper inside a utility class. Usage:

~~~java
import java.util.List;

verifyCompatibility(
        0L,
        (Long sum, String word) -> sum + word.length(),
        Long::sum,
        List.of(0L, 2L, 7L),
        List.of("", "ab", "cde")
); // PASS

// Using Long::max will FAIL, e.g., u=2, t="cde":
// max(2, 3) != 2 + 3.
~~~

In addition to compatibility, **you still must check identity and associativity of the combiner**. A compatibility check alone does not validate the entire contract.

### 16.3. Why Should You Not Reuse Mutable Objects in Law Checks?

When calling `op.apply(a,b)`, a mutable operator may **modify a or b**. Reusing those same two objects for the opposite side corrupts test inputs and skews results.

For mutable operations, you must:

- Construct **fresh containers** for each check from immutable test inputs.
- Compare **snapshot** results before and after.
- Test merging empty containers and different parenthesizations.
- Carefully evaluate whether `collect` should replace `reduce` altogether.

---

## 17. Verifying Results Against an Independent Oracle

Algebraic laws are baseline requirements. You also need an **independent oracle** that computes the problem's exact expected result.

For example, `int` sums can overflow, so use `BigInteger` as the reference oracle to validate a candidate reducer:

~~~java
import java.math.BigInteger;
import java.util.List;

static BigInteger oracleSum(List<Integer> input) {
    BigInteger expected = BigInteger.ZERO;

    for (int n : input) {
        expected = expected.add(BigInteger.valueOf(n));
    }
    return expected;
}

static BigInteger parallelExactSum(List<Integer> input) {
    return input.parallelStream()
            .map(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);
}

List<Integer> input = List.of(
        1_500_000_000, 1_500_000_000, -1
);

BigInteger expected = oracleSum(input);
BigInteger actual = parallelExactSum(input);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected " + expected + ", actual " + actual
    );
}

System.out.println(actual); // 2999999999
~~~

Both static methods can live inside a test class. The oracle uses a plain loop without calling the reducer under test. For requirements like currency and averages, the oracle must use the **exact numeric type and rounding policy** dictated by business rules.

### 17.1. Counterexample Test Matrix

| Test Case | Bug Likely Exposed |
|---|---|
| Empty source | Fake identity; `max`/`min` missing empty-data handling |
| Single element | Invalid identity; operator alters value |
| Two non-empty partitions | Combiner drops or duplicates one side |
| Three partitions with different groupings | Associativity violated |
| All negative numbers | `max` with identity `0` |
| Large cancelling positive/negative numbers | `double` and `addExact` sensitivity to grouping |
| `int` sum exceeding 2,147,483,647 | Numeric type overflow |
| Multiple ordered strings | Combiner concatenating backwards |
| Unequal-sized groups | Average of averages |
| Mutable `List` used as identity | Shared container, duplication, data race |
| Repeated parallel runs | Schedule-dependent bugs |
| Empty/null data | Execution on unvalidated or empty input |

### 17.2. Manual Partitioning Checks Without Guessing Thread Counts

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 3, 5, 7);

// Split into [2,3] and [5,7].
List<Integer> leftData = numbers.subList(0, 2);
List<Integer> rightData = numbers.subList(2, 4);

int left = leftData.stream().reduce(0, Integer::sum);
int right = rightData.stream().reduce(0, Integer::sum);

int combined = Integer.sum(left, right);
int full = numbers.stream().reduce(0, Integer::sum);

if (combined != full) {
    throw new AssertionError("Merge violation");
}
~~~

This checks a valid merge. Replacing `Integer::sum` with a broken combiner like `Math::max` exposes a counterexample on suitable inputs even if a single `parallelStream` run wouldn't happen to split along that exact boundary.

---

## 18. Beginner Exercises: Find the Bug Before Checking the Answer

### Exercise 1. Correct Sum

**Prompt:** Given `[4, 8, 3, 5]`, write a two-argument `reduce` returning `20` and justify identity and associativity.

**Hint:** Addition and `0`.

**Answer:**

~~~java
import java.util.List;

int total = List.of(4, 8, 3, 5).parallelStream()
        .reduce(0, Integer::sum);

System.out.println(total); // 20
~~~

`0 + x = x + 0 = x`. `int` addition is associative modulo \(2^{32}\); the sample sum does not overflow, so it also matches exact integer addition.

### Exercise 2. Spotting a Bad Identity

**Prompt:** For `List.of(2, 3)` and `reduce(5, Integer::sum)`, compute the sequential result and one two-partition merge.

**Answer:**

~~~text
Sequential: ((5+2)+3) = 10
Two parts [2], [3]:
  (5+2) + (5+3) = 7+8 = 15
~~~

Wrong because `5` is not the additive identity. Change identity to `0` and add the business constant `5` once after `reduce` if needed.

### Exercise 3. Proving Subtraction Is Not Associative

**Prompt:** Find three integers `a,b,c` such that `(a-b)-c != a-(b-c)`.

**Answer:** `a=10`, `b=3`, `c=2`: the two sides give `5` and `9`. Do not use subtraction as an associative reduction; sum costs first and subtract once instead.

### Exercise 4. Maximum on All-Negative Values

**Prompt:** What does `List.of(-8, -2, -5).stream().reduce(0, Integer::max)` return? Is it the true maximum of the data?

**Answer:** Returns `0`, which is wrong because the true maximum is `-2`. Use `reduce(Integer::max)` returning `Optional<Integer>`, or identity `Integer.MIN_VALUE` when a sentinel for empty sources is acceptable.

### Exercise 5. Handling an Empty Stream

**Prompt:** Predict the output:

~~~java
import java.util.List;

System.out.println(List.<Integer>of().stream()
        .reduce(0, Integer::sum));

System.out.println(List.<Integer>of().stream()
        .reduce(Integer::max));
~~~

**Answer:** The first line prints `0`; the second prints `Optional.empty`. The two overloads have different empty-input return contracts.

### Exercise 6. String Concatenation Preserving Encounter Order

**Prompt:** Given `["J","A","V","A"]`, write a `reduce` with the proper identity to produce `"JAVA"` and state whether the operator needs to be commutative.

**Answer:**

~~~java
String text = List.of("J", "A", "V", "A")
        .parallelStream()
        .reduce("", String::concat);

System.out.println(text); // JAVA
~~~

String concatenation is associative with identity `""`, yet non-commutative. With an ordered `List`, the result preserves encounter order. In production when joining many strings, prefer `Collectors.joining()` to reduce allocations.

### Exercise 7. True or False: Accumulator and Combiner Need Not Share the Same Meaning

**Prompt:**

~~~java
long n = List.of("aa", "bbb").parallelStream()
        .reduce(
                0L,
                (sum, s) -> sum + s.length(),
                Long::max
        );
~~~

**Answer:** False. When split into two parts, intermediate results are `2` and `3`, and `max(2,3)=3` differs from the true sum `5`. Change the combiner to `Long::sum`.

---

## 19. Intermediate Exercises: Designing Merges and Counterexamples

### Exercise 8. Total Length via Three-Argument `reduce`

**Prompt:** Given `List.of("a","bb","ccc")`, write a three-argument `reduce` returning `6L` and prove compatibility.

**Answer:**

~~~java
import java.util.List;

long length = List.of("a", "bb", "ccc")
        .parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(length); // 6
~~~

For any valid state `u` and string `s`, `u + (0 + len(s)) = u + len(s)`, so compatibility holds. `Long::sum` has identity 0 and is associative modulo `long`.

### Exercise 9. Splitting into Two Partitions to Catch a Bad Combiner

**Prompt:** A reducer has an adding accumulator but combiner `(a,b) -> a`. Source is `[2,3,5,7]`. Evaluate with two partitions `[2,3]` and `[5,7]`.

**Answer:** Left = `5`, right = `12`. The buggy combiner returns `5` instead of `17`. Fix the combiner to `Integer::sum`.

### Exercise 10. Reversed String Concatenation

**Prompt:** Why is `reduce("", (s,t)->s+t, (left,right)->right+left)` unsuitable for preserving order on `["A","B","C"]`?

**Answer:** Two partitions `["A"]` and `["B","C"]` yield `"A"` and `"BC"`. The faulty combiner produces `"BCA"` instead of `"ABC"`. Use `left + right` in partition order.

### Exercise 11. Computing Average Across Unequal Partitions

**Prompt:** Group one has `[10,20]`, group two has `[100]`. Can we combine by averaging the two averages?

**Answer:** No. `(15+100)/2=57.5` is wrong; the true average is `130/3≈43.3333`. Design a `(sum,count)` state whose accumulator updates both fields, whose combiner adds each field, and divide only in the finalization step.

### Exercise 12. Overflow with a Valid Identity

**Prompt:** Does `reduce(0, Integer::sum)` on two values `1_500_000_000` violate associativity? Does it return the correct business sum?

**Answer:** `int` addition is associative modulo \(2^{32}\), so it does not violate the algebraic law under modular arithmetic. However, `-1294967296` is not the mathematical integer sum `3_000_000_000`. Widen to `long` before adding, or use `BigInteger` if values can exceed `long`.

### Exercise 13. Choosing `collect` or `reduce`?

**Prompt:** If you want a `List<String>` from multiple String elements, should you pass `new ArrayList<>()` as the identity and mutate it inside `reduce`'s accumulator?

**Answer:** No. Gathering into a mutable container calls for `collect(ArrayList::new, List::add, List::addAll)`, `Collectors.toList()`, or `Stream.toList()`. A mutable identity in three-argument `reduce` can be shared across branches and corrupt results.

### Exercise 14. `BigDecimal` and Rounding

**Prompt:** A `reduce` adds `BigDecimal` values using `add(b, new MathContext(2))` at every step. Is the merge guaranteed to be associative?

**Answer:** No. The triple `9.9, 0.2, -9.9` yields `(a+b)+c=0.1` and `a+(b+c)=0.2` under `MathContext(2, HALF_UP)`. When appropriate for business rules, sum without intermediate rounding and round once at the end.

### Exercise 15. Law Checks Alone Do Not Prove Business Correctness

**Prompt:** An `Integer::sum` reducer passes identity/associativity checks on a sample set of integers. Can you conclude it is safe for all monetary totals?

**Answer:** No. You must also check numeric domains and currency rules: `int` overflow can still occur. Verify against a `BigInteger` oracle or sufficiently wide minor-unit integers, including boundary cases and rounding policies.

### Exercise 16. Reduction with Two Metrics

**Prompt:** You need both **total units** and **total revenue** across all sales. Should you update two mutable variables outside a `parallelStream().forEach` lambda?

**Answer:** No. Create a combined state holding both fields, with accumulator/combiner returning fresh states (for `reduce`) or a collector with an independent supplier and valid combiner (for `collect`). Test merging two partitions and verify against an independent oracle.

Illustrative example using `record`:

~~~java
import java.math.BigInteger;
import java.util.List;

record Sale(long units, long cents) {}
record Totals(BigInteger units, BigInteger cents) {

    Totals add(Sale sale) {
        return new Totals(
                units.add(BigInteger.valueOf(sale.units())),
                cents.add(BigInteger.valueOf(sale.cents()))
        );
    }

    Totals merge(Totals other) {
        return new Totals(
                units.add(other.units()),
                cents.add(other.cents())
        );
    }
}

List<Sale> sales = List.of(
        new Sale(2, 1200),
        new Sale(1, 500),
        new Sale(-1, -500)
);

Totals totals = sales.parallelStream()
        .reduce(
                new Totals(BigInteger.ZERO, BigInteger.ZERO),
                Totals::add,
                Totals::merge
        );

System.out.println(totals.units()); // 2
System.out.println(totals.cents()); // 1200
~~~

This works because the identity is neutral for each field, `BigInteger` addition is associative, and no shared container is mutated.

---

## 20. Self-Grading Checklist Before Submitting a `reduce`

For every reduction you write, answer these questions:

| Check Question | Required Evidence |
|---|---|
| **What is the identity?** | Show `f(e,x)=x` and `f(x,e)=x` across the value domain |
| **Is the merge associative?** | Algebraic argument, checking `(a⊕b)⊕c` and `a⊕(b⊕c)` |
| **Is commutativity needed?** | Not by default; verify whether encounter order must be kept |
| **Does three-arg compatibility hold?** | Check `combine(u,acc(e,t)) = acc(u,t)` |
| **Are lambdas stateless/non-interfering?** | No source mutation, no reliance on changing external variables |
| **Are identity or state mutable?** | Never share a mutable object improperly through `reduce` |
| **What does an empty source return?** | Valid identity or `Optional.empty` per contract |
| **Is the numeric type wide enough?** | Check overflow, precision, and rounding mode |
| **Is required order preserved?** | For string/list concatenation, never reverse partition merges |
| **Were multiple partitions tested?** | Two non-empty parts, three parts under both groupings |
| **Is there an independent oracle?** | Loop / hand calculation / `BigInteger` matching business rules |
| **Should `collect` replace `reduce`?** | If the goal is a mutable container, prefer a proper collector |

### 20.1. Solution Selection Flowchart

~~~text
Need to aggregate a Stream?
        |
        v
Gathering into a mutable container (List/Map/Set)?
        |--- Yes --> Prefer collect/Collector
        |
        v
Is there an associative op on type T and a valid identity?
        |--- Yes --> reduce(identity, operator)
        |
        v
No general identity, but need max/min/comparison?
        |--- Yes --> reduce(BinaryOperator) -> Optional<T>
        |
        v
State type U differs from element type T?
        |--- Yes --> reduce(identity, accumulator, combiner)
        |             with compatibility + associativity
        |
        v
Need special sequential ordering or non-associative steps?
        |--- Yes --> Rethink algorithm; do not force into parallel reduce
        |
        v
Verify laws + oracle + edge cases
        |
        v
Benchmark parallel performance only after correctness is proven
~~~

### 20.2. What Cannot Be Inferred from a Single Run

- `sequential == parallel` **does not prove** identity and associativity hold: the combiner path might not have been triggered.
- `sequential == parallel` **does not prove** monetary sums are accurate: both runs could overflow identically.
- One correct `parallel` run **does not guarantee** all other split/merge schedules will succeed.
- Tests on a few small values **are not a mathematical proof** for all inputs.
- Adding `synchronized`/`AtomicInteger` **does not fix** an algorithm with a broken combiner or bad identity.
- "Uses multiple CPU cores" **never substitutes** for validating numeric results and data semantics.

---

## Summary

A solid `reduce` requires a **valid identity**, an **associative operator**, and **stateless, non-interfering** behavior. In the three-argument overload, accumulator and combiner must also be **compatible**. Use **small counterexamples** to expose flaws early: identity `10` for addition, subtraction, `max` with `0` on negative numbers, a max combiner for summing lengths, reversed string merging, or a mutable list passed as identity. Then verify results against an **independent oracle** and boundary inputs, especially before running in parallel.

**Key takeaway:** `reduce` is not "any loop rewritten with lambdas". It is an **algebraic reduction with a formal contract**, designed so the Stream API can split work and recombine partial results accurately. Once you understand and test that contract yourself, you can use `reduce`, `collect`, and parallel Java Stream API pipelines with confidence.

