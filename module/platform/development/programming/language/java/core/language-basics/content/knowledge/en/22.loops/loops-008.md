# Sum, count, and maximum accumulator patterns in Java

> **Java core — language-basics / Loops**  
> **Environment:** JDK 17+, single-file program, no external libraries.  
> **Goal:** Use a single loop to compute a sum, count elements / count conditionally, and find the maximum value; choose correct initial values, handle empty arrays, and avoid `int` sum overflow.

## 1. What is the accumulator (*accumulator*) pattern?

When traversing a sequence of numbers, you can maintain **summary state** variables. Each iteration processes one element and updates the state:

~~~java
int[] numbers = {3, -2, 7, 0, -5};
long sum = 0;
int count = 0;

for (int number : numbers) {
    sum += number;
    count++;
}

System.out.println(sum);   // 3
System.out.println(count); // 5
~~~

- **Sum**: initialize `sum = 0`, update via `sum += number`.
- **Count**: initialize `count = 0`, increment exactly once for each counted element.
- **Maximum value**: after encountering the first element, keep `max` equal to the largest element seen so far; on each pass compare and update if needed.

All three calculations can be performed in **the same single traversal**, without needing three separate loops. For `n` elements, time is **O(n)** and auxiliary memory for the accumulators is **O(1)**.

## 2. Initialization and updates: sum, count, conditional count

The sum of an empty sequence is defined as `0`. The element count of an empty sequence is also `0`. You can also count elements that satisfy a condition:

~~~java
int[] numbers = {3, -2, 7, 0, -5};
long sum = 0;
int count = 0;
int positiveCount = 0;

for (int number : numbers) {
    sum += number;
    count++;

    if (number > 0) {
        positiveCount++;
    }
}
// sum = 3; count = 5; positiveCount = 2.
~~~

Here `0` is **not** counted as positive because the condition is `number > 0`. If non-negative numbers need to be counted, change it to `number >= 0` and update the test table accordingly.

Do not confuse `count` (total number of elements) with `positiveCount` (number of elements satisfying the condition). If summing only positive numbers, the filter condition must wrap **both the addition and the count over the same domain**, rather than dividing the total sum by the count of positive numbers.

## 3. Finding `max` correctly even for all-negative numbers or empty arrays

A common mistake is initializing `max = 0` and only updating if an element is larger:

~~~java
// WRONG for {-8, -3, -12}:
// int max = 0;
// for (int x : numbers) {
//     if (x > max) max = x;
// }
// Wrong result is 0; actual maximum is -3.
~~~

There are two safe approaches:

1. If the array is known to be **non-empty**, set `max = numbers[0]` and start traversing from the second element.
2. If the array **could be empty**, use a `hasAny` flag to record whether any element has been seen, and return an optional result (`OptionalInt`).

~~~java
int max = 0;
boolean hasAny = false;

for (int number : numbers) {
    if (!hasAny || number > max) {
        max = number;
        hasAny = true;
    }
}

java.util.OptionalInt maximum =
        hasAny ? java.util.OptionalInt.of(max)
               : java.util.OptionalInt.empty();
~~~

In the second approach, the initial value `max = 0` is **not treated as a result** before seeing any element: the first iteration assigns `max = number` regardless of whether it is negative or positive. For an empty array, `maximum.isPresent()` is false. Do not assume the max of an empty array is 0, since 0 is not an element of the array.

## 4. Progress table and loop invariant

For the sequence `{3, -2, 7, 0, -5}`, after each iteration, the state changes as follows:

| Element just processed | `sum` | `count` | `positiveCount` | `max` |
| ---: | ---: | ---: | ---: | ---: |
| Not yet processed | 0 | 0 | 0 | None yet |
| 3 | 3 | 1 | 1 | 3 |
| -2 | 1 | 2 | 1 | 3 |
| 7 | 8 | 3 | 2 | 7 |
| 0 | 8 | 4 | 2 | 7 |
| -5 | 3 | 5 | 2 | 7 |

The **loop invariant** after `k` elements is: `sum` equals the sum of the first `k` elements; `count = k`; `positiveCount` equals the number of positive elements among the `k` elements; if `k > 0`, `max` equals the largest element in the traversed segment.

Reasoning: the initial state is valid for `k = 0`; each iteration updates the sum, counters, and max with the new element so it remains valid for `k + 1`. Once all `n` elements are traversed, the variables accurately describe the entire sequence.

Writing the invariant helps catch bugs like placing `count++` in the wrong spot, skipping the first element, or updating `max` with the reversed condition `number < max`.

## 5. Average, data types, and numeric overflow

Once you have the sum and count, you can compute the average:

~~~java
double average = count == 0
        ? Double.NaN
        : (double) sum / count;
~~~

You must check `count == 0` because the average of an empty sequence is **undefined**. In the runnable example below, we print `"N/A"` instead of an empty average. Cast `(double) sum` **before division** to avoid integer division losing the fractional part.

**Use `long` for sums of `int` integers:**

~~~java
int large = Integer.MAX_VALUE;
int wrong = large + large;       // int overflow: -2.
long correct = (long) large + large; // 4_294_967_294.
~~~

If you use `long sum = 0; sum += number;` with each `int`, the addition is performed in `long`, avoiding `int` overflow before adding. However, `long` **does not guarantee infinite range**: summing very many numbers in a huge data stream can still overflow `long`; when overflow detection is needed, use `Math.addExact` or `BigInteger` depending on the problem.

When an array contains negative numbers, the average can also be negative. Do not use the count of positive numbers as the denominator if the sum is computed over **all** elements.

## 6. Choosing a loop and testing edge cases

| Case | Result to check |
| --- | --- |
| Empty array `{}` | Sum 0, count 0, no max, average `N/A` |
| All negative `{-8, -3, -12}` | Max `-3`, not 0 |
| Contains 0 | 0 is counted as an element, but not as a positive number |
| Single element | Sum and max equal the element itself; count 1 |
| Two `Integer.MAX_VALUE`s | Sum `4_294_967_294` as `long` |
| Null array | Cannot traverse with for-each; must check null per contract |

Use `for (int x : numbers)` when only the **value** of each element is needed. Use `for (int i = 0; i < numbers.length; i++)` if you need indices or start at index 1 after assigning max to the first element.

For null inputs, you can proactively throw `IllegalArgumentException` rather than letting the loop cause an unclear `NullPointerException`; the runnable example chooses explicit error reporting.

## 7. Standalone runnable Java 17+ program

Create the file **LoopAccumulatorDemo.java**:

~~~java
import java.util.Locale;
import java.util.OptionalInt;

public final class LoopAccumulatorDemo {
    private record Summary(
            long sum, int count, int positiveCount, OptionalInt max) {}

    private static Summary analyze(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        long sum = 0L;
        int count = 0;
        int positiveCount = 0;
        int max = 0;
        boolean hasAny = false;

        for (int number : values) {
            sum += number;
            count++;

            if (number > 0) {
                positiveCount++;
            }
            if (!hasAny || number > max) {
                max = number;
                hasAny = true;
            }
        }

        return new Summary(sum, count, positiveCount,
                hasAny ? OptionalInt.of(max) : OptionalInt.empty());
    }

    private static void show(String label, int[] values) {
        Summary result = analyze(values);

        String maxText = result.max().isPresent()
                ? String.valueOf(result.max().getAsInt()) : "NONE";
        String averageText = result.count() == 0
                ? "N/A"
                : String.format(Locale.ROOT, "%.2f",
                        (double) result.sum() / result.count());

        System.out.println(label
                + ":sum=" + result.sum()
                + ",count=" + result.count()
                + ",positive=" + result.positiveCount()
                + ",max=" + maxText
                + ",average=" + averageText);
    }

    public static void main(String[] args) {
        show("mixed", new int[] {3, -2, 7, 0, -5});
        show("negative", new int[] {-8, -3, -12});
        show("empty", new int[] {});
        show("zeros", new int[] {0, 0});
        show("min", new int[] {Integer.MIN_VALUE});
        show("large", new int[] {
                Integer.MAX_VALUE, Integer.MAX_VALUE
        });

        try {
            analyze(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("nullInput=IllegalArgumentException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 LoopAccumulatorDemo.java
java LoopAccumulatorDemo
~~~

**Exact expected stdout:**

~~~text
mixed:sum=3,count=5,positive=2,max=7,average=0.60
negative:sum=-23,count=3,positive=0,max=-3,average=-7.67
empty:sum=0,count=0,positive=0,max=NONE,average=N/A
zeros:sum=0,count=2,positive=0,max=0,average=0.00
min:sum=-2147483648,count=1,positive=0,max=-2147483648,average=-2147483648.00
large:sum=4294967294,count=2,positive=2,max=2147483647,average=2147483647.00
nullInput=IllegalArgumentException
~~~

Four key observations: `negative` catches faulty max initialization; `empty` demonstrates having no maximum; `large` proves sums exceeding `int` range are preserved in `long`; and `mixed` shows sum, counters, and max are all computed from **a single traversal**.

## 8. Common mistakes and exercises

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Initializing `max = 0` and using it directly as the maximum | Wrong for all-negative arrays or empty arrays | Initialize from a valid first element or use `hasAny` |
| Using `int sum` for large sums | Can overflow | Use `long` and avoid overflow before casting |
| Only running `count++` on positive numbers | Wrong total element count | Separate `count` and `positiveCount` |
| Computing average `sum / count` with integer division | Loses fractional part, breaks on empty sequence | Check count, cast before dividing |
| Accessing `numbers[0]` on an empty array | `ArrayIndexOutOfBoundsException` | Check for empty or use a first-element flag |
| Confusing `> 0` with `>= 0` | Counts 0 differently | Stick strictly to the definition of positive/non-negative |

**Exercise 1.** Compute `sum`, `count`, `positiveCount`, and `max` by hand for `{4, -1, 0, 10}`, then verify with the program.

**Exercise 2.** Change the positive-number counting condition to count even numbers; pay attention to how negative even numbers and 0 are handled.

**Exercise 3.** Modify the pattern to take only the sum and max of **positive elements**. If there are no positive numbers, what result should be returned so it is not confused with max=0?

**Exercise 4.** Write a variant using `for (int i = 1; i < values.length; i++)` with `max = values[0]`, while handling empty input beforehand.

**Exercise 5.** Use `{Integer.MAX_VALUE, Integer.MAX_VALUE}` to compare storing the sum in `int` vs `long`; explain why casting only **after** adding as `int` is too late.

### Key takeaway

**Accumulating a sum starts at 0, counting starts at 0, while max requires an actually existing first element.** Each pass updates the accumulators accurately and preserves the invariant. For an empty array, there is no max; for all-negative numbers, max remains negative. Use `long` for potentially large `int` sums and check `count == 0` before computing an average.
