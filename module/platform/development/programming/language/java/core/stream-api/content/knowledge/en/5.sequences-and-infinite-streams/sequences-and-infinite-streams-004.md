# Creating Sequences with a Stopping Condition Using Three-Argument Stream.iterate

In the Java Stream API, `Stream.iterate(seed, hasNext, next)` generates a sequence of elements by **starting from an initial value**, **checking a condition allowing continuation**, and then **computing the next element**. This is a declarative way to express many loops with a termination condition without manually maintaining a result list. The three-argument method was added in **Java 9**.

This lesson belongs to the **Sequences and Infinite Streams** chapter of the **JAVA_STREAM_API** module. The goal is to combine this sequence-generating source with lazy pipelines such as `filter`, `map`, `reduce`, and `collect`; understand execution timing, state, resource costs, and why you should not default to converting sequentially dependent sequences into parallel streams. These fundamentals also prepare you for advanced topics like `Spliterator`, grouping, custom collectors, and Stream Gatherers.

## 1. Syntax and Meaning of the Three Arguments

Full declaration in `java.util.stream.Stream`:

```java
public static <T> Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next)
```

| Argument | Role | Example |
|---|---|---|
| `seed` | The first **candidate** element to be emitted | `0` |
| `hasNext` | Function receiving a candidate element, returning `true` if it should enter the Stream | `i -> i < 5` |
| `next` | Function computing the next candidate element from the current element | `i -> i + 1` |

`Predicate<T>` and `UnaryOperator<T>` are both functional interfaces in `java.util.function`. `Predicate` yields a boolean true/false answer; `UnaryOperator` is a function taking and returning **the same type T**. Therefore, `iterate` works well for number sequences, dates, and immutable algorithm states alike.

Its basic meaning resembles a `for` loop:

```java
// Loop form:
for (int i = 0; i < 5; i++) {
    System.out.println(i);
}

// Stream form, from Java 9:
Stream.iterate(0, i -> i < 5, i -> i + 1)
        .forEach(System.out::println);
```

Both snippets print `0`, `1`, `2`, `3`, `4` (one number per line), when run sequentially as shown.

### 1.1. Evaluation Order

Logically, elements are decided as follows:

```text
seed = 0
  |
  v
hasNext(0)? -- false --> END
  | true
  v
emit 0 --> next(0) = 1
                 |
                 v
             hasNext(1)? -- false --> END
                 | true
                 v
             emit 1 --> next(1) = 2 --> ...
```

With the call `Stream.iterate(0, i -> i < 5, i -> i + 1)`, we get the sequence `0, 1, 2, 3, 4`. The value `5` is used to **check the stopping condition**, but **does not appear in the result**.

Key properties to remember:

1. `hasNext` is checked **before** a candidate element is emitted. If `hasNext.test(seed)` is `false` on the very first check, the Stream is empty.
2. `next` describes how to compute the next candidate; emitted elements follow the result chain of repeatedly applying `next`.
3. Upon encountering the first candidate that does not satisfy `hasNext`, the sequence stops; that candidate is not emitted.
4. A Stream created from `iterate` has an **encounter order** and is initially **sequential**. It should not be treated as a collection of independent elements accessible at arbitrary positions.
5. Both `hasNext` and `next` should not interfere with the source or shared state variables (*non-interfering*) and should not rely on side effects (*stateless* in the sense of Stream lambda behavior).

The stopping condition depends on the **candidate value**, not on "running exactly N iterations" like a hidden counter. To get exactly N elements, design `seed`, `predicate`, and `next` so that the bound is explicitly represented.

## 2. Starting with Finite Integer Sequences

### 2.1. Exclusive Upper Bound

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class IterateNumbers {
    public static void main(String[] args) {
        List<Integer> numbers = Stream.iterate(
                        0,          // seed
                        i -> i < 6, // hasNext: checked before emitting
                        i -> i + 2) // next: increment by 2
                .collect(Collectors.toList());

        System.out.println(numbers); // [0, 2, 4]
    }
}
```

Here `6` is an **exclusive** bound: `0`, `2`, `4` are accepted, while `6` is checked and discarded. When writing `i -> i < endExclusive`, the name `endExclusive` clarifies the bound convention.

### 2.2. Inclusive Upper Bound

```java
List<Integer> numbers = Stream.iterate(
                1,
                i -> i <= 5, // includes 5
                i -> i + 1)
        .collect(Collectors.toList());

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

If `seed` is already outside the accepted domain:

```java
long count = Stream.iterate(
                10,
                i -> i < 5,
                i -> i + 1)
        .count();

System.out.println(count); // 0
```

In that case `hasNext(10)` is `false`, no elements are emitted, and `next` never needs to be called to produce sequence elements.

### 2.3. Decreasing Sequences and Arbitrary Step Sizes

```java
List<Integer> countdown = Stream.iterate(
                10,
                n -> n >= 0,
                n -> n - 3)
        .collect(Collectors.toList());

System.out.println(countdown); // [10, 7, 4, 1]
```

`next` does not have to add one. It can subtract a number, multiply by a constant, or compute a new state. However, **the predicate must match the direction of change**. For a decreasing sequence, a condition like `n -> n <= 10` will not guarantee termination because every smaller value still satisfies it.

## 3. Combining an iterate Source with a Lazy Pipeline

`iterate` creates the **source** of a pipeline. Intermediate operations such as `filter` and `map` do not need to create temporary lists; the pipeline only begins traversing when a terminal operation like `collect`, `sum`, `count`, or `findFirst` runs.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> cubesOfEvenNumbers = Stream.iterate(
                1,
                i -> i <= 10,
                i -> i + 1)
        .filter(i -> i % 2 == 0)
        .map(i -> i * i * i)
        .collect(Collectors.toList());

System.out.println(cubesOfEvenNumbers);
// [8, 64, 216, 512, 1000]
```

Here:

- `iterate` sequentially produces candidates from 1 to 10;
- `filter` keeps only even numbers;
- `map` cubes each retained number;
- `collect` is the terminal operation that creates the `List`.

**Where is the stopping condition placed?** The predicate in `iterate` checks each element **before** the `filter` and `map` steps. For instance, even though `filter` discards all odd numbers, `hasNext` still evaluates the odd numbers to know when to stop. Therefore, you cannot alter the sequence generation condition by expecting `filter` to "stop the source from generating further".

### 3.1. Terminal Operations That Can Short-Circuit

`findFirst`, `anyMatch`, and `limit` can let the pipeline avoid traversing the entire source:

```java
Optional<Integer> firstMultipleOfSeven =
        Stream.iterate(1, n -> n <= 1000, n -> n + 1)
                .filter(n -> n % 7 == 0)
                .findFirst();

System.out.println(firstMultipleOfSeven.orElse(-1)); // 7
```

This example requires `import java.util.Optional;`. Once the first matching element is found, processing can terminate early; the program does not need to collect all 1,000 elements. Do not attach side effects such as mandatory logging inside `hasNext` or `next` and assume an exact invocation count: the Stream API is permitted to optimize, and short-circuiting operators can change how many elements are actually requested.

## 4. Practical Example: Generating a Date Schedule with a Stopping Rule

Not all sequences are integers. `LocalDate` is an immutable value type whose `plusDays` method returns a new date object, making it a great fit for `iterate`.

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DailySchedule {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 11, 16);
        LocalDate endInclusive = LocalDate.of(2026, 11, 20);

        List<LocalDate> days = Stream.iterate(
                        start,
                        date -> !date.isAfter(endInclusive),
                        date -> date.plusDays(1))
                .collect(Collectors.toList());

        System.out.println(days);
        // [2026-11-16, 2026-11-17, 2026-11-18,
        //  2026-11-19, 2026-11-20]
    }
}
```

Explanation: start from `start`, continue while the candidate date is **not after** `endInclusive`, and advance by one day at each step. If `start` is after `endInclusive`, the result is an empty list.

Changing the step to `date.plusWeeks(1)` creates a weekly schedule. You can chain `filter(date -> date.getDayOfWeek().getValue() <= 5)` to keep only workdays from Monday to Friday. Note that `filter` removes weekend days from the **output**, while candidate traversal still advances day by day if `next` is `plusDays(1)`.

## 5. Comparing Three Ways to Generate Sequences

### 5.1. Two-Argument vs. Three-Argument iterate

`Stream.iterate(seed, next)` has existed since Java 8 and **creates an infinite source by itself**, unless the pipeline uses short-circuiting operators or encounters an error. `Stream.iterate(seed, hasNext, next)` from Java 9 adds a predicate to constrain element generation.

```java
// Java 8+: infinite source, limiting output with limit.
List<Integer> firstFiveA = Stream.iterate(0, i -> i + 1)
        .limit(5)
        .collect(Collectors.toList());

// Java 9+: finite source based on candidate value.
List<Integer> firstFiveB = Stream.iterate(
                0,
                i -> i < 5,
                i -> i + 1)
        .collect(Collectors.toList());

System.out.println(firstFiveA); // [0, 1, 2, 3, 4]
System.out.println(firstFiveB); // [0, 1, 2, 3, 4]
```

The two results above are identical, but their intents differ:

- `limit(5)` returns **at most 5 elements** regardless of their values; useful when you need a fixed count from an inherently endless source.
- `hasNext` stops at the **first candidate that fails the condition**; suitable when the value domain or business state determines the stopping point.

For example, with step `i -> i + 2`, `iterate(0, i -> i < 5, i -> i + 2)` yields `[0, 2, 4]`, whereas `iterate(0, i -> i + 2).limit(5)` yields `[0, 2, 4, 6, 8]`.

### 5.2. Three-Argument iterate vs. takeWhile

Java 9 also added `takeWhile` to take the contiguous prefix satisfying a predicate from an ordered Stream:

```java
// Checked right at the source.
Stream<Integer> a = Stream.iterate(
        0, i -> i < 5, i -> i + 1);

// Take prefix from a source created by two-argument iterate.
Stream<Integer> b = Stream.iterate(0, i -> i + 1)
        .takeWhile(i -> i < 5);
```

In this example, both yield `0, 1, 2, 3, 4`. However, `takeWhile` is an **intermediate operation**, works with other Stream sources, and operates according to encounter order when the source is ordered. `hasNext` belongs to the **source construction** of `iterate`.

In particular, `takeWhile` on an **unordered** Stream is not guaranteed to return a meaningful "prefix" like on an ordered list. Do not rely on deterministic results in that case.

### 5.3. iterate vs. IntStream.range / rangeClosed

When you only need consecutive integers, `IntStream.range` or `rangeClosed` is usually more concise and efficient:

```java
import java.util.stream.IntStream;

int sumExclusive = IntStream.range(1, 6).sum();       // 1+2+3+4+5 = 15
int sumInclusive = IntStream.rangeClosed(1, 5).sum(); // 15
```

| Problem | Preferred expression |
|---|---|
| Consecutive integers from 0 to 99 | `IntStream.range(0, 100)` |
| Consecutive integers from 1 to 100, including 100 | `IntStream.rangeClosed(1, 100)` |
| Numbers increasing by 3, stopping before 50 | `IntStream.iterate(0, n -> n < 50, n -> n + 3)` |
| Dates from date A to date B | `Stream.iterate(start, day -> !day.isAfter(end), day -> day.plusDays(1))` |
| Take the first 10 elements of an endless sequence | `Stream.iterate(seed, next).limit(10)` |

`IntStream.iterate(seed, hasNext, next)`, `LongStream.iterate(...)`, and `DoubleStream.iterate(...)` also have three-argument variants since Java 9. They use primitive types, avoiding boxing overhead of `Stream<Integer>`/`Stream<Long>`/`Stream<Double>` when processing large quantities.

```java
import java.util.stream.IntStream;

int squaresSum = IntStream.iterate(1, i -> i <= 4, i -> i + 1)
        .map(i -> i * i)
        .sum();

System.out.println(squaresSum); // 30 (1 + 4 + 9 + 16)
```

## 6. State Sequences: An Example That Cannot Be Replaced by a Simple range

A useful case for `iterate` is when each state holds multiple pieces of information, and the next state depends on the previous state. For example, we generate Fibonacci numbers under 100 using an **immutable state** consisting of two adjacent numbers:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FibonacciSequence {
    static final class Pair {
        final long current;
        final long next;

        Pair(long current, long next) {
            this.current = current;
            this.next = next;
        }
    }

    public static void main(String[] args) {
        List<Long> fibonacci = Stream.iterate(
                        new Pair(0, 1),
                        p -> p.current < 100,
                        p -> new Pair(p.next, p.current + p.next))
                .map(p -> p.current)
                .collect(Collectors.toList());

        System.out.println(fibonacci);
        // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
    }
}
```

`Pair` is a helper type created specifically for this example: each step produces a **new object** without mutating the old pair. `hasNext` checks `current < 100`, so the Fibonacci number 144 is not emitted. With this small limit, `long` addition does not overflow; for long Fibonacci sequences, consider `BigInteger` or a safe bound.

This example shows that `iterate` is not merely equivalent to a "counter-based `for` loop": it also expresses a **state transition rule**. However, if the algorithm needs to stop based on a global variable updated elsewhere, consider a loop or an appropriate event source rather than hiding shared state inside a lambda.

## 7. Wrong Stopping Condition: The Source Can Run Infinitely

The `hasNext` parameter **does not automatically guarantee** a finite Stream. If the predicate always returns `true` on the values produced by `next`, the Stream remains infinite.

```java
// DANGEROUS if using count()/collect(): condition is never false.
Stream<Integer> endless = Stream.iterate(
        0,
        i -> i >= 0,
        i -> i + 0);
```

The Stream above keeps repeating `0`. Calling `count()` or `collect(toList())` on this source may never terminate or may exhaust resources. For risky sequences, prove termination by verifying:

1. The **value domain** of the state;
2. Whether the **step progression** of `next` actually moves toward the bound;
3. Whether the **predicate** becomes `false` after finitely many steps;
4. Whether **overflow/underflow** or abnormal data breaks the logic.

### 7.1. Overflow Breaking the Stopping Condition

```java
// WRONG: every int is <= Integer.MAX_VALUE.
// After incrementing past MAX_VALUE, int overflows to MIN_VALUE,
// so this condition stays true forever.
Stream<Integer> broken = Stream.iterate(
        Integer.MAX_VALUE - 1,
        n -> n <= Integer.MAX_VALUE,
        n -> n + 1);
```

To generate a sequence smaller than `Integer.MAX_VALUE`, use `n -> n < Integer.MAX_VALUE`; or switch to `long` when addition risks exceeding the `int` domain. If you need an inclusive upper bound of `Integer.MAX_VALUE`, build a stopping step that does not rely on overflowing `int` addition, such as using `LongStream` with an appropriate `long` bound.

### 7.2. Null Data and Key Extraction Functions

With an object Stream, `hasNext` and `next` may have to handle a `null` value if the seed or transformation returns null. Do not write `value -> value.length() > 0` and pass a potentially null seed. You can design a "no-nulls" contract for the state or include an explicit condition like `value -> value != null`, depending on the problem.

`Stream.iterate` does not catch exceptions and turn them into a retry mechanism. If `hasNext`/`next` throws an exception while the pipeline runs, the terminal operation may fail. Pure lambdas, valid inputs, and controlled bounds help keep the pipeline easy to verify.

## 8. Performance, Ordering, and Parallel Processing

### 8.1. Laziness and Resources

Creating a `Stream.iterate(...)` source does not mean pre-allocating all elements in memory. Candidates are computed when the terminal operation actually needs to traverse them. However, if you use `collect(toList())` to collect **all** of a very large sequence, the resulting list still consumes corresponding memory; if the source is infinite, this operation is inappropriate.

A short-circuiting pipeline can bound processing:

```java
List<Integer> firstThree = Stream.iterate(
                1,
                n -> n < 1_000_000,
                n -> n + 1)
        .limit(3)
        .collect(Collectors.toList());

System.out.println(firstThree); // [1, 2, 3]
```

`limit(3)` caps the **number of output elements** requested. However, if there is a `filter` before `limit`, the pipeline may have to examine more candidates to find three elements passing the filter.

### 8.2. Splitting Work for Parallel Execution

An `iterate` sequence depends on the previous element to compute the next element. This differs from sources that can be arbitrarily split into independent segments, such as `IntStream.range` or arrays. Therefore, calling `parallel()` on an `iterate` sequence **does not automatically improve performance**: value generation may have to proceed partially sequentially while splitting/combining work still incurs overhead.

```java
long total = java.util.stream.LongStream
        .iterate(1L, n -> n <= 100_000L, n -> n + 1)
        .parallel()
        .sum();
```

The example above is valid API usage, but it does not prove parallel processing is fast. When summing a range of integers, `LongStream.rangeClosed(1, 100_000)` states the intent more clearly and is usually easier to split across workers.

Additionally, `forEach` on a parallel stream does not guarantee the invocation order of the action, even though an `iterate` source has an encounter order. If you need to observe elements in order, use `forEachOrdered` and accept potential extra overhead. Avoid writing to a shared `ArrayList` or mutating shared counters inside lambdas of a parallel pipeline.

## 9. Common Errors and How to Fix Them

| Error | Consequence | How to fix |
|---|---|---|
| Using `i <= end` when wanting to exclude `end` | One extra element | Write `i < end` and name it `endExclusive` |
| Using `i < end` when wanting to include `end` | Missing boundary element | Use `i <= end` if the update does not overflow |
| Seed does not satisfy `hasNext` | Empty Stream | Check empty-range handling rules; adjust seed if required |
| `next` does not progress toward the stopping bound | Pipeline may be infinite | Prove termination condition; control step value |
| Arithmetic on `int` exceeds value domain | Overflow, wrong sequence, or non-termination | Use `long`/`BigInteger`, enforce safe bounds |
| Calling `collect` on a sequence with no stopping point | May exhaust memory | Add a stopping condition or limit the output |
| Using `Stream<Integer>` for very large numeric computations without needing objects | Boxing/unboxing overhead | Consider `IntStream`, `LongStream` |
| Putting side effects in `hasNext`/`next` | Unpredictable under laziness or short-circuiting | Write pure functions, immutable state |
| Assuming `parallel()` always speeds things up | Can be slower | Benchmark with real data, prefer splittable sources when appropriate |

## 10. Self-Check Exercises

**Exercise 1.** Write a three-argument `IntStream.iterate` producing multiples of 4 between 4 and 20, **including 20**.

```java
int[] multiples = java.util.stream.IntStream
        .iterate(4, n -> n <= 20, n -> n + 4)
        .toArray();
// [4, 8, 12, 16, 20]
```

**Exercise 2.** With `Stream.iterate(8, n -> n > 0, n -> n / 2)` on integers, what sequence is emitted?

Answer: `[8, 4, 2, 1]`. The next candidate value is `0`, which does not satisfy `n > 0` and is therefore not emitted.

**Exercise 3.** Why does `Stream.iterate(1, n -> n < 20, n -> n * 2).count()` return `5`?

The elements are `1, 2, 4, 8, 16`; `32` does not pass the condition. The number `20` is not in the sequence.

**Exercise 4.** There is an inspection schedule every 7 days from 2026-12-01 through 2026-12-31. Choose the arguments for `iterate`.

```java
LocalDate start = LocalDate.of(2026, 12, 1);
LocalDate end = LocalDate.of(2026, 12, 31);

List<LocalDate> dates = Stream.iterate(
                start,
                d -> !d.isAfter(end),
                d -> d.plusDays(7))
        .collect(Collectors.toList());
// [2026-12-01, 2026-12-08, 2026-12-15, 2026-12-22, 2026-12-29]
```

The snippet uses imports `java.time.LocalDate`, `java.util.List`, `java.util.stream.Stream`, and `java.util.stream.Collectors`.

**Exercise 5.** When you only need consecutive integers from 1 to 1,000, should you start with `IntStream.rangeClosed(1, 1000)` or `Stream.iterate(1, n -> n <= 1000, n -> n + 1)`?

Answer: `IntStream.rangeClosed` directly describes a consecutive range, avoids boxing, and splits better under parallel processing. `iterate` is useful when the state transition rule is complex or depends on the previous value.

## 11. Rules to Remember

`Stream.iterate(seed, hasNext, next)` expresses a **stateful sequence**: check the candidate, emit the candidate if valid, then generate a new candidate. It provides a stopping condition right at the source since Java 9, combines with all Stream API transformation steps, and is especially useful for formula-based number sequences, dates, or immutable state. Choose bounds carefully, ensure the progression makes the condition eventually become false, avoid numeric overflow, and match resource handling to the terminal operation. For simple integer ranges, prefer `IntStream.range`/`rangeClosed`; when you need exactly N elements from a source without a clear value bound, consider `limit(N)`.
