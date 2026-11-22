# `Stream.iterate()` With or Without a Termination Condition in Java

## 1. Nature of `Stream.iterate`

`Stream.iterate` creates a **stream of elements following an iterative rule**: starting from an initial value (*seed*), and repeatedly applying a state-transition function to compute the next value. It is a *stream source*, commonly used when each subsequent element is derived from the previous one, such as number sequences, calendar dates, processing states, or simulating an incremental process.

Java supports two important overloads:

```java
// Available since Java 8: an inherently unbounded source.
static <T> Stream<T> iterate(T seed, UnaryOperator<T> next);

// Available since Java 9: adds a termination condition.
static <T> Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next);
```

The two signatures above are **simplified versions for learning**, belonging to `java.util.stream.Stream`; the actual methods in the JDK have their full API declarations. Meaning:

- `seed`: the first value to be considered.
- `next`: a function taking the current value to compute the next value; same type `T → T` (`UnaryOperator<T>`).
- `hasNext`: continuation condition, taking the current value and returning a `boolean` (`Predicate<? super T>`). It is only present in the three-argument overload.

**Without `hasNext`:** the source is an iterative process with no termination condition declared inside `iterate`. To obtain a finite result, a short-circuiting terminal operation or a limiting intermediate operation such as `limit` and `takeWhile` is typically used.

**With `hasNext`:** before emitting **a current value** into the stream, Java checks the condition. If `hasNext.test(current)` is `false`, that value **does not appear** and the iteration ends. If the condition is always true, the three-argument overload can still produce a non-terminating process.

`Stream.iterate` creates a **sequential stream with encounter order** by default. Emitted elements preserve the exact sequence computed from the seed according to the `next` rule, although processing may differ if the user explicitly switches to `parallel()`.

## 2. Two-Argument Overload: `Stream.iterate(seed, next)`

Example of generating integers from 1 upwards:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

Here:

1. `seed = 1`.
2. `next = n -> n + 1`.
3. The stream supplies 1, 2, 3, 4, 5, ... when requested downstream.
4. `limit(5)` takes **at most 5 elements**, allowing the terminal operation `toList()` to complete.

The snippet above is placed inside a method or `jshell`. If you omit `limit(5)` and call `toList()` on an unbounded stream source, the program has no normal termination point while processing the unbounded sequence; it may continue consuming CPU/memory or run into resource exhaustion.

**Important:** “unbounded” refers to **the number of iterations permitted by the API**, not that the computation always yields a mathematically infinite sequence of distinct values. With `int`, `n + 1` can **overflow** if run for too long; at that point values are still generated but no longer increase in the usual mathematical sense.

### Syntax using a method reference

If a transformation function of type `T → T` already exists, you can pass a method reference:

```java
static int stepByTwo(int current) {
    return current + 2;
}

// Placed in a method of a class that has stepByTwo:
List<Integer> values = Stream.iterate(0, MyClass::stepByTwo)
        .limit(4)
        .toList();
// values = [0, 2, 4, 6]
```

This is **illustrative code**: you need to replace `MyClass` with the name of the class declaring the `static stepByTwo` method, or use the lambda `n -> n + 2`. The goal is to understand that `next` can be a lambda or a method reference as long as it is compatible with `UnaryOperator<T>`.

## 3. Three-Argument Overload: `Stream.iterate(seed, hasNext, next)`

This syntax describes an iterative process closely resembling a traditional `for` loop:

```java
Stream.iterate(1, n -> n <= 5, n -> n + 1)
        .forEach(System.out::println);
```

Output:

```text
1
2
3
4
5
```

Conceptually equivalent to:

```java
for (int n = 1; n <= 5; n++) {
    System.out.println(n);
}
```

Interpretation:

- Check `1`: `1 <= 5` is true, emit 1.
- Compute the next element `2`: condition is true, emit 2.
- Continue up to `5`: condition is still true, emit 5.
- Check `6`: `6 <= 5` is false, **do not emit 6** and terminate.

This is an easy point of confusion: the `hasNext` condition applies to **the element about to be emitted**, not a “emit first, then check whether to stop” condition.

### The endpoint is *exclusive* if using `<`

```java
List<Integer> lessThanFive =
        Stream.iterate(1, n -> n < 5, n -> n + 1)
                .toList();

List<Integer> atMostFive =
        Stream.iterate(1, n -> n <= 5, n -> n + 1)
                .toList();

System.out.println(lessThanFive); // [1, 2, 3, 4]
System.out.println(atMostFive);   // [1, 2, 3, 4, 5]
```

The difference lies in `<` versus `<=`, just like a `for` loop. Decide the boundary rule **before writing** and check the start/end points.

### Seed does not satisfy the condition: empty stream

```java
List<Integer> empty =
        Stream.iterate(8, n -> n < 5, n -> n + 1)
                .toList();

System.out.println(empty); // []
```

`hasNext.test(8)` is false, so **even the seed does not appear**. A stream is never forced to contain one element just because a seed was passed in.

## 4. Complete Compilable and Runnable Java 17 Program

This example compares the ways of creating streams and shows why one overload typically needs a downstream limit, while the other has a termination condition at the source.

Create the file **`StreamIterateDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.Collectors;

public class StreamIterateDemo {
    record Day(int number, int balance) {}

    public static void main(String[] args) {
        // 1. 2-arg iterate: unbounded source, limit element count.
        List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .toList();
        System.out.println("Two args + limit: " + firstFive);

        // 2. 3-arg iterate: stop at condition n <= 5.
        List<Integer> bounded = Stream.iterate(
                        1,
                        n -> n <= 5,
                        n -> n + 1)
                .toList();
        System.out.println("Three args: " + bounded);

        // 3. Take only even numbers less than 10.
        List<Integer> evens = Stream.iterate(
                        0,
                        n -> n < 10,
                        n -> n + 2)
                .toList();
        System.out.println("Evens: " + evens);

        // 4. Seed does not satisfy condition => empty.
        List<Integer> empty = Stream.iterate(
                        8,
                        n -> n < 5,
                        n -> n + 1)
                .toList();
        System.out.println("Rejected seed: " + empty);

        // 5. 2-arg iterate + takeWhile (Java 9+).
        List<Integer> taken = Stream.iterate(1, n -> n + 1)
                .takeWhile(n -> n < 6)
                .toList();
        System.out.println("Take while: " + taken);

        // 6. limit by element count, not by value.
        List<Integer> multiples = Stream.iterate(3, n -> n + 3)
                .limit(4)
                .toList();
        System.out.println("Four multiples: " + multiples);

        // 7. Each element can be an immutable state.
        List<Day> days = Stream.iterate(
                        new Day(1, 100),
                        day -> day.number() <= 4,
                        day -> new Day(day.number() + 1,
                                       day.balance() + 25))
                .toList();
        String dailyReport = days.stream()
                .map(day -> "D" + day.number()
                            + "=" + day.balance())
                .collect(Collectors.joining(", "));
        System.out.println("Balances: " + dailyReport);

        // 8. Case where only primitive integers are needed.
        int sum = IntStream.iterate(1, n -> n <= 5, n -> n + 1)
                .sum();
        System.out.println("IntStream sum: " + sum);

        // 9. Filter first, stop by the number of elements to take.
        List<Integer> evenFour = Stream.iterate(0, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(4)
                .toList();
        System.out.println("First four even: " + evenFour);
    }
}
```

Compile and run:

```bash
javac --release 17 StreamIterateDemo.java
java StreamIterateDemo
```

**Expected exact stdout:**

```text
Two args + limit: [1, 2, 3, 4, 5]
Three args: [1, 2, 3, 4, 5]
Evens: [0, 2, 4, 6, 8]
Rejected seed: []
Take while: [1, 2, 3, 4, 5]
Four multiples: [3, 6, 9, 12]
Balances: D1=100, D2=125, D3=150, D4=175
IntStream sum: 15
First four even: [0, 2, 4, 6]
```

Comparing each result:

1. `firstFive` and `bounded` both produce [1, 2, 3, 4, 5] but **differ in termination mechanism**: `limit(5)` takes five elements; `n <= 5` controls which values are allowed to be emitted.
2. `evens` starts at 0 and increments by 2: 0, 2, 4, 6, 8. The next element 10 does not satisfy `n < 10`.
3. `empty` is an empty list because `8 < 5` is false right at the seed.
4. `takeWhile(n -> n < 6)` only emits the leading consecutive elements that still satisfy the condition, so it stops before 6.
5. `multiples` has four elements: 3, 6, 9, 12. `limit(4)` does not mean “stop when the value equals 4”.
6. `days` models four immutable states. Starting with `Day(1,100)`; after each step, day number +1 and balance +25. Terminates before day 5: D1=100, D2=125, D3=150, D4=175.
7. `IntStream.iterate(...).sum()` computes `1+2+3+4+5 = 15` without boxing each value into an `Integer`.
8. `evenFour` filters numbers divisible by 2 then applies `limit(4)`, so it takes 0, 2, 4, 6; the pipeline does not need to traverse forever.

The program uses sequential streams with encounter order, so `List.toString()` of the lists in the demo produces the order shown above. The `List` returned by `Stream.toList()` cannot be modified via `add`/`remove`; if you need a mutable list, explicitly create `new ArrayList<>(...)`.

## 5. Detailed Comparison of the Two Overloads

| Criterion | `iterate(seed, next)` | `iterate(seed, hasNext, next)` |
| --- | --- | --- |
| Available since | Java 8 | Java 9 |
| Number of parameters | 2 | 3 |
| Source has built-in termination condition | No | Yes |
| Seed can be rejected | No, because there is no `hasNext` | Yes, if `hasNext(seed)` is false |
| Common way to stop | `limit`, `takeWhile`, short-circuiting terminal operation | `hasNext`, can be combined with `limit` |
| Number of elements | Inherently unbounded | Depends on `hasNext` and `next` logic; may still not terminate |
| Example | `iterate(1, n -> n + 1).limit(5)` | `iterate(1, n -> n <= 5, n -> n + 1)` |
| Closest equivalent | Rule for generating a continuous sequence | `for(init; condition; update)` loop |
| Evaluation | Lazy when a terminal operation traverses | Lazy when a terminal operation traverses |

“Has a termination condition” here **does not guarantee** a finite stream: if `hasNext` is always true or `next` never moves the state out of the region satisfying the condition, the stream does not terminate. Example:

```java
// Wrong if expecting toList() to complete:
Stream.iterate(1, n -> n > 0, n -> n)
        .limit(5)
        .forEach(System.out::println); // Prints 1 five times and terminates.
```

The illustration only terminates thanks to `limit(5)`. If you **remove `limit(5)`** and use `toList()`, the predicate `n > 0` is always true because `next` returns `n` itself; the source has no stopping point. This example proves that the condition must be paired with a proper **state-progression rule**.

## 6. How Do `limit` and `takeWhile` Differ?

### `limit(n)` stops by count

`limit(n)` takes **at most n elements** from the stream. For a stream with encounter order, those are the **first n elements**.

```java
System.out.println(
    Stream.iterate(10, n -> n - 1)
            .limit(4)
            .toList()
); // [10, 9, 8, 7]
```

`limit(0)` produces an empty stream. `limit` with a negative number throws `IllegalArgumentException`. It does not care what values the elements have.

### `takeWhile(predicate)` stops by a condition on elements

`takeWhile` (Java 9+) takes the **longest contiguous prefix** of elements that still satisfy the predicate when the stream has encounter order. As soon as the first element that does not satisfy it is encountered, collecting the prefix stops.

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(values); // [1, 2, 3, 4]
```

**Do not confuse `takeWhile` with `filter`**:

- `filter(n -> n < 5)` discards elements that do not satisfy the predicate but does not terminate an infinite source on its own just because element 5 was encountered.
- `takeWhile(n -> n < 5)` stops the prefix at element 5, so it can terminate if a violating element appears after finitely many steps.

An example distinguishing them on a finite source:

```java
List<Integer> items = List.of(1, 2, 8, 3);

System.out.println(items.stream()
        .filter(n -> n < 5)
        .toList()); // [1, 2, 3]

System.out.println(items.stream()
        .takeWhile(n -> n < 5)
        .toList()); // [1, 2]
```

Because `takeWhile` does not collect matching elements after a non-matching element, it is not an arbitrary replacement for `filter`.

### Combining `filter` and `limit` on an infinite source

```java
List<Integer> firstThreeMultiplesOfSeven =
        Stream.iterate(1, n -> n + 1)
              .filter(n -> n % 7 == 0)
              .limit(3)
              .toList();

System.out.println(firstThreeMultiplesOfSeven); // [7, 14, 21]
```

`filter` alone does not create a stopping point; `limit(3)` targets three *filtered* values, not the first three initial values. Make sure there are enough elements satisfying the condition; otherwise, a pipeline with an infinite source may search forever.

## 7. Lazy Evaluation: `iterate` Does Not Compute Everything Upon Creation

A stream is a **lazy** pipeline of operations: calling `Stream.iterate(...)` creates a source description, without pre-creating infinitely many objects. Elements are requested when a terminal operation begins consuming the pipeline.

```java
Stream<Integer> numbers = Stream.iterate(1, n -> n + 1);
// Has not consumed 1, 2, 3... to build a list here yet.

List<Integer> firstThree = numbers.limit(3).toList();
// At the terminal operation, the result is [1, 2, 3].
```

A stream is not designed to be reused after it has been consumed. If you want to get another set of values, create a **new stream**:

```java
List<Integer> firstTwo =
        Stream.iterate(1, n -> n + 1).limit(2).toList();

List<Integer> firstFour =
        Stream.iterate(1, n -> n + 1).limit(4).toList();
```

Do not write:

```java
Stream<Integer> s = Stream.iterate(1, n -> n + 1);
s.limit(2).toList();
// s.limit(4).toList(); // Wrong: reusing a stream that has already been operated on/consumed.
```

Even an intermediate operation like `limit` is part of the pipeline attached to the stream, so you should not try to “branch” from the same stream object. Create a new source via a supplier if you need multiple uses.

### Do not abuse side effects in `next` and `hasNext`

`next` should describe a **state-transition rule**. `hasNext` should describe a **termination condition**. For example, if `next` calls an API, writes logs, or mutates shared variables, lazy evaluation, short-circuiting, or parallelization can make the invocation count and order of side effects unpredictable.

Do not write business logic that depends on the exact number of times `next` or `hasNext` is called just to generate elements. To perform controlled side effects, separate the data-generation step and the saving/displaying step across clear boundaries.

## 8. Using `iterate` to Model State, Not Just Integers

`iterate` is useful when **the next element is a new state** computed from the previous state. For example, a daily deposit schedule:

```java
record PaymentDay(int day, int saved) {}

List<PaymentDay> schedule = Stream.iterate(
        new PaymentDay(1, 100),
        state -> state.day() <= 3,
        state -> new PaymentDay(state.day() + 1,
                                state.saved() + 50))
        .toList();
```

This is an illustrative snippet; `PaymentDay` needs to be placed in a valid class or file with `Stream`/`List` imports. The result is three states: (1,100), (2,150), (3,200). Old states are not mutated; the `next` function returns **a new record**. This aligns well with functional style: immutable data and explicit transformations.

If you instead use a mutable object and have `next` mutate **the exact same object** and return it, the elements in the result may all reference the same object and end up looking like the same state. For a pipeline used to record history, create new values or make defensive copies as required.

Conceptual error example:

```java
// Suppose MutableState has setDay(int) and getDay().
MutableState state = new MutableState(1);

List<MutableState> snapshots = Stream.iterate(
        state,
        s -> s.getDay() <= 3,
        s -> {
            s.setDay(s.getDay() + 1);
            return s; // Returns the EXACT SAME mutated object!
        })
        .toList();
```

This is **illustrative pseudocode** because `MutableState` is not defined. Do not use this approach to store snapshots; even when the stream terminates, the list may contain the same reference multiple times.

## 9. Avoiding Non-Terminating Loops and Numeric Overflow

Several bugs are directly related to the termination condition:

### Condition never becomes false

```java
// Has a condition but makes no progress; do not use terminal toList().
Stream.iterate(1, n -> n > 0, n -> n);
```

`n` stays 1 forever; `hasNext` is always true. Use `limit` as a safeguard or redesign `next` so that the value progresses toward a terminating state.

### Condition does not match the direction of change

```java
// Starts at 5, decreasing, yet the condition is n < 10:
// values can keep decreasing and never cross the threshold 10.
Stream.iterate(5, n -> n < 10, n -> n - 1);
```

If the goal is to get `5,4,3,2,1`, write:

```java
List<Integer> countdown =
        Stream.iterate(5, n -> n > 0, n -> n - 1)
              .toList();
// [5, 4, 3, 2, 1]
```

### Overflow when using `int`

`int` is a bounded 32-bit integer. If `n` keeps increasing near `Integer.MAX_VALUE`, `n + 1` can overflow and wrap around to negative numbers. The condition `n <= Integer.MAX_VALUE` is always true for every `int`, so it is **not a useful termination condition** for incrementing an `int`.

To handle large ranges, consider `long`, `BigInteger`, or checking before incrementing. Finite `BigInteger` example:

```java
java.math.BigInteger one = java.math.BigInteger.ONE;

List<java.math.BigInteger> values = Stream.iterate(
        one,
        n -> n.compareTo(java.math.BigInteger.valueOf(4)) <= 0,
        n -> n.add(one))
        .toList();
// [1, 2, 3, 4]
```

`BigInteger` does not overflow according to ordinary primitive limits, but you still need to avoid non-terminating loops, allocation issues, and resource limits.

### Infinite source with a terminal operation that needs all elements

`count()`, `toList()`, `collect(...)`, or `reduce(...)` generally need to traverse the entire source. On an unbounded `iterate` source without a downstream stopping point, they may never complete. `anyMatch`, `findFirst`, and other short-circuiting terminal operations can stop if the search condition has a solution after finitely many elements, but they are **not guaranteed** to terminate if the condition is never true.

## 10. `IntStream.iterate` and `LongStream.iterate`

When elements are primitive integers, the JDK provides corresponding overloads on `IntStream`/`LongStream`. Example:

```java
import java.util.stream.IntStream;

int total = IntStream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1)
        .sum();

System.out.println(total); // 15
```

`IntStream` processes `int` directly, avoiding boxing each element into an `Integer` as `Stream<Integer>` does. It is useful when performing large-scale numeric computations.

However, if you only need a uniformly increasing range of numbers, `IntStream.range(startInclusive, endExclusive)` or `IntStream.rangeClosed(startInclusive, endInclusive)` can be **simpler**:

```java
System.out.println(
        IntStream.range(1, 6).boxed().toList()
); // [1, 2, 3, 4, 5]

System.out.println(
        IntStream.rangeClosed(1, 5).sum()
); // 15
```

Choose `iterate` when **the rule for the next element is not simply incrementing by 1 over a range** or when you need to model a complex state; choose `range`/`rangeClosed` when they sufficiently express the intent.

### Comparison with `Stream.generate`

`Stream.generate(Supplier<T>)` creates elements by calling a supplier, without directly receiving the *previous value* as input:

```java
Stream<String> same = Stream.generate(() -> "A").limit(3);
System.out.println(same.toList()); // [A, A, A]
```

If you need to compute `next` from the previous element, `iterate` is usually clearer. `generate` can use a stateful supplier, but then you must be careful about side effects and thread safety, especially with parallel streams. A `generate` source may lack the encounter order of an ordered sequential `iterate` source.

## 11. Should `Stream.iterate` Be Switched to Parallel?

`Stream.iterate` creates an **ordered, sequential** source by default. If you call `parallel()`, downstream steps can be processed in parallel, but because the next element **depends on the previous element**, data generation/splitting is not as straightforward as with `ArrayList` or `IntStream.range`.

```java
List<Integer> values = Stream.iterate(1, n -> n <= 100, n -> n + 1)
        .parallel()
        .map(n -> n * 2)
        .toList();
```

With an ordered stream and `toList()`, the result order still follows encounter order, but that **does not mean** each `map` lambda is invoked on threads in the order 1, 2, 3, ... or that parallelization is always faster. Do not use side effects in `next`/`map` and assume that `parallel()` will preserve the order of external state updates.

For simple operations on a contiguous number sequence, `IntStream.range(...).parallel()` can split work more easily; even so, optimization decisions should be based on measurements with realistic workloads.

If you have print/log side effects in a parallel stream, `forEach` does not guarantee order. `forEachOrdered` preserves the encounter order of actions but may negate the benefit of parallelism. A better approach in many cases is to **collect the results**, then perform side effects in the desired order at an outer layer.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong/dangerous | How to fix |
| --- | --- | --- |
| `Stream.iterate(1, n -> n + 1).toList()` | Unbounded source, terminal tries to collect everything | Add `limit`/`takeWhile` or use the overload with `hasNext` |
| Confusing `limit(5)` with “maximum value 5” | `limit` only limits the **number of elements** | Use `hasNext`/`takeWhile` when stopping by value |
| Thinking the three-arg overload is always finite | The predicate may always be true | Check whether `next` moves toward the false region |
| Setting the condition in the wrong direction | `next` moves away from the stopping threshold | Match the increment/decrement direction with the condition |
| Expecting the seed to always appear | `hasNext(seed)` can be false | Test the condition at the seed right away |
| Using `filter` to “stop” an infinite stream | `filter` only discards elements, does not terminate the source | `takeWhile`/`limit` |
| Confusing `takeWhile` with `filter` | `takeWhile` only takes the leading prefix satisfying the condition | Use each for its intended purpose |
| Calling `toList()` on an already consumed stream | Streams are not reusable | Create a new stream |
| `next` mutates and returns the same object | All elements may reference the same mutable object | Use immutable data, return a new state |
| `int` overflow while the condition stays true | Can generate wrong sequences or non-terminating loops | Use safe bounds / an appropriate numeric type |
| Side effects in `next`, `hasNext` | Hard to predict execution order/count | Keep lambdas pure and separate I/O |
| Switching to `parallel` and expecting it to be faster | The source has dependencies between elements | Benchmark, consider `range` |
| Using `iterate` for a simple `1..N` sequence | Longer code, easy to get boundaries wrong | `IntStream.range`/`rangeClosed` |

## 13. Practice Exercises

1. For `Stream.iterate(2, n -> n * 2).limit(5)`, predict the resulting list. **Answer:** [2, 4, 8, 16, 32].
2. Write a three-argument overload generating odd numbers from 1 to 9 (inclusive of 9). **Hint:** seed 1, `n <= 9`, `n + 2`.
3. Write two versions generating [1, 2, 3, 4, 5] using `limit` and using `hasNext`. Explain the difference in termination semantics.
4. Why is `Stream.iterate(10, n -> n < 10, n -> n + 1)` empty? Change the condition to get just the number 10.
5. Compare `Stream.iterate(1, n -> n + 1).filter(n -> n < 5).toList()` with `takeWhile(n -> n < 5).toList()`. In which case might the program not terminate?
6. Create a countdown from 5 to 1 using the three-argument overload. Predict what happens if `n < 5` is used as the predicate instead of `n > 0`.
7. Create a record `BalanceStep(int day, int amount)`, starting at (1,100), increasing by 20 each day, stopping at day 4. Why is returning a new record in `next` safer than mutating the same object?
8. Use `IntStream.iterate` to compute the sum of even numbers less than 12. **Answer:** `0+2+4+6+8+10 = 30`.
9. Write `Stream.iterate(1, n -> n + 1).filter(n -> n % 7 == 0).limit(3).toList()`. Predict the output and explain why placing `filter` before `limit` matters.
10. Try `Stream.iterate(1, n -> n > 0, n -> n)` with `limit(3)`. Then **do not run the unbounded version**, and instead explain by reasoning why it cannot terminate on its own.
11. When processing near `Integer.MAX_VALUE`, why can `n + 1` break the predicate logic? Propose an alternative representation.
12. When a task only needs to generate numbers in the range `[1,1000]`, choose `iterate` or `IntStream.rangeClosed`? State reasons regarding clarity and work-splitting capability.

## 14. Checklist Before Applying `Stream.iterate`

- Does the rule “**next value from current value**” truly fit `iterate`?
- Choose the **two-argument** or **three-argument** overload? If there is no `hasNext`, does downstream have a stopping point?
- Does the predicate checking the **seed** give the desired result? Is the upper bound `<` or `<=`?
- Does `next` drive the state to where the predicate becomes false? Are there cycles or stationary states?
- Is there any risk of numeric overflow or unbounded data allocation?
- Are you confusing `limit` (by **count**) with `takeWhile` (by **condition**)?
- Are you placing side effects in `next`/`hasNext` or sharing mutable objects?
- For a simple number sequence, would `IntStream.range` express it more clearly?
- Have you tested edge cases such as **rejected seed**, **limit of 0**, **stopping right at the boundary**, and **no values matching a filter**?

**Remember:** `Stream.iterate(seed, next)` creates an inherently **unbounded** source and typically needs `limit`/`takeWhile`; `Stream.iterate(seed, hasNext, next)` allows the termination condition to live right in the source, checked **before emitting each element**. Whichever overload you choose, ensure the pipeline has a clear termination path, proper state transitions, and processing costs within acceptable limits.
