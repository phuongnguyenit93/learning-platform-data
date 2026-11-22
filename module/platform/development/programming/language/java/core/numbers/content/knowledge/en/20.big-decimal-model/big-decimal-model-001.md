# Arbitrary-Precision Decimals and BigDecimal Immutability in Java

## 1. What Problem Does BigDecimal Solve?

The **float** and **double** types store numbers in **binary** floating-point format. Not every decimal fraction can be represented exactly in a finite binary system. A familiar example result:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // 0.30000000000000004
~~~

This is the expected behavior of double, not a JVM bug. When an application requires **exact decimal arithmetic according to well-defined rules**, Java provides the **java.math.BigDecimal** class.

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
~~~

BigDecimal has the following characteristics:

- **Decimal representation based on an arbitrary-length integer and a scale**, instead of a 53-bit binary significand.
- **Immutable**: once created, the object does not change across operations. Calculations return a new result value.
- **Exact operations** when the finite decimal result can be represented within resource and scale limits.
- **Controlled rounding** via RoundingMode, MathContext, or setScale.
- **Multiple comparison methods** depending on whether equality is needed by numeric value or also by scale.

BigDecimal is useful in finance, taxes, pricing, decimal rate calculations, user-supplied digit input, and protocols that require preserving decimal digits.

**Arbitrary precision does not mean infinite precision for every real number**: dividing 1/3 does not have a finite decimal representation; BigDecimal must round according to a provided policy or throw an exception. Nor does it have infinite resources: scale is an int, while integer length and operations are subject to implementation, CPU, and memory limits.

## 2. Structure: Unscaled Value and Scale

A BigDecimal represents a mathematical value via the formula:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

- **unscaledValue**: a signed integer; the unscaledValue() method returns a BigInteger.
- **scale**: an integer of type int, which can be positive, zero, or negative.
- **precision**: the number of decimal digits in the unscaled value without the sign; zero has a precision of 1.

Example:

~~~java
BigDecimal n = new BigDecimal("123.4500");

System.out.println(n.unscaledValue()); // 1234500
System.out.println(n.scale());         // 4
System.out.println(n.precision());     // 7
System.out.println(n.toPlainString()); // 123.4500
~~~

The exact value is 1234500 × 10^−4 = 123.4500.

| Initialization String | Unscaled Value | Scale | Numeric Value |
| --- | ---: | ---: | --- |
| "123.4500" | 1234500 | 4 | 123.45 |
| "12.34" | 1234 | 2 | 12.34 |
| "12" | 12 | 0 | 12 |
| "1E+3" | 1 | −3 | 1000 |
| "0.001" | 1 | 3 | 0.001 |

**Scale and precision are two different concepts.** For 123.4500, scale=4, precision=7; for 1E+3, scale=−3, precision=1. BigDecimal does not restrict scale to only being the number of digits to the right of the decimal point; a **negative** scale is valid.

### Negative Scale in Practice

~~~java
BigDecimal x = new BigDecimal("1E+3");
System.out.println(x.scale());         // -3
System.out.println(x.toString());      // 1E+3
System.out.println(x.toPlainString()); // 1000
~~~

This decimal exponent form still represents the exact value **1000**. However, when parsing the plain string "1000" back, the new object can have scale 0, different from the −3 scale of the original value. Therefore, do not assume toPlainString preserves the full representation during a round-trip.

### Arbitrary Precision Still Has Limits

BigDecimal can handle thousands of digits that double cannot store accurately, but:

1. Scale belongs to the int range (it cannot be an unbounded integer).
2. The unscaled integer requires heap memory and has practical/implementation limits.
3. Multiplying, dividing, and exponentiating very large numbers consume time and resources.
4. A MathContext with finite precision **allows intentional rounding**.

If user-supplied data can be extremely long, validate the digit count, scale, operation complexity, and resource limits before processing.

## 3. How to Create BigDecimal Without Losing Digits

To represent a **decimal value that you intentionally enter**, prefer a decimal string:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3);
~~~

The String constructor converts text into BigDecimal without going through double.

### The Trap of new BigDecimal(double)

~~~java
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
BigDecimal expected = new BigDecimal("0.1");

System.out.println(fromBinaryDouble.equals(expected)); // false
~~~

Reason: the double literal **0.1** is not exactly 1/10 in binary representation. **new BigDecimal(double)** describes the exact approximate binary value that double holds, resulting in many decimal digits.

**BigDecimal.valueOf(0.1)** uses the decimal text corresponding to Double.toString of the double:

~~~java
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
System.out.println(fromValueOf.toPlainString()); // 0.1
~~~

The valueOf(double) method is generally more appropriate than the double constructor if you must receive an existing double value and want to convert it using the corresponding short decimal representation. However, **it cannot fix errors that have already occurred earlier**:

~~~java
double alreadyRounded = 0.1 + 0.2;
BigDecimal converted = BigDecimal.valueOf(alreadyRounded);
// converted = 0.30000000000000004, it does not revert to 0.3.
~~~

For decimal inputs that require precision, convert **String → BigDecimal right from the start**. For long integers, BigDecimal.valueOf(long) preserves the exact value.

### Constants and Utility Methods

- **BigDecimal.ZERO**, **BigDecimal.ONE**, **BigDecimal.TEN** are built-in constants in Java 17.
- **BigDecimal.valueOf(2)** creates the value 2.
- **BigDecimal.TWO** is not a constant in the Java 17 API.
- **BigDecimal.valueOf(long, int scale)** is useful when the initial value is an unscaled integer with a predetermined scale.

Do not confuse BigDecimal with BigInteger: BigInteger is for integers, whereas BigDecimal supports powers of 10 to represent decimals.

## 4. Immutability: Operations Do Not Modify Objects

BigDecimal is an **immutable object**: methods like add, subtract, multiply, divide, negate, abs, setScale, round, and stripTrailingZeros do not modify the operands' contents; they return the resulting BigDecimal.

~~~java
BigDecimal first = new BigDecimal("1.20");
BigDecimal second = new BigDecimal("2.30");

BigDecimal sum = first.add(second);

System.out.println(first.toPlainString()); // 1.20
System.out.println(sum.toPlainString());   // 3.50
~~~

**If the return value is ignored, the variable's data does not change:**

~~~java
BigDecimal total = BigDecimal.ZERO;
total.add(new BigDecimal("10.00"));
System.out.println(total); // 0

total = total.add(new BigDecimal("10.00"));
System.out.println(total); // 10.00
~~~

The assignment statement **total = ...** only updates the reference in the variable; it does not change the original ZERO object.

### Benefits of Immutability

- Constants BigDecimal.ZERO/ONE/TEN can be reused across many places.
- Reduces the risk of another method modifying an object passed via a parameter.
- Easier to test because input objects remain unchanged after calculations.
- Created BigDecimal objects can be shared for **reading** across multiple threads without mutating their contents.

However, immutability **does not make updating a shared variable atomic**. Two threads reading the same balance variable, computing the added value, and assigning it back can lose an update. Appropriate synchronization, transactions, or atomic structures must be used when updating shared state.

### Immutability Is a Property of the Object, Not the Variable

~~~java
BigDecimal a = new BigDecimal("100");
BigDecimal alias = a;

a = a.add(BigDecimal.ONE);

// a holds 101; alias still points to the old object with value 100.
~~~

If a DTO has a setter for a BigDecimal field, the DTO itself can still be **mutable**, even though each BigDecimal in the field is immutable.

## 5. Exact Addition/Subtraction/Multiplication and Result Scale

Addition, subtraction, and multiplication **that do not take a MathContext** attempt to produce an exact decimal result within implementation limits.

~~~java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("0.045");

BigDecimal sum = a.add(b);       // 12.345
BigDecimal diff = a.subtract(b); // 12.255
~~~

For exact addition/subtraction, the **preferred scale** is typically max(scale of the operands). For exact multiplication, the preferred scale is the sum of the scales:

~~~java
BigDecimal a = new BigDecimal("1.20"); // scale 2
BigDecimal b = new BigDecimal("3.00"); // scale 2
BigDecimal product = a.multiply(b);   // 3.6000, scale 4
~~~

The resulting string may contain trailing zeros. This is not an error: it reflects BigDecimal's representation and scale rules. If business logic requires exactly 2 decimal places, use setScale or a specified rounding step; do not assume multiply automatically outputs exactly two digits.

## 6. Why Is Division Different from Addition/Subtraction/Multiplication?

A fraction may not have a finite decimal expansion. With BigDecimal:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");
BigDecimal exact = one.divide(eight); // 0.125
~~~

Conversely:

~~~java
// BigDecimal.ONE.divide(new BigDecimal("3"));
// Throws ArithmeticException at runtime because 1/3 does not terminate.
~~~

BigDecimal.divide(BigDecimal) without digit-limit/rounding information only accepts a **finite exact** decimal quotient. If the divisor is zero, it also throws ArithmeticException.

A fraction a/b after reduction to a positive denominator b has a finite decimal form when the prime factors of b consist only of **2 and 5**. Therefore, 1/8 and 1/40 terminate, while 1/3 and 1/7 do not.

### Division with Scale and Rounding

~~~java
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333, scale 4
~~~

This overload requests **4 digits after the decimal point**, not 4 significant digits.

### Division with MathContext

~~~java
import java.math.MathContext;

MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), mc);
// 0.33333, precision 5
~~~

MathContext controls **precision measured in number of significant digits** along with RoundingMode. The difference between **scale** and **precision** is clearly demonstrated in this example.

## 7. MathContext: Precision Is Not Scale

- **scale**: the decimal exponent represented in the value, which can be understood as the number of fractional positions when scale is non-negative.
- **precision**: the number of decimal digits of the unscaled value, not just the number of digits to the right of the decimal point.
- **MathContext**: a policy parameter that limits the precision of a **specific calculation**.

Example:

~~~java
BigDecimal x = new BigDecimal("12345.6789");
BigDecimal y = x.round(
        new MathContext(5, RoundingMode.HALF_EVEN));
// y = 12346, consisting of 5 significant digits
~~~

The result does not have 5 digits after the decimal point; it has **5 total significant digits**.

**MathContext.UNLIMITED** has precision equal to 0 and requests exact results for appropriate operations. It does not suddenly give 1/3 a finite decimal expansion, so non-terminating division still needs a rounding policy.

MathContext is not a global variable that automatically affects every operation. You can pass MathContext per call:

~~~java
BigDecimal a = new BigDecimal("12345.6789");
BigDecimal b = new BigDecimal("2.5");

BigDecimal exact = a.multiply(b);
BigDecimal rounded = a.multiply(b,
        new MathContext(6, RoundingMode.HALF_EVEN));
~~~

The two results may differ because **rounded** is rounded according to the policy after multiplication.

## 8. setScale: Controlling the Number of Digits After the Decimal Point

~~~java
BigDecimal original = new BigDecimal("2.345");
BigDecimal newValue = original.setScale(2, RoundingMode.HALF_UP);
// original is still 2.345; newValue is 2.35
~~~

setScale returns a resulting BigDecimal, **it does not modify original**. If only increasing scale from 1.2 to 1.20, adding zeros does not change the value:

~~~java
BigDecimal price = new BigDecimal("1.2");
BigDecimal twoDigits = price.setScale(2, RoundingMode.UNNECESSARY);
// 1.20
~~~

With RoundingMode.UNNECESSARY, if changing scale requires rounding away significant digits, the method throws ArithmeticException.

### RoundingMode Options

| Mode | Description |
| --- | --- |
| HALF_EVEN | Tie → last kept digit is even |
| HALF_UP | Tie → away from zero |
| HALF_DOWN | Tie → towards zero |
| UP | If remainder exists, away from zero |
| DOWN | If remainder exists, towards zero |
| CEILING | Towards positive infinity |
| FLOOR | Towards negative infinity |
| UNNECESSARY | Rounding is not permitted |

There is no single RoundingMode that is right for every application. For taxes, fees, currencies, or measurement data, choose according to **business rules and applicable standards**.

**Where rounding happens matters**: rounding individual components before aggregating may differ from rounding the final total. BigDecimal provides the tools to enforce a policy, but does not decide the policy itself.

## 9. How Does equals() Differ from compareTo()?

Two BigDecimals with the same numeric value but different scales:

~~~java
BigDecimal a = new BigDecimal("1.0");  // scale 1
BigDecimal b = new BigDecimal("1.00"); // scale 2

System.out.println(a.equals(b));   // false
System.out.println(a.compareTo(b)); // 0
~~~

- **equals()** considers both numeric value and scale.
- **compareTo()** compares numeric value in numerical order and can return 0 even when scales differ.
- **==** compares object references, not BigDecimal values.

When checking whether two decimal values have the same numeric value:

~~~java
boolean numericallyEqual = a.compareTo(b) == 0;
boolean smaller = a.compareTo(b) < 0;
boolean larger = a.compareTo(b) > 0;
~~~

### HashSet, HashMap, and TreeSet

BigDecimal's **hashCode()** takes scale into account, consistent with equals. A HashSet can contain both 1.0 and 1.00 as two distinct values according to equals. Conversely, TreeSet uses natural ordering/compareTo, so it typically keeps only one element that is equivalent in numeric value. **The natural ordering of BigDecimal is inconsistent with equals.**

If using BigDecimal as a **key** or to represent money, define a clear policy: is scale part of the identity, and when should it be normalized? Avoid mixing equals and compareTo arbitrarily when the application requires consistent logic.

## 10. stripTrailingZeros and Scientific Notation

~~~java
BigDecimal a = new BigDecimal("123.4500");
BigDecimal normalized = a.stripTrailingZeros();

System.out.println(normalized.toPlainString()); // 123.45
System.out.println(normalized.scale());         // 2
~~~

Do not assume stripTrailingZeros always produces a number with a non-negative scale:

~~~java
BigDecimal large = new BigDecimal("1000").stripTrailingZeros();
System.out.println(large.toString()); // 1E+3
System.out.println(large.scale());    // -3
~~~

Sometimes normalizing scale is appropriate for keys/comparisons; however, for prices requiring exactly two digits, stripping trailing zeros may lose part of the representation convention. Define the goal clearly beforehand.

**Zero is special:** stripTrailingZeros can normalize a zero value to BigDecimal.ZERO, scale 0. This affects equals against a zero BigDecimal with a different scale.

## 11. toString, toPlainString, and Preserving Representation

- **toString()**: outputs a canonical form that may use exponent notation.
- **toPlainString()**: outputs decimal digits without exponent notation.
- **toEngineeringString()**: may output engineering notation with exponents that are multiples of 3.

~~~java
BigDecimal n = new BigDecimal("1E+3");

System.out.println(n.toString());      // 1E+3
System.out.println(n.toPlainString()); // 1000
~~~

**toPlainString may not preserve scale if the string is parsed back**, as in the example where 1E+3 with scale −3 turns into "1000" with scale 0. If the system needs to preserve both value and scale, use an appropriate round-trip representation or store the scale separately per contract.

Formatting BigDecimal with NumberFormat for UI display can change grouping separators, decimal points, and digit limits; do not write formatted output back as a source value if original precision is needed.

## 12. Money and Tax Applications: Exact Does Not Mean No Rounding Needed

~~~java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal quantity = BigDecimal.valueOf(3);
BigDecimal subtotal = unitPrice.multiply(quantity); // 59.97

BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal tax = subtotal.multiply(taxRate); // 4.49775
~~~

The fact that tax has many digits after the decimal point is not a binary error; it is the **exact decimal result of the multiplication**.

If the policy requires rounding at this step:

~~~java
BigDecimal chargedTax = tax.setScale(2, RoundingMode.HALF_UP);
// 4.50 per the example rule
~~~

Do not use RoundingMode.HALF_UP out of habit when business/legal requirements specify another rule. Similarly, the rounding order must be determined: per line item, per tax item, or on the invoice total. Currency units and currency codes should be stored separately; BigDecimal does not itself represent USD/EUR/VND and does not convert exchange rates.

## 13. Thread Safety and Storage Models

Immutable BigDecimal has no setters to modify unscaled value or scale; therefore, sharing **already-created objects** for reading is safe with respect to object contents. However, managing a **mutable variable holding a BigDecimal reference** across multiple threads still requires proper synchronization if writes occur.

For example, a balance property updated by two requests in a read–add–assign flow can lose an update. Appropriate locks, transactions, or atomic structures are needed depending on the architecture.

When transferring over JSON, CSV, or databases:

1. Check whether the parser preserves decimals or silently converts them to double.
2. Use a **decimal String** or a native decimal type with appropriate precision/scale when required by the protocol.
3. For SQL DECIMAL/NUMERIC, check column precision/scale and driver conversion rules.
4. Limit string length and scale magnitude before processing untrusted input.
5. Do not confuse UI strings containing grouping/currency symbols with standard strings accepted by BigDecimal(String).

BigDecimal does not solve every data safety, transaction, or formatting problem. It provides a decimal number model so those rules can be implemented explicitly.


## 14. Standalone Runnable Java 17+ Example

Save as file **BigDecimalModelDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalModelDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");

        System.out.println("value: " + a.toPlainString());
        System.out.println("unscaled: " + a.unscaledValue());
        System.out.println("scale: " + a.scale());
        System.out.println("precision: " + a.precision());

        BigDecimal normalized = a.stripTrailingZeros();
        System.out.println("normalized: " + normalized.toPlainString()
                + " (scale=" + normalized.scale() + ")");

        BigDecimal first = new BigDecimal("1.20");
        BigDecimal second = new BigDecimal("2.30");
        BigDecimal sum = first.add(second);

        System.out.println("first stays: " + first.toPlainString());
        System.out.println("sum: " + sum.toPlainString());
        System.out.println("decimal 0.1 + 0.2: "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("valueOf(0.1): " + BigDecimal.valueOf(0.1));

        System.out.println("new BigDecimal(0.1) equals 0.1: "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("equals 1.0 / 1.00: " + x.equals(y));
        System.out.println("compareTo 1.0 / 1.00: " + x.compareTo(y));

        System.out.println("8th: "
                + BigDecimal.ONE.divide(new BigDecimal("8")));
        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException e) {
            System.out.println("1 / 3 exact: ArithmeticException");
        }

        System.out.println("1 / 3 scale 4: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 4, RoundingMode.HALF_UP));
        System.out.println("1 / 3 precision 5: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        new MathContext(5, RoundingMode.HALF_UP)));

        BigDecimal rounded = new BigDecimal("12345.6789")
                .round(new MathContext(5, RoundingMode.HALF_EVEN));
        System.out.println("round 12345.6789 to 5 digits: "
                + rounded.toPlainString());
        System.out.println("setScale HALF_UP: "
                + new BigDecimal("2.345")
                        .setScale(2, RoundingMode.HALF_UP));

        BigDecimal scientific = new BigDecimal("1E+3");
        System.out.println("scientific scale: " + scientific.scale());
        System.out.println("scientific string: " + scientific);
        System.out.println("scientific plain: " + scientific.toPlainString());
        System.out.println("stripped 1000: "
                + new BigDecimal("1000").stripTrailingZeros());

        System.out.println("10.00 / 4: "
                + new BigDecimal("10.00").divide(new BigDecimal("4")));
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac --release 17 BigDecimalModelDemo.java
java BigDecimalModelDemo
~~~

Stdout (verified against the BigDecimal API on the JDK):

~~~text
value: 123.4500
unscaled: 1234500
scale: 4
precision: 7
normalized: 123.45 (scale=2)
first stays: 1.20
sum: 3.50
decimal 0.1 + 0.2: 0.3
valueOf(0.1): 0.1
new BigDecimal(0.1) equals 0.1: false
equals 1.0 / 1.00: false
compareTo 1.0 / 1.00: 0
8th: 0.125
1 / 3 exact: ArithmeticException
1 / 3 scale 4: 0.3333
1 / 3 precision 5: 0.33333
round 12345.6789 to 5 digits: 12346
setScale HALF_UP: 2.35
scientific scale: -3
scientific string: 1E+3
scientific plain: 1000
stripped 1000: 1E+3
10.00 / 4: 2.50
~~~

### Reading the Output

- unscaled=1234500, scale=4, precision=7 accurately reflect the original decimal number model.
- normalized has scale=2, yet its numeric value is unchanged.
- first remains 1.20 after add; this is immutability.
- 0.1+0.2 as BigDecimal strings yields exact decimal 0.3.
- new BigDecimal(0.1) does not equal the decimal value "0.1" because it received a binary double.
- equals distinguishes scale, compareTo compares numeric value.
- 1/8 has a finite decimal result, while 1/3 cannot be divided exactly without rounding.
- Scale 4 differs from precision 5; the results are 0.3333 and 0.33333 respectively.
- Round with MathContext(5) keeps only 5 significant digits, so 12345.6789 becomes 12346.
- The value 1000 can be represented via a negative scale when normalized.
- 10.00/4 returns 2.50 due to the preferred scale of exact division.

## 15. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using new BigDecimal(0.1) to create exact 0.1 | Receives the exact binary double value near 0.1, not decimal 0.1 | Use new BigDecimal("0.1") |
| Converting an already-rounded double result to BigDecimal expecting to fix error | Prior error still remains | Parse decimal data before calculation |
| Calling total.add(amount) without assignment | total does not change | total = total.add(amount) |
| Using == to compare two BigDecimals | Compares references, not values | Use equals/compareTo as appropriate |
| Using equals for 1.0 and 1.00 when intending to compare numeric value | false due to different scales | Use compareTo == 0 |
| Using BigDecimal as a HashMap key without a scale rule | Two numbers with the same value can be two distinct keys | Normalize representation per contract |
| Thinking scale and precision mean the same thing | Wrong rounding limits | Scale is the decimal exponent; precision is the number of significant digits |
| Thinking scale is always positive | 1E+3 has scale −3 | Handle negative scales |
| Believing stripTrailingZeros always prints in plain form | May output 1E+3 | Use toPlainString when needed and understand round-trip behavior |
| Calling divide for 1/3 without rounding | ArithmeticException | Specify scale/RoundingMode or MathContext |
| Thinking MathContext(5) is equivalent to setScale(5) | Different rounding | Choose based on significant digits vs. decimal places |
| Thinking setScale modifies original | Ignoring return value leaves original unchanged | Assign the returned object |
| Choosing HALF_UP by default for all money and taxes | Can violate business rules | Choose RoundingMode according to actual policy |
| Thinking BigDecimal holds unlimited digits with no resource cost | Can consume heavy heap/CPU; int scale limit | Set resource limits |
| Thinking immutability automatically makes a shared variable safe under concurrent writes | Updates can be lost | Synchronize or use transactions |
| Using NumberFormat as the value storage model | Display strings can round/depend on Locale | Store decimal numbers from source data |

## 16. Self-Check Exercises

**Exercise 1.** For a BigDecimal from the string "12.3400", what are unscaledValue and scale?

**Answer:** 123400 and 4. Numeric value = 123400 × 10^−4 = 12.3400.

**Exercise 2.** What does new BigDecimal("1.0").equals(new BigDecimal("1.00")) return? What does compareTo return?

**Answer:** equals returns false because scales 1 and 2 differ; compareTo returns 0 because numeric values are equal.

**Exercise 3.** BigDecimal a = new BigDecimal("2"); a.multiply(BigDecimal.TEN); what is a afterward?

**Answer:** Still 2. BigDecimal is immutable; you must assign the result if you want the variable to reference the new value.

**Exercise 4.** Why does exact division 1/3 throw ArithmeticException?

**Answer:** The result has an infinite decimal expansion and cannot be represented by a finite BigDecimal without a rounding policy.

**Exercise 5.** To represent 1/3 as 0.3333, which overload must be used?

**Answer:** BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP).

**Exercise 6.** Does MathContext(5) keep 5 digits after the decimal point or 5 significant digits?

**Answer:** 5 significant digits. If you need 5 fractional digits, use setScale(5, mode) according to policy.

**Exercise 7.** Why can BigDecimal from the string "1000" become "1E+3" after stripTrailingZeros?

**Answer:** Trailing zeros are removed from the unscaled value, and the scale can become −3; the mathematical value remains 1000.

**Exercise 8.** At which step should tax amounts be rounded?

**Answer:** According to the system's business/legal contract. BigDecimal only supports executing the rounding method that has been defined.

**Exercise 9.** Does BigDecimal.valueOf(0.1 + 0.2) guarantee becoming an exact BigDecimal 0.3?

**Answer:** No. The double addition already produced a value near 0.30000000000000004 before conversion.

**Exercise 10.** Is a BigDecimal balance variable shared across multiple threads safe when threads concurrently execute balance = balance.add(delta)?

**Answer:** Not by default. The object is immutable, but updating the variable can lose data without synchronization or transactions.

## 17. Primary Sources

- [BigDecimal API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): unscaledValue/scale model, immutability, preferred scales, operations, equals/compareTo.
- [MathContext API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision, rounding, and UNLIMITED.
- [RoundingMode API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding modes.
- [BigInteger API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): arbitrary-precision integers and unscaled value.
- [Double API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): double representation, Double.toString.
