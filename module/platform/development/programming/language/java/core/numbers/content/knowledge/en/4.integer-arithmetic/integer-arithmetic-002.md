# Integer Division in Java: Why Is the Fractional Part Truncated Toward Zero?

When **both operands of `/` are integers**, Java performs **integer division**. The result is an integer: the fractional part of the mathematical quotient is **discarded toward zero** (*truncation toward zero*). Therefore:

- `7 / 3` → `2`, because the mathematical quotient is approximately `2.333...`.
- `-7 / 3` → `-2`, because the mathematical quotient is approximately `-2.333...`.
- `1 / 2` → `0`, not `0.5`.

This is the semantic rule of the operator, **not a precision bug or random rounding error**. To compute a quotient with a fractional part, you must make **at least one operand** a floating-point type before performing the division.

## 1. What Does `/` Do with Integer Types?

Java's primitive integral types are `byte`, `short`, `char`, `int`, and `long`. For an expression `a / b` where both operands belong to the integer group:

1. Java determines the computation type using **binary numeric promotion**. `byte` and `short` are promoted to at least `int`. If one operand is `long`, the integer division result is `long`.
2. The machine performs integer division on the two integer values.
3. The mathematical quotient has its **fractional part truncated toward zero**. The returned value has an integer type (`int` or `long`); there is no fractional part left to preserve.

| Expression | Mathematical quotient | Java value | Explanation |
| --- | ---: | ---: | --- |
| `7 / 3` | `2.333...` | `2` | Drops the part after the decimal point |
| `8 / 4` | `2` | `2` | Divides evenly |
| `1 / 2` | `0.5` | `0` | Positive value less than 1 is truncated to 0 |
| `-1 / 2` | `-0.5` | `0` | Fractional part is truncated toward 0 |
| `-7 / 3` | `-2.333...` | `-2` | Toward 0, not down to `-3` |
| `7 / -3` | `-2.333...` | `-2` | Negative quotient truncated toward 0 |
| `-7 / -3` | `2.333...` | `2` | Two negative signs yield a positive quotient |
| `10 / 2L` | `5` | `5L` | Has a `long` operand, so result type is `long` |

**Sign of the quotient:** If the quotient is non-zero, operands with the same sign produce a positive quotient; opposite signs produce a negative quotient. If the magnitude of the mathematical quotient is less than `1`, the result is `0`; Java does not have distinct `+0` and `-0` values for `int` or `long`.

**"Truncate toward 0" is different from "round to nearest":** `8 / 3` is `2` even though it is arithmetically closer to `3`; `-8 / 3` is `-2` even though the mathematical quotient is closer to `-3`. The `/` operator on two integers **does not perform rounding-to-nearest**.

## 2. Why Is `-7 / 3` Equal to `-2` Instead of `-3`?

There are three ways to obtain an integer from `-2.333...`:

- **Truncation toward zero:** drop the fractional part in the direction of 0 → `-2`.
- **Floor (round down):** take the greatest integer not exceeding the value → `-3`.
- **Ceiling (round up):** take the smallest integer not less than the value → `-2`.

For the positive number `2.333...`, both truncation and floor produce `2`, so the difference usually only shows up when the result is negative.

Java uses truncation for integer `/`. If you need **floor** division, use `Math.floorDiv(a, b)`; for example:

```java
int a = -7, b = 3;
int truncated = a / b;            // -2
int floored = Math.floorDiv(a, b); // -3
```

`Math.floorDiv` has overloads for `int` and `long`. Choose the rule based on business logic: splitting a debt, computing indices of buckets with negative coordinates, and converting negative time intervals may require floor; computing an ordinary integer quotient may require truncation. Do not replace `/` with `Math.floorDiv` out of habit without determining the desired rounding rule.

## 3. The Remainder Operator `%` Paired with Division `/`

In integer division, `%` computes the **remainder**, not a "percentage" operation. For dividend `a` and divisor `b != 0`, the quotient `q = a / b` and remainder `r = a % b` satisfy the relation:

\[
a = q \times b + r
\]

for ordinary integer divisions. Java chooses `q` by truncating toward zero, which gives the remainder `r` the following properties:

- `|r| < |b|` mathematically when `b != 0`.
- If `r != 0`, **the sign of `r` matches the sign of `a`** (the dividend), regardless of the sign of `b`.
- If `a` is evenly divisible by `b`, then `r == 0`.

| `a` | `b` | `a / b` | `a % b` | Check |
| ---: | ---: | ---: | ---: | --- |
| 7 | 3 | 2 | 1 | `7 = 2 * 3 + 1` |
| -7 | 3 | -2 | -1 | `-7 = (-2) * 3 - 1` |
| 7 | -3 | -2 | 1 | `7 = (-2) * (-3) + 1` |
| -7 | -3 | 2 | -1 | `-7 = 2 * (-3) - 1` |

Do not confuse `%` with a mathematical modulo that always returns a non-negative number. For instance, `-7 % 3 == -1` in Java, whereas `Math.floorMod(-7, 3) == 2`. When `b` is positive, `Math.floorMod(a, b)` is suitable when you need a cyclic index or bucket in `0..b-1` even when `a` is negative.

**Exception to understand:** `Integer.MIN_VALUE / -1` and `Long.MIN_VALUE / -1L` do not have a mathematical quotient representable in the target type itself. Java produces an overflow result (see section 7); do not extrapolate every range property of mathematical quotients to this case without considering type limits.

## 4. To Get a Decimal Result, Change the Type Before Division

Writing `double result = 1 / 2;` still produces **`0.0`**, because Java evaluates `1 / 2` in `int` before converting the result to `double`. You must use a floating-point literal or cast an operand:

```java
double wrong = 1 / 2;          // 0.0: integer division ran first
double correctA = 1.0 / 2;     // 0.5: 1.0 is double
double correctB = (double) 1 / 2; // 0.5: converted before division
double correctC = 1 / 2.0;     // 0.5: 2.0 is double
double tooLate = (double) (1 / 2); // 0.0: cast after division
```

When one operand is `double`, floating-point division can produce a fractional part; however, `double` has finite binary precision and **cannot represent every decimal fraction exactly**. "Wanting a result with a fractional part" is different from "wanting an exact base-10 decimal result". For currency or decimal rounding rules, consider `BigDecimal` with an explicit `RoundingMode` policy.

Be careful when casting a very large `long` to `double`: the integer value may be rounded because the `double` significand holds only 53 bits of effective precision. If the problem demands exact integer quotients and remainders for huge numbers, do not convert to `double` to solve it.

## 5. Result Types, Expressions, and Order of Operations

### `byte` and `short` Still Divide as `int`

```java
byte numerator = 7, denominator = 3;
int q = numerator / denominator;  // Valid, q = 2
// byte invalid = numerator / denominator; // Compile error: result is int
```

`byte`/`short` operands are promoted to `int`. Meanwhile, `long / int` produces a result of type `long`, but **still truncates toward zero**:

```java
long q = 10_000_000_000L / 3;  // 3_333_333_333L
```

`long` only expands the **value range**; it does not automatically turn integer division into fractional division.

### `*`, `/`, and `%` Share the Same Precedence Level

They associate from left to right. Because integer division discards the fractional part, changing parentheses can change the result:

```java
int a = 20 / 3 * 3;   // (20 / 3) * 3 = 6 * 3 = 18
int b = 20 * 3 / 3;   // (20 * 3) / 3 = 60 / 3 = 20
```

Example `b` works because `20 * 3` does not exceed `int`. With large operands, **multiplying before dividing** can overflow, so you cannot arbitrarily rewrite a formula to "preserve precision" without checking the intermediate range.

In an average example:

```java
int sum = 7, count = 2;
int averageTruncated = sum / count;      // 3
double averageDecimal = (double) sum / count; // 3.5
```

Determine whether the expected output is a truncated integer quotient or a decimal value before choosing the expression.

## 6. Standalone Runnable Example on Java 17+

Save the following program to `IntegerDivisionDemo.java`:

```java
public class IntegerDivisionDemo {
    public static void main(String[] args) {
        System.out.println("7 / 3 = " + (7 / 3) + ", 7 % 3 = " + (7 % 3));
        System.out.println("-7 / 3 = " + (-7 / 3) + ", -7 % 3 = " + (-7 % 3));
        System.out.println("7 / -3 = " + (7 / -3) + ", 7 % -3 = " + (7 % -3));
        System.out.println("-7 / -3 = " + (-7 / -3) + ", -7 % -3 = " + (-7 % -3));

        System.out.println("1 / 2 = " + (1 / 2));
        System.out.println("double division = " + ((double) 1 / 2));
        System.out.println("cast after division = " + ((double) (1 / 2)));

        byte a = 7, b = 3;
        int quotient = a / b;
        System.out.println("byte division result = " + quotient);

        System.out.println("floorDiv(-7, 3) = " + Math.floorDiv(-7, 3));
        System.out.println("floorMod(-7, 3) = " + Math.floorMod(-7, 3));
        System.out.println("MIN / -1 = " + (Integer.MIN_VALUE / -1));
        System.out.println("MIN % -1 = " + (Integer.MIN_VALUE % -1));

        int zero = 0;
        try {
            System.out.println(7 / zero);
        } catch (ArithmeticException e) {
            System.out.println("integer division by zero: ArithmeticException");
        }
        System.out.println("long division = " + (10_000_000_000L / 3));
    }
}
```

Use JDK 17 or later to compile and run:

```bash
javac IntegerDivisionDemo.java
java IntegerDivisionDemo
```

Stdout:

```text
7 / 3 = 2, 7 % 3 = 1
-7 / 3 = -2, -7 % 3 = -1
7 / -3 = -2, 7 % -3 = 1
-7 / -3 = 2, -7 % -3 = -1
1 / 2 = 0
double division = 0.5
cast after division = 0.0
byte division result = 2
floorDiv(-7, 3) = -3
floorMod(-7, 3) = 2
MIN / -1 = -2147483648
MIN % -1 = 0
integer division by zero: ArithmeticException
long division = 3333333333
```

**Key observations:** `/` and `%` are consistent with the operand signs; casting **before** division differs from casting **after** division; `Math.floorDiv`/`Math.floorMod` give different results when dividing negative numbers; `MIN_VALUE / -1` overflows; a zero divisor throws an exception.

## 7. Two Edge Cases to Control

### Integer Division by Zero

`int` and `long` do not have infinity/NaN values like floating-point types. Therefore, `a / 0` or `a % 0` throws an **`ArithmeticException`** at runtime. For example:

```java
int divisor = 0;
int value = 5;
try {
    int result = value / divisor;
} catch (ArithmeticException ex) {
    System.out.println("Cannot divide integers by zero");
}
```

When receiving a divisor from input, **check `divisor != 0` before dividing**, then report invalid data or handle it per application policy. An invalid divisor should not be silently replaced with `1` unless business rules permit it.

### `MIN_VALUE / -1`: Quotient Cannot Fit in the Type

`int` has the range `-2_147_483_648` to `2_147_483_647`. The mathematical absolute value of `Integer.MIN_VALUE` is `2_147_483_648`, which **exceeds the `int` range**. When divided by `-1`:

```java
int value = Integer.MIN_VALUE;
int q = value / -1; // -2147483648, due to integer overflow
int r = value % -1; // 0
```

Similarly, `Long.MIN_VALUE / -1L` returns `Long.MIN_VALUE`. This is a special case that **does not automatically throw an exception**. Truncation toward zero is still the rule for determining the quotient, but **the finite range of the integer type** causes the result to follow overflow semantics.

If you do not want to accept overflow:

```java
int dividend = Integer.MIN_VALUE;
int divisor = -1;
if (divisor == -1 && dividend == Integer.MIN_VALUE) {
    throw new ArithmeticException("integer quotient overflows int");
}
int quotient = dividend / divisor;
```

The snippet above illustrates a guard branch, **not a standalone program**. When used in a real method, also check for a zero divisor and keep exception handling consistent.

Another approach when an `int` division might need a result larger than the `int` range is to **promote the dividend to `long` before dividing**, for example `(long) Integer.MIN_VALUE / -1 == 2_147_483_648L`. For `long` cases exceeding the range, use `BigInteger` when an exact integer result is strictly required.

## 8. Using `/` in Applications Without Breaking Business Logic

**Example 1: Fixed-size grouping.** Suppose there are 11 people and each group holds at most 4 people; `11 / 4 == 2` is **two full groups**, with `11 % 4 == 3` people remaining. If asked for the total number of groups to prepare, **3 groups** are needed.

For `total >= 0` and `size > 0`, a way to avoid intermediate overflow from `(total + size - 1) / size` is:

```java
int total = 11;
int size = 4;
int groups = total / size + (total % size == 0 ? 0 : 1); // 3
```

This formula only applies under the stated assumptions of non-negative total and positive size; if data can be negative, you must redefine the rounding semantics and possibly use `Math.floorDiv` or another business rule.

**Example 2: Ratios and percentages.** If `completed = 1` and `total = 4`, the expression `completed / total * 100` evaluates to **0**, because `1 / 4` is truncated to `0` before multiplying. If only an integer percentage is needed and the data is within a suitable range, you can compute `(long) completed * 100 / total` to avoid intermediate `int` overflow and then explicitly handle truncation of the remainder. If a decimal percentage is needed, use `100.0 * completed / total` or a decimal type with a rounding rule matching business requirements.

**Example 3: Bucketing by negative indices.** When grouping negative timestamps or coordinates into bins of positive width, `a / width` can place `-1` into bin `0` because of truncation toward zero. `Math.floorDiv(-1, width)` places it into bin `-1` when `width > 1`, matching how a number line is partitioned into floor-aligned intervals.

The common thread across all three examples: before choosing an expression, determine whether the requirement calls for **quotient truncated toward zero**, **round down (floor)**, **round up (ceiling)**, **floating-point quotient**, or **grouping with remainder**.

## 9. Common Mistakes

1. **"If the receiving variable is `double`, `1 / 2` will give `0.5`."** False: Java evaluates `1 / 2` to `int` `0` first and then assigns `0.0`.
2. **"`(double) (a / b)` restores the fractional part."** False: integer division has already discarded the fraction; you need `(double) a / b`.
3. **"Integer division always rounds down."** False for non-integer negative quotients: `-7 / 3 == -2`, whereas `Math.floorDiv(-7,3) == -3`.
4. **"The remainder is always non-negative."** False: `-7 % 3 == -1`. If you need a non-negative remainder with a positive divisor, consider `Math.floorMod`.
5. **"Using `long` keeps the decimal part."** False: `10L / 4` still equals `2L`; `long` only widens the range.
6. **"`byte / byte` returns `byte`."** False: the operands are promoted to `int`, and the expression type is `int`.
7. **"Swapping the order of multiplication and division does not change the result."** False when integer division truncates the fraction; and multiplying first can overflow.
8. **"Dividing an integer by 0 returns infinity."** False: it throws `ArithmeticException`, unlike floating-point division.
9. **"Dividing `Integer.MIN_VALUE` by -1 always throws an overflow error."** False: the result is `Integer.MIN_VALUE` due to defined overflow behavior.
10. **"`a / b` automatically gives the integer closest to the true quotient."** False: Java truncates toward zero. If business logic requires a specific rounding mode, express that rule explicitly.

## 10. Self-Check

1. **What do `9 / 4` and `-9 / 4` produce?** → `2` and `-2`, because the fractional part is truncated toward zero.
2. **What do `9 % 4` and `-9 % 4` produce?** → `1` and `-1`, a non-zero remainder takes the sign of the dividend.
3. **What value does `double ratio = 3 / 2;` store?** → `1.0`. For `1.5`, write `double ratio = 3.0 / 2;`.
4. **Why is `Math.floorDiv(-9,4) == -3`?** → Floor takes the greatest integer not exceeding `-2.25`, which is `-3`.
5. **Given `byte a = 8, b = 3;`, what type is the expression `a / b`?** → `int`.
6. **If there are 13 items and each box holds 5, how many boxes are needed?** → `13 / 5 = 2` full boxes and `13 % 5 = 3` remaining, so **3** boxes are needed if all items must be packed.

**Key Takeaway:** `/` between two integer operands produces an **integer quotient truncated toward zero**. Distinguish this rule from *floor* and *rounding to nearest*; if you need a value with a fractional part, convert at least one operand to an appropriate numeric type **before division**. Use `%` to handle remainders, and check the divisor, result range, and the `MIN_VALUE / -1` edge case when safe computation is required.
