# Reduce Associativity and Correctness in Parallel Streams

> Covers the Java Stream API (Java 17+) and the rules that preserve reduction semantics when the JVM splits work in parallel. Scope is pure Java concurrency, without framework dependencies.

## 1. Why Does Parallelism Require an Associative Combining Operation?

`reduce` is a **reduction** operation: it traverses elements and combines them into a single value, such as a sum, a maximum value, a string, or a summary statistic. For example:

```java
int result = java.util.stream.Stream.of(1, 2, 3, 4)
        .reduce(0, Integer::sum); // 10
```

For a sequential stream, you can visualize the computation as:

```text
(((0 + 1) + 2) + 3) + 4 = 10
```

With `parallel()`, the data is partitioned into groups, each group produces a **subtotal**, and then a **combiner** merges the subtotals. For example:

```text
                  [1, 2, 3, 4]
                     /    \
                 [1, 2]  [3, 4]
                   |        |
                 (1+2)    (3+4)
                   \        /
                     3 + 7
                       |
                      10
```

The Stream API **does not promise** a fixed partitioning tree or the same execution schedule across runs. For multiple valid trees to produce the same result, the combining operation must satisfy **associativity**.

An operator `⊕` is associative if:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

This is the ability to **change parenthesization**. It is different from **commutativity**, which is the ability to **swap operand order**:

```text
Associativity: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
Commutativity: a ⊕ b = b ⊕ a
```

For example, string concatenation is associative:

```text
("a" + "b") + "c" = "abc"
"a" + ("b" + "c") = "abc"
```

However, string concatenation is **not commutative** because `"ab" != "ba"`. With an **ordered stream** (such as `List.stream()`), a valid string-concatenation reduction can run in parallel while still preserving **encounter order**. Do not confuse the order in which workers finish with the order of elements in the result. Conversely, calling `unordered()` means you no longer require encounter order to be preserved.

## 2. Subtraction Breaks Associativity

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

The two expressions yield different results; subtraction is not associative. Therefore, the following snippet **violates the parallel reduce contract**:

```java
int invalid = java.util.stream.Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

With the same data, we can visualize two ways of combining:

```text
Sequential: (((0 - 1) - 2) - 3) - 4 = -10

Partitioning: [1, 2] and [3, 4]
    left part  = (0 - 1) - 2 = -3
    right part = (0 - 3) - 4 = -7
    combined   = -3 - (-7)  = 4
```

Do **not** claim that every Java run will produce `4` or `-10`: the partitioning result is not part of the public contract. The two calculations above are independent proof that parenthesization can change the meaning.

Write the business operation properly: if the goal is `start - sum(items)`, compute `sum = items.parallelStream().reduce(0, Integer::sum)`, and then compute `start - sum` **once**, instead of using subtraction as the accumulator.

## 3. The Three Overloads of Stream.reduce

### 3.1. `Optional<T> reduce(BinaryOperator<T> accumulator)`

There is no explicit `identity` value. If the stream is empty, it returns `Optional.empty()`; if non-empty, the accumulator combines elements and must be **associative, stateless, and non-interfering**:

```java
java.util.Optional<Integer> largest =
        java.util.stream.Stream.of(4, 8, 3)
                .parallel()
                .reduce(Integer::max); // Optional[8]
```

`Integer::max` is associative. Avoid calling `get()` directly when the source can be empty; use `orElse` or `orElseThrow` depending on business logic.

### 3.2. `T reduce(T identity, BinaryOperator<T> accumulator)`

```java
int sum = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum); // 6
```

Requirements:

1. **Neutral identity**: for all `t`, `accumulator(identity, t) == t` according to the value semantics to preserve. In reduction design, `op(t, identity) = t` is also typically required for every subtotal value that may occur.
2. **Associativity**: `op(op(a,b),c) = op(a,op(b,c))`.
3. **Stateless/non-interfering**: does not depend on shared mutable state and does not modify the stream source while the stream is executing.

Common identity table:

| Combining operation | Identity | Reason |
|---|---|---|
| Integer addition | `0` | `0 + x = x` |
| Integer multiplication | `1` | `1 * x = x` |
| String concatenation | `""` | `"" + s = s` |
| Boolean AND | `true` | `true && b = b` |
| Boolean OR | `false` | `false || b = b` |
| `max` for all `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| `min` for all `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

**Pitfall: using a seed that is not the identity.** Incorrect example:

```java
int broken = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum); // WRONG: 10 is not the identity for addition
```

Sequentially: `10 + 1 + 2 + 3 = 16`. If three independent partitions each use `10`, combining them could yield `(10+1) + (10+2) + (10+3) = 36`. The number `36` is an illustrative possibility, **not stdout guaranteed by the JVM**. If you want to add the constant `10` exactly once:

```java
int correct = 10 + java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum); // 16
```

Choosing an identity that matches the data domain is critical: `0` is not an identity for `max` if negative numbers are present. If the stream can be empty and "no max" differs from the minimum possible value, using `Optional` is a more appropriate representation.

### 3.3. `<U> U reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)`

Use the three-argument overload when the element type `T` and the result type `U` differ. For example, summing the lengths of strings:

```java
int totalLength = java.util.stream.Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(
                0,
                (current, word) -> current + word.length(),
                Integer::sum
        ); // 6
```

- **Identity**: neutral intermediate result `0`.
- **Accumulator**: `a(u,t) = u + length(t)`, updating a subtotal with one input element.
- **Combiner**: `c(u,v) = u + v`, merging two subtotals of the same type `U`.

In addition to the identity and associativity of the combiner, the API requires **compatibility** between the accumulator and the combiner:

```text
c(identity, u) = u
c(c(x, y), z) = c(x, c(y, z))
c(u, a(identity, t)) = a(u, t)
```

The last equation states that "accumulating element `t` into subtotal `u`" must be equivalent to "accumulating `t` in a separate branch and then combining it with `u`". **Checking that the combiner is associative alone is not enough.**

Incorrect example:

```java
// WRONG: accumulator adds, but combiner subtracts.
int broken = java.util.stream.Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left - right);
```

In a sequential pipeline, the combiner might not be called at all, making this bug hard to spot in single-threaded tests. The fix is `Integer::sum`, or redesigning both the accumulator and combiner around the same associative operation.

## 4. A Standalone Runnable Java 17+ Example

Create the file **`ReduceAssociativityDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class ReduceAssociativityDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        int sum = numbers.parallelStream().reduce(0, Integer::sum);
        String letters = List.of("a", "b", "c", "d")
                .parallelStream().reduce("", String::concat);
        int lengths = List.of("a", "bb", "ccc")
                .parallelStream()
                .reduce(0, (n, s) -> n + s.length(), Integer::sum);

        Optional<Integer> empty = List.<Integer>of()
                .parallelStream().reduce(Integer::sum);

        // Illustrate two combining trees without forcing the JVM to pick a specific one.
        int sequentialSubtraction = numbers.stream()
                .reduce(0, (a, b) -> a - b);
        int left = (0 - 1) - 2;
        int right = (0 - 3) - 4;
        int groupedSubtraction = left - right;

        System.out.println("sum=" + sum);
        System.out.println("letters=" + letters);
        System.out.println("lengths=" + lengths);
        System.out.println("empty=" + empty);
        System.out.println("sequentialSubtraction=" + sequentialSubtraction);
        System.out.println("groupedSubtraction=" + groupedSubtraction);
    }
}
```

Compile and run:

```bash
javac ReduceAssociativityDemo.java
java ReduceAssociativityDemo
```

Exact stdout:

```text
sum=10
letters=abcd
lengths=6
empty=Optional.empty
sequentialSubtraction=-10
groupedSubtraction=4
```

The results of the three valid reductions do not depend on the combining tree. The two subtraction lines demonstrate the difference **through explicit calculation**; the program does not expect any fixed result from parallel subtraction.

## 5. Associativity Is Different from Commutativity and Thread Safety

String concatenation like `String::concat` is associative but **not commutative**. When encounter order is preserved, `List.of("a","b","c").parallelStream().reduce("", String::concat)` must evaluate to `"abc"` regardless of worker scheduling. If you drop the ordering constraint with `unordered()`, a result that is only valid when the original order is preserved is no longer guaranteed.

At the same time, **thread-safe** does not mean **associative**. A lambda writing to a shared `AtomicInteger` might have no data race on the counter itself, but its logic depends on scheduling, the number of accumulator invocations, and state outside the pipeline, so it fails the stateless function requirement. `reduce` must compute its result from inputs and partial results, without relying on external side effects to "collect" data.

Four distinct questions for code review:

| Property | What must hold |
|---|---|
| Associativity | Re-parenthesizing subtotal combinations still yields the right result |
| Commutativity | Only needed if you actually allow reordering elements |
| Identity / compatibility | Independent branches, empty branches, and merging subtotals produce the same result |
| Stateless / non-interfering | Functions do not depend on shared mutable state and do not modify the source |

For streams declared unordered or collectors with special characteristics, read the contract of the specific operation rather than applying a single simplistic rule about ordering to every case.

## 6. Floating-Point Numbers and Overflow: Mathematical Operations May Not Match Java Semantics

In real arithmetic, addition is associative. With IEEE 754 `double`, each addition can round, so the combining tree affects the result.

Create the file **`FloatingPointGrouping.java`**:

```java
public class FloatingPointGrouping {
    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        System.out.println("left=" + ((a + b) + c));
        System.out.println("right=" + (a + (b + c)));
    }
}
```

Run:

```bash
javac FloatingPointGrouping.java
java FloatingPointGrouping
```

Exact stdout:

```text
left=1.0
right=0.0
```

`b + c` loses the `1.0` due to rounding error near `-1.0e16`. Therefore, `reduce(0.0, Double::sum)` does not satisfy **bit-exact** associativity. `DoubleStream.sum()` may use a higher-precision summation algorithm than a manual `reduce`, but the result can still depend on summation order and rounding; applications must define a tolerance or use exact arithmetic if deterministic values are required.

For currency, consider integer minor units (e.g., cents) or exact `BigDecimal` addition, paying attention to scale and overflow. `BigDecimal.add` without a `MathContext` performs exact value addition; if rounding step by step with a `MathContext`, associativity may no longer hold. `BigDecimal.equals` also distinguishes scale; if you need to compare numeric values, consider `compareTo` according to your design.

For `int` and `long`, addition wraps around under modulo arithmetic; that addition is still associative **on the bits of Java integer types**, but it can be wrong for the application's mathematical sum. `Math.addExact` can throw `ArithmeticException` in one combining tree whose intermediate sum overflows even when another tree does not, so it does not automatically guarantee that a reduction can be arbitrarily regrouped.

## 7. Do Not Use a Mutable Container as the Identity of reduce

Dangerous mistake:

```java
// WRONG illustration, assuming words is List<String>.
List<String> result = words.parallelStream()
    .reduce(new ArrayList<>(),
            (list, word) -> { list.add(word); return list; },
            (left, right) -> { left.addAll(right); return left; });
```

This snippet requires importing `java.util.List` and `java.util.ArrayList` if placed in a Java class. Because the exact same `new ArrayList<>()` object is passed as the identity, branches can mutate **the same object**; the combiner might even merge a list into itself. This violates the value contract and can cause data races, duplicated elements, or runtime errors.

For mutable aggregation, use **`collect`**:

```java
// Correct illustration when words is List<String>.
List<String> result = words.parallelStream()
        .collect(java.util.stream.Collectors.toList());
```

Or:

```java
List<String> result = words.parallelStream()
        .collect(java.util.ArrayList::new,
                 java.util.List::add,
                 java.util.List::addAll);
```

`collect` uses a supplier that creates a **separate container for each accumulation partition**, an accumulator that adds each element to a container, and a combiner that merges containers; both snippets above are fragments requiring the `words` variable and `import java.util.List` in the surrounding program. With an ordered stream and a compatible collector, encounter order is preserved. The exact concrete type and mutability of the list returned by `Collectors.toList()` are not guaranteed by the API; avoid depending on implementation details.

If you need an immutable result or an operation that computes a **new value** on each step, `reduce` is the natural choice. If you need to build a list/map/set by mutating a container, generally use `collect`.

## 8. Checking the Laws Before Benchmarking Parallel Execution

Do not just compare sequential and parallel results on a single input set: contract violations may happen not to show up if the runtime splits into few branches or uses a similar schedule.

You can check the laws on a representative data domain:

```text
identity:
    op(identity, x) == x
    op(x, identity) == x

associativity:
    op(op(a,b),c) == op(a,op(b,c))

3-argument reduce:
    combine(identity, u) == u
    combine(combine(x,y),z) == combine(x,combine(y,z))
    combine(u, accumulate(identity,t)) == accumulate(u,t)

state:
    same input => same result; no reading/writing shared mutable state
```

Simple test example in **Java 17+**. Create the file **`ReduceLawsCheck.java`**:

```java
import java.util.function.BinaryOperator;

public class ReduceLawsCheck {
    static void test(BinaryOperator<Integer> op, int identity) {
        int[] values = {-3, -1, 0, 1, 2, 7};

        for (int x : values) {
            if (op.apply(identity, x) != x || op.apply(x, identity) != x) {
                throw new AssertionError("identity failed: " + x);
            }
        }
        for (int a : values) {
            for (int b : values) {
                for (int c : values) {
                    int left = op.apply(op.apply(a, b), c);
                    int right = op.apply(a, op.apply(b, c));
                    if (left != right) {
                        throw new AssertionError(
                                "associativity failed: " + a + "," + b + "," + c);
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        test(Integer::sum, 0);
        test(Integer::max, Integer.MIN_VALUE);
        System.out.println("reduction laws: PASS");
    }
}
```

Run:

```bash
javac ReduceLawsCheck.java
java ReduceLawsCheck
```

Exact stdout:

```text
reduction laws: PASS
```

This is only a **sample-set test**, not a proof for all inputs and all operators. Add property-based testing, empty inputs, negative numbers, extreme values, duplicates, overflow, and values with different scales/precisions. For the three-argument overload, test **compatibility** across subtotals that can actually be produced. Choose the right result comparison for your business logic: `equals` for objects with a suitable contract, an intentional tolerance for floating-point numbers, or numeric comparison for decimals.

### QA Checklist When Reviewing `parallelStream().reduce(...)`

1. Identify the value/meaning to compute and whether the stream has encounter order.
2. Verify the identity (including empty streams and per-partition subtotals).
3. Prove associativity of the accumulator or combiner under **Java type semantics**, not just symbolic notation on paper.
4. For the three-argument overload, verify the compatibility law between accumulator and combiner.
5. Ensure lambdas are stateless, non-interfering, and do not mutate a shared identity.
6. Review policies for overflow, floating-point error, ordering, and equality.
7. Test sequential and parallel execution across various sizes and datasets before benchmarking throughput/latency. `parallel()` is not faster by default due to splitting, scheduling, and merging overhead.

## 9. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| `reduce(10, Integer::sum)` to add constant 10 | The constant can be applied per branch | `10 + reduce(0, Integer::sum)` |
| `reduce(0, (a,b)->a-b)` | Subtraction is not associative | Reduce with a suitable operation, then apply subtraction once |
| Accumulator adds, combiner subtracts | Violates compatibility | Use a combiner matching the subtotal semantics |
| Shared mutable `ArrayList` as identity | Branches can mutate the same object concurrently | `collect` with a supplier |
| Updating an external `AtomicInteger` | State depends on scheduling, breaking purity | Fold the result into the reduction |
| Concatenating strings after dropping encounter order | Result can reorder strings | Keep an ordered source and ordered operations |
| Expecting bit-identical `double` sums | Rounding is not associative | Accept a tolerance or use exact representation |
| Using `Integer::sum` and ignoring overflow | Valid modulo arithmetic, wrong business total | Use an appropriate numeric domain or control overflow |
| Testing only sequentially | Does not exercise combining trees/combiner | Verify laws and test on parallel streams |
| Measuring runtime only | Can be fast yet produce wrong results | Lock down correctness before performance |

## Authoritative References

- [Oracle Java 21 — Stream API, reduce](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): contracts for identity, associativity, non-interference, statelessness, and compatibility.
- [Oracle Java 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): explanation of reduction and parallelizable aggregation.
- [Oracle Java 21 — Collector API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html): rules for mutable reduction.
- [Oracle Java 21 — DoubleStream.sum](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/DoubleStream.html#sum()): floating-point precision and summation order dependence.

**Key takeaway:** `parallel()` changes how data is split and combined. `reduce` results are reliable only when the combining operation is **associative**, the identity is **neutral**, three-argument overloads are **compatible**, lambdas are **stateless/non-interfering**, and actual semantics (ordering, overflow, floating-point error) match business requirements.
