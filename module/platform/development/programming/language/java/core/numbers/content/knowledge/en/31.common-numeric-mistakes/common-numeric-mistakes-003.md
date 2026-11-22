# Why Are `Float.MIN_VALUE` and `Double.MIN_VALUE` Not the Smallest Negative Numbers?

## 1. Common Mistake: Confusing "MIN" with the Largest-Magnitude Negative Number

When programming in Java, learners are often used to `Integer.MIN_VALUE` being the smallest representable negative integer. From there, it is easy to mistakenly assume that `Float.MIN_VALUE` or `Double.MIN_VALUE` carries the same meaning.

**In reality in Java 17+:**

- `Float.MIN_VALUE` is the **smallest positive nonzero `float`**, approximately `1.4E-45`.
- `Double.MIN_VALUE` is the **smallest positive nonzero `double`**, approximately `4.9E-324`.
- The smallest finite negative `float` is **`-Float.MAX_VALUE`**, approximately `-3.4028235E38`.
- The smallest finite negative `double` is **`-Double.MAX_VALUE`**, approximately `-1.7976931348623157E308`.
- If special infinity values are included, `Float.NEGATIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are smaller than all finite numbers of the same type.

A typical bug:

```java
double max = Double.MIN_VALUE;  // WRONG if the data can consist entirely of negative numbers.

for (double value : new double[]{-8.0, -3.0, -11.0}) {
    if (value > max) {
        max = value;
    }
}
System.out.println(max); // 4.9E-324 — not even in the data!
```

Because `Double.MIN_VALUE > 0`, all three negative numbers are smaller than the initial value, so the loop never updates `max`.

**Goal of this article:** accurately understand the meanings of `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE`, infinity, and `NaN`; choose the right min/max initialization; build safe aggregation over empty sets and special values; and avoid using `MIN_VALUE` as an error tolerance threshold.

## 2. Comparison Table with Integer Types

| Constant | Approximate Value | Meaning |
| --- | --- | --- |
| `Integer.MIN_VALUE` | `-2147483648` | Smallest `int` |
| `Integer.MAX_VALUE` | `2147483647` | Largest `int` |
| `Long.MIN_VALUE` | `-9223372036854775808` | Smallest `long` |
| `Float.MIN_VALUE` | `1.4E-45` | Smallest nonzero **positive** `float` |
| `Float.MIN_NORMAL` | `1.1754944E-38` | Smallest positive **normal** `float` |
| `Float.MAX_VALUE` | `3.4028235E38` | Largest finite positive `float` |
| `-Float.MAX_VALUE` | `-3.4028235E38` | Smallest finite negative `float` |
| `Double.MIN_VALUE` | `4.9E-324` | Smallest nonzero **positive** `double` |
| `Double.MIN_NORMAL` | `2.2250738585072014E-308` | Smallest positive **normal** `double` |
| `Double.MAX_VALUE` | `1.7976931348623157E308` | Largest finite positive `double` |
| `-Double.MAX_VALUE` | `-1.7976931348623157E308` | Smallest finite negative `double` |
| `Float.NEGATIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | `-Infinity` | Special value smaller than any finite number |
| `Float.POSITIVE_INFINITY`, `Double.POSITIVE_INFINITY` | `Infinity` | Special value larger than any finite number |

The values above use the format Java typically prints via `Float.toString`/`Double.toString`; these constants are stored in IEEE 754 binary, so they do not necessarily have exact short decimal representations like the printed strings.

**Key takeaway:** for integer types, `MIN_VALUE` is the negative lower bound of the value range. For `float` and `double`, `MIN_VALUE` is instead the **smallest nonzero positive magnitude** of the floating-point type, including the subnormal region. The naming is a standardized API characteristic; do not infer its meaning from the identically named constant in integer types.

## 3. Why Is the Smallest Nonzero Positive Number So Tiny?

`float` and `double` are IEEE 754 binary floating-point types, which do not store numbers as a contiguous segment with uniform spacing. The representation has a sign, an exponent, and a significand, so resolution depends on the magnitude of the number.

Regular finite values (**normal**) have an exponent and significant bits following normal rules. As values approach very close to 0, Java also has **subnormal** (*denormalized*) values to represent magnitudes smaller than the normal lower bound; they have fewer significant digits/bits.

- `Float.MIN_NORMAL` is the smallest positive bound that is still **normal**.
- `Float.MIN_VALUE` is much smaller than `Float.MIN_NORMAL` and is the smallest nonzero **subnormal** positive number.
- `Double.MIN_NORMAL` and `Double.MIN_VALUE` share the same relationship.

Example in Java:

```java
System.out.println(Float.MIN_VALUE);       // 1.4E-45
System.out.println(Float.MIN_NORMAL);      // 1.1754944E-38
System.out.println(Double.MIN_VALUE);      // 4.9E-324
System.out.println(Double.MIN_NORMAL);     // 2.2250738585072014E-308
```

This snippet is **embedded** inside a method. `Float.MIN_NORMAL` is not the smallest negative number; the word `NORMAL` simply distinguishes normal numbers from subnormal ones. `MIN_VALUE` is **not** the smallest positive number *in the mathematical real-number sense* (there is no smallest positive number on the real line); it is merely the smallest nonzero value representable by `float`/`double` in Java.

### 3.1. The Key Number Line

Ordered by **numerical order**:

```text
-Infinity
   <
-Double.MAX_VALUE
   <
... negative finite numbers ...
   <
-Double.MIN_VALUE
   <
-0.0 / +0.0 (equal under == comparison)
   <
Double.MIN_VALUE
   <
... positive finite numbers ...
   <
Double.MAX_VALUE
   <
+Infinity
```

This diagram illustrates numerical ordering; under `Double.compare`, `-0.0` is ordered before `+0.0`. `NaN` does not lie on this real number line. For `<`, `>`, and `==` with `NaN`, behavior does not follow ordinary linear ordering (see Section 6).

`Double.MIN_VALUE` sits **just on the positive side of 0** among representable values, not at the deepest negative end.

### 3.2. `Math.nextUp` and `Math.nextDown` Clarify the Bounds

```java
System.out.println(Math.nextUp(0.0));   // 4.9E-324
System.out.println(Math.nextDown(0.0)); // -4.9E-324
```

`Math.nextUp(0.0)` returns the next representable `double` value greater than 0, which is `Double.MIN_VALUE`. `Math.nextDown(0.0)` returns the next value smaller than 0, namely `-Double.MIN_VALUE`. **`-Double.MIN_VALUE` is the negative number closest to 0 while still nonzero**, not the smallest negative number.

Similarly, `Math.nextDown(-Double.MAX_VALUE)` transitions to `Double.NEGATIVE_INFINITY`: there is no **finite** `double` smaller than `-Double.MAX_VALUE`.

## 4. Bugs When Initializing Maximum with `MIN_VALUE`

### 4.1. The Most Obvious Bug: All Negative Data

```java
double[] temperatures = {-8.0, -3.0, -11.0};
double maximum = Double.MIN_VALUE; // Wrong initialization policy.

for (double temperature : temperatures) {
    if (temperature > maximum) {
        maximum = temperature;
    }
}
System.out.println(maximum); // 4.9E-324 — wrong!
```

The correct value must be **`-3.0`**. If the code uses `Float.MIN_VALUE`, the exact same phenomenon occurs for a `float[]` of all negative numbers.

### 4.2. Symmetric Mistake: Using `MIN_VALUE` to Initialize Minimum Is Also Wrong

```java
double[] positives = {8.0, 3.0, 11.0};
double minimum = Double.MIN_VALUE; // Wrong: smaller than every element.

for (double value : positives) {
    if (value < minimum) {
        minimum = value;
    }
}
System.out.println(minimum); // 4.9E-324 — wrong, correct is 3.0.
```

The name `MIN_VALUE` sounds like "the smallest element", yet it **does not mean** it is an appropriate initial constant for a min-finding algorithm. If an algorithm needs to find the min/max of data, it must ensure the result belongs to the data and handle the empty case properly.

### 4.3. Is Switching to `-Double.MAX_VALUE` Enough?

For **data guaranteed to be finite and non-empty**, initializing:

```java
double maximum = -Double.MAX_VALUE;
```

can be valid for finding the maximum. However, if the data contains `Double.NEGATIVE_INFINITY` and no finite numbers, `-Double.MAX_VALUE` is greater than every element: you still get the wrong result because the sentinel does not belong to the data. If the array is empty, the sentinel is also returned as an extremum despite there being no elements.

Similarly:

```java
double minimum = Double.MAX_VALUE;
```

is wrong if every element is `Double.POSITIVE_INFINITY`, or if the array is empty and the result is treated as a real minimum.

`Double.NEGATIVE_INFINITY` can serve as a max initialization sentinel, and `Double.POSITIVE_INFINITY` as a min initialization sentinel in some algorithms, but **a data-present flag is needed** to distinguish an empty set from an input consisting solely of infinities. If the data domain includes `NaN`, a separate handling policy is also required.

A usually more maintainable solution: **take the first value when data exists**, or use a stream returning `OptionalDouble` (Section 5).

## 5. Choosing Ways to Find `min`/`max` Without Relying on Wrong Sentinels

### 5.1. Using `DoubleStream.min()` and `max()`

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

OptionalDouble min = DoubleStream.of(-8.0, -3.0, -11.0).min();
OptionalDouble max = DoubleStream.of(-8.0, -3.0, -11.0).max();

System.out.println(min.orElseThrow()); // -11.0
System.out.println(max.orElseThrow()); // -3.0
```

This is **embedded** code. `min()`/`max()` are terminal operations and return `OptionalDouble` because the source **may be empty**. Do not reuse the same stream after a terminal operation: create a new stream from the array/list or choose `summaryStatistics()` if you need multiple statistics in one pass.

```java
OptionalDouble none = DoubleStream.empty().max();
System.out.println(none.isEmpty()); // true
```

An empty source is clearly represented via `Optional` rather than faking a number as the result. If business rules require at least one value, you can use `orElseThrow(() -> new IllegalArgumentException("Empty data"))`. If empty is valid, return the `Optional` to the caller. `orElse(0.0)` is appropriate **only when business logic genuinely defines the default value as 0**, because 0 is also a valid data value.

### 5.2. Using the First Value and a Presence Flag

When you need a custom loop (for example, validating data while finding the max), use a `found` flag:

```java
boolean found = false;
double maximum = 0.0; // Initial value is unused while !found.

for (double value : values) {
    if (!found || Double.compare(value, maximum) > 0) {
        maximum = value;
        found = true;
    }
}

OptionalDouble result =
        found ? OptionalDouble.of(maximum) : OptionalDouble.empty();
```

This is **embedded** code assuming `double[] values` and `import java.util.OptionalDouble;`. Since `!found` always wins on the first element, `0.0` is merely a memory placeholder and is never mistaken for a data result.

**Keep in mind, however:** `Double.compare` defines an order even for `NaN` (placing `NaN` greater than every numeric value) and for the two signed zeros. Therefore, the loop above does not automatically share the same `NaN` policy as `DoubleStream.min/max`. When you want to reject `NaN`, check before comparing; when you want `NaN` to propagate, implement that policy explicitly. Do not swap the two approaches without comparing their contracts.

### 5.3. When Only Finite Data Is Accepted

If the input domain must not contain `NaN` or `±Infinity`, validate it:

```java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Only finite numbers are accepted");
}
```

After validation, the function can find extrema using `Double.compare` or directly with `<`/`>`, depending on whether `-0.0` and `+0.0` need to be distinguished. Do not silently drop non-finite values by default if they indicate upstream errors (such as division by zero or corrupted sensor data).

## 6. Three Special `double` Cases: Infinity, `NaN`, and Signed Zero

### 6.1. Infinity and Finite Bounds

`Double.MAX_VALUE` is the largest **finite** positive number; it is not `Double.POSITIVE_INFINITY`. `-Double.MAX_VALUE` is the smallest finite negative number; it is not `Double.NEGATIVE_INFINITY`.

```java
System.out.println(Double.NEGATIVE_INFINITY < -Double.MAX_VALUE); // true
System.out.println(Double.POSITIVE_INFINITY > Double.MAX_VALUE);  // true
```

If data can contain infinity, you must not return `-Double.MAX_VALUE` as the max of a source containing only `-Infinity`. Likewise, the min of a source containing only `+Infinity` must be `+Infinity` if the contract permits infinity. `Math.min` and `DoubleStream.min` do not reject infinity automatically.

### 6.2. `NaN` Is Not a Real Number and Does Not Compare via `<`/`>`

`Double.NaN` (Not a Number) is a special value:

```java
double invalid = Double.NaN;

System.out.println(invalid < 0.0);          // false
System.out.println(invalid > 0.0);          // false
System.out.println(invalid == Double.NaN);  // false
System.out.println(Double.isNaN(invalid));  // true
```

With primitive comparison operators, even `NaN == NaN` is `false`. A loop using `if (x > current)` can **skip over** `NaN`; this is dangerous if `NaN` indicates an invalid measurement and ought to fail.

In Java 17, `DoubleStream.min/max` **returns `NaN` if the source contains any `NaN` value**, even when finite values are also present. `Math.min`/`Math.max` on `double` also returns `NaN` if either operand is `NaN`.

```java
double min = java.util.stream.DoubleStream
        .of(5.0, Double.NaN, -2.0)
        .min()
        .orElseThrow();

System.out.println(min); // NaN
```

Here `OptionalDouble` **has a value**, just the special value `NaN`; `isPresent()` does not mean "valid data".

If business rules require ignoring `NaN`, apply `.filter(v -> !Double.isNaN(v))` and decide what happens if the filtered result is empty; if business rules require reporting an error, throw an exception as soon as it is detected. Do not pick a policy just because it makes the loop faster.

### 6.3. `-0.0` and `+0.0` Have Different Representations

```java
System.out.println(-0.0 == +0.0);         // true
System.out.println(Double.compare(-0.0, +0.0) < 0); // true

System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
```

Both zeros are equal under `==`, but `Double.compare` orders `-0.0` below `+0.0`. `Math.min`/`Math.max` and `DoubleStream.min/max` define rules for signed zeros. If you replace these APIs with a loop, test `-0.0`/`+0.0` cases so you do not inadvertently change semantics when element order changes.

None of the issues above occur in `int` in the same way: `int` has no `NaN`, no infinity, and no separate negatively signed zero.

## 7. `Float.MIN_VALUE` and `Double.MIN_VALUE` Are Also Not Epsilons for Approximate Equality

A related misconception is writing:

```java
boolean approximatelyEqual =
        Math.abs(a - b) < Double.MIN_VALUE; // Almost always far too strict.
```

This is illustrative code assuming `double a` and `double b` already exist. `Double.MIN_VALUE` describes **the distance from 0 to the smallest nonzero positive number**, not an absolute rounding tolerance suitable for all operations and all magnitudes.

Around `1.0`, the distance to the next representable `double` upward is:

```java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
```

It is vastly larger than `Double.MIN_VALUE` and `Float.MIN_VALUE`. `Math.ulp(x)` describes the size of one unit in the last place near `x`, which differs from a universal "business epsilon".

### 7.1. Approximate Equality Policy Must Be Problem-Driven

An **illustrative** approach for finite numbers when the application has defined tolerances:

```java
static boolean approximatelyEqualFinite(
        double a, double b, double absTolerance, double relTolerance) {

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("Only finite numbers can be compared");
    }
    if (!Double.isFinite(absTolerance) || absTolerance < 0.0
            || !Double.isFinite(relTolerance) || relTolerance < 0.0) {
        throw new IllegalArgumentException("Invalid tolerance");
    }
    if (a == b) { // Includes +0.0 == -0.0 per the example policy.
        return true;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(absTolerance, relTolerance * scale);
}
```

This is an **embedded** method for a defined finite domain. For extremely large values, subtraction or tolerance multiplication can overflow to infinity, so a comparator requiring strict arithmetic bounds must handle domains and intermediate calculations more carefully. The formula is only a starting point when business rules permit defined absolute and relative errors—**not a universal band-aid** for every numeric test.

If exact comparison of currency or integers is needed, use the appropriate representation (`BigDecimal`/integer minor units) and matching comparison rules; do not use an epsilon to mask data loss from type conversions.

## 8. Complete Java 17+ Program and Execution Output

Save as **`FloatingMinimumDemo.java`**:

```java
import java.util.OptionalDouble;

public class FloatingMinimumDemo {

    // Contract: accepts infinities, but rejects NaN;
    // returns Optional.empty() when there are no elements.
    static OptionalDouble maximumRejectNaN(double[] values) {
        boolean found = false;
        double maximum = 0.0;

        for (double value : values) {
            if (Double.isNaN(value)) {
                throw new IllegalArgumentException("NaN is not allowed");
            }

            if (!found || Double.compare(value, maximum) > 0) {
                maximum = value;
                found = true;
            }
        }

        return found
                ? OptionalDouble.of(maximum)
                : OptionalDouble.empty();
    }

    public static void main(String[] args) {
        System.out.println("Float.MIN_VALUE = " + Float.MIN_VALUE);
        System.out.println("-Float.MAX_VALUE = " + (-Float.MAX_VALUE));
        System.out.println("Double.MIN_VALUE = " + Double.MIN_VALUE);
        System.out.println("-Double.MAX_VALUE = " + (-Double.MAX_VALUE));

        double[] values = {-8.0, -3.0, -11.0};
        double wrongMax = Double.MIN_VALUE;

        for (double value : values) {
            if (value > wrongMax) {
                wrongMax = value;
            }
        }

        System.out.println("wrong max = " + wrongMax);
        System.out.println("correct max = "
                + maximumRejectNaN(values).orElseThrow());
        System.out.println("empty = "
                + maximumRejectNaN(new double[0]).isEmpty());
        System.out.println("only -Infinity = "
                + maximumRejectNaN(
                        new double[]{Double.NEGATIVE_INFINITY})
                        .orElseThrow());
        System.out.println("signed zero max = "
                + maximumRejectNaN(new double[]{-0.0, 0.0})
                        .orElseThrow());
        System.out.println("nextUp zero = " + Math.nextUp(0.0));

        try {
            maximumRejectNaN(new double[]{1.0, Double.NaN});
        } catch (IllegalArgumentException e) {
            System.out.println("NaN policy = rejected");
        }
    }
}
```

Compile and run:

```bash
javac FloatingMinimumDemo.java
java FloatingMinimumDemo
```

Standard stdout on Java 17+:

```text
Float.MIN_VALUE = 1.4E-45
-Float.MAX_VALUE = -3.4028235E38
Double.MIN_VALUE = 4.9E-324
-Double.MAX_VALUE = -1.7976931348623157E308
wrong max = 4.9E-324
correct max = -3.0
empty = true
only -Infinity = -Infinity
signed zero max = 0.0
nextUp zero = 4.9E-324
NaN policy = rejected
```

### Interpreting the Output

1. The first four lines clearly distinguish the **smallest nonzero positive** value from the **smallest finite negative** value for `float` and `double`.
2. `wrong max` exposes the common bug: the sentinel `Double.MIN_VALUE` is greater than every negative element, yielding the wrong result.
3. `maximumRejectNaN` picks the first element before comparing remaining elements, returning `-3.0` for the sample data.
4. An empty array returns `OptionalDouble.empty()` instead of a fake sentinel.
5. Data containing only `-Infinity` is returned accurately because the contract permits infinity.
6. `Double.compare` preserves standard ordering between `-0.0` and `+0.0`, so `max` selects `+0.0`.
7. `Math.nextUp(0.0)` proves `Double.MIN_VALUE` lies directly on the positive side of 0.
8. `NaN` is rejected according to the **illustrative function's** policy. This differs from `DoubleStream.max()`, which returns `NaN` when the source contains `NaN`; choose one policy explicitly when designing an API.

Writing a manual loop is not always better than `DoubleStream.max()`: the example here is meant to illustrate input conditions and result-selection rules. For typical business code, prefer standard APIs if their `NaN`/infinity and empty-result contracts match your needs.

## 9. Choosing the Right Initialization for Each Contract

| Data and Result Requirement | Recommended Implementation | Notes |
| --- | --- | --- |
| Find `max` of non-empty array, **finite numbers only** | Start with first element, or `-Double.MAX_VALUE` when domain is proven | Guard empty array; validate finite |
| Find `min` of non-empty array, **finite numbers only** | Start with first element, or `Double.MAX_VALUE` when domain is proven | Never use `Double.MIN_VALUE` |
| May be empty and may contain ±infinity | `DoubleStream.min/max()` returning `OptionalDouble` | `NaN` propagates per the API |
| May be empty; `NaN` is an error; ±infinity valid | `found` flag + `Double.compare` + reject `NaN` | As in the example program |
| Source accepts only finite numbers | Validate `Double.isFinite` then compute | Do not silently discard bad elements |
| Need smallest finite value of the type's range | `-Double.MAX_VALUE` / `-Float.MAX_VALUE` | Not the `min` result of an arbitrary array |
| Need special value lower than every finite number | `Double.NEGATIVE_INFINITY` / `Float.NEGATIVE_INFINITY` | Distinguish from real values in the source |
| Need next representable positive number after 0 | `Double.MIN_VALUE` / `Float.MIN_VALUE` | Only this is the right use of `MIN_VALUE` |

### When Is a Sentinel Still Reasonable?

A sentinel can be a **technical value** in an algorithm when you know the exact input domain and have a way to mark an empty set. For instance, a reduction needing an identity value `-Infinity` for max can make sense on `double`s if the `NaN` handling contract is documented. However, an identity is not "the largest element of an empty sequence", and an empty state must not be confused with real data.

If an API returns data to a caller, `OptionalDouble` generally communicates "no extremum" much more clearly than emitting an out-of-context `-Infinity`.

## 10. Related Mistakes to Recognize

**Mistake 1: `Float.MIN_VALUE` is the negative limit.** Wrong because the constant is positive. The lowest finite negative number is `-Float.MAX_VALUE`.

**Mistake 2: `-Float.MIN_VALUE` is the lowest negative number.** Wrong because this is the nonzero negative number closest to 0; it has a tiny magnitude. Do not confuse **smallest negative by numerical order** with **negative number of smallest absolute magnitude**.

**Mistake 3: `Double.MIN_NORMAL` is the smallest representable positive number.** Wrong: there are smaller positive subnormal numbers, down to `Double.MIN_VALUE`.

**Mistake 4: `Double.MAX_VALUE` means infinity.** Wrong: `Double.MAX_VALUE` is finite. Operations exceeding `double` range can yield `Infinity`, but this constant is not infinity.

**Mistake 5: Returning a sentinel when data is empty.** Wrong when the contract requires "no data"; represent absence or throw an error.

**Mistake 6: Using `Double.MIN_VALUE` as an approximate-comparison threshold.** Far too small compared to representable spacing in most domains; thresholds must come from the problem's allowable error.

**Mistake 7: Using `Math.abs(Double.MIN_VALUE)` to get a negative number.** `Math.abs` keeps values non-negative, so it cannot create a negative bound. Negation needs the `-` operator, yet `-Double.MIN_VALUE` is still near 0, not the lowest.

**Mistake 8: Comparing via `Double.compare` and forgetting `NaN`.** `Double.compare` provides a deterministic ordering, but it treats `NaN` as larger than all numeric values; that may not match sensor/business rules.

**Mistake 9: Ignoring `-0.0` when replacing `Math.min/max` with `if (a < b)` or `if (a > b)`.** Those operators do not distinguish `-0.0` from `+0.0`; output sign of zero can depend on data order.

**Mistake 10: Truncating `double` to `float` when creating bounds.** `-Double.MAX_VALUE` is outside `float`'s finite range; casting to `float` produces `-Infinity`, unlike `-Float.MAX_VALUE`.

## 11. Testing Boundary Inputs to Prevent Regression

When writing or reviewing a min/max function, test at least:

1. **All negative:** `{-8.0, -3.0, -11.0}` must yield max `-3.0`, min `-11.0`.
2. **All positive:** `{8.0, 3.0, 11.0}` must yield min `3.0`, max `11.0`.
3. **Only zero:** `{0.0}` must return 0, not `Double.MIN_VALUE`.
4. **Empty array:** return empty `Optional` or the defined error, not an arbitrary sentinel.
5. **Subnormals:** `{Double.MIN_VALUE, 0.0}` must be handled according to the appropriate sign/zero policy.
6. **Infinite data:** `{-Infinity}` and `{+Infinity}` to ensure finite bounds are not mistakenly returned.
7. **NaN:** `{1.0, NaN}` must propagate `NaN`, be rejected, or be filtered strictly per contract, not by accident of comparison operators.
8. **Signed zeros:** `{-0.0, +0.0}` test selection and string/bit representation if sign matters.
9. **Finite extreme bounds:** `{-Double.MAX_VALUE, Double.MAX_VALUE}` and overflow cases when computing derived values from bounds.
10. **Separate `float` type:** repeat cases with `Float.MIN_VALUE`, `Float.MAX_VALUE`, and ±infinity; do not assume every type conversion preserves range.

Tests should verify expected values against the **contract**. If signed zeros must be distinguished, `==` is insufficient; check `Double.compare` or raw bits. When checking for `NaN`, use `Double.isNaN`, never `actual == Double.NaN`.

## 12. Self-Assessment Exercises

1. Is `Float.MIN_VALUE > 0.0f` true or false? Can `Float.MIN_VALUE` be the smallest negative number?
2. Distinguish `Double.MIN_VALUE`, `Double.MIN_NORMAL`, `-Double.MAX_VALUE`, and `Double.NEGATIVE_INFINITY`. Which value is the lowest **finite** bound?
3. Given `{-10.0, -20.0, -5.0}`, what does a loop using `double max = Double.MIN_VALUE` return? Why?
4. If an operation accepts `-Infinity` but rejects `NaN`, why is `double max = -Double.MAX_VALUE` an unsafe sentinel for all sources?
5. For an empty source, why does `DoubleStream.empty().max()` return `OptionalDouble.empty()` instead of `-Infinity`?
6. What value does `Math.nextUp(0.0)` return? Which negative number corresponds to `Math.nextDown(0.0)`?
7. Why might an approximate equality function using `Double.MIN_VALUE` reject even two numbers that look nearly equal around `1.0`?
8. Write a `minimumRejectNaN(double[])` method similar to `maximumRejectNaN` in the article, using `Double.compare` and `OptionalDouble`. Test `+Infinity`, `-0.0`, empty source, and `NaN`.
9. Explain why `DoubleStream.of(2.0, Double.NaN).max().isPresent()` still returns `true` even though the actual max is `NaN`.

**Summary Answers:** (1) True; this constant is positive. (2) `Double.MIN_VALUE` is the smallest positive subnormal number; `MIN_NORMAL` is the smallest positive normal number; `-MAX_VALUE` is the lowest finite negative bound; `NEGATIVE_INFINITY` is smaller than finite numbers but is not finite. (3) Returns `4.9E-324` wrongly because all elements are negative. (4) For a source with only `-Infinity`, the finite sentinel is greater than the true value. (5) The extremum of an empty source does not exist. (6) `+Double.MIN_VALUE`, `-Double.MIN_VALUE`. (7) Representable spacing around 1 is vastly larger than `Double.MIN_VALUE`. (8) Use a `found` flag, check for `NaN`, and change `> 0` to `< 0` in `Double.compare`. (9) The `Optional` holds an element; `NaN` is a special `double` value, distinct from missing data.

## 13. Quick Takeaways

`Float.MIN_VALUE` and `Double.MIN_VALUE` are both **positive**, tiny, and nonzero; they are not negative bounds of the types. When you need the **lowest finite number** of `float`/`double`, use `-Float.MAX_VALUE` or `-Double.MAX_VALUE`. When you need a special value **smaller than every finite number**, use `NEGATIVE_INFINITY` with clear awareness of the value range.

When finding extrema of real data, the safest approaches are usually `DoubleStream.min/max()` returning `OptionalDouble` or a loop initialized with **the first element**, combined with explicit policies for emptiness, infinity, `NaN`, and signed zeros. Never use a constant named `MIN_VALUE` as a sentinel just because of the word "MIN".

Java SE 17 Standard References:
- [`Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): exact meanings of `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE`, ±infinity, and `NaN`.
- [`Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `min`, `max`, `nextUp`, `nextDown`, `ulp`.
- [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html), [`OptionalDouble`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalDouble.html): safe extrema on potentially empty sources.
