# Avoiding Overflow When Writing Comparisons by Subtraction

When writing `Comparable.compareTo` or `Comparator.compare`, an easy approach that comes to mind is subtracting the second value from the first:

```java
return first - second;
```

The reasoning seems sound: if the first is smaller, the difference is negative; if they are equal, the difference is zero; if the first is greater, the difference is positive. That reasoning holds for arithmetic on unbounded integers. However, Java's `int` and `long` have finite ranges; subtraction can **overflow** and return the wrong sign.

A comparator that fails only at boundary values can still corrupt sorting, searching, or key lookup in a collection.

This lesson focuses on identifying and fixing that bug. The complete programs use Java 17 APIs, have been compiled with `--release 17`, and run to verify stdout. Other shortened snippets illustrate expressions or method bodies, not standalone runnable files.

After this lesson, you will be able to:

- Explain why subtraction is not a safe comparison method across the entire `int` or `long` domain.
- Distinguish arithmetic overflow bugs from narrowing cast bugs.
- Use `Integer.compare`, `Long.compare`, and appropriately typed comparator factory methods.
- Reverse order or combine criteria without mismanipulating signs.
- Test the comparator contract with boundary data.

## 1. Comparison Needs the Sign, Not the Distance

For `compare(first, second)`:

| Result | Meaning |
| --- | --- |
| Negative | `first` comes before `second` |
| Zero | The two values are tied according to the comparison rule |
| Positive | `first` comes after `second` |

The result is not meant to describe "how far apart the two numbers are." Therefore, computing the full difference usually adds risk without providing needed information.

For example, to compare `Integer.MIN_VALUE` with `Integer.MAX_VALUE`, we only need to know that the first value is smaller. There is no need to fit the mathematical distance between the two numbers into an `int` variable.

A valid comparator is also not required to always return exactly `-1`, `0`, or `1`. Callers must check the sign:

```java
if (order.compare(first, second) < 0) {
    // first comes before second.
}
```

Handling signs properly is the foundation for both implementing a comparator and consuming its result.

## 2. Finite Ranges Cause Subtraction to Flip Signs

Two common integer types:

| Type | Range |
| --- | --- |
| `int` | `-2_147_483_648` to `2_147_483_647` |
| `long` | `-9_223_372_036_854_775_808` to `9_223_372_036_854_775_807` |

Consider:

```text
first  = 2_147_483_647
second = -1
```

Mathematically:

```text
first - second = 2_147_483_648
```

That value is greater than `Integer.MAX_VALUE`. When performed with ordinary `int` subtraction, the result overflows to:

```text
-2_147_483_648
```

A positive number has become a negative number. A subtraction-based comparator will conclude that `first` comes before `second`, contrary to the required numerical relation.

### Java Does Not Automatically Throw an Exception on int or long Subtraction Overflow

In ordinary integer arithmetic, Java retains the result up to the bit width of the type; high bits beyond the range are discarded. The result is reinterpreted as a signed integer.

This can produce a value that is valid for the data type but wrong for the purpose of comparison.

You should not expect `ArithmeticException` from ordinary subtraction to catch the bug. Overflow-checking methods such as `Math.subtractExact` have a different contract, discussed later.

### The Opposite Direction Can Also Fail

```text
Integer.MIN_VALUE - 1
```

has a mathematical value below the lower bound of `int`, so the `int` result wraps around to `Integer.MAX_VALUE`, a positive number.

Therefore, there is no rule like "overflow only turns large numbers into small numbers" that can salvage the comparator. Operations that can overflow must be avoided by design.

## 3. A Broken Comparator Can Violate the Entire Ordering Contract

The bug does not just misorder two elements. It can cause the rule to no longer represent a consistent ordering at all.

Suppose the comparator is:

```java
Comparator<Integer> unsafe = (first, second) -> first - second;
```

Pick three values:

```text
a = Integer.MIN_VALUE
b = 0
c = Integer.MAX_VALUE
```

According to the subtraction-based comparator:

- `a - b` is negative, so it says `a < b`.
- `b - c` is negative, so it says `b < c`.
- `a - c` overflows to `1`, so it says `a > c`.

The rule has violated **transitivity**: if `a < b` and `b < c`, then `a < c` must hold.

It can also violate the rule that swapping arguments must invert the sign. For example, `Integer.MIN_VALUE - 0` and `0 - Integer.MIN_VALUE` both evaluate to `Integer.MIN_VALUE`, which is negative in both cases.

### Impact on Collections

| Usage Site | Risk When the Comparison Rule Is Broken |
| --- | --- |
| Sorting a `List` or object array | Wrong order; the algorithm may detect the contract violation and throw an exception |
| `TreeSet` | Elements are organized or identified by an invalid relation |
| `TreeMap` keys | Key lookup and updates rely on a broken rule |
| `PriorityQueue` | Elements are dequeued in a priority order that does not match requirements |
| Binary search on sorted data | Unreliable results if the ordering precondition is no longer guaranteed |

Not every use of a broken comparator throws an exception. The fact that a small list "still sorts properly" does not prove the rule is valid across the entire data domain.

This lesson does not give a fixed stdout for sorting with a broken comparator. When the contract is violated, an incidental outcome of the algorithm should never be relied upon as expected behavior.

## 4. Program Verifying the int Bug and the Fix

Create the file **`SubtractionOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SubtractionOrderDemo {
    public static void main(String[] args) {
        int left = Integer.MAX_VALUE;
        int right = -1;
        int wrapped = left - right;
        long exactForIntOperands = (long) left - right;

        System.out.println("exact int-operand difference = " + exactForIntOperands);
        System.out.println("wrapped int difference = " + wrapped);
        System.out.println("subtraction says left < right = " + (wrapped < 0));
        System.out.println("Integer.compare says left > right = "
                + (Integer.compare(left, right) > 0));

        Comparator<Integer> unsafe = (first, second) -> first - second;
        int first = Integer.MIN_VALUE;
        int middle = 0;
        int last = Integer.MAX_VALUE;

        System.out.println("unsafe first < middle = "
                + (unsafe.compare(first, middle) < 0));
        System.out.println("unsafe middle < last = "
                + (unsafe.compare(middle, last) < 0));
        System.out.println("unsafe first < last = "
                + (unsafe.compare(first, last) < 0));

        List<Integer> values = new ArrayList<>(
                List.of(Integer.MAX_VALUE, 0, Integer.MIN_VALUE, -1));
        values.sort(Integer::compare);
        System.out.println("safe sorted = " + values);
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 SubtractionOrderDemo.java
java -Dfile.encoding=UTF-8 SubtractionOrderDemo
```

Stdout:

```text
exact int-operand difference = 2147483648
wrapped int difference = -2147483648
subtraction says left < right = true
Integer.compare says left > right = true
unsafe first < middle = true
unsafe middle < last = true
unsafe first < last = false
safe sorted = [-2147483648, -1, 0, 2147483647]
```

### Reading the Output

1. `exactForIntOperands` casts one operand to `long` **before** subtraction, which is wide enough to hold the difference of any two `int` values.
2. `wrapped` is computed in `int`, so it overflows and has a negative sign.
3. The subtraction-based comparator fails to preserve transitivity on the chosen triple.
4. `Integer.compare` determines the right relation without computing a difference.
5. The final list is sorted with a safe comparator, so the ascending order matches the numerical values.

Using `long` to display the exact difference in the example is purely an illustrative tool. When comparing two `int` values, the direct approach remains `Integer.compare`.

## 5. The Primary Fix: Type-Appropriate Comparisons

### For int

Replace:

```java
return this.priority - other.priority;
```

with:

```java
return Integer.compare(this.priority, other.priority);
```

Or as a comparator:

```java
Comparator<Integer> order = Integer::compare;
```

### For long

Do not use:

```java
return (int) (this.sequence - other.sequence);
```

Use:

```java
return Long.compare(this.sequence, other.sequence);
```

`Long.compare` returns an `int` representing the relation, even though the operands are `long`. It does not try to squeeze the distance between two `long` numbers into an `int`.

### Writing It Manually with Relational Operators

For two primitive variables with a suitable value domain, the following illustrative expression also avoids computing a difference:

```java
return first < second ? -1 : (first > second ? 1 : 0);
```

Standard library methods are usually easier to read and offer fewer opportunities for mistakes. They also clearly state the data type being compared.

### Selection Table

| Data to Compare | Recommended Choice |
| --- | --- |
| `int` | `Integer.compare(first, second)` |
| `long` | `Long.compare(first, second)` |
| `int` field of an object | `Comparator.comparingInt(...)` |
| `long` field of an object | `Comparator.comparingLong(...)` |
| Reverse order of a comparator | `order.reversed()` |
| Multiple criteria | `thenComparing...` or compare each criterion in turn, advancing only when equal to zero |

For numeric types with their own contracts such as `BigInteger` or `BigDecimal`, use the type's own comparison method instead of subtracting and converting the result to `int`.

## 6. Halfway Fixes That Are Still Broken

### 6.1. Casting to long After Subtraction Is Too Late

```java
long difference = (long) (first - second);
```

If `first` and `second` are `int`, the parenthesized expression has already been evaluated in `int`. The cast merely converts the **already overflowed result** to `long`.

Even writing:

```java
long difference = first - second;
```

does not automatically promote the subtraction to `long`. The target variable's type does not change the operand types used to evaluate the expression.

If you genuinely need the mathematical difference of two `int` values:

```java
long difference = (long) first - second;
```

the widening occurs before the operation, so the difference fits within the `long` range.

### 6.2. Computing the Difference in long and Narrowing Back to int Loses the Guarantee

This is still dangerous:

```java
return (int) ((long) first - second);
```

The difference itself may be accurate in `long`, but casting back to `int` drops the high bits. A positive difference outside the `int` range can turn negative.

A comparator does not need that difference. Using `Integer.compare` eliminates both the subtraction and the unnecessary narrowing.

### 6.3. Narrowing a long Difference to int Can Produce Zero

Two `long` values:

```text
0
4_294_967_296
```

differ by exactly `2^32`. The difference fits within the `long` range, but casting that difference down to `int` yields `0`.

When a comparator erroneously returns `0`:

- Sorting treats them as tied.
- A structure such as `TreeSet` can treat them as the same element.
- `TreeMap` can treat them as the same key under the comparator rule.

This is a **narrowing conversion** bug, even though the preceding `long` subtraction did not overflow.

### 6.4. Promoting int to long Does Not Solve the Full long Domain

The difference of two `int` numbers always fits in `long`, but the difference of any two `long` numbers can exceed the `long` range.

If the two operands are already `long`, no "cast to `long`" will widen the range. Use `Long.compare`.

### 6.5. Converting Through double Can Make Distinct Numbers Equal

`double` has a large range, but it cannot represent every `long` integer with full precision.

For example, the two consecutive integers at `2^53` and `2^53 + 1` are no longer distinguishable after conversion to `double` in the example below. Comparing the lossy results can return `0`.

Therefore:

- Overflow is not the only risk.
- "A numeric type with a larger range" does not mean "it preserves the required precision."
- If the data is `long`, compare it as `long`.

## 7. Program Verifying Casting and long Bugs

Create the file **`NumericConversionDemo.java`**:

```java
public class NumericConversionDemo {
    public static void main(String[] args) {
        int intLeft = Integer.MAX_VALUE;
        int intRight = -1;

        long castAfter = (long) (intLeft - intRight);
        long castBefore = (long) intLeft - intRight;
        int narrowedAgain = (int) castBefore;

        System.out.println("cast after subtraction = " + castAfter);
        System.out.println("cast before subtraction = " + castBefore);
        System.out.println("narrowed again = " + narrowedAgain);

        long zero = 0L;
        long distant = 1L << 32;
        System.out.println("narrowed long difference = "
                + (int) (zero - distant));
        System.out.println("Long.compare distinct values = "
                + Long.compare(zero, distant));

        long largest = Long.MAX_VALUE;
        long negative = -1L;
        System.out.println("overflowed long difference = " + (largest - negative));
        System.out.println("Long.compare correct direction = "
                + Long.compare(largest, negative));

        long first = 1L << 53;
        long next = first + 1;
        System.out.println("compare after double conversion = "
                + Double.compare((double) first, (double) next));
        System.out.println("compare exact long values = " + Long.compare(first, next));

        try {
            Math.subtractExact(intLeft, intRight);
        } catch (ArithmeticException exception) {
            System.out.println("subtractExact = "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 NumericConversionDemo.java
java -Dfile.encoding=UTF-8 NumericConversionDemo
```

Stdout:

```text
cast after subtraction = -2147483648
cast before subtraction = 2147483648
narrowed again = -2147483648
narrowed long difference = 0
Long.compare distinct values = -1
overflowed long difference = -9223372036854775808
Long.compare correct direction = 1
compare after double conversion = 0
compare exact long values = -1
subtractExact = ArithmeticException
```

### What Does Each Output Group Show?

| Group | Evidence |
| --- | --- |
| Cast after operation | The overflowed `int` result is preserved as-is when converted to `long` |
| Cast before operation | The difference of two `int` values is computed accurately in `long` |
| Cast back to `int` | Information is lost, and the sign can become wrong |
| Difference of two `long` values cast to `int` | Two distinct numbers can yield `0` |
| `long` overflow | Subtracting two valid `long` values can still flip the sign |
| Conversion to `double` | Two distinct `long` values can collapse into the same value |
| `subtractExact` | Overflow is reported via an exception, not turned into a valid comparison relation |

Different bugs need to be named accurately. A value narrowing to `0` does not necessarily mean the subtraction overflowed; the difference calculation itself may be exact while the cast is what corrupts the data.

## 8. Why subtractExact, abs, or signum Do Not Salvage Subtraction

### Math.subtractExact Validates Arithmetic, Not Full Ordering

`Math.subtractExact(first, second)` throws `ArithmeticException` if the difference exceeds the type's range.

That is useful when business logic truly requires an **exactly representable difference** and wants to reject invalid arithmetic. However, a comparator must be able to compare two valid numbers at opposite ends of the range, even when the distance between them is too large to fit in the same type.

Replacing `first - second` with `Math.subtractExact(first, second)` turns a silent wrong sign into a runtime failure; it does not replace `Integer.compare` or `Long.compare`.

### signum After an Overflowed Subtraction Still Reads the Wrong Sign

The following approach is still broken:

```java
return Integer.signum(first - second);
```

`signum` only reads the sign of the **result it receives**. If the subtraction result has already overflowed and flipped sign, normalizing it to `-1` or `1` does not recover the original meaning.

In this lesson, `Integer.signum` is used only to inspect or display the sign of a result; it is never used as a fix for overflowed subtraction.

### abs Loses Direction and Has Its Own Limits

`Math.abs(first - second)` cannot serve as an ascending comparator because absolute value discards information about which operand is larger.

Furthermore, the positive negation of `Integer.MIN_VALUE` cannot be represented as an `int`; taking the absolute value of that number has a corresponding limitation. You must understand method contracts rather than chaining them together to guess a sign.

## 9. Reversing Order Properly

A valid comparator can return any negative or positive value. Therefore, writing:

```java
return -order.compare(first, second);
```

is not a safe choice for an arbitrary comparator.

If the original result is `Integer.MIN_VALUE`, unary negation still yields `Integer.MIN_VALUE`, so the sign does not flip.

### Proper Approaches

- With `Integer.compare` or `Long.compare`, swap the order of the two arguments to reverse direction.
- With a `Comparator` object, use `reversed()`.
- When combining multiple criteria, decide whether to reverse the entire ordering or only a single criterion.

For example, given the rule:

```java
Comparator<Job> ascending = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .thenComparing(Job::id);
```

then:

- `ascending.reversed()` reverses the entire chain of criteria.
- Reversing the `priority` comparator first and then calling `thenComparing...` reverses only that priority criterion.

Changing where `reversed()` is called can change the meaning of the ordering, even though neither version overflows.

## 10. Comparing Multiple Criteria Without Adding or Subtracting Results

Combining multiple fields into a single arithmetic expression often causes bugs:

```java
return first.priority - second.priority
        + (int) (first.sequence - second.sequence);
```

It has multiple problems:

1. Each subtraction can overflow or be narrowed improperly.
2. A later criterion can overwhelm an earlier criterion.
3. Two differences can cancel each other out and return `0` even though the data differs.
4. The rule no longer clearly expresses which criterion takes precedence.

### Step-by-Step Comparison

Inside a comparison method body, a clean structure is:

```java
int result = Integer.compare(first.priority(), second.priority());
if (result != 0) {
    return result;
}

return Long.compare(first.sequence(), second.sequence());
```

The second criterion is consulted only when the first criterion is tied. If additional criteria are needed, continue following the exact same pattern.

### Using Type-Specific Comparator Factories

`comparingInt` and `comparingLong` express the same meaning as a chain:

```java
Comparator<Job> order = Comparator.comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .thenComparing(Job::id);
```

In this example, `id` is a tie-breaker criterion that determines the order among jobs with the same `priority` and `sequence`. Returning zero from a comparison must not be treated as a mere display detail; if the rule is used in a unique set or as a map key, it directly affects how elements are identified.

The example assumes both the job and `id` are non-`null`. If the data allows missing values, define an explicit policy and place it clearly in the appropriate comparator.

## 11. Complete Program: Safe Comparator and Order Reversal

Create the file **`SafeJobOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SafeJobOrderDemo {
    public record Job(String id, int priority, long sequence) {
    }

    public static void main(String[] args) {
        List<Job> input = List.of(
                new Job("A", Integer.MAX_VALUE, 0),
                new Job("B", Integer.MIN_VALUE, Long.MAX_VALUE),
                new Job("C", 0, Long.MAX_VALUE),
                new Job("D", 0, Long.MIN_VALUE),
                new Job("E", 0, Long.MIN_VALUE));

        Comparator<Job> ascending = Comparator.comparingInt(Job::priority)
                .thenComparingLong(Job::sequence)
                .thenComparing(Job::id);

        List<Job> jobs = new ArrayList<>(input);
        jobs.sort(ascending);
        System.out.println("ascending ids = " + ids(jobs));

        jobs.sort(ascending.reversed());
        System.out.println("reverse all ids = " + ids(jobs));

        Comparator<Job> priorityDescending = Comparator
                .comparingInt(Job::priority).reversed()
                .thenComparingLong(Job::sequence)
                .thenComparing(Job::id);

        jobs.sort(priorityDescending);
        System.out.println("reverse priority only ids = " + ids(jobs));

        Comparator<Integer> arbitraryMagnitude = (left, right) -> {
            if (left < right) {
                return Integer.MIN_VALUE;
            }
            if (left > right) {
                return Integer.MAX_VALUE;
            }
            return 0;
        };

        int wrongReverse = -arbitraryMagnitude.compare(1, 2);
        int safeReverse = arbitraryMagnitude.reversed().compare(1, 2);
        System.out.println("negated result sign = " + Integer.signum(wrongReverse));
        System.out.println("reversed comparator sign = " + Integer.signum(safeReverse));
    }

    private static List<String> ids(List<Job> jobs) {
        return jobs.stream().map(Job::id).toList();
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 SafeJobOrderDemo.java
java -Dfile.encoding=UTF-8 SafeJobOrderDemo
```

Stdout:

```text
ascending ids = [B, D, E, C, A]
reverse all ids = [A, C, E, D, B]
reverse priority only ids = [A, D, E, C, B]
negated result sign = -1
reversed comparator sign = 1
```

### Tracing the Job Order

- **Ascending:** `B` has the smallest priority; `A` has the largest. Jobs with priority `0` are ordered next by sequence and then by id.
- **Reverse all:** priority, sequence, and id are all reversed.
- **Reverse priority only:** priority is descending, while jobs sharing the same priority still follow ascending sequence and then ascending id.

The name `priority` does not by itself dictate whether larger or smaller numbers should be processed first. The program explicitly chooses ascending or descending direction; in a real system, align the meaning with business requirements.

### Why Is a Comparator with Arbitrary Result Magnitudes Still Valid?

`arbitraryMagnitude` returns:

- `Integer.MIN_VALUE` when smaller.
- `Integer.MAX_VALUE` when greater.
- `0` when equal.

Even though the magnitudes are asymmetric, the signs accurately describe the numerical ordering. The contract requires the right relationship among signs, not that two results be exact arithmetic negations of each other.

Direct negation fails to flip `Integer.MIN_VALUE`, whereas `reversed()` produces the proper direction. This example shows why you should not rely on an implicit assumption that an external comparator always returns `-1` or `1`.

## 12. When Does Subtraction Not Overflow?

You should not conclude that every subtraction is wrong. It is only unsafe as a general comparison technique when there is no guarantee on the value domain.

If two scores always fall within `1..100`, their difference lies in `-99..99`, which is safely representable as an `int`.

However, using subtraction still imposes an obligation to prove and maintain invariants:

- Where is the value domain validated?
- Is there any data ingestion path that bypasses validation?
- Could requirements later change to allow negative numbers or a wider range?
- Could the same method be reused for a different data type?
- Could adding a new criterion cause a combined arithmetic expression to exceed the range?

If the goal is simply comparison, `Integer.compare` is usually clearer and does not depend on whether the data domain expands in the future.

### Distinguishing Signed Numbers from Unsigned Interpretation

`Integer.compare` and `Long.compare` compare values as signed integers. If a business domain genuinely interprets bit patterns as unsigned numbers, Java provides operations such as `compareUnsigned`.

This is a choice about **data semantics**, not an ad-hoc workaround for an overflowing comparator. Never switch to unsigned comparison just because you encounter a negative value, as doing so can completely distort the ordering required by the domain.

## 13. Testing the Contract with Boundary Data

Useful checks include:

1. **Reflexivity:** `compare(x, x) == 0`.
2. **Antisymmetry (sign inversion on swap):** the sign of `compare(x, y)` must be the negation of the sign of `compare(y, x)`.
3. **Transitivity:** if `x > y` and `y > z`, then `x > z`.
4. **Consistency of tied elements:** if `compare(x, y) == 0`, the relationships of `x` and `y` to any `z` must agree.

The sample set should include negative numbers, positive numbers, `0`, equal values, and the extremes of the range.

### Complete Program

Create the file **`BoundaryContractDemo.java`**:

```java
import java.util.Comparator;

public class BoundaryContractDemo {
    public static void main(String[] args) {
        int[] samples = {
                Integer.MIN_VALUE, Integer.MIN_VALUE + 1, -1, 0,
                1, Integer.MAX_VALUE - 1, Integer.MAX_VALUE
        };

        Comparator<Integer> unsafe = (left, right) -> left - right;
        Comparator<Integer> safe = Integer::compare;

        System.out.println("subtraction passes samples = "
                + obeysContract(unsafe, samples));
        System.out.println("Integer.compare passes samples = "
                + obeysContract(safe, samples));
    }

    private static boolean obeysContract(
            Comparator<Integer> order, int[] samples) {
        for (int first : samples) {
            if (order.compare(first, first) != 0) {
                return false;
            }

            for (int second : samples) {
                int firstSecond = Integer.signum(order.compare(first, second));
                int secondFirst = Integer.signum(order.compare(second, first));

                if (firstSecond != -secondFirst) {
                    return false;
                }

                for (int third : samples) {
                    int firstThird = Integer.signum(order.compare(first, third));
                    int secondThird = Integer.signum(order.compare(second, third));

                    if (firstSecond > 0 && secondThird > 0 && firstThird <= 0) {
                        return false;
                    }

                    if (firstSecond == 0 && firstThird != secondThird) {
                        return false;
                    }
                }
            }
        }
        return true;
    }
}
```

Compile and run:

```text
javac -encoding UTF-8 --release 17 BoundaryContractDemo.java
java -Dfile.encoding=UTF-8 BoundaryContractDemo
```

Stdout:

```text
subtraction passes samples = false
Integer.compare passes samples = true
```

### Limitations of This Verification

The program checks pairs and triples within a finite sample set, stopping at the first violation.

- A `false` result is proof that a bug exists on at least one tested case.
- A `true` result only proves that the chosen samples passed the conditions checked in the program.
- It does not replace reasoning that the rule holds across the entire data domain.
- It does not test out-of-scope policies such as `null` handling, mutating objects after inserting them into a tree, or consistency with `equals`.

For standard integer comparators, reasoning based on direct relational comparison without subtraction is an essential complement to runtime testing.

When applying this lesson to project tests, you can use the same categories of boundary cases to build targeted test suites. There is no need to put a broken comparator into production code just to "see when the sorting algorithm throws an exception."

## 14. Self-Review Checklist When Writing compareTo or Comparator

| Question | Sign That a Fix Is Needed |
| --- | --- |
| Does it use `a - b` to produce the result? | Must either prove the value domain or switch to a type-appropriate compare method |
| Does it cast a `long` difference to `int`? | Can flip the sign or falsely return `0` |
| Does it widen to a larger type after subtraction? | Overflow may have already occurred before the cast |
| Does it convert `long` to `double` for comparison? | Risk of precision loss |
| Does it call `signum` on a difference? | Normalizing a wrong sign does not fix the subtraction |
| Does it negate the result of an arbitrary comparator? | `Integer.MIN_VALUE` does not flip sign under unary negation |
| Does it add comparison results across criteria? | Criteria can overwhelm or cancel each other out |
| Are boundary values included in tests? | Without them, small examples may mask overflow bugs |
| Is the ordering used by a uniqueness structure? | Must verify the exact meaning of `compare == 0` |

The goal of the review is to ensure the comparison rule accurately models the domain relationship, rather than merely surviving an incidental sort run.

## 15. Practice

### Exercise 1: Catch the Bug with Pairs of Numbers

Write down the mathematical value and the actual `int` value of:

```text
Integer.MAX_VALUE - (-1)
Integer.MIN_VALUE - 1
0 - Integer.MIN_VALUE
```

For each expression, determine whether the sign accurately describes the relation between the two operands. Verify with `Integer.compare`.

### Exercise 2: Distinguish Overflow from Narrowing

Choose:

```text
first  = 0L
second = 1L << 32
```

Compare the results of:

- The initial `long` difference.
- The difference after casting to `int`.
- `Long.compare(first, second)`.

Explain why two distinct values can be treated as tied by a broken comparator even though no overflow occurred during the `long` subtraction step.

### Exercise 3: Adjust the Job Ordering

Starting from `SafeJobOrderDemo`, implement a new requirement:

1. Priority ascending.
2. If priority is equal, sequence descending.
3. If still equal, id ascending.

Do not subtract values and do not negate an arbitrary comparator result. With the existing dataset, the resulting id order should be:

```text
[B, C, D, E, A]
```

Explain where to call `reversed()` so that only sequence is reversed without reversing the other criteria.

### Exercise 4: Extend the Contract Check to long

Write a check suite similar to `BoundaryContractDemo` for `long`, using the values:

```text
Long.MIN_VALUE, -1L, 0L, 1L, Long.MAX_VALUE
```

Add two values separated by exactly `2^32`. Compare a comparator that casts the difference to `int` against `Long.compare`, and identify which cases falsely return `0`.

The completion criterion is being able to explain the root cause of the failure, point out the reproducing inputs, and fix it with a rule that preserves the right sign across the required value domain.
