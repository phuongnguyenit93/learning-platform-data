# Combining Infinite Sources with limit, takeWhile, and Short-Circuiting Operations

An **infinite stream** can keep generating elements without a natural endpoint. The Java Stream API still allows processing such sources thanks to **lazy evaluation**: the pipeline only requests elements when needed, and certain operations can stop requesting additional data once enough information has been obtained.

This lesson belongs to the **Sequences and Infinite Streams** chapter of the **JAVA_STREAM_API** module. This is a key application of the declarative data processing model with `filter`, `map`, `reduce`, and `collect`: generate a sequence according to a rule, limit it or define a stopping condition, and then obtain a finite result. At the same time, you must understand the impact of stateful operations, parallel processing, resource limits, and the possibility of **non-termination** when choosing the wrong pipeline order.

## 1. How Do Infinite Sources Actually Work?

In Java, `Stream.iterate` and `Stream.generate` are commonly used to describe sources capable of generating unbounded elements:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

// The sequence 1, 2, 3, 4, ... (conceptually has no endpoint).
IntStream naturals = IntStream.iterate(1, n -> n + 1);

// Each time an element is requested, a value is pulled from the Supplier.
Stream<String> repeated = Stream.generate(() -> "tick");
```

The calls above **do not pre-allocate an infinite set of elements in memory**. They set up a source that is traversed on demand. When a terminal operation is invoked, elements are computed and passed through intermediate steps.

`Stream.iterate(seed, next)` (Java 8+) creates a **sequential stream with an encounter order**, starting from `seed`, and applies `next` to compute the subsequent element. `Stream.generate(supplier)` (Java 8+) creates a **sequential stream with no guaranteed encounter order**, calling `supplier` to supply elements on demand.

| Creation approach | Element generation rule | Ordering | Suitable cases |
| --- | --- | --- | --- |
| `IntStream.iterate(1, n -> n + 1)` | Each next element is based on the previous one | Has encounter order | Index sequences, ordinals, arithmetic progressions |
| `Stream.iterate(seed, next)` | Evolves state from the previous value | Has encounter order | Date sequences, immutable states, geometric progressions |
| `Stream.generate(supplier)` | Supplier is called whenever an element is needed | No guaranteed encounter order | Independent sample generation, test data generation |
| `Stream.iterate(seed, hasNext, next)` | Only continues while `hasNext` is true | Has encounter order | Sequences with a stopping condition right at the source (Java 9+) |

> **"Infinite" here describes how the source is constructed, not a claim that a real program runs forever.** For example, `IntStream.iterate(1, n -> n + 1)` uses `int`, so if traversed too far the integer can overflow. When you need a large sequence that truly keeps growing, consider `BigInteger` or an appropriate data domain.

## 2. limit(n): Taking at Most n Elements

`limit(long maxSize)` is a **short-circuiting intermediate operation**. It allows at most `maxSize` elements to proceed past the point where it is placed in the pipeline.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

Sequence of steps:

1. `iterate` describes a source capable of generating consecutive numbers.
2. `limit(5)` lets only five numbers pass through and does not request the sixth.
3. `boxed()` converts primitive `int` values to `Integer`.
4. `collect` consumes those five values to build a `List`.

`limit(0)` creates a pipeline with no output elements; `limit` with a negative argument throws `IllegalArgumentException`. The operation only limits **the number of elements passing through it**, without directly placing a cap on how many times preceding steps are evaluated.

### The Position of limit Changes the Result

Suppose we want the first three even numbers from the natural numbers:

```java
List<Integer> firstThreeEven = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .boxed()
    .collect(Collectors.toList());
// [2, 4, 6]
```

The pipeline must examine `1` through `6` in sequence to find three even numbers. If you move `limit` earlier:

```java
List<Integer> evenAmongFirstThree = IntStream.iterate(1, n -> n + 1)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList());
// [2]
```

The second expression only inspects **the first three numbers from the source**, and then filters. Both terminate, but they answer two different questions.

### Even with limit, It Can Still Fail to Terminate

`limit(3)` does not guarantee completion if **the preceding step never supplies three elements**:

```java
// DO NOT RUN: there are no negative numbers in this positive BigInteger sequence.
// Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE))
//     .filter(n -> n.signum() < 0)
//     .limit(3)
//     .collect(Collectors.toList());
```

`filter` here will keep searching infinitely because no element gets through. This is the most important rule when combining an infinite source with intermediate operations: **you must ensure there is a path to termination, including enough matching elements or another termination condition**.

## 3. takeWhile(predicate): Taking the Contiguous Prefix Matching a Condition

`takeWhile` was added in **Java 9**. On a Stream **with an encounter order**, it yields the *longest contiguous prefix* of elements satisfying the predicate; as soon as it encounters the first element that fails, it stops taking further elements from the sequence under normal sequential traversal.

```java
import java.util.stream.IntStream;

List<Integer> belowSix = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n < 6)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5]
```

If `predicate` is false right at the first element, the result is empty. If `predicate` is always true on an infinite source, `takeWhile` cannot create a stopping point for a terminal operation that requires all elements.

### How Does takeWhile Differ from filter?

Given the finite sequence `[1, 2, 3, 4, 5, 6]`:

```java
List<Integer> prefix = IntStream.rangeClosed(1, 6)
    .takeWhile(n -> n % 2 != 0)
    .boxed()
    .collect(Collectors.toList());
// [1] because it stops when encountering 2.

List<Integer> odds = IntStream.rangeClosed(1, 6)
    .filter(n -> n % 2 != 0)
    .boxed()
    .collect(Collectors.toList());
// [1, 3, 5] because filter inspects the entire source.
```

| Operation | On an ordered source | Meaning of the condition |
| --- | --- | --- |
| `filter(p)` | Checks each element in the consumed source; discards non-matching elements | "Keep every element satisfying `p`" |
| `takeWhile(p)` | Keeps the contiguous prefix satisfying `p` and stops at the first failure | "Continue **as long as** `p` holds" |
| `limit(n)` | Keeps at most `n` elements at that position | "Take only the first `n` elements" |

Therefore, `takeWhile(n -> n < 100)` on a **monotonically increasing** sequence is a way to define a stopping threshold. If data fluctuates around the threshold, `takeWhile` stops at the **first threshold crossing**, even if valid values could appear later. To keep all values below the threshold, use `filter` along with an appropriate limiting condition.

### Using BigInteger to Avoid Overflow in Growing Sequences

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<BigInteger> powersOfTwo = Stream
    .iterate(BigInteger.ONE, value -> value.shiftLeft(1))
    .takeWhile(value -> value.compareTo(BigInteger.valueOf(100)) < 0)
    .collect(Collectors.toList());

System.out.println(powersOfTwo);
// [1, 2, 4, 8, 16, 32, 64]
```

Each time an element is generated, the value doubles the previous one. When the value reaches `128`, the predicate becomes false and the ordered pipeline stops. `BigInteger` avoids `int`/`long` overflow in this example, though you must still watch memory if the requested values or element counts become too large.

### Finite Source Using Three-Argument iterate

Java 9 also supports `Stream.iterate(seed, hasNext, next)` (and primitive Stream variants):

```java
List<Integer> values = IntStream
    .iterate(1, n -> n <= 5, n -> n + 1)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5]
```

The `hasNext` condition is checked before emitting the corresponding element. This expresses the stopping point directly at the source, which is useful when the generation rule itself has a bound. `takeWhile`, on the other hand, is useful when you want to **apply a stopping condition to an already constructed Stream**.

## 4. Short-Circuiting Terminal Operations

Beyond `limit` and `takeWhile` in the **intermediate** group, Java also has **short-circuiting terminal operations**: they can determine a result without examining the entire source.

| Terminal | When does it stop early? | On an infinite source |
| --- | --- | --- |
| `findFirst()` | Once the first element in encounter order (if any) is found | Can terminate quickly if a matching element appears. |
| `findAny()` | Once any element is found | Often suitable when order is not needed, especially with parallel streams. |
| `anyMatch(p)` | Encounters an element satisfying `p` | Returns `true` when witness is found; if none exists, may not stop. |
| `allMatch(p)` | Encounters an element **not** satisfying `p` | Returns `false` as soon as a counterexample is found; if all satisfy, may not stop. |
| `noneMatch(p)` | Encounters an element satisfying `p` | Returns `false` as soon as a counterexample is found; if none satisfy, may not stop. |

Examples:

```java
import java.util.stream.IntStream;

int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1);
// 7

boolean hasMultipleOfEleven = IntStream.iterate(1, n -> n + 1)
    .anyMatch(n -> n % 11 == 0);
// true: found 11.

boolean allLessThanFive = IntStream.iterate(1, n -> n + 1)
    .allMatch(n -> n < 5);
// false: encountered 5.

boolean noMultipleOfFour = IntStream.iterate(1, n -> n + 1)
    .noneMatch(n -> n % 4 == 0);
// false: encountered 4.
```

The examples above use sequential Streams to illustrate the number of elements inspected. When executing in parallel, multiple elements may be processed before the short-circuit signal halts the work.

### Why True Results Do Not Always Mean Termination?

Consider `Stream.generate(() -> 1).allMatch(n -> n == 1)`. Every element the program encounters equals `1`, yet on an infinite source there is never a point where the terminal can prove **all** remaining elements also satisfy it simply by exhausting the source. It has no stopping condition.

Similarly:

- `Stream.generate(() -> 1).anyMatch(n -> n == 2)` can run forever because it never encounters `2`.
- `Stream.generate(() -> 1).noneMatch(n -> n == 2)` can run forever because it cannot confirm there are no more elements.
- `Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE)).filter(n -> n.signum() < 0).findFirst()` has no matching element to return.

For an **empty** Stream, short-circuiting rules still hold: `anyMatch` returns `false`, while `allMatch` and `noneMatch` both return `true` without calling the predicate. This is a logical consequence of having no counterexample element.

## 5. Pipeline Order Determines Termination

An infinite source is generally safe to pass into a terminal operation needing all data **only after the pipeline has become finite**. However, you must also check steps placed **before** the limiting point.

| Pipeline (omitting imports) | Does it terminate? | Reason |
| --- | --- | --- |
| `IntStream.iterate(1, n -> n + 1).limit(10).sum()` | Yes | Only ten elements are requested. |
| `IntStream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0).limit(10).sum()` | Yes | The filter finds ten even numbers. |
| `IntStream.iterate(1, n -> n + 1).takeWhile(n -> n <= 10).sum()` | Yes | Condition becomes false at `11`. |
| `Stream.generate(() -> 1).filter(n -> n == 2).limit(3).count()` | Does not terminate under normal evaluation | Filter emits no elements, so `limit` never gets three elements. |
| `Stream.generate(() -> 1).distinct().limit(2).count()` | Does not terminate under normal evaluation | Only one distinct value exists, so a second value can never be found. |
| `IntStream.iterate(1, n -> n + 1).sorted().limit(3).boxed().collect(Collectors.toList())` | Does not terminate under normal evaluation | `sorted` needs to receive the entire source before emitting the first value. |
| `IntStream.iterate(1, n -> n + 1).limit(3).sorted().boxed().collect(Collectors.toList())` | Yes | `sorted` only has to sort the first three elements. |

> "Does not terminate" conclusions describe **semantics and normal evaluation**, excluding external interruption, resource exhaustion, or exceptions like overflow. Do not put pipelines marked as non-terminating into production applications just to test them.

`sorted` is a **stateful** intermediate operation that usually needs to buffer the entire input before emitting sorted elements. Therefore, a limit after `sorted` cannot rescue a pipeline using an infinite source. `distinct` is also stateful, though it can emit new values incrementally; it only terminates with `limit(k)` if it actually encounters `k` distinct values.

**Design rule:** place the limiting step before operations that must inspect all data, if business requirements allow. For example, "sort the first 100 elements" is `limit(100).sorted()`; whereas "get the 100 smallest elements of an arbitrary infinite sequence" is usually not a problem solvable by `sorted().limit(100)`.

## 6. Combining limit and takeWhile for Two Boundaries

In practice, you can impose **both a count limit and a value condition**, preventing excessive data collection if the sequence generation rule changes:

```java
List<Integer> bounded = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n <= 100)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
// [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

Here, `limit(10)` determines the stopping point first, so the pipeline does not need to wait for `takeWhile` to reach `101`. If you change `limit(10)` to `limit(200)`, `takeWhile` will stop at `101` and the result will contain 100 numbers.

You can swap the order of these two operations in some simple problems and keep the same result, but **never assume all intermediate operations are commutative**. With `filter`, `sorted`, `skip`, or conditions with side effects, both semantics and cost can change significantly.

Practical example: generate a sequence of times spaced 15 minutes apart, taking only slots before noon and at most six slots:

```java
import java.time.LocalTime;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<LocalTime> slots = Stream
    .iterate(LocalTime.of(9, 0), t -> t.plusMinutes(15))
    .takeWhile(t -> t.isBefore(LocalTime.NOON))
    .limit(6)
    .collect(Collectors.toList());

// [09:00, 09:15, 09:30, 09:45, 10:00, 10:15]
```

Note: `LocalTime.plusMinutes` wraps around to the start of the day after midnight. If you need a time model that does not wrap across multiple days, use `LocalDateTime` or `Instant` with an appropriate stopping condition; the example above only takes six morning slots before noon on the same session.

## 7. Encounter Order, Parallel Streams, and takeWhile

`Stream.iterate` returns a Stream with an encounter order, while `Stream.generate` does not guarantee an encounter order. This difference is especially important for `takeWhile`:

- On an **ordered** source, `takeWhile(p)` takes the longest contiguous prefix of elements satisfying `p`.
- On an **unordered** source, `takeWhile(p)` is allowed to select an arbitrary subset of elements satisfying `p`; there is no reliable notion of a "first prefix".
- On an ordered parallel stream, `limit`, `takeWhile`, and `findFirst` still honor the output ordering contract, but coordination and order-preservation overhead can be significant. Predicate execution may occur on additional elements before the entire task stops.

If the problem requires "stopping at the **first threshold crossing**" of a time-ordered series, **preserve encounter order**. Do not call `unordered()` merely hoping for speed, as that changes the meaning of `takeWhile`.

Conversely, `findAny` does not promise to return the first element. For a "find any matching element" problem, it can enable a more efficient parallel implementation than `findFirst`.

Do not use logging statements in `peek` or side effects inside `map` to conclude the exact number of times elements were evaluated. Java Streams are permitted to optimize, skip steps, or evaluate extra elements during parallel processing, as long as the result contract is upheld.

## 8. Resource Risks and How to Prevent Them

Laziness avoids **storing the entire source in memory**, but does not automatically protect a program from an infinitely running pipeline. A terminal operation needing all data, such as `collect(toList())`, `toArray()`, `reduce(...)`, or `sum()`, may never return if the input remains infinite.

Practical guidelines:

1. **Determine the stopping point before running:** bound quantity with `limit`, monotonic thresholds with `takeWhile`, or source conditions with `iterate(seed, hasNext, next)`.
2. **Inspect steps before the limit:** does `filter` actually yield enough results? Does `distinct` have enough distinct values? Is `sorted` placed before a limit?
3. **Do not confuse element limits with time limits:** `limit(10)` can still hang forever if the source blocks when fetching elements. For a real timeout, cancellation/control mechanisms at the appropriate layer are needed; `limit` does not provide a timeout by itself.
4. **Watch out for accumulating operations:** avoid collecting huge amounts of data into a `List`; you can use `forEach` with proper handling, but still need a stopping mechanism and side-effect management.
5. **Avoid numeric overflow and state wrap-around:** `int`, `long`, and `LocalTime` all have finite domains; a condition that looks certain to flip from true to false may fail to do so due to overflow or wrap-around.
6. **Consider parallelism carefully:** splitting a sequence whose generation depends on previous elements does not necessarily deliver good performance; `parallel()` does not guarantee speed and does not waive the requirement for lambdas free of shared state.
7. **Manage external resources:** `Stream.generate` with a supplier reading from network/files still needs resource-closing mechanisms; a finished terminal operation does not mean external resources are automatically released.

For pipelines that need to iterate over a sequence for multiple calculations, create a **new** Stream for each terminal operation. A Java Stream can only be consumed once.

## 9. Complete Runnable Example for Java 9+

The following program demonstrates three ways to produce finite results from infinite sources. Only JDK 9 or later is required, with no external libraries:

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class InfiniteStreamDemo {
    public static void main(String[] args) {
        List<Integer> evenNumbers = IntStream.iterate(1, n -> n + 1)
            .filter(n -> n % 2 == 0)
            .limit(5)
            .boxed()
            .collect(Collectors.toList());

        List<BigInteger> powersOfTwo = Stream
            .iterate(BigInteger.ONE, n -> n.shiftLeft(1))
            .takeWhile(n -> n.compareTo(BigInteger.valueOf(20)) < 0)
            .collect(Collectors.toList());

        boolean hasMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
            .anyMatch(n -> n % 7 == 0);

        System.out.println("First five evens: " + evenNumbers);
        System.out.println("Powers of two under 20: " + powersOfTwo);
        System.out.println("Has a multiple of 7: " + hasMultipleOfSeven);
    }
}
```

Output:

```text
First five evens: [2, 4, 6, 8, 10]
Powers of two under 20: [1, 2, 4, 8, 16]
Has a multiple of 7: true
```

In the example, `filter().limit(5)` needs to find five even numbers; `takeWhile` stops when the first value not less than 20 is `32`; `anyMatch` stops as soon as it sees the first multiple of 7.

## 10. Self-Check

**Question 1.** Predict the results of the two pipelines:

```java
// A
IntStream.iterate(1, n -> n + 1).limit(6)
    .filter(n -> n % 2 == 0).boxed()
    .collect(Collectors.toList());

// B
IntStream.iterate(1, n -> n + 1).filter(n -> n % 2 == 0)
    .limit(6).boxed().collect(Collectors.toList());
```

**Answer:** A is `[2, 4, 6]` because only the first six source values are filtered. B is `[2, 4, 6, 8, 10, 12]` because `limit(6)` only counts elements that have passed the filter.

**Question 2.** Does `Stream.generate(() -> 10).distinct().limit(2).collect(Collectors.toList())` terminate?

**Answer:** It does not terminate under normal evaluation: after the first `10`, `distinct` discards every subsequent `10`. `limit(2)` never receives two elements.

**Question 3.** On `[3, 4, 3, 2, 1]`, how does `takeWhile(n -> n >= 3)` differ from `filter(n -> n >= 3)`?

**Answer:** `takeWhile` yields `[3, 4, 3]`, stopping at `2`; `filter` also yields `[3, 4, 3]` on **this specific data**, but still checks `1`. Changing the sequence to `[3, 2, 4, 3, 1]` reveals the clear difference: `takeWhile` gives `[3]`, whereas `filter` gives `[3, 4, 3]`.

**Question 4.** Why doesn't `Stream.generate(() -> 1).allMatch(n -> n == 1)` return `true` after a few predicate calls?

**Answer:** No element refutes the condition, so `allMatch` does not have enough information to stop; meanwhile, the source has no natural end. To test a **finite sample**, use `limit(n)` before `allMatch`.

**Question 5.** To check whether there is a number divisible by 7 in the first 100 natural numbers, where should the limit be placed?

```java
boolean found = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .anyMatch(n -> n % 7 == 0);
// true
```

**Explanation:** `limit(100)` defines the set to inspect; `anyMatch` can stop early when `7` is found. If the requirement is to inspect all 100 elements unconditionally, use another terminal operation or computation suited to that goal instead of `anyMatch`.

## Key Takeaways

When working with infinite Streams in **JAVA_STREAM_API**, what matters is not only creating a source with `iterate` or `generate`, but also **proving the pipeline can terminate**. `limit` bounds the output element count; `takeWhile` (Java 9+) takes the contiguous matching prefix on an ordered source; `findFirst`, `findAny`, `anyMatch`, `allMatch`, and `noneMatch` can finish as soon as there is enough evidence. A `filter` that lets no elements through, `distinct` without enough new values, or `sorted` before a limit can cause a pipeline to run forever. Combine operations in the right order, manage resources, and preserve encounter-order semantics when exact stopping points are required.
