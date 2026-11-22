# Distinguishing Results Between `filter`, `takeWhile`, and `dropWhile`

## 1. Lesson and Exercise Objectives

In the **Beginner and Intermediate Exercises** chapter of **JAVA_STREAM_API**, you have already learned to build declarative pipelines with `filter`, `map`, `reduce`, and `collect`. This lesson focuses on a distinction that easily causes bugs: with the exact same `Predicate`, `filter`, `takeWhile`, and `dropWhile` can produce **three different result sets**.

After completing this lesson, you will be able to:

- Accurately predict the output of all three operations on a **Stream with encounter order**.
- Identify the **contiguous matching prefix** and the **suffix** starting from the first non-matching element.
- Explain when `filter` and `takeWhile` yield identical results, and when they diverge completely.
- Select the right operation for sensor readings, event streams, logs, and time-series data.
- Handle empty sources, `null` elements, always-true/always-false predicates, and infinite sources.
- Understand `unordered()` contracts and coordination costs in parallel streams.
- Write tests based on **output assertions**, not callback invocation counts.

Examples use **Java 17+**. `filter` has existed since Java 8; `takeWhile` and `dropWhile` were added in **Java 9**, and apply to both `Stream<T>` and primitive streams such as `IntStream`, `LongStream`, and `DoubleStream`.

### Quick Reference Table

| Operation | Behavior on Ordered Stream | Upon First Element Failing `P` | Result |
| --- | --- | --- | --- |
| `filter(P)` | Tests every element across the whole source | Continues checking subsequent elements | **All elements** matching `P` |
| `takeWhile(P)` | Takes contiguous prefix matching `P` | Stops taking elements | **Matching prefix** |
| `dropWhile(P)` | Drops contiguous prefix matching `P` | Begins keeping this element and everything after | **Remaining suffix** |

**Key point:** Once `dropWhile` encounters the first element that fails `P`, it **stops filtering by `P`**. Elements in the suffix may pass or fail the predicate, yet all of them are kept.

## 2. Mental Model: One Source, One Predicate, Three Answers

Consider an ordered source:

~~~text
Source: [2, 4, 7, 3, 8, 1]
P(x):    x < 5

Element by element:
         2✓  4✓  7✗  3✓  8✗  1✓
                │
                └── First boundary failing P

filter(P):     [2, 4, 3, 1]
takeWhile(P):  [2, 4]
dropWhile(P):  [7, 3, 8, 1]
~~~

`filter` selects every number less than 5 whether at the start, middle, or end. `takeWhile` selects only `2` and `4` because `7` breaks the contiguous prefix. `dropWhile` discards the prefix `[2,4]` and keeps all of `7`, `3`, `8`, `1`.

### Complete Runnable Example

~~~java
import java.util.Arrays;
import java.util.List;

public class CompareThreeOperations {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 7, 3, 8, 1);

        List<Integer> filtered = values.stream()
            .filter(n -> n < 5)
            .toList();

        List<Integer> taken = values.stream()
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> dropped = values.stream()
            .dropWhile(n -> n < 5)
            .toList();

        System.out.println(filtered); // [2, 4, 3, 1]
        System.out.println(taken);     // [2, 4]
        System.out.println(dropped);   // [7, 3, 8, 1]
    }
}
~~~

We create a fresh Stream for **each** operation. Streams are designed for single-use consumption; never create one Stream variable and invoke three terminal operations on it.

### Warm-Up Question Before Starting

If we replace `n < 5` with `n >= 5`, what does `takeWhile` return? Since the first element is `2` and fails the condition, the result is an **empty list**. Meanwhile, `dropWhile` retains the **entire source**.

## 3. Exercise 1 — Predicting Output on Unsorted Data

**Level:** Beginner.

**Prompt:** Given the sequence `[1, 3, 6, 2, 7, 4]` and the condition `n < 5`, write down the results of `filter`, `takeWhile`, and `dropWhile` before running the program.

**Answer:**

| Operation | Result | Explanation |
| --- | --- | --- |
| `filter(n -> n < 5)` | `[1, 3, 2, 4]` | Selects all numbers less than 5. |
| `takeWhile(n -> n < 5)` | `[1, 3]` | Stops at `6`, the first element not less than 5. |
| `dropWhile(n -> n < 5)` | `[6, 2, 7, 4]` | Drops only the prefix `[1,3]`. |

**Java Solution:**

~~~java
import java.util.List;

public class Exercise01 {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 3, 6, 2, 7, 4);

        System.out.println(numbers.stream()
            .filter(n -> n < 5).toList());
        // [1, 3, 2, 4]

        System.out.println(numbers.stream()
            .takeWhile(n -> n < 5).toList());
        // [1, 3]

        System.out.println(numbers.stream()
            .dropWhile(n -> n < 5).toList());
        // [6, 2, 7, 4]
    }
}
~~~

**Common mistake:** assuming `dropWhile(n -> n < 5)` is equivalent to `filter(n -> n >= 5)`. On this sequence, the negated filter produces `[6,7]`, whereas `dropWhile` also keeps `2` and `4` in the suffix.

## 4. Exercise 2 — Data Sorted in Ascending Order

**Level:** Beginner.

**Prompt:** Given `[1, 2, 2, 4, 5, 7, 9]` sorted ascending, separate numbers **less than 5** from numbers 5 or greater; compare the three operations.

~~~java
import java.util.List;

public class Exercise02 {
    public static void main(String[] args) {
        List<Integer> sorted = List.of(1, 2, 2, 4, 5, 7, 9);

        List<Integer> allSmall = sorted.stream()
            .filter(n -> n < 5)
            .toList();

        List<Integer> prefix = sorted.stream()
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> suffix = sorted.stream()
            .dropWhile(n -> n < 5)
            .toList();

        System.out.println(allSmall); // [1, 2, 2, 4]
        System.out.println(prefix);   // [1, 2, 2, 4]
        System.out.println(suffix);   // [5, 7, 9]
    }
}
~~~

**Why are `filter` and `takeWhile` equal in this case?**

Because the data is sorted ascending and the predicate `n < 5` is **monotonic with respect to that order**: once a number `>= 5` appears, no number less than 5 can appear afterward. Every matching element forms **a single prefix**.

The general condition for `filter(P)` and `takeWhile(P)` to yield the same result on an ordered Stream is: **no element satisfying `P` appears after the first element that fails `P`**.

Similarly, if all elements failing `P` form a single suffix, `dropWhile(P)` equals `filter(P.negate())` on that sequence. This is a property of the **data and predicate**, not an API equivalence.

### Be Careful with Other Predicates

An ascending list **does not guarantee** that every predicate is monotonic. For instance, `n % 2 == 0` can alternate true, false, and true again even on a sorted list:

~~~text
Source: [2, 3, 4, 5, 6]
P: even number

filter       → [2, 4, 6]
takeWhile    → [2]
dropWhile    → [3, 4, 5, 6]
~~~

Only replace `filter` with `takeWhile` when you know for certain how the **data ordering interacts with the predicate**.

## 5. Exercise 3 — First Element Already Fails the Condition

**Level:** Beginner.

**Prompt:** Predict the output when the source is `[9, 1, 2, 3]` and `P(n) = n < 5`.

~~~java
import java.util.List;

List<Integer> numbers = List.of(9, 1, 2, 3);

System.out.println(numbers.stream()
    .filter(n -> n < 5).toList()); // [1, 2, 3]

System.out.println(numbers.stream()
    .takeWhile(n -> n < 5).toList()); // []

System.out.println(numbers.stream()
    .dropWhile(n -> n < 5).toList()); // [9, 1, 2, 3]
~~~

**Explanation:** `takeWhile` has no initial valid element to keep. `dropWhile` has no valid prefix to drop, so it returns the entire sequence. Meanwhile, `filter` still sees `1, 2, 3` later and selects them.

**Extension experiment:** If you simply reorder the source to `[1,2,3,9]`, `takeWhile` returns `[1,2,3]`, and `dropWhile` returns `[9]`. The same set of values with a **different encounter order** produces different results.

## 6. Exercise 4 — Always-True, Always-False, and Empty Sources

**Level:** Beginner.

**Prompt:** Fill in a table of results for all three operations when the predicate always returns `true`, always returns `false`, or the Stream has no elements.

| Source | Predicate | `filter` | `takeWhile` | `dropWhile` |
| --- | --- | --- | --- | --- |
| `[1,2,3]` | `n -> true` | `[1,2,3]` | `[1,2,3]` | `[]` |
| `[1,2,3]` | `n -> false` | `[]` | `[]` | `[1,2,3]` |
| `[]` | Any valid predicate | `[]` | `[]` | `[]` |

**Verification Solution:**

~~~java
import java.util.List;

public class Exercise04 {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3);

        System.out.println(source.stream()
            .takeWhile(n -> true).toList()); // [1, 2, 3]

        System.out.println(source.stream()
            .dropWhile(n -> true).toList()); // []

        System.out.println(source.stream()
            .takeWhile(n -> false).toList()); // []

        System.out.println(source.stream()
            .dropWhile(n -> false).toList()); // [1, 2, 3]

        System.out.println(List.<Integer>of().stream()
            .filter(n -> n > 0).toList()); // []

        System.out.println(List.<Integer>of().stream()
            .takeWhile(n -> n > 0).toList()); // []

        System.out.println(List.<Integer>of().stream()
            .dropWhile(n -> n > 0).toList()); // []
    }
}
~~~

Using `List.<Integer>of()` makes the generic element type of the empty Stream explicit. If a terminal `findFirst()` follows, any pipeline with no remaining elements returns `Optional.empty()`.

## 7. Exercise 5 — Defining Boundaries with `<=` vs. `<`

**Level:** Beginner → Intermediate.

**Prompt:** Given the ascending sequence `[10,20,30,40,50]`, take all elements **before** threshold 30, then take all elements **from** threshold 30 onward. Modify the predicate if you want to include 30 in the first group.

**Solution:**

~~~java
import java.util.List;

public class BoundaryExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(10, 20, 30, 40, 50);

        List<Integer> before30 = values.stream()
            .takeWhile(n -> n < 30)
            .toList();

        List<Integer> from30 = values.stream()
            .dropWhile(n -> n < 30)
            .toList();

        List<Integer> through30 = values.stream()
            .takeWhile(n -> n <= 30)
            .toList();

        System.out.println(before30);  // [10, 20]
        System.out.println(from30);    // [30, 40, 50]
        System.out.println(through30); // [10, 20, 30]
    }
}
~~~

The **first element that fails the predicate** is included in the result of `dropWhile`, rather than discarded. With `n < 30`, the value 30 becomes the first element of the suffix.

### Checking Duplicate Boundary Values

~~~text
Source: [10, 20, 30, 30, 40]

takeWhile(n < 30) → [10, 20]
dropWhile(n < 30) → [30, 30, 40]

takeWhile(n <= 30) → [10, 20, 30, 30]
dropWhile(n <= 30) → [40]
~~~

**Question:** Why does `dropWhile(n -> n < 30)` keep both 30s? Because once it encounters the first 30 that fails the predicate, it keeps **all remaining elements** without continuing to evaluate the predicate per element.

## 8. Exercise 6 — Preserving Results in Event-Log Order

**Level:** Intermediate.

**Prompt:** A system logs statuses in chronological order. We want to find:

1. Events **before the first error**.
2. Events **from the first error onward**.
3. All **non-error** events across the entire log.

These three questions are distinct; select the corresponding operation for each.

**Solution:**

~~~java
import java.util.List;

public class EventLogExercise {
    record Event(int sequence, String level, String message) {}

    public static void main(String[] args) {
        List<Event> log = List.of(
            new Event(1, "INFO",  "Started"),
            new Event(2, "WARN",  "Waiting for resource"),
            new Event(3, "ERROR", "Connection lost"),
            new Event(4, "INFO",  "Retrying"),
            new Event(5, "ERROR", "Retries exhausted")
        );

        List<Event> beforeFirstError = log.stream()
            .takeWhile(e -> !"ERROR".equals(e.level()))
            .toList();

        List<Event> fromFirstError = log.stream()
            .dropWhile(e -> !"ERROR".equals(e.level()))
            .toList();

        List<Event> allNonErrors = log.stream()
            .filter(e -> !"ERROR".equals(e.level()))
            .toList();

        System.out.println(beforeFirstError.stream()
            .map(Event::sequence).toList()); // [1, 2]

        System.out.println(fromFirstError.stream()
            .map(Event::sequence).toList()); // [3, 4, 5]

        System.out.println(allNonErrors.stream()
            .map(Event::sequence).toList()); // [1, 2, 4]
    }
}
~~~

**Explanation:** `takeWhile` returns the error-free **prefix**. `dropWhile` returns the **suffix** starting at the first error; that suffix may contain INFO/WARN events after the error. `filter` returns all non-error events, including events **after the error**.

This is a classic example where substituting `filter` for `takeWhile` breaks business semantics: "before the first error" is not "all non-error events".

### What If the Log Is Not Chronologically Ordered?

`takeWhile` and `dropWhile` rely on the **Stream's encounter order**; they do not inspect timestamps or `sequence` fields automatically. If records arrive out of order and business rules require "before the first error in time", sort by a clear time key before finding the boundary:

~~~java
List<Event> chronological = log.stream()
    .sorted(java.util.Comparator.comparingInt(Event::sequence))
    .toList();

List<Event> beforeError = chronological.stream()
    .takeWhile(e -> !"ERROR".equals(e.level()))
    .toList();
~~~

Sorting adds extra time and memory overhead. Do not add `sorted()` if the problem only actually needs `filter`.

## 9. Exercise 7 — Reading Measurement Sequences Before and After a Threshold

**Level:** Intermediate.

**Prompt:** A sensor sends a sequence of temperatures in **chronological order**: `[65,68,72,82,75,90]`. The alarm threshold is 80. Extract:

- All measurements below threshold across the entire session.
- Contiguous measurements **before the first alarm**.
- Measurements **from the first alarm** to the end of the session.

~~~java
import java.util.List;

public class TemperatureExercise {
    public static void main(String[] args) {
        List<Integer> temperatures =
            List.of(65, 68, 72, 82, 75, 90);

        List<Integer> safeReadings = temperatures.stream()
            .filter(t -> t < 80)
            .toList();

        List<Integer> beforeAlarm = temperatures.stream()
            .takeWhile(t -> t < 80)
            .toList();

        List<Integer> fromAlarm = temperatures.stream()
            .dropWhile(t -> t < 80)
            .toList();

        System.out.println(safeReadings); // [65, 68, 72, 75]
        System.out.println(beforeAlarm);  // [65, 68, 72]
        System.out.println(fromAlarm);    // [82, 75, 90]
    }
}
~~~

After crossing the threshold at 82, the temperature drops back to 75, yet **75 remains in the `dropWhile` suffix**. If you want **only** readings of 80 or above, use `filter(t -> t >= 80)`, producing `[82,90]`.

### Extension Exercise

Write a function returning the index (or timestamp) of the first alarm. If the data contains no alarm, represent **absence** explicitly—for instance with `OptionalInt` or `Optional<Reading>`—rather than returning a misleading dummy timestamp.

## 10. Exercise 8 — Composing Operations: Step Order Matters

**Level:** Intermediate.

**Prompt:** Given `[2,5,4,1,6]`, compare two pipelines:

- Filter even numbers, **then** take numbers less than 5 until the first non-matching element.
- Take the prefix less than 5, **then** filter even numbers.

~~~java
import java.util.List;

public class CompositionExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 5, 4, 1, 6);

        List<Integer> filterThenTake = values.stream()
            .filter(n -> n % 2 == 0)
            .takeWhile(n -> n < 5)
            .toList();

        List<Integer> takeThenFilter = values.stream()
            .takeWhile(n -> n < 5)
            .filter(n -> n % 2 == 0)
            .toList();

        System.out.println(filterThenTake); // [2, 4]
        System.out.println(takeThenFilter); // [2]
    }
}
~~~

**Detailed trace:**

~~~text
Original source:             [2, 5, 4, 1, 6]

filter(even):                [2, 4, 6]
takeWhile(n < 5):            [2, 4]

takeWhile(n < 5) first:      [2]
filter(even) after:          [2]
~~~

Removing 5 in the earlier `filter` step prevents `takeWhile` from **seeing that boundary**, allowing it to continue and keep 4. When `takeWhile` comes first, 5 ends the prefix, so 4 is never considered.

**Conclusion:** Never reorder `filter` relative to `takeWhile` or `dropWhile` arbitrarily. They do not commute like independent filters.

## 11. Exercise 9 — Empty Sources, `null` Elements, and `null` Boundaries

**Level:** Intermediate.

**Prompt:** A `List<Integer>` source may contain `null`. On `[1,2,null,3,4]`, implement two different policies:

- **Policy A:** encountering `null` **ends the valid segment**.
- **Policy B:** discard `null` and evaluate numbers normally.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class NullBoundaryExercise {
    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(1, 2, null, 3, 4);

        // A: null acts as a boundary.
        List<Integer> beforeGap = values.stream()
            .takeWhile(n -> n != null && n < 4)
            .toList();

        List<Integer> fromGap = values.stream()
            .dropWhile(n -> n != null && n < 4)
            .toList();

        // B: strip null before applying predicate.
        List<Integer> afterCleaning = values.stream()
            .filter(Objects::nonNull)
            .takeWhile(n -> n < 4)
            .toList();

        System.out.println(beforeGap);    // [1, 2]
        System.out.println(fromGap);      // [null, 3, 4]
        System.out.println(afterCleaning); // [1, 2, 3]
    }
}
~~~

**Notes:**

- `n -> n < 4` **automatically unboxes** `Integer` to `int`; if `n == null`, this can throw `NullPointerException`.
- When `null` is a boundary, the predicate must check `n != null` before comparing.
- When stripping `null` from the source, you can call `filter(Objects::nonNull)` before `takeWhile`.
- `Stream.toList()` can contain null elements while still being unmodifiable; `Collectors.toUnmodifiableList()` forbids nulls.

Policies A and B are **not equivalent**. Choose based on whether missing data signifies a "break in continuity" or merely a "record to skip".

### Null Source Reference Differs from Null Elements

~~~java
List<Integer> source = null;

// Do not call source.stream().
List<Integer> safeSource =
    java.util.Optional.ofNullable(source).orElseGet(List::of);

System.out.println(safeSource.stream()
    .takeWhile(n -> n < 4).toList()); // []
~~~

Use the "null source equals empty source" rule only when the business contract allows it. If the source is required, use `Objects.requireNonNull(source, "...")` to fail explicitly.

## 12. Exercise 10 — Infinite Streams and Non-Termination Risk

**Level:** Intermediate.

**Prompt:** An unbounded integer stream starts at 0. Produce:

1. The first five integers less than 5.
2. Three consecutive integers starting at 5.
3. Explain why `filter` cannot replace `takeWhile` in all infinite-stream cases.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class InfiniteStreamExercise {
    public static void main(String[] args) {
        int[] prefix = IntStream.iterate(0, n -> n + 1)
            .takeWhile(n -> n < 5)
            .toArray();

        int[] suffixStart = IntStream.iterate(0, n -> n + 1)
            .dropWhile(n -> n < 5)
            .limit(3)
            .toArray();

        System.out.println(Arrays.toString(prefix)); // [0, 1, 2, 3, 4]
        System.out.println(Arrays.toString(suffixStart)); // [5, 6, 7]
    }
}
~~~

Here `takeWhile(n < 5)` terminates because the source eventually emits a number not less than 5. `dropWhile(n < 5)` skips 0–4; `limit(3)` afterward ensures the terminal operation finishes after retaining three elements.

### Do Not Run These Examples on an Unbounded Infinite Source

~~~java
// Avoid running: never terminates because filter keeps reading
// looking for more elements matching n < 5 after passing the threshold.
// IntStream.iterate(0, n -> n + 1)
//     .filter(n -> n < 5)
//     .toArray();

// Avoid running: the suffix after the boundary is infinite.
// IntStream.iterate(0, n -> n + 1)
//     .dropWhile(n -> n < 5)
//     .toArray();
~~~

`filter` is not permitted to halt the entire pipeline just because one element failed; subsequent elements **could theoretically match again**. `takeWhile` can stop at the prefix break on an ordered source. `dropWhile` does not bound the suffix, so it needs another limiting operation or terminal condition.

**Important exception:** `filter(P).limit(k)` can still terminate if the source eventually supplies **at least k elements** matching `P`. Do not equate "filter on an infinite stream" with "every pipeline using filter hangs forever".

### What If the Predicate Never Fails?

`takeWhile(n -> true)` on an infinite source **cannot** produce a finite `toList()` result on its own. A stopping condition must exist either in the data or in another bounding operation.

## 13. Exercise 11 — Parallel and `unordered`: No Single Deterministic Prefix

**Level:** Intermediate.

**Prompt:** Run all three operations on `IntStream.rangeClosed(1,8)` in parallel. Then add `unordered()` and explain why **you must not write tests asserting one fixed output** for `takeWhile`/`dropWhile` once encounter order is dropped.

### 13.1. Ordered Parallel Stream

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class OrderedParallelExercise {
    public static void main(String[] args) {
        int[] filtered = IntStream.rangeClosed(1, 8)
            .parallel()
            .filter(n -> n < 5)
            .toArray();

        int[] taken = IntStream.rangeClosed(1, 8)
            .parallel()
            .takeWhile(n -> n < 5)
            .toArray();

        int[] dropped = IntStream.rangeClosed(1, 8)
            .parallel()
            .dropWhile(n -> n < 5)
            .toArray();

        System.out.println(Arrays.toString(filtered)); // [1, 2, 3, 4]
        System.out.println(Arrays.toString(taken)); // [1, 2, 3, 4]
        System.out.println(Arrays.toString(dropped)); // [5, 6, 7, 8]
    }
}
~~~

`parallel()` **does not automatically discard encounter order**. `IntStream.rangeClosed` has a defined encounter order; operations must still preserve ordered semantics even when splits run across multiple threads.

### 13.2. Unordered Stream

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class UnorderedWhileExercise {
    public static void main(String[] args) {
        int[] taken = IntStream.rangeClosed(1, 8)
            .parallel()
            .unordered()
            .takeWhile(n -> n < 5)
            .toArray();

        int[] dropped = IntStream.rangeClosed(1, 8)
            .parallel()
            .unordered()
            .dropWhile(n -> n < 5)
            .toArray();

        System.out.println(Arrays.toString(taken));
        System.out.println(Arrays.toString(dropped));
        // Do not rely on fixed contents or ordering for these arrays.
    }
}
~~~

On an **unordered stream**, Java allows:

- `takeWhile(P)` to take **any subset** of elements matching `P`. It is not guaranteed to return all of `[1,2,3,4]`.
- `dropWhile(P)` to drop **any subset** of elements matching `P`. Elements failing `P` must remain in the result; some elements matching `P` may also remain.
- `filter(P)` must still keep **all elements matching `P`** as a multiset of values, even though encounter order may be unspecified.

`unordered()` **is not a shuffle**. Observing one run match the ordered output creates no guarantee for future runs.

### 13.3. Invariants You Can Test

For `taken` after `takeWhile(n < 5)`, you can rely only on every returned element being less than 5; the count may vary. For `dropped`, all elements from 5 to 8 must remain, while numbers from 1 to 4 may still be present.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] taken = IntStream.rangeClosed(1, 8)
    .parallel().unordered()
    .takeWhile(n -> n < 5)
    .toArray();

boolean allTakenMatch = Arrays.stream(taken)
    .allMatch(n -> n < 5);

if (!allTakenMatch) {
    throw new AssertionError("takeWhile emitted an invalid element");
}

int[] dropped = IntStream.rangeClosed(1, 8)
    .parallel().unordered()
    .dropWhile(n -> n < 5)
    .toArray();

for (int mustRemain = 5; mustRemain <= 8; mustRemain++) {
    final int value = mustRemain;
    if (Arrays.stream(dropped).noneMatch(n -> n == value)) {
        throw new AssertionError("dropWhile lost " + value);
    }
}
~~~

These assertions test only invariants guaranteed by the contract; they do not infer speed or thread scheduling. If the problem requires **preserving a chronological prefix**, keep encounter order and do not use `unordered()`.

## 14. Exercise 12 — Combining with `limit`, `skip`, and `findFirst`

**Level:** Intermediate.

**Prompt:** Given `[1,2,3,8,4,9]`, compare taking the first two elements via `limit` against taking a conditional prefix. Then find the **first element failing `n < 5`**.

~~~java
import java.util.List;
import java.util.Optional;

public class TerminalCompositionExercise {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 8, 4, 9);

        List<Integer> firstTwo = values.stream()
            .limit(2)
            .toList();

        List<Integer> prefix = values.stream()
            .takeWhile(n -> n < 5)
            .toList();

        Optional<Integer> firstFailure = values.stream()
            .dropWhile(n -> n < 5)
            .findFirst();

        List<Integer> afterBoundary = values.stream()
            .dropWhile(n -> n < 5)
            .skip(1)
            .toList();

        System.out.println(firstTwo);      // [1, 2]
        System.out.println(prefix);        // [1, 2, 3]
        System.out.println(firstFailure);  // Optional[8]
        System.out.println(afterBoundary); // [4, 9]
    }
}
~~~

- `limit(k)` limits by **element count**, not by a predicate.
- `takeWhile(P)` limits by the **first boundary** failing `P`.
- `dropWhile(P).findFirst()` retrieves the element that **breaks the prefix**, if any.
- `dropWhile(P).skip(1)` skips that boundary element itself, keeping everything after it.

If every element satisfies `P`, `dropWhile(P).findFirst()` returns `Optional.empty()`. Do not call `get()` when no result exists; use `orElse`, `orElseGet`, or `orElseThrow` per business policy.

### Do Not Confuse This with `filter` Finding All Failing Elements

~~~java
List<Integer> allFailures = values.stream()
    .filter(n -> n >= 5)
    .toList();

System.out.println(allFailures); // [8, 9]
~~~

`filter(n -> n >= 5)` returns **all** numbers exceeding the threshold, not **the first threshold-crossing number plus everything after it**.

## 15. Capstone Exercise — Analyzing a Test Session Up to the First Failure

**Level:** Intermediate.

**Scenario:** A test runner records execution steps in order. Each record has `sequence`, `durationMs`, and `passed`. Operations needs:

1. A list of steps that **passed** at any point.
2. A list of **contiguous passing steps before the first failure**.
3. A list of steps **from the first failure to the end of the session**.
4. The `sequence` of the **first failure**, as an `OptionalInt` since failures may be absent.
5. The total duration of steps **before the first failure** as a `long`.

**Complete Solution:**

~~~java
import java.util.List;
import java.util.OptionalInt;

public class SessionAnalysis {
    record Step(int sequence, int durationMs, boolean passed) {}

    record Summary(
        List<Step> allPassed,
        List<Step> passedBeforeFailure,
        List<Step> fromFirstFailure,
        OptionalInt firstFailureSequence,
        long preFailureDurationMs
    ) {}

    static Summary analyze(List<Step> steps) {
        List<Step> allPassed = steps.stream()
            .filter(Step::passed)
            .toList();

        List<Step> prefix = steps.stream()
            .takeWhile(Step::passed)
            .toList();

        List<Step> suffix = steps.stream()
            .dropWhile(Step::passed)
            .toList();

        OptionalInt firstFailure = suffix.stream()
            .mapToInt(Step::sequence)
            .findFirst();

        long duration = prefix.stream()
            .mapToLong(Step::durationMs)
            .sum();

        return new Summary(
            allPassed,
            prefix,
            suffix,
            firstFailure,
            duration
        );
    }

    public static void main(String[] args) {
        List<Step> steps = List.of(
            new Step(1, 120, true),
            new Step(2, 80, true),
            new Step(3, 200, false),
            new Step(4, 50, true),
            new Step(5, 100, false)
        );

        Summary summary = analyze(steps);

        System.out.println(summary.allPassed().stream()
            .map(Step::sequence).toList()); // [1, 2, 4]

        System.out.println(summary.passedBeforeFailure().stream()
            .map(Step::sequence).toList()); // [1, 2]

        System.out.println(summary.fromFirstFailure().stream()
            .map(Step::sequence).toList()); // [3, 4, 5]

        System.out.println(summary.firstFailureSequence());
        // OptionalInt[3]

        System.out.println(summary.preFailureDurationMs()); // 200

        Summary noFailure = analyze(List.of(
            new Step(1, 10, true),
            new Step(2, 15, true)
        ));

        System.out.println(noFailure.firstFailureSequence());
        // OptionalInt.empty

        System.out.println(noFailure.fromFirstFailure());
        // []
    }
}
~~~

**Explanation:**

- `filter(Step::passed)` retains step `4` even though it occurs after the first failure.
- `takeWhile(Step::passed)` retains only the prefix `1,2`.
- `dropWhile(Step::passed)` starts at step `3` and includes the passing step `4` afterward.
- `firstFailureSequence` is an Optional because a session may have **no failures at all**.
- `mapToLong` sums durations as `long`, avoiding early overflow when summing `int` values across many steps.

**Type note:** `suffix.stream().mapToInt(Step::sequence).findFirst()` returns `OptionalInt`. Do not call `mapToInt` after `findFirst()` on `Stream<Step>`, because at that point the result is already `Optional<Step>`, not a Stream. On an empty source or a failure-free session, `OptionalInt.empty()` accurately represents no incident.

### Input Data Policy

This exercise assumes:

- The `steps` list is non-null; `Step` elements are non-null.
- Records are already in **execution order**. If order may be scrambled, sort explicitly by `sequence` or timestamp first.
- `durationMs` is non-negative; if negative values are possible, fail fast or handle per business rules before summing.
- A `Step` with `passed = true` after the first failure must remain in the suffix because the report analyzes what happened **after the incident**.

Do not mutate `steps` inside callbacks; do not use `parallel().unordered()` when reporting depends on event order.

### Extension Exercise

Add `long totalFailureDurationMs`: compute the total duration of **all failed steps** via `filter(step -> !step.passed())` followed by `mapToLong(Step::durationMs).sum()`. That metric differs from the total duration of the suffix, because the suffix can contain passing steps after the incident.

## 16. Systematic Testing: Do Not Rely on Callback Logs

**Level:** Intermediate.

A solid test suite verifies the outputs of all three operations across multiple scenarios rather than counting predicate invocations. The Stream API can optimize pipelines; in parallel streams, callback timing and execution order are not contracts for correctness.

Use a pure Java verification helper:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.IntPredicate;
import java.util.stream.IntStream;

public class WhileOperationsChecks {
    static void expect(
        int[] input,
        IntPredicate predicate,
        int[] expectedFilter,
        int[] expectedTake,
        int[] expectedDrop
    ) {
        int[] filtered = Arrays.stream(input)
            .filter(predicate)
            .toArray();

        int[] taken = Arrays.stream(input)
            .takeWhile(predicate)
            .toArray();

        int[] dropped = Arrays.stream(input)
            .dropWhile(predicate)
            .toArray();

        if (!Arrays.equals(filtered, expectedFilter)) {
            throw new AssertionError("filter is wrong");
        }
        if (!Arrays.equals(taken, expectedTake)) {
            throw new AssertionError("takeWhile is wrong");
        }
        if (!Arrays.equals(dropped, expectedDrop)) {
            throw new AssertionError("dropWhile is wrong");
        }

        // For an ordered source, take + drop reconstructs the exact input.
        int[] joined = IntStream.concat(
            IntStream.of(taken),
            IntStream.of(dropped)
        ).toArray();

        if (!Arrays.equals(joined, input)) {
            throw new AssertionError("Missing or duplicate elements");
        }
    }

    public static void main(String[] args) {
        expect(
            new int[] {2, 4, 7, 3, 8, 1},
            n -> n < 5,
            new int[] {2, 4, 3, 1},
            new int[] {2, 4},
            new int[] {7, 3, 8, 1}
        );

        expect(
            new int[] {1, 2, 3},
            n -> true,
            new int[] {1, 2, 3},
            new int[] {1, 2, 3},
            new int[] {}
        );

        expect(
            new int[] {1, 2, 3},
            n -> false,
            new int[] {},
            new int[] {},
            new int[] {1, 2, 3}
        );

        expect(
            new int[] {},
            n -> n > 0,
            new int[] {},
            new int[] {},
            new int[] {}
        );

        System.out.println("PASS");
    }
}
~~~

### An Important Invariant of Ordered Streams

Given the same ordered source and the same pure predicate, concatenating `takeWhile(P)` with `dropWhile(P)` must reconstruct the source:

~~~text
source = concat(takeWhile(P), dropWhile(P))
~~~

This invariant does not mean the two operations share one traversal automatically. They are **two independent pipelines** (in the example, each creates a fresh Stream from the array). When the source mutates between traversals or the predicate has state/side effects, this comparison is no longer reliable.

### Edge-Case Checklist

| Case | Result to Verify |
| --- | --- |
| Empty source | All three are empty |
| First element fails | `takeWhile` empty; `dropWhile` keeps entire source |
| All elements pass | `takeWhile` keeps entire source; `dropWhile` empty |
| All elements fail | `filter`, `takeWhile` empty; `dropWhile` keeps entire source |
| Pass, then fail, then pass | `takeWhile` **does not** capture trailing passing elements |
| Multiple elements equal threshold | Verify `<` vs. `<=` carefully |
| Source contains `null` | Choose either skip-null policy or null-as-boundary policy |
| Unordered source | Do not assert a single prefix/suffix in original order |
| Parallel ordered | Result semantics still follow encounter order |
| Infinite source | Prove pipeline terminates or add an explicit bound |

## 17. Performance, Lazy Evaluation, and Risks of Stateful Callbacks

### 17.1. `filter` Is Stateless; `takeWhile`/`dropWhile` Are Stateful

`filter` is a **stateless intermediate operation**: deciding whether to keep or reject an element requires no memory of earlier elements.

`takeWhile` and `dropWhile` are **stateful intermediate operations** on ordered streams: they must track where **the predicate first failed** to determine the prefix/suffix split.

`takeWhile` is also **short-circuiting**: upon hitting the boundary on an ordered stream, it can stop pulling elements from the source before consuming everything. `dropWhile` does not make the suffix disappear; if the terminal operation consumes the whole suffix, elements after the boundary still flow through.

### 17.2. Parallel Does Not Guarantee Speedup

On an ordered source, finding the exact prefix boundary in parallel can incur coordination overhead across splits. This is particularly noticeable for `takeWhile`, `dropWhile`, `limit`, and `skip`. If business rules do not require encounter order, `unordered()` can unlock optimizations, **but it alters the contract of both while operations**.

There is no universal element-count threshold where parallel becomes faster. Benchmark with representative data sizes and distributions, especially when the boundary occurs very early or very late.

### 17.3. Never Put External State Inside a Predicate

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

// Do not build boundary semantics on an external mutable counter:
AtomicInteger calls = new AtomicInteger();

int[] result = IntStream.range(0, 20)
    .parallel()
    .takeWhile(n -> calls.incrementAndGet() < 5)
    .toArray();
~~~

`AtomicInteger` makes the increment atomic, **not** the count/order of predicate calls stable under encounter order. In parallel, the output can vary with work-splitting and scheduling; the intent "take only the first four elements" must be written with `limit(4)` on an ordered source, never a counter inside a predicate.

### 17.4. Do Not Compare Operations via `peek` Side Effects

~~~java
// Do not use print counts from peek to claim
// a Stream must traverse everything or skip an exact number of elements.
~~~

Some terminal operations may optimize or short-circuit; intermediate callbacks are not a reliable auditing protocol. Verify outputs and source contracts instead. To measure performance, use a proper benchmarking tool and representative datasets.

## 18. Misconceptions to Avoid

### Misconception 1: `takeWhile` Is a Faster `filter`

No. `takeWhile` takes only the matching prefix, so it differs from `filter` whenever matching elements appear after a non-matching element. **Semantic** differences must be settled before performance questions.

### Misconception 2: `dropWhile` Always Drops Every Element Matching the Predicate

No. It drops only the **contiguous prefix**. Once it begins keeping the suffix, all remaining elements are retained even if some match the predicate.

### Misconception 3: `takeWhile` Automatically Sorts Data

No. It depends on the source's encounter order. If the task is "all elements below threshold" and the data is not guaranteed to be ordered, `filter` is the right choice.

### Misconception 4: Putting `filter` Before `takeWhile` Always Equals the Reverse

No. An earlier `filter` can remove an element that would have terminated the prefix, letting `takeWhile` advance further. Exercise 8 demonstrated the different outputs.

### Misconception 5: `parallel` Means `unordered`

No. `parallel()` selects parallel execution; `unordered()` drops encounter-order constraints. A parallel ordered stream still preserves prefix/suffix semantics according to source order.

### Misconception 6: `takeWhile` on an Infinite Source Always Terminates

No. It terminates only if an element eventually fails the predicate (or a downstream operation stops early). If the predicate is always true with no other bound, the pipeline may never finish.

### Misconception 7: `dropWhile(P).findFirst()` Always Has a Value

No. If the source is empty or **every element satisfies `P`**, the suffix is empty and `findFirst()` returns `Optional.empty()`.

### Misconception 8: One Stream Can Be Reused for All Three Operations

No. Each terminal operation consumes the Stream. To compare them, create three fresh Streams from a stable source or use a `Supplier<Stream<T>>` that supplies a new Stream each time.

### Misconception 9: `takeWhile` Exists in Java 8

No. `takeWhile` and `dropWhile` were introduced in **Java 9**. If a project must run on Java 8, use another approach or suitable library; these calls will not compile directly under Java 8.

## 19. Decision Table and Self-Check Questions

| Practical Requirement | Appropriate Operation | Reason |
| --- | --- | --- |
| Get all transactions above a threshold | `filter` | Evaluates entire source, independent of boundaries |
| Get passing steps **before the first failure** | `takeWhile` | Exactly the contiguous prefix |
| Inspect logs **from the first error** onward | `dropWhile` | Keeps suffix including passing steps after the error |
| Get all temperature readings below threshold | `filter` | Readings below threshold can recur after a spike |
| Get initial values of an ascending sequence before cutoff | `takeWhile` | Cutoff predicate is monotonic with source order |
| Drop all initial values before cutoff in an ascending sequence | `dropWhile` | Starts at the first failing element |
| Get exactly the first `k` elements regardless of predicate | `limit(k)` | Count-based rather than condition-based |
| Get the element that breaks the prefix | `dropWhile(P).findFirst()` | Returns Optional; may be absent |
| Get any matching element from an unordered source | `filter(P).findAny()` | No prefix requirement |
| Stable pagination requirement | Deterministic order + `skip/limit` or dedicated pagination | `unordered().takeWhile` has no fixed boundary |

### Self-Check Questions

1. **Given `[1,4,7,2]` and `P(n) = n < 5`, what does `filter(P)` return?** `[1,4,2]`.
2. **On the same source, what does `takeWhile(P)` return?** `[1,4]`.
3. **On the same source, what does `dropWhile(P)` return?** `[7,2]`.
4. **Is `dropWhile(P) = filter(P.negate())` always true?** Not in general; they match only when the source satisfies the predicate contiguously and then fails it contiguously.
5. **When does `takeWhile(P)` equal `filter(P)`?** When no element matching the predicate appears after the first element failing it in encounter order.
6. **If the first element fails `P`, what does `takeWhile` return?** An empty Stream.
7. **If all elements satisfy `P`, what does `dropWhile` return?** An empty Stream.
8. **Can `dropWhile(P).findFirst()` return `Optional.empty()`?** Yes.
9. **Does `parallel()` make `takeWhile` on a List automatically unordered?** No.
10. **Must `unordered().takeWhile(P)` keep all elements matching `P`?** No; it may return any subset.
11. **May `unordered().dropWhile(P)` drop elements that fail `P`?** No; it may only drop a subset of elements that satisfy the predicate.
12. **Why is `filter(Objects::nonNull)` sometimes needed before `takeWhile(n -> n < 5)`?** To avoid NPE from auto-unboxing null, though doing so alters the boundary if null was meant to stop the prefix.
13. **On an infinite ascending source, does `takeWhile(n < 5)` terminate?** Yes, if the source reaches 5.
14. **Does `filter(n < 5).toArray()` on an infinite ascending source terminate?** No; filter keeps reading to check whether later numbers satisfy the predicate.
15. **Should you use a mutable counter inside a predicate to express a count limit?** No; use `limit` or an explicit data model.
16. **If you want all data from an incident onward, what do you use?** `dropWhile` with a predicate describing the "no incident yet" state.
17. **If you want all error-free items, even after the first error, what do you use?** `filter`.
18. **What property must data satisfy for `takeWhile` to mean "before a timestamp cutoff"?** Encounter order must match chronological order, or the data must be sorted chronologically beforehand.
19. **Can you invoke three terminal operations on one already-created Stream?** No; create a fresh Stream each time.
20. **What is the minimum Java version for `Stream.takeWhile`/`dropWhile`?** Java 9.

### Extension Exercises

**Exercise A:** Given `[4,6,8,3,10,12]`, predict all three results for `P(n) = n % 2 == 0`. Explain why `dropWhile` keeps both `10` and `12` even though they are even.

**Exercise B:** A list of connection sessions has a `connected` flag. Compute the total duration of the **initial contiguous connected streak** and compare it with the total duration of **all connected sessions**; use `takeWhile` and `filter`, respectively.

**Exercise C:** Modify the log example to return `Optional<Event> firstError` using `dropWhile(e -> !"ERROR".equals(e.level())).findFirst()`. Test logs with no errors and logs starting with an error.

**Exercise D:** Write tests for `IntStream.rangeClosed(1,1000).parallel().takeWhile(n -> n < 100)`, verifying the ordered result. Then add `unordered()` and check only invariants guaranteed by the specification, without asserting exactly 99 elements.

**Key takeaway:** `filter(P)` selects **every element matching `P`**. On an ordered source, `takeWhile(P)` keeps only the **contiguous prefix** matching `P`, while `dropWhile(P)` discards that prefix and keeps **the entire suffix**, including elements matching `P` that appear after the boundary. The three operations can coincide in special cases, but they cannot be substituted freely. Always confirm business semantics, encounter order, missing-data policy, and termination conditions before choosing an operation or enabling parallel execution.
