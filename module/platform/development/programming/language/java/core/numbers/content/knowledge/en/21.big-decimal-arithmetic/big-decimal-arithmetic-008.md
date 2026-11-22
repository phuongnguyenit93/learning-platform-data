# `BigDecimal`: `movePointLeft`, `movePointRight`, and `scaleByPowerOfTen`

The three methods `movePointLeft(int n)`, `movePointRight(int n)`, and `scaleByPowerOfTen(int n)` of `java.math.BigDecimal` all multiply or divide a decimal number by a power of 10 **exactly**, without going through `double` floating-point arithmetic. The important differences lie in **shift direction, how `scale` is preserved, and how the result is represented**. Understanding these points helps when handling currency, decimal unit conversions, and numbers in scientific notation without unintended value changes.

## 1. Foundations: Numeric Value and `scale`

A `BigDecimal` has two core components:

- `unscaledValue()`: integer without a decimal point.
- `scale()`: number of decimal digits according to the rule `value = unscaledValue × 10^(-scale)`. `scale` can be positive, 0, or negative.

| Construction | `toString()` | `unscaledValue()` | `scale()` | Value |
|---|---|---:|---:|---:|
| `new BigDecimal("123.45")` | `123.45` | `12345` | 2 | 123.45 |
| `new BigDecimal("123.4500")` | `123.4500` | `1234500` | 4 | 123.45 |
| `new BigDecimal("123")` | `123` | `123` | 0 | 123 |
| `new BigDecimal("1.23E+3")` | `1.23E+3` | `123` | -1 | 1230 |

Therefore, two `BigDecimal` objects can represent the **same numeric value** yet have different `scale`s. The methods in this lesson do not round numbers; however, they can produce results differing in `scale`, number of zeros, and `toString()`.

## 2. Comparison Table of the Three Methods

With `x` as the initial value, `s = x.scale()`, and `n` as an integer:

| Method | New mathematical value | Result `scale` | Meaning |
|---|---|---|---|
| `x.movePointLeft(n)` | `x × 10^(-n)` | `max(s + n, 0)` | Shifts decimal point left `n` places when `n > 0` |
| `x.movePointRight(n)` | `x × 10^n` | `max(s - n, 0)` | Shifts decimal point right `n` places when `n > 0` |
| `x.scaleByPowerOfTen(n)` | `x × 10^n` | `s - n` | Changes decimal exponent and keeps negative `scale` if needed |

**Sign rules for `n`:**

- `n > 0`: `movePointLeft` divides by `10^n`; `movePointRight` and `scaleByPowerOfTen` multiply by `10^n`.
- `n < 0`: shift direction reverses. For example, `movePointLeft(-2)` is equivalent in value to `movePointRight(2)`; `scaleByPowerOfTen(-2)` divides by 100.
- `n = 0`: numeric value does not change. However, `movePointLeft(0)` and `movePointRight(0)` may still normalize a negative `scale` to 0; `scaleByPowerOfTen(0)` keeps `scale` unchanged.

In particular, **`movePointRight(n)` and `scaleByPowerOfTen(n)` are equal in numeric value, yet not necessarily equal under `equals()`**.

## 3. Standalone Runnable Java 17+ Example

Create file `BigDecimalShiftDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalShiftDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("12.3400");

        show("original", x);
        show("left(2)", x.movePointLeft(2));
        show("right(3)", x.movePointRight(3));
        show("power(3)", x.scaleByPowerOfTen(3));

        // Proves BigDecimal is immutable.
        System.out.println("original after calls: " + x);

        BigDecimal y = new BigDecimal("1.23");
        BigDecimal right = y.movePointRight(3);
        BigDecimal power = y.scaleByPowerOfTen(3);

        show("1.23 right(3)", right);
        show("1.23 power(3)", power);
        System.out.println("compareTo = " + right.compareTo(power));
        System.out.println("equals = " + right.equals(power));
        System.out.println("plain right = " + right.toPlainString());
        System.out.println("plain power = " + power.toPlainString());
    }

    private static void show(String name, BigDecimal value) {
        System.out.println(name + ": " + value + " | scale=" + value.scale());
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalShiftDemo.java
java BigDecimalShiftDemo
~~~

Standard output:

~~~text
original: 12.3400 | scale=4
left(2): 0.123400 | scale=6
right(3): 12340.0 | scale=1
power(3): 12340.0 | scale=1
original after calls: 12.3400
1.23 right(3): 1230 | scale=0
1.23 power(3): 1.23E+3 | scale=-1
compareTo = 0
equals = false
plain right = 1230
plain power = 1230
~~~

Explanation of each change:

1. `12.3400` has `scale = 4`. `movePointLeft(2)` produces `0.123400` with `scale = 6`: shifts the value left by two powers of 10 and keeps trailing fractional zeros.
2. `movePointRight(3)` produces `12340.0` with `scale = 1`; here `scaleByPowerOfTen(3)` also has `scale = 1`, so the representations look identical.
3. `1.23` has `scale = 2`. Shifting right three places yields `s - n = -1`: `movePointRight(3)` normalizes to `1230`, `scale = 0`; `scaleByPowerOfTen(3)` keeps `scale = -1`, printing `1.23E+3`.
4. `compareTo() == 0` because both have value 1230, yet `equals() == false` because `BigDecimal.equals()` also checks `scale`. `toPlainString()` displays both as `1230`, without altering the object itself.
5. Every operation returns a **new BigDecimal**; the original variable `x` remains `12.3400`.

## 4. `movePointLeft(n)`: Shifting Left

`x.movePointLeft(n)` performs multiplication `x × 10^(-n)`. With `n > 0`, the decimal point moves left; if needed, Java pads leading zeros in the significand.

~~~java
BigDecimal a = new BigDecimal("12345.67");
System.out.println(a.movePointLeft(2)); // 123.4567
System.out.println(a.movePointLeft(5)); // 0.1234567
System.out.println(a.movePointLeft(-1)); // 123456.7
~~~

These three lines are an **illustrative snippet placed inside a Java method**, not a complete program; the program in Section 3 is a standalone compilable example.

Note on `scale`: `new BigDecimal("1E+3")` has value 1000 yet `scale = -3`. Calling `movePointLeft(2)` gives value 10 and `scale = 0`, rather than keeping `scale = -1`. This differs from `scaleByPowerOfTen(-2)`, which yields value 10 while keeping `scale = -1`.

Practical example: from the **smallest unit** to a unit 100 times larger, `new BigDecimal("12345").movePointLeft(2)` gives `123.45`. Use a factor of 100 only if the unit system being processed truly has a 100:1 ratio.

## 5. `movePointRight(n)`: Shifting Right

`x.movePointRight(n)` performs `x × 10^n`. With `n > 0`, the decimal point moves right; if no digits remain after the decimal point, the result has `scale = 0` and zeros are appended to the integer part when needed.

~~~java
BigDecimal a = new BigDecimal("12.345");
System.out.println(a.movePointRight(2));  // 1234.5
System.out.println(a.movePointRight(4));  // 123450
System.out.println(a.movePointRight(-2)); // 0.12345
~~~

When converting currency to minor units, **shifting the decimal point does not guarantee an integer**. For example, `12.345 × 100 = 1234.5`; if the smallest unit must be an integer, you must check or apply an explicit rounding rule rather than using `intValue()` to silently drop the fraction.

`movePointLeft` and `movePointRight` are symmetric **in numeric value**. Do not assume the reverse shift reproduces the exact original `scale`, especially when negative `scale` is involved or when a step normalized scale to 0.

## 6. `scaleByPowerOfTen(n)`: Adjusting the Power of 10

`x.scaleByPowerOfTen(n)` returns `x × 10^n` by choosing `new scale = old scale - n`, even when the result is negative. This is particularly natural when data is in `1.23E+3` form or when manipulating large powers of 10.

~~~java
BigDecimal a = new BigDecimal("1.23");
System.out.println(a.scaleByPowerOfTen(3));  // 1.23E+3
System.out.println(a.scaleByPowerOfTen(-2)); // 0.0123
System.out.println(a.scaleByPowerOfTen(0));  // 1.23
~~~

For instance, `new BigDecimal("5").scaleByPowerOfTen(3)` gives value 5000 in `5E+3` form with `scale = -3`, while `movePointRight(3)` gives `5000` with `scale = 0`. Do not interpret the letter `E` as an error; it is simply **scientific notation for representing the numeric value**.

Example with initial data already having a negative `scale`:

~~~java
BigDecimal a = new BigDecimal("1E+3");
System.out.println(a.movePointLeft(0));      // 1000
System.out.println(a.scaleByPowerOfTen(0));  // 1E+3
System.out.println(a.movePointLeft(2));      // 10
System.out.println(a.scaleByPowerOfTen(-2)); // 1E+1
~~~

Even though `movePointLeft(0)` and `scaleByPowerOfTen(0)` keep the same value 1000, they represent it differently because of how negative `scale` is handled.

## 7. Distinguishing from `setScale`, `multiply`, and Rounding

Similarly named APIs serve different purposes:

| Operation | Changes **numeric value**? | Purpose |
|---|---|---|
| `movePointLeft(2)` | Yes: divides by 100 | Shifts decimal point left |
| `movePointRight(2)` | Yes: multiplies by 100 | Shifts decimal point right |
| `scaleByPowerOfTen(2)` | Yes: multiplies by 100 | Multiplies by power of 10, keeping mathematical `scale` |
| `setScale(2)` | No, if representable exactly | Sets two decimal places; may throw `ArithmeticException` if rounding is required |
| `setScale(2, RoundingMode.HALF_UP)` | Possibly, due to rounding | Enforces representational precision and rounding policy |
| `multiply(new BigDecimal("100"))` | Yes: multiplies by 100 | General decimal multiplication; `scale` is sum of both operands' `scale`s |

For example, `new BigDecimal("1.234").setScale(2, RoundingMode.HALF_UP)` yields `1.23`, whereas `movePointRight(2)` yields `123.4`. The two operations solve completely different needs.

`scaleByPowerOfTen` and the two `movePoint...` methods do not need `MathContext` or `RoundingMode` because multiplying/dividing by powers of 10 is exact within `BigDecimal`'s model, provided `scale` and representational resources remain valid. If a problem requires rounding to a fixed number of digits, perform a separate `setScale(..., RoundingMode...)` step and choose the rounding rule per business logic.

Also do not assume `multiply(new BigDecimal("100"))` has the same `scale` as `movePointRight(2)`: for example, `new BigDecimal("1.23").multiply(new BigDecimal("100"))` creates `123.00` (`scale = 2`), while `movePointRight(2)` creates `123` (`scale = 0`).

## 8. Practical Scenario: Converting Minor Units Safely

Suppose a system stores money in the **smallest integer unit**, with the convention that one major unit equals 100 minor units. Reading uses `movePointLeft(2)`. Writing back must confirm the number of minor units is an integer.

Standalone file `MinorUnitDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class MinorUnitDemo {
    public static void main(String[] args) {
        BigDecimal minorUnits = new BigDecimal("12345");
        BigDecimal majorUnits = minorUnits.movePointLeft(2);
        BigInteger exactMinorUnits =
                majorUnits.movePointRight(2).toBigIntegerExact();

        System.out.println("major = " + majorUnits);
        System.out.println("minor = " + exactMinorUnits);

        BigDecimal invalidMajor = new BigDecimal("12.345");
        try {
            invalidMajor.movePointRight(2).toBigIntegerExact();
            System.out.println("unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("fractional minor unit rejected");
        }
    }
}
~~~

Run:

~~~bash
javac MinorUnitDemo.java
java MinorUnitDemo
~~~

Result:

~~~text
major = 123.45
minor = 12345
fractional minor unit rejected
~~~

Points to remember:

- `toBigIntegerExact()` checks integrality explicitly; unlike `toBigInteger()`, which discards any fractional part.
- If business rules **allow** entering more than two decimal digits, you must define rounding or rejection before saving. `movePointRight(2)` itself does not round.
- Do not assume every currency or unit of measure has a 100:1 ratio. The conversion factor must come from the system's specification.
- If you also need to bound within `long`'s range, you can use `longValueExact()` instead of ordinary casting to detect both fractional parts and range overflow.

## 9. Display, Comparison, and External Data

**`toString()` and `toPlainString()`:** `toString()` may choose scientific notation like `1.23E+3`. `toPlainString()` displays a form without exponents, such as `1230`. This is purely string formatting; do not use `toPlainString()` to infer the original `scale` or normalize comparison logic.

**`compareTo()` and `equals()`:** `compareTo()` compares by numeric value; `equals()` requires both value and `scale` to match. For example, `new BigDecimal("1230")` and `new BigDecimal("1.23E+3")` compare as 0 under `compareTo()` yet are not `equals()`. In a `HashSet` or `HashMap` key, `equals()/hashCode()` rules decide key collisions. If an application needs numerically equivalent values treated as the same key, establish a uniform canonicalization rule beforehand; `stripTrailingZeros()` can turn `scale` negative and should not be used indiscriminately when `scale` carries business meaning.

**Accurate initialization:** prefer `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` over `new BigDecimal(0.1)`. The `double` constructor records the exact binary value of the argument and can produce unexpectedly long decimal strings. During unit conversions, this initialization mistake often causes confusion with how shifting methods work.

**Immutability:** `BigDecimal` is immutable. The statement `x.movePointLeft(2);` without keeping the return value does not alter `x`. Assign `BigDecimal smaller = x.movePointLeft(2);` or reassign `x = x.movePointLeft(2);` when you truly want to update the variable.

## 10. Common Mistakes and Limits to Consider

1. **Confusing multiply/divide direction:** `movePointLeft(3)` divides by 1000, whereas `movePointRight(3)` and `scaleByPowerOfTen(3)` multiply by 1000. Test with a simple value like 12.34 before bulk-converting data.
2. **Confusing `scale` with numeric value:** `1.23E+3` and `1230` have the same value, yet may differ in `equals()` and display form.
3. **Implicitly assuming an integer result:** `movePointRight(2)` on `12.345` is `1234.5`, not 1235 or 1234.
4. **Using `setScale` instead of multiplication/division:** `setScale` controls digits after the decimal point; it cannot replace multiplying by `10^n`.
5. **Ignoring negative or zero `n`:** negative `n` reverses direction; `n = 0` can still cause `movePoint...` to adjust a negative `scale` to 0.
6. **Using overly large exponents:** `BigDecimal`'s `scale` is an `int`. Requesting an out-of-range `scale`, or creating an overly large string representation, can cause `ArithmeticException` or resource issues. Validate input powers of 10 and avoid `toPlainString()` for numbers with extreme exponents.
7. **Storing/serializing without a convention:** if the system needs exactly two decimal digits, explicitly define digit count, rounding rules, and output format; do not infer those conventions from calling `movePointRight` or `scaleByPowerOfTen`.

## 11. Self-Check

Predict the value, `scale`, and `toString()` representation for the following cases:

~~~java
BigDecimal a = new BigDecimal("0.0100");
BigDecimal b = new BigDecimal("5");
BigDecimal c = new BigDecimal("1E+3");

BigDecimal q1 = a.movePointRight(2);
BigDecimal q2 = b.movePointRight(3);
BigDecimal q3 = b.scaleByPowerOfTen(3);
BigDecimal q4 = c.movePointLeft(0);
BigDecimal q5 = c.scaleByPowerOfTen(0);
~~~

Answers:

| Variable | Numeric value | `toString()` | `scale()` |
|---|---:|---|---:|
| `q1` | 1 | `1.00` | 2 |
| `q2` | 5000 | `5000` | 0 |
| `q3` | 5000 | `5E+3` | -3 |
| `q4` | 1000 | `1000` | 0 |
| `q5` | 1000 | `1E+3` | -3 |

Two key questions to explain to yourself: Why is `q2.compareTo(q3) == 0` yet `q2.equals(q3) == false`? Why do `q4` and `q5` have the same value yet different `toString()` output? Both stem from how `scale` is preserved or normalized.

When choosing a method, start from the **mathematical rule** (dividing or multiplying by `10^n`), then determine whether **`scale` carries business meaning or affects output, comparisons, and storage**. Shifting the decimal point via `movePointLeft`/`movePointRight` is convenient for unit conversions; `scaleByPowerOfTen` fits when you want to work explicitly with powers of 10 and preserve potentially negative `scale`.