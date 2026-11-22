# Identifying Overflow and Precision Issues Before Writing Arithmetic — Java 17+

An operation that **compiles successfully** does not necessarily produce the **right result**. With Java primitive types, two major risk categories are:

- **Integer overflow**: an operation exceeds the representable range of `int` or `long`, and the result can wrap around to a different number.
- **Floating-point rounding/precision error**: `float` and `double` use finite binary representations, so many decimal numbers cannot be stored exactly.

The most effective prevention is not fixing bugs after they happen, but **estimating the input range, intermediate result range, and required precision before choosing types or writing arithmetic**.

## 1. Pre-Coding Self-Check Table

| Question to answer | Example risk | How to handle |
| --- | --- | --- |
| What are the largest and smallest inputs? | Adding to `Integer.MAX_VALUE` | Check bounds, use `long` or checked arithmetic |
| Could the **intermediate product/sum** exceed the operand type range? | `int * int` then assigning to `long` | Convert to `long` **before multiplying** |
| Does division need the fractional part? | `5 / 2` yields `2` | Choose `5 / 2.0` or cast before dividing |
| Are **exact** decimal values needed? | `0.1 + 0.2` does not exactly equal `0.3` in `double` | Use `BigDecimal` from strings or appropriate integer units |
| Is there a narrowing conversion? | Casting `130` to `byte` yields `-126` | Check range before casting |
| Could floating-point operations exceed range or be undefined? | `Double.MAX_VALUE * 2`, `0.0 / 0.0` | Handle `Infinity` and `NaN` as appropriate |
| Are very large integers converted to `double`? | `2^53 + 1` is not preserved exactly | Keep `long` when unit-level accuracy is needed |

Common limits on Java 17: `byte` from −128 to 127; `short` from −32,768 to 32,767; `int` from −2,147,483,648 to 2,147,483,647; `long` from −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.

## 2. Runnable Java 17+ Program

Save the file **`NumericSafetyDemo.java`**:

~~~java
import java.math.BigDecimal;

public class NumericSafetyDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("wrapped=" + (max + 1));

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact=overflow");
        }

        int unit = 80_000;
        int quantity = 35_000;

        long badProduct = (long) (unit * quantity);
        long goodProduct = (long) unit * quantity;
        System.out.println("badProduct=" + badProduct);
        System.out.println("goodProduct=" + goodProduct);

        try {
            Math.multiplyExact(unit, quantity);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow");
        }

        System.out.println("intDivision=" + (5 / 2));
        System.out.println("realDivision=" + (5 / 2.0));

        double floatingSum = 0.1 + 0.2;
        System.out.println("floatingSum=" + floatingSum);
        System.out.println("floatingEqual=" + (floatingSum == 0.3));

        BigDecimal exactSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimalSum=" + exactSum.toPlainString());
        System.out.println("decimalEqual="
                + (exactSum.compareTo(new BigDecimal("0.3")) == 0));

        long big = 9_007_199_254_740_993L;
        double rounded = big;
        System.out.println("longPrecisionLost=" + ((long) rounded != big));

        System.out.println("floatingOverflow="
                + (Double.MAX_VALUE * 2));
        System.out.println("nan=" + (0.0 / 0.0));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file. Use JDK 17 or later:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericSafetyDemo.java
java NumericSafetyDemo
~~~

**Expected output:**

~~~text
wrapped=-2147483648
addExact=overflow
badProduct=-1494967296
goodProduct=2800000000
multiplyExact=overflow
intDivision=2
realDivision=2.5
floatingSum=0.30000000000000004
floatingEqual=false
decimalSum=0.3
decimalEqual=true
longPrecisionLost=true
floatingOverflow=Infinity
nan=NaN
~~~

## 3. Why Do Integer Results Overflow?

`int` uses 32 signed bits. When adding beyond `Integer.MAX_VALUE`, ordinary `int` operations **do not automatically throw an exception**, and instead keep the result under Java's integer overflow rules:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1; // -2147483648.
~~~

If overflow is a **business error**, detect it instead of accepting the wrapped-around value:

~~~java
int checked = Math.addExact(100, 200); // 300.
int product = Math.multiplyExact(10, 20); // 200.

// Math.addExact(Integer.MAX_VALUE, 1)
// throws ArithmeticException when the result exceeds int range.
~~~

`Math.addExact` and `Math.multiplyExact` have overloads for `int`/`long`, throwing `ArithmeticException` when the result cannot be represented in the respective type. They do not automatically make the result type larger; to hold numbers beyond `long`, consider `BigInteger`.

### Trap: Switching to `long` After Multiplication Is Too Late

~~~java
int unit = 80_000;
int quantity = 35_000;

long wrong = (long) (unit * quantity); // -1494967296.
long right = (long) unit * quantity;   // 2800000000.
~~~

On the `wrong` line, `unit * quantity` is computed in `int` **before the cast**, so it has already overflowed. `(long)` only widens the **wrong value**. The `right` line converts one operand to `long` **before the multiplication**; Java then performs `long` multiplication.

However, `long` also has a limit; if the product can exceed `Long.MAX_VALUE`, you still need checks or the arbitrary-precision integer type `BigInteger`.

## 4. Precision Error Is Not the Same as Overflow

`float` (32 bits) and `double` (64 bits) use IEEE 754 binary representation. Many decimal fractions such as `0.1` and `0.2` **are not represented exactly**. Therefore:

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
~~~

`double` is typically more accurate than `float`, yet it **does not make decimal arithmetic strictly exact**.

| Requirement | How to choose |
| --- | --- |
| Scientific, graphics, and statistical calculations accepting rounding error | `double` normally; `float` when format/performance requires it |
| Currency with fixed smallest unit | Integers representing cents/dong, with range checking |
| Decimal calculations needing exact digits preserved | `BigDecimal`, initialized from `String` |
| Exact counting beyond `long` range | `BigInteger` |
| Approximate equality checks in floating-point domain | Use absolute/relative error per problem specification |

To preserve the decimal value `0.1`, write:

~~~java
BigDecimal amount = new BigDecimal("0.1"); // Exact 0.1.
~~~

Avoid `new BigDecimal(0.1)` if the goal is the exact decimal value 0.1, because that constructor receives the **binary-rounded `double` value**. When comparing numeric values of `BigDecimal`, `compareTo` can be more appropriate than `equals` because `equals` also checks **scale** (`1.0` differs from `1.00` under `equals`).

### Converting Large Integers to `double` Can Also Lose Precision

`double` has 53 bits of significand precision; it cannot hold **every** very large integer accurately:

~~~java
long big = 9_007_199_254_740_993L; // 2^53 + 1.
double rounded = big;
System.out.println((long) rounded != big); // true
~~~

A conversion allowed by Java **does not mean the value stays exact**.

## 5. Traps to Check Before Writing Formulas

**Integer division:** `double result = 5 / 2;` produces `2.0`, not `2.5`, because the division already ran in `int`. Write `5 / 2.0` or `(double) 5 / 2` if the fractional part is needed.

**Narrowing:** `(byte) 130` yields `-126` by keeping the low 8 bits and interpreting them as signed. Compare against the target range before casting.

**Division by zero:** `1 / 0` on integer types throws `ArithmeticException` if executed; conversely, `1.0 / 0.0` yields `Infinity` and `0.0 / 0.0` yields `NaN`. Check denominators and result validity per requirements.

**`NaN` does not equal itself:** `Double.NaN == Double.NaN` returns `false`; use `Double.isNaN(value)` to detect it. Use `Double.isFinite(value)` to check for a finite result if the problem does not accept `NaN` or infinity.

**Do not use one fixed epsilon for every problem:** approximate comparisons must account for scale, absolute/relative error, and `NaN` risks. For data requiring **strict exactness**, change the representation rather than merely increasing the error threshold.

## 6. Arithmetic Design Checklist

Before writing a formula, answer:

1. **Largest and smallest inputs/outputs?** For example, what is maximum quantity times maximum unit price?
2. **Which type computes the intermediates?** Cast before or after the operator? Could `int` addition/multiplication overflow before assigning to `long`?
3. **Integer or floating-point division?** What is the type of each operand?
4. **How much error is acceptable?** If it is money or numeric identifiers, is exact representation required?
5. **Are there narrowing conversions or large integer-to-float conversions?** Which values could be lost?
6. **How are abnormal results handled?** Throw errors with `Math.*Exact`, check denominators, `NaN`, and `Infinity`.
7. **Have boundary values been tested?** Test 0, negative numbers, min/max limits, large products, small fractions, and out-of-range data.

## 7. Short Exercises

**Exercise 1.** Why does `long x = 100_000 * 100_000;` produce a result different from 10,000,000,000? How do you fix it?

*Answer:* Both operands are `int`, so the `int` product overflows before assignment. Use `100_000L * 100_000` or `(long) 100_000 * 100_000`.

**Exercise 2.** Does `Math.addExact(Integer.MAX_VALUE, 1)` return a negative number or throw an error?

*Answer:* It throws `ArithmeticException`; ordinary `+` is what wraps around.

**Exercise 3.** Why does `double x = 7 / 2;` yield `3.0`, whereas `double y = 7 / 2.0;` yields `3.5`?

*Answer:* Operand types determine integer vs. floating-point division **before assignment**.

**Exercise 4.** Compute `0.1 + 0.2` exactly in decimal. Which approach should you use?

*Answer:* `new BigDecimal("0.1").add(new BigDecimal("0.2"))` yields `0.3` accurately.

**Exercise 5.** What do `Double.MAX_VALUE * 2` and `0.0 / 0.0` produce?

*Answer:* `Infinity` and `NaN` respectively, unlike integer overflow.

**Conclusion:** Before writing Java arithmetic, check the **data range**, the **type of each intermediate result**, and the **desired precision**. Use a wider type **before the operation**, check overflow with `Math.*Exact`, and choose `BigDecimal`/`BigInteger` when primitive limits do not meet requirements.
