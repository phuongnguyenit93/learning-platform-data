# Testing Associativity and Identity Elements of Reductions in Java Streams

## 1. Lesson goal

When writing **Stream.reduce(...)**, getting the right result on a small example is **not enough** to conclude that the reduction is correct. A Stream can split the source into multiple parts and merge partial results, especially when running in **parallel**. Therefore, the reduction operation must obey certain **algebraic laws** so that the result does not depend on how work is split and combined.

The two foundational laws are:

- **Identity element:** combining a value with the identity does not change that value.
- **Associativity:** changing how parentheses are grouped in a chain of combinations does not change the result under the defined equivalence relation.

For the three-argument overload `reduce(identity, accumulator, combiner)`, you also need to test **compatibility** between how elements are accumulated and how partial results are combined.

After this lesson, you will be able to:

1. Distinguish the three overloads of `reduce()`, and identify the corresponding identity and combination operation.
2. Write two-sided identity, associativity, and compatibility tests matching Java semantics.
3. Catch subtraction, non-identity "initial values", wrong combiners, and shared mutable accumulators.
4. Test empty sources, single elements, negative numbers, boundary values, partitions, and sequential/parallel execution.
5. Understand the difference between correctness **under Java integer semantics** and correctness **under business requirements**.
6. Evaluate `double` addition, `BigDecimal`, string concatenation, and non-commutative combination operations.
7. Use targeted sample tests and fixed-seed random tests to catch bugs, without equating testing with mathematical proof.

## 2. Why does reduce need these laws?

Example:

~~~java
int sum = List.of(1, 2, 3, 4).parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 10
~~~

In one execution, the source might be processed as:

~~~text
Left branch:   1 + 2 = 3
Right branch:  3 + 4 = 7
Combine:       3 + 7 = 10
~~~

Or in another way:

~~~text
Branch A: 1
Branch B: 2
Branch C: 3 + 4 = 7
Combine:  1 + (2 + 7) = 10
~~~

This is an illustrative diagram, **not a guarantee that the JVM actually creates those exact three branches**. The point is that the framework may change how elements are grouped while still having to produce a result consistent with the reduction contract.

If `Integer::sum` is replaced with subtraction, the result can change when parentheses are grouped differently. If identity `0` is replaced with `10`, each branch may carry 10 as an initial value, causing the result to no longer be "10 plus the source sum" as intended.

**Conclusion:** you need to test the **laws of the combination operation**, not just run a single terminal operation on one dataset.

## 3. Three reduce() overloads to distinguish

### 3.1. reduce(BinaryOperator<T>): no explicit identity

~~~java
Optional<Integer> maximum = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(maximum.orElse(-1)); // 9
~~~

Signature:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Because no identity is passed, when the source is empty the result is `Optional.empty()`. The combination operation still needs to be **associative**. This is a useful choice when there is no valid identity value across the entire domain.

~~~java
Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::max);

System.out.println(none.isEmpty()); // true
~~~

These snippets require importing `Optional`, `List`, and `Stream`.

### 3.2. reduce(identity, BinaryOperator<T>): same result type

~~~java
int product = List.of(2, 3, 4).parallelStream()
        .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
~~~

Signature:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

For multiplication, the identity is **1**, not 0. If 0 is used, every product becomes 0, even when all elements are non-zero.

Calling `reduce(1, (a,b)->a*b)` on an empty source returns **1**: this is precisely the role of the identity element. By contrast, the overload without identity returns `Optional.empty` on an empty source.

### 3.3. reduce(identity, accumulator, combiner): different element and result types

~~~java
int totalLength = List.of("Java", "Go", "C")
        .parallelStream()
        .reduce(
                0,
                (subtotal, word) -> subtotal + word.length(),
                Integer::sum
        );

System.out.println(totalLength); // 7
~~~

General signature:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Here:

- Source element **T = String**.
- Result **U = Integer**.
- Identity of type U is **0**.
- Accumulator turns a **U** and a **String** into a new **U**.
- Combiner combines **two U** values from branches into one **U**.

This overload has **two different function types**; besides associativity of the combiner, you must also test the compatibility law between accumulator and combiner.

## 4. What is an identity element?

For a combination operation \(\oplus\), a value e is a **two-sided identity** if:

\[
e \oplus x = x
\]

and

\[
x \oplus e = x
\]

for every x in the allowed value domain.

An intuitive table:

| Combination operation | Identity | Why |
| --- | --- | --- |
| Integer addition | **0** | 0 + x = x + 0 = x |
| Integer multiplication | **1** | 1 × x = x × 1 = x |
| `String` concatenation | **""** | "" + s = s + "" = s |
| Boolean AND | **true** | true && x = x && true = x |
| Boolean OR | **false** | false &#124;&#124; x = x &#124;&#124; false = x |
| Max over full `int` range | **Integer.MIN_VALUE** | max(minInt, x) = x |
| Min over full `int` range | **Integer.MAX_VALUE** | min(maxInt, x) = x |

**Note on min/max:** an effective identity must be valid across the **entire domain**. Choosing 0 as the identity for max can fail if all numbers are negative. If there is no suitable boundary value or the domain is not clearly bounded, use `reduce(BinaryOperator)` without identity and return `Optional`.

### 4.1. Why check both left and right?

Some operations have a one-sided identity but not a two-sided identity.

For example, with subtraction:

~~~text
x - 0 = x           (0 is a right identity)
0 - x = -x ≠ x      (0 is not a left identity, unless x = 0)
~~~

Thus `0` is **not** a two-sided identity for subtraction.

A test that only checks `combine(x, identity) == x` will miss this bug.

### 4.2. Identity is not an "initial offset to add"

Counterexample:

~~~java
int result = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

If the intent is "10 + sum of [1,2,3]", this code **does not have a valid identity** for addition. When partitioned, the identity 10 can be applied to multiple branches.

Right way:

~~~java
int result = 10 + IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // 16
~~~

Here the extra 10 sits **outside the reduce**, while the identity of addition remains 0.

### 4.3. Testing an empty source is a useful identity check

~~~java
int emptySum = IntStream.empty().reduce(0, Integer::sum);
int emptyProduct = IntStream.empty().reduce(1, (a, b) -> a * b);

System.out.println(emptySum);     // 0
System.out.println(emptyProduct); // 1
~~~

Testing an empty source verifies the return value when there are no elements, but **does not prove** the identity holds for all values. You must test both sides across many values, especially negative and boundary values.

## 5. Associativity

A combination operation \(\oplus\) is associative if:

\[
(a \oplus b) \oplus c = a \oplus (b \oplus c)
\]

for all triples a, b, c in the corresponding domain.

This allows the framework to change how parentheses are grouped without changing the result, a foundation of parallel reduction.

### 5.1. Addition example

~~~text
(2 + 3) + 4 = 9
2 + (3 + 4) = 9
~~~

On Java integers, `int` addition is associative under **32-bit wraparound semantics**, even though the mathematical sum may overflow. Therefore, distinguish:

- **Correct per reduce contract in Java int domain:** addition is defined with overflow modulo 2³².
- **Correct per business requirements:** if a mathematical sum must be exact beyond 32 bits, `Integer::sum` can yield an unacceptable value, regardless of being associative in the int domain.

For example:

~~~java
int wrapped = Integer.MAX_VALUE + 1;
System.out.println(wrapped); // -2147483648
~~~

An associativity law test **does not automatically detect** that the chosen numeric type is too narrow for the business domain.

### 5.2. Subtraction is not associative

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

If subtraction is used as the accumulator/combiner of a parallel reduce, different partitions can lead to different results. You need an algorithm that expresses the requirement properly: for instance, if you want "first number minus the sum of the rest", separate the first element and the remainder using an explicitly ordered structure instead of expecting a parallel reduce to interpret sequential subtraction.

### 5.3. Associativity differs from commutativity

**Commutativity** is:

\[
a \oplus b = b \oplus a
\]

It is **not** a required condition for reduce on an **ordered stream**.

String concatenation example:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
"A" + "B" = "AB", but "B" + "A" = "BA"
~~~

String concatenation is **associative** but **not commutative**. On an ordered stream from `Stream.of("A","B","C")`, string-concatenation reduction per contract produces **"ABC"** even when run in parallel, provided the reduction conditions are satisfied.

If the source or aggregation is **unordered**, do not impose a textual order that is not guaranteed. For non-commutative operations, encounter order can be a critical part of the requirement.

### 5.4. Max/min operations

`Integer::max` and `Integer::min` are associative. For int values, the identities for max/min in the table above are valid. However, when comparing objects with a Comparator, the Comparator must be stable and obey comparison laws; a comparator depending on mutable state can break the correctness of finding min/max.

## 6. Testing laws with reusable check functions

For a `BinaryOperator<T>`, you can write checks:

~~~java
static <T> void checkIdentity(
        T identity,
        BinaryOperator<T> combine,
        T value) {
    if (!Objects.equals(combine.apply(identity, value), value)
            || !Objects.equals(combine.apply(value, identity), value)) {
        throw new AssertionError("Invalid identity");
    }
}

static <T> void checkAssociative(
        BinaryOperator<T> combine,
        T a, T b, T c) {
    T left = combine.apply(combine.apply(a, b), c);
    T right = combine.apply(a, combine.apply(b, c));
    if (!Objects.equals(left, right)) {
        throw new AssertionError("Not associative");
    }
}
~~~

These are fragments; you need to import `BinaryOperator` and `Objects` and place them inside a class. Using `Objects.equals` is appropriate when type T's `equals` accurately expresses result equivalence.

**Do not blindly apply `Objects.equals` to every numeric or mutable type:**

- For `BigDecimal`, `equals` also considers **scale**, while `compareTo` checks numeric value; choose the equivalence notion per business rules.
- For `double`, rounding error means exact equality checks may be unsuitable for approximate operations.
- For mutable objects, two branches may share a reference; checking `equals` on the same mutated object can hide ownership/aliasing bugs.
- If the result has unrelated metadata fields, define the exact equivalence relation for that reduction.

### 6.1. Do not test only one triple

A test with `a=1,b=2,c=3` can miss many bugs. You should test:

1. **0**, positive numbers, and negative numbers.
2. Duplicate values.
3. **Integer.MIN_VALUE** and **Integer.MAX_VALUE**.
4. Reversed element order.
5. Triples where intermediate pairs can overflow.
6. Values with null or missing-data states if the domain allows them.
7. Triples with equal comparison keys in max/min problems.
8. Random data with a fixed seed to reproduce counterexamples.

A test suite can detect law violations; it **does not replace proving** that the combination operation holds for all possible values.

## 7. Property-based tests with a fixed seed

A useful technique is generating many triples a, b, c and checking the identity and associativity laws.

Pseudo-code:

~~~text
for each value x:
    assert combine(identity, x) == x
    assert combine(x, identity) == x

for each triple (a, b, c):
    assert combine(combine(a, b), c)
        == combine(a, combine(b, c))
~~~

If using `Random`, **fix the seed** and include the seed in failure messages. When a test fails, you can rerun with the same seed to reproduce.

Generators should also include:

- Explicit boundary values, since random generation may rarely pick them.
- Representation of 0 and negative numbers.
- Sequences longer than three elements in end-to-end tests.
- For financial aggregations, large values/decimals/negative quantities if business rules allow them.

Design failure messages to record the **pair/triple of values** causing the error and the **results of both sides**. Do not just print "test failed", as that lacks the data needed for investigation.

### 7.1. Pitfall of only comparing sequential and parallel

A reduction that violates the laws can still produce the **same result** on some sequential and parallel runs, because the scheduler happens to split data in a "lucky" way or the dataset does not trigger the bug.

Therefore:

- **Law tests** to check the underlying cause.
- **End-to-end tests** on sequential/parallel to check the implementation.
- **Code review** to spot aliasing, mutation, and preconditions.
- Do not claim "passed 1,000 times" as proof that a shared mutable identity is safe.

## 8. Compatibility in reduce(identity, accumulator, combiner)

For the three-argument overload, another important condition is needed besides identity and associativity of the combiner.

Suppose:

- Identity is e of type U.
- Accumulator `acc(U,T)`.
- Combiner `combine(U,U)`.

Java's **compatibility** condition can be written:

\[
combine(u, acc(e,t)) = acc(u,t)
\]

for all valid u, t. It guarantees that adding t to a subtotal U is equivalent to creating a subtotal containing only t from the identity and then combining.

### 8.1. Correct example: total string length

~~~java
int total = Stream.of("Java", "Go", "C")
        .parallel()
        .reduce(
                0,
                (subtotal, word) -> subtotal + word.length(),
                Integer::sum
        );

System.out.println(total); // 7
~~~

With u=5, t="Go" (length 2):

~~~text
combine(5, acc(0, "Go")) = 5 + 2 = 7
acc(5, "Go")             = 5 + 2 = 7
~~~

Both sides are equal. Combiner `Integer::sum` is associative with identity 0.

### 8.2. Wrong example: incompatible combiner

~~~java
BiFunction<Integer, String, Integer> accumulator =
        (subtotal, word) -> subtotal + word.length();

BinaryOperator<Integer> badCombiner = Integer::max;
~~~

With u=3, t="Java":

~~~text
combine(3, acc(0, "Java")) = max(3, 4) = 4
acc(3, "Java")              = 3 + 4 = 7
~~~

The two sides differ. Even though **max** is associative on its own, it is **incompatible** with the length-summing accumulator.

**This is why checking only associativity of the combiner is not enough for the three-argument overload.**

### 8.3. Compatibility test

~~~java
static <U, T> void checkCompatibility(
        U identity,
        BiFunction<U, T, U> accumulator,
        BinaryOperator<U> combiner,
        U subtotal,
        T item) {
    U left = combiner.apply(
            subtotal, accumulator.apply(identity, item));
    U right = accumulator.apply(subtotal, item);
    if (!Objects.equals(left, right)) {
        throw new AssertionError("Incompatible reduction");
    }
}
~~~

This is a fragment requiring imports for `BiFunction`, `BinaryOperator`, and `Objects`, placed inside a class. Test many meaningful subtotals U and items T. Do not test only subtotal 0: a broken combiner may still happen to pass at that value.

## 9. Mutable identity and aliasing: bugs that equals comparisons can miss

A dangerous counterexample:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new ArrayList<String>(),
                (list, word) -> {
                    list.add(word);     // Mutation of identity.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right); // May receive an alias.
                    return left;
                }
        );
~~~

This is a **counterexample that should not be run in production**. Even though the code compiles, it violates the reduce model:

- The identity is **a mutable ArrayList**.
- Branches can use the same identity object instead of each branch having an independent container.
- The accumulator mutates the very list it receives and returns the same reference.
- The combiner can receive `left == right`, appending a list to itself and duplicating elements.
- ArrayList is not thread-safe, so races or lost/corrupted data can occur.

**A reduce test on a few elements that happens to pass does not prove this pattern is valid.** Adding `synchronizedList` or `AtomicInteger` only addresses one aspect of concurrency; it does not fix identity/aliasing or the compatibility law.

### 9.1. When to use collect?

If you want to build a **result list**, use `collect`:

~~~java
List<String> values = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(values); // [A, B, C]
~~~

Here `Supplier` creates a fresh container for mutable reduction; accumulator updates the work unit's container; combiner merges separate containers per contract.

**Do not return the same shared container from collect's Supplier**. For example, `() -> sharedArrayList` is a different bug with the same root cause: breaking container ownership when the framework splits work.

### 9.2. Testing mutable results properly

If an aggregation returns a mutable object, do not only check `result.equals(expected)` once. Verify:

- Is a **separate object** created for each unit of work when needed?
- Can partial results **alias** each other?
- Can the combiner be called with the same object for both parameters, and does the contract allow that?
- After reduction, are the source and related objects unexpectedly mutated?
- Under parallel execution, is adding elements thread-safe?
- Across multiple partitions, does the result have all elements with no duplicates and no missing items?

**Value laws** and **state ownership** are two separate testing axes.

## 10. Associativity of double: tests must know the semantics

In real-number mathematics, addition is associative. However, Java **double** uses IEEE 754 floating-point numbers, rounding after each operation. Therefore, double addition is **not associative in the bitwise-equal sense**.

Example:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Left side: `a+b = 0.0`, plus c → 1.0.

Right side: `b+c` can round to -1e16, plus a → 0.0.

**Consequence:** if a `DoubleStream.sum()` or parallel reduction changes how additions are grouped, the result may differ slightly from sequential addition order.

### 10.1. Choosing an appropriate comparison condition

In approximate measurement problems, you can use an absolute or relative tolerance:

~~~java
double tolerance = 1e-9;
if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("Difference too large");
}
~~~

However, **do not treat this as a universal formula**:

- Acceptable error depends on scale and domain requirements.
- `NaN` must be checked separately: any greater-than/less-than comparison with NaN is false.
- `Infinity` and overflow can make tolerance meaningless.
- Summing many numbers with large magnitude differences can lose small terms.
- If the problem requires **exact literal arithmetic with no error**, change the numeric type/algorithm rather than arbitrarily widening tolerance.

An exact associativity law test using `Double.equals` will **catch** the counterexample above. Yet you should not necessarily treat `Double::sum` as "completely useless": the JDK provides double aggregations with documented precision/value contracts, and they are useful when the business domain accepts floating-point error.

### 10.2. BigDecimal and MathContext

`BigDecimal` is immutable. `BigDecimal::add` does not round if no MathContext is passed, making it suitable for certain aggregations requiring decimal precision.

~~~java
BigDecimal total = Stream.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"))
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
~~~

However, when adding with a **precision-limiting MathContext** or rounding at each step, parenthesization order can affect the result. Law tests must match the exact rounding configuration used in production.

**Be careful with `BigDecimal.equals`:** for example, `new BigDecimal("1.0")` and `new BigDecimal("1.00")` differ under `equals` because of different scale, even though they are equal under `compareTo` by numeric value. Tests must choose the equivalence relation matching the contract.

## 11. Monoid: a useful mental model

A **monoid** is a set of values with:

1. An associative combination operation.
2. A two-sided identity element.

Many reduce operations fit this model:

| Value | Combination operation | Identity |
| --- | --- | --- |
| Integer under wraparound sum | `Integer::sum` | 0 |
| Integer under wraparound product | `(a,b) -> a*b` | 1 |
| String | `String::concat` | "" |
| Boolean | AND | true |
| Boolean | OR | false |
| Immutable set (by element set) | Union creating a new set | Empty set |
| BigInteger | `BigInteger::add` | BigInteger.ZERO |

You do not need to know the term monoid to write Java, but it gives a concise question: **"Can I merge partial results under any parenthesization and still get the right answer?"**

**Do not equate monoid with commutativity.** String concatenation is an example that is associative with an identity, yet not commutative.

## 12. Complete Java 17 law-testing program

The following program:

- Checks identity and associativity of **Integer::sum** on boundary values and **1,000 random triples** with a fixed seed.
- Checks identity/associativity of String concatenation on all triples from a four-string sample set.
- Checks compatibility of the three-argument reduce computing total String length across multiple subtotals.
- Compares sequential/parallel totals per contract.
- Verifies empty-source results and string concatenation with encounter order.
- Demonstrates **counterexamples** for subtraction, a wrong combiner, and non-associative double addition.
- Does not run the dangerous mutable-identity reduce pattern.

Create the file **ReductionLawDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Random;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ReductionLawDemo {
    static <T> void checkIdentity(
            T identity, BinaryOperator<T> operation, T x) {
        T left = operation.apply(identity, x);
        T right = operation.apply(x, identity);
        if (!Objects.equals(left, x)
                || !Objects.equals(right, x)) {
            throw new AssertionError(
                    "Identity failed for " + x);
        }
    }

    static <T> void checkAssociative(
            BinaryOperator<T> operation,
            T a, T b, T c) {
        T left = operation.apply(
                operation.apply(a, b), c);
        T right = operation.apply(
                a, operation.apply(b, c));
        if (!Objects.equals(left, right)) {
            throw new AssertionError(
                    "Associativity failed: " + a + ","
                            + b + "," + c);
        }
    }

    static <U, T> void checkCompatibility(
            U identity,
            BiFunction<U, T, U> accumulator,
            BinaryOperator<U> combiner,
            U partial, T item) {
        U left = combiner.apply(
                partial,
                accumulator.apply(identity, item));
        U right = accumulator.apply(partial, item);
        if (!Objects.equals(left, right)) {
            throw new AssertionError(
                    "Compatibility failed");
        }
    }

    public static void main(String[] args) {
        BinaryOperator<Integer> addition = Integer::sum;
        int[] edgeCases = {
                Integer.MIN_VALUE, -5, -1, 0, 1, 5,
                Integer.MAX_VALUE
        };

        for (int n : edgeCases) {
            checkIdentity(0, addition, n);
        }

        Random random = new Random(0x5EED);
        int intTriples = 1000;

        for (int i = 0; i < intTriples; i++) {
            int a = random.nextInt();
            int b = random.nextInt();
            int c = random.nextInt();
            checkAssociative(addition, a, b, c);
        }
        System.out.println("int law cases: " + intTriples);

        BinaryOperator<String> concat = String::concat;
        List<String> pieces =
                List.of("", "A", "BC", "xyz");
        int stringTriples = 0;

        for (String a : pieces) {
            checkIdentity("", concat, a);
            for (String b : pieces) {
                for (String c : pieces) {
                    checkAssociative(concat, a, b, c);
                    stringTriples++;
                }
            }
        }
        System.out.println(
                "string law cases: " + stringTriples);

        BiFunction<Integer, String, Integer> length =
                (sum, word) -> sum + word.length();
        BinaryOperator<Integer> combiner = Integer::sum;
        List<Integer> partials = List.of(0, 3, 7);
        List<String> words = List.of("", "A", "Java", "Go");

        int compatCases = 0;
        for (int partial : partials) {
            for (String word : words) {
                checkCompatibility(
                        0, length, combiner, partial, word);
                compatCases++;
            }
        }
        System.out.println(
                "three-arg cases: " + compatCases);

        int sequential = IntStream.rangeClosed(1, 1000)
                .reduce(0, Integer::sum);
        int parallel = IntStream.rangeClosed(1, 1000)
                .parallel()
                .reduce(0, Integer::sum);
        if (sequential != 500_500 || parallel != 500_500) {
            throw new AssertionError("Wrong total");
        }
        System.out.println("parallel total: " + parallel);

        int totalLength = words.parallelStream()
                .reduce(0, length, combiner);
        if (totalLength != 7) {
            throw new AssertionError("Wrong word length");
        }
        System.out.println("parallel length: " + totalLength);

        String text = Stream.of("A", "B", "C")
                .parallel()
                .reduce("", String::concat);
        System.out.println("concat: " + text);

        Optional<Integer> noMax =
                Stream.<Integer>empty().reduce(Integer::max);
        System.out.println("max empty: " + noMax.isEmpty());

        BinaryOperator<Integer> subtract = (a, b) -> a - b;
        boolean subtractionIdentity =
                subtract.apply(0, 3) == 3
                        && subtract.apply(3, 0) == 3;
        boolean subtractionAssociative =
                subtract.apply(subtract.apply(10, 3), 2)
                        == subtract.apply(
                                10, subtract.apply(3, 2));
        System.out.println(
                "subtraction identity: " + subtractionIdentity);
        System.out.println(
                "subtraction associative: "
                        + subtractionAssociative);

        BinaryOperator<Integer> wrongCombiner = Integer::max;
        boolean badCompatibility =
                Objects.equals(
                        wrongCombiner.apply(
                                3, length.apply(0, "Java")),
                        length.apply(3, "Java"));
        System.out.println(
                "bad combiner compatible: " + badCompatibility);

        double a = 1e16, b = -1e16, c = 1.0;
        boolean doubleAssociative =
                Double.compare((a + b) + c,
                        a + (b + c)) == 0;
        System.out.println(
                "double associative: " + doubleAssociative);

        System.out.println("all law checks passed");
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac ReductionLawDemo.java
java ReductionLawDemo
~~~

**Exact output:**

~~~text
int law cases: 1000
string law cases: 64
three-arg cases: 12
parallel total: 500500
parallel length: 7
concat: ABC
max empty: true
subtraction identity: false
subtraction associative: false
bad combiner compatible: false
double associative: false
all law checks passed
~~~

### 12.1. Why does String have 64 triples?

The set `pieces` has four values. Each position a, b, c has four choices, so the total number of tested triples is:

\[
4 \times 4 \times 4 = 64
\]

For each triple, the test checks:

~~~text
concat(concat(a,b),c) == concat(a,concat(b,c))
~~~

Identity `""` is also checked on both sides for every value.

### 12.2. Why does Integer::sum pass random tests?

int additions use Java's 32-bit semantics. Even with overflow, regrouping additions **does not change the 32-bit remainder**. Thus `Integer::sum` is associative over the int range under Java semantics.

However, if business rules require a mathematical sum exceeding `Integer.MAX_VALUE`, a sufficiently wide type must be chosen; the property tests above only verify the **laws of the chosen operation**, not domain bounds.

### 12.3. Why does compatibility have 12 cases?

There are three subtotals: 0, 3, 7. There are four Strings: "", "A", "Java", "Go". Each pair `(partial, word)` is checked once, giving **3 × 4 = 12** cases.

`length` adds the String length to the subtotal and `combiner` sums two subtotals. The two operations are compatible via identity 0, so all tests pass.

### 12.4. Why are subtraction identity and associative both false?

For x=3, `0-3=-3` differs from 3, so 0 is not a two-sided identity. For triple (10,3,2), the two parenthesizations yield 5 and 9. Thus subtraction does not satisfy the desired parallel reduce laws.

### 12.5. Why is bad combiner compatible false?

With subtotal=3 and word="Java", the accumulator adds 4. Yet combiner `max` only picks max(3,4)=4, which differs from `3+4=7`. Even though max alone is associative, you cannot replace the sum combiner with max when the accumulator still sums.

### 12.6. Why is double associative false?

The number 1e16 is too large relative to 1.0 for `-1e16 + 1.0` to retain the 1.0 part under double precision. The two parenthesization orders produce 1.0 and 0.0, so comparison via `Double.compare` yields false.

### 12.7. Why does max on an empty stream not exist?

The overload `reduce(BinaryOperator)` returns Optional. When there is no identity and the source is empty, the result is `Optional.empty()`. This avoids having to pick an arbitrary sentinel for the maximum result.

## 13. Designing comprehensive tests by bug category

An effective QA strategy has three layers:

| Layer | Goal | Example |
| --- | --- | --- |
| **Unit laws** | Left/right identity and associativity | `e⊕x=x⊕e=x`; two parenthesizations |
| **Composition laws** | Compatibility of three-arg reduce | `combine(u,acc(e,t)) == acc(u,t)` |
| **End-to-end** | Semantics on pipeline and domain | `parallel == sequential` under valid conditions; no business overflow |

Additional scope tests:

- **Empty source**: identity or Optional.empty per contract.
- **Single element**: result equals the element or accumulator(identity, t).
- **Two, three, many elements**: test different partitions.
- **Boundary/negative/0**: avoid assuming all data is positive.
- **Data formats**: empty String, Unicode, null if the API allows it.
- **Parallel**: run with larger data and varied splits without relying on a specific scheduler.
- **Non-interference**: the source is not modified by behavioral parameters.
- **Mutable identity**: eliminate by design, not just "race testing".
- **Precision error**: floating-point and rounding have their own evaluation criteria.
- **Domain bugs**: valid operation yet insufficient numeric range, or algorithm does not express the business rule.

### 13.1. Do not "prove" with stress tests

A race test run 10,000 times without failing **does not prove** `reduce(new ArrayList<>(), mutate, ...)` is safe. It may simply mean the partitioning/execution in the test environment did not expose the bug.

Conversely, when code review sees a mutable identity being mutated and a combiner assuming independent partial objects, we have a theoretical basis to fix the code **before** running the system.

### 13.2. Tests for a custom collector differ from tests for reduce

With `collect(supplier, accumulator, combiner)`, mutation **is allowed inside containers created by supplier**, provided it obeys the Collector laws. You need to test that supplier creates independent containers, combiner merges properly, results do not depend on partitioning, and the `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` characteristics if self-declared.

Do not take a set of `reduce` rules with a shared object identity and treat it as the model for `collect`; the nature of mutable reduction is different.

## 14. How to design a new reduction yourself

Before adding a reducer to an application, determine:

### Step 1 — Value domain

Is the result `int`, `long`, `BigInteger`, `BigDecimal`, `String`, an immutable record, or a mutable collection? Are nulls allowed? Are there value bounds?

**Do not choose a type just because the compiler accepts it.** If summing large currency amounts, `int` may not suffice.

### Step 2 — Combination operation

Write a `combine(a,b)` expression with business meaning. Is it associative? Form an argument, test three typical values and boundary values.

### Step 3 — Identity

Find e such that both sides hold. Do not use an arbitrary seed as identity. If there is no natural identity, consider the overload returning Optional.

### Step 4 — Accumulator and combiner (if three arguments)

Check compatibility:

~~~text
combine(u, accumulator(identity, element))
    == accumulator(u, element)
~~~

If it does not hold, fix the accumulator/combiner logic or choose another collection model.

### Step 5 — Ownership and side effects

Does it mutate a shared object? Does it modify the source? Does it read mutable shared state, time, or randomness? If so, switch to immutable values or separate data-writing responsibilities from the reduction.

### Step 6 — Tests and production evaluation

Write law tests, boundary tests, seeded random tests, sequential/parallel tests, and domain tests. Only after correctness is clear should you benchmark parallel performance.

## 15. Common mistakes

| Mistake | Why dangerous | Fix |
| --- | --- | --- |
| Testing only one sequential reduce result | Does not test splitting/merging | Test identity, associativity, and parallel |
| Testing identity on only one side | Misses subtraction with right identity | Test both `combine(e,x)` and `combine(x,e)` |
| Using seed 10 as addition identity | Seed may be applied in every branch | Use identity 0, add 10 after reduction |
| Using subtraction in parallel reduce | Not associative | Design a different algorithm matching the real meaning |
| Testing only combiner associativity in three-arg overload | May be incompatible with accumulator | Test compatibility |
| Assuming max with identity 0 is always right | Wrong when all numbers are negative | Use min-domain identity or Optional |
| Equating associative with commutative | String concat is associative but not commutative | Preserve encounter order when needed |
| Using mutable `ArrayList` as reduce identity | Aliasing and races in parallel | Use collect or immutable results |
| Using AtomicInteger/synchronized to "fix" reduce | Does not fix identity/alias laws | Fix the reduction model |
| Checking only `equals` on the same mutable object | Aliasing can hide bugs | Check ownership and value snapshots |
| Using `==` for approximate double | Rounding depends on order | Justified tolerance or exact numeric type |
| Seeing Integer::sum is associative and assuming sum won't overflow | Modulo law differs from business needs | Choose a numeric type with enough range |
| Using BigDecimal.equals when only numeric equality is wanted | Different scale can fail tests | Use compareTo when appropriate |
| Claiming passing random tests is proof of correctness | Tests only sample finitely | Combine law reasoning and testing |
| Forgetting empty/single-element tests | Misses wrong identity/sentinel | Mandatory boundary tests |
| Enabling parallel with stateful/side-effecting mapper | Results depend on scheduling | Stateless/non-interfering operations |

## 16. Practice exercises

### Exercise 1 — Identity of max

There is a Stream<Integer> that may contain negative numbers. Is it right to call `reduce(0, Integer::max)`?

**Answer:** not right across the full int domain. For a source containing only -5 and -2, the true max is -2, yet the result with identity 0 is 0. Use `reduce(Integer::max)` returning Optional<Integer>, or `reduce(Integer.MIN_VALUE, Integer::max)` if an identity valid for the entire domain is needed.

### Exercise 2 — Predict the subtraction counterexample

~~~java
BinaryOperator<Integer> subtract = (a, b) -> a - b;
~~~

Compute `(10 - 3) - 2` and `10 - (3 - 2)`.

**Answer:** 5 and 9. Subtraction is not associative and 0 is not a two-sided identity.

### Exercise 3 — Check string concatenation

For `String::concat` and identity `""`, check both sides and associativity on `"A", "B", "C"`. Is it commutative?

**Answer:** identity and associativity hold by content; not commutative because `"AB"` differs from `"BA"`. With an ordered stream and a contract-compliant reducer, merging by encounter order produces "ABC".

### Exercise 4 — Fix a wrong combiner

An API computes total String length using accumulator:

~~~java
(sum, word) -> sum + word.length()
~~~

but uses combiner `Integer::max`. Show that `u=3, t="Java"` breaks compatibility.

**Answer:** `max(3,4)=4` differs from `3+4=7`. Use `Integer::sum` as the combiner.

### Exercise 5 — Fix mutable reduce

Legacy code uses `reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)`. Why not use it on a parallel stream? Rewrite it with `collect`.

**Hint:**

~~~java
String result = words.parallelStream()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();
~~~

With an ordered source, the result preserves order per collector semantics when the contract is met. Supplier creates separate builders for mutable reduction instead of sharing a mutable identity in reduce.

### Exercise 6 — Check floating-point addition

Why does `(1e16 + (-1e16)) + 1.0` differ from `1e16 + ((-1e16) + 1.0)` in double?

**Answer:** due to precision loss when adding very large and very small numbers; rounding order yields 1.0 and 0.0. Do not apply raw mathematical associativity assumptions to double if tests require bitwise equality.

### Exercise 7 — Design a property test suite

Write a loop generating 1,000 int triples with a fixed seed, testing identity 0 and associativity of Integer::sum. Add checks for MIN/MAX values.

**Hint:** the program in section 12 can serve as a template. If switching to a custom reducer, include the three values and both sides in the failure message for easy reproduction.

### Exercise 8 — Business validation

A system sums revenue, where each transaction has an amount in the smallest currency unit. int addition satisfies the laws modulo 32-bit, yet the total can overflow. What tests are needed besides identity/associativity?

**Answer:** value-range/overflow tests and choosing a type (long, BigInteger, BigDecimal) matching unit/rounding rules. Algebraic correctness of reduce does not replace business correctness.

## 17. Key takeaways

A reliable reduction does not merely "produce the right result on a small list". For `Stream.reduce()`, verify:

- **Two-sided identity:** `combine(identity,x)==x` and `combine(x,identity)==x`.
- **Associativity:** `combine(combine(a,b),c)==combine(a,combine(b,c))`.
- **Compatibility** for the three-argument overload: `combine(u,acc(identity,t))==acc(u,t)`.
- **Stateless/non-interfering:** do not rely on shared mutable variables, do not mutate the source or a mutable identity.
- **Right type and domain:** handle overflow, precision error, null, currency rules, and equivalence relations.
- **Multi-layered testing:** boundary values, fixed-seed randomness, empty/single-element cases, and sequential/parallel.
- **Do not require commutativity when only associativity is needed**, but watch encounter order when the combination operation is not commutative.

Use **reduce** for contract-compliant value combination; use **collect** when mutable accumulation with clear container ownership is needed. Algebraic laws tell you **why a reduction is right**, while multi-layered testing catches implementation mistakes and business requirements beyond those laws.
