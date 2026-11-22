# Practice: Array Statistics and Method Decomposition in Java

## 1. Goal and practice requirements

Given an integer array `int[]`, build a Java 17+ program that computes the following statistics:

1. **Array length**: total number of elements.
2. **Counts of positive, negative, and zero values**: positive satisfies `x > 0`, negative satisfies `x < 0`, and zero is `x == 0`.
3. **Sum of all elements**: use `long` to avoid `int` overflow when adding many integers.
4. **Minimum (`min`) and maximum (`max`) values** when the array is non-empty.
5. **Arithmetic average** when the array has at least one element; use floating-point division so fractional digits are preserved.

Quality requirement: **do not cram all logic into `main`**. Separate calculation, aggregation, and presentation into clearly named methods. Statistical methods must not modify the elements of the input array.

Given the sample input:

```text
[8, -3, 0, 7, -2, 8]
```

the expected results are:

| Metric | Value | Reason |
| --- | ---: | --- |
| Length | 6 | Six elements |
| Positive count | 3 | `8, 7, 8` |
| Negative count | 2 | `-3, -2` |
| Zero count | 1 | One `0` |
| Sum | 18 | `8 - 3 + 0 + 7 - 2 + 8 = 18` |
| Minimum | -3 | Smallest number in the entire array |
| Maximum | 8 | Largest number in the entire array |
| Average | 3.00 | `18 / 6 = 3.0` |

Note: **sum, min, max, and average apply to the entire array here**, not just positive numbers. Positive/negative/zero counts are additional statistics. Read the requirement carefully to distinguish those so you do not compute the wrong numbers.

## 2. Breaking the problem into small methods

Instead of writing a long `main` with many loops, design independent methods:

| Method | Input | Return value / responsibility |
| --- | --- | --- |
| `sum(int[] values)` | Integer array | Sum as `long` |
| `countPositive(int[] values)` | Integer array | Count of elements `> 0` |
| `countNegative(int[] values)` | Integer array | Count of elements `< 0` |
| `findMin(int[] values)` | Integer array | `OptionalInt`: minimum value, or empty |
| `findMax(int[] values)` | Integer array | `OptionalInt`: maximum value, or empty |
| `average(long sum, int count)` | Sum and element count | `OptionalDouble`: average, or empty if no elements |
| `analyze(int[] values)` | Integer array | Combines the results above into a `Stats` object |
| `printReport(String title, int[] values)` | Title and array | Prints results clearly without recomputing formulas inside print code |
| `main(String[] args)` | Application entry point | Prepares data, invokes methods, verifies results |

This decomposition follows **one primary responsibility per method**:

- `sum`, `countPositive`, `countNegative`, `findMin`, and `findMax` focus solely on computation and never print to the screen.
- `analyze` **coordinates** the computations and enforces the input precondition.
- `printReport` decides only **how to display** the computed statistics.
- `main` orchestrates test scenarios instead of housing the entire algorithm.

When a step fails, you know exactly which method to inspect. Methods that only compute and return values can also be **unit tested independently** without parsing console text.

### Method contract

Before writing Java, define clearly:

- **Precondition:** input `values` must not be `null`. An empty array `new int[0]` **is allowed**.
- **Postcondition:** `sum` is the sum of all elements; `countPositive + countNegative + countZero == values.length`.
- **No side effects:** calculations do not mutate `values[i]`, do not print to the console, and do not depend on mutable global state.
- **Empty input:** sum and all counts equal `0`; `min`, `max`, and `average` **have no value** and must never default to `0` as an extremum or average result.
- **`null` input:** the coordinating method `analyze` rejects it explicitly via `Objects.requireNonNull`, rather than treating `null` as an empty array.

Internal helpers in this lesson are called by `analyze` after the `null` check; if reused as public APIs, each helper should declare and enforce its own preconditions.

## 3. Pseudocode before implementation

This is an algorithm description; **not Java code to compile**.

```text
FUNCTION SUM(values):
    total ← 0 (using 64-bit integer)
    FOR EACH x IN values:
        total ← total + x
    RETURN total

FUNCTION COUNT_POSITIVE(values):
    count ← 0
    FOR EACH x IN values:
        IF x > 0:
            count ← count + 1
    RETURN count

FUNCTION COUNT_NEGATIVE(values):
    count ← 0
    FOR EACH x IN values:
        IF x < 0:
            count ← count + 1
    RETURN count

FUNCTION MIN(values):
    IF values is empty: RETURN no value
    result ← values[0]
    FOR EACH remaining element x:
        IF x < result: result ← x
    RETURN result

FUNCTION MAX(values):
    IF values is empty: RETURN no value
    result ← values[0]
    FOR EACH remaining element x:
        IF x > result: result ← x
    RETURN result

FUNCTION AVERAGE(total, count):
    IF count = 0: RETURN no value
    RETURN (floating-point) total / count

FUNCTION ANALYZE(values):
    IF values = null: report input error
    positives ← COUNT_POSITIVE(values)
    negatives ← COUNT_NEGATIVE(values)
    zeros ← LENGTH(values) - positives - negatives
    total ← SUM(values)
    minimum ← MIN(values)
    maximum ← MAX(values)
    mean ← AVERAGE(total, LENGTH(values))
    RETURN all statistical results
```

**Why can zeros be counted by subtraction?** Every integer belongs to exactly one of three groups: `> 0`, `< 0`, or `== 0`. These three groups are disjoint and cover the entire array; hence `zeros = length - positives - negatives` holds.

**Why must `min` and `max` handle empty arrays?** You cannot access `values[0]` when `values.length == 0`. Nor can you say the minimum of an empty array is `0`: `0` can be valid data, whereas an empty array has no elements at all.

## 4. Predicting behavior with a trace table

For `[8, -3, 0, 7, -2, 8]`, you can trace counts and sum in a single **element-by-element dry run** as follows:

| Step | Element `x` | Positive | Negative | Zero | Sum after step |
| --- | ---: | ---: | ---: | ---: | ---: |
| Init | — | 0 | 0 | 0 | 0 |
| 1 | 8 | 1 | 0 | 0 | 8 |
| 2 | -3 | 1 | 1 | 0 | 5 |
| 3 | 0 | 1 | 1 | 1 | 5 |
| 4 | 7 | 2 | 1 | 1 | 12 |
| 5 | -2 | 2 | 2 | 1 | 10 |
| 6 | 8 | 3 | 2 | 1 | 18 |

The table models **a combined state after each element**, useful for verifying logic; the decomposed program below computes the metrics using **independent passes** and arrives at the exact same final values.

When finding `min` and `max`, start with the first element `8`. After encountering `-3`, `min = -3`; no later element is smaller, so the final minimum is `-3`. `max` stays `8` for this array. Average result: `18 / 6 = 3.0`.

Such a table helps pinpoint the **first** step where a sum or count diverges from expectations. During practice, you can set breakpoints in each method and compare actual values against the table.

## 5. Java 17+: complete program decomposed into methods

Create a single file **`ArrayStatisticsPractice.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class ArrayStatisticsPractice {
    record Stats(
            int length,
            int positive,
            int negative,
            int zero,
            long sum,
            OptionalInt min,
            OptionalInt max,
            OptionalDouble average) {}

    static long sum(int[] values) {
        long total = 0L;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static int countPositive(int[] values) {
        int count = 0;
        for (int value : values) {
            if (value > 0) {
                count++;
            }
        }
        return count;
    }

    static int countNegative(int[] values) {
        int count = 0;
        for (int value : values) {
            if (value < 0) {
                count++;
            }
        }
        return count;
    }

    static OptionalInt findMin(int[] values) {
        if (values.length == 0) {
            return OptionalInt.empty();
        }
        int result = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] < result) {
                result = values[i];
            }
        }
        return OptionalInt.of(result);
    }

    static OptionalInt findMax(int[] values) {
        if (values.length == 0) {
            return OptionalInt.empty();
        }
        int result = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] > result) {
                result = values[i];
            }
        }
        return OptionalInt.of(result);
    }

    static OptionalDouble average(long total, int count) {
        if (count == 0) {
            return OptionalDouble.empty();
        }
        return OptionalDouble.of((double) total / count);
    }

    static Stats analyze(int[] values) {
        Objects.requireNonNull(values, "values");

        int positive = countPositive(values);
        int negative = countNegative(values);
        int zero = values.length - positive - negative;
        long total = sum(values);

        return new Stats(
                values.length,
                positive,
                negative,
                zero,
                total,
                findMin(values),
                findMax(values),
                average(total, values.length));
    }

    static void printReport(String title, int[] values) {
        Stats stats = analyze(values);
        System.out.println(title);
        System.out.println("array=" + Arrays.toString(values));
        System.out.println("length=" + stats.length());
        System.out.println("positive=" + stats.positive());
        System.out.println("negative=" + stats.negative());
        System.out.println("zero=" + stats.zero());
        System.out.println("sum=" + stats.sum());

        System.out.println("min=" + (stats.min().isPresent()
                ? stats.min().getAsInt() : "N/A"));
        System.out.println("max=" + (stats.max().isPresent()
                ? stats.max().getAsInt() : "N/A"));

        if (stats.average().isPresent()) {
            System.out.printf(Locale.US, "average=%.2f%n",
                    stats.average().getAsDouble());
        } else {
            System.out.println("average=N/A");
        }
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("test " + label + ": PASS");
    }

    public static void main(String[] args) {
        int[] sample = {8, -3, 0, 7, -2, 8};
        int[] empty = {};
        int[] negatives = {-5, -1, -5};
        int[] large = {Integer.MAX_VALUE, Integer.MAX_VALUE};

        printReport("Case A", sample);
        printReport("Case B", empty);
        printReport("Case C", negatives);
        printReport("Case D", large);

        Stats a = analyze(sample);
        Stats b = analyze(empty);
        Stats d = analyze(large);

        check("sample", a.length() == 6
                && a.positive() == 3 && a.negative() == 2
                && a.zero() == 1 && a.sum() == 18L
                && a.min().orElseThrow() == -3
                && a.max().orElseThrow() == 8);

        check("empty", b.length() == 0 && b.sum() == 0
                && b.min().isEmpty() && b.max().isEmpty()
                && b.average().isEmpty());

        check("large sum", d.sum() == 4294967294L);
    }
}
```

The program requires no external libraries. Use **JDK 17 or later** and open a terminal in the directory containing `ArrayStatisticsPractice.java`:

```bash
javac -encoding UTF-8 ArrayStatisticsPractice.java
java ArrayStatisticsPractice
```

A successful `javac` command prints no output. **Exact stdout** of `java`:

```text
Case A
array=[8, -3, 0, 7, -2, 8]
length=6
positive=3
negative=2
zero=1
sum=18
min=-3
max=8
average=3.00
Case B
array=[]
length=0
positive=0
negative=0
zero=0
sum=0
min=N/A
max=N/A
average=N/A
Case C
array=[-5, -1, -5]
length=3
positive=0
negative=3
zero=0
sum=-11
min=-5
max=-1
average=-3.67
Case D
array=[2147483647, 2147483647]
length=2
positive=2
negative=0
zero=0
sum=4294967294
min=2147483647
max=2147483647
average=2147483647.00
test sample: PASS
test empty: PASS
test large sum: PASS
```

### Explaining the four datasets

- **Case A**: includes positive, negative, and zero values; the array-wide average is `3.00`.
- **Case B**: empty array; counts and sum are 0, while `min`, `max`, and `average` are `N/A`, avoiding accessing `values[0]` or dividing by 0.
- **Case C**: negative numbers only; `max = -1` (not 0) and average `-11 / 3` prints as `-3.67`.
- **Case D**: two `Integer.MAX_VALUE` entries. The mathematical sum `4294967294` exceeds `int` range, while `long sum` holds the exact result here.

The last three checks use `check`: if a condition fails, it throws `AssertionError`, rather than always printing `PASS` even when the algorithm is wrong. It is not a full test framework, but it works well for practicing output assertions against expected values.

## 6. Why use `OptionalInt` and `OptionalDouble`?

A common mistake is defaulting to `min = 0` and `max = 0` for an empty array and printing them as if they were valid statistics.

For example, for `{-5, -1, -5}`, the true `max` is `-1`, **not 0**. Initializing `max = 0` and updating only when an element is greater than `max` keeps the wrong answer `0`.

In this program:

- `OptionalInt.of(value)` represents **the presence of an `int` value**.
- `OptionalInt.empty()` represents **no value exists** to return.
- `OptionalDouble` serves the same purpose for the floating-point average.

The printing code calls `getAsInt()` only after `isPresent()` is `true`, and calls `getAsDouble()` only when `average` is present. Calling `getAsInt()` on `OptionalInt.empty()` throws `NoSuchElementException`.

`OptionalInt`/`OptionalDouble` is well suited for **representing an optionally absent result**, though it is not the only approach. In tiny exercises, you can also check `values.length == 0` before computing or printing min/max. Most importantly, **never confuse "no result" with a result of 0**.

## 7. `record Stats`: bundling results without cramming computation logic

Java 17 supports **`record`**, convenient for representing a group of related values returned together:

```java
record Stats(int length, int positive, int negative) {}
```

This is only a **syntax illustration**; the complete program defines `Stats` with eight fields. A record automatically generates a constructor, accessor methods such as `length()` and `positive()`, and other standard members.

Returning `Stats` avoids global variables or passing mutable parameters back and forth just to update results. Because `analyze` returns an aggregate value, different callers can use the statistics as needed (printing reports, testing, saving data, etc.) without manually invoking each helper again.

**Do not confuse a record with deep immutability of every reference.** A record stores its components as `final` fields, but if a component holds a mutable object, that object's contents can still change. Here `Stats` stores primitives and immutable `OptionalInt`/`OptionalDouble` objects, so no input array is placed in the record to be mutated through the result.

## 8. Testing individual methods and edge cases

Method decomposition pays off most when each method has its own **contract and test cases**:

| Method | Test case | Expected result |
| --- | --- | --- |
| `sum` | `[8, -3, 0, 7, -2, 8]` | `18L` |
| `sum` | `[]` | `0L` |
| `sum` | `[Integer.MAX_VALUE, Integer.MAX_VALUE]` | `4294967294L` |
| `countPositive` | `[-1, 0, 4, 4]` | `2` |
| `countNegative` | `[-1, 0, 4, 4]` | `1` |
| `findMin` | `[-5, -1, -5]` | `OptionalInt.of(-5)` |
| `findMax` | `[-5, -1, -5]` | `OptionalInt.of(-1)` |
| `findMin` / `findMax` | `[]` | Both empty |
| `average` | `(18L, 6)` | `OptionalDouble.of(3.0)` |
| `average` | `(0L, 0)` | `OptionalDouble.empty()` |

These cases represent **test expectations**, not additional standalone snippets. You can write `check(...)` calls yourself or use JUnit in projects configured with a testing library.

In particular, be sure to test:

1. **Empty array** to avoid indexing `0` and dividing by `0`.
2. **Negative numbers** and **zero** to verify `> 0`, `< 0`, and `== 0` clearly.
3. **All-negative array** to catch wrong `max` initialization.
4. **Array with duplicate values** to verify `min`/`max` updates.
5. **Sum exceeding `int` range** to confirm `long` is used.
6. **`null`** to verify the input contract is enforced consistently.
7. **Single-element array**: `min` and `max` must both equal that element; `average` equals that exact value.
8. **Input unchanged**: compare array elements before and after calling `analyze` if verifying no side effects.

A test suite must not assert only that `sum` is right and assume counting or extremum methods are right too; each responsibility needs its own test coverage.

## 9. Common mistakes when decomposing into methods

### Mistake 1: Computing average with integer division

```java
long sum = 14;
int count = 3;
double wrong = sum / count;         // 4.0: integer division first
double right = (double) sum / count; // approximately 4.6667
```

This is an illustrative snippet inside a method. Assigning to `double` **after** integer division cannot restore the lost fractional part. Cast or make one operand floating-point before dividing.

### Mistake 2: Using `int` for sums that can grow large

```java
int wrongSum = Integer.MAX_VALUE + Integer.MAX_VALUE;
// wrongSum == -2 due to int overflow.
```

Adding two `int` values evaluates in `int` arithmetic, so it can overflow **before assignment**, even if the target variable is `long`. In the complete program, `total` is declared `long`, so `total += value` evaluates in `long` context.

### Mistake 3: Counting zero as positive or negative

```java
if (value >= 0) {
    positive++;
}
```

The snippet above is **wrong** when "positive" means `> 0`. `0` must be counted in its own group. A useful invariant to double-check is `positive + negative + zero == length`.

### Mistake 4: One method computing, printing, and mutating data

For example, a `sum` method that adds, modifies `values[i]`, and prints results is hard to reuse and hard to test. Here, calculation helpers **only return results**. `printReport` handles console output; `main` selects scenarios and checks assertions.

### Mistake 5: Packing unrelated tasks into one method

If `main` holds every loop, number formatting, empty-array handling, and test assertion, changing report formatting forces you to read through the entire algorithm. Decomposing by **responsibility** is far better than splitting just to keep functions a few lines long.

### Mistake 6: Adding extra passes without recognizing the trade-off

The design in section 5 uses multiple passes: `sum`, `countPositive`, `countNegative`, `findMin`, and `findMax` each scan part or all of the array. For an array of length `n`, total work still scales linearly with `n` because the number of methods is constant: **O(n) time** and **O(1) auxiliary memory** for computation. `Arrays.toString` builds a display string, which adds memory proportional to array size.

If an application needs higher throughput on huge arrays, you can combine updates into a single loop while still keeping `analyze` separate from `printReport` and `main`. Do not optimize prematurely at the expense of clarity in a learning example, yet do not equate "method decomposition" with "requiring multiple passes over the data."

## 10. Guided extension exercises

After getting the program running cleanly:

1. Add `countEven(int[] values)` counting even numbers with `value % 2 == 0`, including `0` and negative even numbers. Add a corresponding field to `Stats` and a test case.
2. Add a helper `sumPositive` computing the sum of **positive numbers only**; do not confuse it with the total sum of the entire array.
3. Add `findFirstIndexOfMax` returning the **first** index of the maximum value; define its behavior for empty arrays.
4. Try writing a **single-pass** version of `analyze` and compare its results against the multi-helper version on the same test suite.
5. Write a test suite covering at least an empty array, single element, all-negative, all-positive, duplicate values, zeros, and a sum exceeding `int`.

These extensions are extra practice and do not change the main outputs of the program in section 5.

**Remember:** Array statistics are not just about writing loops—they are about defining each metric accurately, handling edge cases, and separating responsibilities cleanly. Small, side-effect-free, deterministic methods make Java code **easier to read, debug, test, and reuse**.
