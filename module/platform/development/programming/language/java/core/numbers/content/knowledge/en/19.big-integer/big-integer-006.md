# BigInteger.divideAndRemainder and Divisibility Checks in Java

## 1. Goal and Problem

Java provides the `java.math.BigInteger` type to work with integers whose magnitudes exceed the `int` and `long` ranges. When determining whether a large number is divisible by another, integer division and **remainder** operations are the primary tools. The `divideAndRemainder(BigInteger divisor)` method returns **both the quotient and the remainder** in a single call.

After this lesson, you will:

- Know how to use `divideAndRemainder`, `divide`, and `remainder` according to their contracts.
- Read the returned `BigInteger[]`: `result[0]` is the quotient, `result[1]` is the remainder.
- Check divisibility accurately using the condition that the remainder equals `BigInteger.ZERO`.
- Understand the rules for negative numbers: quotient truncated toward **0**, remainder matching the sign of the dividend if nonzero.
- Distinguish `remainder` from `mod`: both deal with remainders, but **their sign rules and argument domains differ**.
- Handle division by zero, division in counting/scheduling problems, string inputs, and calculations on very large numbers.
- Know when to obtain both quotient and remainder, and when only a divisibility check is needed.

Examples use **Java 17+**. No external libraries or preview features are needed.

## 2. What Is `BigInteger` and Why Not Use `long`?

`long` is signed and holds values from `-9223372036854775808` to `9223372036854775807`. If numbers in a calculation exceed this range, primitive integer arithmetic can overflow, producing wrong results.

`BigInteger` represents integers with arbitrary precision, subject to JVM memory and practical processing capacity. It is an **immutable class**: operations return a new result or another valid instance without modifying the source number.

~~~java
import java.math.BigInteger;

// Place the following statements inside a method:
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger divisor = BigInteger.valueOf(9L);

BigInteger[] result = huge.divideAndRemainder(divisor);
System.out.println(result[0]); // Quotient
System.out.println(result[1]); // Remainder
~~~

Pay attention to how large numbers are created: prefer `new BigInteger("...")` from a **character string** when the value exceeds the `long` range. Never write an oversized integer literal and pass it to `BigInteger.valueOf(...)`, as the literal is already invalid at compile time.

~~~java
BigInteger a = new BigInteger("1000000000000000000000000");
BigInteger b = BigInteger.valueOf(8);
~~~

Both values above represent exact integers, free from binary rounding errors like `double`.

## 3. Integer Division Rule: `a = q × b + r`

For two integers `a` and `b`, where `b != 0`, Java defines quotient and remainder satisfying:

\[
a = q \times b + r
\]

In `BigInteger`:

\[
q = a.\operatorname{divide}(b),\qquad
r = a.\operatorname{remainder}(b)
\]

Beyond that key identity, `BigInteger` division has these properties:

1. **Quotient `q` is truncated toward 0** (*truncation toward zero*), not always rounded down by `floor`.
2. **`|r| < |b|`**: the magnitude of the remainder is always strictly less than the magnitude of the divisor when `b` is nonzero.
3. If `r != 0`, the sign of `r` is the same as the sign of `a` (the dividend).
4. If `a` is divisible by `b`, then `r = 0`.

Example `17 / 5`:

\[
17 = 3\times5 + 2.
\]

In Java:

~~~java
BigInteger a = BigInteger.valueOf(17);
BigInteger b = BigInteger.valueOf(5);

BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // 3
System.out.println(qr[1]); // 2
~~~

An integer division can have a **quotient of 0** while the remainder is still nonzero: `3 / 5` has quotient 0, remainder 3. Therefore, never use `q.equals(BigInteger.ZERO)` to conclude divisibility.

## 4. How to Use `BigInteger.divideAndRemainder`

Method signature:

~~~java
public BigInteger[] divideAndRemainder(BigInteger val)
~~~

This is an instance method on `BigInteger`. It returns a **two-element array** in fixed order:

| Index | Meaning | Equivalent |
| --- | --- | --- |
| `result[0]` | Integer quotient | `a.divide(b)` |
| `result[1]` | Integer remainder | `a.remainder(b)` |

Example:

~~~java
BigInteger amount = new BigInteger("12345");
BigInteger groupSize = BigInteger.valueOf(100);

BigInteger[] qr = amount.divideAndRemainder(groupSize);

BigInteger fullGroups = qr[0];
BigInteger leftover = qr[1];

System.out.println(fullGroups); // 123
System.out.println(leftover);   // 45
~~~

You can also verify the division:

~~~java
BigInteger reconstructed = fullGroups.multiply(groupSize)
        .add(leftover);

System.out.println(reconstructed.equals(amount)); // true
~~~

**Why use `divideAndRemainder`?** When needing **both quotient and remainder**, the method expresses intent directly and the API allows computing both results together. If only the quotient or only the remainder is needed, `divide` and `remainder` usually express intent more clearly. Do not claim `divideAndRemainder` is always faster across all JVMs/inputs without appropriate benchmarking.

## 5. Checking Divisibility by Zero Remainder

An integer `a` is divisible by a nonzero integer `b` if and only if:

\[
a\bmod b=0
\]

In Java code, this should be executed as `a.remainder(b).signum() == 0` or `BigInteger.ZERO.equals(a.remainder(b))`. This check loses no precision, even for numbers with hundreds or thousands of digits.

~~~java
BigInteger value = new BigInteger("1000000000000000000000000");
BigInteger divisor = BigInteger.valueOf(8);

boolean divisible = value.remainder(divisor).signum() == 0;
System.out.println(divisible); // true
~~~

With `divideAndRemainder` results:

~~~java
BigInteger[] qr = value.divideAndRemainder(divisor);
boolean divisible = qr[1].equals(BigInteger.ZERO);

System.out.println(divisible); // true
~~~

**Do not use the `%` operator with `BigInteger`:** these are objects, not primitives. `a % b` is invalid syntax when `a` and `b` are `BigInteger`. Instead, call `a.remainder(b)`.

**Do not use `==` to check if the remainder equals `BigInteger.ZERO`:** `==` compares references, not numeric values. `equals` or `signum() == 0` serves the right purpose.

### Safe Divisibility Check Function

~~~java
static boolean isDivisible(BigInteger dividend, BigInteger divisor) {
    if (dividend == null || divisor == null) {
        throw new IllegalArgumentException("Arguments must not be null");
    }
    if (divisor.signum() == 0) {
        throw new IllegalArgumentException("Divisor must be nonzero");
    }
    return dividend.remainder(divisor).signum() == 0;
}
~~~

This is a **class-level method**; to run standalone, place it inside a Java class and call it from `main`. The function intentionally throws an error on `null` input or division by 0, rather than conflating invalid data with "not divisible."

## 6. Divisibility Does Not Depend on the Divisor's Sign

For integers, the sign of the divisor does not change divisibility:

- 20 is divisible by 5.
- 20 is divisible by −5.
- −20 is divisible by 5.
- −20 is divisible by −5.

~~~java
BigInteger twenty = BigInteger.valueOf(20);
BigInteger minusFive = BigInteger.valueOf(-5);

BigInteger[] qr = twenty.divideAndRemainder(minusFive);

System.out.println(qr[0]);                       // -4
System.out.println(qr[1]);                       // 0
System.out.println(qr[1].signum() == 0);          // true
~~~

With divisor `-5`, the quotient is `-4`, the remainder is 0, and the identity `20 = (-4) × (-5) + 0` still holds.

To compare remainders of divisions with different signs, you need a clear grasp of `remainder` behavior. A nonzero remainder can be negative; **the divisibility condition is still just remainder equal to 0**, regardless of the signs of the quotient or divisor.

## 7. Dividing Negative Numbers: Quotient Toward 0, Remainder Follows Dividend

The table below uses `divideAndRemainder` with small numbers to clearly show the sign rules:

| `a` | `b` | Quotient `q` | Remainder `r` | Verification |
| ---: | ---: | ---: | ---: | --- |
| 17 | 5 | 3 | 2 | `17 = 3 × 5 + 2` |
| −17 | 5 | −3 | −2 | `−17 = −3 × 5 − 2` |
| 17 | −5 | −3 | 2 | `17 = −3 × (−5) + 2` |
| −17 | −5 | 3 | −2 | `−17 = 3 × (−5) − 2` |
| 15 | −5 | −3 | 0 | `15 = −3 × (−5)` |
| 3 | 5 | 0 | 3 | `3 = 0 × 5 + 3` |

Runnable snippet:

~~~java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);

BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // -3
System.out.println(qr[1]); // -2
~~~

Note that `floor(-17 / 5)` over real numbers is −4, whereas `BigInteger` integer division returns −3 because it **truncates toward 0**. Do not replace `BigInteger` division with a floor formula if the problem requires Java's exact contract.

**A negative remainder is not an error:** it is the valid result of `remainder` with a negative dividend. If the problem requires a non-negative remainder (for example, circular indices or modular arithmetic), consider `mod` with a positive modulus; see the next section.

## 8. Distinguishing `remainder` and `mod`

`BigInteger` provides two similar-looking methods:

- `a.remainder(b)`: remainder operation paired with **quotient truncated toward 0**. The divisor `b` can be negative as long as it is nonzero. A nonzero remainder carries the sign of **`a`**.
- `a.mod(m)`: returns a **non-negative remainder** with a **strictly positive modulus** (`m > 0`). If `m <= 0`, Java throws `ArithmeticException`.

| Expression | Result |
| --- | ---: |
| `BigInteger.valueOf(17).remainder(BigInteger.valueOf(5))` | 2 |
| `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(5))` | −2 |
| `BigInteger.valueOf(-17).mod(BigInteger.valueOf(5))` | 3 |
| `BigInteger.valueOf(17).remainder(BigInteger.valueOf(-5))` | 2 |
| `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(-5))` | −2 |
| `BigInteger.valueOf(17).mod(BigInteger.valueOf(-5))` | **ArithmeticException** |

~~~java
BigInteger n = BigInteger.valueOf(-17);
BigInteger five = BigInteger.valueOf(5);

System.out.println(n.remainder(five)); // -2
System.out.println(n.mod(five));       // 3
~~~

The two results `−2` and `3` are equivalent **modulo 5**, yet not equal as integers. Since `-17 = -4 × 5 + 3`, the result of `mod(5)` is the non-negative representative 3.

### When to Use Which Method?

- **Checking divisibility:** `remainder(divisor).signum() == 0` is the simplest way, even when the divisor is negative. `mod` also checks divisibility for positive divisors, but rejects negative divisors.
- **Wanting both quotient and remainder:** `divideAndRemainder` returns the pair following truncation-toward-0 rules.
- **Circular indices, congruence classes, modular arithmetic algorithms:** use `mod(m)` when `m > 0` is assured to obtain results in `[0, m)`.
- **Needing floor-style quotient with positive divisor:** `divideAndRemainder` does not directly share the same rule when the dividend is negative; you must compute according to separate mathematical requirements.

Do not use `remainder` and `mod` interchangeably just because positive examples give the same result.

## 9. Division by 0: A Mandatory Error to Handle

Division by 0 is undefined. With `BigInteger`, the following calls throw `ArithmeticException`:

~~~java
BigInteger ten = BigInteger.TEN;
BigInteger zero = BigInteger.ZERO;

// ten.divide(zero);             // ArithmeticException
// ten.remainder(zero);          // ArithmeticException
// ten.divideAndRemainder(zero); // ArithmeticException
// ten.mod(zero);                // ArithmeticException (modulus must be positive)
~~~

If input data streams may contain `"0"` for the divisor, validate early to produce contextual error messages rather than letting the arithmetic exception surface deep inside processing:

~~~java
static BigInteger[] divideNonZero(BigInteger a, BigInteger b) {
    if (a == null || b == null) {
        throw new IllegalArgumentException("Missing operands");
    }
    if (b.signum() == 0) {
        throw new IllegalArgumentException("Division by zero");
    }
    return a.divideAndRemainder(b);
}
~~~

This is an illustrative class-level method. **Do not** return a quotient/remainder pair `[0, 0]` when the divisor is 0; doing so fabricates results and hides business errors.

By contrast, a dividend of 0 is valid if the divisor is nonzero: `0 / 7` has quotient 0 and remainder 0. Thus `0` is divisible by **every nonzero integer**, while `0 / 0` is disallowed.

## 10. Complete Java 17+ Program

Save to file `BigIntegerDivisionDemo.java`:

~~~java
import java.math.BigInteger;

public class BigIntegerDivisionDemo {
    static boolean isDivisible(BigInteger a, BigInteger b) {
        if (a == null || b == null || b.signum() == 0) {
            throw new IllegalArgumentException("Invalid operands");
        }
        return a.remainder(b).signum() == 0;
    }

    static void showDivision(long a, long b) {
        BigInteger left = BigInteger.valueOf(a);
        BigInteger right = BigInteger.valueOf(b);
        BigInteger[] qr = left.divideAndRemainder(right);

        System.out.println(a + "/" + b +
                " => q=" + qr[0] + ", r=" + qr[1] +
                ", divisible=" + qr[1].equals(BigInteger.ZERO));
    }

    public static void main(String[] args) {
        showDivision(17, 5);
        showDivision(-17, 5);
        showDivision(17, -5);
        showDivision(-17, -5);
        showDivision(15, -5);
        showDivision(0, 7);

        BigInteger huge = new BigInteger("1000000000000000000000000");
        BigInteger eight = BigInteger.valueOf(8);
        BigInteger[] parts = huge.divideAndRemainder(eight);

        System.out.println("huge quotient=" + parts[0]);
        System.out.println("huge remainder=" + parts[1]);
        System.out.println("huge divisible=" + isDivisible(huge, eight));

        BigInteger negative = BigInteger.valueOf(-17);
        BigInteger five = BigInteger.valueOf(5);
        System.out.println("remainder=" + negative.remainder(five));
        System.out.println("mod=" + negative.mod(five));

        BigInteger reconstructed = parts[0].multiply(eight).add(parts[1]);
        System.out.println("reconstructed=" + reconstructed.equals(huge));

        try {
            huge.divideAndRemainder(BigInteger.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("divide by zero: ArithmeticException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 BigIntegerDivisionDemo.java
java BigIntegerDivisionDemo
~~~

Stdout output:

~~~text
17/5 => q=3, r=2, divisible=false
-17/5 => q=-3, r=-2, divisible=false
17/-5 => q=-3, r=2, divisible=false
-17/-5 => q=3, r=-2, divisible=false
15/-5 => q=-3, r=0, divisible=true
0/7 => q=0, r=0, divisible=true
huge quotient=125000000000000000000000
huge remainder=0
huge divisible=true
remainder=-2
mod=3
reconstructed=true
divide by zero: ArithmeticException
~~~

Explanation:

1. The four cases of `±17 / ±5` have quotients truncated toward 0 and remainders matching the sign of the dividend.
2. `15 / -5` has remainder 0 so it is divisible, even though the divisor is negative.
3. `0 / 7` is also divisible, whereas division by 0 is invalid.
4. `10²⁴ / 8` has exact integer quotient `125000000000000000000000`. The number exceeds `long` range yet `BigInteger` still handles it.
5. `-17.remainder(5)` under method semantics gives `-2`; `-17.mod(5)` gives non-negative `3`.
6. `q.multiply(b).add(r).equals(a)` verifies the quotient–remainder identity.
7. Dividing by `BigInteger.ZERO` throws `ArithmeticException`, which is caught and handled in the example.

## 11. Validating String Data Before Performing Division

In APIs and data files, numbers are often received as strings. `new BigInteger(text)` parses valid decimal integers; if invalid, it throws `NumberFormatException`. A basic function:

~~~java
static BigInteger parseRequiredInteger(String text, String fieldName) {
    if (text == null || text.isEmpty()) {
        throw new IllegalArgumentException(fieldName + " is required");
    }
    try {
        return new BigInteger(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                fieldName + " must be a decimal integer", ex);
    }
}
~~~

This is an illustrative method placed inside a class. This implementation accepts integers matching `BigInteger(String)` syntax, not floating-point numbers or grouping separators such as `"1,000"`.

Depending on the contract, the application may:

- Allow `-` or `+` signs on integers.
- Specify whitespace trimming via an explicit normalization step.
- Use `new BigInteger(text, radix)` for binary, hex, or other valid radix representations.
- Limit input character count to protect resources, as very large `BigInteger`s carry CPU/memory cost.
- Check for a nonzero divisor and business bounds before computing.

Do not use `Double.parseDouble` to read a large integer and then cast/round; `double` may already have lost integer digits. The original decimal string should be parsed directly into `BigInteger`.

## 12. `BigInteger.ZERO`, `equals`, and `signum`

Three common ways to check for a zero remainder:

~~~java
BigInteger remainder = BigInteger.valueOf(25)
        .remainder(BigInteger.valueOf(5));

boolean a = remainder.equals(BigInteger.ZERO);
boolean b = BigInteger.ZERO.equals(remainder);
boolean c = remainder.signum() == 0;

System.out.println(a && b && c); // true
~~~

All are correct when `remainder` is a non-null `BigInteger`. In a successful `divideAndRemainder` call, neither array element is null. For an external source that might be null, `BigInteger.ZERO.equals(value)` is a null-safe check; `value.signum()` needs a null guard.

**Common mistake:**

~~~java
// Wrong intent: == compares BigInteger object identity
// if (remainder == BigInteger.ZERO) { ... }
~~~

A result coincidentally sharing a reference with `BigInteger.ZERO` is not a contract for checking whether two numbers have the same value. Use `equals` or `signum`.

### Why Is `signum` Useful?

`signum()` returns:

- `-1` when the number is negative;
- `0` when the number equals 0;
- `1` when the number is positive.

It checks the sign on very large integers without converting to `int` or `long`. A zero remainder has `signum()==0` regardless of the signs of the original dividend/divisor.

## 13. Comparing `divideAndRemainder`, `divide`, and `remainder` Usage

All three APIs perform integer division, but express different intents.

~~~java
BigInteger a = new BigInteger("12345");
BigInteger b = BigInteger.valueOf(100);

// Need both:
BigInteger[] qr = a.divideAndRemainder(b);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];

// Need quotient only:
BigInteger qOnly = a.divide(b);

// Need remainder only:
BigInteger rOnly = a.remainder(b);
~~~

| Need | API to consider |
| --- | --- |
| Splitting into full groups and leftover | `divideAndRemainder` |
| Obtaining integer quotient | `divide` |
| Checking divisibility | `remainder` then check zero |
| Obtaining non-negative remainder with positive modulus | `mod` |
| Checking congruence in a modulo m > 0 model | `mod` or `subtract` + `mod` |

**When needing both quotient and remainder, call `divideAndRemainder` once** to keep code concise and show intent. When only checking divisibility, taking `remainder` alone suffices; no need to compute or hold the quotient.

Do not convert `BigInteger` to `long` just to use primitive `%`. If the value exceeds the `long` range, `longValue()` can truncate high bits and return wrong results. When conversion is mandatory, consider `longValueExact()` to detect out-of-range values via `ArithmeticException`.

## 14. Splitting into Batches or Groups

Suppose we have `items` objects and each box holds at most `capacity` items. We need to know the number of **full** boxes and **leftover** items:

~~~java
BigInteger items = new BigInteger("12345");
BigInteger capacity = BigInteger.valueOf(100);
BigInteger[] qr = items.divideAndRemainder(capacity);

BigInteger fullBoxes = qr[0];
BigInteger leftoverItems = qr[1];

System.out.println(fullBoxes);    // 123
System.out.println(leftoverItems); // 45
~~~

If the **total** number of boxes is needed, including a partially filled last box, and values are **non-negative** with `capacity > 0`:

~~~java
BigInteger boxesNeeded = qr[1].signum() == 0
        ? qr[0]
        : qr[0].add(BigInteger.ONE);

System.out.println(boxesNeeded); // 124
~~~

This pattern corresponds to **ceil** division for `items >= 0` and `capacity > 0`. Do not apply it verbatim to negative numbers, where `BigInteger` quotients truncate toward 0 and the "box" concept no longer fits. Business range checks should happen before computing.

## 15. Applying to Cycles, Pagination, and Batch Systems

Another common scenario is splitting a total workload into fixed-size batches.

Example:

~~~java
BigInteger records = new BigInteger("1001");
BigInteger batchSize = BigInteger.valueOf(100);

BigInteger[] qr = records.divideAndRemainder(batchSize);
System.out.println("full batches=" + qr[0]); // full batches=10
System.out.println("remainder=" + qr[1]);    // remainder=1
~~~

If the question is "can it be divided evenly into equal-sized batches?", all you need is:

~~~java
boolean evenBatches = qr[1].signum() == 0;
System.out.println(evenBatches); // false
~~~

When doing pagination or 0-based indexing, pay attention to explicit index requirements (whether negative is possible, whether page size is positive). A negative `remainder` on negative indices can cause array access to fail. For **non-negative circular indices**, `mod` with a positive modulus is the better fit.

## 16. Checking Divisibility by a Specific Number

### Even or Odd

Check evenness via remainder by 2:

~~~java
BigInteger huge = new BigInteger("1000000000000000000000000");
boolean even = huge.remainder(BigInteger.TWO).signum() == 0;

System.out.println(even); // true
~~~

`BigInteger.TWO` is available in Java 17. With bitwise operations, `!huge.testBit(0)` also checks whether the lowest bit is 0, but using `remainder(BigInteger.TWO)` exposes divisibility intent clearly for beginners.

### Divisibility by a Product or Multiple

Suppose you want to check if `n` is divisible by `12`:

~~~java
BigInteger n = new BigInteger("123456");
BigInteger twelve = BigInteger.valueOf(12);

System.out.println(n.remainder(twelve).signum() == 0); // true
~~~

Do not replace a single division by 12 with multiple remainder conditions without a clear reason: a direct check using `remainder(12)` is complete and exact. Mathematical rules like "divisible by 3 and 4 means divisible by 12" rely on coprime multiple properties; prove them before optimizing with them.

### Dividend Equal to 0

~~~java
System.out.println(BigInteger.ZERO.remainder(BigInteger.TEN)); // 0
~~~

Zero is divisible by every nonzero number. However, **you cannot divide by 0**. This rule must be separated in validation, especially when users enter a "divisor" into a form.

## 17. Limits and Pitfalls to Watch For

| Case | What to know |
| --- | --- |
| `a.divideAndRemainder(BigInteger.ZERO)` | Throws `ArithmeticException` |
| `a.remainder(BigInteger.ZERO)` | Throws `ArithmeticException` |
| `a.mod(BigInteger.ZERO)` | Throws `ArithmeticException` because modulus is non-positive |
| `a.mod(negative)` | Throws `ArithmeticException`, even though `remainder(negative)` is valid |
| `a.divideAndRemainder(null)` | Null input is not a valid divisor; needs null guard |
| `result[0] == 0` | A zero quotient does not prove divisibility |
| `result[1].signum() == 0` | Correct divisibility condition for a nonzero divisor |
| `result[1] == BigInteger.ZERO` | Compares object identity, do not use as value check |
| `result[1].intValue()` | Can lose data for large remainders; unnecessary for checking zero |
| `BigInteger.valueOf(veryLargeLiteral)` | Literals/`long` have finite range; parse string directly |
| `BigDecimal.divide` | Decimal division with different scale/rounding rules; does not replace `BigInteger` integer division |
| `a.mod(m)` and `a.remainder(m)` | Differ when `a` is negative and `m` is positive |
| `a.divide(b)` vs `Math.floorDiv` | `BigInteger` truncates quotient toward 0; primitive floor division has different rules for negatives |

### `BigInteger` Is Immutable

Calls like `a.divide(b)`, `a.remainder(b)`, or `a.divideAndRemainder(b)` **do not modify `a` or `b`**. The returned array is a container whose elements you can reassign, but the `BigInteger` objects inside the array remain immutable.

Example:

~~~java
BigInteger a = BigInteger.valueOf(17);
BigInteger b = BigInteger.valueOf(5);
BigInteger[] qr = a.divideAndRemainder(b);

qr[0] = BigInteger.ZERO; // Reassigns array element, does not modify a or b.
System.out.println(a);   // 17
~~~

Do not assume that because the array is mutable, the source numbers themselves were modified.

## 18. Verifying Using Mathematical Properties

A good testing strategy is to verify **both** the quotient and remainder simultaneously against the definition. For `b != 0`:

\[
a = q b + r,\qquad |r|<|b|
\]

and if `r != 0`, `sign(r) = sign(a)`.

Example test method:

~~~java
static boolean validQuotientRemainder(
        BigInteger a, BigInteger b, BigInteger[] qr) {
    if (a == null || b == null || b.signum() == 0
            || qr == null || qr.length != 2
            || qr[0] == null || qr[1] == null) {
        return false;
    }

    BigInteger q = qr[0];
    BigInteger r = qr[1];

    boolean equation = q.multiply(b).add(r).equals(a);
    boolean bounded = r.abs().compareTo(b.abs()) < 0;
    boolean signCorrect = r.signum() == 0
            || r.signum() == a.signum();

    return equation && bounded && signCorrect;
}
~~~

This is an **illustrative class-level method**, which can be added to automated tests. These properties are stronger than checking just a few positive examples and help catch wrong assumptions when scaling algorithms.

You can test many input combinations:

- Both `a` and `b` positive.
- `a` negative, `b` positive.
- `a` positive, `b` negative.
- Both negative.
- `a` equal to 0, `b` nonzero.
- `|a| < |b|`, quotient equal to 0.
- `a` a multiple of `b`, remainder equal to 0.
- Numbers with hundreds of digits.
- `b` equal to 0: check exception, do not look for quotient/remainder.

## 19. Self-Check Questions

**Question 1.** What does `BigInteger.valueOf(17).divideAndRemainder(BigInteger.valueOf(5))` return?

**Answer:** The array `[3, 2]`, where quotient is 3 and remainder is 2. Since the remainder is nonzero, 17 is not divisible by 5.

**Question 2.** What quotient and remainder does `-17` divided by `5` produce in `BigInteger`?

**Answer:** Quotient `-3`, remainder `-2`; `−17 = (−3) × 5 + (−2)`. Do not use `floor(-17/5)` to infer the quotient.

**Question 3.** Is checking divisibility with `qr[0].equals(BigInteger.ZERO)` correct?

**Answer:** No. That checks if the quotient is 0. Divisibility holds when **`qr[1].signum() == 0`**, with a nonzero divisor.

**Question 4.** Why does `BigInteger.valueOf(-17).remainder(BigInteger.valueOf(5))` equal `-2`, while `mod(BigInteger.valueOf(5))` equals `3`?

**Answer:** `remainder` follows the rule of quotient truncated toward 0 and remainder carrying the dividend's sign; `mod` normalizes the result into `[0, m)` when `m > 0`.

**Question 5.** Is `BigInteger.ZERO` divisible by `BigInteger.valueOf(7)`?

**Answer:** Yes, because `0 = 0 × 7 + 0`. However, `0 / 0` division is undefined.

**Question 6.** When needing both the number of full boxes **and** the number of leftover items, which method should be used?

**Answer:** `divideAndRemainder`; element `[0]` is the quotient/full boxes, `[1]` is the leftover. Validate non-negative quantity and positive capacity before applying the box formula.

**Question 7.** If only checking divisibility for a very large number, should you use `longValue()` to take `%`?

**Answer:** No. Narrowing a `BigInteger` outside the `long` range can drop high-order bits. Use `remainder` directly to guarantee accuracy.

**Question 8.** Why does `BigInteger.mod` disallow a negative modulus?

**Answer:** The contract of `mod` requires a **positive** modulus, so that the remainder is non-negative in `[0, m)`. To get the integer-division remainder with a negative divisor, use `remainder`.

## 20. Summary and References

- **`divideAndRemainder(divisor)`** returns the pair `[quotient, remainder]`; both are exact on `BigInteger`.
- For a nonzero divisor: `a = q.multiply(b).add(r)`, `|r| < |b|`; quotient is **truncated toward 0**, remainder takes the dividend's sign if nonzero.
- **Divisibility check:** `a.remainder(b).signum() == 0`, after verifying `b != 0`.
- Use **`equals` or `signum`**, never `==`, for `BigInteger` value checks.
- **`remainder` differs from `mod`** when the dividend is negative; `mod` requires a positive modulus.
- **Division by 0 throws `ArithmeticException`**; never turn the error into a fake result.
- For numbers beyond the `long` range, create `BigInteger` from strings and avoid converting to primitives just for arithmetic.

Official documentation:

- [BigInteger — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): `divideAndRemainder`, `divide`, `remainder`, `mod`, `ZERO`, `signum`, and exception rules.
- [Java Language Specification 17 — Integer Division](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2): reference for the integer quotient truncation-toward-zero rule.
- [Java Language Specification 17 — Remainder Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): quotient/remainder relationship in primitive operators to understand remainder sign.