# Addition, Subtraction, Multiplication, Division, and Rounding to Representable Values in Java

## 1. The Core Point: Mathematical Results and Machine-Stored Results Can Differ

In mathematics, the operations `+`, `-`, `*`, and `/` on real numbers produce exact results if the operands are known exactly. In Java, the `float` and `double` types only store a **finite set of binary floating-point values**. When an arithmetic operation produces a mathematical result that does not belong to that set, Java must **round it to a representable value**.

Classic example:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);           // 0.30000000000000004
System.out.println(result == 0.3);    // false
~~~

This is an illustrative snippet, not a standalone runnable class. The program does not "add incorrectly": the decimal literals `0.1`, `0.2`, and `0.3` have already been converted into the nearest representable `double` values. The rounded result of adding the first two `double` values does not match bit-for-bit with the `double` value that the literal `0.3` represents.

**What to distinguish:**

1. **Mathematical value**: for example `1/10 + 2/10 = 3/10`.
2. **Stored value of the operand**: the finite binary representation close to those decimal fractions.
3. **Result of the operation before rounding**: the exact arithmetic result of the two stored values, conceptually speaking.
4. **Result returned by Java**: rounded into the representable value range of the result type, or receiving a special value such as infinity/NaN according to IEEE 754 rules.

You should not treat `float` and `double` as decimal numbers that can be written and computed with arbitrary exactness.

## 2. Two Floating-Point Types in Java

| Property | `float` | `double` |
|---|---|---|
| Representation standard | IEEE 754 binary32 | IEEE 754 binary64 |
| Size | 32 bits | 64 bits |
| Significand precision | 24 binary bits | 53 binary bits |
| Approximate significant decimal digits | 6–7 | 15–16 |
| Normal finite number range | Wide, but narrower than `double` | Wider than `float` |
| Special values | `+Infinity`, `-Infinity`, `NaN`, `+0.0`, `-0.0` | Same |
| Default literal | Requires `f`/`F` suffix, e.g. `0.1f` | `0.1` defaults to `double` |

Besides *normal* numbers, both types can store **subnormal** numbers very close to 0, with reduced relative precision. `Double.MIN_VALUE` is the **smallest positive subnormal number** greater than 0, not "the most negative `double` number"; the finite negative value farthest from 0 is `-Double.MAX_VALUE`. For `float`, the meaning of `Float.MIN_VALUE` is similar.

When precision is prioritized and there is no memory-saving constraint or protocol requiring `float`, `double` is usually the more appropriate choice. However, `double` does not make `0.1` an exact binary fraction either.

### Why Is `0.1` Not Exactly Representable in Binary?

The values `0.5 = 1/2` and `0.25 = 1/4` have finite binary representations. However, `0.1 = 1/10` has an infinitely repeating binary pattern; it cannot be stored exactly with a finite number of bits. The compiler converts decimal literals into `float` or `double` values according to the rounding rule.

Printing `System.out.println(0.1)` and seeing `0.1` **does not prove exact storage**: `Double.toString` chooses a concise decimal representation that, when parsed back, recovers the exact corresponding `double` value. The decimal digits displayed are not the entire bit content of the stored value.

## 3. Rules for Rounding to a Representable Value

For basic floating-point arithmetic operations in Java 17+, finite results are rounded using IEEE 754's **round to nearest, ties to even** mode:

- If the exact result is closer to one representable value than another, pick the nearest value.
- If the result lies **exactly halfway** between two consecutive representable values, pick the value whose last bit of the significand is even (*ties to even*).
- This rule applies to the results of floating-point arithmetic operators; it is **not synonymous** with the rules of every method in `Math`, such as `Math.round`.

In particular, **each basic operation** (addition/subtraction/multiplication/division) produces a result in the type of the expression with the corresponding precision and exponent range. In Java 17+, floating-point semantics are always strict (*always-strict*), so there is no longer any variation in extended-exponent intermediates across `strictfp`/non-`strictfp` regions as in very old JDKs.

### ULP and the Gap Between Two Adjacent Numbers

**ULP** (*unit in the last place*) helps express the coarseness of the grid of representable numbers at a given magnitude. Java provides `Math.ulp(double)` and `Math.ulp(float)`; `Math.nextUp(x)` and `Math.nextDown(x)` step to the adjacent representable floating-point number in the corresponding direction.

Around `1.0` of type `double`, the gap from `1.0` to the next larger `double` is `2^-52`, approximately `2.220446049250313E-16`. Therefore, the expression:

~~~java
double halfGap = Math.ulp(1.0) / 2.0;
double rounded = 1.0 + halfGap;
~~~

has `rounded == 1.0`: the ideal sum lies exactly halfway between `1.0` and `Math.nextUp(1.0)`, and the tie rounds to `1.0` by the ties-to-even rule.

There is no single "fixed absolute error" for all `double` values. As the absolute magnitude increases, the gap between representable numbers generally increases; for very small numbers in the subnormal region, the mechanism has its own specifics.

## 4. Addition and Subtraction: Rounding and Loss of Significant Digits

### 4.1. Addition `+`

For two floating-point operands, Java adds the values currently stored in each operand, then returns a representable result of the result type. That can introduce a small discrepancy compared to idealized decimal addition.

~~~java
double a = 0.1;
double b = 0.2;
double sum = a + b;      // 0.30000000000000004
~~~

There is no exact representation of `0.1` or `0.2` in binary64, so the comparison `sum == 0.3` is `false` here.

**Adding a very large number to a very small number** can "swallow" the small number when the difference exceeds the resolution of `double`:

~~~java
double large = 1e16;
double small = 1.0;
double same = large + small; // still represented as 1.0E16
~~~

A difference of 1 is too small compared to the ULP gap around `1e16`. Therefore, even though mathematically `large + 1` differs from `large`, the Java result can be strictly equal to `large`.

### 4.2. Subtraction `-` and *Catastrophic Cancellation*

Subtracting two very close numbers can lose many significant digits: if the two numbers were already rounded in an earlier step, the error of each number can become large relative to the small difference. This phenomenon is called **catastrophic cancellation**.

For example, not every algebraic expression preserves its result when intermediate operations are rounded:

~~~java
double original = 1e16;
double modified = original + 1.0;
double difference = modified - original; // 0.0, not 1.0
~~~

The value `modified` already became equal to `original` after addition, so subtraction cannot "recover" the lost 1.0 information. Switching to `double` from `float` can reduce error, but does not eliminate this property.

### 4.3. Addition Is Not Strictly Associative

In real algebra, `(a + b) + c = a + (b + c)`. With floating-point numbers, each `+` operation may round, so the two ways of parenthesizing can differ:

~~~java
double left = (1e16 + -1e16) + 1.0;    // 1.0
double right = 1e16 + (-1e16 + 1.0);  // 0.0
~~~

The addition inside parentheses `-1e16 + 1.0` loses the small 1; whereas `1e16 + -1e16` yields 0. This is why the order of summing multiple elements affects accuracy; you must not freely rearrange the order of floating-point operations as you would when transforming algebraic expressions over exact real numbers.

## 5. Multiplication `*`: Results Can Overflow to Infinity or Underflow to 0

Multiplying two finite values can yield a mathematical product larger than every finite number representable in the result type: **floating-point overflow**. In that case, the result can be `+Infinity` or `-Infinity`, depending on the sign. Unlike Java integer multiplication, floating-point multiplication **does not wrap around to negative values with two's-complement bit patterns**.

~~~java
double overflow = 1e308 * 10.0; // Infinity
~~~

A multiplication (or division) can also produce a non-zero number that is too small to represent, leading to **underflow**, resulting in a subnormal number or rounding to `+0.0`/`-0.0`.

~~~java
double underflow = Double.MIN_VALUE / 2.0; // 0.0
~~~

Here `Double.MIN_VALUE` itself is the smallest positive subnormal unit; halving it yields no representable non-zero positive `double`, so the result is rounded to `0.0`.

Not every multiplication of very large numbers yields Infinity, nor does every very small number automatically become 0: subnormal numbers can still store finite non-zero values very close to 0.

## 6. Division `/`: Rounding, Division by 0, Infinity, and NaN

With floating-point operands, `/` computes the quotient and rounds to a representable value. Division that does not terminate in binary usually produces an approximate result, similar to `1.0 / 10.0`.

A major difference from **integer division**: floating-point division by 0 **does not throw `ArithmeticException`**. It follows IEEE 754 rules:

| `double` Operation | Result | Explanation |
|---|---|---|
| `1.0 / 0.0` | `Infinity` | Positive value divided by +0 |
| `1.0 / -0.0` | `-Infinity` | Positive value divided by -0 |
| `0.0 / 0.0` | `NaN` | Indeterminate form |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` | Quotient approaches 0 with positive sign |
| `Double.MIN_VALUE / 2.0` | `0.0` | Underflow |
| `-7.0 / 2.0` | `-3.5` | Has fractional part due to floating-point division |

In Java:

~~~java
int integerQuotient = 7 / 2;    // 3: integer division, discards remainder
double floatingQuotient = 7.0 / 2; // 3.5
double castFirst = (double) 7 / 2; // 3.5
double castTooLate = (double) (7 / 2); // 3.0
~~~

This is an illustrative snippet. When both operands are integers, `7 / 2` has already completed integer division **before casting the result** to `double`. To get floating-point division, at least one operand must be `float` or `double` (or cast before computing).

`NaN` is not equal to itself under `==`. Use `Double.isNaN(result)` and `Float.isNaN(result)` to detect it, and `Double.isFinite`/`Float.isFinite` when only finite numbers are accepted.

## 7. Signed Zero and Operations on Special Values

Both `float` and `double` distinguish `+0.0` and `-0.0` in representation, even though the arithmetic comparison `0.0 == -0.0` evaluates to `true`.

- `1.0 / 0.0` is `Infinity`.
- `1.0 / -0.0` is `-Infinity`.
- Negating `-0.0` with the unary minus operator flips the sign to `+0.0`.
- Addition/subtraction of signed zero follows floating-point rules; do not assume every operation on 0 preserves the sign bit.
- `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` yields `NaN`; `0.0 * Double.POSITIVE_INFINITY` also yields `NaN`.

If `NaN` appears in an ordinary arithmetic operation, the result usually continues to be `NaN`. Most ordering comparisons with `NaN` (`<`, `<=`, `>`, `>=`) and equality comparisons `==` evaluate to `false`; `NaN != NaN` is `true`.

**Do not use `result != Double.NaN` to check validity:** this condition is always `true` when an ordinary numeric comparison involves NaN. Use `Double.isNaN` or `Double.isFinite` depending on the requirement.

## 8. Expression Type Affects Precision Before Assignment

`float` and `double` participate in Java's **binary numeric promotion** rules:

- If either operand is `double`, the operation is performed in `double`.
- If neither is `double` and one is `float`, the operation is performed in `float`.
- With two `int` or `long` operands, the operation **does not automatically become floating-point** just because the variable receiving the result is `double`.

Example:

~~~java
float f = 0.1f;
double d = 0.2;
double mixed = f + d;      // double type, but f was already rounded as float
double simple = 1f + 1d;   // 2.0

int a = 7;
int b = 2;
double wrong = a / b;         // 3.0: int division first, then converted to double
double correct = (double) a / b; // 3.5
~~~

This is an illustrative snippet. Promoting `float` to `double` does not reconstruct the exact digits already lost in `float` earlier. The order of type conversion matters just like the order of computation.

For expressions involving literals, `0.1f` is a `float` literal, while `0.1` is a `double` literal. You should not write `float x = 0.1;` because assigning a `double` literal to a `float` variable usually causes a type error; use `0.1f` or an explicit cast.

## 9. Java 17+ Example: Seeing Rounding and Result Types

Create the file `FloatingArithmeticDemo.java`:

~~~java
public class FloatingArithmeticDemo {
    public static void main(String[] args) {
        double sum = 0.1 + 0.2;

        System.out.println("sum=" + sum);
        System.out.println("equal03=" + (sum == 0.3));
        System.out.println("sumHex=" + Double.toHexString(sum));
        System.out.println("literal03Hex="
                + Double.toHexString(0.3));

        double large = 1e16;
        System.out.println("lostOne=" + ((large + 1.0) - large));
        System.out.println("assocLeft=" + ((large + -large) + 1.0));
        System.out.println("assocRight=" + (large + (-large + 1.0)));

        System.out.println("intDivision=" + (7 / 2));
        System.out.println("doubleDivision=" + (7.0 / 2));
        System.out.println("castTooLate=" + (double) (7 / 2));
        System.out.println("floatSum=" + (0.1f + 0.2f));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac FloatingArithmeticDemo.java
java FloatingArithmeticDemo
~~~

Output:

~~~text
sum=0.30000000000000004
equal03=false
sumHex=0x1.3333333333334p-2
literal03Hex=0x1.3333333333333p-2
lostOne=0.0
assocLeft=1.0
assocRight=0.0
intDivision=3
doubleDivision=3.5
castTooLate=3.0
floatSum=0.3
~~~

`Double.toHexString` shows the binary-exponent representation of the `double` value. The two lines `sumHex` and `literal03Hex` differ by **1 ULP at that magnitude**: the rounded sum has a different last bit from the literal `0.3`.

The line `floatSum=0.3` is only the decimal string form Java chooses when printing a `float` value; it does not prove that `0.1f` and `0.2f` were exact decimal fractions.

## 10. Java 17+ Example: ULP, Halfway Rounding, and Exact Integer Limits

Create the file `FloatingRoundingDemo.java`:

~~~java
public class FloatingRoundingDemo {
    public static void main(String[] args) {
        double one = 1.0;
        double gap = Math.ulp(one);
        double halfGap = gap / 2.0;

        System.out.println("ulpAtOne=" + gap);
        System.out.println("halfUlpAdded=" + (one + halfGap));
        System.out.println("nextUp=" + Math.nextUp(one));

        float largeFloat = 16_777_216f; // 2^24
        System.out.println("floatBefore=" + largeFloat);
        System.out.println("floatPlusOne=" + (largeFloat + 1.0f));
        System.out.println("floatPlusTwo=" + (largeFloat + 2.0f));

        System.out.println("doubleRoundTie=" + Math.rint(2.5));
        System.out.println("mathRoundPositive=" + Math.round(2.5));
        System.out.println("mathRoundNegative=" + Math.round(-2.5));
    }
}
~~~

~~~bash
javac FloatingRoundingDemo.java
java FloatingRoundingDemo
~~~

Output:

~~~text
ulpAtOne=2.220446049250313E-16
halfUlpAdded=1.0
nextUp=1.0000000000000002
floatBefore=1.6777216E7
floatPlusOne=1.6777216E7
floatPlusTwo=1.6777218E7
doubleRoundTie=2.0
mathRoundPositive=3
mathRoundNegative=-2
~~~

In `float`, `2^24` is 16,777,216; the gap to the next larger `float` number is 2. Adding 1 lies exactly halfway between two representable values, so it rounds to the value with an even last bit: **still 16,777,216**. Adding 2 reaches an exactly representable number: **16,777,218**.

The last three lines **do not describe the rounding of each arithmetic operator**, but show that explicit rounding APIs in `Math` have their own rules:

- `Math.rint(2.5)` returns `double 2.0` using *nearest, ties to even*.
- `Math.round(2.5)` returns `long 3` (the overload taking `double`).
- `Math.round(-2.5)` returns `long -2`.

For ordinary finite values, `Math.round(x)` rounds to the nearest integer, with halfway cases choosing the direction toward **positive infinity**. Do not equate it with the "round-to-nearest ties-to-even" of `+`, `-`, `*`, and `/`.

## 11. Java 17+ Example: Overflow, Underflow, Infinity, and NaN

Create the file `FloatingSpecialValuesDemo.java`:

~~~java
public class FloatingSpecialValuesDemo {
    public static void main(String[] args) {
        double overflow = 1e308 * 10.0;
        double underflow = Double.MIN_VALUE / 2.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double notANumber = 0.0 / 0.0;

        System.out.println("overflow=" + overflow);
        System.out.println("underflow=" + underflow);
        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("notANumber=" + notANumber);
        System.out.println("finiteOverflow=" + Double.isFinite(overflow));
        System.out.println("isNaN=" + Double.isNaN(notANumber));
        System.out.println("nanEqualsSelf=" + (notANumber == notANumber));
        System.out.println("zerosEqual=" + (0.0 == -0.0));
    }
}
~~~

~~~bash
javac FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
~~~

Output:

~~~text
overflow=Infinity
underflow=0.0
positiveInfinity=Infinity
negativeInfinity=-Infinity
notANumber=NaN
finiteOverflow=false
isNaN=true
nanEqualsSelf=false
zerosEqual=true
~~~

The results above are **special floating-point values according to the specification**, not Java exceptions. If the program is not allowed to have NaN or infinity, you must **check** after computing or validate inputs and range conditions before the operation.

Note: when processing data that needs to be persisted or sent via JSON, `NaN`/`Infinity` values may not be accepted by data interchange formats. Do not assume every serializer handles them the same way.

## 12. Basic Operations Can Round *at Each Step*

Consider:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c; // 1.0
double second = a + (b + c); // 0.0
~~~

Both expressions are identical if `a`, `b`, `c` are viewed as real numbers with exact algebra, but **differ in IEEE 754 binary64** because the result of `b + c` cannot store the `1.0` difference. Therefore:

- You must not assume floating-point addition is associative.
- Multiplication and division can round; grouping/reordering operations can change both the error and when overflow/underflow occurs.
- When summing many numbers spanning widely different orders of magnitude, consider compensated summation algorithms (*compensated summation*, such as Kahan) or changing the summation order when the problem and reproducibility requirements allow.
- When you need a multiply-add operation with **a single rounding** instead of rounding multiplication and then addition separately, Java provides `Math.fma(a, b, c)`: it approximates `a * b + c` with fused multiply-add semantics (*fused multiply-add*). It is useful for certain numerical algorithms, though it does not make all binary data completely exact.

`Math.fma` is not simply the `*` operator followed by `+`: the purpose of the API is to round **once after the combined multiply-add result**, instead of twice for two separate operations.

## 13. Distinguishing Representational Rounding from Intentional Rounding

There are at least **three distinct things** commonly lumped together as "rounding":

| Goal | Mechanism | Example |
|---|---|---|
| Storing the result of addition/subtraction/multiplication/division into `float`/`double` | IEEE 754 rounding to a **representable** value | `1.0 + ulp(1.0)/2` may remain `1.0` |
| Rounding a floating-point number to an integer value or an integral value as `double` | `Math.round`, `Math.rint`, `Math.floor`, `Math.ceil` | `Math.round(2.5) == 3L` |
| Rounding a decimal number to a number of digits by business rules | `BigDecimal.setScale` with `RoundingMode` | Monetary amount with two decimal places |

**Do not confuse a number printed with two decimal places with a result stored accurately to two decimal places.** `System.out.printf("%.2f", value)` only formats the display; the variable `value` remains the same old `double`.

In some applications (pricing, taxes, payments), exact decimal numbers and business-defined rounding rules are required. `BigDecimal` is more suitable provided it is **initialized from a decimal string or `BigDecimal.valueOf` appropriate to the data source**, with an explicit `RoundingMode` chosen, and without converting intermediate results through `double` in steps that require exactness.

### Currency Example: Using Decimal From the Source

Create the file `DecimalVsBinaryDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalVsBinaryDemo {
    public static void main(String[] args) {
        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum =
                new BigDecimal("0.1").add(new BigDecimal("0.2"));

        System.out.println("binarySum=" + binarySum);
        System.out.println("decimalSum=" + decimalSum);
        System.out.println("money="
                + decimalSum.setScale(2, RoundingMode.HALF_UP));
        System.out.println("formattedBinary="
                + String.format(java.util.Locale.ROOT,
                        "%.2f", binarySum));
    }
}
~~~

~~~bash
javac DecimalVsBinaryDemo.java
java DecimalVsBinaryDemo
~~~

Output:

~~~text
binarySum=0.30000000000000004
decimalSum=0.3
money=0.30
formattedBinary=0.30
~~~

The formatting statement on the last line **does not turn** `binarySum` into an exact decimal number; it is only a string for presentation. The line `decimalSum` is the exact decimal addition result of two `BigDecimal` instances created from strings. Avoid `new BigDecimal(0.1)` if the goal is exactness to the decimal value typed by the user, because the `double` constructor preserves the exact binary approximation of `0.1`.

## 14. Comparing Approximate Results and Checking Boundary Conditions

With `float`/`double` computations, do not use `==` to ask "are two mathematical results close to each other" when they have passed through different sequences of operations and rounding errors may have accumulated.

For example, for small finite values near `0.3`:

~~~java
double observed = 0.1 + 0.2;
double expected = 0.3;
boolean close = Math.abs(observed - expected) <= 1e-12;
~~~

`close` is `true` here. This is an **illustrative snippet**, not a universal solution for all numeric comparisons. An absolute threshold of `1e-12` may be too wide for extremely small quantities or too narrow for large quantities.

When designing an approximate equality comparison, consider:

1. **The unit and acceptable error tolerance of the business domain** (degrees, meters, seconds, money...).
2. **Absolute** error and sometimes **relative** error as well, especially when values span many orders of magnitude.
3. **Cases of `NaN`, `Infinity`, and signed zero** — subtraction and `Math.abs` do not handle every case.
4. **Whether bitwise deterministic results are required or tolerance is acceptable**: the algorithm, order of operations, and input data must be specified accordingly.

In code, you should check for finiteness before using a number as an index, size, ratio, or stored value:

~~~java
if (!Double.isFinite(observed)) {
    throw new IllegalArgumentException("Result is not finite");
}
~~~

This is an illustrative code snippet. `Double.isFinite` returns `false` for `NaN` and `+/-Infinity`, but **does not** evaluate the accuracy or business validity of a finite value.

## 15. Common Mistakes

| Claim | Accurate Explanation |
|---|---|
| "`0.1 + 0.2` must equal `0.3` because they are all decimals." | `double` literals are binary approximations; the rounded result may differ by bits. |
| "`double` has no error because it uses 64 bits." | `double` has 53 bits of significand precision; many fractions cannot be represented. |
| "Only division rounds." | `+`, `-`, `*`, and `/` can all round. |
| "Changing the order of addition does not change the result." | Rounding at each step makes floating-point addition non-associative. |
| "`double huge + 1` is always greater than `huge`." | When `huge` is large enough, 1 can be smaller than half a ULP gap. |
| "Dividing `double` by 0 throws `ArithmeticException`." | It usually returns Infinity or NaN; integer division by 0 throws that exception. |
| "Floating-point overflow wraps around like `int`." | The result can be Infinity, not integer wraparound. |
| "`Double.MIN_VALUE` is the smallest negative number." | It is the **smallest positive subnormal number** greater than 0. |
| "`Math.round` uses the same tie-even rule as `+`." | `Math.round` has its own rounding rule; `Math.rint` uses ties-to-even for a `double` result. |
| "Printing `%.2f` turns a number into an exact two-decimal monetary value." | That is only formatting; for exact decimal business logic, use `BigDecimal` properly. |
| "Assigning an `int / int` expression to a `double` variable produces a real quotient." | `int / int` computes integer division first; an operand must be converted before division. |

## 16. Checklist for Solving Floating-Point Problems

1. **What domain does the data belong to?** Counting integers, approximate measured quantities, or exact decimal numbers?
2. **Choose `float` or `double`:** weigh precision, range, and protocol requirements.
3. **Determine the type before each operation:** `int / int` does not automatically become floating-point division; mixing `float` with `double` can carry error from the `float` operand.
4. **Watch for error as operations proceed:** especially adding numbers of widely different magnitudes, subtracting two close numbers, and multiplying/dividing near limits.
5. **Check for special values:** use `Double.isFinite` and `Double.isNaN` when the problem does not allow Infinity/NaN.
6. **Separate representational rounding from business rounding:** `Math.round`, `Math.rint`, and `BigDecimal.setScale` are different tools.
7. **Test boundary cases:** `0.1 + 0.2`, half ULP, `Double.MIN_VALUE / 2`, `Double.MAX_VALUE * 2`, dividing by `+0.0`/`-0.0`, and operations prone to digit loss.
8. **Preserve reproducibility:** document calculation order and units; avoid transforming expressions using real-algebra identities without assessing their impact on rounding.

## 17. Self-Check Exercises

1. Why is `0.1 + 0.2 == 0.3` `false` in `double`?
2. Why can `1e16 + 1.0` still equal `1e16`?
3. What quantity does `Math.ulp(1.0)` represent, and why might adding half this gap to `1.0` leave the result unchanged?
4. Is `(a + b) + c` always equal to `a + (b + c)` for `double`? Give an example.
5. What are the results of `1.0 / 0.0`, `1.0 / -0.0`, and `0.0 / 0.0`? Do they throw `ArithmeticException`?
6. What value does `double x = 7 / 2;` produce? How do you fix it to get `3.5`?
7. Why can `1e308 * 10.0` return Infinity, while `Double.MIN_VALUE / 2.0` returns `0.0`?
8. How does `Math.round(2.5)` differ from `Math.rint(2.5)`?
9. Why does `String.format("%.2f", 0.1 + 0.2)` not solve accuracy for monetary data?
10. If you need to add two decimal values `0.1` and `0.2` accurately for business logic, which representation should you choose?

**Answer Key:** (1) The binary values are rounded differently, so the sum and the literal `0.3` do not share the same bits. (2) The ULP near `1e16` is larger than a change of 1. (3) The unit gap in the last place; ties-to-even can choose `1.0`. (4) No, for example `(1e16 + -1e16) + 1` differs from `1e16 + (-1e16 + 1)`. (5) `Infinity`, `-Infinity`, and `NaN`; floating-point division does not throw that exception. (6) `3.0`, use `7.0 / 2` or cast before dividing. (7) Overflow and underflow relative to the representable value range. (8) `3L` versus `2.0`. (9) It only rounds the display string, without changing the source data. (10) `BigDecimal` initialized from appropriate decimal strings.

**Remember:** Java rounds `float`/`double` results of **addition, subtraction, multiplication, and division** to representable binary values according to IEEE 754 rules. Error can appear **as soon as a literal is written** and continue after **each operation**. Do not confuse that mechanism with rounding to an integer, rounding for display, or exact decimal arithmetic for business logic.