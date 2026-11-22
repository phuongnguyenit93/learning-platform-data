# Map of Primitives, Wrappers, Number, BigInteger, and BigDecimal in Java

> **Topic:** Java core – numbers · **Group:** Overview  
> **Goal:** Identify Java's numeric type families, understand their relationships, choose the right storage/computation type, and avoid conversion errors, overflow, and decimal inaccuracies.

## 1. The Big Picture

Java has two common ways to represent numbers: **primitives** store a value directly as a primitive type; **objects** represent numbers through wrapper classes or numeric classes in the standard library. There is no single common "Number type" encompassing both primitives and objects.

```text
Numeric values in Java
├── Primitive (does not inherit Object/Number)
│   ├── Signed integers: byte, short, int, long
│   ├── Floating-point real numbers: float, double
│   └── char: unsigned 16-bit UTF-16 code unit, usable in some arithmetic operations
└── Reference / object
    ├── java.lang.Number (abstract class)
    │   ├── Byte, Short, Integer, Long
    │   ├── Float, Double
    │   └── java.math.BigInteger, java.math.BigDecimal
    └── Character (wrapper for char; does NOT extend Number)

boolean / Boolean: logical type, not a numeric type.
```

The tree above is a **conceptual map**, not an inheritance tree from primitives to wrappers. Primitive `int` is not a subclass of `Integer`; `Integer` is an object under the `Number` branch. `Character` and `Boolean` are wrappers but do not belong to the `Number` branch. Some other specialized classes also extend `Number`, though they are unnecessary for understanding this foundational set of numeric types.

## 2. Primitives: Foundational Types and Value Ranges

| Type | Size | Meaning and Notable Range | Example |
| --- | --- | --- | --- |
| `byte` | 8 bits | Signed integer: −128 to 127 | `byte b = 100;` |
| `short` | 16 bits | −32,768 to 32,767 | `short s = 32000;` |
| `int` | 32 bits | −2³¹ to 2³¹ − 1 | `int n = 1_000_000;` |
| `long` | 64 bits | −2⁶³ to 2⁶³ − 1 | `long n = 3_000_000_000L;` |
| `float` | 32 bits | IEEE 754 binary; typically about 6–7 significant decimal digits | `float f = 1.5f;` |
| `double` | 64 bits | IEEE 754 binary; typically about 15–16 significant decimal digits | `double d = 1.5;` |
| `char` | 16 bits | Unsigned UTF-16 code unit: 0 to 65,535; primarily represents characters | `char c = 'A';` |

**Distinguishing range and precision:** `float`/`double` can represent numbers with very large or very small absolute values, yet cannot represent every decimal number exactly. "15–16 digits" is a precision estimate, not a guarantee that an arbitrary decimal value will be preserved untouched.

- Addition, subtraction, and multiplication on `byte`, `short`, and `char` are normally promoted to `int` before producing a result; e.g., `byte x = 1, y = 2; int z = x + y;`. Assigning back to `byte` requires an explicit cast and accepting the risk of data loss.
- An `int * int` expression is evaluated as `int`, even if the target variable is `long`. At least one operand must be widened **before multiplication**.
- Use `L` (preferably uppercase) for `long` literals; `f` or `F` for `float` literals. Underscores in literals like `1_000_000` only aid readability.
- `boolean` does not participate in arithmetic; `char` can be promoted to `int`, yet is not a suitable choice for storing general numeric quantities.

**Integer overflow:** when a primitive integer operation exceeds the type's range, the result can wrap around according to bit representation without automatically signaling an error. `Math.addExact`, `Math.multiplyExact`, and related `*Exact` methods detect overflow and throw `ArithmeticException`. They do not widen the value range; if exceeding `long` is needed, use `BigInteger`.

## 3. Wrappers: Objects Corresponding to Primitives

| Primitive | Wrapper | Extends `Number`? |
| --- | --- | --- |
| `byte` | `Byte` | Yes |
| `short` | `Short` | Yes |
| `int` | `Integer` | Yes |
| `long` | `Long` | Yes |
| `float` | `Float` | Yes |
| `double` | `Double` | Yes |
| `char` | `Character` | No |
| `boolean` | `Boolean` | No |

Wrappers are **immutable** classes: the value inside an object cannot be modified after creation. A wrapper value can be `null` because it is a reference; a primitive cannot be `null`.

Java supports:

- **Boxing:** `int` → `Integer`; e.g., `Integer a = 42;`.
- **Unboxing:** `Integer` → `int`; e.g., `int b = a;`. If `a == null`, unboxing throws `NullPointerException`.
- **Explicit conversion:** `Integer.parseInt("42")` returns `int`, while `Integer.valueOf("42")` returns `Integer`. `Long.parseLong`, `Double.parseDouble`, etc. play analogous roles.

Wrappers are useful when an API requires objects: `List<Integer>` is valid, `List<int>` is invalid; when representing missing values with `null`; or when using an API that accepts `Number`. Arrays `int[]` and `Integer[]` are two distinct types; there is no automatic conversion of the whole array.

**Comparison:** `==` between two wrapper references compares object identity; `equals` compares values within the same wrapper type. Some wrappers maintain an object cache for small values, so `==` results can be misleading. For two `Integer` instances, use `a.equals(b)` if guaranteed non-null, or `Objects.equals(a, b)` if `null` is possible. Do not rely on `==` to conclude two wrapper objects have the same value.

**Overhead:** primitives are generally simpler for dense numeric data and tight computations. Boxing/unboxing inside loops or collections can introduce object overhead and `null` risk. Only optimize based on actual requirements and measurement.

## 4. What `Number` Is, and What It Is Not

`java.lang.Number` is the common **abstract class** of many number representation classes. It provides a contract for retrieving values as primitive types:

```java
Number value = Integer.valueOf(42);
int i = value.intValue();
double d = value.doubleValue();
```

Its primary methods are `byteValue()`, `shortValue()`, `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`. The first two may have default implementations based on `intValue()`; the remaining four form the core abstract contract of `Number`.

**Important limitations:**

1. `Number` is a reference type, so you cannot declare `Number n = 5;` and treat it as a primitive. Boxing allows assigning `5` as an `Integer` upcast to `Number`, yet `n` remains a reference.
2. You cannot write `n1 + n2` when both variables are declared as `Number`; `Number` does not define a polymorphic addition operator. Pick a concrete type or design explicit operations once exact requirements are known.
3. `intValue()`, `longValue()`, etc. are **conversions** that can truncate fractional parts, overflow, or round. They do not preserve arbitrary precision: e.g., converting a huge `BigInteger` to `long` drops the high bits.
4. `Number` does not give `BigDecimal`, `BigInteger`, and `Double` the same comparison rules or representational capability. Do not force every number into `double` just to process through a common interface.

Brief example: a statistics API accepting `Number` might read `doubleValue()` if loss of precision is acceptable. An accounting API calculating money should expose `BigDecimal` in its contract and avoid casting to `double`.

## 5. `BigInteger`: Large Integers of Arbitrary Precision

`java.math.BigInteger` represents **signed integers** beyond the fixed range of `long`. Magnitude is primarily bounded by memory and processing cost rather than a 64-bit primitive limit. It is an immutable object and extends `Number`.

```java
import java.math.BigInteger;

BigInteger population = new BigInteger("9223372036854775808");
BigInteger next = population.add(BigInteger.ONE);
BigInteger squared = next.multiply(next);
```

Common operations: `add`, `subtract`, `multiply`, `divide` (integer quotient), `remainder`, `pow` (non-negative integer exponent), `gcd`, `compareTo`. `mod` takes a positive divisor and yields a non-negative remainder; distinguish it from `remainder` when working with negative numbers. Each operation returns a new result; calling `population.add(BigInteger.ONE)` and discarding the result **does not mutate** `population`.

Create instances using `new BigInteger("...")` for large string numbers, or `BigInteger.valueOf(123L)` for values already fitting in `long`. Use `toString()` for output and `intValueExact()`/`longValueExact()` when you want `ArithmeticException` thrown if the value does not fit the target type. Plain `intValue()`/`longValue()` can drop high-order bits silently.

**When to choose:** huge integer counts, large combinatorics/permutations, integer-arithmetic algorithms. If `long` already suffices and runs in a performance-critical loop, there is no default reason to move everything to `BigInteger`.

## 6. `BigDecimal`: Exact Base-10 Decimal Numbers

`java.math.BigDecimal` represents a decimal number via an **unscaled integer value** and a **scale**: mathematically, value = `unscaledValue × 10^(-scale)`. For example, `"12.340"` has unscaled value `12340` and scale `3`. It is immutable, extends `Number`, and supports programmer-controlled decimal precision.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.90");
BigDecimal tax = new BigDecimal("1.99");
BigDecimal total = price.add(tax); // 21.89

BigDecimal oneThird = BigDecimal.ONE.divide(
    new BigDecimal("3"), 2, RoundingMode.HALF_UP
); // 0.33
```

**Proper initialization matters greatly:**

- `new BigDecimal("0.1")` represents the exact decimal `0.1`.
- `BigDecimal.valueOf(0.1)` uses `double`'s string form and yields `0.1` in this example; useful when the input is already a `double`, though it cannot recover intent or precision already lost earlier.
- `new BigDecimal(0.1)` receives the **actual binary value** of the `double` literal; the result is not equal to exact decimal `0.1`. Avoid this when the source is money or a specified decimal.
- `BigDecimal.valueOf(123L)` is handy for small integers; use strings for decimal literals requiring exactness.

**Arithmetic and rounding:**

- `add`, `subtract`, and `multiply` do not require rounding if no `MathContext` is passed, though the result gets a scale/precision dictated by the operation.
- Division can yield an infinite decimal expansion: `BigDecimal.ONE.divide(new BigDecimal("3"))` throws `ArithmeticException` if no rounding rule is specified. Choose scale + `RoundingMode`, or an appropriate `MathContext` for the business rules.
- `setScale(2, RoundingMode.HALF_UP)` adjusts the number of digits after the decimal point; `MathContext(precision, roundingMode)` limits **total significant digits**, not digits after the decimal point.
- No single rounding rule fits every application. `HALF_EVEN` vs. `HALF_UP` depends on standards and business regulations; for currency, decimal places also depend on the currency/unit and workflow.

**Comparison and map keys:**

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));           // false
System.out.println(x.compareTo(y) == 0);    // true
```

`equals` considers **both value and scale**; `compareTo` compares numeric value. Consequently, a `BigDecimal` used as a `HashMap` key or `HashSet` element must have a clear scale-normalization rule if business logic treats `1.0` and `1.00` as equivalent. `stripTrailingZeros()` can turn scale into 0 or negative, so do not assume display formatting will remain unchanged. `toPlainString()` is useful when wanting a decimal string without scientific notation.

## 7. Choosing a Type by Requirement

| Situation | Usually Suitable Choice | Main Reason |
| --- | --- | --- |
| Counters/indices/integer codes fitting 32-bit range | `int` | Natural in Java, lightweight, easy to use |
| Integers needing 64-bit range | `long` | Wider range than `int` yet still finite |
| Raw data/binary formats requiring 8 or 16 bits | `byte`, `short` | Matches protocol/format; does not mean all arithmetic runs in 8/16 bits |
| Scientific measurements, graphics, statistics tolerating approximation | `double` (or `float` with reason) | Speed and floating-point real-number range |
| Integers exceeding `long` needing exact operations | `BigInteger` | Does not overflow at the 64-bit boundary |
| Money, unit prices, decimal rates with clear rounding rules | `BigDecimal` | Exact decimal representation and controlled rounding |
| Generic API needing to accept a family of number objects | `Number` | Common conversion contract; does not imply generic exact arithmetic |
| Collections/generics or potentially missing data | Corresponding wrapper | Object, can be `null`; watch out for unboxing |

Do not use `BigDecimal` merely because `double` is "not big enough": the two types solve two different problems—**binary approximate reals** vs. **decimals with controlled precision/rounding**. Likewise, do not use `BigInteger` in place of `BigDecimal` if calculations involve a fractional part.

## 8. Standalone Java 17+ Example: Connecting the Full Map

Create the file `NumberMapDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberMapDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer wrapper = Integer.valueOf(primitive);
        Number general = wrapper;

        BigInteger huge = new BigInteger("9223372036854775808");
        BigInteger next = huge.add(BigInteger.ONE);

        BigDecimal decimal = new BigDecimal("0.10")
                .add(new BigDecimal("0.20"));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("primitive=" + primitive);
        System.out.println("wrapper=" + wrapper);
        System.out.println("Number->int=" + general.intValue());
        System.out.println("BigInteger=" + next);
        System.out.println("BigDecimal=" + decimal.toPlainString());
        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + (a.compareTo(b) == 0));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac NumberMapDemo.java
java NumberMapDemo
```

Standard output:

```text
primitive=42
wrapper=42
Number->int=42
BigInteger=9223372036854775809
BigDecimal=0.30
equals=false
compareTo=true
```

Meaning: `int` is boxed into `Integer` and referenced via `Number`; `BigInteger` exceeds the `long` range; `BigDecimal` addition preserves scale in the result `0.30`; two decimals that are numerically equal yet differ in scale representation produce different `equals` results.

## 9. Testing Common Mistakes: Overflow, Rounding Error, and Unboxing

Create the file `NumericPitfalls.java`:

```java
import java.math.BigDecimal;

public class NumericPitfalls {
    public static void main(String[] args) {
        int amount = 1_500_000_000;
        long overflowed = amount * 2;
        long safe = (long) amount * 2;

        double binary = 0.1 + 0.2;
        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        System.out.println("overflowed=" + overflowed);
        System.out.println("safe=" + safe);
        System.out.println("double=" + binary);
        System.out.println("decimal=" + exact.toPlainString());

        Integer maybeMissing = null;
        try {
            int value = maybeMissing; // unboxing null
            System.out.println(value);
        } catch (NullPointerException e) {
            System.out.println("unboxing=null -> NullPointerException");
        }
    }
}
```

```bash
javac NumericPitfalls.java
java NumericPitfalls
```

Output:

```text
overflowed=-1294967296
safe=3000000000
double=0.30000000000000004
decimal=0.3
unboxing=null -> NullPointerException
```

Explanation: `amount * 2` is evaluated in 32 bits before assigning to `long`; casting `(long) amount` before multiplication makes the multiplication happen in 64 bits. `0.1` and `0.2` as `double` are not represented with absolute exactness in binary; the two strings `"0.1"` and `"0.2"` in `BigDecimal` preserve the intended decimal values. Finally, a wrapper reference can be `null`, and the error surfaces at unboxing.

## 10. Misconceptions to Avoid

1. **"Every number is a `Number`."** False: primitives inherit no class, and `char`/`Character` do not belong to the `Number` branch.
2. **"Wrappers are identical to primitives."** False: wrappers are objects, having `null`, methods, object identity, and associated overhead.
3. **"Assigning to `long` avoids every `int` overflow."** False if the expression before assignment is still evaluated as `int`.
4. **"`double` is exact for any monetary amount because it has many digits."** False: binary representation of many decimal fractions is approximate.
5. **"`new BigDecimal(0.1)` is equivalent to `new BigDecimal("0.1")`."** False: the `double` argument already carries an approximate binary value.
6. **"`BigDecimal.divide` always works."** False: division without a finite decimal representation may require specifying rounding.
7. **"Every numeric `equals` is consistent across classes."** False: wrappers of different types and `BigDecimal` values with different scales have their own `equals` rules.
8. **"Converting via `Number.doubleValue()` is lossless."** False for very large integers and many decimals; converting to a primitive can round or overflow.
9. **"Calling `add` modifies `BigInteger`/`BigDecimal`."** False: both are immutable; the returned result must be saved.
10. **"`float`/`double` only contain finite numbers."** False: there are also `NaN`, positive/negative infinity, and signed zeros. These cases must be handled explicitly during validation and comparison.

## 11. Checklist When Designing a Numeric Value

- Does the value have a fractional part? If so, does the application tolerate **binary approximation** or require **exact decimal with rounding**?
- Do the minimum/maximum integers fit in `int` or `long`? Do you need overflow detection or an arbitrary integer range?
- Does the API need primitives or objects? Is `null` allowed, and where does unboxing occur?
- Is there any lossy `Number` → primitive conversion?
- For `BigDecimal`: is the input source a string or `double`; where are scale, rounding, `equals`/`compareTo`, and display formatting rules decided?
- For data placed into collections/maps, are equality and normalization rules consistent?

**Map takeaway:** `int/long/double` handle primitive arithmetic within finite ranges; wrappers provide objects for those values; `Number` is a common point to **read/convert** numbers across classes; `BigInteger` solves **very large integers**; `BigDecimal` solves **exact decimals with scale/rounding rules**.