# Integers, Floating-Point Numbers, and Exact Decimals in Java

In Java, "number" is not a single type. Choosing a data type means choosing a **value range**, **representation**, **precision level**, and **calculation rules**. The three groups to distinguish are integers, binary floating-point numbers, and exact decimals (with `BigDecimal`). This lesson focuses on meaning, practical behavior, and how to pick the right one for each calculation.

## 1. Quick Selection Map

| Need | Types to Consider | Reasons and Limitations |
| --- | --- | --- |
| Counting, array indices, integer quantities within a known range | `int`, `long` | Exact integer arithmetic **within the type's range**; overflow must be controlled. |
| Integers larger than `long` | `BigInteger` | Arbitrary magnitude bounded by memory; operations via methods, cannot use `+` on objects. |
| Measurements, simulations, graphics, scientific data tolerating binary rounding error | `double` (or `float` with clear justification) | Fast, supports special values; many decimal fractions are not represented exactly. |
| Money, taxes, unit prices, decimal calculations needing transparent rounding rules | `BigDecimal` | Stores decimal significand and scale; still must decide precision/rounding when division does not terminate. |
| Monetary amounts in the smallest unit, with a fixed scale | `long` or `BigInteger` | Can represent whole dong/xu/cents accurately; must specify unit, range, and conversion method. |

No type automatically solves every business requirement: even when using `BigDecimal`, the application still needs rounding rules, units, scale, and when to round.

## 2. Integers: Exact Within the Representation Range

### 2.1. Primitive Integer Types

| Type | Bits | Minimum Value | Maximum Value |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32,768 | 32,767 |
| `int` | 32 | -2,147,483,648 | 2,147,483,647 |
| `long` | 64 | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

These types are signed and use two's complement representation. `char` is an unsigned 16-bit character type and should not be chosen as a counting number type. Wrapper classes `Byte`, `Short`, `Integer`, `Long` are objects, differing from primitives in `null`, boxing, and allocation overhead.

Integer literals default to `int`; append `L` to create a `long` literal. Java allows binary with `0b`, hexadecimal with `0x`, octal with a `0` prefix, and underscores for readability:

```java
int population = 1_250_000;
long distance = 9_000_000_000L;
int mask = 0b1010_0001;
int color = 0xFF_A0_10;
```

These are illustrative declarations, not a standalone runnable program. Omitting `L` on a large `long` integer value causes the compiler to reject the literal because it attempts to parse it as `int` first. Additionally, a leading `0` on an integer literal means octal, so `010` is 8, not 10.

### 2.2. Overflow and How to Prevent It

Addition, subtraction, and multiplication on `int`/`long` do not automatically throw exceptions on overflow; the result wraps around according to the bit width. For example, `Integer.MAX_VALUE + 1` gives `Integer.MIN_VALUE`. Assigning the result to `long` **after** computing does not save an operation that has already overflowed:

```java
int count = 1_500_000_000;
long wrong = count * 2;          // int multiplication already overflowed before assignment.
long correct = (long) count * 2; // Widen one operand before multiplication.
```

When overflow is treated as an error, use `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `toIntExact`, or `negateExact` where appropriate. They throw `ArithmeticException` when the result cannot be represented. Choose `long` if data exceeds `int` yet fits in 64 bits; choose `BigInteger` when no finite bound is appropriate.

### 2.3. Integer Division, Remainder, and Negative Numbers

When both operands are integers, `/` is **integer division, truncating the fractional part toward 0**, and `%` is the remainder operation; a denominator of 0 causes `ArithmeticException`.

| Java Expression | Result | Explanation |
| --- | ---: | --- |
| `7 / 2` | `3` | Drops fractional part. |
| `7 / 2.0` | `3.5` | One operand is `double`. |
| `-7 / 3` | `-2` | Rounds toward 0. |
| `-7 % 3` | `-1` | Remainder with the sign of the dividend. |
| `Math.floorDiv(-7, 3)` | `-3` | Division rounding down (floor). |
| `Math.floorMod(-7, 3)` | `2` | Matches floor rule when divisor is positive. |

With `byte` or `short`, arithmetic operators normally promote operands to `int`, so `byte b = 10; b = b + 1;` does not compile without a cast; `b++` has its own implicit conversion mechanism. Narrowing casts (`(int) aLong`, `(byte) anInt`) can drop bits and change the value; do not treat a cast as a range check.

### 2.4. Arbitrary-Magnitude Integers: BigInteger

`java.math.BigInteger` stores integers without fixed 32/64-bit limits and is immutable. Construct from a string to avoid `long` literal limits, then use `add`, `subtract`, `multiply`, `divide`, `remainder`, `pow`, `gcd`, and `compareTo`:

```java
BigInteger huge = new BigInteger("9223372036854775808");
BigInteger next = huge.add(BigInteger.ONE);
boolean larger = next.compareTo(huge) > 0;
```

The snippet above requires `import java.math.BigInteger;`. `add` returns a new object: calling `huge.add(BigInteger.ONE);` without capturing the result leaves `huge` unchanged. `BigInteger` suits counts or integer operations beyond `long`, but cannot hold a fractional part.

## 3. Floating-Point Numbers: Binary Approximation

### 3.1. What Do float and double Store?

Java uses the IEEE 754 standard for 32-bit `float` and 64-bit `double`. Each finite value is represented by sign, exponent, and binary significand; `float` has roughly 6–7 significant decimal digits, and `double` has roughly 15–16 significant digits. `double` has a larger range and higher precision, usually serving as the default choice for real-number calculations where binary error is permitted. The literal `0.1` has type `double`; `0.1f` has type `float`.

Many fractions that appear simple in base 10, such as 1/10, have no finite binary representation. Therefore:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

These lines are an illustrative snippet placed inside `main`. The error does not mean the JVM added "wrongly"; the operation rounded to the nearest `double` value to the mathematical expression according to the type's rules. Addition order of floating-point numbers can change the result: due to rounding after each step, floating-point arithmetic is generally not associative like mathematical real numbers.

### 3.2. Special Values and Comparison

Floating point has `NaN` (not a number), `POSITIVE_INFINITY`, `NEGATIVE_INFINITY`, `+0.0`, and `-0.0`:

- `1.0 / 0.0` produces `Infinity`, `0.0 / 0.0` produces `NaN`; unlike integer division by 0.
- `NaN == NaN` is `false`. Test using `Double.isNaN(value)` or `Float.isNaN(value)`; test for finite values using `Double.isFinite(value)`.
- `-0.0 == 0.0` is `true`, though some operations and `Double.compare(-0.0, 0.0)` distinguish the sign (`Double.compare` returns a negative number).
- `Double.compare` establishes a total order for sorting per Java's rules, but does not replace approximate comparison criteria in scientific computation.

Avoid comparing two floating-point calculation results with `==` when the problem's meaning is "approximately equal". A basic approach is checking `Math.abs(a - b) <= tolerance`, with an absolute threshold appropriate to **units and scale**. Over wide value ranges, combine absolute and relative thresholds; define how to handle `NaN`, infinity, values very close to 0, and subtraction overflow risk. There is no single fixed `epsilon` that works correctly for every program.

### 3.3. Rounding and Printing Results

Functions `Math.round`, `Math.floor`, and `Math.ceil` have their own rules and do not turn a `double` into an exact decimal. `System.out.printf` or `String.format` can **format display output**, yet the underlying storage remains binary:

```java
System.out.printf(java.util.Locale.US, "%.2f%n", 1.235);
```

The statement above displays two digits after the decimal point according to floating-point formatting rules; avoid concluding that the displayed string proves financial calculations were done in exact decimal. Locale affects the decimal separator and grouping symbol when formatting; internal data and interchange data should have clear conventions.

## 4. BigDecimal: Exact Decimal Values with Scale Rules

### 4.1. Value Model

`BigDecimal` represents finite numbers in the form **unscaledValue × 10^(-scale)**: an integer coefficient without a fixed limit and a 32-bit integer `scale`. For example, `2.50` has unscaled value 250 and scale 2. Unlike `double`, the decimal string `"0.1"` can be stored exactly.

Create `BigDecimal` from a **string**, or use `BigDecimal.valueOf(double)` if the input is already a `double` and you intentionally want the canonical decimal representation of that exact value:

```java
BigDecimal precise = new BigDecimal("0.1");
BigDecimal fromDouble = BigDecimal.valueOf(0.1);
BigDecimal exposedBinary = new BigDecimal(0.1);
```

`precise` and `fromDouble` both have decimal value `0.1` in this example. `exposedBinary` carries the exact decimal value of the binary `double` near 0.1, typically a long string; avoid `new BigDecimal(0.1)` when expecting the monetary value 0.1. `BigDecimal.valueOf(0.1 + 0.2)` cannot recover the intent `0.3` after `double` addition has already rounded to `0.30000000000000004`.

You can use `BigDecimal.ZERO`, `ONE`, `TEN`, or `BigDecimal.valueOf(long)`. Do not use `+`, `-`, `*`, `/` operators directly between `BigDecimal` instances; use methods and capture the returned value.

### 4.2. Four Operations and the Division Problem

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);                       // 0.3
BigDecimal difference = b.subtract(a);          // 0.1
BigDecimal product = a.multiply(b);             // 0.02
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("8"));                   // 0.125, terminates finitely
```

This is a code snippet; add `import java.math.BigDecimal;` and place inside a method when running. Addition, subtraction, and multiplication can produce exact decimal results (within machine resource limits). However, **1/3 has no finite decimal representation**. `BigDecimal.ONE.divide(new BigDecimal("3"))` without a rounding mode will throw `ArithmeticException` because it asks for an exact result.

When a result does not terminate, specify the number of digits after the decimal point and the rounding mode:

```java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP); // 0.33
```

This snippet needs `import java.math.RoundingMode;`. Do not assume `HALF_UP` is automatically "financially correct": the rule could be `HALF_EVEN` (round ties to even digit), `DOWN`, `UP`, `CEILING`, `FLOOR`, etc., depending on the contract or business standard. Choose the right sign handling, midpoint tie-breaking, and where rounding is applied.

### 4.3. Scale vs. Precision

- **Scale**: number of digits to the right of the decimal point in the representation (`12.340` has scale 3); scale can be negative.
- **Precision**: number of digits of the unscaled integer as computed by `BigDecimal.precision()` (`12.340` has precision 5).
- `setScale(2, mode)`: sets the number of decimal places of the result; if digits must be discarded, `RoundingMode` is required.
- `MathContext(precision, mode)`: limits the number of **significant digits** when performing operations with the context; does not mean always taking that many digits after the decimal point.

```java
BigDecimal price = new BigDecimal("12.345");
BigDecimal cents = price.setScale(2, RoundingMode.HALF_EVEN); // 12.34
BigDecimal significant = price.round(
        new MathContext(3, RoundingMode.HALF_EVEN));          // 12.3
```

This snippet requires `import java.math.MathContext;` and `import java.math.RoundingMode;`. `BigDecimal` is immutable: `price.setScale(2, ...)` does not mutate `price`; you must assign the result. Rounding each invoice line before summing versus rounding once at the total can differ; business rules must state which clearly.

### 4.4. equals, compareTo, and Display

`new BigDecimal("2.0").equals(new BigDecimal("2.00"))` returns `false` because `equals` examines **both value and scale**. `compareTo` returns 0 because the two numbers have the same mathematical value. Therefore, value equality checks should use `compareTo(...) == 0` when scale is not significant:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");
boolean sameRepresentation = x.equals(y);   // false
boolean sameNumericValue = x.compareTo(y) == 0; // true
```

Accordingly, `HashSet<BigDecimal>` uses `equals`/`hashCode`, whereas ordered structures like `TreeSet<BigDecimal>` typically examine `compareTo`; thus two strings representing different scales may be treated differently. `stripTrailingZeros()` can change scale (even to negative scale). Use `toPlainString()` when you want a plain decimal string and want to avoid scientific notation for values that can be formatted that way; the output scale still needs to be specified.

`BigDecimal` cannot carry `NaN` or infinity; if receiving a non-finite `double` to convert to `BigDecimal`, check and handle it beforehand.

## 5. Standalone Java 17+ Program

Save the following as **`NumericDemo.java`**. This example picks calculations with deterministic results and output to highlight differences across integer, floating point, `BigInteger`, and `BigDecimal`.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericDemo {
    public static void main(String[] args) {
        System.out.println("int-division=" + (7 / 2));
        System.out.println("real-division=" + (7 / 2.0));

        System.out.println("int-overflow=" + (Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("checked-overflow=detected");
        }

        System.out.println("floating-sum=" + (0.1 + 0.2));
        System.out.println("floating-equal=" + ((0.1 + 0.2) == 0.3));
        System.out.println("nan=" + Double.isNaN(0.0 / 0.0));

        BigDecimal oneTenth = new BigDecimal("0.1");
        BigDecimal twoTenths = new BigDecimal("0.2");
        System.out.println("decimal-sum=" + oneTenth.add(twoTenths));
        System.out.println("third=" + BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP));

        BigDecimal first = new BigDecimal("2.0");
        BigDecimal second = new BigDecimal("2.00");
        System.out.println("scale-equals=" + first.equals(second));
        System.out.println("value-equal=" + (first.compareTo(second) == 0));

        BigInteger beyondLong = new BigInteger("9223372036854775808");
        System.out.println("big-integer=" + beyondLong.add(BigInteger.ONE));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac NumericDemo.java
java NumericDemo
```

Stdout output:

```text
int-division=3
real-division=3.5
int-overflow=-2147483648
checked-overflow=detected
floating-sum=0.30000000000000004
floating-equal=false
nan=true
decimal-sum=0.3
third=0.33
scale-equals=false
value-equal=true
big-integer=9223372036854775809
```

Explanation: `7 / 2` drops the fractional part via integer division, while `7 / 2.0` uses `double`; `int` addition wraps on overflow while `Math.addExact` detects it; `0.1 + 0.2` rounds in binary; `BigDecimal` built from strings adds to exact `0.3`. The two representations `2.0` and `2.00` have the same mathematical value but different scales. `BigInteger` handles values greater than `Long.MAX_VALUE`.

## 6. Conversion Rules and Common Mistakes

| Situation | What Can Happen? | How to Handle |
| --- | --- | --- |
| `int` addition/multiplication exceeds limits | Silent overflow | Analyze data range; use `long`, `BigInteger`, or `Math.*Exact`. |
| Multiply two `int`s then assign to `long` | Already overflowed in multiplication step | Widen at least one operand to `long` **before** the operation. |
| `int / int` then assign to `double` | Fractional part already dropped | Use `(double) numerator / denominator` if real division is wanted. |
| Store money in `double` | Representation or calculation error | Create `BigDecimal` from original decimal string/data; or store smallest monetary unit as integer. |
| `new BigDecimal(someDouble)` | Exposes approximate binary value | Accept original decimal string; use `valueOf` when intentionally converting via `Double.toString`. |
| `BigDecimal.divide` without rounding specified | Can throw `ArithmeticException` on repeating infinite results | Specify scale or `MathContext` and `RoundingMode`. |
| Compare with `BigDecimal.equals` | `2.0` differs from `2.00` | Use `compareTo == 0` to compare value independent of scale. |
| Ignore return value of `add`/`setScale` | Original object is unchanged | Assign or return the new object. |
| Cast `double` to `int`/`long` | Drops fractional part, NaN becomes 0, out-of-range values clamped to boundary per cast rules | Check finiteness, range, and rounding rule before converting. |
| Call `Double.parseDouble` or `new BigDecimal(text)` on invalid data | `NumberFormatException` | Validate input; standardize decimal convention and locale at the interface layer. |

**On conversions:** converting `int` to `double` is generally exact for every `int` value, but not every `long` can be represented exactly as a `double` (finite significand precision). Converting `BigDecimal` to `double` via `doubleValue()` can also lose digits or exceed range. Do not treat string formatting as a substitute for exact calculation.

**On monetary data:** for example, an amount `"19.99"` can be constructed with `new BigDecimal("19.99")`. When multiplying by an integer quantity, use `price.multiply(BigDecimal.valueOf(quantity))`. The application must define currency/unit, valid scale, rounding mode for tax/discount/allocation, negative value handling, and line-total reconciliation. A single `BigDecimal` does not carry a currency code and does not pick accounting rules automatically.

## 7. Self-Check Your Knowledge

1. Why can `long total = 2_000_000_000 * 2;` produce a wrong result, whereas `long total = 2_000_000_000L * 2;` does not overflow in this multiplication? Point out the **types of operands before multiplication occurs**.
2. Predict and verify `-7 / 3`, `-7 % 3`, `Math.floorDiv(-7, 3)`, and `Math.floorMod(-7, 3)`.
3. Why is `0.1 + 0.2 == 0.3` `false`, while `new BigDecimal("0.1").add(new BigDecimal("0.2"))` has exact value `0.3`?
4. Write the division `1 / 3` with `BigDecimal` to four digits after the decimal point, state the rounding mode, and explain why `divide` without a rounding rule can throw an error.
5. Compare `new BigDecimal("10.0")` and `new BigDecimal("10.00")` with `equals` and `compareTo`. In a program using `HashSet` and `TreeSet`, how does that difference affect behavior?
6. Design an invoice total calculation with decimal unit price, quantity, discount, and tax. State when rounding occurs, scale, currency unit, and tests for midpoint cases; do not use `double` for money.

## 8. Key Points to Remember

- **Integers** are exact within the type's range, though overflow must be actively controlled; `BigInteger` is for integers beyond `long`.
- **`float`/`double`** represent binary approximate real numbers; suited for problems with acceptable error, needing approximate-comparison policies and `NaN`/infinity handling.
- **`BigDecimal`** represents exact finite decimals when initialized properly; division and business constraints still require precision, scale, and rounding policies.
- The right data type is determined by value range, units, required precision, and problem rules—not merely by whether the program compiles cleanly.