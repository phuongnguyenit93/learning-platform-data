# Exact Arithmetic and `BigDecimal` When Primitive Types Do Not Meet Requirements — Java 17+

Basic integer types (`int`, `long`) and floating-point types (`float`, `double`) are very useful, yet have limitations:

- **`int` and `long` have finite value ranges.** Ordinary integer addition, subtraction, or multiplication can **overflow** and return a mathematically wrong value without throwing an exception.
- **`float` and `double` represent real numbers in binary.** Some decimal values such as `0.1` cannot be represented exactly; they can also round, underflow, or overflow.
- When a system needs **integer overflow detection**, use `Math.*Exact()` methods; when it needs **very large integers**, use `BigInteger`; when it needs **decimal arithmetic with explicitly managed precision**, use `BigDecimal`.

These are three solutions for **different needs**. `Math.addExact` does not widen the `int` range; `BigDecimal` does not automatically decide how to round for every problem.

## 1. Quick Selection Table

| Problem | Java 17+ Solution | Meaning |
| --- | --- | --- |
| `int` add/subtract/multiply may overflow | `Math.addExact`, `subtractExact`, `multiplyExact` | Throws `ArithmeticException` when result is out of range |
| `long` add/subtract/multiply may overflow | `long` overloads of the methods above | Still uses `long`, but checks for overflow |
| Increment/decrement/negate at boundary | `incrementExact`, `decrementExact`, `negateExact` | Detects out-of-range result |
| Safely convert `long` to `int` | `Math.toIntExact(long)` | Does not silently truncate high bits |
| Integers larger than `long` | `java.math.BigInteger` | Integer length is not limited by 64 bits, though still subject to memory |
| Money, taxes, decimal quantities | `java.math.BigDecimal` | Decimal arithmetic as `unscaled value × 10^(-scale)` |
| Non-terminating decimal division | `BigDecimal.divide` with `scale`/`RoundingMode` or `MathContext` | Specifies precision and rounding |
| Approximate real numbers, scientific measurement | `double`, with an error policy | Usually suitable when binary precision is acceptable |

**Rule:** choose numeric types based on **value range and business precision requirements**, not merely syntactic convenience.

## 2. `exact` Integer Arithmetic: Detecting Overflow

Java does not throw an exception by default on integer overflow:

~~~java
int wrapped = Integer.MAX_VALUE + 1;
System.out.println(wrapped); // -2147483648.
~~~

The mathematical value of `2_147_483_647 + 1` is `2_147_483_648`, outside the `int` range; ordinary integer arithmetic returns an overflowed result in 32-bit representation.

To **require the calculation to stay within range**, use:

~~~java
int total = Math.addExact(100, 250); // 350.

// Math.addExact(Integer.MAX_VALUE, 1)
// -> throws ArithmeticException at runtime.
~~~

| Method | Example | Result if Out of Range |
| --- | --- | --- |
| `Math.addExact(a, b)` | `Math.addExact(100, 250)` → `350` | `ArithmeticException` |
| `Math.subtractExact(a, b)` | `Math.subtractExact(10, 15)` → `-5` | `ArithmeticException` |
| `Math.multiplyExact(a, b)` | `Math.multiplyExact(100, 200)` → `20000` | `ArithmeticException` |
| `Math.incrementExact(a)` | `Math.incrementExact(5)` → `6` | `ArithmeticException` |
| `Math.decrementExact(a)` | `Math.decrementExact(5)` → `4` | `ArithmeticException` |
| `Math.negateExact(a)` | `Math.negateExact(-5)` → `5` | `ArithmeticException` |
| `Math.toIntExact(x)` | `Math.toIntExact(42L)` → `42` | `ArithmeticException` if it does not fit in `int` |

These methods **do not return arbitrary-width numbers**. `Math.multiplyExact(int, int)` still returns `int`; to hold a product that can exceed `int`, use appropriate `long` operands and type, or `BigInteger`.

**Watch the order:** `Math.addExact(a * b, c)` does not detect overflow that already happened **inside `a * b`**. Check the multiplication itself with `Math.multiplyExact(a, b)` before passing the result into addition.

`Math.*Exact` does not turn `double` floating-point arithmetic into exact decimal arithmetic; they are for integers and integer conversions per their supported overloads.

## 3. Standalone Runnable Java 17+ Program

Save a UTF-8 file named **`ExactAndBigDecimalDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class ExactAndBigDecimalDemo {
    public static void main(String[] args) {
        System.out.println("== exact integers ==");
        System.out.println("wrappedInt=" + (Integer.MAX_VALUE + 1));
        System.out.println("safeAdd=" + Math.addExact(100, 250));
        System.out.println("safeLongMultiply="
                + Math.multiplyExact(50_000L, 50_000L));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addOverflow=ArithmeticException");
        }

        try {
            Math.multiplyExact(50_000, 50_000);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyOverflow=ArithmeticException");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("subtractOverflow=ArithmeticException");
        }

        try {
            Math.toIntExact(3_000_000_000L);
        } catch (ArithmeticException ex) {
            System.out.println("narrowingOverflow=ArithmeticException");
        }

        System.out.println("== big integers ==");
        BigInteger left = new BigInteger("3000000000");
        BigInteger right = new BigInteger("4000000000");
        BigInteger product = left.multiply(right);
        System.out.println("bigProduct=" + product);
        System.out.println("bigProductPlusOne="
                + product.add(BigInteger.ONE));

        System.out.println("== exact decimals ==");
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("decimalSum=" + a.add(b).toPlainString());
        System.out.println("binaryDoubleSum=" + (0.1 + 0.2));

        BigDecimal price = new BigDecimal("19.99");
        BigDecimal quantity = new BigDecimal("3");
        System.out.println("lineTotal="
                + price.multiply(quantity).toPlainString());

        BigDecimal amount = new BigDecimal("12.50");
        amount.add(new BigDecimal("0.50"));
        System.out.println("unchangedAmount=" + amount.toPlainString());
        amount = amount.add(new BigDecimal("0.50"));
        System.out.println("updatedAmount=" + amount.toPlainString());

        System.out.println("== division and rounding ==");
        System.out.println("oneEighth="
                + BigDecimal.ONE.divide(new BigDecimal("8")));

        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("nonTerminating=ArithmeticException");
        }

        System.out.println("oneThirdRounded="
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("halfUp="
                + new BigDecimal("10.005").setScale(
                        2, RoundingMode.HALF_UP));
        System.out.println("halfEvenDown="
                + new BigDecimal("2.345").setScale(
                        2, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenUp="
                + new BigDecimal("2.355").setScale(
                        2, RoundingMode.HALF_EVEN));

        System.out.println("== construction and equality ==");
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal fromDouble = new BigDecimal(0.1);
        System.out.println("doubleConstructorEquals="
                + fromText.equals(fromDouble));
        System.out.println("valueOfEquals="
                + fromText.equals(BigDecimal.valueOf(0.1)));

        BigDecimal twoOneDecimal = new BigDecimal("2.0");
        BigDecimal twoTwoDecimals = new BigDecimal("2.00");
        System.out.println("scaleSensitiveEquals="
                + twoOneDecimal.equals(twoTwoDecimals));
        System.out.println("numericCompare="
                + twoOneDecimal.compareTo(twoTwoDecimals));
        System.out.println("stripZeros="
                + twoTwoDecimals.stripTrailingZeros().toPlainString());

        System.out.println("intExact="
                + new BigDecimal("123.00").intValueExact());
        try {
            new BigDecimal("123.5").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("fractionToInt=ArithmeticException");
        }
    }
}
~~~

Using **JDK 17 or later**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ExactAndBigDecimalDemo.java
java ExactAndBigDecimalDemo
~~~

**Exact expected stdout** of `java ExactAndBigDecimalDemo` alone:

~~~text
== exact integers ==
wrappedInt=-2147483648
safeAdd=350
safeLongMultiply=2500000000
addOverflow=ArithmeticException
multiplyOverflow=ArithmeticException
subtractOverflow=ArithmeticException
narrowingOverflow=ArithmeticException
== big integers ==
bigProduct=12000000000000000000
bigProductPlusOne=12000000000000000001
== exact decimals ==
decimalSum=0.3
binaryDoubleSum=0.30000000000000004
lineTotal=59.97
unchangedAmount=12.50
updatedAmount=13.00
== division and rounding ==
oneEighth=0.125
nonTerminating=ArithmeticException
oneThirdRounded=0.33
halfUp=10.01
halfEvenDown=2.34
halfEvenUp=2.36
== construction and equality ==
doubleConstructorEquals=false
valueOfEquals=true
scaleSensitiveEquals=false
numericCompare=0
stripZeros=2
intExact=123
fractionToInt=ArithmeticException
~~~

The output of `java -version` and `javac -version` depends on the installed JDK version on the machine, so it is not included in the fixed stdout block.

## 4. `BigInteger` When `long` Is Not Large Enough

`BigInteger` in `java.math` stores arbitrary-precision integers (practically bounded by machine resources and implementation limits). It is appropriate when results exceed `Long.MAX_VALUE`:

~~~java
BigInteger a = new BigInteger("3000000000");
BigInteger b = new BigInteger("4000000000");
BigInteger result = a.multiply(b);
// result = 12000000000000000000.
~~~

| Type | Illustrative Operation | Notes |
| --- | --- | --- |
| `int` | `int c = a + b;` | Overflows if value is out of range |
| `long` | `long c = a + b;` | Wider range than `int`, yet still finite |
| `BigInteger` | `a.add(b)`, `a.multiply(b)` | Methods return a **new object** holding the new value |

`BigInteger` is **immutable**: `a.add(b)` does not mutate `a`; to update a variable, write `a = a.add(b)`. It does not have direct addition via the `+` operator between two `BigInteger` objects.

Do not think `BigInteger` replaces `BigDecimal` for all data: `BigInteger` is an **integer**, and stores no fractional part.

## 5. `BigDecimal`: Scaled Decimal, Not an Infinite Real-Number Type

`BigDecimal` represents a number using an **unscaled integer** and a **scale**:

~~~text
Value = unscaledValue × 10^(-scale)

"19.99" -> unscaledValue = 1999, scale = 2
"2.00"  -> unscaledValue = 200,  scale = 2
~~~

Given decimal inputs represented as strings, `BigDecimal` addition, subtraction, and multiplication compute **exact base-10 arithmetic** without `double`-style binary error:

~~~java
BigDecimal x = new BigDecimal("0.1");
BigDecimal y = new BigDecimal("0.2");
BigDecimal sum = x.add(y); // 0.3.
~~~

### Creating `BigDecimal` Properly

| Construction | Recommendation | Reason |
| --- | --- | --- |
| `new BigDecimal("0.1")` | **Prefer** when the source is decimal data | Represents exact 0.1 |
| `BigDecimal.valueOf(0.1)` | Usually suitable when you already have a `double` | Uses the decimal representation of `Double.toString` |
| `new BigDecimal(0.1)` | **Avoid if decimal 0.1 is intended** | Converts the exact existing approximate binary value |
| `BigDecimal.valueOf(100L)` | Suitable for integers | Creates exact value from `long` |

`new BigDecimal(0.1)` does not round to decimal `0.1`; it represents the exact `double` value currently held. That is why the demo prints `doubleConstructorEquals=false` when compared to `new BigDecimal("0.1")`.

**Error that occurred before creating `BigDecimal` is not automatically fixed.** When calculating money, read decimal amounts directly from strings or exact data types, rather than computing in `double` and converting afterward.

## 6. Division May Require Rounding Rules

Not every quotient of two decimal numbers has a **finite** decimal representation:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: 1/3 has infinite decimal digits.
BigDecimal rounded = one.divide(three, 2, RoundingMode.HALF_UP);
// 0.33.
~~~

| Division Call | Behavior |
| --- | --- |
| `one.divide(new BigDecimal("8"))` | Exact, returns `0.125` |
| `one.divide(new BigDecimal("3"))` | Throws `ArithmeticException` because the decimal expansion does not terminate |
| `one.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)` | Rounds to two decimal places after the point, returns `0.33` |
| `one.divide(divisor, new MathContext(10, RoundingMode.HALF_EVEN))` | Limits to **10 significant digits**, different from scale = 10 |

**`scale` and `precision` are not the same**:

- `scale = 2` denotes **two digits after the decimal point** (for positive scale).
- `MathContext(10, ...)` specifies **10 significant digits** for the operation.

`RoundingMode.HALF_UP` rounds exact halves away from 0. `RoundingMode.HALF_EVEN` chooses the even final digit when exactly halfway between two results, useful in certain accounting rules, though **you must not arbitrarily assume it is a business requirement for every system**.

### Intentional Rounding

~~~java
BigDecimal price = new BigDecimal("10.005");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
// 10.01.
~~~

If using `RoundingMode.UNNECESSARY`, the operation throws `ArithmeticException` when rounding is required and cannot be performed exactly. This mechanism is useful when you want to **prove a result is exact at a specified scale**.

## 7. Comparing `BigDecimal`: `equals` Differs from `compareTo`

~~~java
BigDecimal first = new BigDecimal("2.0");
BigDecimal second = new BigDecimal("2.00");

System.out.println(first.equals(second)); // false.
System.out.println(first.compareTo(second) == 0); // true.
~~~

- `equals` checks **both value and scale**; `2.0` and `2.00` have different scales so they are not `equals`.
- `compareTo` compares **numeric value**; both are numerically equal, so it returns 0.

If your goal is checking **equivalent monetary amounts**, typically use `compareTo(...) == 0` after defining a scale policy. If data structures use `HashSet` or `HashMap`, they rely on `equals` and `hashCode`, so treating `2.0` and `2.00` as distinct values can affect behavior. Do not mix the two notions of equality without specifying rules clearly.

`stripTrailingZeros()` can produce a `BigDecimal` with a different scale yet the same numeric value. When a stable text representation is needed, `toPlainString()` avoids scientific notation that `toString()` may choose.

## 8. Choosing the Right Tool for the Limit

An integer that is **too large** and a decimal that **must be exact** are two different problems. Combining appropriately:

~~~java
// Only need overflow detection while still wanting int:
int count = Math.addExact(currentCount, addedCount);

// If the integer may exceed long:
BigInteger idSequence = new BigInteger("999999999999999999999");

// If monetary amount needs decimal arithmetic:
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal total = unitPrice.multiply(new BigDecimal("3"));
~~~

This snippet is a conceptual example requiring `currentCount`/`addedCount` to be declared in actual scope; the runnable program in section 3 declares all variables itself.

**Do not treat any type as "infinite" in resources.** `BigInteger`/`BigDecimal` can consume more memory and CPU than primitives; nor do they automatically solve input validation, currency units, rounding policies, overflow when converting back to primitives, or performance requirements.

When converting a `BigDecimal` with a fractional part to `int`, `intValue()` can lose information. If you require **no loss of fractional part** and no out-of-range overflow, use `intValueExact()` (or `longValueExact()`). The demo shows `"123.00"` converts to 123, while `"123.5"` throws `ArithmeticException`.

## 9. Common Misconceptions

| Misconception | Correct Fact |
| --- | --- |
| "`Math.addExact` automatically widens `int` to `long`." | No; it **throws an error** if out of range |
| "`Math.addExact(a * b, c)` detects every overflow." | No; `a * b` can overflow beforehand |
| "`long` is enough for all practical integers." | No; `BigInteger` is used when exceeding `long` range is needed |
| "`BigDecimal` uses the `+` operator like primitives." | No; use `add`, `subtract`, `multiply`, `divide` |
| "`new BigDecimal(0.1)` equals exact decimal 0.1." | No; it reflects the exact approximate `double` value |
| "`BigDecimal.divide` always returns a result." | Divisions like 1/3 require rounding rules |
| "`scale` and `precision` are the same thing." | No; one is decimal-place position, the other is significant digit count |
| "`equals` only looks at the numeric value of `BigDecimal`." | No; `equals` also considers scale |
| "Converting `BigDecimal` to `int` is always safe." | Can lose fractional part / overflow range; use `intValueExact` when needed |
| "`BigDecimal` automatically enforces all financial rules." | No; you must specify rounding, scale, units, and input constraints |

## 10. Self-Check Exercises

1. What value does `Math.addExact(Integer.MAX_VALUE, 1)` return?  
   *Answer:* It does not return an `int`; it throws `ArithmeticException`.
2. To compute the exact product of two integers that may exceed `long`, which type should you choose?  
   *Answer:* `BigInteger`.
3. Why does `new BigDecimal("0.1").add(new BigDecimal("0.2"))` give 0.3 whereas `0.1 + 0.2` equals 0.30000000000000004?  
   *Answer:* A string passed to `BigDecimal` specifies an exact decimal value; `double` uses an approximate binary representation.
4. What does `BigDecimal.ONE.divide(new BigDecimal("3"))` do?  
   *Answer:* Throws `ArithmeticException` if no suitable rounding/precision rule is provided for the non-terminating quotient.
5. What do `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` and `compareTo` evaluate to, respectively?  
   *Answer:* `false` and `0`.
6. What is `new BigDecimal("10.005").setScale(2, RoundingMode.HALF_UP)`?  
   *Answer:* `10.01`.
7. What does `new BigDecimal("123.5").intValueExact()` return?  
   *Answer:* Throws `ArithmeticException` because there is a fractional part.

## Checklist

- [ ] Know that primitive `int`/`long` can overflow silently.
- [ ] Use `Math.*Exact` when integer operations must **fail immediately on overflow**.
- [ ] Use `BigInteger` for integers exceeding primitive ranges.
- [ ] Construct `BigDecimal` from exact decimal strings when source data is decimal.
- [ ] Understand that `BigDecimal` is immutable and uses methods instead of arithmetic operators.
- [ ] Specify `scale`, `precision`, and `RoundingMode` before required divisions/roundings.
- [ ] Distinguish `equals` (value and scale) from `compareTo` (numeric value).
- [ ] Use `intValueExact`/`longValueExact` when converting back to primitives without data loss.

**Conclusion:** When `int`/`long` do not meet requirements, decide clearly between **overflow detection** (`Math.*Exact`) and **widening the integer domain** (`BigInteger`). When `double` is unsuitable for decimal calculations, use `BigDecimal` with **exact data sources and an explicitly designed rounding policy**.