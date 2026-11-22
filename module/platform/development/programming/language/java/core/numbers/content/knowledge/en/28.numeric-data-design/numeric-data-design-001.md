# Explicitly Specifying Value Ranges, Units, and Limits When Designing Numeric Data in Java

A numeric field such as `amount`, `distance`, `quantity`, or `rate` is not completely described by a type like `int`, `long`, `double`, or `BigDecimal` alone. The same value `100` could mean 100 dong, 100 cents, 100 meters, 100 milliseconds, or 100 percent. Similarly, the `long` type can store a very large negative number, yet a product quantity in a business domain might only be allowed from 0 to 10,000. Using an appropriate Java type is necessary; **a numeric data contract must explicitly specify the value range, unit, precision, and how out-of-bounds values are handled**.

This article focuses on how to describe and enforce numeric contracts at API, DTO, model, storage, and calculation boundaries. The desired outcome: two independent developers can read the specification and share the exact same understanding of what a number means, instead of guessing from variable names or primitive types.

## 1. Distinguishing Java Type Ranges from Business Domain Ranges

**The representation range of a type** is every value that the data type can store. **The valid business range** is the subset permitted by the system.

| Data | Possible Java Type | Example Business Range | Unit |
| --- | --- | --- | --- |
| Item quantity | `int` | 0 to 10,000 | items |
| Request timeout | `long` | 1 to 120,000 | milliseconds |
| Distance | `long` | 0 to 10,000,000 | millimeters |
| Non-negative price | `long` | 0 to 100,000,000 | smallest currency unit |
| Discount rate | `int` | 0 to 10,000 | basis points, 1 bp = 0.01% |
| Mass | `BigDecimal` | 0 to 1,000, resolution 0.001 | kilograms |

**The numbers in this table are examples of a specific contract**, not default limits imposed by Java or by any industry. Each product must determine its own ranges.

Technically:

- `byte`: from -128 to 127.
- `short`: from -32,768 to 32,767.
- `int`: from -2,147,483,648 to 2,147,483,647.
- `long`: from -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.
- `BigInteger`: represents variable-magnitude integers, not limited to 32/64 bits, though still subject to resource limits.
- `BigDecimal`: represents exact decimal numbers via an unscaled integer value (`unscaled value`) and `scale`; still requires defining appropriate range, resolution, and rounding rules.
- `float` and `double`: binary floating-point numbers, having `NaN`, positive/negative infinity, and representation error; should only be chosen if those characteristics fit the data domain.

For example, if `quantity` is an `int`, Java does not prevent callers from passing `-5` or `2_000_000`. The condition "0 to 10,000" must be **stated in the contract and validated in code**, not inferred from the `int` type.

The specification must clarify whether both endpoints are **inclusive** or **exclusive**. For instance, `0 <= count && count <= 10_000` differs from `0 < count && count < 10_000`. A field that allows 0 also differs from one that must always be positive.

## 2. Explicitly Specifying Units and Semantics of Each Field

Numbers of the same Java type can still be quantities with incompatible units. The snippet below compiles, yet is very error-prone:

```java
long timeout = 5;       // 5 seconds or 5 milliseconds?
long distance = 1200;   // 1200 meters or 1200 millimeters?
long price = 1999;      // 1999 dong or 19.99 currency units?
```

There is not enough information to tell whether these values are correct. Make the meaning explicit and, where appropriate, include the unit in variable/API names:

```java
long timeoutMillis = 5_000L;
long distanceMillimeters = 1_200L;
long priceMinorUnits = 1_999L;
```

A contract for a numeric field should describe at least:

1. **Quantity name:** count, duration, length, price, rate, or identifier.
2. **Canonical unit:** milliseconds, millimeters, cents, basis points, bytes...
3. **Valid range:** min/max, whether bounds are inclusive, whether negative numbers and 0 are allowed.
4. **Resolution and precision:** smallest increment, accepted number of decimal places.
5. **Missing value policy:** whether `null` is valid; whether 0 means "unknown".
6. **Conversion and rounding policy:** what factor to convert units by; whether to discard or round remainders; if rounding, according to which rule.
7. **Behavior on violation:** reject with an exception/error result, or handle per business rules.

For example, a duration field can be specified as: "`timeoutMillis`: integer milliseconds; from 1 to 120,000 inclusive; required; zero and negative values invalid; out-of-range values rejected." That is a contract ready for implementation and testing.

### Avoiding Mixed-Unit Addition

```java
long durationSeconds = 3;
long durationMillis = 500;

// Wrong semantics: 3 seconds + 500 milliseconds is not 503 milliseconds.
long wrong = durationSeconds + durationMillis;

// Correct: convert to the same unit (milliseconds) before adding.
long correct = Math.addExact(
        Math.multiplyExact(durationSeconds, 1_000L), durationMillis);
// correct = 3500
```

`Math.multiplyExact` and `Math.addExact` help detect overflow during integer conversion and addition. This is an illustrative snippet placed inside a method. If inputs come from different systems, convert all of them to the same unit **before calculating**, and document clearly where the conversion happens.

Java provides types that clarify certain data domains, such as `java.time.Duration` for time intervals. When using `Duration`, two arbitrary `long` parameters should not be treated as sharing the same meaning. APIs like `Duration.ofSeconds(3)` and `Duration.ofMillis(500)` make the unit explicit right at the point of creation.

## 3. Resolution and Decimal Policy Belong to the Field Contract

Even when the **unit** of a number is known, the API must still specify the smallest step, such as 0.001 kg or 0.01 currency units. `BigDecimal.scale()` is the power-of-10 exponent of the representation, while `precision()` is the number of significant digits in the coefficient. They do not by themselves define units or business rules.

```java
BigDecimal value = new BigDecimal("12.30");
System.out.println(value.scale());     // 2
System.out.println(value.precision()); // 4
BigDecimal accepted = value.setScale(2, RoundingMode.UNNECESSARY);
```

When the requirement is **no rounding allowed**, `setScale(2, RoundingMode.UNNECESSARY)` accepts `12.30` but rejects `12.345`. This checks representability at a resolution of 0.01 without forcing the original token to have literally two digits after the decimal point. If the system allows rounding, it must state when it happens and the `RoundingMode` (do not assume one mode fits all currencies). The article `Putting Precision, Scale, and Rounding into the Numeric Data Design Contract in Java` covers the full policy and division operations.

For money, an integer count of the **smallest unit** can be appropriate if the currency and the ratio between the two units are specified. Do not assume all currencies have exactly two decimal places or that amounts in different units can be added together.

## 4. Limits Must Cover Intermediate Calculations

Individual field ranges may be small, yet their **sum or product** can exceed the primitive type of the operands. If the maximum quantity is 50,000 and the maximum unit price is 100,000 minor units, the product can reach 5,000,000,000, exceeding `int`:

```java
int quantity = 50_000;
int unitPriceMinor = 100_000;
long correct = (long) quantity * unitPriceMinor; // 5000000000
```

Type promotion must occur **before multiplying**, not wait for the variable receiving the result. Use `Math.multiplyExact`, `Math.addExact`, `Math.toIntExact`, or `BigInteger` according to business limits. If the final result is small but an intermediate step overflows, the contract must specify whether intermediate overflow is rejected or computed in a wider type before checking the final result.

The article `Choosing Intermediate Calculation Types Separately from Storage Types in Java` thoroughly analyzes `IntStream`, intermediate operations, narrowing conversions, and storage boundaries.

## 5. The Same Contract Must Hold from Java to Receiving Systems

The numeric data contract must align across Java models, DTOs/APIs, JSON, databases, and file representations. A `long` that is valid in the backend can exceed JavaScript's `Number.MAX_SAFE_INTEGER` on the client; if exact two-way integers are needed, agree on a schema—for example, transmitting decimal strings with a matching parser. A `DECIMAL(p,s)` column still needs business rules for range, sign, precision, and scale.

Interfaces may accept **meters** while the model stores **millimeters**; convert units at clear boundaries, check for overflow, and output the published unit. Never use strings formatted with grouping separators or rounded for human display as canonical payloads. The article `Separating Display Formatting from Calculation and Exchange of Numeric Data in Java` expands on protocols and locales.

## 6. From Primitive Fields to Domain-Representing Types

A `long` field can be suitable when the codebase is small and everyone shares the same understanding of the contract. For critical APIs, wrap the value in a **value object** to validate the range upon creation:

```java
record DistanceMillimeters(long value) {
    static final long MAX_VALUE = 10_000_000L; // Example 10 km limit.

    DistanceMillimeters {
        if (value < 0 || value > MAX_VALUE) {
            throw new IllegalArgumentException("distance out of range");
        }
    }
}
```

This is a Java 17 `record` and an **illustrative snippet**. The compact constructor is invoked when creating the record and rejects any value outside the range. `DistanceMillimeters` helps prevent accidentally passing milliseconds to a distance parameter; a compiler seeing only `long` cannot distinguish the two quantities.

The value object can be extended to accept input in meters and convert it to millimeters:

```java
static DistanceMillimeters fromMeters(String meters) {
    long mm = new BigDecimal(meters)
            .movePointRight(3)
            .longValueExact();
    return new DistanceMillimeters(mm);
}
```

This method lives **inside** the `DistanceMillimeters` record and requires importing `java.math.BigDecimal`. `movePointRight(3)` converts meters to millimeters; `longValueExact()` rejects values with fractional parts smaller than 1 millimeter (which cannot be converted exactly to integer millimeters) or values outside the `long` range. The constructor then rejects negative values or values exceeding 10,000,000 millimeters.

For example, `fromMeters("1.250")` stores 1,250 mm; `fromMeters("0.0005")` is rejected because it equals 0.5 mm and this contract **does not allow rounding**. If the product wants to allow rounding half-millimeters, it must document the `RoundingMode` and decide that before implementation.

Physical quantities can have negative values (such as Celsius temperature) or not (such as length). Do not apply a "no quantity may be negative" rule by default; set limits that match each domain.

## 7. Complete Java 17+ Program: Enforcing Units, Ranges, and Resolution

The following example assumes a price domain with **two decimal places**, a single currency, allowing only **non-negative** prices not exceeding 1,000,000 major currency units. Distance is entered in **meters**, stored as **millimeters**, non-negative, and not exceeding 10 km. These limits are chosen to illustrate how to write a contract, not as universal rules of commerce or measurement.

Save the file **`NumericContractDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Objects;

public final class NumericContractDemo {
    private NumericContractDemo() {}

    record PriceCents(long value) {
        static final long MAX_CENTS = 100_000_000L;

        PriceCents {
            if (value < 0 || value > MAX_CENTS) {
                throw new IllegalArgumentException("price out of range");
            }
        }

        static PriceCents fromDecimal(String text) {
            Objects.requireNonNull(text, "price text");
            long cents = new BigDecimal(text)
                    .movePointRight(2)
                    .longValueExact();
            return new PriceCents(cents);
        }

        PriceCents plus(PriceCents other) {
            Objects.requireNonNull(other, "other");
            return new PriceCents(Math.addExact(value, other.value()));
        }

        String asDecimal() {
            return BigDecimal.valueOf(value, 2).toPlainString();
        }
    }

    record DistanceMillimeters(long value) {
        static final long MAX_MM = 10_000_000L;

        DistanceMillimeters {
            if (value < 0 || value > MAX_MM) {
                throw new IllegalArgumentException("distance out of range");
            }
        }

        static DistanceMillimeters fromMeters(String text) {
            Objects.requireNonNull(text, "meters text");
            long mm = new BigDecimal(text)
                    .movePointRight(3)
                    .longValueExact();
            return new DistanceMillimeters(mm);
        }

        String asMeters() {
            return BigDecimal.valueOf(value, 3).toPlainString();
        }
    }

    public static void main(String[] args) {
        PriceCents a = PriceCents.fromDecimal("12.34");
        PriceCents b = PriceCents.fromDecimal("2.66");
        System.out.println("total price = " + a.plus(b).asDecimal());

        DistanceMillimeters distance =
                DistanceMillimeters.fromMeters("1.250");
        System.out.println("distance m = " + distance.asMeters());

        try {
            PriceCents.fromDecimal("1.234");
        } catch (ArithmeticException ex) {
            System.out.println("price precision = rejected");
        }

        try {
            DistanceMillimeters.fromMeters("10000.001");
        } catch (IllegalArgumentException ex) {
            System.out.println("distance limit = rejected");
        }

        try {
            PriceCents.fromDecimal("-1.00");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative price = rejected");
        }

        long widened = (long) Integer.MAX_VALUE + 1;
        System.out.println("int widened sum = " + widened);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 NumericContractDemo.java
java NumericContractDemo
```

Expected stdout:

```text
total price = 15.00
distance m = 1.250
price precision = rejected
distance limit = rejected
negative price = rejected
int widened sum = 2147483648
```

**Explanation:**

- `"12.34"` and `"2.66"` are multiplied exactly by 100 and stored as `long` cents. The sum of 1,500 cents is displayed as `15.00`.
- `"1.250"` meters converts exactly to 1,250 millimeters. When formatted with `BigDecimal.valueOf(value, 3)`, it returns to `1.250`.
- `"1.234"` in major currency units corresponds to 123.4 cents; `longValueExact()` rejects it because of the fractional part smaller than 1 cent. The example contract **does not round**.
- `"10000.001"` meters corresponds to 10,000,001 mm, exceeding the 10,000,000 mm limit and is therefore rejected.
- `"-1.00"` is rejected because the domain forbids negative prices, even though `long` can easily represent -100.
- The expression `(long) Integer.MAX_VALUE + 1` promotes to `long` **before the addition**, so `int` does not overflow.

This program uses `record`, available since Java 16 and compatible with Java 17+. It intentionally omits currency codes or exchange rate conversion rules because the example contract assumes **a single agreed currency**. If the application handles multiple currencies, the price type must explicitly carry the currency code and disallow direct addition across different codes without a conversion rule.

## 8. Describing Numeric Fields in APIs and Documentation

A clear specification can be written as a table for frontend, backend, QA, and storage teams to share:

| Field | Wire Type | Meaning/Unit | Range/Resolution | On Invalid Input |
| --- | --- | --- | --- | --- |
| `quantity` | JSON integer | items | 0–10,000, step 1 | Return range error |
| `timeoutMillis` | JSON integer | milliseconds | 1–120,000, step 1 | Return range error |
| `distanceMillimeters` | JSON integer | millimeters | 0–10,000,000, step 1 | Return range error |
| `priceMinorUnits` | JSON integer or numeric string if client needs 64-bit precision | minor unit of a specified currency | 0–100,000,000, step 1 | Return range error |
| `discountBasisPoints` | JSON integer | basis points | 0–10,000, step 1 (= 0.01%) | Return range error |
| `massKg` | decimal numeric string | kilograms | 0–1,000, step 0.001 kg | Reject overly granular numbers |

All example ranges are **inclusive at both endpoints**. If a JSON string is chosen to preserve large integers, the API documentation must declare the **actual data type** as string and define the valid format; never document a JSON integer and silently return a string.

JSON example illustrating a quantity and duration object:

```json
{
  "quantity": 12,
  "timeoutMillis": 5000,
  "distanceMillimeters": 1250
}
```

Documentation must clarify that `distanceMillimeters: 1250` means 1.25 meters, not 1,250 meters. Fields with unit suffixes significantly reduce integration confusion.

If there are nullable fields, explicitly document how they are interpreted: whether `null` means "unknown" or "not applicable", whether it is rejected in requests or persisted in the database, and **do not** use `0` or `-1` as arbitrary sentinels if those values could be valid. Another case is an **unmeasured value**; a dedicated status type may be needed to distinguish `NOT_MEASURED`, `UNAVAILABLE`, and actual numeric values.

## 9. Validating Values at the Right Boundaries

Data constraints should appear wherever values are created or received from outside: when parsing requests, constructing value objects, converting units, or writing to a data store.

A typical, sound processing pipeline:

1. **Receive input:** identify data type, unit, locale, and missing-value rules.
2. **Parse without precision loss:** prefer `BigDecimal(String)` for decimal data; avoid going through `double` when exact decimals are required.
3. **Convert to canonical unit:** multiply/divide by the defined factor using appropriate arithmetic; check resolution and round if the contract allows it.
4. **Validate range:** min/max and business constraints; fail explicitly when invalid.
5. **Store and process:** keep the canonical unit; do not repeatedly convert using different rules.
6. **Return data:** reflect the exact unit and precision; update the API schema accordingly.

`Objects.requireNonNull` is used for required fields; for invalid user input, the API can translate parse/range failures into structured error codes such as `INVALID_FORMAT`, `OUT_OF_RANGE`, `INVALID_PRECISION`, `UNSUPPORTED_UNIT`. Do not rely on verbatim JDK exception messages as a public contract because those messages can change.

For immutable objects, placing validation in constructors/factories prevents invalid states from ever being created. Still, validation at the API boundary is worthwhile to return clear error messages instead of letting errors propagate deep into the system.

## 10. Decisions Easily Overlooked

### Do Not Rely on Primitive Type Names to Infer Quantities

`long` does not mean "milliseconds," nor does it mean "large monetary amount." If multiple layers use the same `long` for distance, duration, and money, field names, value objects, or schemas must make the distinction clear.

### Do Not Automatically Treat `null` as 0

`0` can be valid data; `null` can mean missing data. A model might specify a minimum price of 0 while treating an unprovided input price as invalid or undefined. Documentation must state this explicitly.

### Do Not Equate "Numerically Equal" with "Identical String Representations"

For `BigDecimal`, `"1.0"` and `"1.00"` have the same numeric value but different `scale`. `compareTo` returns 0, whereas `equals` returns `false`. If scale or the number of decimal digits is part of the data, equality rules must be clearly documented; if only arithmetic equality is needed, avoid accidentally using `equals` to decide that two monetary amounts differ.

### Do Not Round Without a Contract

An API that accepts a price `"1.234"` and silently turns it into `"1.23"` may violate a requirement to reject unsupported resolution. A rounding rule needs to specify the rounding mode, when rounding occurs, and the target unit.

### Do Not Accept All `double` Values by Default

`Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY` can pass through a `double` type, even when a business quantity requires a finite number. Use `Double.isFinite(value)` when the contract only accepts finite numbers, alongside appropriate min/max checks. For exact decimal currency, use an appropriate decimal data type.

### Do Not Expect the Database to Replace Business Rules

SQL types define representation ranges, but quantity limits, units, or "rates must not exceed 100%" must be enforced in the application and/or database constraints. Never let the frontend, backend, and database each choose a different boundary.

## 11. Numeric Contract Test Suite

A valuable test suite should test **at the boundaries and outside the boundaries**, rather than only normal values. For a `quantity` field from 0 to 10,000:

| Value | Expected |
| --- | --- |
| `0` | Valid if lower bound is inclusive |
| `1` | Valid |
| `10_000` | Valid if upper bound is inclusive |
| `-1` | Rejected |
| `10_001` | Rejected |
| `null` | Per required/nullable contract |
| `"1.5"` | Rejected if integers only |

For fields with units and resolution, also test: `1.250 m` → 1,250 mm; `0.0005 m` → rejected if rounding is disallowed; 10,000 m is the maximum boundary and 10,000.001 m exceeds the limit. For 2-decimal money: test `"0"`, `"0.01"`, `"1000000.00"`, `"1000000.01"`, `"-0.01"`, and `"1.234"`. Also test intermediate calculations (additions/multiplications exceeding `int` or `long`), narrowing conversions, and serialization to JavaScript clients.

If the requirement "the final sum must stay within range" differs from "no intermediate addition may exceed the range," test cases where positive and negative numbers cancel each other out. This verifies the exact contract rather than relying on an accident of the implementation.

## 12. Checklist for Every New Numeric Field

Before releasing a numeric field in an API or storage schema, you should be able to answer:

- **What quantity does it measure or identify?** Is it a count, duration, money, or identifier (numeric identifiers are not necessarily suitable for arithmetic)?
- **What is the unit?** Do the field name and documentation express the same canonical unit? If conversions exist, what are the rules?
- **What are the valid minimum/maximum values?** Are bounds closed or open, and are negatives or 0 allowed?
- **What are the resolution and scale?** Is rounding allowed, and using which rule?
- **What do missing values mean?** Are `null`, absent fields, 0, and sentinels confused with one another?
- **Are intermediate calculations safe?** Promote types before adding/multiplying; use exact checks or `BigInteger` where needed.
- **Do all layers share the same understanding?** Do Java, JSON/clients, SQL, CSV, and documentation agree on units, bounds, precision, and error handling?
- **Are boundary tests in place?** Covering bounds, out-of-bounds, conversions with remainders, overflow, and serializing large values.

**Key takeaway:** A data type tells "how the computer stores a value"; a numeric contract must also state **which values are valid, what unit it carries, how precise it is, and what the system does when limits are exceeded**. Specifying these upfront prevents silent bugs in calculations, APIs, and storage.

### Java SE 21 References

- [`Integer` and `int` type limits](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [`Long` and `long` type limits](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html)
- [`BigDecimal`: scale, precision, exact conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Math`: addExact, multiplyExact, toIntExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`Duration`: representing and converting durations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)