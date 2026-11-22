# BigDecimal.valueOf and the Constants ZERO, ONE, TEN in Java

`java.math.BigDecimal` is Java's arbitrary-precision decimal number type. When creating a `BigDecimal` value, two questions must be answered separately: **what meaning the input carries** (an integer, a decimal with scale, or a binary `double` floating-point number) and **which decimal representation needs to be preserved**. The `valueOf` factories along with the three constants `ZERO`, `ONE`, and `TEN` are the foundational tools for that.

Example:

```java
import java.math.BigDecimal;

BigDecimal a = BigDecimal.valueOf(42L);       // 42, scale 0
BigDecimal b = BigDecimal.valueOf(12345L, 2); // 123.45, scale 2
BigDecimal c = BigDecimal.valueOf(0.1);       // 0.1, scale 1
BigDecimal zero = BigDecimal.ZERO;            // 0, scale 0
BigDecimal one = BigDecimal.ONE;              // 1, scale 0
BigDecimal ten = BigDecimal.TEN;              // 10, scale 0
```

This is an **illustrative code snippet** to be placed inside a method. Important points: `valueOf(double)` **differs** from `new BigDecimal(double)`; the constants have **scale equal to 0**; and two numbers with the same value but different scales can have `compareTo` equal to 0 while `equals` returns false.

## 1. The Decimal Number Model of BigDecimal

A `BigDecimal` is interpreted by the formula:

```text
Value = unscaledValue × 10^(-scale)
```

`unscaledValue()` is a signed `BigInteger`. `scale()` is an `int` that can be positive, zero, or negative. `precision()` is the number of significant digits of the unscaled value; **precision is not scale**.

| Unscaled value | Scale | Numeric value |
| ---: | ---: | ---: |
| 12345 | 0 | 12345 |
| 12345 | 2 | 123.45 |
| 12345 | 4 | 1.2345 |
| 12345 | -2 | 1234500 |
| 10 | 1 | 1.0 |
| 1 | 0 | 1 |
| 0 | 2 | 0.00 |

Two objects can have the same arithmetic value while differing in representation: `1` and `1.0` have equal value, yet the pair `(unscaled=1, scale=0)` differs from `(unscaled=10, scale=1)`. Therefore, when learning the factories and constants, always observe **both value and scale**.

## 2. The valueOf Overloads

| API | Parameter types | Main behavior |
| --- | --- | --- |
| `BigDecimal.valueOf(long val)` | `long` | Creates a decimal number from an exact integer, scale 0 |
| `BigDecimal.valueOf(long unscaledVal, int scale)` | `long`, `int` | Creates an unscaled/scale pair per the decimal formula |
| `BigDecimal.valueOf(double val)` | `double` | Creates from the round-trip decimal representation of `Double.toString(val)` |

Choose the overload according to **the kind of information you actually have**. If the source is a large integer stored in a `long`, avoid converting to `double` first. If the source is an integer even larger than `long`, use the constructor from `BigInteger` or a numeric string, rather than narrowing to a primitive.

A factory is a `static` method. It does not "magically" round all data; it creates an object from the **passed-in value** according to the semantics of each overload.

## 3. valueOf(long): Exact Integer, Scale Equal to 0

```java
BigDecimal count = BigDecimal.valueOf(12345L);
System.out.println(count);                 // 12345
System.out.println(count.unscaledValue()); // 12345
System.out.println(count.scale());         // 0
```

Every `long` value can be represented exactly by `BigDecimal`. Therefore, this factory is well-suited for integer fields, counters, or already-determined smallest-unit values.

**Do not go through double:**

```java
long large = 9_007_199_254_740_993L; // 2^53 + 1.
BigDecimal exact = BigDecimal.valueOf(large); // Exact 9007199254740993.
BigDecimal lossy = BigDecimal.valueOf((double) large);
// Double already rounded to 9007199254740992 before valueOf was called.
```

`double` has 53 effective bits of significand, so it cannot represent every integer larger than `2^53`. If a unit was already lost during the cast step, `BigDecimal` cannot recover that bit of information.

## 4. valueOf(long, int): Constructing from Unscaled Value and Scale

```java
BigDecimal dollars = BigDecimal.valueOf(12345L, 2);
System.out.println(dollars); // 123.45
```

The two arguments are **not "integer part" and "fractional part"**. The first argument is the unscaled integer, and the second argument is the scale. Examples:

| Call | Mathematical value | `toString()` result on Java 17 |
| --- | ---: | --- |
| `valueOf(12345L,0)` | 12345 | 12345 |
| `valueOf(12345L,2)` | 123.45 | 123.45 |
| `valueOf(12345L,-2)` | 1234500 | 1.2345E+6 |
| `valueOf(0L,2)` | 0 | 0.00 |

**Negative scale is valid**: unscaled 12345, scale -2 means multiplying by `10^2`. Thus `toString()` may use exponent form. When a representation without exponents is required, use `toPlainString()`.

A common use case is monetary amounts stored in the smallest unit, e.g., 125 cents and a decimal scale-2 rule:

```java
long cents = 125;
BigDecimal amount = BigDecimal.valueOf(cents, 2); // 1.25.
```

The unit and scale must be documented in the data contract. If the source is already denominated in main units, applying scale 2 again will unintentionally divide the value by 100.

## 5. How Is valueOf(double) Created?

With `BigDecimal.valueOf(double)`, Java uses the **round-trip decimal string representation** of `double` (equivalent to converting via `Double.toString` and then constructing BigDecimal). Example:

```java
BigDecimal value = BigDecimal.valueOf(0.1);
System.out.println(value.toPlainString()); // 0.1
System.out.println(value.scale());         // 1
```

A `double` stores 0.1 approximately in binary, yet `Double.toString(0.1)` returns `"0.1"` because that is the short decimal string suitable for parsing back to the exact same double value. `valueOf(0.1)` creates **decimal 0.1 with scale 1** from it.

This does not mean earlier calculations done in `double` get fixed to become exact:

```java
double computed = 0.1 + 0.2;
System.out.println(computed);                   // 0.30000000000000004
System.out.println(BigDecimal.valueOf(computed)); // 0.30000000000000004
```

If business logic requires exact decimal addition, create BigDecimal from the original decimal **before adding**, not after double addition has already introduced discrepancy.

## 6. valueOf(0.1) Differs from new BigDecimal(0.1)

This is one of the most common points of confusion:

```java
BigDecimal a = BigDecimal.valueOf(0.1);
BigDecimal b = new BigDecimal(0.1);
BigDecimal c = new BigDecimal("0.1");
```

| Expression | Displayed value |
| --- | --- |
| `BigDecimal.valueOf(0.1)` | `0.1` |
| `new BigDecimal("0.1")` | `0.1` |
| `new BigDecimal(0.1)` | `0.1000000000000000055511151231257827021181583404541015625` |

`new BigDecimal(double)` stores the **exact true value of the existing double binary pattern**, expressing it as an exact decimal number. The binary value of the literal `0.1` is slightly larger than exact 1/10, so the long string appears.

`valueOf(0.1)` uses the round-trip decimal string `"0.1"`, whereas `new BigDecimal("0.1")` comes straight from the characters written by the author. Both produce exact decimal 0.1 in the example, yet the data source and API semantics remain different.

**Practical choice:** if the source is a monetary string, decimal measurement, or JSON decimal data requiring exactness, read from the decimal string with `new BigDecimal(text)`; if the source is `long`, use `valueOf(long)`; if you must accept `double`, `valueOf(double)` typically produces a more explainable decimal result than the direct double constructor, though remember double is already an approximate input.

## 7. The Three Constants ZERO, ONE, TEN

Three built-in constants:

```java
BigDecimal zero = BigDecimal.ZERO;
BigDecimal one = BigDecimal.ONE;
BigDecimal ten = BigDecimal.TEN;
```

| Constant | `unscaledValue()` | `scale()` | Value |
| --- | ---: | ---: | ---: |
| `BigDecimal.ZERO` | 0 | 0 | 0 |
| `BigDecimal.ONE` | 1 | 0 | 1 |
| `BigDecimal.TEN` | 10 | 0 | 10 |

They are very useful as initial values, increment-by-one terms, or multipliers by 10. There is no need to write `new BigDecimal("0")` repeatedly.

```java
BigDecimal total = BigDecimal.ZERO;
total = total.add(BigDecimal.ONE); // 1.
total = total.multiply(BigDecimal.TEN); // 10.
```

**All three constants have scale 0**, and do not automatically carry a currency scale of 2. If you want to represent zero as `0.00`, create a scale-2 value from `ZERO.setScale(2)` or `valueOf(0L,2)`.

## 8. A Constant Having Value 0 Does Not Mean All Zero BigDecimals Are Equal Under equals

Consider:

```java
BigDecimal zero = BigDecimal.ZERO;          // 0, scale 0.
BigDecimal moneyZero = BigDecimal.valueOf(0L, 2); // 0.00, scale 2.

System.out.println(zero.equals(moneyZero));   // false.
System.out.println(zero.compareTo(moneyZero)); // 0.
```

Both equal zero mathematically. However:

- `equals()` compares **value and scale**, hence false;
- `compareTo()` compares **arithmetic value**, hence 0;
- `signum()` is 0 for every BigDecimal with value zero, regardless of scale.

If you want to check "is this number equal to 0" in arithmetic business logic, use `value.signum() == 0` or `value.compareTo(BigDecimal.ZERO) == 0`. If you want to check scale representation too, using `equals` makes sense.

**Consequence for collections:** `HashSet<BigDecimal>` relies on `equals/hashCode`, while `TreeSet<BigDecimal>` with natural ordering uses `compareTo`; thus `1.0` and `1.00` can be treated as two distinct key values in HashSet yet the same ordering position in TreeSet. Choose the data structure per business contract.

## 9. valueOf(1L) Differs from valueOf(1.0) in Scale

Java resolves overloads by the **static type of the argument**:

```java
BigDecimal integerOne = BigDecimal.valueOf(1L); // 1, scale 0.
BigDecimal decimalOne = BigDecimal.valueOf(1.0); // 1.0, scale 1.

System.out.println(integerOne.equals(BigDecimal.ONE)); // true
System.out.println(decimalOne.equals(BigDecimal.ONE)); // false
System.out.println(decimalOne.compareTo(BigDecimal.ONE)); // 0
```

Both have arithmetic value 1. However, `Double.toString(1.0)` gives `"1.0"`, so the factory from double retains the scale-1 decimal form. This matters for reporting fractional digit counts, decimal encoding, and equality/hash consistency rules.

You can set scale explicitly:

```java
BigDecimal oneAtScale2 = BigDecimal.ONE.setScale(2);
System.out.println(oneAtScale2.toPlainString()); // 1.00
```

`setScale` returns a BigDecimal result with the new scale; it does not modify the `ONE` constant.

## 10. BigDecimal Has No Separate Negative Zero

`double` has two bit patterns `+0.0` and `-0.0`. `BigDecimal`, on the other hand, represents zero with unscaled value equal to 0; there is no independent mathematical negative zero value.

```java
BigDecimal z = BigDecimal.valueOf(-0.0);
System.out.println(z);          // 0.0
System.out.println(z.scale());  // 1
System.out.println(z.signum()); // 0
```

The minus sign of `-0.0` is not retained as a bit-level BigDecimal state, yet the **scale 1** of the string `"0.0"` is still preserved. Therefore `z.equals(BigDecimal.ZERO)` is false, while `z.compareTo(BigDecimal.ZERO)` equals 0.

If a data format requires **preserving the IEEE 754 sign bit**, do not use BigDecimal as an intermediate step expecting to recover raw zero bits. Use a `double` value or raw bits per an appropriate transport contract.

## 11. Can NaN and Infinity Create a BigDecimal?

No. BigDecimal only represents **finite** decimal numbers. Therefore:

```java
// BigDecimal.valueOf(Double.NaN) -> NumberFormatException.
// BigDecimal.valueOf(Double.POSITIVE_INFINITY) -> NumberFormatException.
```

Check before calling if input from floating-point sources is not guaranteed to be finite:

```java
static BigDecimal requireFiniteDecimal(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Expected finite value");
    }
    return BigDecimal.valueOf(value);
}
```

This is an **illustrative method inside a class** that imports BigDecimal, not a standalone program. Checking `Double.isFinite` only handles NaN/Infinity; it cannot recover ideal decimal numbers that lost precision in earlier double calculations.

## 12. BigDecimal Is Immutable: add Does Not Update the Old Object

`BigDecimal` is an **immutable** class, so `add`, `subtract`, `multiply`, `divide`, `setScale`, and `stripTrailingZeros` all return results without mutating the source object.

```java
BigDecimal total = BigDecimal.ZERO;
total.add(BigDecimal.ONE);        // Return value unused: total is still 0.
total = total.add(BigDecimal.ONE); // total becomes 1.
```

Especially when writing an accumulator:

```java
BigDecimal sum = BigDecimal.ZERO;
for (BigDecimal x : amounts) {
    sum = sum.add(x);
}
```

This snippet assumes `amounts` is an existing list of BigDecimals. For currency requirements with scale 2, define a scale policy/input constraint rather than thinking the ZERO constant already has exactly two decimal places.

Do not use the `+` operator between two BigDecimals: Java does not allow overloading the `+` operator for this object. Use `sum.add(x)`.

## 13. MathContext and RoundingMode: valueOf Does Not Replace a Rounding Policy

`valueOf` only creates a value; subsequent operations may require precision/rounding rules.

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3L);

// one.divide(three) will throw ArithmeticException because 1/3 is an infinite decimal.

BigDecimal result = one.divide(
        three,
        new java.math.MathContext(10, java.math.RoundingMode.HALF_UP));
System.out.println(result.toPlainString()); // 0.3333333333
```

A `MathContext` with precision 10 limits the result to **10 significant digits**, not a default scale of 10. `setScale(2, RoundingMode.HALF_UP)` is a different decision: requesting two digits after the decimal point.

Do not confuse `valueOf(12345L,2)` with "rounding 12345 to two decimal places": it only sets scale so the value becomes 123.45.

## 14. toString, toPlainString, and stripTrailingZeros

How it prints depends on scale:

```java
BigDecimal a = BigDecimal.valueOf(12345L, -2);
System.out.println(a.toString());       // 1.2345E+6
System.out.println(a.toPlainString()); // 1234500
```

Trailing zeros can be **representation information** that business logic cares about:

```java
BigDecimal original = new BigDecimal("10.00");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original); // 10.00
System.out.println(stripped); // 1E+1
```

Both values equal 10 arithmetically, yet their scales differ. `stripTrailingZeros` is not merely display decoration; it can change the scale and `equals` results. If the number of digits after the decimal point is used in reports/contracts, do not strip by default.

`valueOf(1e20)` also shows negative scale naturally arising from scientific strings: on Java 17, the result is `1.0E+20`, unscaled 10, scale -19.

## 15. The TEN Constant, Decimal Shifting, and Units

`BigDecimal.TEN` has value 10 with scale 0. You can multiply by TEN:

```java
BigDecimal hundred = BigDecimal.TEN.multiply(BigDecimal.TEN); // 100.
```

If your goal is to **multiply by a power of 10** or move the decimal point position, look at the appropriate methods:

```java
BigDecimal amount = new BigDecimal("12.34");
BigDecimal cents = amount.movePointRight(2);       // 1234.
BigDecimal scaled = amount.scaleByPowerOfTen(2);   // 1234 in value.
```

The two calls can yield different scales in some cases, especially when transitioning through negative scales. Specify requirements for **value** and **scale** separately, rather than assuming every way of multiplying by 10 is identical under `equals`.

## 16. Should You Compare Two BigDecimal Values with ==?

No, if the goal is to compare values. `==` on Java objects compares **reference identity**, not decimal value. Some factories may optimize by **caching/reusing objects** for common numbers; therefore it is all the more important not to rely on `==` results in business logic.

```java
BigDecimal a = BigDecimal.valueOf(1L);
BigDecimal b = BigDecimal.ONE;

// a == b is not a reliable value comparison across APIs/JDKs.
// a.equals(b) is true; a.compareTo(b) == 0 is also true.
```

To compare **value + scale**, use `equals`. To compare **arithmetic value**, use `compareTo`. To check **arithmetically equal to 0**, `signum() == 0` is usually simpler.

## 17. Choosing How to Create BigDecimal by Data Source

| Source | Recommended creation | Reason |
| --- | --- | --- |
| Validated `long` | `BigDecimal.valueOf(long)` | Preserves integer, scale 0 |
| Smallest-unit integer + decimal scale convention | `BigDecimal.valueOf(unscaled, scale)` | Preserves decimal number pair |
| Decimal string from input/API | `new BigDecimal(String)` | Does not go through binary approximation |
| Existing finite `double` | `BigDecimal.valueOf(double)` if semantics fit | Based on decimal round-trip |
| Need to inspect exact binary double | `new BigDecimal(double)` | Exposes the exact stored binary double value |
| Zero as initial value | `BigDecimal.ZERO` | Clear intent, scale 0 |
| One unit | `BigDecimal.ONE` | Clear intent, scale 0 |
| Factor of 10 | `BigDecimal.TEN` | Clear intent, scale 0 |
| Zero with 2 decimal digits | `BigDecimal.ZERO.setScale(2)` | Preserves scale 2 |
| Integer exceeding long | `new BigDecimal(BigInteger)` or string | Avoids bit loss from primitive narrowing |

If data comes from the double calculation result `0.1 + 0.2`, converting to BigDecimal at the end **does not produce exact decimal 0.3**; you must design the data types right from the start.

## 18. Complete Java 17+ Example and Run Output

Save file **`BigDecimalValueOfDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalValueOfDemo {
    static void describe(String label, BigDecimal number) {
        System.out.println(label + "=" + number.toString()
                + ",scale=" + number.scale()
                + ",unscaled=" + number.unscaledValue());
    }

    static String failure(Runnable work) {
        try {
            work.run();
            return "NO_EXCEPTION";
        } catch (ArithmeticException | NumberFormatException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        describe("zeroConstant", BigDecimal.ZERO);
        describe("oneConstant", BigDecimal.ONE);
        describe("tenConstant", BigDecimal.TEN);
        describe("longValueOf", BigDecimal.valueOf(12345L));
        describe("decimalScaled", BigDecimal.valueOf(12345L, 2));
        describe("negativeScale", BigDecimal.valueOf(12345L, -2));
        describe("zeroScale2", BigDecimal.valueOf(0L, 2));
        describe("doublePointOne", BigDecimal.valueOf(0.1));
        describe("doubleConstructor", new BigDecimal(0.1));
        describe("decimalString", new BigDecimal("0.1"));
        describe("onePointZero", BigDecimal.valueOf(1.0));
        describe("negativeDoubleZero", BigDecimal.valueOf(-0.0));
        describe("scientificDouble", BigDecimal.valueOf(1e20));

        System.out.println("valueOfEqualsString="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOfEqualsDoubleCtor="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal(0.1)));
        System.out.println("onePointZeroEqualsONE="
                + BigDecimal.valueOf(1.0).equals(BigDecimal.ONE));
        System.out.println("onePointZeroCompareONE="
                + BigDecimal.valueOf(1.0).compareTo(BigDecimal.ONE));
        System.out.println("valueOfOneLongEqualsONE="
                + BigDecimal.valueOf(1L).equals(BigDecimal.ONE));
        System.out.println("scaledZeroEqualsZERO="
                + BigDecimal.valueOf(0L, 2).equals(BigDecimal.ZERO));
        System.out.println("scaledZeroCompareZERO="
                + BigDecimal.valueOf(0L, 2).compareTo(BigDecimal.ZERO));
        System.out.println("negativeZeroEqualsZERO="
                + BigDecimal.valueOf(-0.0).equals(BigDecimal.ZERO));
        System.out.println("negativeZeroSignum="
                + BigDecimal.valueOf(-0.0).signum());

        BigDecimal original = BigDecimal.valueOf(7L);
        BigDecimal increased = original.add(BigDecimal.ONE);
        System.out.println("immutableOriginal=" + original);
        System.out.println("immutableResult=" + increased);

        BigDecimal tenth = BigDecimal.valueOf(0.1);
        BigDecimal fifth = BigDecimal.valueOf(0.2);
        System.out.println("decimalSum=" + tenth.add(fifth).toPlainString());
        System.out.println("binaryDoubleComparison=" + ((0.1 + 0.2) == 0.3));

        System.out.println("divideExactThirdError="
                + failure(() -> BigDecimal.ONE.divide(BigDecimal.valueOf(3L))));
        System.out.println("divideRoundedThird="
                + BigDecimal.ONE.divide(BigDecimal.valueOf(3L),
                        new MathContext(10, RoundingMode.HALF_UP)).toPlainString());
        System.out.println("nanValueOfError="
                + failure(() -> BigDecimal.valueOf(Double.NaN)));
        System.out.println("positiveInfinityValueOfError="
                + failure(() -> BigDecimal.valueOf(Double.POSITIVE_INFINITY)));
        System.out.println("stripTrailingZeros="
                + new BigDecimal("10.00").stripTrailingZeros().toString());
        System.out.println("oneScaled=" + BigDecimal.ONE.setScale(2).toPlainString());
        System.out.println("tenTimesTen=" + BigDecimal.TEN.multiply(BigDecimal.TEN));
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 BigDecimalValueOfDemo.java
java BigDecimalValueOfDemo
```

Verified stdout:

```text
zeroConstant=0,scale=0,unscaled=0
oneConstant=1,scale=0,unscaled=1
tenConstant=10,scale=0,unscaled=10
longValueOf=12345,scale=0,unscaled=12345
decimalScaled=123.45,scale=2,unscaled=12345
negativeScale=1.2345E+6,scale=-2,unscaled=12345
zeroScale2=0.00,scale=2,unscaled=0
doublePointOne=0.1,scale=1,unscaled=1
doubleConstructor=0.1000000000000000055511151231257827021181583404541015625,scale=55,unscaled=1000000000000000055511151231257827021181583404541015625
decimalString=0.1,scale=1,unscaled=1
onePointZero=1.0,scale=1,unscaled=10
negativeDoubleZero=0.0,scale=1,unscaled=0
scientificDouble=1.0E+20,scale=-19,unscaled=10
valueOfEqualsString=true
valueOfEqualsDoubleCtor=false
onePointZeroEqualsONE=false
onePointZeroCompareONE=0
valueOfOneLongEqualsONE=true
scaledZeroEqualsZERO=false
scaledZeroCompareZERO=0
negativeZeroEqualsZERO=false
negativeZeroSignum=0
immutableOriginal=7
immutableResult=8
decimalSum=0.3
binaryDoubleComparison=false
divideExactThirdError=ArithmeticException
divideRoundedThird=0.3333333333
nanValueOfError=NumberFormatException
positiveInfinityValueOfError=NumberFormatException
stripTrailingZeros=1E+1
oneScaled=1.00
tenTimesTen=100
```

The first lines sequentially prove that constants ZERO/ONE/TEN have scale 0; `decimalScaled` and `negativeScale` verify the unscaled/scale formula. `doublePointOne` differs from `doubleConstructor` because the conversion paths from double differ. `onePointZeroEqualsONE=false` yet `onePointZeroCompareONE=0` proves representation comparison differs from value comparison. `scaledZeroEqualsZERO=false` and `negativeZeroSignum=0` illustrate decimal zero having scale yet no separate negative-zero value.

`immutableOriginal=7` and `immutableResult=8` prove immutability; `decimalSum=0.3` contrasts with `binaryDoubleComparison=false` when numeric sources are created at the right time. The lines `divideExactThirdError`, `nanValueOfError`, and `positiveInfinityValueOfError` demonstrate division constraints and BigDecimal's domain. The last two lines confirm `setScale` and multiplication by TEN.

The `failure` method in the program catches exceptions to **display names in the lesson**; this is not a recommendation to swallow exceptions in production programming.

## 19. Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `new BigDecimal(0.1)` thinking it gives decimal 0.1 | Gets the binary double value expanded as a long decimal | Use a decimal string or `valueOf(0.1)` when appropriate |
| Using `valueOf(double)` to fix a flawed double calculation | The double value was already rounded earlier | Compute with BigDecimal from the beginning |
| Using `valueOf((double)bigLong)` | Loses precision for large integers above 2^53 | Call `valueOf(long)` |
| Thinking `valueOf(12345,2)` means 12345.2 | The two parameters are unscaled and scale | Understand it as 123.45 |
| Thinking the ZERO constant has scale 2 | ZERO has scale 0 | Create `ZERO.setScale(2)` |
| Thinking `ZERO.equals(0.00)` is always true | Different scale makes equals false | Use `compareTo` for value |
| Comparing BigDecimals with `==` | Comparing identity, not value | Use `equals`/`compareTo` |
| Calling `sum.add(x)` without using the return value | Total does not change | Assign `sum = sum.add(x)` |
| Forgetting a rounding policy when dividing 1/3 | `ArithmeticException` | Pass `MathContext` or scale + rounding mode |
| Passing NaN/Infinity into `valueOf(double)` | `NumberFormatException` | Check `Double.isFinite` |
| Using `stripTrailingZeros` when scale must be preserved | Can change scale and toString | Keep scale per contract |
| Treating `valueOf(1L)` and `valueOf(1.0)` as the same representation | Scale 0 differs from scale 1 | Pay attention to input types |

## 20. Self-Check Questions

1. **By what formula is BigDecimal represented?** Unscaled value multiplied by `10^(-scale)`.
2. **What number does `valueOf(12345L,2)` create?** 123.45.
3. **What number does `valueOf(12345L,-2)` create?** 1,234,500; `toString` may print `1.2345E+6`.
4. **Why does `valueOf(0.1)` differ from `new BigDecimal(0.1)`?** The factory goes through the round-trip decimal string; the constructor takes the exact rounded binary double value.
5. **What scale do the three constants ZERO, ONE, TEN have?** All have scale 0.
6. **What is `valueOf(1.0).equals(BigDecimal.ONE)`?** False, because of different scales.
7. **If you want to compare them by arithmetic value?** Use `compareTo`, result 0.
8. **Why is `BigDecimal.valueOf(0L,2).equals(ZERO)` false?** The two zeros have scales 2 and 0.
9. **How do you create zero with two decimal digits?** `BigDecimal.ZERO.setScale(2)` or `valueOf(0L,2)`.
10. **What is `valueOf(-0.0).signum()`?** 0; BigDecimal has no separate negative zero.
11. **Can `Double.NaN` be passed into `valueOf`?** No, it throws `NumberFormatException`.
12. **Does `BigDecimal.ONE.divide(BigDecimal.valueOf(3L))` succeed?** No without providing a rounding context, because 1/3 has no finite decimal representation.
13. **Does calling `total.add(ONE)` without reassigning change total?** No, BigDecimal is immutable.
14. **How do you create BigDecimal from a large integer long to preserve exactness?** `valueOf(long)`.
15. **Can `stripTrailingZeros` change scale?** Yes, for example `10.00` becomes `1E+1`.
16. **Since factories may cache objects, should you use `==`?** No; caching is not a value comparison contract.

**Takeaway:** `valueOf(long)` creates an exact decimal integer with scale 0; `valueOf(long,scale)` uses unscaled value and scale; `valueOf(double)` relies on the round-trip decimal representation of an existing double. The constants `ZERO`, `ONE`, and `TEN` are **immutable** and all have **scale 0**. Pay attention to the difference between arithmetic value and representation scale, control rounding in operations, and do not use `double` as an intermediary if exact decimals are needed from the start.