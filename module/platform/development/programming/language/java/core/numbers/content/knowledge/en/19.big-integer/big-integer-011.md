# `BigInteger.compareTo`, `equals`, `signum`, `abs`, and `negate` in Java

## 1. Goal and Context

`java.math.BigInteger` represents arbitrary-precision signed integers. Values are not confined to 32 bits of `int` or 64 bits of `long`; practical limits are memory, computation resources, and library implementation limits. It is an **immutable object type**, so operations do not modify the source object.

The five methods in this lesson answer five core questions:

| Method | Question | Return type |
| --- | --- | --- |
| `a.compareTo(b)` | Is `a` less than, equal to, or greater than `b`? | negative, `0`, or positive `int` |
| `a.equals(b)` | Do two objects have the same **`BigInteger` value**? | `boolean` |
| `a.signum()` | Is the value negative, 0, or positive? | `int` in `-1`, `0`, `1` |
| `a.abs()` | What is the non-negative magnitude of `a`? | `BigInteger` |
| `a.negate()` | What is the additive inverse (negation) of `a`? | `BigInteger` |

Short example placed in a Java method with `import java.math.BigInteger`:

```java
BigInteger a = new BigInteger("-123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42);

System.out.println(a.compareTo(b)); // -1: a is less than b
System.out.println(a.signum());      // -1: a is negative
System.out.println(a.abs());         // 123456789012345678901234567890
System.out.println(a.negate());      // 123456789012345678901234567890
System.out.println(a);               // Still the original negative number
```

Three concepts must be distinguished: **arithmetic ordering**, **value equality**, and **same object reference**. In most business code, `compareTo`, `equals`, and `signum` answer the right questions; `==` cannot replace them.

## 2. `compareTo(BigInteger)`: Exact Ordering Even for Huge Numbers

API signature:

```java
public int compareTo(BigInteger val)
```

The result carries the **sign** of the ordering relation:

\[
a.\mathrm{compareTo}(b)
\begin{cases}
< 0 & \text{when } a < b,\\
= 0 & \text{when } a = b,\\
> 0 & \text{when } a > b.
\end{cases}
\]

Examples:

```java
BigInteger small = BigInteger.valueOf(-5);
BigInteger zero = BigInteger.ZERO;
BigInteger large = new BigInteger("99999999999999999999999999");

System.out.println(small.compareTo(zero) < 0); // true
System.out.println(large.compareTo(zero) > 0); // true
System.out.println(zero.compareTo(BigInteger.ZERO) == 0); // true
```

**Do not rely on exact `-1` or `1` as a general `Comparable` contract.** The contract guarantees negative/0/positive; test `< 0`, `== 0`, `> 0`.

`compareTo` operates directly on `BigInteger`, rather than converting values to `int`, `long`, or `double`:

```java
BigInteger left = new BigInteger("9007199254740993");
BigInteger right = new BigInteger("9007199254740992");

System.out.println(left.compareTo(right) > 0); // true
```

If both were converted to `double`, those values could round to the same number, breaking the comparison. `compareTo` preserves mathematical order across all valid `BigInteger` values.

### Cross-Sign Comparison and Two Negative Numbers

- Every negative number is less than 0, and 0 is less than every positive number.
- Between two negative numbers, the one with the **larger absolute value** is **smaller** in standard order.

Example:

```java
BigInteger a = BigInteger.valueOf(-100);
BigInteger b = BigInteger.valueOf(-2);

System.out.println(a.compareTo(b) < 0); // true
System.out.println(a.abs().compareTo(b.abs()) > 0); // true
```

`-100 < -2`, whereas `|-100| > |-2|`.

### Do Not Subtract and Narrow to `int` for a Comparator

Common mistake:

```java
// Do not use in Comparator<BigInteger>:
int compareWrong(BigInteger a, BigInteger b) {
    return a.subtract(b).intValue();
}
```

The difference can exceed the `int` range, causing `intValue()` to drop high bits. Two distinct numbers can yield 0 or the wrong sign, breaking ordering.

Correct approach:

```java
int compareCorrect(BigInteger a, BigInteger b) {
    return a.compareTo(b);
}
```

These are illustrative methods in a Java class, not two standalone programs. In practice, you can directly use `Comparator.naturalOrder()` or `BigInteger::compareTo`.

### `min` and `max`

Two related utilities:

```java
BigInteger a = BigInteger.valueOf(-3);
BigInteger b = BigInteger.valueOf(2);

System.out.println(a.min(b)); // -3
System.out.println(a.max(b)); // 2
```

`min`/`max` select the value according to the order defined by `compareTo`. Do not use them when needing to compare **absolute magnitudes**; inspect `abs()` in that case.

## 3. `equals(Object)`: Compare Values, Not Object Addresses

Signature:

```java
public boolean equals(Object x)
```

`BigInteger.equals` returns `true` when the argument is a `BigInteger` representing the same integer. It **does not** care how the value was constructed:

```java
BigInteger a = new BigInteger("42");
BigInteger b = BigInteger.valueOf(42);
BigInteger c = new BigInteger("0042");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // true
```

The strings `"42"` and `"0042"` are different notations for the same integer 42, so the objects have equal values. `BigInteger` does not store "number of leading zeros" as a meaningful arithmetic attribute.

### `==` Only Compares References

```java
BigInteger a = new BigInteger("42");
BigInteger b = new BigInteger("42");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false: two separate objects were created here
```

The `new BigInteger(String)` calls allocate distinct objects for the two variables in this example, so reference comparison returns `false`. Yet **do not infer the converse** that equal values always have distinct references: constants and `valueOf` can reuse objects.

```java
BigInteger x = BigInteger.valueOf(10);
BigInteger y = BigInteger.TEN;

System.out.println(x.equals(y)); // true
// Do not use x == y as the rule for numeric equality.
```

`BigInteger.valueOf` may cache commonly used values. This is a performance/identity detail, not a replacement for the `equals` contract. Never use `System.identityHashCode` as a mathematical ID.

### Comparing Across Types

```java
System.out.println(BigInteger.valueOf(42).equals(Long.valueOf(42L)));
// false
```

`BigInteger` and `Long` are different classes, even when both represent the mathematical number 42. If you need to compare a `long` integer against a `BigInteger`, convert `long` to `BigInteger` **without losing information**:

```java
long input = 42L;
BigInteger value = new BigInteger("42");

boolean equal = value.equals(BigInteger.valueOf(input)); // true
```

Never narrow a large `BigInteger` down to `long` or `double` to compare without verifying range; precision loss can make two distinct numbers appear equal.

### `equals` and `compareTo` Are Consistent with Each Other

For two non-null `BigInteger` objects:

\[
a.equals(b) \iff a.compareTo(b) == 0.
\]

This is an important contract when using collections. Whereas `BigDecimal` can treat `"2.0"` and `"2.00"` as equal in ordering yet unequal under `equals` due to scale, `BigInteger` **has no decimal scale**: its natural ordering is consistent with `equals`.

If original formatting must be kept (for instance, `"0042"` differs from `"42"` as a record code), keep the source string or a suitable string-based ID; `BigInteger.equals` intentionally treats them as the same number.

## 4. `signum()`: Getting the Sign Without Repeatedly Comparing to 0

Signature:

```java
public int signum()
```

The result is **strictly** `-1`, `0`, or `1`:

| `BigInteger` value | `signum()` | Meaning |
| --- | ---: | --- |
| Negative, e.g., `-9` | `-1` | Less than 0 |
| Equal to 0 | `0` | Neither negative nor positive |
| Positive, e.g., `42` | `1` | Greater than 0 |

Example:

```java
System.out.println(BigInteger.valueOf(-9).signum()); // -1
System.out.println(BigInteger.ZERO.signum());        // 0
System.out.println(BigInteger.valueOf(42).signum()); // 1
```

Unlike `compareTo`, `signum` does not require a second object. Use it when you only care about the sign:

```java
static String describe(BigInteger value) {
    return switch (value.signum()) {
        case -1 -> "NEGATIVE";
        case  0 -> "ZERO";
        case  1 -> "POSITIVE";
        default -> throw new AssertionError("Unexpected sign");
    };
}
```

The snippet above is a method in a Java 17 class and assumes `value != null`. This `switch` is valid in JDK 17; its cases cover the full value domain promised by `signum()`.

### `signum` Is Not a Parity Check

`signum()` does not tell whether a number is even or odd. Both `-8` and `-7` have `signum() == -1`. To test parity, use operations such as `testBit(0)` after verifying the proper interpretation of negative numbers, or `remainder(BigInteger.TWO)` per needed arithmetic rules.

### `BigInteger` Has No Negative Zero

```java
BigInteger zero = new BigInteger("-0");

System.out.println(zero);          // 0
System.out.println(zero.signum()); // 0
```

Unlike `double`, `BigInteger` does not have two zero values with different sign bits. Parsing `"-0"` still represents integer 0, and `signum()` returns 0. If you must record that a user typed a `-` sign, keep the original string; that is **formatting** information, not an integer value.

## 5. `abs()`: Absolute Value Without Overflow at the `long` Boundary

Signature:

```java
public BigInteger abs()
```

Definition:

\[
|n| =
\begin{cases}
-n & n < 0,\\
n  & n \ge 0.
\end{cases}
\]

Example:

```java
BigInteger negative = new BigInteger("-12345678901234567890");
BigInteger magnitude = negative.abs();

System.out.println(magnitude); // 12345678901234567890
System.out.println(negative);  // -12345678901234567890
```

`abs()` returns a non-negative value **without modifying** `negative`. For 0, the result is 0. For positive numbers, the result has the same value as the input; the library may return the same object or another depending on optimization, yet code must not depend on that identity.

### Notable Difference from `Math.abs(Long.MIN_VALUE)`

The `long` type ranges from `-2^63` to `2^63 - 1`. The absolute value of `Long.MIN_VALUE` is `2^63`, which **does not fit in the positive `long` range**:

```java
System.out.println(Math.abs(Long.MIN_VALUE));
// -9223372036854775808
```

Under Java integer rules, the result stays negative at this boundary case.

If you convert the `long` value to `BigInteger` first, the absolute value is preserved accurately:

```java
BigInteger exactMagnitude =
        BigInteger.valueOf(Long.MIN_VALUE).abs();

System.out.println(exactMagnitude); // 9223372036854775808
```

**The right order is convert then `abs`**, not `BigInteger.valueOf(Math.abs(Long.MIN_VALUE))`, because `Math.abs(long)` may already have produced an unwanted negative result before `BigInteger` ever received the value.

Real-world scenarios include checking huge value deltas, distances between integers, and algorithms receiving data near 64-bit bounds.

### `abs` Differs from `signum`

`abs()` returns **the full magnitude** as a `BigInteger`, whereas `signum()` returns only the sign as an `int`. Never use `abs().equals(BigInteger.ONE)` to check for positive sign, as that is only true for `1`, not for all positive numbers.

## 6. `negate()`: Creating the Additive Inverse While Preserving the Source Object

Signature:

```java
public BigInteger negate()
```

Definition:

\[
\operatorname{negate}(n)=-n.
\]

Example:

```java
BigInteger original = BigInteger.valueOf(17);
BigInteger opposite = original.negate();

System.out.println(opposite); // -17
System.out.println(original); // 17
```

`negate()` does not modify `original`. To update the variable's state, assign the result:

```java
BigInteger balance = BigInteger.valueOf(17);
balance = balance.negate();

System.out.println(balance); // -17
```

Some identities that hold by value:

\[
-(-n)=n,\qquad -0=0,\qquad |-n|=|n|.
\]

Verification:

```java
BigInteger n = new BigInteger("-12345678901234567890");

System.out.println(n.negate().negate().equals(n)); // true
System.out.println(BigInteger.ZERO.negate());      // 0
System.out.println(n.negate().abs().equals(n.abs())); // true
```

Do not infer from `n.negate().negate().equals(n)` that `n.negate().negate() == n`; the method is a value operation with no identity-preservation contract.

### `negate()` of `Long.MIN_VALUE` Does Not Overflow Like `long`

```java
long x = Long.MIN_VALUE;
System.out.println(-x); // -9223372036854775808: long overflow

BigInteger bi = BigInteger.valueOf(x);
System.out.println(bi.negate()); // 9223372036854775808
```

When needing the exact additive inverse of a minimum negative value, convert to `BigInteger` **before** negating.

### Is `abs()` Just `negate()`?

No:

- For `n > 0`, `n.abs()` stays positive, whereas `n.negate()` becomes negative.
- For `n < 0`, both results have the same positive value.
- For `n == 0`, both return 0.

`abs` **takes magnitude**, while `negate` **flips sign**. These are two different transformations, not interchangeable on positive data.

## 7. Immutability: Return Values Must Be Captured

`BigInteger` does not have `++`, `--`, `+`, or unary `-` operators like primitives. Its operations are methods:

```java
BigInteger n = BigInteger.TEN;

// n++;      // Does not compile: BigInteger is not a primitive numeric type
// n = -n;   // Does not compile
n = n.add(BigInteger.ONE);
n = n.negate();

System.out.println(n); // -11
```

If you discard the return value of `add`, `negate`, or `abs`, the old value **does not change**:

```java
BigInteger n = BigInteger.valueOf(-5);
n.abs();
System.out.println(n); // -5

n = n.abs();
System.out.println(n); // 5
```

This is why functions transforming `BigInteger` sequences usually return a new `BigInteger` **by value**. "Immutable" does not promise every call allocates a brand-new object; it only guarantees existing object data is never mutated.

## 8. Combining All Five Methods in Real-World Code Patterns

### 8.1. Range Checking

If a user enters a large integer `quantity` and only values from `0` to `max` are accepted:

```java
static boolean inRange(BigInteger quantity, BigInteger max) {
    if (quantity == null || max == null) {
        return false;
    }
    return quantity.signum() >= 0 && quantity.compareTo(max) <= 0;
}
```

Here `signum() >= 0` checks non-negativity; `compareTo(max) <= 0` checks the upper bound. **Do not** cast `quantity` to `long` just to check bounds, as casting can lose data.

### 8.2. Absolute Distance Between Two Integers

One-dimensional distance between `a` and `b`:

\[
d = |a-b|.
\]

```java
static BigInteger distance(BigInteger a, BigInteger b) {
    return a.subtract(b).abs();
}
```

Example:

```java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = new BigInteger("99999999999999999995");

System.out.println(distance(a, b)); // 5
```

Note this is the **absolute value of the difference**, not the difference of the two absolute values:

\[
|a-b|\ \text{generally differs from}\ |a|-|b|.
\]

With `a = -5` and `b = 3`, `|a-b| = 8`, whereas `|a|-|b| = 2`.

### 8.3. Normalizing by Sign in Algorithms

An algorithm may need to separate sign and magnitude:

```java
BigInteger input = new BigInteger("-12345678901234567890");

int sign = input.signum();
BigInteger magnitude = input.abs();

System.out.println(sign);      // -1
System.out.println(magnitude); // 12345678901234567890
```

If reconstructing the number later:

```java
BigInteger restored =
        sign < 0 ? magnitude.negate() : magnitude;

System.out.println(restored.equals(input)); // true
```

For zero, `sign == 0` and `magnitude == 0` by **value**, since `BigInteger` has no negative zero. This pattern helps in custom sign-handling logic, though do not rewrite library algorithms when a built-in method already handles everything.

### 8.4. Natural Sorting

`BigInteger` implements `Comparable<BigInteger>`, so it uses natural ordering:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

List<BigInteger> values = new ArrayList<>(
        List.of(
                BigInteger.TEN,
                BigInteger.valueOf(-3),
                BigInteger.ZERO,
                BigInteger.valueOf(2)
        )
);

values.sort(BigInteger::compareTo);
System.out.println(values); // [-3, 0, 2, 10]
```

This order is **arithmetic order**: `-3 < 0 < 2 < 10`. If sorting by absolute magnitude is required, you must specify tie-breaking (for example, `-3` and `3` have equal magnitudes).

Magnitude comparator example:

```java
values.sort((left, right) -> left.abs().compareTo(right.abs()));
```

This comparator treats `-3` and `3` as equal in order (returning 0) even though `equals` is `false`. If used in `TreeSet`/`TreeMap`, that can **collapse distinct-value keys**. To prioritize magnitude while maintaining a total order consistent with `equals`, add a tie-breaker:

```java
values.sort(
        (left, right) -> {
            int order = left.abs().compareTo(right.abs());
            return order != 0 ? order : left.compareTo(right);
        }
);
```

### 8.5. Branching by Sign for Business Logic

```java
static String status(BigInteger balance) {
    return switch (balance.signum()) {
        case -1 -> "DEBT";
        case 0 -> "SETTLED";
        case 1 -> "CREDIT";
        default -> throw new AssertionError();
    };
}
```

This is purely an algorithmic illustration: interpreting negative as debt and positive as credit must match the actual data contract. `signum()` does not inherently know financial or business semantics.

## 9. `equals`, `hashCode`, and Collections

`BigInteger.equals` checks value equality and `hashCode` obeys the corresponding contract. Therefore `BigInteger` can serve as a key in `HashMap`/`HashSet`:

```java
import java.math.BigInteger;
import java.util.HashSet;
import java.util.Set;

Set<BigInteger> identifiers = new HashSet<>();
identifiers.add(new BigInteger("1234567890123456789012345"));

boolean present = identifiers.contains(
        new BigInteger("1234567890123456789012345")
);

System.out.println(present); // true
```

Two constructor calls create two distinct objects by reference, yet `HashSet` matches **by value**.

`TreeSet<BigInteger>` uses natural ordering via `compareTo`; because that order is consistent with `equals`, it exhibits expected value-based membership behavior.

Do not use `IdentityHashMap<BigInteger, ...>` for numeric keys when the goal is equality by **value**: `IdentityHashMap` intentionally uses reference identity, causing equal-numbered data to be treated as distinct keys.

### Negative Sign Does Not Affect Identity Like Source Strings

`new BigInteger("-0")`, `BigInteger.ZERO`, and `new BigInteger("000")` are all equal in value. If a string-based identifier requires preserving leading zeros, do not convert it to `BigInteger` expecting `equals` to tell the source strings apart.

## 10. Null and Data Types: Exceptions to Know

`BigInteger` is a **reference** type, so variables can hold `null`:

```java
BigInteger missing = null;
// missing.signum(); // NullPointerException
// missing.abs();    // NullPointerException
// missing.negate(); // NullPointerException
```

`null` has no numeric value. You must decide how to handle it:

```java
static boolean isZeroIfPresent(BigInteger value) {
    return value != null && value.signum() == 0;
}
```

`Objects.equals` supports comparing nullable objects:

```java
boolean same = java.util.Objects.equals(
        (BigInteger) null, (BigInteger) null
); // true because both references are null
```

However, `Objects.equals(null, null)` does not prove two zeros exist. If business logic requires two valid numbers, check non-null first.

Methods requiring a `BigInteger` argument like `compareTo(null)` have no numeric value to compare; in Java 17, this throws `NullPointerException`. Validate at API boundaries:

```java
static int compareRequired(BigInteger a, BigInteger b) {
    java.util.Objects.requireNonNull(a, "a");
    java.util.Objects.requireNonNull(b, "b");
    return a.compareTo(b);
}
```

`equals(null)`, on the other hand, returns `false` if the receiver is a non-null `BigInteger`, per the `equals(Object)` contract. **Do not equate** `equals(null)` with `compareTo(null)`.

### `BigInteger` Is Not a Primitive and Does Not Auto-Unbox

You cannot write:

```java
BigInteger n = BigInteger.TEN;
// if (n > 0) {} // Does not compile
// int x = n;    // Does not compile
```

To compare against 0, use `n.signum() > 0` or `n.compareTo(BigInteger.ZERO) > 0`. To extract a `long`, use `longValueExact()` when exactness and range fit are mandatory; never use `longValue()` casually on huge numbers.

## 11. Complete Java 17 Example

Save as `BigIntegerComparisonDemo.java`:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

public class BigIntegerComparisonDemo {

    static BigInteger distance(BigInteger left, BigInteger right) {
        return left.subtract(right).abs();
    }

    static String describe(BigInteger value) {
        return switch (value.signum()) {
            case -1 -> "NEGATIVE";
            case 0 -> "ZERO";
            case 1 -> "POSITIVE";
            default -> throw new AssertionError();
        };
    }

    public static void main(String[] args) {
        BigInteger negative =
                new BigInteger("-123456789012345678901234567890");
        BigInteger positive = BigInteger.valueOf(42);

        System.out.println("compare negative to 42: "
                + negative.compareTo(positive));
        System.out.println("compare 42 to negative: "
                + positive.compareTo(negative));

        System.out.println("equals same value: "
                + new BigInteger("42").equals(positive));
        System.out.println("equals different type: "
                + positive.equals(Long.valueOf(42L)));

        System.out.println("negative signum: " + negative.signum());
        System.out.println("zero signum: " + BigInteger.ZERO.signum());
        System.out.println("positive signum: " + positive.signum());

        System.out.println("absolute negative: " + negative.abs());
        System.out.println("negated negative: " + negative.negate());
        System.out.println("original unchanged: " + negative);
        System.out.println("double negation equals: "
                + negative.negate().negate().equals(negative));

        System.out.println("abs min long: "
                + BigInteger.valueOf(Long.MIN_VALUE).abs());
        System.out.println("Math.abs min long: "
                + Math.abs(Long.MIN_VALUE));

        System.out.println("negative zero signum: "
                + new BigInteger("-0").signum());
        System.out.println("describe zero: "
                + describe(BigInteger.ZERO));

        System.out.println("distance: " + distance(
                new BigInteger("100000000000000000000"),
                new BigInteger("99999999999999999995")));

        List<BigInteger> values = new ArrayList<>(List.of(
                BigInteger.TEN,
                BigInteger.valueOf(-3),
                BigInteger.ZERO,
                BigInteger.valueOf(2)
        ));
        values.sort(BigInteger::compareTo);
        System.out.println("sorted: " + values);
    }
}
```

Run with JDK 17 or newer:

```bash
javac BigIntegerComparisonDemo.java
java BigIntegerComparisonDemo
```

Output:

```text
compare negative to 42: -1
compare 42 to negative: 1
equals same value: true
equals different type: false
negative signum: -1
zero signum: 0
positive signum: 1
absolute negative: 123456789012345678901234567890
negated negative: 123456789012345678901234567890
original unchanged: -123456789012345678901234567890
double negation equals: true
abs min long: 9223372036854775808
Math.abs min long: -9223372036854775808
negative zero signum: 0
describe zero: ZERO
distance: 5
sorted: [-3, 0, 2, 10]
```

These values clarify that `compareTo` checks order via sign, `equals` checks value equality of the same type, `signum` branches on sign, `abs` computes exact magnitudes beyond `long` limits, and `negate` returns the opposite **without modifying the input**.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| `a == b` for two `BigInteger`s | Compares references; equal values can still be `false` | `a.equals(b)` |
| `compareTo(b) == 1` to check greater-than | Relies on exact value rather than sign per `Comparable` contract | `compareTo(b) > 0` |
| `a.subtract(b).intValue()` as a comparator | Drops bits, flips sign, or returns 0 unexpectedly | `a.compareTo(b)` |
| Casting `BigInteger` to `double` to compare | Can lose digits of large integers | Compare directly with `compareTo` |
| `Math.abs(Long.MIN_VALUE)` then calling `valueOf` | `long` absolute value already overflowed | `BigInteger.valueOf(Long.MIN_VALUE).abs()` |
| `-someLong` then converting to `BigInteger` | Negation can overflow at `Long.MIN_VALUE` | `BigInteger.valueOf(someLong).negate()` |
| `n.abs();` without assigning result | `BigInteger` is immutable; `n` unchanged | `n = n.abs();` |
| `n.negate();` without assigning result | Does not change stored number | `n = n.negate();` |
| Using `negate()` instead of `abs()` on positive numbers | Flips to negative instead of keeping non-negative | Use the right method for the goal |
| `value.signum()` when `value == null` | `NullPointerException` | Check for `null` |
| Treating `equals(null)` like `compareTo(null)` | The two APIs behave differently | `equals(null)` returns `false`; ordering requires a value |
| Treating `BigInteger("-0")` as different from `ZERO` | `BigInteger` has no negative zero | Both are integer 0 |
| Creating a `TreeSet` with an `abs`-only comparator when `-a` and `a` must be distinct | Comparator returns 0 for distinct values | Add a `compareTo` tie-breaker |
| Choosing `BigInteger` as an ID while needing leading zeros preserved | `"0042"` and `"42"` become the same numeric value | Store IDs as strings if formatting matters |
| Assuming `abs()` or `negate()` always allocates a new instance | Identity is not part of value-transformation contracts | Do not compare references; use `equals` |
| Calling `longValue()` to check `long` range | Can lose data silently | Use `longValueExact()` when needed |

### Quick Method Selection Rules

- **Order two numbers:** `a.compareTo(b)`.
- **Check value equality of same type:** `a.equals(b)`.
- **Check negative, 0, positive:** `a.signum()`.
- **Get non-negative magnitude:** `a.abs()`.
- **Flip sign:** `a.negate()`.
- **Get magnitude of difference between two numbers:** `a.subtract(b).abs()`.

## 13. Exercises with Answers

**Exercise 1.** With `a = -5`, `b = -2`, what sign does `a.compareTo(b)` have? What sign does `a.abs().compareTo(b.abs())` have?

**Answer:** `a.compareTo(b) < 0` because `-5 < -2`. Conversely, `a.abs().compareTo(b.abs()) > 0` because `5 > 2`. Numeric ordering differs from magnitude comparison.

**Exercise 2.** Are two objects created by separate `new BigInteger("42")` calls equal under `equals`? Should `==` be used?

**Answer:** Yes, `equals` is `true`; `==` between two separately created objects is `false`, and inappropriate for checking value equality.

**Exercise 3.** What does `BigInteger.ZERO.signum()` return? Does `new BigInteger("-0").signum()` differ?

**Answer:** Both return `0`; `BigInteger` does not have a separate negative zero.

**Exercise 4.** Why does `BigInteger.valueOf(Long.MIN_VALUE).abs()` give the right positive result while `Math.abs(Long.MIN_VALUE)` stays negative?

**Answer:** `long` cannot represent positive `2^63`, so `Math.abs(long)` hits the representation boundary. `BigInteger` is not capped at 64 bits and holds `9223372036854775808`.

**Exercise 5.** If `n` is a negative `BigInteger`, after running `n.negate();` without assigning the result, does `n` change?

**Answer:** No. `BigInteger` is immutable; `n = n.negate()` is needed for the variable to reference the negated number.

**Exercise 6.** What does `BigInteger.valueOf(42).equals(Long.valueOf(42L))` return and why?

**Answer:** `false`. `BigInteger.equals` requires the object to be a `BigInteger` with the same value, and does not compare across `Number` subclasses merely for having the same mathematical value.

**Exercise 7.** Write an expression checking that `BigInteger total` is non-negative, assuming `total != null`.

**Answer:** `total.signum() >= 0` or `total.compareTo(BigInteger.ZERO) >= 0`. If input can be `null`, check `total != null` first.

**Exercise 8.** Why not use `a.subtract(b).intValue()` as a comparator between two huge `BigInteger`s?

**Answer:** Extracting `intValue()` can drop high bits, corrupting the sign and magnitude of the difference; `compareTo` computes exact order across the entire `BigInteger` range.

**Exercise 9.** What happens to the two keys `-7` and `7` in a `TreeSet<BigInteger>` if the comparator is only `(a,b) -> a.abs().compareTo(b.abs())`?

**Answer:** The comparator returns `0` for the two keys even though `equals` returns `false`. `TreeSet` may treat them as the same element per the comparator. To retain both, add a tie-breaker using `a.compareTo(b)` or use natural ordering.

**Exercise 10.** Compare `n.abs()` and `n.negate()` for `n = 17`, `n = -17`, `n = 0`.

**Answer:** For `17`, `abs = 17`, `negate = -17`; for `-17`, both are `17`; for `0`, both are `0`. The two methods differ in meaning even though they sometimes yield the same result.

**Key takeaway:** `compareTo` is ordering, `equals` is value equality, `signum` indicates sign, `abs` takes non-negative magnitude, and `negate` takes the additive inverse. All apply directly to large `BigInteger`s without narrowing to primitives; respect immutability, check for `null`, and never use object identity or lossy casts instead of mathematical comparison.