# BigInteger.pow, sqrt, sqrtAndRemainder, and gcd in Java

## 1. Lesson Goal

**java.math.BigInteger** is Java's arbitrary-precision integer class. Rather than being limited to 32 bits of `int` or 64 bits of `long`, it can represent and compute with very large integers within the memory and processing limits of the environment.

This lesson focuses on four methods:

- **pow(int exponent)**: computes integer exponentiation with a **non-negative** integer exponent.
- **sqrt()**: takes the **integer square root**, i.e., the floor integer part of the square root of a non-negative number.
- **sqrtAndRemainder()**: simultaneously obtains the **integer square root** and the **remainder** relative to the square of that integer root.
- **gcd(BigInteger val)**: greatest common divisor of two integers, including negative or 0 inputs.

What they share is **exact integer results**, without needing to convert to `double` or accept digit loss from floating-point numbers. You will learn definitions, input bounds, edge cases, combining methods, justified optimizations, and testing with a Java 17+ program.

## 2. Reviewing BigInteger: Immutability and Exact Arithmetic

Create a `BigInteger` from a decimal string or a `long` value:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42);
BigInteger sum = a.add(b);
~~~

Operations **do not modify** `a` and `b`. `BigInteger` is an **immutable** object type: each method returns a result value according to API rules while the original operands remain unchanged. For common constants, use **BigInteger.ZERO**, **ONE**, **TWO**, **TEN** (`TWO` since Java 9).

Do not write:

~~~java
// Invalid: BigInteger does not have the + operator between objects.
// BigInteger invalid = a + b;
~~~

Use `a.add(b)`, `a.multiply(b)`, `a.pow(...)`. Immutability also means:

~~~java
BigInteger x = BigInteger.valueOf(3);
x.pow(4);                 // result is discarded
System.out.println(x);   // still 3
BigInteger y = x.pow(4);  // 81
~~~

### Why Not Convert Through `double`?

The `double` type has only about **53 bits of precision** in its significand; large integers cannot always be represented accurately. For example, a number with hundreds of digits can completely exceed the finite range of `double`. When wanting an **exact** integer square root or gcd on large numbers, keep the data in `BigInteger` rather than routing through `Math.sqrt(double)`.

## 3. Quick Comparison of the Four APIs

| Method | Input | Output | Mathematical meaning | Cases to watch |
| --- | --- | --- | --- | --- |
| **a.pow(e)** | `e` of type **int**, e ≥ 0 | BigInteger | exact a^e | negative `e` → ArithmeticException |
| **n.sqrt()** | n ≥ 0 | BigInteger | floor(√n) | negative `n` → ArithmeticException |
| **n.sqrtAndRemainder()** | n ≥ 0 | BigInteger[2] | [s, n−s²], s=floor(√n) | negative `n` → ArithmeticException |
| **a.gcd(b)** | a, b are BigInteger | BigInteger | non-negative gcd(|a|,|b|) | gcd(0,0) = 0 |

**pow** has existed since very early Java versions. **sqrt** and **sqrtAndRemainder** were introduced in **Java 9**; in Java 17 they are available. **gcd** is also available in Java 17.

The word **floor** means taking the greatest integer not exceeding the real value. For n=200, √200 is approximately 14.142..., so **sqrt() equals 14**, not the decimal 14.142.

## 4. pow(int exponent): Exact Integer Exponentiation

For a `BigInteger` `a` and non-negative exponent `e`:

\[
a^e = \underbrace{a\times a\times\dots\times a}_{e\text{ factors}}
\]

Method:

~~~java
BigInteger base = BigInteger.valueOf(12);
BigInteger result = base.pow(5); // 248832
~~~

The result is an exact `BigInteger`. There is no 32/64-bit overflow in internal multiplications as commonly happens with `int` or `long`; however, if the result is too large for memory or implementation limits, the operation can still fail to complete.

### The Exponent Is `int`, Not `BigInteger`

The signature is **BigInteger pow(int exponent)**:

~~~java
BigInteger x = BigInteger.valueOf(7);
BigInteger y = x.pow(4); // 2401
~~~

There is no **pow(BigInteger)** overload for general exponentiation. If you have a `BigInteger` as an exponent, you must redesign the algorithm or convert to `int` with an **intValueExact()** check if it genuinely satisfies the bound. Never turn an enormous exponent into `int` with `intValue()` and assume the result is still right: that operation can lose bits.

### Negative Sign by Parity of the Exponent

\[
(-3)^4=81,\qquad (-3)^5=-243
\]

~~~java
BigInteger minusThree = BigInteger.valueOf(-3);
BigInteger even = minusThree.pow(4); // 81
BigInteger odd = minusThree.pow(5);  // -243
~~~

For a negative base, an even exponent produces a non-negative result and an odd exponent produces a negative result. For a positive base, the result is positive when the exponent is positive.

### Cases of 0 and Exponent 0

In the `BigInteger` API:

~~~java
BigInteger a = BigInteger.ZERO.pow(0); // 1
BigInteger b = BigInteger.ZERO.pow(5); // 0
BigInteger c = BigInteger.TEN.pow(0);  // 1
~~~

By the API's integer exponentiation convention, **0.pow(0) returns BigInteger.ONE**. Do not confuse this programming convention with taking an analytic limit at (0,0): that is a different mathematical question.

### Negative Exponents Are Invalid

~~~java
BigInteger base = BigInteger.valueOf(2);
// base.pow(-1) -> ArithmeticException
~~~

For integers, **2^−1=1/2** no longer belongs to the set of integers. `BigInteger.pow` does not return fractions or decimals, and **throws ArithmeticException when exponent < 0**. If the problem requires negative exponents, design a fraction/`BigDecimal` representation or a specific algorithm; do not implicitly coerce types.

### `pow` Differs from `Math.pow`

| Feature | BigInteger.pow | Math.pow |
| --- | --- | --- |
| Base | BigInteger | double |
| Exponent | non-negative int | double |
| Result | Exact integer BigInteger | double, subject to rounding |
| Very large numbers | Not capped at 64 bits, still resource-bounded | Can overflow to Infinity |
| Negative exponents | Unsupported; ArithmeticException | Supported under double semantics |

For example, **BigInteger.TEN.pow(20)** yields exact **100000000000000000000**. Calling **Math.pow(10,20)** returns a `double` with its own representation, and when applied to large integers in general there is no guarantee of keeping every digit.

### Do Not Write Naive Multiplication Loops for Giant Results

You can write a multiplication loop for mathematical illustration, but `BigInteger.pow` is already optimized for the type's characteristics. A very large exponent can generate a result with millions of bits or more. For **untrusted input**, validate the exponent and bound output length **before** running; do not rely on `BigInteger`'s arbitrary precision to omit resource limits.

## 5. sqrt(): Integer Square Root, Not Decimal Root

For a non-negative `BigInteger` `n`, let:

\[
s=\lfloor\sqrt n\rfloor
\]

Then `s` is the **largest non-negative integer satisfying s² ≤ n**. Equivalent definition:

\[
s^2\le n <(s+1)^2
\]

Examples:

| n | √n in mathematics | n.sqrt() |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | approx. 1.414... | 1 |
| 15 | approx. 3.873... | 3 |
| 16 | 4 | 4 |
| 17 | approx. 4.123... | 4 |
| 81 | 9 | 9 |
| 200 | approx. 14.142... | 14 |

~~~java
BigInteger n = BigInteger.valueOf(200);
BigInteger floorRoot = n.sqrt(); // 14
~~~

**sqrt() does not return a double**, does not round to the nearest integer, and does not take the ceiling. It takes the **floor** of the non-negative square root.

### Why Use `BigInteger.sqrt` Instead of `Math.sqrt(double)`?

If `n` has tens or hundreds of digits, converting to `double` can **round `n`**, or even turn it into **Infinity**. Applying `Math.sqrt` to the converted value and casting back to `long`/`int` cannot recover lost information.

Even when `double` remains finite, rounding can cause the root of a number very close to a perfect square to become an **incorrect** integer. `BigInteger.sqrt` computes the exact integer result of **`n` itself**, without relying on a `double` approximation as the output.

### `sqrt` of a Negative Number

~~~java
BigInteger negative = BigInteger.valueOf(-4);
// negative.sqrt() -> ArithmeticException
~~~

`BigInteger` represents real signed integers, not complex numbers. For **n < 0**, `sqrt()` throws **ArithmeticException**. Check **n.signum() >= 0** if the interface needs a custom error message.

### Checking for a Perfect Square

A perfect square is a number of the form k² with integer `k`. For n ≥ 0:

~~~java
static boolean isPerfectSquare(BigInteger n) {
    if (n.signum() < 0) {
        return false;
    }
    BigInteger s = n.sqrt();
    return s.multiply(s).equals(n);
}
~~~

This is an illustrative method to be placed inside a class with `import java.math.BigInteger`. For n=81, s=9, the comparison returns `true`. For n=200, s=14, 14²=196 differs from 200, returning `false`.

An alternative using the next API is **sqrtAndRemainder()[1].signum() == 0** on non-negative `n`.

## 6. sqrtAndRemainder(): Getting Integer Root and Remainder Together

For n ≥ 0:

\[
s=\lfloor\sqrt n\rfloor,\qquad r=n-s^2
\]

**BigInteger.sqrtAndRemainder()** returns a **`BigInteger[]` array of exactly two elements**:

- **result[0]** is `s`, the integer square root.
- **result[1]** is `r`, the remainder after subtracting s².

~~~java
BigInteger n = BigInteger.valueOf(200);
BigInteger[] pair = n.sqrtAndRemainder();

BigInteger s = pair[0]; // 14
BigInteger r = pair[1]; // 4
~~~

Be sure to call **`r = n−s²`**, **not** division remainder like **`n % s`**. For example, 200 modulo 14 being 4 is merely a coincidence in this example, and the two definitions are not identical in general.

Take n=99 to see clearly:

~~~java
BigInteger[] pair = BigInteger.valueOf(99).sqrtAndRemainder();
// s = 9, r = 99-81 = 18
// Yet 99 % 9 = 0. Two different kinds of "remainder".
~~~

### Important Mathematical Invariants

Because s=floor(√n):

\[
s^2\le n <(s+1)^2=s^2+2s+1
\]

Hence:

\[
n=s^2+r,\qquad 0\le r<2s+1
\]

Since `r` is an integer, this can be written **0 ≤ r ≤ 2s**.

Use this invariant to verify results:

~~~java
BigInteger[] qr = n.sqrtAndRemainder();
BigInteger s = qr[0];
BigInteger r = qr[1];

boolean exactReconstruction = s.pow(2).add(r).equals(n);
boolean validRange = r.signum() >= 0
        && r.compareTo(s.shiftLeft(1).add(BigInteger.ONE)) < 0;
~~~

The illustrative snippet sits inside a method with **n ≥ 0** already declared; **shiftLeft(1)** multiplies `s` by 2. Every step uses `BigInteger`, avoiding `int`/`long` overflow in multiplication/addition.

### When to Use `sqrtAndRemainder` Instead of `sqrt`?

- Need both the **integer root** and the **remainder**.
- Need to check for a **perfect square** (r=0).
- Need an output invariant to test integer algorithms.
- Want to know **how far `n` is from the largest integer square not exceeding `n`**.

Examples:

| n | s = floor(√n) | r = n−s² | Is n a perfect square? |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Yes |
| 1 | 1 | 0 | Yes |
| 2 | 1 | 1 | No |
| 81 | 9 | 0 | Yes |
| 99 | 9 | 18 | No |
| 200 | 14 | 4 | No |

`sqrtAndRemainder()` also **throws ArithmeticException for negative numbers**. If only `s` is needed, calling `sqrt()` is more direct and clearer.

## 7. gcd(BigInteger): Greatest Common Divisor

**gcd** stands for **greatest common divisor**. For two integers `a`, `b` not both zero, `gcd(a,b)` is the largest positive integer dividing both.

Example:

~~~java
BigInteger a = BigInteger.valueOf(54);
BigInteger b = BigInteger.valueOf(24);
BigInteger g = a.gcd(b); // 6
~~~

The positive common divisors of 54 and 24 are 1, 2, 3, 6; the largest is 6.

### Negative Numbers Do Not Make `gcd` Negative

**BigInteger.gcd** always returns a **non-negative** number; fundamentally:

\[
\gcd(a,b)=\gcd(|a|,|b|)
\]

~~~java
BigInteger g = BigInteger.valueOf(-54)
        .gcd(BigInteger.valueOf(24)); // 6
~~~

If either operand is nonzero, `gcd` returns a positive number. With one operand equal to 0, `gcd` returns the absolute magnitude of the other operand.

### Zero Cases

| a | b | a.gcd(b) |
| ---: | ---: | ---: |
| 54 | 24 | 6 |
| −54 | 24 | 6 |
| 0 | 24 | 24 |
| 0 | −24 | 24 |
| 0 | 0 | **0** |
| 101 | 24 | 1 |

In number theory there may be different conventions for `gcd(0,0)`, but **the BigInteger.gcd(0,0) API defines it to return 0**. Do not throw your own exception for this case if you want to stay faithful to API behavior.

**A gcd equal to 1** means the two numbers are **coprime**, without either number necessarily being prime itself.

### Why Is `gcd` Suitable for Very Large Numbers?

The Euclidean algorithm relies on division with remainder:

\[
\gcd(a,b)=\gcd(b,a\bmod b)
\]

Repeating until the remainder is 0. Java provides `BigInteger.gcd` built-in, so you do not need to write an `int`/`long`-based version that accidentally overflows or drops large digits.

For example, if inputs have hundreds of digits, do not convert to `long` to compute `gcd`. Keep them as `BigInteger` and call `a.gcd(b)`.

## 8. Combined Application: Reducing Fractions Using `gcd`

Given a fraction a/b with **b ≠ 0**. If g=gcd(a,b) then:

\[
\frac{a}{b}=\frac{a/g}{b/g}
\]

For example, **84/30** has gcd 6, so it reduces to **14/5**:

~~~java
BigInteger numerator = BigInteger.valueOf(84);
BigInteger denominator = BigInteger.valueOf(30);

if (denominator.signum() == 0) {
    throw new ArithmeticException("Zero denominator");
}
BigInteger g = numerator.gcd(denominator);
BigInteger reducedNumerator = numerator.divide(g);   // 14
BigInteger reducedDenominator = denominator.divide(g); // 5
~~~

This is an illustrative snippet inside a method. `BigInteger.divide` performs integer division and here **divides evenly** because `g` is a common divisor.

For a canonical fraction representation, a **positive denominator** is usually required: if the denominator is negative, flip the signs of both numerator and denominator before or after reduction. If `numerator=0`, `gcd(0,b)=|b|`, so the fraction `0/b` normalizes to `0/1` (once the denominator sign is normalized).

**Warning:** `gcd(0,0)=0`, yet `0/0` is still an invalid fraction; check for a zero denominator **before** dividing by `gcd`.

## 9. Combined Application: Least Common Multiple (LCM)

The least common multiple of two integers `a`, `b` can be computed from `gcd`:

\[
\operatorname{lcm}(a,b)=
\begin{cases}
0,&a=0\text{ or }b=0\\
\left|\frac{a}{\gcd(a,b)}\times b\right|,&\text{otherwise}
\end{cases}
\]

To avoid producing an intermediate value larger than necessary, **divide by gcd first and then multiply**:

~~~java
static BigInteger lcm(BigInteger a, BigInteger b) {
    if (a.signum() == 0 || b.signum() == 0) {
        return BigInteger.ZERO;
    }
    return a.divide(a.gcd(b)).multiply(b).abs();
}
~~~

This is an illustrative method to place inside a class. For example, `lcm(84,30)=420`; for negative inputs, **`abs()`** ensures a non-negative result. With `BigInteger`, multiplication does not suffer `long`-style overflow, yet still incurs memory/CPU cost, so shrinking intermediates helps.

## 10. `pow` with Very Large Numbers: CPU and Memory Limits

You can construct **10^1,000,000** with `BigInteger.TEN.pow(1_000_000)` if the environment has sufficient resources, but the result will have over one million decimal digits. The issue is no longer 64-bit overflow, but rather:

- Object size, heap demand, and temporary memory.
- Time to compute the power and time to convert the value to a string.
- Risk of users exploiting huge exponents to exhaust resources.
- Internal `BigInteger` limits and JVM configuration.

A rough estimate for nonzero `a`, `|a|>1`, and exponent `e`:

\[
\operatorname{bitLength}(|a^e|)
\approx e\log_2|a|+1
\]

This is a **size estimate**, not an exact bit-counting formula for every `n`. If parsing a user-supplied exponent, enforce an application-appropriate limit **before calling `pow`**.

If you only need **a^e modulo m**, do not build the full `a^e` and then take the remainder: use **BigInteger.modPow(exponent, modulus)** according to its contract to save resources. `modPow` is a separate API, especially useful in modular algorithms and cryptography; it is **not** the pure integer exponentiation of this lesson.

## 11. `sqrt` of Giant Numbers: Do Not Use `double` Root as the Answer

For `n` with hundreds of digits, **sqrt()** gives the exact integer result matching `n`'s value. Example:

~~~java
BigInteger n = BigInteger.TEN.pow(40);
BigInteger s = n.sqrt();
// s equals 10^20 = 100000000000000000000
~~~

When `n` is a perfect square, `sqrtAndRemainder` returns remainder 0. For non-squares, the remainder shows the distance from `n` to the square `s²`, and is always less than `2s+1`.

A common task is checking whether `n` is a perfect square before factoring further. Use **n.signum() < 0** to reject invalid domain values, then:

~~~java
boolean perfect = n.sqrtAndRemainder()[1].signum() == 0;
~~~

This snippet requires `n` to be a **non-negative** `BigInteger` already declared. Never compare `Math.sqrt(n.doubleValue())` against large integers, because `doubleValue()` can lose precision or become `Infinity`.

## 12. Signs and Exceptions: Boundary Check Table

| Situation | Result/behavior |
| --- | --- |
| **BigInteger.valueOf(12).pow(5)** | 248832 |
| **BigInteger.valueOf(-3).pow(4)** | 81 |
| **BigInteger.valueOf(-3).pow(5)** | −243 |
| **BigInteger.ZERO.pow(0)** | 1 |
| **a.pow(-1)** | **ArithmeticException** |
| **BigInteger.ZERO.sqrt()** | 0 |
| **BigInteger.valueOf(200).sqrt()** | 14 |
| **BigInteger.valueOf(200).sqrtAndRemainder()** | [14, 4] |
| **BigInteger.valueOf(-1).sqrt()** | **ArithmeticException** |
| **BigInteger.valueOf(-1).sqrtAndRemainder()** | **ArithmeticException** |
| **BigInteger.valueOf(-54).gcd(BigInteger.valueOf(24))** | 6 |
| **BigInteger.ZERO.gcd(BigInteger.ZERO)** | 0 |

If an argument is a **`null`** reference, do not treat it as 0. Depending on the method and null position, the program may throw `NullPointerException`; when handling external data, perform explicit null checks before operations.

## 13. Verifying Correctness via Invariants Instead of Only Comparing Output

Several useful QA conditions:

- **pow**: for even `e`, `a.pow(e)` is non-negative; for odd `e`, result sign matches `a`'s sign; `a.pow(0)=1`.
- **sqrt**: for `s=n.sqrt()`, `s≥0`, `s²≤n`, and `(s+1)²>n`.
- **sqrtAndRemainder**: `n=s²+r`, `r≥0`, `r<2s+1`; `n` is a perfect square when `r=0`.
- **gcd**: `g≥0`, if `g>0` then `a.remainder(g)=0` and `b.remainder(g)=0`; `gcd(a,b)=gcd(b,a)=gcd(|a|,|b|)`; `gcd(a,0)=|a|`.
- **Immutability**: `a`, `b`, `n` retain their original values after calling the methods.

Test **0, 1, negative numbers (where API allows), perfect squares, and numbers adjacent to both sides of perfect squares**, as well as numbers with hundreds of digits. For property-based tests, bound sizes of `n`/`e` so the test suite does not consume excessive resources.

**Do not only test string output values and ignore exception types.** The negative exponent condition of `pow` and negative radicand condition of `sqrt` are part of the API contract to test.

## 14. Version Differences and API Syntax

All standalone runnable examples here target **Java 17+**:

- **BigInteger.pow(int)** takes a non-negative `int` integer exponent.
- **BigInteger.sqrt()** and **sqrtAndRemainder()** appeared in **Java 9**, unavailable in older Java 8 releases.
- **BigInteger.gcd(BigInteger)** returns a non-negative number.
- **BigInteger.TWO** appeared in Java 9; if Java 8 compatibility is needed, use `BigInteger.valueOf(2)`.

`BigInteger` does not support operator overloading of the **^** operator for exponentiation. In Java, **^** on primitive types is bitwise XOR, **not** exponentiation. To compute 2^10, write **BigInteger.valueOf(2).pow(10)**, not `2 ^ 10`.

Likewise, there is no **BigInteger.sqrt(double precision)** or **pow(BigInteger exponent)** method matching those simple meanings. Use the exact signatures in the API docs and redesign when the problem has different input types.

## 15. Standalone Runnable Java 17+ Program

Create file **BigIntegerOperationsDemo.java** with the following code:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerOperationsDemo {
    static void show(String label, BigInteger value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        BigInteger twelve = BigInteger.valueOf(12);
        BigInteger negativeThree = BigInteger.valueOf(-3);

        show("12^5", twelve.pow(5));
        show("(-3)^5", negativeThree.pow(5));
        show("(-3)^4", negativeThree.pow(4));
        show("10^20", BigInteger.TEN.pow(20));
        show("0^0", BigInteger.ZERO.pow(0));

        BigInteger n = BigInteger.valueOf(200);
        BigInteger[] pair = n.sqrtAndRemainder();

        show("floor sqrt(200)", n.sqrt());
        System.out.println("sqrtAndRemainder(200): "
                + Arrays.toString(pair));
        show("reconstruct(200)", pair[0].pow(2).add(pair[1]));

        BigInteger square = BigInteger.valueOf(123456789).pow(2);
        show("perfect-square root", square.sqrt());
        System.out.println("sqrtAndRemainder(81): "
                + Arrays.toString(
                        BigInteger.valueOf(81).sqrtAndRemainder()));

        show("gcd(-54, 24)",
                BigInteger.valueOf(-54).gcd(BigInteger.valueOf(24)));
        show("gcd(0, -24)",
                BigInteger.ZERO.gcd(BigInteger.valueOf(-24)));
        show("gcd(0, 0)",
                BigInteger.ZERO.gcd(BigInteger.ZERO));
        show("gcd(101, 24)",
                BigInteger.valueOf(101).gcd(BigInteger.valueOf(24)));

        show("sqrt(10^40)", BigInteger.TEN.pow(40).sqrt());

        try {
            negativeThree.pow(-1);
        } catch (ArithmeticException e) {
            System.out.println("negative exponent: ArithmeticException");
        }

        try {
            BigInteger.valueOf(-1).sqrt();
        } catch (ArithmeticException e) {
            System.out.println(
                    "negative square root: ArithmeticException");
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 BigIntegerOperationsDemo.java
java BigIntegerOperationsDemo
~~~

Stdout:

~~~text
12^5: 248832
(-3)^5: -243
(-3)^4: 81
10^20: 100000000000000000000
0^0: 1
floor sqrt(200): 14
sqrtAndRemainder(200): [14, 4]
reconstruct(200): 200
perfect-square root: 123456789
sqrtAndRemainder(81): [9, 0]
gcd(-54, 24): 6
gcd(0, -24): 24
gcd(0, 0): 0
gcd(101, 24): 1
sqrt(10^40): 100000000000000000000
negative exponent: ArithmeticException
negative square root: ArithmeticException
~~~

### Program Output Analysis

1. **12^5** is computed as 248832. In Java, the **^** symbol in the label is only text; to compute exponentiation use the `pow` method.
2. **(-3)^5** is negative, while **(-3)^4** is positive according to odd/even exponent rules.
3. **10^20** is a large integer printed with all digits intact thanks to `BigInteger`, without `double` scientific notation.
4. **0^0** returns 1 per `BigInteger` API convention.
5. **sqrt(200)** returns 14, while **sqrtAndRemainder** returns `[14,4]`, since 14²=196 and 200−196=4.
6. The `reconstruct(200)` line verifies the **n=s²+r** invariant.
7. The square of 123456789 is a perfect square; `sqrt` recovers exact 123456789.
8. **sqrtAndRemainder(81)** has `r=0`, so 81 is a perfect square.
9. `gcd` handles negative signs, zero, and coprime pairs per specification.
10. For the large number 10^40, `sqrt` returns exact 10^20.
11. `pow` with a negative exponent and `sqrt` with negative `n` both throw **ArithmeticException**; the program catches them to demonstrate without exiting early.

These values are verified using the `BigInteger` API on the JDK. All used methods exist in Java 17.

## 16. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | Right direction |
| --- | --- | --- |
| Using the **^** operator for exponents | In Java `^` is XOR, not exponentiation | Use **pow(int)** |
| Calling **pow(-1)** to compute inverse | Negative exponents are rejected | Represent fraction or decimal per problem |
| Converting large `n` to `double` then `Math.sqrt` | Can lose precision/Infinity | Use **BigInteger.sqrt()** |
| Thinking `sqrt(200)` will be 14.142... | API returns **integer** root | Use `BigDecimal.sqrt` if decimal root and precision rules are truly needed |
| Thinking `sqrt` rounds to nearest | `sqrt` takes floor, not round | Check s²≤n<(s+1)² |
| Assuming remainder is `n % s` | `sqrtAndRemainder` returns **n−s²** | Identify the right invariant |
| Taking the first array element as remainder | Result `[0]` is root, `[1]` is remainder | Name root/remainder variables clearly |
| Checking perfect square only via `Math.sqrt(n.doubleValue())` | Fails for large numbers near squares | Use `sqrtAndRemainder()[1] == 0` |
| Calling `sqrt` on negative numbers without a policy | `ArithmeticException` | Check `signum` beforehand |
| Thinking `gcd(-54,24) = -6` | API returns non-negative number | Result =6 |
| Thinking `gcd(0,0)` throws an exception | API defines result 0 | Test the zero case |
| Using `gcd` before checking zero denominator | `0/0` is still invalid | Validate `denominator != 0` |
| Multiplying `a*b` then dividing by `gcd` for `lcm` in `long` | Can overflow `long` | Use `BigInteger` and divide by `gcd` before multiplying |
| Discarding result of **x.pow(e)** | `BigInteger` is immutable | Assign returned object |
| Running `pow` with huge exponents from input | Consumes heavy memory/CPU | Limit exponent and output size |
| Using `BigInteger.pow` for `a^e mod m` | Creates unnecessarily huge intermediates | Consider **modPow** |
| Using `BigInteger.TWO` on Java 8 | `TWO` appeared in Java 9 | Java 17 supports it; Java 8 uses `valueOf(2)` |

## 17. Practice Exercises

**Exercise 1.** Compute 7^4 using `BigInteger`. Which method should be called?

*Answer:* **BigInteger.valueOf(7).pow(4)**, result **2401**.

**Exercise 2.** What is **BigInteger.ZERO.pow(0)**? What about **BigInteger.TEN.pow(-1)**?

*Answer:* The first returns **BigInteger.ONE (1)**; the second throws **ArithmeticException** due to the negative exponent.

**Exercise 3.** Given n=99, what does `sqrtAndRemainder` return?

*Answer:* √99 lies between 9 and 10, s=9, r=99−81=18, so it returns **[9,18]**. This remainder is not `99%9`.

**Exercise 4.** Given n=81, how do you know `n` is a perfect square without using `double`?

*Answer:* **n.sqrtAndRemainder()[1].signum() == 0** (for non-negative `BigInteger` `n`) or compare **n.sqrt().pow(2).equals(n)**.

**Exercise 5.** What do `gcd(-54, 24)` and `gcd(0,0)` return?

*Answer:* **6** and **0** per the `BigInteger.gcd` contract.

**Exercise 6.** Why is `BigInteger.valueOf(101).gcd(BigInteger.valueOf(24))` not 101? What is the result?

*Answer:* 101 and 24 share no positive common divisors other than 1, so the gcd is **1**.

**Exercise 7.** What does reducing the fraction 84/30 with `gcd` produce?

*Answer:* gcd(84,30)=6; new numerator 84/6=14, new denominator 30/6=5, giving **14/5**.

**Exercise 8.** What is the LCM of 84 and 30? In what order should it be computed?

*Answer:* **420**. Take **84/gcd(84,30)=14**, then multiply by 30. In `BigInteger` code, handle zero inputs and signs.

**Exercise 9.** Why must `pow` be bounded when receiving base and exponent from an HTTP request, even when using `BigInteger`?

*Answer:* The result can be millions or billions of bits long, putting pressure on memory/CPU and even exceeding implementation limits. `BigInteger` does not mean infinite resources.

**Exercise 10.** For n=200, prove that the remainder from `sqrtAndRemainder` lies within the allowed range.

*Answer:* s=14, r=4. **0≤4<2×14+1=29**, and **14²+4=200**.

## 18. Official References

- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): signatures and contracts of **pow(int)**, **sqrt()**, **sqrtAndRemainder()**, **gcd(BigInteger)**, and supporting methods.
- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): consider when a decimal root is needed instead of an integer root; **sqrt(MathContext)** requires precision and rounding rules.
- [Java SE 17 Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): contrasting **Math.sqrt(double)** with `BigInteger` integer roots and `double` limits.
- [Java Language Specification SE 17 — Integer Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): `int`/`long` limits and primitive operations.