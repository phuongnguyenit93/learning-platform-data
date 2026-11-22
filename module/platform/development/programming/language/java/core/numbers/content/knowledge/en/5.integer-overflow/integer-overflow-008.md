# `Math.abs` with `MIN_VALUE` and Choosing `absExact` in Java

`Math.abs(x)` looks like a simple way to get an absolute value, yet for **`Integer.MIN_VALUE`** and **`Long.MIN_VALUE`** it cannot return the corresponding positive number within the same integer type. Surprisingly, **`Math.abs` does not throw an exception**: the result remains `MIN_VALUE` itself, which is a negative number.

```java
System.out.println(Math.abs(Integer.MIN_VALUE)); // -2147483648
System.out.println(Math.abs(Long.MIN_VALUE));    // -9223372036854775808
```

If an algorithm relies on the assumption "`Math.abs` is always non-negative," bugs can appear in array indexing, distance checks, magnitude-based sorting, hash-table bucket selection, or limit enforcement. **`Math.absExact`** (available in Java 17+) specifically detects when the absolute value cannot be represented in the input integer type: it **throws `ArithmeticException`** instead of returning an unexpected negative value.

This lesson belongs to the **Overflow and Boundary Checks** section of **Java core – numbers**, focusing on the two's complement mechanism, the difference between `abs` and `absExact`, appropriate handling choices, and pitfalls when computing operations before taking an absolute value.

## 1. Why Doesn't `MIN_VALUE` Have a Positive Absolute Value in the Same Type?

Java's signed integer types use fixed-width **two's complement** representation. The value range is asymmetric around 0:

| Type | Minimum Value | Maximum Value | Mathematical Absolute Value of `MIN_VALUE` |
| --- | ---: | ---: | ---: |
| 32-bit `int` | `-2_147_483_648` | `2_147_483_647` | `2_147_483_648` |
| 64-bit `long` | `-9_223_372_036_854_775_808` | `9_223_372_036_854_775_807` | `9_223_372_036_854_775_808` |

For an `n`-bit signed integer, the range is from `-2^(n-1)` to `2^(n-1)-1`. Therefore, the absolute value of `MIN_VALUE` equals `2^(n-1)`, **exceeding `MAX_VALUE` by exactly one**.

32-bit example:

```text
Integer.MIN_VALUE  = -2147483648
int bits           = 10000000 00000000 00000000 00000000
Math negation      = +2147483648 (exceeds Integer.MAX_VALUE)
32-bit result      = 10000000 00000000 00000000 00000000
int interpretation = -2147483648
```

Primitive integer addition, subtraction, and negation in Java have well-defined behavior over fixed bit widths. Unary negation `-Integer.MIN_VALUE` also returns `Integer.MIN_VALUE` without throwing. `Math.abs(int)` uses the same value range and **does not automatically check for overflow**.

### Values "near `MIN_VALUE`" still behave normally

```java
int a = Integer.MIN_VALUE + 1;
System.out.println(Math.abs(a)); // 2147483647
```

Only `Integer.MIN_VALUE` lacks a representable positive counterpart in `int`; likewise, only `Long.MIN_VALUE` is that special case for `long`. Every other signed integer value, including `-MAX_VALUE`, has an absolute value within its type's range.

## 2. What Does `Math.abs` Actually Guarantee?

In Java, `java.lang.Math` has overloads `abs(int)`, `abs(long)`, `abs(float)`, and `abs(double)`. For **`int` and `long`**, the result is the non-negative magnitude of the argument in every case **except that type's own `MIN_VALUE`**, where the method returns `MIN_VALUE`.

```java
int normal = Math.abs(-42);                  // 42
int zero = Math.abs(0);                      // 0
int edge = Math.abs(Integer.MIN_VALUE);      // Integer.MIN_VALUE
long longEdge = Math.abs(Long.MIN_VALUE);    // Long.MIN_VALUE
```

These lines are a Java snippet placed inside a method. They compile and do not throw an exception on `MIN_VALUE`.

This has a crucial consequence: **an `int` result from `Math.abs(int)` cannot be treated as an invariant "`result >= 0`"** unless `Integer.MIN_VALUE` has been excluded from the inputs. The same holds for `long`.

A check like the following can catch the error after it occurs, yet still does not yield a valid value:

```java
int magnitude = Math.abs(value);
if (magnitude < 0) {
    throw new ArithmeticException("Magnitude does not fit in int");
}
```

Instead of writing this check yourself when you want an exception, Java already provides **`Math.absExact(value)`**.

## 3. `Math.absExact`: Detecting Overflow Instead of Returning `MIN_VALUE`

Java provides two overloads: **`Math.absExact(int)`** and **`Math.absExact(long)`**. Both are available in Java 17. They return the absolute value when the result is representable in the input type, and **throw `ArithmeticException`** if the input equals that type's `MIN_VALUE`.

```java
int a = Math.absExact(-42);       // 42
long b = Math.absExact(-42L);     // 42L

// Math.absExact(Integer.MIN_VALUE) → ArithmeticException
// Math.absExact(Long.MIN_VALUE)    → ArithmeticException
```

Comparing the options:

| Input | `Math.abs` | `Math.absExact` |
| --- | --- | --- |
| `-42` (`int`) | `42` | `42` |
| `0` (`int`) | `0` | `0` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE + 1` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE` | `-2147483648` | Throws `ArithmeticException` |
| `Long.MIN_VALUE` | `-9223372036854775808` | Throws `ArithmeticException` |

Use `absExact` when the operation contract requires **returning a non-negative integer of the same type or failing**. For example: an API must return an `int` deviation magnitude, and `Integer.MIN_VALUE` is considered an invalid input.

Key point: `Math.absExact` **cannot return `2147483648` as an `int`**. It signals that the result is unrepresentable. If your problem truly needs to store that absolute value, choose a sufficiently wide type before computing.

### There is no `Math.absExact(float)` or `Math.absExact(double)`

`Math.absExact` is for the integer types `int` and `long`; there are no `float`/`double` overloads. For floating-point numbers, rules involving `NaN`, infinities, and `+0.0`/`-0.0` differ from integer overflow. Do not use an integer method to infer semantics for floating point.

## 4. When You Need the True Absolute Value of `Integer.MIN_VALUE`: Promote First

The value `2147483648` exceeds `int` yet **fits inside `long`**. Therefore, if the source is `int` and the output may be `long`, convert to `long` **before calling `Math.abs`**:

```java
int value = Integer.MIN_VALUE;

long correct = Math.abs((long) value);
// correct == 2147483648L
```

Do not swap the order:

```java
int value = Integer.MIN_VALUE;

long tooLate = (long) Math.abs(value);
// tooLate == -2147483648L: Math.abs(int) already failed expectations before the cast.
```

These two approaches differ in **which overload is selected**:

- `Math.abs((long) value)`: the argument is `long`, calling `Math.abs(long)`. `-2147483648L` has an absolute value that fits in `long`.
- `(long) Math.abs(value)`: the initial argument is `int`, calling `Math.abs(int)`; widening to `long` afterward merely preserves the negative value already returned.

The same principle applies to negation:

```java
long correct = -(long) Integer.MIN_VALUE; // 2147483648L
long tooLate = (long) (-Integer.MIN_VALUE); // -2147483648L
```

Overload selection and conversion order determine correctness, not merely looking at the receiving variable's type.

### Should you choose `Math.abs` or `Math.absExact` after widening?

If the goal of processing an `int` is to **return an exact `long` absolute value**, `Math.abs((long) value)` suffices because every `int` and its absolute value fit in `long`. `Math.absExact((long) value)` is also valid, though the `long` overload's overflow case cannot happen when the original input is guaranteed to be an `int`.

If the goal is to **return an `int` and fail fast when it does not fit**, use `Math.absExact(value)`. Choose according to the return contract and how the application handles out-of-range data.

## 5. For `Long.MIN_VALUE`, Widening to `long` Is No Longer Enough

The absolute value of `Long.MIN_VALUE` is `9223372036854775808`, which is larger than `Long.MAX_VALUE` by one. There is no primitive Java integer type wider than `long`.

There are three design options depending on requirements:

1. **Report overflow:** `Math.absExact(longValue)` throws `ArithmeticException` when given `Long.MIN_VALUE`.
2. **Represent exact magnitude:** use `BigInteger` and **convert before taking the absolute value**.
3. **Handle as unsigned under an explicit bit contract:** dedicated unsigned operations may be needed, without treating signed `long` as a positive number larger than `Long.MAX_VALUE`.

Correct example with `BigInteger`:

```java
import java.math.BigInteger;

// Placed inside a Java method:
long value = Long.MIN_VALUE;

BigInteger magnitude = BigInteger.valueOf(value).abs();
// 9223372036854775808
```

`BigInteger.valueOf(value)` takes the signed `long` value as-is and creates an integer object; `BigInteger.abs()` can produce an absolute value exceeding 64 bits. Conversely, the following order is wrong:

```java
long value = Long.MIN_VALUE;
BigInteger wrong = BigInteger.valueOf(Math.abs(value));
// wrong is still -9223372036854775808.
```

Passing an already-mishandled value into a larger type cannot recover the original mathematical intent.

## 6. More Dangerous Trap: An Expression Already Overflowed Before Calling `absExact`

`Math.absExact` checks only the **absolute value of the value it actually receives**. The method cannot tell if the addition, subtraction, or multiplication producing its argument already overflowed earlier.

Consider computing the absolute distance between two `int` values:

```java
int a = Integer.MAX_VALUE;
int b = -Integer.MAX_VALUE;

int wrong = Math.absExact(a - b); // Returns 2, does NOT throw an exception!
```

Analysis:

```text
a                    =  2147483647
b                    = -2147483647
Mathematical a - b   =  4294967294
a - b in int         = -2            (int overflow)
Math.absExact(-2)    =  2            (no overflow at the abs step)
```

The result `2` looks valid and throws no exception, yet the true mathematical distance is `4294967294`. **`absExact` is not a tool that automatically detects every overflow occurring before the call**.

Because the distance between any two `int` values fits within `long`, the right approach is to **widen before subtracting**:

```java
long distance = Math.abs((long) a - b);
// distance == 4294967294L
```

You can use `Math.absExact((long) a - b)` to express a checked-arithmetic policy, though with both inputs as `int`, the absolute difference stays within `long` limits.

### For two arbitrary `long` values, `BigInteger` is more appropriate

The mathematical difference between `Long.MAX_VALUE` and `Long.MIN_VALUE` is `18446744073709551615`, exceeding `long`. Casting two `long` operands to `long` again does nothing:

```java
BigInteger distance = BigInteger.valueOf(Long.MAX_VALUE)
        .subtract(BigInteger.valueOf(Long.MIN_VALUE))
        .abs();
// 18446744073709551615
```

If the specification requires returning `long`, check the data range upfront or use checked subtraction like `Math.subtractExact` followed by `Math.absExact`, prepared to report an error when unrepresentable. If the specification requires returning the **exact mathematical distance for every pair of `long`s**, `BigInteger` is the right path.

## 7. Practical Example: Taking the Absolute Value of a Hash and Computing an Index

A common code pattern is:

```java
int hash = key.hashCode();
int index = Math.abs(hash) % capacity;
```

If `hash == Integer.MIN_VALUE`, `Math.abs(hash)` stays negative. With `capacity = 10`, the resulting `index` is **`-8`**, outside the `0..9` index range.

```java
int hash = Integer.MIN_VALUE;
int capacity = 10;

int brokenIndex = Math.abs(hash) % capacity; // -8
```

You could fix it by widening before `abs`, yet when the real goal is simply **mapping integers, including negative ones, into a positive cycle**, `Math.floorMod(hash, capacity)` expresses the requirement more directly:

```java
int hash = Integer.MIN_VALUE;
int capacity = 10;

int index = Math.floorMod(hash, capacity); // 2
```

When `capacity > 0`, `Math.floorMod(hash, capacity)` lies in `0..capacity-1` for every `int hash`. Be sure to verify `capacity > 0`; if it is 0, there is no valid index. The `floorMod` result `2` **does not necessarily match** `Math.abs((long) hash) % capacity` (the latter is 8). They represent **two different mapping policies**; choose the policy based on the algorithm, distribution stability, and existing contracts.

### Why not use `absExact` to "fix" the hash formula?

```java
int index = Math.absExact(hash) % capacity;
```

This formula detects `Integer.MIN_VALUE` and throws an exception. That may make sense if your application rules treat that special hash as an error. Normally, however, a hash can be **any `int`**, and having one valid hash value make index mapping fail is undesirable. For positive cyclic indexing, `floorMod` is more appropriate.

Another option when an algorithm works on **unsigned bits** is masking off the sign bit with `hash & Integer.MAX_VALUE`; this also yields a non-negative value, though with a **different mapping policy** from `floorMod`. Do not arbitrarily change the mapping function in an existing data structure, as it can affect buckets or compatibility with previously stored data.

## 8. Practical Example: Deviations, Distances, and Limit Checks

Suppose a service needs to compute the quantity difference between two counters:

```java
static long absoluteDifference(int current, int previous) {
    return Math.abs((long) current - previous);
}
```

The method above is safe for any pair of `int`s. It produces a `long` from 0 to `4294967295` without losing data to `int` overflow. However, checking a business rule like "deviation does not exceed 1000" still requires comparing against the threshold and validating inputs.

If the method is required to return `int`, decide explicitly:

```java
static int absoluteDifferenceExact(int current, int previous) {
    long distance = Math.abs((long) current - previous);
    return Math.toIntExact(distance);
}
```

`Math.toIntExact` throws `ArithmeticException` when the distance exceeds `Integer.MAX_VALUE`; it reports an error **at the return boundary**, rather than letting a cast silently lose information.

When inputs are `long` and the distance must be exact, use `BigInteger` as shown earlier.

### Absolute values in calculations and intermediate expressions

Three common mistakes share the same structure:

```java
// 1. Calling abs too late after an int subtraction already overflowed:
long wrongDistance = Math.abs(a - b);

// 2. Casting too late, after Math.abs(int) already returned MIN_VALUE:
long wrongMagnitude = (long) Math.abs(Integer.MIN_VALUE);

// 3. Converting to BigInteger after Math.abs(long) already returned MIN_VALUE:
BigInteger wrongBigMagnitude =
        BigInteger.valueOf(Math.abs(Long.MIN_VALUE));
```

You must put **a sufficiently wide type or the right check at the point where the operation can overflow**. Checking only the final result cannot substitute for controlling intermediate steps.

## 9. Should You Use `if`/Ternary Instead of `Math.absExact`?

A common hand-written implementation:

```java
static int naiveAbs(int value) {
    return value < 0 ? -value : value;
}
```

It **does not solve** the `Integer.MIN_VALUE` case. The `-value` branch also wraps back to the smallest negative number without throwing an exception. To keep `int` and detect overflow, `Math.absExact` expresses the intent more clearly than a custom special-case branch.

If you need a custom business exception other than `ArithmeticException`, check the input explicitly:

```java
static int checkedMagnitude(int value) {
    if (value == Integer.MIN_VALUE) {
        throw new IllegalArgumentException("Magnitude exceeds int range");
    }
    return Math.abs(value);
}
```

This is a design choice with a **different contract** from `Math.absExact`: the exception type and error description depend on your API. There is no need to rewrite it if overflow throwing `ArithmeticException` is all you need.

If the problem accepts returning the result in `long`, widening before calling `abs` is usually cleaner and handles the boundary case without throwing an error.

## 10. Standalone Runnable Java 17+ Program

Save the following snippet as **`AbsMinValueDemo.java`**. The program illustrates `Math.abs` returning `MIN_VALUE`, `Math.absExact` throwing an error, timely type promotion, `BigInteger`, the overflowed-difference trap, and generating non-negative modulo indices.

```java
import java.math.BigInteger;

public class AbsMinValueDemo {
    public static void main(String[] args) {
        int minInt = Integer.MIN_VALUE;
        long minLong = Long.MIN_VALUE;

        System.out.println("abs-int-min=" + Math.abs(minInt));
        System.out.println("abs-long-min=" + Math.abs(minLong));
        System.out.println("abs-int-near-min=" +
                Math.absExact(minInt + 1));

        try {
            Math.absExact(minInt);
        } catch (ArithmeticException ex) {
            System.out.println("abs-exact-int=overflow");
        }

        try {
            Math.absExact(minLong);
        } catch (ArithmeticException ex) {
            System.out.println("abs-exact-long=overflow");
        }

        System.out.println("widen-before-abs=" +
                Math.abs((long) minInt));
        System.out.println("widen-after-abs=" +
                (long) Math.abs(minInt));
        System.out.println("big-long-magnitude=" +
                BigInteger.valueOf(minLong).abs());

        int a = Integer.MAX_VALUE;
        int b = -Integer.MAX_VALUE;
        System.out.println("incorrect-abs-diff=" +
                Math.absExact(a - b));
        System.out.println("correct-abs-diff=" +
                Math.abs((long) a - b));

        System.out.println("naive-hash-index=" +
                (Math.abs(minInt) % 10));
        System.out.println("floor-mod-index=" +
                Math.floorMod(minInt, 10));

        BigInteger bigDifference = BigInteger.valueOf(Long.MAX_VALUE)
                .subtract(BigInteger.valueOf(Long.MIN_VALUE))
                .abs();
        System.out.println("big-long-distance=" + bigDifference);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac AbsMinValueDemo.java
java AbsMinValueDemo
```

Stdout output:

```text
abs-int-min=-2147483648
abs-long-min=-9223372036854775808
abs-int-near-min=2147483647
abs-exact-int=overflow
abs-exact-long=overflow
widen-before-abs=2147483648
widen-after-abs=-2147483648
big-long-magnitude=9223372036854775808
incorrect-abs-diff=2
correct-abs-diff=4294967294
naive-hash-index=-8
floor-mod-index=2
big-long-distance=18446744073709551615
```

**Explanation:**

- The two `abs-*-min` lines show that `Math.abs` does not throw an exception on integer `MIN_VALUE`.
- The two `abs-exact-*` lines appear only because the `catch` blocks caught exceptions from `Math.absExact`.
- `widen-before-abs` preserves the true magnitude of `Integer.MIN_VALUE`; `widen-after-abs` cannot fix the already-wrapped `int` result.
- `incorrect-abs-diff=2` is especially important: `absExact` does not detect the subtraction that overflowed before the call. You must widen before subtracting.
- Index `-8` from `Math.abs(minInt) % 10` is invalid for an array; `Math.floorMod(minInt, 10)` returns `2`.
- The two `BigInteger` calculations retain absolute values beyond the `long` range.

## 11. Distinguishing Easily Confused Mistakes

| Code or Decision | Result / Issue | Appropriate Usage |
| --- | --- | --- |
| `Math.abs(Integer.MIN_VALUE)` | Returns `Integer.MIN_VALUE`, still negative | Use only when the edge case is handled or `MIN_VALUE` is excluded from the domain |
| `Math.absExact(Integer.MIN_VALUE)` | Throws `ArithmeticException` | When the result must fit in `int` or overflow must be reported |
| `Math.abs((long) Integer.MIN_VALUE)` | Returns `2147483648L` | When exact magnitude is needed and `long` is acceptable |
| `(long) Math.abs(Integer.MIN_VALUE)` | Still negative `-2147483648L` | Avoid: type conversion happened too late |
| `Math.abs(Long.MIN_VALUE)` | Returns `Long.MIN_VALUE` | Do not use as a guarantee of a non-negative result |
| `Math.absExact(Long.MIN_VALUE)` | Throws `ArithmeticException` | When `long` is the output limit |
| `BigInteger.valueOf(Long.MIN_VALUE).abs()` | Returns exact `9223372036854775808` | When magnitude exceeds `long` |
| `Math.absExact(a - b)` with two `int`s | Expression `a-b` may have already overflowed | Widen before subtracting: `Math.abs((long)a-b)` |
| `Math.abs(hash) % capacity` | Can be negative if hash is `MIN_VALUE` | With positive capacity, consider `Math.floorMod(hash, capacity)` |
| `Math.absExact(hash) % capacity` | Can throw on a valid hash | Choose a full-domain mapping policy; do not assume `MIN_VALUE` is an error |

### A note on Java floating point

`Math.abs(float)` and `Math.abs(double)` do not suffer from the integer range asymmetry of `int`/`long`. For floating point, `Float.MIN_VALUE` and `Double.MIN_VALUE` are the **smallest non-zero positive numbers** representable, not the largest-magnitude negative values. `Math.abs(Double.NaN)` remains `NaN`, and `Math.abs(-0.0d)` returns positive `0.0`.

Therefore, whenever you see `MIN_VALUE` in code, read the **type** carefully: `Integer.MIN_VALUE` / `Long.MIN_VALUE` are extreme negative integers; `Double.MIN_VALUE` / `Float.MIN_VALUE` have a completely different meaning. When validating measurement data, use `Double.isFinite`, handle `NaN`, or apply an appropriate floating-point policy.

## 12. Testing and Self-Practice Exercises

1. Predict the results of `Math.abs(Integer.MIN_VALUE + 1)`, `Math.abs(Integer.MIN_VALUE)`, and `Math.absExact(Integer.MIN_VALUE)`. Explain why only one case has no positive absolute value in `int`.
2. Write a method `long magnitude(int value)` that returns the exact absolute value of any `int`. Test `-42`, `0`, `Integer.MAX_VALUE`, and `Integer.MIN_VALUE`.
3. Write a method `int magnitudeExact(int value)` using `Math.absExact`. Verify that the exception occurs only on `Integer.MIN_VALUE`, and identify the exception type.
4. Why is `(long) Math.abs(Integer.MIN_VALUE)` wrong while `Math.abs((long) Integer.MIN_VALUE)` is right? Show the overload chosen at each step.
5. Given `a=Integer.MAX_VALUE`, `b=-Integer.MAX_VALUE`, predict `Math.absExact(a-b)` and `Math.abs((long)a-b)`. Point out where overflow occurs.
6. Write a function `BigInteger magnitude(long value)` that works for `Long.MIN_VALUE`. Explain why you must not call `Math.abs(value)` before `BigInteger.valueOf`.
7. With `capacity=10`, compute `Math.abs(Integer.MIN_VALUE) % capacity` and `Math.floorMod(Integer.MIN_VALUE, capacity)`. How do the two approaches differ in policy?
8. Design an API that computes the difference between two `long` values, required to be **exact for every pair of inputs**. Choose the return type and operation, then test with `Long.MIN_VALUE` and `Long.MAX_VALUE`.
9. Write a test proving that any `int` value other than `Integer.MIN_VALUE` always has a non-negative absolute value in `int`. Which boundary value groups should you cover?
10. Explain the difference in meaning between `Integer.MIN_VALUE` and `Double.MIN_VALUE`. Why can confusing these two constants lead to broken boundary checks?

## 13. Checklist for Choosing How to Take an Absolute Value

- **Input is `int`/`long`?** Recognize `MIN_VALUE` and the type's representation limits.
- **Need to keep the same type and report an error on overflow?** Use `Math.absExact(int/long)`; handle `ArithmeticException` at the appropriate layer.
- **Source is `int`, need exact mathematical magnitude?** Cast to `long` **before** `Math.abs`.
- **Source is `long`, need exact magnitude including `MIN_VALUE`?** Convert to `BigInteger` before calling `abs()`.
- **Argument is the result of addition/subtraction/multiplication?** Check **overflow of the intermediate expression**, not just calling `absExact` afterward.
- **Goal is an index/bucket in `0..n-1`?** Consider `Math.floorMod(x,n)` with `n>0`, following the algorithm's mapping policy.
- **Values might be floating-point?** Do not apply integer `MIN_VALUE` rules to `float`/`double`; define handling for `NaN`, infinity, and signed zero.
- **Testing:** include `MIN_VALUE`, `MIN_VALUE+1`, `-1`, `0`, `1`, `MAX_VALUE`, and intermediate expressions that can overflow.

**Core takeaway:** `Math.abs` on `int`/`long` does not guarantee every result is non-negative; `MIN_VALUE` is an exception due to the asymmetric two's complement range. `Math.absExact` reports an error when the absolute value does not fit in the type; when you need exact values beyond the range, switch to a sufficiently wide type **before performing the operation**.
