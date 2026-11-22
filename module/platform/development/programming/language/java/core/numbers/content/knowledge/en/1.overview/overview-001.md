# What Are Numbers in Java and What Problems Need Representation?

## 1. What Is a Number in a Program?

In mathematics, integers and real numbers are concepts with a very broad value domain. In Java, a **numeric value** is represented by a data type with defined limits: bit count, value range, precision, and supported operations. Because memory is finite, no primitive type can represent every mathematical number with exactness.

Look at these values that all consist of digits but have different meanings:

- `27` learners: an **integer quantity**, needing counting, addition, and comparison.
- `36.5` °C: a **measured quantity**, usually with a fractional part and measurement error.
- `19.90` USD: a **price**, needing decimal precision and rounding policies.
- `00123`: could be a **customer code**, which must preserve leading zeros and does not need addition.
- `20261027`: could be a date format, unsuitable for arbitrary arithmetic operations.

Therefore, before choosing `int` or `double`, determine the **data meaning**, valid range, required precision, operations, units, and formatting. A character string consisting entirely of digits should not necessarily be stored using a numeric type.

## 2. Java's Primary Numeric Types

The six primitive types commonly used for arithmetic are `byte`, `short`, `int`, `long`, `float`, and `double`. Java also has `char` (an *integral* type according to the specification, though its primary meaning is a UTF-16 code unit) and `boolean` (not a numeric type).

| Type | Size | Range or Characteristics | Purpose |
|---|---:|---|---|
| `byte` | 8 bits | −128 to 127 | Bytes/protocols, binary data |
| `short` | 16 bits | −32,768 to 32,767 | Protocol compatibility, 16-bit formats |
| `int` | 32 bits | −2,147,483,648 to 2,147,483,647 | Quantities, indices, general integer arithmetic |
| `long` | 64 bits | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | Counters, large integers |
| `float` | 32 bits | IEEE 754 binary floating-point, about 6–9 significant decimal digits | 32-bit data where inaccuracy is acceptable |
| `double` | 64 bits | IEEE 754 binary floating-point, about 15–17 significant decimal digits | General measurement and scientific computation |

The precision of `float`/`double` is the **number of significant digits**, not always exactness to a fixed number of digits after the decimal point. These are **binary approximation** types: values like decimal `0.1` are generally not stored with absolute exactness. `float` and `double` also have `NaN`, infinity, and signed zero.

Two `java.math` classes are especially important:

- **`BigInteger`**: exact integers of arbitrary magnitude within machine resource limits; used when even `long` is not enough.
- **`BigDecimal`**: exact decimal numbers represented by an integer unscaled value and a *scale* (number of digits on the decimal scale). Suitable for prices, taxes, and calculations with explicit decimal and rounding requirements.

`BigInteger` and `BigDecimal` are **objects**, not primitives; use methods like `add`, `multiply`, and `divide` instead of regular arithmetic operators. Wrapper classes `Integer`, `Long`, `Double`, etc., are for situations requiring objects/generics/collections; keep in mind boxing/unboxing and that a `null` value can cause an error during unboxing.

## 3. Three Important Dimensions of Numeric Representation

### 3.1. Value Range: How Large Can the Number Be?

`int` holds 32-bit signed integers. `long` holds 64-bit signed integers. A primitive integer addition, subtraction, or multiplication can **overflow**: for example, `Integer.MAX_VALUE + 1` becomes `Integer.MIN_VALUE`. Java does not automatically widen the result to `long`, and normal integer addition does not automatically throw an error.

When overflow detection is needed, use `Math.addExact`, `Math.subtractExact`, and `Math.multiplyExact`; they throw `ArithmeticException` when exceeding the range. When a wider range is needed, convert an operand to `long` **before the calculation**, e.g., `(long) a * b`; writing `(long) (a * b)` may already be too late if `a * b` is an `int` multiplication that overflows. If `long` is not enough, consider `BigInteger` and evaluate memory/performance costs.

### 3.2. Precision: Does the Number Equal the Intended Value Exactly?

`double` uses a binary representation with finite precision. The decimal value `0.1` is typically stored only approximately, so `0.1 + 0.2 == 0.3` is `false`. This does not make `double` useless: it is very well suited for many measurements and numerical algorithms with controlled error models.

If the problem requires **decimal exactness**, such as adding money `0.10 + 0.20 = 0.30`, use a `BigDecimal` created from a string, e.g., `new BigDecimal("0.10")`. Avoid `new BigDecimal(0.1)`: that constructor receives the pre-existing approximate binary value of the `double` literal. `BigDecimal.valueOf(0.1)` usually carries the intended decimal meaning when starting from a `double` literal, but ideally monetary data should come from a string or an explicit smallest unit.

### 3.3. Semantics and Units: Is It Truly an Arithmetic Quantity?

A postal code `"00123"`, employee code `"000045"`, or phone number should use `String` to preserve characters, leading zeros, `+` signs, and formatting. Dates should use `LocalDate`, instants `Instant`, and durations `Duration` in `java.time` when appropriate; avoid "raw" integers where it is unclear whether they mean seconds, milliseconds, or calendar days.

The number `5` meters is different from `5` seconds. If an API must accept primitive numbers, name them with units (e.g., `timeoutMillis`), validate data ranges, and convert at system boundaries.

## 4. Literals and Basic Operations

Common literal forms:

~~~java
int learners = 27;                // decimal system
int oneMillion = 1_000_000;       // _ for readability
int bits = 0b1010;                // binary: 10
int hex = 0xFF;                   // hexadecimal: 255
long views = 3_000_000_000L;      // L suffix for long
double ratio = 0.125;             // decimal literal defaults to double
float sample = 0.125f;            // f or F for float
double distance = 6.02e3;         // 6020.0
~~~

Decimal integer literals without `L` normally have type `int`, while literals with a decimal point normally have type `double` (unless suffixed with `f`/`F`). The `_` character may only be placed between digits in valid positions; `1_.0` is invalid syntax. Java also has octal literals with a `0` prefix: `010` carries decimal value `8`, which can easily surprise readers expecting a decimal number.

Several rules directly affect results:

- `5 / 2` equals `2` because both operands are integers; `5.0 / 2` and `(double) 5 / 2` equal `2.5`.
- `byte`, `short`, and `char` are normally promoted to `int` in arithmetic expressions (*numeric promotion*).
- `int` can be widened to `long` and `double`, but **converting to floating-point can still lose precision**, especially for large integers.
- Casting from `double` to `int` drops the fractional part for finite values in range; outside the finite range the result saturates at the boundary, and `NaN` becomes 0. Do not treat a cast as a guarantee of lossless conversion.
- The literal `byte b = 100;` is accepted because the `int` constant fits in `byte`, but not every `int` **variable** can be automatically converted to `byte`.

When reading numbers from text, you can use `Integer.parseInt("42")`, `Long.parseLong("3000000000")`, `new BigInteger("12345678901234567890")`, or `new BigDecimal("19.90")`. Invalid or out-of-range input produces errors such as `NumberFormatException`; validate and handle at the application boundary. For locale-formatted numbers (comma/dot separators), define the `Locale` and corresponding parse/format tools; do not replace characters ad hoc in an ambiguous way.

## 5. Which Problem Calls for Which Type?

| Data to Represent | Example | Starting Choice | What to Determine |
|---|---|---|---|
| Regular counts | 27 learners; array index | `int` | Can it be negative, what is the max limit? |
| Large counters | 3 billion views | `long` | Could accumulation cause overflow? |
| Binary/protocol data | Bytes, 16-bit integers | `byte`, `short` | Signedness, decoding method, byte order |
| Price/money/tax | 19.90 × 3 | `BigDecimal` or `long` storing smallest unit by contract | Currency, scale, rounding |
| Physical measurements | 36.5 °C; 2.75 m | `double` | Instrument error, units, and comparison method |
| Extremely large integers | 100-digit integer | `BigInteger` | Time and memory |
| Ratios, probabilities | 17/23; 12.5% | `double` if approximation allowed; `BigDecimal` when decimal must be exact | 0..1 range, rounding/display method |
| Identifiers | `"00123"`; phone number | `String` | Preserving leading zeros and characters |
| Time | 90 minutes; UTC instant | `Duration`; `Instant` | Units, calendar, time zone |

The table is a **starting suggestion**, not a replacement for business rules. For instance, an invoice does not just need `BigDecimal`: it must also specify currency, when rounding occurs, number of decimal places, and how to allocate remainders. Ratios in statistics might need `double`, while financial systems might need decimal-exact methods.

### A Ticketing Scenario

- `seatCount = 120` is a seat count; `int` is usually appropriate.
- `ticketPrice = 149.90` is a monetary price, represented with `BigDecimal("149.90")`.
- `bookingCode = "000120"` is a booking code; use `String` so `00` is not lost.
- `elapsed = 90 minutes` is a time duration; use `Duration.ofMinutes(90)`.
- `successRate = 0.973` is a statistical rate; `double` can be appropriate if error is acceptable.

All five contain digits, yet the five cases require five different interpretations of the data.

## 6. Standalone Java 17+ Example: Representing Each Quantity Properly

Create the file `NumberRepresentationDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberRepresentationDemo {
    public static void main(String[] args) {
        int students = 27;
        long views = 3_000_000_000L;
        double temperature = 36.5;

        BigDecimal ticketPrice = new BigDecimal("19.90");
        BigDecimal ticketCount = new BigDecimal("3");
        BigDecimal total = ticketPrice.multiply(ticketCount);

        BigInteger hugeNumber =
                new BigInteger("123456789012345678901234567890");
        String customerCode = "00123";

        System.out.println("students=" + students);
        System.out.println("views=" + views);
        System.out.println("temperature=" + temperature);
        System.out.println("total=" + total.toPlainString());
        System.out.println("huge+1=" + hugeNumber.add(BigInteger.ONE));
        System.out.println("customerCode=" + customerCode);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac NumberRepresentationDemo.java
java NumberRepresentationDemo
~~~

Exact output:

~~~text
students=27
views=3000000000
temperature=36.5
total=59.70
huge+1=123456789012345678901234567891
customerCode=00123
~~~

`views` exceeds the `int` range so `long` is used; `temperature` is a measurement that permits floating-point representation. `BigDecimal` preserves two decimal digits in the multiplication `19.90 × 3 = 59.70`. `BigInteger` allows adding integers larger than the `long` range. `customerCode` preserves leading zeros because it is an identifier.

## 7. Standalone Java 17+ Example: Common Mistakes

Create the file `NumberPitfalls.java`:

~~~java
public class NumberPitfalls {
    public static void main(String[] args) {
        int a = 5;
        int b = 2;

        System.out.println("5 / 2 (int) = " + (a / b));
        System.out.println("5 / 2 (double) = " + ((double) a / b));
        System.out.println("int overflow = " + (Integer.MAX_VALUE + 1));
        System.out.println("0.1 + 0.2 == 0.3 = " + ((0.1 + 0.2) == 0.3));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
~~~

~~~bash
javac NumberPitfalls.java
java NumberPitfalls
~~~

Output:

~~~text
5 / 2 (int) = 2
5 / 2 (double) = 2.5
int overflow = -2147483648
0.1 + 0.2 == 0.3 = false
overflow detected
~~~

These are three **distinct** phenomena: integer division drops the fractional part, integer addition overflows the range, and floating-point stores only an approximation. How you handle them depends on the problem: use floating-point operands when an approximate quotient is wanted, `Math.addExact` or a wider type to handle integers, and `BigDecimal` when decimal exactness is required. Approximate `double` comparison using a tolerance is only appropriate when the tolerance is determined by the units, magnitude, and error of the problem; do not pick one fixed `epsilon` for every case.

## 8. BigDecimal, Division, and Rounding

`BigDecimal` does not support `+`/`*`/`/` operators like primitives; it has `add`, `subtract`, `multiply`, and `divide`. The division `10 / 3` is a non-terminating decimal: calling `new BigDecimal("10").divide(new BigDecimal("3"))` will throw `ArithmeticException` because it cannot be represented exactly with a finite number of digits. Specify scale and rounding rules according to business requirements.

For example, create the file `DecimalRoundingDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalRoundingDemo {
    public static void main(String[] args) {
        BigDecimal result = new BigDecimal("10")
                .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println(result.toPlainString());
    }
}
~~~

~~~bash
javac DecimalRoundingDemo.java
java DecimalRoundingDemo
~~~

Result:

~~~text
3.33
~~~

One more detail: `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false` because `equals` considers *scale* as well. `compareTo` between those two values returns 0 because they are numerically equal. Choose the appropriate comparison method, especially when using them as map keys or checking business conditions.

A system can also store prices in counts of the **smallest currency unit** using `long`, such as price converted to cents. This approach is appropriate if the unit, value range, and conversion rules are clearly specified; it does not automatically solve division, exchange rates, or arbitrary rounding.

## 9. Representation Selection Checklist

1. **Nature of data:** Is it a quantity to calculate, a measurement, a ratio, money, an identifier, or a date/time?
2. **Value range:** Minimum/maximum, can it be negative, can it grow without bound, could intermediate values exceed the range?
3. **Precision:** Do you need exact integers, exact decimals, or floating-point approximation? Is there a measured/designed tolerance?
4. **Operations:** Is there division, accumulation, tax calculation, repeated multiplication, or equality comparison? What are the overflow/rounding rules?
5. **Units and formatting:** Meters or km, seconds or milliseconds, VND or USD, code characters to preserve, input/output locale?
6. **Boundary values:** Test with 0, negative numbers, maximums, very large numbers, denominator 0, invalid input, accumulated error, and intermediate operations.

### Common Misconceptions

- "`double` has 64 bits so money is always exact": false, because it is **binary** floating-point.
- "When `int` overflows, Java automatically switches to `long`": false; you must widen the type before the operation or check for overflow.
- "All digits means it must be stored as a number": false; identifiers and phone numbers are usually text.
- "`BigDecimal` automatically chooses accounting rounding": false; you must set scale and `RoundingMode` according to the contract.
- "`float` has seven digits **after the decimal point**": false; you must understand **significant** digits.
- "A cast is a lossless conversion": false; narrowing types and converting to floating-point can lose information.
- "`BigInteger` is completely infinite": false; it is bounded by memory and computation cost of the runtime environment.

## 10. Self-Check Questions

1. A counter can grow up to 4 billion: is `int` or `long` more appropriate? Why?
2. Why should `"000045"` as an employee code be kept as a `String`?
3. When adding money `0.10` and `0.20`, why should you not default to `double`?
4. How do `5 / 2` and `5.0 / 2` differ?
5. A sensor has ±0.1 °C error: what needs to be clarified before comparing two measurements?
6. Given `int a, b`, why might `(long) (a * b)` already lose information, whereas `(long) a * b` can avoid it?

**Answer hints:** (1) `long` because 4 billion exceeds `int`; (2) leading zeros must be kept and codes do not use arithmetic operations; (3) `double` uses binary approximation while `BigDecimal` fits exact decimal requirements; (4) one expression does integer division yielding `2`, the other yields `2.5`; (5) units, sensor accuracy, and comparison tolerance; (6) the `int` multiplication can overflow **before** the cast, so an operand must be widened first.

**Takeaway:** Choosing a numeric type in Java is choosing a **representation model** for a quantity: meaning, value range, precision, units, operations, and rounding rules all affect program correctness.