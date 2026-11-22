# `divideToIntegralValue`, `remainder`, and `divideAndRemainder` in `BigDecimal`

> **Java core – numbers · BigDecimal Operations**  
> **Goal:** Understand the differences between division returning the **integral part of the quotient**, division returning the **remainder**, and the API returning **both**; read signs, scale, precision, and exceptions accurately; distinguish `remainder` from Euclidean modulo; know when to pass a `MathContext`; and write Java 17+ code to verify results accurately.

## 1. When Decimal Division Does Not Need a Fractional Quotient

A common scenario: dividing an exact amount of money, weight, or quantity into groups, and needing to know **how many whole groups** there are and **how much is left over**.

For example, having `17.5` units where each group requires `3` units:

\[
17.5 = 5 \times 3 + 2.5
\]

We need the integral quotient 5 and remainder 2.5; we do not necessarily need to compute the infinitely repeating decimal quotient `17.5/3 = 5.83333...`.

`BigDecimal` provides three methods for that need:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("17.5");
BigDecimal unit = new BigDecimal("3");

BigDecimal quotient = amount.divideToIntegralValue(unit);
BigDecimal remainder = amount.remainder(unit);
BigDecimal[] both = amount.divideAndRemainder(unit);

System.out.println(quotient);  // 5.0
System.out.println(remainder); // 2.5
System.out.println(both[0]);   // 5.0
System.out.println(both[1]);   // 2.5
```

**Why does it print `5.0` instead of `5`?** `BigDecimal` has a **scale** property. A result with an integer numeric value can still be represented as a BigDecimal with positive scale. `5.0` still has numeric value 5; how representation works will be analyzed in the scale section.

### Core API Table

| Method | Return type | Meaning |
| --- | --- | --- |
| `a.divideToIntegralValue(b)` | `BigDecimal` | Integral part of the quotient, truncating the fractional part toward 0 |
| `a.remainder(b)` | `BigDecimal` | `a - q×b` where q is the integral quotient above |
| `a.divideAndRemainder(b)` | `BigDecimal[]` | Two-element array: `[0]` is q, `[1]` is r |
| `a.divideToIntegralValue(b, mc)` | `BigDecimal` | Integral quotient, constrained in representability by `MathContext` |
| `a.remainder(b, mc)` | `BigDecimal` | Remainder using the integral quotient computed with `mc` |
| `a.divideAndRemainder(b, mc)` | `BigDecimal[]` | Pair of integral quotient and remainder with `mc` |

All six methods exist in Java 17 in `java.math.BigDecimal`. They are not static methods: they are invoked on the **dividend**.

## 2. Exact Definition of the Integral Quotient

Given dividend `a` and divisor `b != 0`. The integral part of the quotient is computed by **truncating the fractional part of the true quotient toward zero** (*truncate toward zero*).

Notation:

\[
q = \operatorname{trunc}(a/b)
\]
\[
r = a - q\times b
\]

The identity must always hold in terms of arithmetic value:

\[
a = q\times b + r
\]

In particular, q is not necessarily the result of the **floor** function (rounding down toward −∞). The difference becomes clear with negative numbers:

```text
 a       b      a/b (approx.)   q = trunc(a/b)    r
-------------------------------------------------------
 17.5    3       5.8333...          5         2.5
-17.5    3      -5.8333...         -5        -2.5
 17.5   -3      -5.8333...         -5         2.5
-17.5   -3       5.8333...          5        -2.5
```

With `a=-17.5` and `b=3`, using `floor(-5.8333...)` gives q=−6; however, `divideToIntegralValue` returns value q=−5. They are two different rules.

**Do not call this quotient “rounding down” when negative numbers may appear.** Use “truncating the fractional part toward 0” or “integral quotient by truncation”.

### The Integral Quotient Still Has Type BigDecimal

`divideToIntegralValue` returns **`BigDecimal`**, not `BigInteger`, `int`, or `long`:

```java
BigDecimal q = new BigDecimal("17.5")
        .divideToIntegralValue(new BigDecimal("3"));

// May be 5.0, yet still represents an integer.
System.out.println(q.toBigIntegerExact()); // 5
```

If downstream APIs truly need an integer type, `toBigIntegerExact()` can convert the integer value to BigInteger without discarding any fractional part. To convert to int or long without losing value, consider `intValueExact()` / `longValueExact()`; they report an error if the result does not fit the target type's range.

## 3. What Is `remainder`? Not “Always Non-Negative Modulo”

With `a=17.5`, `b=3`:

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");

BigDecimal q = a.divideToIntegralValue(b);
BigDecimal r = a.remainder(b);

System.out.println(q); // 5.0
System.out.println(r); // 2.5
```

The identity `a = q×b + r` holds in exact BigDecimal numeric value:

```java
BigDecimal reconstructed = q.multiply(b).add(r);
System.out.println(reconstructed.compareTo(a) == 0); // true
```

With negative numbers:

```java
BigDecimal negative = new BigDecimal("-17.5");
System.out.println(negative.divideToIntegralValue(b)); // -5.0
System.out.println(negative.remainder(b));             // -2.5
```

**BigDecimal's remainder can be negative.** It takes the sign of the dividend `a` when the remainder is nonzero, because q is truncated toward 0. That follows the same spirit as Java's integer `%` operator, **not** Euclidean modulo which always lies in `[0,m)` for a positive modulus.

Properties when `b != 0` and values are finite:

- `a = q×b+r`;
- `|r| < |b|` when r is nonzero, and the condition also holds for r=0;
- nonzero r carries the sign of a;
- flipping the sign of b can flip the sign of q, but **does not flip the sign of r** if a stays the same;
- the integral quotient q is truncated toward 0, independent of usual decimal division rounding modes.

### Distinguishing `remainder` from Euclidean Modulo

Suppose you need a **non-negative** remainder from a positive modulus 3:

```java
BigDecimal a = new BigDecimal("-17.5");
BigDecimal m = new BigDecimal("3");

BigDecimal raw = a.remainder(m); // -2.5
BigDecimal euclidean = raw.signum() < 0
        ? raw.add(m) : raw;       // 0.5
```

`0.5` is the Euclidean remainder in `[0,3)`, whereas `-2.5` is BigDecimal's remainder. If you want Euclidean modulo for BigDecimal, define a **positive modulus** and normalize the remainder as above.

BigInteger has `mod(modulus)` requiring a positive modulus; **BigDecimal has no equivalent `mod(BigDecimal)`**. Do not name `remainder` a non-negative modulo and build an algorithm on that false assumption.

## 4. `divideAndRemainder`: One Call, Two Results

When a program needs **both the integral quotient and the remainder**, write:

```java
BigDecimal[] result = amount.divideAndRemainder(unit);
BigDecimal quotient = result[0];
BigDecimal remainder = result[1];
```

The array has **exactly two elements** in order:

1. `result[0]`: the integral quotient `divideToIntegralValue`.
2. `result[1]`: the remainder `remainder`.

Do not swap the two elements or interpret `result[0]` as a fractional decimal quotient.

```java
BigDecimal amount = new BigDecimal("17.5");
BigDecimal unit = new BigDecimal("3");

BigDecimal[] qr = amount.divideAndRemainder(unit);

System.out.println("q = " + qr[0]); // q = 5.0
System.out.println("r = " + qr[1]); // r = 2.5
```

According to the Javadoc, when both quotient and remainder are needed, this method **may be faster** than calling the two operations separately because the quotient computation can be reused. Do not infer that a single call always has fixed speed or is always faster in every workload; actual optimization requires benchmarking.

### Immutability of BigDecimal

Division and remainder operations **do not mutate** either operand:

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");
BigDecimal[] qr = a.divideAndRemainder(b);

System.out.println(a); // 17.5
System.out.println(b); // 3
```

`BigDecimal` is immutable; reassigning a variable or storing a new value does not alter the old object. The `BigDecimal[]` array returned by the method is a container holding two references; you can replace elements of the array without changing the BigDecimal values inside.

## 5. How Does It Differ from `divide` and Ordinary Decimal Division?

This is a very important distinction:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// No terminating decimal quotient:
// BigDecimal bad = one.divide(three); // ArithmeticException

BigDecimal integerPart = one.divideToIntegralValue(three);
BigDecimal rest = one.remainder(three);
BigDecimal[] both = one.divideAndRemainder(three);

System.out.println(integerPart); // 0
System.out.println(rest);        // 1
System.out.println(both[0]);     // 0
System.out.println(both[1]);     // 1
```

`1/3` has an infinitely repeating decimal part, so `BigDecimal.divide(BigDecimal)` **without a rounding mode/context** cannot produce an exact terminating decimal quotient and throws `ArithmeticException`.

However, **the integral quotient of 1/3 is simply 0, and the remainder is 1**. Those two values are represented exactly; `divideToIntegralValue` and `remainder` do not need to compute every digit of the decimal quotient.

When you want a quotient with a fractional part according to a rounding rule, use a **different** division API:

```java
import java.math.RoundingMode;

BigDecimal rounded = one.divide(
        three, 2, RoundingMode.HALF_UP);
System.out.println(rounded); // 0.33
```

Yet `0.33` is **not** the integral quotient q=0 and must not replace q in the default remainder formula. If you use `0.33` as the quotient to compute `1 - 0.33×3`, what remains is 0.01 — different from the defined r=1.

| Operation | `1/3` | Meaning |
| --- | --- | --- |
| `one.divide(three)` | Throws `ArithmeticException` | Demands an exact terminating decimal quotient |
| `one.divide(three, 2, HALF_UP)` | 0.33 | Rounded decimal quotient |
| `one.divideToIntegralValue(three)` | 0 | Integral part of the quotient |
| `one.remainder(three)` | 1 | Remainder according to q=0 |
| `one.divideAndRemainder(three)` | [0, 1] | Returns both |

**Takeaway:** Do not choose `divideToIntegralValue` just to “avoid an exception” if business requirements actually call for a decimal quotient. It intentionally **discards the fractional part of the quotient**.

## 6. Signs of Quotient and Remainder: Checking All 4 Cases

Try all four sign combinations:

```java
BigDecimal positive = new BigDecimal("17.5");
BigDecimal negative = new BigDecimal("-17.5");
BigDecimal three = new BigDecimal("3");
BigDecimal minusThree = new BigDecimal("-3");

System.out.println(java.util.Arrays.toString(
        positive.divideAndRemainder(three)));
// [5.0, 2.5]

System.out.println(java.util.Arrays.toString(
        negative.divideAndRemainder(three)));
// [-5.0, -2.5]

System.out.println(java.util.Arrays.toString(
        positive.divideAndRemainder(minusThree)));
// [-5.0, 2.5]

System.out.println(java.util.Arrays.toString(
        negative.divideAndRemainder(minusThree)));
// [5.0, -2.5]
```

Notes:

- q is negative when a and b have opposite signs; q is positive when they have the same sign and |a|≥|b|.
- r is 2.5 if a=17.5; r is −2.5 if a=−17.5.
- When a has magnitude smaller than |b|, q=0 numerically and r=a.
- Do not use `Math.floor` or downward rounding to compute negative q manually; that would be a different operation.

In accounting or measurement systems, test negative numbers whenever adjustments or refunds can occur. Testing only a>0, b>0 often misses sign errors.

## 7. Scale: q Is an Integer in Value, Yet May Print `5.0` or `2.00`

Every `BigDecimal` is interpreted via **unscaled value** and **scale**:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}.
\]

`new BigDecimal("17.5")` has scale 1; `new BigDecimal("3")` has scale 0. The preferred scale of `divideToIntegralValue`'s result is the difference between the dividend's scale and the divisor's scale; in this example, it is 1:

```java
BigDecimal q = new BigDecimal("17.5")
        .divideToIntegralValue(new BigDecimal("3"));

System.out.println(q);         // 5.0
System.out.println(q.scale()); // 1
```

The quotient **mathematically is the integer 5**. Yet `BigDecimal` may retain scale 1 and print `5.0` to match the operation's preferred representation.

Example with two fractional digits:

```java
BigDecimal a = new BigDecimal("10.00");
BigDecimal b = new BigDecimal("4");

BigDecimal[] qr = a.divideAndRemainder(b);
System.out.println(java.util.Arrays.toString(qr));
// [2.00, 2.00]

System.out.println(qr[0].scale()); // 2
System.out.println(qr[1].scale()); // 2
```

Here both results have scale 2, whereas if we write the input data as `"10"` instead of `"10.00"`, the printed form of quotient and remainder can differ.

**Do not promise that every integral quotient always has scale 0, or that scale always equals the exact scale difference.** Preferred scale is a formatting/representation rule; in certain divisions or when `MathContext` constrains precision, the API may have to use a different scale to represent the integral quotient accurately.

### `equals` Differs from `compareTo`

`BigDecimal.equals` compares both value **and scale**. `compareTo` compares numeric value ordering:

```java
BigDecimal x = new BigDecimal("2.00");
BigDecimal y = new BigDecimal("2");

System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y)==0); // true
```

To verify the identity `a=q×b+r` by **numeric value**, use `compareTo(...)==0`. If the contract also requires matching representation (scale), check `scale()` as well or use `equals` when intentional.

Do not automatically call `stripTrailingZeros()` on every result in financial applications: it can change scale and how data is printed, sometimes into scientific notation. Distinguish **exact arithmetic** from **presentation rules**.

## 8. What Is `MathContext` and How Does It Relate to Integral Quotient Division?

`MathContext` configures **precision** (number of significant digits) and a `RoundingMode`:

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(
        4, RoundingMode.HALF_UP);
```

The overloads:

```java
BigDecimal q = a.divideToIntegralValue(b, mc);
BigDecimal r = a.remainder(b, mc);
BigDecimal[] pair = a.divideAndRemainder(b, mc);
```

For these three methods, think of `mc` primarily as a **representational limit on the integral quotient**. Do not assume `RoundingMode.HALF_UP` will round `5.833...` to q=6. The integral part under **truncation toward 0** is still 5.

A subtlety from the Javadoc: the remainder computed via the integral quotient **is not rounded to `MathContext`'s precision**; therefore, the returned remainder value **can have more digits than `mc.getPrecision()`**.

### Example When the Integral Quotient Needs More Digits Than Precision

```java
BigDecimal a = new BigDecimal("12345");
BigDecimal b = new BigDecimal("2");
MathContext tooSmall = new MathContext(
        3, RoundingMode.DOWN);

try {
    a.divideToIntegralValue(b, tooSmall);
} catch (ArithmeticException ex) {
    System.out.println("precision insufficient");
}
```

Because the integral part of `12345 / 2` is `6172`, it needs 4 significant digits to be represented exactly. `MathContext(3,...)` cannot hold q accurately, so `divideToIntegralValue` throws `ArithmeticException` instead of “rounding q=6170” or “truncating further to q=617”.

```java
MathContext enough = new MathContext(
        4, RoundingMode.DOWN);

BigDecimal[] qr = a.divideAndRemainder(b, enough);
System.out.println(java.util.Arrays.toString(qr));
// [6172, 1]
```

**Essence:** for overloads with MathContext, it does not mean the API is allowed to return a wrong integral quotient just to fit precision. If the exact integral quotient cannot be represented within the chosen limit, it can throw an exception.

### RoundingMode Does Not Change the Definition of Remainder

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");

BigDecimal[] qr = a.divideAndRemainder(
        b, new MathContext(2, RoundingMode.HALF_UP));

// q is still 5 numerically, r is still 2.5.
```

The result is not an ordinary rounded decimal division. When you need to divide to get 5.83 or 5.833, use `divide(..., mc)` and understand the precision requirement of a **fractional quotient**.

## 9. `MathContext.UNLIMITED` and `precision = 0`

A `MathContext` with `precision == 0` denotes **unlimited precision** in the sense of MathContext. Convenience constant:

```java
MathContext unlimited = MathContext.UNLIMITED;
```

You can use:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
BigDecimal[] qr = one.divideAndRemainder(
        three, MathContext.UNLIMITED);

System.out.println(java.util.Arrays.toString(qr));
// [0, 1]
```

However, **do not assume** that `one.divide(three, MathContext.UNLIMITED)` will automatically generate infinitely many digits or choose rounding on its own. Decimal division without an exact finite decimal representation can still throw `ArithmeticException` because there is no way to return an exact finite result.

Unlimited precision here **does not mean infinite heap, CPU, or BigDecimal size**. BigDecimal is still bounded by resources and implementation limits.

## 10. `remainder` with `MathContext` Does Not Necessarily Fit Precision

The Javadoc states that remainder is not a rounding operation in the sense of “the result must have at most P digits”:

```java
BigDecimal r = a.remainder(b, mc);
```

This method in principle computes:

```text
q = a.divideToIntegralValue(b, mc)
r = a - q*b
```

After determining q under the context's conditions, the remainder is formed at exact value from the subtraction, rather than being forced down to `mc.getPrecision()` digits.

For instance, a subtraction with small scale or a remainder with many digits after the decimal point may require more significant digits than q. If you want to round r afterward, that is a **separate business decision**; you can use `r.round(mc)` and accept that the identity `a = q×b + r_rounded` may no longer hold strictly.

### Do Not Use Context to “Hide” Overflow

`BigDecimal` does not have 32/64-bit primitive overflow like `int`/`long`, but it can still throw `ArithmeticException` when exactness does not fit `MathContext`, when dividing by zero, or when hitting scale limits. You should not catch all errors and return `BigDecimal.ZERO`: an actual value of 0 and an invalid operation are two different situations.

## 11. Zero Divisor and Edge Cases

Every method in this group requires **divisor != 0**:

```java
BigDecimal ten = BigDecimal.TEN;

// ten.divideToIntegralValue(BigDecimal.ZERO); // ArithmeticException
// ten.remainder(BigDecimal.ZERO);             // ArithmeticException
// ten.divideAndRemainder(BigDecimal.ZERO);    // ArithmeticException
```

Check upfront if inputs might be invalid:

```java
static BigDecimal[] split(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) {
        throw new IllegalArgumentException(
                "divisor must not be zero");
    }
    return a.divideAndRemainder(b);
}
```

This snippet assumes a and b are non-null; if an API accepts arbitrary data, check for null before calling `signum()` and `divideAndRemainder()`.

### Dividend Equal to 0

```java
BigDecimal a = BigDecimal.ZERO;
BigDecimal b = new BigDecimal("7");
BigDecimal[] qr = a.divideAndRemainder(b);

System.out.println(qr[0].compareTo(BigDecimal.ZERO) == 0); // true
System.out.println(qr[1].compareTo(BigDecimal.ZERO) == 0); // true
```

The scale and printed form of 0 can depend on how operands were constructed; compare **numeric values** using `compareTo` when that is the goal.

### |a| < |b|

```java
BigDecimal a = new BigDecimal("2.5");
BigDecimal b = new BigDecimal("8");

BigDecimal q = a.divideToIntegralValue(b);
BigDecimal r = a.remainder(b);

System.out.println(q.compareTo(BigDecimal.ZERO)==0); // true
System.out.println(r.compareTo(a)==0);                // true
```

If the magnitude of the dividend is smaller than the magnitude of the divisor, the integral quotient has value 0 and the remainder equals the dividend in value. Do not confuse it with the decimal quotient `0.3125`.

## 12. Financial Arithmetic: Group Splitting vs. Equal Money Division

With `BigDecimal` in finance, you should not always pick `divideToIntegralValue`:

- If the goal is **number of whole groups** and **kept remainder**, this operation is right.
- If the goal is splitting money **evenly among multiple people**, you may need a rounding rule at the smallest currency unit.
- If the goal is computing taxes, interest rates, or percentages, you usually need a decimal quotient and a `RoundingMode` per contract.

Example dividing 10.00 units into batches of 4.00 units:

```java
BigDecimal available = new BigDecimal("10.00");
BigDecimal batchSize = new BigDecimal("4.00");

BigDecimal[] qr = available.divideAndRemainder(batchSize);
// Numeric value of integral quotient = 2, remainder = 2.00.
```

This counts the number of **full batches** and the leftover amount. It does not say “each batch gets 2.50 units”: that is the problem of splitting 10.00 evenly into four parts, which needs `divide` with the appropriate unit.

If you need to preserve an exact currency scale (e.g., always 2 digits), apply `setScale(2,...)` only after defining arithmetic semantics and rounding rules, rather than assuming the scale produced by `divideAndRemainder` always equals the business display scale.

## 13. Verifying Correctness with the Identity `a = q*b + r`

This is the most useful **invariant** when writing unit tests:

```java
static boolean invariantHolds(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) return false;

    BigDecimal[] qr = a.divideAndRemainder(b);
    BigDecimal rebuilt = qr[0].multiply(b).add(qr[1]);

    return rebuilt.compareTo(a) == 0;
}
```

Also check:

```java
BigDecimal[] qr = a.divideAndRemainder(b);

boolean smallRemainder =
        qr[1].abs().compareTo(b.abs()) < 0;

boolean signCompatible =
        qr[1].signum() == 0
        || qr[1].signum() == a.signum();
```

These three checks are especially helpful with negative numbers, negative divisors, and numbers with different scales. **Do not necessarily use `equals`** for the reconstructed identity, because the scale of the reconstructed value can differ from a's scale even when both numeric values are equal.

### Testing with a Property-Based Approach

You can generate many pairs `a,b` with varying scales (b≠0), including negative numbers and values like `0.00`/`1E+3`, and verify the invariants above.

When running overloads with `MathContext`, distinguish two cases:

- Operation returns a result → check the invariants.
- Operation throws `ArithmeticException` because precision does not permit the integral quotient → this can be **correct contract behavior**, not an invariant failure.

## 14. Complete Java 17+ Demo

Create file **`BigDecimalQuotientRemainderDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Arrays;

public class BigDecimalQuotientRemainderDemo {

    private static void show(String label,
            BigDecimal a, BigDecimal b) {
        BigDecimal[] qr = a.divideAndRemainder(b);
        BigDecimal rebuilt = qr[0].multiply(b).add(qr[1]);

        System.out.println(label + " -> q=" + qr[0]
                + ", r=" + qr[1]
                + ", identity=" + (rebuilt.compareTo(a) == 0));
    }

    private static BigDecimal euclideanMod(
            BigDecimal a, BigDecimal modulus) {
        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException(
                    "modulus must be positive");
        }
        BigDecimal r = a.remainder(modulus);
        return r.signum() < 0 ? r.add(modulus) : r;
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("17.5");
        BigDecimal b = new BigDecimal("3");

        show("positive", a, b);
        show("negative dividend", a.negate(), b);
        show("negative divisor", a, b.negate());
        show("both negative", a.negate(), b.negate());

        System.out.println("integral = "
                + a.divideToIntegralValue(b));
        System.out.println("remainder = " + a.remainder(b));
        System.out.println("euclidean mod(-17.5,3) = "
                + euclideanMod(a.negate(), b));

        BigDecimal[] scaled =
                new BigDecimal("10.00")
                .divideAndRemainder(new BigDecimal("4"));
        System.out.println("scaled = " + Arrays.toString(scaled));
        System.out.println("quotient scale = "
                + scaled[0].scale());
        System.out.println("2.00 equals 2 = "
                + new BigDecimal("2.00").equals(
                        new BigDecimal("2")));
        System.out.println("2.00 compareTo 2 = "
                + (new BigDecimal("2.00").compareTo(
                        new BigDecimal("2")) == 0));

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        System.out.println("1 / 3 qr = " +
                Arrays.toString(one.divideAndRemainder(three)));

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("exact 1 / 3 = rejected");
        }

        System.out.println("rounded 1 / 3 = " +
                one.divide(three, 2, RoundingMode.HALF_UP));

        BigDecimal numerator = new BigDecimal("12345");
        BigDecimal denominator = new BigDecimal("2");

        try {
            numerator.divideToIntegralValue(denominator,
                    new MathContext(3, RoundingMode.DOWN));
        } catch (ArithmeticException ex) {
            System.out.println("precision 3 = rejected");
        }

        BigDecimal[] withContext =
                numerator.divideAndRemainder(denominator,
                    new MathContext(4, RoundingMode.DOWN));
        System.out.println("precision 4 = "
                + Arrays.toString(withContext));

        System.out.println("unlimited 1/3 qr = "
                + Arrays.toString(one.divideAndRemainder(
                        three, MathContext.UNLIMITED)));

        try {
            a.divideAndRemainder(BigDecimal.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("zero divisor = rejected");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 BigDecimalQuotientRemainderDemo.java
java BigDecimalQuotientRemainderDemo
```

**Expected output:**

```text
positive -> q=5.0, r=2.5, identity=true
negative dividend -> q=-5.0, r=-2.5, identity=true
negative divisor -> q=-5.0, r=2.5, identity=true
both negative -> q=5.0, r=-2.5, identity=true
integral = 5.0
remainder = 2.5
euclidean mod(-17.5,3) = 0.5
scaled = [2.00, 2.00]
quotient scale = 2
2.00 equals 2 = false
2.00 compareTo 2 = true
1 / 3 qr = [0, 1]
exact 1 / 3 = rejected
rounded 1 / 3 = 0.33
precision 3 = rejected
precision 4 = [6172, 1]
unlimited 1/3 qr = [0, 1]
zero divisor = rejected
```

### Points Verified by the Program

1. All four sign combinations obey `a=q×b+r`, and a nonzero remainder follows the dividend's sign.
2. `remainder` of a negative number is not necessarily non-negative; for Euclidean modulo, normalize separately with a positive modulus.
3. BigDecimal preserves scale in some operations: `10.00/4` gives q=2.00, r=2.00; `equals` differs from `compareTo`.
4. `divideAndRemainder(1,3)` does not need to represent an infinite decimal quotient, whereas exact `divide(3)` must report an error.
5. `MathContext(3)` is insufficient to represent the integral quotient 6172; `MathContext(4)` produces the result.
6. `MathContext.UNLIMITED` does not turn `divideAndRemainder` into an infinite decimal division.
7. Division by 0 is rejected with `ArithmeticException`.

## 15. Common Mistakes and How to Fix Them

| Confusion | Correct understanding |
| --- | --- |
| “divideToIntegralValue returns int” | Returns a `BigDecimal` holding an integer numeric value |
| “Integral quotient is always Math.floor(a/b)” | Truncates toward 0; differs from floor for negative numbers |
| “remainder is always non-negative” | BigDecimal remainder can be negative; sign follows the dividend |
| “BigDecimal.remainder is like BigInteger.mod” | No; BigInteger.mod requires a positive modulus and returns non-negative modulo |
| “divideAndRemainder returns a decimal quotient and remainder” | Element 0 is the **integral quotient**, element 1 is remainder |
| “divide(BigDecimal) and divideToIntegralValue are the same” | One demands an exact decimal quotient, the other takes only the integral part |
| “If 1/3 cannot be divided exactly, taking remainder also errors” | `1.divideAndRemainder(3)` still gives [0,1] |
| “With MathContext.HALF_UP, q=5.833... rounds to 6” | q still truncates toward 0; it does not round the decimal quotient to 6 |
| “Small MathContext precision truncates the result to fit digits” | If the true integral quotient cannot be represented, it may throw `ArithmeticException` |
| “remainder(mc) always has ≤ mc.precision digits” | Remainder is not automatically rounded to precision; it can be longer |
| “MathContext.UNLIMITED makes every division exact” | Infinitely repeating decimal division still has no finite representation |
| “Integral quotient must have scale 0” | Can be 5.0 or 2.00 depending on preferred scale |
| “2.00.equals(2) is true” | false because scales differ; `compareTo` returns 0 |
| “Returning the result mutates the original BigDecimal” | BigDecimal is immutable; methods return new values |
| “Dividing by 0 just creates Infinity” | BigDecimal has no Infinity; throws `ArithmeticException` |
| “Rounding remainder does not affect the invariant” | Rounding the remainder can break the identity a=q*b+r |
| “To split into whole groups, call divide first” | You can use divideAndRemainder directly and avoid repeating decimal quotients |

## 16. Exercises and Solutions

**Exercise 1.** For a=17.5 and b=3, write q and r according to the BigDecimal API.  
**Answer:** q has value 5 (may display as 5.0), r=2.5; use `a.divideAndRemainder(b)` to get both.

**Exercise 2.** For a=−17.5, b=3, why is q not −6?  
**Answer:** `divideToIntegralValue` truncates the quotient toward 0 so q=−5; r=−2.5. Using floor would be a different operation.

**Exercise 3.** For a=17.5 and b=−3, what is the sign of r?  
**Answer:** r=+2.5, because a nonzero remainder carries the sign of dividend a, not the sign of divisor b.

**Exercise 4.** Do `BigDecimal.ONE.divide(new BigDecimal("3"))` and `BigDecimal.ONE.remainder(new BigDecimal("3"))` behave the same way?  
**Answer:** No. divide without rounding requires an exact terminating decimal quotient so it throws an error; remainder returns 1.

**Exercise 5.** What is the result of `new BigDecimal("10.00").divideAndRemainder(new BigDecimal("4"))`?  
**Answer:** [2.00, 2.00], per the example's scale representation; integral quotient value is 2, remainder is 2.

**Exercise 6.** When using `divideAndRemainder`, which element holds q and which holds r?  
**Answer:** `qr[0]` is q, `qr[1]` is r.

**Exercise 7.** Why can `a.remainder(b, new MathContext(3))` throw an exception?  
**Answer:** Because the algorithm needs to compute the integral quotient under MathContext; if the required integral quotient cannot be represented with precision=3, the operation can throw ArithmeticException.

**Exercise 8.** Does using `MathContext(3, RoundingMode.UP)` with 12345/2 round q to 6180?  
**Answer:** No. The exact truncated integral quotient is 6172; a precision=3 limit does not hold enough digits, so it may throw ArithmeticException.

**Exercise 9.** If you need the Euclidean remainder of −17.5 with positive modulus 3, how do you compute it?  
**Answer:** Take `r = a.remainder(m)` (−2.5), then if r is negative, `r.add(m)` (0.5).

**Exercise 10.** Why might testing the identity with `rebuilt.equals(a)` return false even when the arithmetic is right?  
**Answer:** Because BigDecimal.equals also checks scale; use `rebuilt.compareTo(a)==0` when checking equality by numeric value.

**Exercise 11.** To represent the integral part of the quotient as a BigInteger, which API should you call after dividing?  
**Answer:** `a.divideToIntegralValue(b).toBigIntegerExact()`, because the quotient has no fractional component in value.

**Exercise 12.** If user input has divisor=0, what should you do?  
**Answer:** Validate and report an error per contract; division/remainder APIs throw ArithmeticException rather than returning Infinity.

## 17. Checklist Before Using the Three Methods

1. **Read the names carefully:** `divideToIntegralValue` for the integral quotient, `remainder` for the remainder, `divideAndRemainder` for both.
2. **Choose the integer rule:** q truncates toward 0, not floor for negative numbers.
3. **Do not confuse remainder with non-negative modulo.** If Euclidean modulo is needed, check for a positive modulus and normalize r.
4. **Ensure divisor is nonzero**; have a clear policy for null and invalid data.
5. **Do not mechanically replace divide with divideToIntegralValue** if business logic requires a fractional/rounded decimal quotient.
6. **Use MathContext for its intended purpose:** precision bounds the integral quotient result, rather than automatically choosing a rounded q.
7. **Remainder with context can have more digits than precision**; do not silently round it if the invariant must hold.
8. **Check scale and equals:** integer numeric value does not mean scale 0; use compareTo if checking numeric value only.
9. **Verify the invariant a=q*b+r**, remainder magnitude, and remainder sign on positive/negative data.
10. **When both are needed, prefer divideAndRemainder** for clear intent and potential reuse of computation.
11. **When converting results to int/long**, use `*Exact` conversions to catch out-of-range values.
12. **Respect units of measure and currency:** splitting into whole batches differs from splitting evenly into decimal money with rounding.
13. **Test edge cases:** 0, negative divisor, negative a, |a|<|b|, 1/3, varying scales, and small precision.

### References

- [BigDecimal — Java SE 17 Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [MathContext — Java SE 17 Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [RoundingMode — Java SE 17 Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)

**Key Takeaway:** All three methods take the **integral quotient truncated toward 0** and remainder r satisfying `a=q×b+r`. `remainder` can be negative and is not synonymous with Euclidean modulo; `divideAndRemainder` returns the array `[q,r]`. With `MathContext`, the API does not automatically round the integral quotient to fit precision and may throw an exception instead. Always check divisor, scale, and the business meaning of keeping the remainder.