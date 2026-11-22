# Sign of the Remainder with Negative Operands — Java 17+

In Java, the **`%`** operator computes the **remainder of division**, not a modulo operation that always yields a non-negative result. For two integers `a` and `b` (where `b != 0`), Java divides integers according to **truncation toward zero**, and then computes the remainder:

~~~text
q = a / b      (integer quotient truncated toward 0)
r = a % b
a = q * b + r  (mathematical identity)
~~~

**Main rule:** A non-zero integer remainder carries the **same sign as the dividend `a`** (the left operand), **not the sign of the divisor `b`** (the right operand). If it divides evenly, the integer remainder is `0`.

~~~java
System.out.println( 7 %  3); //  1
System.out.println(-7 %  3); // -1
System.out.println( 7 % -3); //  1
System.out.println(-7 % -3); // -1
~~~

Do not confuse `-7 % 3` with `Math.floorMod(-7, 3)`: they are **`-1`** and **`2`**, respectively. The two expressions use **different quotient rules**.

## 1. Sign Table for Integer Remainder

| Dividend `a` | Divisor `b` | Integer Quotient `a / b` | Remainder `a % b` | Check |
| ---: | ---: | ---: | ---: | --- |
| 7 | 3 | 2 | 1 | `7 = 2 * 3 + 1` |
| −7 | 3 | −2 | −1 | `-7 = (-2) * 3 + (-1)` |
| 7 | −3 | −2 | 1 | `7 = (-2) * (-3) + 1` |
| −7 | −3 | 2 | −1 | `-7 = 2 * (-3) + (-1)` |
| −9 | 3 | −3 | 0 | Divides evenly |
| 0 | −3 | 0 | 0 | Dividend is 0 |

For a non-zero integer divisor, the mathematical magnitude of the remainder satisfies **`|r| < |b|`**; when `r != 0`, the sign of `r` is the sign of `a`. Note that `Math.abs(Integer.MIN_VALUE)` is still negative due to `int` representation limits, so do not blindly use `Math.abs` to verify this inequality at every boundary.

### Why Does `-7 % 3 == -1`?

Java takes the integer quotient of `-7 / 3` as **`-2`**, not `-3`:

~~~text
-7 / 3 = -2       (truncated toward 0)
-7 = (-2) * 3 + r
 r = -7 - (-6) = -1
~~~

If you replace the quotient with `floor(-7/3) = -3`, the corresponding remainder is 2. That is the **floor division / floor modulus** approach, not how Java computes integer `%`.

## 2. Runnable Java 17+ Program

Save a UTF-8 file named **`RemainderSignsDemo.java`**:

~~~java
public class RemainderSignsDemo {
    private static void show(int a, int b) {
        System.out.println(a + "/" + b + "=" + (a / b)
                + ",remainder=" + (a % b));
    }

    public static void main(String[] args) {
        System.out.println("== integer signs ==");
        show(7, 3);
        show(-7, 3);
        show(7, -3);
        show(-7, -3);
        show(-9, 3);
        show(0, -3);

        int dividend = -7;
        int divisor = 3;
        int quotient = dividend / divisor;
        int remainder = dividend % divisor;
        System.out.println("recombined="
                + (quotient * divisor + remainder));

        System.out.println("== floor modulus ==");
        System.out.println("remainderNeg=" + (-7 % 3));
        System.out.println("floorModNeg=" + Math.floorMod(-7, 3));
        System.out.println("floorModPosNeg=" + Math.floorMod(7, -3));
        System.out.println("floorModNegNeg=" + Math.floorMod(-7, -3));

        int slots = 3;
        int rawIndex = -7 % slots;
        int safeIndex = Math.floorMod(-7, slots);
        System.out.println("rawIndex=" + rawIndex);
        System.out.println("safeIndex=" + safeIndex);

        System.out.println("== edge cases ==");
        System.out.println("longRemainder=" + (-7L % 3L));
        System.out.println("minByMinusOne="
                + (Integer.MIN_VALUE % -1));

        try {
            int invalid = 7 % 0;
            System.out.println("unexpected=" + invalid);
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }

        System.out.println("== floating-point ==");
        System.out.println("doubleNeg=" + (-7.5 % 3.0));
        System.out.println("doubleNegDivisor=" + (7.5 % -3.0));
        System.out.println("negativeZero=" + (-0.0 % 3.0));
        System.out.println("floatingZeroIsNaN="
                + Double.isNaN(7.0 % 0.0));
        System.out.println("infiniteDividendIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY % 3.0));
        System.out.println("infiniteDivisor="
                + (-7.5 % Double.POSITIVE_INFINITY));
    }
}
~~~

With **JDK 17 or later**, open PowerShell or Bash in the directory containing the file and run:

~~~bash
java -version
javac -version
javac -encoding UTF-8 RemainderSignsDemo.java
java RemainderSignsDemo
~~~

**Exact expected output** from `java RemainderSignsDemo` (excluding the JDK version output):

~~~text
== integer signs ==
7/3=2,remainder=1
-7/3=-2,remainder=-1
7/-3=-2,remainder=1
-7/-3=2,remainder=-1
-9/3=-3,remainder=0
0/-3=0,remainder=0
recombined=-7
== floor modulus ==
remainderNeg=-1
floorModNeg=2
floorModPosNeg=-2
floorModNegNeg=-1
rawIndex=-1
safeIndex=2
== edge cases ==
longRemainder=-1
minByMinusOne=0
integerZero=ArithmeticException
== floating-point ==
doubleNeg=-1.5
doubleNegDivisor=1.5
negativeZero=-0.0
floatingZeroIsNaN=true
infiniteDividendIsNaN=true
infiniteDivisor=-7.5
~~~

## 3. Where Is the Negative Operand?

In the expression `a % b`:

- `a`: the **dividend**, located to the **left** of `%`.
- `b`: the **divisor**, located to the **right** of `%`.
- The sign of a non-zero integer remainder follows **`a`**, whether `b` is positive or negative.

Example with the same dividend `7`:

~~~java
int a = 7;
System.out.println(a % 3);  // 1.
System.out.println(a % -3); // 1.
~~~

Negating the **divisor** changes the quotient's sign, but **does not flip the remainder's sign**. Conversely, changing the dividend from 7 to −7 flips the remainder's sign when non-zero:

~~~java
System.out.println(-7 % 3);  // -1.
System.out.println(-7 % -3); // -1.
~~~

Do not conclude that `%` "always returns a positive number in the range 0 to `b-1`". That holds only under certain conditions (such as `a >= 0` and `b > 0`), and is **false when `a` is negative**.

## 4. Differences Between `%` and `Math.floorMod()`

Java provides `Math.floorMod` to compute the remainder corresponding to **floor division** (rounding the quotient down toward negative infinity). For integers:

~~~text
%:            a = (a / b) * b + (a % b)         (quotient truncated toward 0)
floorMod:     a = floorDiv(a,b) * b + floorMod(a,b)
~~~

| Expression | `%` Result | `Math.floorMod` Result |
| --- | ---: | ---: |
| `-7` and `3` | −1 | 2 |
| `7` and `-3` | 1 | −2 |
| `-7` and `-3` | −1 | −1 |
| `7` and `3` | 1 | 1 |

With a **positive divisor**, `Math.floorMod(a, b)` produces a result from **0 to `b - 1`**, which is useful when normalizing circular indices, cyclic sequence numbers, or grouping into a fixed number of slots.

~~~java
int slotCount = 3;
int raw = -7 % slotCount;              // -1: negative index.
int index = Math.floorMod(-7, slotCount); // 2: within 0..2.
~~~

If `b` is negative, `Math.floorMod(a, b)` gives a result **equal to 0 or having the sign of the divisor** (which can be negative). Therefore, when using `floorMod` to compute an array index, ensure a **positive modulus**.

**Do not hand-roll `(a % n + n) % n` as a universal formula**, because the intermediate addition can overflow `int` when `n` is large. `Math.floorMod(a, n)` expresses the intent better for `n > 0`. If `n == 0`, integer `floorMod` also throws `ArithmeticException`.

## 5. Boundary Notes for `int` and `long`

`%` operations between `int` and `long` are carried out on integer operands after Java applies the appropriate numeric promotion rules. The result has the corresponding integer type:

~~~java
int i = -7 % 3;     // int -1.
long j = -7L % 3L;  // long -1.
~~~

A surprising boundary case:

~~~java
int rem = Integer.MIN_VALUE % -1; // 0.
~~~

Mathematically, `Integer.MIN_VALUE` is evenly divisible by −1, so the remainder is 0. The separate division `Integer.MIN_VALUE / -1` produces a quotient not representable in `int` (Java handles overflow per integer semantics), yet **the `%` operator still returns 0 and does not throw an exception**.

**Divide-by-zero warning:**

~~~java
// int bad = 7 % 0; // Runtime ArithmeticException.
int divisor = 3;
if (divisor != 0) {
    System.out.println(7 % divisor); // 1.
}
~~~

With integer `%`, a divisor **equal to 0** throws `ArithmeticException`. A negative divisor **does not** throw an exception just for being negative.

## 6. Is `%` Different for `float` and `double`?

Yes. The `%` operator also works on floating-point types. It still follows remainder logic based on **truncating the quotient toward 0**, **not** `Math.IEEEremainder` (which uses a different quotient rule). When operands are finite and the divisor is non-zero, a non-zero remainder normally takes the sign of the dividend.

~~~java
System.out.println(-7.5 % 3.0);  // -1.5.
System.out.println(7.5 % -3.0);  //  1.5.
~~~

However, IEEE 754 floating-point numbers have special cases:

| Expression | Result | Explanation |
| --- | --- | --- |
| `-7.5 % 3.0` | `-1.5` | Remainder carries the dividend's sign |
| `7.5 % -3.0` | `1.5` | Divisor's sign does not determine remainder's sign |
| `-0.0 % 3.0` | `-0.0` | Floating-point distinguishes negative zero and positive zero |
| `7.0 % 0.0` | `NaN` | **Does not** throw `ArithmeticException` like integers |
| `Double.POSITIVE_INFINITY % 3.0` | `NaN` | Infinite dividend |
| `-7.5 % Double.POSITIVE_INFINITY` | `-7.5` | Infinite divisor, finite dividend |

Do not confuse `-0.0` (a floating-point value with a sign bit) with `int` `0`: integer remainders have no "negative zero" state.

When program logic needs to guard against invalid floating-point numbers, consider `Double.isFinite(...)`, `Double.isNaN(...)`, and the problem's rounding/precision requirements. Do not apply a blanket "modulo by 0 always throws an exception" rule across both integers and floating-point numbers.

## 7. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`-7 % 3` equals 2." | In Java, the result is **−1** |
| "The remainder follows the divisor's sign." | A **non-zero integer remainder follows the dividend's sign** |
| "`7 % -3` must be negative." | The result is **1** |
| "`%` always returns a non-negative index." | No, if the dividend is negative |
| "`%` and `Math.floorMod` are always the same." | They differ when signs cause the quotient and remainder rules to diverge |
| "A negative divisor causes `ArithmeticException`." | Only dividing by **0** causes this arithmetic error for integers |
| "`double % 0.0` also throws `ArithmeticException`." | The result is `NaN` |
| "The negative sign of 0 is not worth distinguishing in `double`." | You can get `-0.0` as a floating-point remainder |
| "`Math.abs` always returns a non-negative number for any `int`." | `Math.abs(Integer.MIN_VALUE)` is still negative due to overflow |

## 8. Self-Check Exercises

1. What is `-10 % 3`?  
   *Answer:* **−1** because `-10 / 3` gives integer quotient −3 and `-10 - (-3)*3 = -1`.
2. What is `10 % -3`?  
   *Answer:* **1**: the dividend is positive.
3. What is `-10 % -3`?  
   *Answer:* **−1**: the dividend is negative.
4. What is `-12 % 4`?  
   *Answer:* **0** because it divides evenly.
5. How do `Math.floorMod(-10, 3)` and `-10 % 3` differ?  
   *Answer:* **2** versus **−1**; `floorMod` with a positive divisor normalizes the remainder to be non-negative.
6. Is `int index = -1 % 5;` suitable for accessing a five-element array?  
   *Answer:* No; `index == -1` is a negative index. Use `Math.floorMod(-1, 5) == 4` if wrap-around indexing is needed.
7. Does `7.0 % 0.0` throw `ArithmeticException`?  
   *Answer:* No; the floating-point result is `NaN`, unlike integer `7 % 0`.
8. What does `Integer.MIN_VALUE % -1` return?  
   *Answer:* **0**, because the dividend is evenly divisible by −1.

## Checklist

- [ ] Distinguish the **dividend on the left** from the **divisor on the right** of `%`.
- [ ] Remember integer `/` truncates the quotient toward 0, so a non-zero integer remainder follows the **dividend's sign**.
- [ ] Use the sign table to check all four positive/negative combinations of the two operands.
- [ ] Do not use `%` directly as a non-negative index if data can be negative.
- [ ] For `n > 0`, consider `Math.floorMod(a, n)` to get a remainder from 0 to `n - 1`.
- [ ] Check for a zero divisor before integer `%`.
- [ ] Distinguish floating-point `%` from integer `%`, especially `NaN`, infinity, and `-0.0`.
- [ ] Do not assume that negating the divisor automatically negates the remainder.

**Conclusion:** In Java, `%` is the **remainder based on a quotient truncated toward 0**. For integers, **the sign of a non-zero remainder follows the left operand**. When you need a non-negative modulo for wrap-around indexing, use `Math.floorMod(a, n)` with **`n > 0`** instead of assuming `a % n` is always non-negative.