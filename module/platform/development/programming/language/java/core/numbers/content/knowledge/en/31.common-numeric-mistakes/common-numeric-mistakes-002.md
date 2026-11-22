# Dividing Two ints Before Converting to double: Why Is the Fractional Part Lost?

## 1. The Typical Mistake

In Java, the following code **does not produce 3.5**:

~~~java
int numerator = 7;
int denominator = 2;
double ratio = numerator / denominator;

System.out.println(ratio); // 3.0
~~~

Even though the target variable has type `double`, Java performs the division `numerator / denominator` **first**, on **two `int` operands**, so it uses **integer division** and produces `3`. Only then is `3` converted to `3.0` when assigned to `ratio`. The `0.5` part has already been discarded, and later conversion cannot recover it.

The correct fix for computing a real-number ratio:

~~~java
double ratio = (double) numerator / denominator; // 3.5
~~~

The line above converts **one operand** to `double` **before the division**. The `/` operator then applies **binary numeric promotion** and performs floating-point division, producing `3.5`.

This article focuses on expression evaluation order, casting rules, mistakes made when computing averages/percentages/progress, dividing negative numbers, division by zero, overflow cases, and when `double` is still not accurate enough.

## 2. Operand Types Determine the Division Type

In Java, the `/` operator applies to primitive numeric types; before evaluating, Java applies **binary numeric promotion** rules. Simply put:

- If one operand is `double`, the operation uses `double`.
- If there is no `double` but one operand is `float`, it uses `float`.
- If there is no `double`/`float` but one operand is `long`, it uses `long`.
- Otherwise, smaller integer types such as `byte`, `short`, and `char` are promoted to `int`, and the operation uses `int`.

**The deciding point is the type of the operands directly at the `/` operator**, not the type of the variable receiving the result afterward.

| Expression | Division Type | Result | Explanation |
|---|---|---|---|
| `7 / 2` | `int` | `3` | Truncates fractional part |
| `7L / 2` | `long` | `3L` | Has `long` but is still integer division |
| `7.0 / 2` | `double` | `3.5` | Literal `7.0` is double |
| `7 / 2.0` | `double` | `3.5` | Literal `2.0` is double |
| `7f / 2` | `float` | `3.5f` | Literal has suffix `f` |
| `(double) 7 / 2` | `double` | `3.5` | Casts operand before dividing |
| `(double) (7 / 2)` | `int` then cast to `double` | `3.0` | Casts **the result whose remainder was already truncated** |
| `7 / (double) 2` | `double` | `3.5` | Casts right operand first |
| `7 / 2 * 1.0` | `int` at first division | `3.0` | Fractional part lost before multiplying |
| `7 * 1.0 / 2` | `double` at division | `3.5` | Converted to double at the first multiplication |

`int` and `long` differ in integer width; widening to `long` **does not produce fractional results**. `float` and `double` allow representing fractions, but they are binary floating-point numbers with finite precision.

### Why Doesn't the Target Type Flow Backward?

Consider:

~~~java
double result = 7 / 2;
~~~

Step-by-step analysis:

1. Java infers that both literals `7` and `2` are `int`.
2. `/` is evaluated as `int` division: `7 / 2 == 3`.
3. Assigning to a `double` variable triggers widening primitive conversion: `3` becomes `3.0`.

No step inspects `result` and "goes back" to perform the division in `double`. Similarly:

~~~java
double result = 7 / 2;           // 3.0
double result2 = (double) (7 / 2); // 3.0
double result3 = (double) 7 / 2;   // 3.5
~~~

For these three expressions, Java can assign the result to `double` in all three cases; however, only the third expression uses floating-point division from the start.

## 3. Parentheses and Cast Placement Change the Result

Compare two ways of placing parentheses:

~~~java
int a = 7;
int b = 2;

double wrong = (double) (a / b);  // 3.0
double right = ((double) a) / b;  // 3.5
~~~

In `wrong`, the parentheses `(a / b)` force integer division to run first. In `right`, the parentheses `((double) a)` wrap only operand `a`, making `a` a `double` when `/` is evaluated.

You can cast **either operand**:

~~~java
double x = (double) a / b; // 3.5
double y = a / (double) b; // 3.5
double z = a / 2.0;        // 3.5
~~~

When the divisor comes from a variable, explicitly casting `a` or `b` is readable and avoids accidentally breaking the formula if a literal value is no longer fixed.

### Operators of Equal Precedence Evaluate Left-to-Right

Multiplication and division share the same precedence and associate from left to right:

~~~java
double lost = 7 / 2 * 100.0; // 300.0
double good = 7 * 100.0 / 2; // 350.0
~~~

In `lost`, Java already evaluated `7 / 2 == 3` before multiplying by `100.0`. Having a `double` **later** does not save the lost fractional part. In `good`, the multiplication `7 * 100.0` produces a `double` first, so the subsequent division also uses `double`.

The same issue appears in real-world code:

~~~java
int completed = 3;
int total = 8;

double incorrectPercent = 100.0 * (completed / total); // 0.0
double correctPercent = 100.0 * completed / total;     // 37.5
~~~

The parenthesized form computes `3 / 8 == 0` first and then multiplies by 100; the correct form multiplies by `100.0` first, giving the true percentage `37.5%`.

For easier code review, you can also express this directly:

~~~java
double fraction = (double) completed / total;
double percent = fraction * 100.0;
~~~

For critical data, you should next decide whether `double` precision is acceptable or whether an exact decimal type like `BigDecimal` is needed.

## 4. Standalone Runnable Java 17+ Program

Save the file as **`IntegerDivisionDemo.java`**:

~~~java
public class IntegerDivisionDemo {
    public static void main(String[] args) {
        int numerator = 7;
        int denominator = 2;

        double wrong = (double) (numerator / denominator);
        double correct = (double) numerator / denominator;

        System.out.println("wrong = " + wrong);
        System.out.println("correct = " + correct);
        System.out.println("right operand cast = "
                + numerator / (double) denominator);
        System.out.println("literal double = " + numerator / 2.0);

        System.out.println("-7 / 2 = " + (-numerator / denominator));
        System.out.println("-7 % 2 = " + (-numerator % denominator));
        System.out.println("floorDiv(-7, 2) = "
                + Math.floorDiv(-numerator, denominator));
        System.out.println("floorMod(-7, 2) = "
                + Math.floorMod(-numerator, denominator));

        int completed = 3;
        int total = 8;
        System.out.println("wrong percent = "
                + 100.0 * (completed / total));
        System.out.println("correct percent = "
                + 100.0 * completed / total);

        int zero = 0;
        try {
            int ignored = numerator / zero;
            System.out.println(ignored);
        } catch (ArithmeticException expected) {
            System.out.println(
                    "integer divide by zero: ArithmeticException");
        }

        System.out.println("double divide by zero = " + numerator / 0.0);
        System.out.println("double zero by zero = " + 0.0 / 0.0);
        System.out.println("MAX/MIN edge = "
                + (Integer.MIN_VALUE / -1));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac IntegerDivisionDemo.java
java IntegerDivisionDemo
~~~

**Verified stdout:**

~~~text
wrong = 3.0
correct = 3.5
right operand cast = 3.5
literal double = 3.5
-7 / 2 = -3
-7 % 2 = -1
floorDiv(-7, 2) = -4
floorMod(-7, 2) = 1
wrong percent = 0.0
correct percent = 37.5
integer divide by zero: ArithmeticException
double divide by zero = Infinity
double zero by zero = NaN
MAX/MIN edge = -2147483648
~~~

This example demonstrates casting order while also distinguishing negative integer division from floating-point division by zero. The `Integer.MIN_VALUE / -1` result is an integer division overflow exception case with its own rule in Java; section 7 explains it in detail.

## 5. Integer Division Does Not Round Down Toward Negative Infinity

When both operands are `int` or `long`, division produces an integer quotient **truncated toward zero**, rather than always using `Math.floor`.

~~~java
System.out.println(7 / 2);    // 3
System.out.println(-7 / 2);   // -3
System.out.println(7 / -2);   // -3
System.out.println(-7 / -2);  // 3
~~~

In real arithmetic:

- `7 / 2 = 3.5`, truncated toward zero gives `3`.
- `-7 / 2 = -3.5`, truncated toward zero gives `-3`. Rounding down toward negative infinity would give `-4`.

Java provides `Math.floorDiv` when division **rounded down toward negative infinity** is required:

~~~java
int truncated = -7 / 2;               // -3
int floored = Math.floorDiv(-7, 2);   // -4
~~~

If you need the remainder corresponding to the floor quotient, use `Math.floorMod`. Distinguish:

~~~java
System.out.println(-7 % 2);            // -1
System.out.println(Math.floorMod(-7, 2)); // 1
~~~

`/` and `%` on `int` follow Java's contract: except for the overflow case `MIN_VALUE / -1`, quotient `q = a / b` and remainder `r = a % b` satisfy `a == b * q + r` in integer arithmetic under the contract, with `|r| < |b|` and the remainder having the same sign as the dividend or being zero. With `floorDiv`/`floorMod`, choose them together as a pair when business logic requires partitioning toward negative infinity.

**Do not use `(int) ((double) a / b)` to implement `floorDiv` yourself.** Casting from `double` to `int` also truncates toward zero (and has special rules for overflow/NaN). If you need integer division with floor semantics, call the appropriate API.

## 6. Real-World Bugs in Averages, Percentages, and Formulas

### 6.1. Computing an Average Score

~~~java
int totalScore = 17;
int subjects = 4;

double wrongAverage = totalScore / subjects;          // 4.0
double correctAverage = (double) totalScore / subjects; // 4.25
~~~

Assigning to `double` does not automatically turn `totalScore / subjects` into `double` division. If you only want the integer part, you can intentionally use `int quotient = totalScore / subjects` and name the variable to reflect its meaning.

### 6.2. Computing Completion Ratio

~~~java
int done = 3;
int planned = 8;

double wrongRatio = done / planned;            // 0.0
double correctRatio = (double) done / planned; // 0.375
double correctPercent = correctRatio * 100;   // 37.5
~~~

A serious bug when only part of the work is done: the true ratio is nonzero, yet integer division yields 0, causing **0%** to be displayed. For `planned == 0`, you must define the application's rule: return a "no plan" status, report an error, or return a documented convention value; never divide by 0 directly.

### 6.3. Average of Two Large ints

Casting properly at the division is still **not enough** if the preceding addition has already overflowed:

~~~java
int a = Integer.MAX_VALUE;
int b = Integer.MAX_VALUE;

double wrong = (a + b) / 2.0;        // -1.0: a+b overflows first
double right = ((double) a + b) / 2.0; // 2.147483647E9
~~~

In `wrong`, `a + b` is `int` addition, overflowing from `4294967294` (mathematically) down to `-2` via 32-bit wraparound; `-2 / 2.0` equals `-1.0`. A `double` target variable or divisor `2.0` cannot fix an already-overflowed addition.

Another approach is to widen to `long` **before adding**:

~~~java
double exactSumThenDivide =
        ((long) a + b) / 2.0; // 2.147483647E9
~~~

For two `int` values, their sum always fits within `long`, so the sum does not overflow `long`; dividing by `2.0` afterward uses `double`. However, if the two operands are `long`s near the extremes to begin with, even `long` addition can overflow; in that case a better design is needed, such as overflow checking or `BigInteger`.

### 6.4. Pagination and Rounding Up Page Counts

With `itemCount = 10` and `pageSize = 3`, the needed page count is **4**, not 3.

~~~java
int itemCount = 10;
int pageSize = 3;

int wrongPages = itemCount / pageSize; // 3
int correctPages = itemCount / pageSize
        + (itemCount % pageSize == 0 ? 0 : 1); // 4
~~~

This formula is correct when `itemCount >= 0` and `pageSize > 0`. It avoids converting to `double` and avoids overflow of the common formula `(itemCount + pageSize - 1) / pageSize` when `itemCount + pageSize - 1` exceeds the `int` limit. If you only need an integer page count, there is no compelling reason to use `double`; choose integer division with an appropriate ceiling policy.

Similarly, when calculating "how many buckets are needed to hold n items", the key is not just switching to `double`, but determining whether **the desired result is an integer rounded up**.

## 7. Dividing by Zero: int and double Have Different Contracts

For integers:

~~~java
int denominator = 0;
// int invalid = 1 / denominator; // throws ArithmeticException at runtime
~~~

Integer division by zero throws `ArithmeticException`. Nor should a constant expression `1 / 0` be put in code as a valid value; do not rely on whether an IDE/compiler flags it in every context as a substitute for input validation.

When a `double` or `float` operand is present, Java follows IEEE 754 floating-point rules for division by zero:

~~~java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(-1.0 / 0.0); // -Infinity
System.out.println(0.0 / 0.0);  // NaN
~~~

These are special floating-point values, **unlike the integer division error**. Business policy may require rejecting a zero divisor in both cases. If an expression becomes `Infinity` or `NaN` and propagates through later steps, reports or calculations can be corrupted without any exception.

**Always decide whether a zero input is valid.** For example, a ratio function only makes sense when total is greater than 0:

~~~java
static double completionRatio(int completed, int total) {
    if (total <= 0) {
        throw new IllegalArgumentException("total must be positive");
    }
    return (double) completed / total;
}
~~~

This is an **illustrative method** placed inside a class, not a standalone program with `main`. If `completed` can be negative or greater than `total`, the domain must also specify whether to reject it; casting does not replace validation.

## 8. A double Operand Can Introduce Binary Rounding Error

Converting an operand to `double` fixes the integer division bug, but **it does not turn every fraction into an exact decimal number**.

~~~java
double oneThird = (double) 1 / 3;
System.out.println(oneThird); // 0.3333333333333333
~~~

The real number 1/3 has an infinite expansion, whereas `double` only has finite bits of precision, so the result is an approximation. Similarly, decimal numbers like 0.1 and 0.2 generally have no exact binary representation.

For `int` values, every individual value converted to `double` is represented exactly because `double` has 53 bits of binary precision and `int` only has 32 bits. However, the **division result** between them may still not be exactly representable as a `double`.

For `long`, not every integer is represented exactly in `double`. For example:

~~~java
long large = 9_007_199_254_740_993L;  // 2^53 + 1
double converted = (double) large;
// converted is the nearest double, not preserving every unit of large.
~~~

If exact comparison or reconciliation of large integers is required, do not convert to `double` and assume all numbers remain distinct. Use `long` when results stay within `long` range and operations do not overflow, or `BigInteger` for integers beyond that range. For ratios requiring decimal precision or well-defined rounding rules, consider `BigDecimal`.

### When BigDecimal Is Needed

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal numerator = BigDecimal.valueOf(7);
BigDecimal denominator = BigDecimal.valueOf(2);
BigDecimal exact = numerator.divide(denominator);

System.out.println(exact); // 3.5

BigDecimal oneThird = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3), 4, RoundingMode.HALF_UP);
System.out.println(oneThird); // 0.3333
~~~

This snippet sits inside a method and assumes imports are declared. `BigDecimal.divide(divisor)` without a rounding mode only succeeds when the quotient has a terminating decimal representation; for `1/3` you must specify an appropriate scale/rounding mode or `MathContext`. Choose the number of decimal digits based on actual requirements rather than always defaulting to 4.

**Avoid** constructing monetary amounts with `new BigDecimal(0.1)` because the `double` input is already a binary approximation. For monetary data, prefer parsing decimal strings, using the smallest integer unit, or designing `BigDecimal` arithmetic from the start.

## 9. Casting Before or After Also Affects Overflow and Precision

General rule: **any operation occurring before a cast keeps the semantics of the active type**, including overflow, integer division, and float precision loss.

| Expression | What Happens First | Consequence |
|---|---|---|
| `(double) (a / b)` | `int` division | Fractional part is lost |
| `(double) a / b` | Cast `a` to `double` | Keeps fractional part if quotient needs it |
| `(double) (a + b) / 2` | `int` addition | Can overflow before cast |
| `((double) a + b) / 2` | Cast `a` to `double` before adding | Avoids `int` overflow in that addition, but uses floating point |
| `(long) (a * b)` | `int` multiplication | Can overflow before cast |
| `(long) a * b` | Cast `a` to `long` before multiplying | `long` multiplication, still bounded by `long` limits |
| `(float) a / b` | `float` division | Has fractional part, but lower precision than `double` |
| `a / (long) b` | `long` division | Still truncates fractional part |

Concrete example of multiplying before casting:

~~~java
int a = 50_000;
int b = 50_000;

long wrong = (long) (a * b);  // -1794967296 due to int overflow
long right = (long) a * b;    // 2500000000
~~~

This extends the principle from division to multiplication to prevent the same kind of error: **casting to the right type, but too late**. In Java, if an operation must be exact and might exceed its current type, promote the type or apply overflow checks **before the operation**.

## 10. Choosing the Calculation Based on Business Meaning

Depending on the goal, you should not always convert to `double`:

| Goal | Example Solution | Reason |
|---|---|---|
| Get integer quotient truncated toward zero | `int q = a / b;` | Right when you only need whole-unit counts |
| Compute approximate real ratio | `double r = (double) a / b;` | Avoids integer division |
| Compute approximate percentage | `100.0 * a / b` | Converts to double before dividing |
| Integer division rounded down toward negative infinity | `Math.floorDiv(a, b)` | Correct for negative numbers |
| Compute page count for non-negative counts | `a / b + (a % b != 0 ? 1 : 0)` | Counts whole groups and rounds up |
| Exact money calculation by scale/mode | `BigDecimal.divide(..., scale, mode)` | Clear decimal rules |
| Exact large-integer calculation | `BigInteger` and its divide method | Avoids precision loss from double conversion |

Expressions with `a / b` require `b != 0`; the page-count formula assumes `a >= 0, b > 0`. If business logic defines these conditions upfront, validating inputs at the boundary is clearer and safer than handling exceptions across multiple layers.

## 11. How to Test to Catch the Bug on the First Review

Do not test only divisible cases, because `6 / 2` gives `3.0` even with the buggy `double result = 6 / 2`. A test suite should include:

1. **Non-zero fractional part:** `7/2 → 3.5`, `1/2 → 0.5`, `3/8 → 0.375` when `double` is required.
2. **Exact division:** `8/2 → 4.0`; ensures adding a cast did not break simple cases.
3. **Negative numbers:** `-7/2 == -3` under `int` division; `-3.5` under `double`; `-4` under `Math.floorDiv`.
4. **Zero cases:** `0/5 == 0`; a zero divisor is rejected according to policy.
5. **int boundaries:** `Integer.MAX_VALUE`, `Integer.MIN_VALUE`, and addition/multiplication before division to catch overflow early.
6. **Operator precedence bugs:** `100.0 * (3/8) == 0.0` and `100.0 * 3/8 == 37.5`.
7. **Real-number precision:** hard-to-represent ratios (1/3) need comparison with an appropriate tolerance or domain decimal expectations; do not carelessly use `==` between two floating-point formulas computed via different paths.
8. **Return destination:** if a function returns `double` while its body returns `a/b` with two `int`s, the signature does not prevent the bug. Tests must verify the numerical result.

Plain Java assertion example inside a method:

~~~java
int a = 7;
int b = 2;
double actual = (double) a / b;

if (Double.compare(actual, 3.5) != 0) {
    throw new AssertionError("Expected 3.5");
}
~~~

Here `3.5` is exactly representable in binary, so direct comparison is reliable for this isolated case. For `1/3` or long floating-point calculation chains, choose a tolerance check or exact reference appropriate for your requirements.

### Questions to Ask When Reviewing a Division Expression

- What types do the two operands at `/` currently have?
- Do you need the **fractional part**, or only the **integer quotient**?
- Is the cast placed before the division, or does it wrap **the entire computed result**?
- Could preceding additions or multiplications overflow?
- Can the divisor be 0?
- If using `double`, is approximate precision sufficient?
- For negative numbers, do you want truncation or floor?
- If the result represents currency, are scale and rounding rules defined?

## 12. Common Mistakes and Quick Fixes

**Wrong:** `double avg = sum / count;` when `sum` and `count` are both `int` and a fractional result is needed.

**Right:** `double avg = (double) sum / count;` when `count` is non-zero.

**Wrong:** `double avg = (double) (sum / count);` because the cast is too late.

**Right:** `double avg = sum / (double) count;` or cast the numerator first.

**Wrong:** `double pct = (done / total) * 100.0;` because parentheses force integer division first.

**Right:** `double pct = ((double) done / total) * 100.0;` with `total` non-zero.

**Wrong:** `double avg = (a + b) / 2.0;` if `a+b` can overflow `int`.

**Right:** `double avg = ((double) a + b) / 2.0;` when `double` semantics fit, or widen to `long` before adding if range allows.

**Wrong:** `double r = (long) a / b;` thinking the division will now keep a fractional part.

**Right:** `double r = (double) a / b;` because `long` is still an integer type.

**Wrong:** using `Math.floorDiv` just to "get a number with decimal places".

**Right:** `Math.floorDiv` is for **floor integer quotients**; to keep the fractional part, a floating-point type must participate in the division.

## 13. Exercises

**Exercise 1.** Predict the output:

~~~java
System.out.println(5 / 2);
System.out.println((double) (5 / 2));
System.out.println((double) 5 / 2);
System.out.println(5 / 2.0);
~~~

**Exercise 2.** With `a = -5` and `b = 2`, compare `a / b`, `(double) a / b`, `Math.floorDiv(a,b)`, `a % b`, and `Math.floorMod(a,b)`.

**Exercise 3.** Fix this code:

~~~java
static double percentage(int success, int total) {
    return success / total * 100;
}
~~~

Requirement: return `37.5` when `success=3` and `total=8`; reject `total=0`.

**Exercise 4.** Why doesn't `double x = (Integer.MAX_VALUE + Integer.MAX_VALUE) / 2.0;` give the expected average? Fix it without adding two `int`s first.

**Exercise 5.** If a page count requires integer ceiling division for `items = 10, pageSize = 3`, why is merely casting to `double` incomplete for the requirement? Choose a way to compute the page count returning `int`.

**Reference Answers:**

1. `2`, `2.0`, `2.5`, `2.5`.
2. `-2`, `-2.5`, `-3`, `-1`, `1`.
3. Check `total != 0` (or `total > 0` per domain), then `return (double) success / total * 100.0;`.
4. Integer addition overflows before dividing. Use `((double) Integer.MAX_VALUE + Integer.MAX_VALUE) / 2.0` or add as `long` first.
5. The page count must be an integer rounded up; with non-negative `items` and positive `pageSize`, use `items / pageSize + (items % pageSize == 0 ? 0 : 1)` to get 4.

## 14. Java SE 17 Standard References

- Java Language Specification, ``15.17.2 Division Operator /`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2
- Java Language Specification, ``5.6 Numeric Contexts` (binary numeric promotion): https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6
- Java Language Specification, ``5.1.2 Widening Primitive Conversion`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2
- Java SE 17, `Math.floorDiv`/`floorMod`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html

**Remember:** `double result = a / b;` with two `int`s performs **integer division first and only then converts to double**. To preserve the fractional part, place `(double)` before **at least one operand of the division** and ensure no preceding `int` operation has lost information or overflowed.
