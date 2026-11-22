# Choosing Primitive, Wrapper, BigInteger, or BigDecimal in Java

## 1. Goal: Choose Numeric Types by Requirement, Not Habit

Java has multiple ways to represent numeric data: **primitive** types, **wrapper** classes, `BigInteger`, and `BigDecimal`. No single type is "best for every case." Type selection should be based on **value range**, **precision**, **units**, **nullability/presence**, **API usage**, and **execution cost**.

This lesson is a reference table for choosing the right numeric type when declaring variables, field types, parameters, computation results, collection keys, and interchange data. Core criteria:

1. **Integer or decimal?** Quantities, sequences, and indices are usually integers; prices, rates, and measurements may need fractional parts.
2. **Absolute exactness or approximation?** Do not use `double` instead of `BigDecimal` when even a single digit of monetary error is unacceptable.
3. **Are there upper/lower bounds?** `int` and `long` have fixed limits; `BigInteger` scales according to resources.
4. **Do you need to represent missing data?** Primitives cannot hold `null`; wrappers can hold `null` but require avoiding unchecked unboxing.
5. **Working with generics/collections/frameworks?** `List<int>` is invalid in Java 17; `List<Integer>` is valid.
6. **Storage types and intermediate calculation types can differ.** The final result may fit in `int`, while an intermediate sum or product requires `long` or `BigInteger`.

## 2. Quick Selection Table — Typical Cases

| Need | Choice to Consider | Why | Pitfall to Avoid |
| --- | --- | --- | --- |
| Counters, indices, small quantities within 32-bit range | `int` | Compact primitive, simple arithmetic, non-null | Sums/products of multiple `int` values can still overflow |
| Large sums, timestamps, or integers within 64-bit range | `long` | Wider range than `int` | `long` still has limits; addition/multiplication can still overflow |
| Values restricted to byte or short by protocol/schema | `byte`, `short` | Matches external range/format | `byte`/`short` arithmetic is usually promoted to `int` |
| Representing UTF-16 code units | `char` | 16-bit primitive for code units | Do not use `char` as a numeric type just because it is unsigned |
| Measurements, graphics, statistics tolerating approximation | `double` | Standard floating point, good speed | 0.1 is not stored exactly; has NaN/Infinity/-0.0 |
| Data or API explicitly requiring 32-bit float | `float` | Smaller footprint, matches protocol | Lower precision than `double`; avoid using by default |
| Integers needing `null` or entering `List<T>`, `Map<K,V>` | `Integer`, `Long`, and matching wrappers | Object types supporting generics, nullable | Boxing/unboxing, `==`, `NullPointerException` |
| Exact integers exceeding `long` | `BigInteger` | No fixed 64-bit limit | Object overhead; use `add`/`multiply` instead of operators |
| Exact decimals, money, and rule-based rounding | `BigDecimal` | Decimal system with scale and explicit rounding methods | Division must handle repeating quotients; `equals` checks scale |
| Possibly absent integer/real without wanting `null` | `OptionalInt`, `OptionalLong`, `OptionalDouble` (especially in result APIs) | Clearly expresses presence/absence of a value | Not a numeric type used for arithmetic like primitives |
| Money settled in smallest units, fitting 64-bit range | `long` cents (domain-specific) | Exact integer with fixed unit | Tax/percentages may require intermediate `BigDecimal` |
| Digit-based IDs, possibly with leading zeros, not for math | `String` | Preserves identifier and leading zeros | Do not pick `int`/`long` just because it looks like a number |

These are **recommendations based on domain contracts**, not a mandate to use a single type everywhere. For instance, `Long` is reasonable for a nullable column if the schema allows missing values, whereas `long` is better for a mandatory counter.

## 3. Capability Matrix of the Main Choices

| Criterion | Integer Primitives `int/long` | Floating Primitives `float/double` | Wrappers `Integer/Long/Double/...` | `BigInteger` | `BigDecimal` |
| --- | --- | --- | --- | --- | --- |
| `null` value | No | No | Yes | Reference variable can be null, though null is not a number | Reference variable can be null, though null is not a number |
| Range | Fixed by bit width | Fixed by IEEE 754 | Same as corresponding primitive | Flexible magnitude limited by resources | Flexible decimal magnitude limited by resources |
| Exact integers | Yes within range | Only certain ranges and magnitudes; not every `long` | Follows wrapped primitive | Yes | Can represent exact integers |
| Exact decimals | Does not represent fractions | Generally not decimally exact | Wrappers of `float/double` are also approximate | Integers only | Yes for values with finite decimal representation |
| Arithmetic with `+ - * /` | Yes | Yes | Yes via unboxing (with null risk) | No; use methods | No; use methods |
| Direct use in `List<T>` | No | No | Yes | Yes | Yes |
| Creates many objects during math | No for pure primitive values | No for pure primitive values | May trigger boxing | Operations create new result objects | Operations create new result objects |
| Decimal rounding control | Not applicable | Floating-point rules, not business decimal | Same as primitive | No fractional part | Uses `scale`, `MathContext`, `RoundingMode` |
| Common hazards | Overflow, integer division | Precision error, NaN/Infinity | Null unboxing, `==` comparison | Incorrect narrowing conversion | Using `double` constructor, scale/rounding, `equals` |

Immutability: `BigInteger`, `BigDecimal`, and standard numeric wrappers are immutable. For example, `total.add(value)` does not modify `total`; you must reassign the result. Primitives are not objects, so they have no shared reference state like wrappers.

## 4. Text Decision Tree

```text
Is the input truly a numeric value for calculation?
  ├─ No: codes, IDs, account numbers, postal codes... → consider String
  └─ Yes
      ├─ Is a fractional part needed?
      │   ├─ No, integer only
      │   │   ├─ Fits in int and no null/generics needed? → int
      │   │   ├─ Fits in long and no null/generics needed? → long
      │   │   ├─ Exceeds long but must be exact? → BigInteger
      │   │   └─ Needs null/generics? → wrapper matching range (Integer/Long...)
      │   └─ Yes
      │       ├─ Must have exact decimal / business rounding? → BigDecimal
      │       └─ Tolerates IEEE 754 approximation? → double (or float when justified)
      └─ Before storing/returning via API:
          validate range, units, null, rounding, and exact conversions
```

Note that a single value can carry multiple constraints simultaneously. For example, "monetary amount must be exact yet stored in a `List`" does not mean choosing `Double`: you can choose `List<BigDecimal>`. An "optional integer value" can be represented by `OptionalInt` at a return boundary or by nullable `Integer` as required by a framework.

## 5. Primitives: int, long, float, and double

### 5.1. Signed Integers: byte, short, int, long

| Type | Bits | Min | Max |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32,768 | 32,767 |
| `int` | 32 | -2,147,483,648 | 2,147,483,647 |
| `long` | 64 | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

In many arithmetic expressions, `byte`, `short`, and `char` are promoted to `int`; storing a field in a small type does not mean every calculation stays in that type.

`int` is a good default for counters/indices with well-defined bounds. `long` fits when the range exceeds `int`. However, **beware that a calculation can overflow before being assigned to a wider type**:

```java
int quantity = 50_000;
int price = 50_000;

long wrong = quantity * price;         // -1794967296
long right = (long) quantity * price;  // 2500000000
```

Both lines compile; only the second multiplies in `long`. If you want overflow checks rather than wraparound, use `Math.addExact`, `Math.multiplyExact`, `Math.subtractExact`, and their matching overloads.

### 5.2. Binary Floating-Point: float, double

`double` is a 64-bit floating-point number with roughly 53 bits of significand; `float` is 32-bit with roughly 24 bits of significand. They can represent very large and very small numbers, yet **cannot represent every decimal number exactly**.

```java
double result = 0.1 + 0.2;
// Typically prints 0.30000000000000004, not exact decimal 0.3
```

These types have `NaN`, `+Infinity`, `-Infinity`, `+0.0`, and `-0.0`, plus a subnormal region near 0. `Double.isFinite(value)` checks whether a value is finite, but does not assess business precision.

**Do not choose `double` as a "very large integer"**: every integer up to 2^53 is represented exactly, but integers beyond that are no longer guaranteed to be exact. `long` keeps integers within its range completely exact, even though its magnitude range is smaller than part of `double`'s range.

`float` is not inherently more accurate because of its shorter name. Use `float` only when protocol, memory, GPU data, or an API explicitly requires 32-bit, or after measuring and weighing precision trade-offs.

## 6. Wrappers: Integer, Long, Double, and Autoboxing

Each numeric primitive has a corresponding wrapper:

| Primitive | Wrapper |
| --- | --- |
| `byte` | `Byte` |
| `short` | `Short` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |
| `char` | `Character` |

`Boolean` is also the wrapper for `boolean`, but it is not a numeric type; do not include it in the options for numeric data.

Wrappers are objects and allow:

- Representing `null` when the domain or framework permits missing data.
- Using with generics such as `List<Integer>`, `Map<Long, String>`.
- Calling utility methods: `Integer.parseInt`, `Integer.valueOf`, `Long.compare`, `Double.isFinite`, `Integer.toString`.
- Satisfying APIs that accept objects instead of primitives.

Java supports **autoboxing** (converting primitive to wrapper) and **unboxing** (converting wrapper to primitive):

```java
int primitive = 42;
Integer boxed = primitive; // autoboxing
int unboxed = boxed;       // unboxing
```

However, `Integer nullable = null; int x = nullable;` causes `NullPointerException` on unboxing. Also do not use the `==` operator to compare values of two wrapper references: `==` on two wrapper objects can compare **object identity**; results for certain values may be affected by boxing caches. Use `Objects.equals(a,b)` when either side may be null, or unbox/`Integer.compare` after checking for null.

`Integer.parseInt("17")` returns primitive `int`; `Integer.valueOf("17")` returns wrapper `Integer`. In generic collections, Java 17 requires object types: `List<int>` is invalid, `List<Integer>` is valid.

### Choosing a Wrapper Does Not Mean "Always Wanting null"

If the data is guaranteed to exist and is not constrained by generics or APIs, primitives are usually simpler and avoid null. Wrappers should be used only when there is a reason: a nullable contract, generics, reflection/ORM, or a library requiring objects.

Do not equate `Integer` with `OptionalInt`: `Integer` can be null, whereas `OptionalInt` is an object holding the present/absent state of an `int` and is primarily useful at return boundaries. Avoid using `Optional` indiscriminately as a data field if your system's frameworks or serialization do not support that contract.

## 7. BigInteger: Exact Integers Beyond long

`java.math.BigInteger` represents integers not limited to 32 or 64 bits. Practical magnitude is bounded by memory, computation time, and implementation limits.

Example:

```java
BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE); // 9223372036854775808
```

Unlike primitives, you must use methods:

| Operation | BigInteger |
| --- | --- |
| Addition | `a.add(b)` |
| Subtraction | `a.subtract(b)` |
| Multiplication | `a.multiply(b)` |
| Integer division | `a.divide(b)` |
| Remainder | `a.remainder(b)` or `a.divideAndRemainder(b)` |
| Comparison | `a.compareTo(b)` |
| Non-negative integer power | `a.pow(exponent)` |
| Checked conversion to long | `a.longValueExact()` |
| Checked conversion to int | `a.intValueExact()` |

`BigInteger` is for integers only: dividing `7 / 2` yields integer quotient `3`; there is no `3.5` fractional part. If you need exact rational arithmetic, you can store numerator/denominator separately or choose `BigDecimal` with a precision/rounding policy when a decimal result is needed.

**Do not use `longValue()`/`intValue()` if data loss is forbidden**, because they can narrow and drop bits. Use `longValueExact()` or `intValueExact()` to receive `ArithmeticException` if out of range.

## 8. BigDecimal: Exact Decimals and Rounding

`java.math.BigDecimal` represents values as:

```text
unscaledValue × 10^(-scale)
```

For example, `new BigDecimal("12.34")` has unscaled value 1234 and scale 2. Use `BigDecimal` when calculations must preserve exact decimals or when the domain has explicit rounding policies, such as money, tax rates, limits, and accounting figures.

### Constructing BigDecimal Properly

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(1234L, 2); // 12.34
BigDecimal c = BigDecimal.valueOf(0.1);
```

This snippet is used inside a method with `import java.math.BigDecimal`.

`new BigDecimal("0.1")` is the exact decimal 0.1. `BigDecimal.valueOf(0.1)` uses the canonical string representation of the `double` 0.1; it is usually preferable to `new BigDecimal(0.1)` if the input is already a `double`. However, if earlier calculations already lost source precision, `valueOf` cannot recover the lost information.

**Avoid `new BigDecimal(0.1)` when you intend the exact decimal 0.1**: the `double` constructor represents the exact approximate binary value of the `double`, which does not equal decimal 0.1.

### Arithmetic, Division, and Rounding

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal tax = price.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP); // 1.50
```

This example assumes the domain requires two decimal digits and `HALF_UP` rounding; do not assume every currency needs scale 2 or every business workflow uses the same `RoundingMode`.

| Need | API |
| --- | --- |
| Addition | `a.add(b)` |
| Subtraction | `a.subtract(b)` |
| Multiplication | `a.multiply(b)` |
| Exact division if quotient terminates | `a.divide(b)` |
| Division with rounding | `a.divide(b, scale, roundingMode)` |
| Controlled scale change | `a.setScale(scale, roundingMode)` |
| Compare numerical value | `a.compareTo(b)` |
| Exact conversion to int/long | `a.intValueExact()`, `a.longValueExact()` |
| Verify decimal fits precision limits | Use `precision()`, `scale()`, and domain/schema validation |

`BigDecimal.ONE.divide(new BigDecimal("3"))` throws `ArithmeticException` because `1/3` has a non-terminating decimal expansion. Use an overload with scale/`RoundingMode` or a suitable `MathContext` when division is allowed to round.

`BigDecimal` is immutable. Calling `balance.add(amount)` does **not** mutate `balance`; you must write `balance = balance.add(amount)`.

### equals Differs from compareTo

```java
BigDecimal first = new BigDecimal("2.0");
BigDecimal second = new BigDecimal("2.00");

System.out.println(first.compareTo(second) == 0); // true
System.out.println(first.equals(second));          // false
```

`compareTo` compares by numerical value; `equals` checks both value and scale. This affects `HashSet`/`HashMap` when `BigDecimal` is used as a key: 2.0 and 2.00 are two distinct keys if left unnormalized. If the domain only cares about numeric value, establish a consistent key normalization policy (such as `stripTrailingZeros()`) before both insertion and lookup.

## 9. Java 17+ Program Demonstrating Scenario-Based Choices

Save `NumberChoiceDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;
import java.util.OptionalInt;

public class NumberChoiceDemo {
    public static void main(String[] args) {
        int quantity = 50_000;
        int priceUnits = 50_000;
        long amount = Math.multiplyExact((long) quantity, priceUnits);
        System.out.println("long product: " + amount);

        BigInteger beyondLong = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        System.out.println("beyond long: " + beyondLong);

        BigDecimal exact = new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal sum: " + exact);

        BigDecimal base = new BigDecimal("19.99");
        BigDecimal tax = base.multiply(new BigDecimal("0.075"))
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("tax rounded: " + tax);
        System.out.println("with tax: " + base.add(tax));

        List<Integer> readings = List.of(3, 4);
        System.out.println("boxed list total: "
                + readings.stream().mapToInt(Integer::intValue).sum());
        OptionalInt missing = OptionalInt.empty();
        System.out.println("optional int empty: " + missing.isEmpty());
    }
}
```

Compile and run:

```bash
javac NumberChoiceDemo.java
java NumberChoiceDemo
```

Stdout verified with Java:

```text
long product: 2500000000
beyond long: 9223372036854775808
decimal sum: 0.3
tax rounded: 1.50
with tax: 21.49
boxed list total: 7
optional int empty: true
```

Using multiple types in one scenario is normal: `int` for quantity, `long` for a product needing 64-bit range, `BigInteger` for integers exceeding 64 bits, `BigDecimal` for exact decimals, and `Integer` inside a generic collection. Do not force everything into the same type merely for syntactic uniformity.

## 10. Converting Across Type Boundaries: Use exact When Data Loss Is Forbidden

Data may be computed in a wider type and then need to be stored in a smaller type; **conversion** must be a separately checked step.

| Converting From | Risk | Suggestion |
| --- | --- | --- |
| `long` to `int` | Bit loss/sign change if out of range | `Math.toIntExact(value)` |
| `BigInteger` to `long` | Value larger than 64-bit | `longValueExact()` |
| `BigInteger` to `int` | Value outside 32-bit | `intValueExact()` |
| `BigDecimal` to `long` | Fractional part or out of range | `longValueExact()` |
| `BigDecimal` to `int` | Fractional part or out of range | `intValueExact()` |
| `BigDecimal` to `long` cents | Sub-cent fraction remains or out of range | `movePointRight(2).longValueExact()` when domain uses scale 2 |
| `double` to `int`/`long` | Truncation toward 0, saturation at bounds, NaN; data loss | Explicit range/precision validation or domain conversion |
| `BigDecimal` to `double` | Precision loss, possible infinity | Only when approximation is acceptable |

For `BigDecimal`, exact conversion to `int`/`long` **does not require scale 0**: `new BigDecimal("2.00").longValueExact()` returns 2 because there is no nonzero fractional part. However, `new BigDecimal("2.01").longValueExact()` throws an error.

Do not substitute `longValue()` for `longValueExact()` if silently dropping fractional parts or out-of-range bits is prohibited.

### Checked Conversion Example

Save `NumberBoundaryDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumberBoundaryDemo {
    public static void main(String[] args) {
        int x = 50_000;
        int y = 50_000;
        System.out.println("int overflow: " + (x * y));
        System.out.println("widen first: " + ((long) x * y));

        try {
            System.out.println(Math.toIntExact((long) x * y));
        } catch (ArithmeticException e) {
            System.out.println("narrowing rejected");
        }

        BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        try {
            System.out.println(huge.longValueExact());
        } catch (ArithmeticException e) {
            System.out.println("big integer narrowing rejected");
        }

        BigDecimal amount = BigDecimal.valueOf(1234L, 2);
        System.out.println("minor units to decimal: " + amount);
        System.out.println("back to minor units: "
                + amount.movePointRight(2).longValueExact());

        try {
            new BigDecimal("12.345").movePointRight(2).longValueExact();
        } catch (ArithmeticException e) {
            System.out.println("fractional minor unit rejected");
        }

        BigDecimal d1 = new BigDecimal("2.0");
        BigDecimal d2 = new BigDecimal("2.00");
        System.out.println("numeric equal: " + (d1.compareTo(d2) == 0));
        System.out.println("object equal: " + d1.equals(d2));
        System.out.println("1/3 rounded: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
    }
}
```

Compile and run:

```bash
javac NumberBoundaryDemo.java
java NumberBoundaryDemo
```

Verified stdout:

```text
int overflow: -1794967296
widen first: 2500000000
narrowing rejected
big integer narrowing rejected
minor units to decimal: 12.34
back to minor units: 1234
fractional minor unit rejected
numeric equal: true
object equal: false
1/3 rounded: 0.33
```

The example uses **2 minor-unit digits** enabling cents conversion. If the domain does not follow this convention (or rates require more intermediate digits), you must adjust the factor/scale and rounding policy accordingly; do not apply it unconditionally to every currency.

## 11. Wrappers and Collections: Null, Boxing, and Performance

Save `BoxingChoiceDemo.java` to see wrapper and primitive conversions clearly:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BoxingChoiceDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer wrapper = primitive;
        int unboxed = wrapper;
        System.out.println("unboxed: " + unboxed);
        System.out.println("wrapper value equality: "
                + Integer.valueOf(42).equals(wrapper));

        List<Integer> values = new ArrayList<>();
        values.add(3);
        values.add(4);
        System.out.println("collection sum: "
                + values.stream().mapToInt(Integer::intValue).sum());

        Integer nullable = null;
        System.out.println("nullable absent: " + Objects.isNull(nullable));
        try {
            int dangerous = nullable;
            System.out.println(dangerous);
        } catch (NullPointerException e) {
            System.out.println("null unboxing rejected");
        }

        System.out.println("parsed int: " + Integer.parseInt("17"));
    }
}
```

Run:

```bash
javac BoxingChoiceDemo.java
java BoxingChoiceDemo
```

Stdout:

```text
unboxed: 42
wrapper value equality: true
collection sum: 7
nullable absent: true
null unboxing rejected
parsed int: 17
```

For aggregations over many wrappers, you can switch to primitive streams using `mapToInt(Integer::intValue)`, `mapToLong(Long::longValue)`, or `mapToDouble(Double::doubleValue)`. **Watch the input stream type**: `IntStream` is already primitive, so do not use `mapToLong(Integer::longValue)` on an `IntStream`; instead use `asLongStream()` or `mapToLong(x -> (long) x)`.

Primitive streams help reduce boxing in certain computations, though they do not eliminate all object overhead of the original collection. For very large data volumes, benchmark and profile rather than choosing wrappers or primitives by intuition.

## 12. Choosing Intermediate Types Different from Storage Types

Some values fit in `int` for storage, while intermediate calculations require `long`; similarly, sums or products of multiple `long` values may require `BigInteger`. When performing exact decimal arithmetic, you can use `BigDecimal` and then store the smallest unit as `long` **after** rounding and validation.

Order processing example:

```text
quantity: int or long depending on per-line limits
unitPriceCents: long if smallest unit is fixed
subtotalCents: long with multiplyExact, or BigInteger if range is too large
tax: BigDecimal with rate/rounding from domain
finalCents: long after exact conversion and range check
DB: BIGINT cents or DECIMAL(p,s) per schema
```

This is a reference design, not a mandatory formula for every monetary system. Depending on data scope, you may use `BigDecimal` for both calculation and storage, or `BigInteger` for high-volume aggregation. The important part is **having a clear contract at conversion boundaries**.

Do not wait until the end to catch overflow: if an `int` multiplication has already overflowed, converting the wrong result to `BigInteger` cannot recover the original value. Choose the right type *before* the operation, or use checked arithmetic.

## 13. Java APIs and Databases/JSON

Java types alone do not dictate range and precision across system boundaries:

- **Database:** `INTEGER`, `BIGINT`, `DECIMAL(p,s)`, and `FLOAT`/`DOUBLE` have different ranges and conversion rules depending on the DBMS. Verify schema, nullability, magnitude, precision, and scale rather than expecting the driver to fix data automatically.
- **JSON:** a JSON number is neither Java's `long` nor `BigDecimal`. A JavaScript client using `Number` cannot preserve integers larger than `2^53 - 1` accurately; consider decimal strings or protocols supporting large numeric types when integrity is critical.
- **NaN/Infinity:** `double` has non-finite values, whereas standard JSON numbers cannot represent NaN/Infinity. Define an explicit rejection or special encoding policy.
- **Nullable:** distinguish `null` (no value), `0` (numeric value zero), and an omitted field. Depending on the framework, wrappers can fit nullable fields, while primitives fit mandatory fields with validation.
- **ID:** customer codes, account numbers, and strings with leading zeros are not inherently numbers for math; store them as `String` when identifier semantics matter.

In particular, if input/output data must be decimally exact, do not pass it through `double` during serialization or computation simply because `double` is convenient.

## 14. Common Mistakes When Choosing Types

| Mistake | Consequence | Fix Rule |
| --- | --- | --- |
| Using `int` for sums that can exceed 2^31-1 | Positive/negative overflow | `long`/`BigInteger` and range checks |
| `long total = intA * intB` | `int` overflows before assignment | Cast `(long) intA * intB` before multiplying |
| Using `double` for exact cents | Binary rounding error | `long` minor units or `BigDecimal` |
| Choosing `BigInteger` for 7/2 when expecting 3.5 | Integer division drops fraction | `BigDecimal`/rationals and explicit rounding |
| `new BigDecimal(0.1)` | Creates decimal matching **binary approximation**, not decimal 0.1 | `new BigDecimal("0.1")` |
| `BigDecimal.divide` on 1/3 without rounding | `ArithmeticException` | Specify scale/`MathContext`/`RoundingMode` |
| `BigDecimal.equals` to compare 2.0 and 2.00 by numeric value | False due to differing scale | `compareTo == 0` |
| Comparing two wrappers with `==` | Compares object identity, depends on boxing/cache | `equals` or `Objects.equals` |
| Unboxing a null wrapper | `NullPointerException` | Check for null or design non-nullable API |
| Using `List<int>` | Invalid in Java 17 generics | `List<Integer>` or primitive array/stream |
| `BigInteger.longValue()` when data exceeds long | Bit loss | `longValueExact()` |
| `BigDecimal.longValue()` when fraction remains | Drops fraction, may break business logic | `longValueExact()` when exactness required |
| Using `float` to "increase precision" | Actually has less precision than double | `double` or `BigDecimal` per need |
| Using integers for codes with leading zeros | Leading zeros lost | `String` |
| Using `Integer` because "objects are always better" | Unnecessary null/boxing/overhead | Primitives when non-null and no generics needed |
| Using `BigDecimal` for every approximate measurement | Complexity overhead without adding source accuracy | `double` when approximation error is acceptable |

## 15. Pre-Decision Selection Checklist

Use these questions to move from requirements to a type:

1. **Is the value a number meant for calculation?** If it is only an identifier, consider `String`.
2. **Integer-only or fractional?** Integer: `int`/`long`/`BigInteger`; decimal: `double` or `BigDecimal`.
3. **Largest range of both intermediate and final results?** Account for multiplication, accumulation, exponentiation, and future data growth.
4. **Is IEEE 754 error acceptable?** If not, do not choose `float`/`double` to hold exact decimals.
5. **Is null needed?** Primitives are non-null; wrappers can be null but must be checked before unboxing; `OptionalInt/Long/Double` can be used in result APIs.
6. **Are generics/collections involved?** Choose wrappers or `BigInteger/BigDecimal` for Java 17 generics.
7. **Are there specific rounding requirements?** For `BigDecimal`, specify scale and `RoundingMode` at the right boundary.
8. **Is there conversion to a smaller type?** Use `Math.toIntExact`, `intValueExact/longValueExact`, or thorough validation.
9. **Do the schema and clients understand the values?** Check JDBC, JSON/JavaScript, database precision/scale, and nullability.
10. **Are there boundary tests?** Test MIN/MAX, overflow, 0, negatives, 0.1, 1/3, null, and decimal representations with different scales.

## 16. Self-Check Questions

1. **Storing a small mandatory quantity without generics?** Usually `int`.
2. **Sum of two `int`s might exceed `Integer.MAX_VALUE`?** Widen to `long` before adding or use checked arithmetic.
3. **Can you use `List<int>` in Java 17?** No; use `List<Integer>`.
4. **What if an `Integer` is null and unboxed to `int`?** Throws `NullPointerException`.
5. **Need an exact integer larger than `Long.MAX_VALUE`?** `BigInteger`.
6. **Need to keep 0.1 and 0.2 decimally exact?** `BigDecimal` from string or exact decimal source.
7. **Does `BigInteger.divide` return a fractional part?** No; it performs integer division.
8. **Why is `BigDecimal("2.0").equals(BigDecimal("2.00"))` false?** Different scales; `compareTo` is appropriate when comparing mathematical value only.
9. **Converting `BigDecimal("12.345")` to `long` cents at scale 2 while forbidding data loss?** `movePointRight(2).longValueExact()` throws an error; apply business rounding if permitted.
10. **Does `double` hold every `long` integer exactly?** No, because of finite precision.
11. **When should you choose a wrapper over a primitive?** When you need nullability, generics, or an API requiring objects; do not automatically choose wrappers for every field.
12. **Why is `BigDecimal` not always better than `double`?** `double` suits many approximate calculations with low cost; `BigDecimal` adds overhead and requires scale/rounding management.

## 17. Conclusion

You can keep a minimal selection table in mind:

- **`int`/`long`:** integers with fixed ranges and mandatory values; choose according to the full calculation range.
- **`Integer`/`Long` and wrappers:** same numeric meaning as their primitives when objects, nullability, or generics are required.
- **`double` (and `float` when justified):** approximate binary floating-point numbers, suitable for many scientific/statistical problems but not preserving all decimals.
- **`BigInteger`:** exact integers beyond fixed-width types.
- **`BigDecimal`:** exact decimals and business rounding, especially for money or controlled decimal data.

Always determine **range, precision, nullability, units, and data boundaries** before choosing. In a real processing pipeline, multiple types often appear together — that is good design as long as each type has a clear role and conversions between them are validated.
