# Choosing Numeric Types in Java by Data Semantics and Calculation Requirements

A program can compile and run yet still compute **wrong business results** if an unsuitable numeric type is chosen. The first question is not "should I use `int` or `double`?", but rather: **what does this value represent, what values is it allowed to take, what calculations will be performed, and what counts as correct?**

In the **Java core – numbers** module, this lesson builds a decision process for choosing `byte`, `short`, `int`, `long`, `float`, `double`, `BigInteger`, `BigDecimal`, or a **non-numeric** type when data merely looks like digits. The goal is an explainable, verifiable choice, not merely memorizing a table of data type ranges.

## 1. Four Questions to Answer Before Choosing a Type

### Question 1: What Meaning Does the Data Truly Carry?

Distinguish **quantities** used for calculation from **identifiers** used for identification:

- **Discrete counts**: number of learners, number of packages, view counts, byte counts → integers.
- **Continuous measurements**: sensor temperature, physical coordinates, velocity → often `double` can be used if binary error is acceptable.
- **Decimals governed by business rules**: unit prices, taxes, money, allocation ratios, decimal-scale grades → usually require `BigDecimal` or an integer representing the smallest unit.
- **Identifiers**: postal codes `"00123"`, phone numbers, customer codes `"000042"`, account numbers, card numbers, item codes → usually `String`. These values have no meaningful addition or subtraction and may contain leading zeros.
- **Time and durations**: event timestamps, delivery dates, processing deadlines → typically use `Instant`, `LocalDate`, `Duration`, or an appropriate `java.time` type rather than picking a number with unclear units.

**Counterexample:** writing `int postalCode = 00123;` both strips leading zeros and runs into octal literal syntax. True to data semantics is `String postalCode = "00123";`. Likewise, an all-digit ID is still not automatically a mathematical quantity.

### Question 2: What Are the Value Range and Growth Rate?

Identify the minimum, maximum, whether negatives are possible, how long it can grow, and whether **intermediate values** are larger than the final result.

For example, item count in a shopping cart may fit `int`; total bytes processed in a multi-year service may need `long`; a combinatorial counter may exceed `long` and require `BigInteger`.

Do not base the decision solely on today's data. Also ask "what about 3 years from now?", "what about summing 10,000 items?", and "what about multiplying two large numbers?". Safety margin is a design requirement, not an excuse to skip overflow checks.

### Question 3: How Is Precision Defined?

Three different goals lead to different choices:

1. **Absolute exactness for integers:** `int`, `long` within range; `BigInteger` when range can exceed 64 bits.
2. **Approximation with controlled error:** `double` or `float` for binary arithmetic, measurements, simulations, statistics; specify error bounds by context.
3. **Decimal exactness with defined rounding:** `BigDecimal` for business decimal values. "Exact" here does not mean non-terminating divisions like `1/3` are represented completely on their own; scale/precision and rounding must be specified when needed.

A value with a decimal point does not automatically demand `BigDecimal`: a temperature reading `23.7°C` can fit `double`; a monetary amount `23.70` usually requires strict decimal rules.

### Question 4: Which Operations and Data-Exchange Boundaries Are Involved?

The chosen type also depends on:

- Operations: store/display only, addition/subtraction, multiplication/division, exponentiation, comparison, sorting, aggregation, rounding.
- Data flow: whether values arrive from JSON, CSV, a database, an API, a sensor, user input, or a quantized measurement.
- Consuming software: some `long` values cannot be preserved accurately in JavaScript when sent as JSON numbers; the consumer may need strings or an explicit safe-integer protocol.
- Domain conventions: units (`ms`, `s`, `bytes`, `kg`), negative signs, decimal scale, rounding level, valid bounds, how missing values are represented.

## 2. Decision Table: Choosing by Purpose

| Data Meaning / Requirement | Preferred Choice | Why | What to Check |
| --- | --- | --- | --- |
| Small counts, loop/array indices | `int` | Convenient, many Java APIs use `int` | Non-negative when domain requires; no overflow on add/multiply |
| Counters/total capacity that can exceed 2.1 billion | `long` | 64-bit range wider than `int` | Overflow can still occur; consistent API or DB read/write |
| Integers exceeding `long` limits | `BigInteger` | Not fixed to 64-bit width | Performance, memory, input limits |
| Measured real values, simulations, approximate probabilities | `double` | Better dynamic range and precision than `float` | Absolute/relative error; NaN, infinity |
| `float` data explicitly required by API/memory/model | `float` | 32-bit format compatibility, can save memory in large arrays | Only about 6–7 significant decimal digits |
| Unit prices, money, taxes, decimal rates under business rules | `BigDecimal` | Finite decimals are represented accurately when initialized properly | Scale, rounding, currency, when rounding occurs |
| Money converted to smallest unit with clear bounds | `long` | Exact integer add/subtract in range | Currency unit, conversion/allocation policy |
| True/false status flags | `boolean` | Accurately represents boolean domain | Avoid 0/1 when unnecessary |
| Postal codes, phones, card numbers, codes with leading zeros | `String` | Identifiers, not quantities | Preserve characters/length; protect sensitive data |
| Dates, instants, durations | Appropriate `java.time` type | Clear temporal semantics | Time zone, calendar, units, UTC vs. local time |

`byte` and `short` have a role when binary protocols, storage layouts, or APIs explicitly require 8/16-bit widths. For ordinary counting and calculation, `int` is usually easier to work with even when current values are small: arithmetic expressions on `byte`/`short` are frequently promoted to `int` anyway. Do not pick `byte` just because "the number is under 100".

## 3. Reusable Decision Flowchart

```text
Is the value a quantity used for calculation?
├─ No → String, boolean, enum, java.time, or a dedicated domain type
└─ Yes
   ├─ Must the value be an integer?
   │  ├─ Yes → Within int range?
   │  │        ├─ Yes → int
   │  │        └─ No → Within long range?
   │  │                ├─ Yes → long
   │  │                └─ No → BigInteger
   │  └─ No
   │     ├─ Controlled binary error permitted?
   │     │  ├─ Yes → double (float if specifically required)
   │     │  └─ No → BigDecimal or integer with defined unit/scale
   │     └─ Division/rounding → must define a policy
   └─ On every branch: confirm data range, units, error handling, and
      how values are preserved when stored or sent over APIs.
```

The flowchart is a starting point; a numeric type can still fall short if an intermediate calculation overflows or if an interface layer loses precision. For counters where negative values are invalid, you must still validate `value >= 0`: `int` is a **signed** type and does not enforce domain constraints by itself.

## 4. Choosing Integers: Range, Overflow, and Intermediate Results

Signed integer types in Java:

| Type | Range | Usage Guidance |
| --- | --- | --- |
| `byte` (8-bit) | -128 to 127 | Binary data or 8-bit format protocols |
| `short` (16-bit) | -32,768 to 32,767 | 16-bit structure compatibility |
| `int` (32-bit) | -2,147,483,648 to 2,147,483,647 | General quantities and indices |
| `long` (64-bit) | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | Integers larger than `int` |
| `BigInteger` | Not constrained by fixed bit count | Very large math/counts; practical limit by memory/resources |

**Determine the type at the moment the calculation executes.** In this example:

```java
int count = 1_500_000_000;

long wrong = count * 3;          // Multiply as int before assigning to long: already overflowed.
long correct = (long) count * 3; // Widen type before multiplication: 4_500_000_000L.
long exact = Math.multiplyExact((long) count, 3L);
```

This is an illustrative snippet, not a standalone program. Java does not automatically report overflow for ordinary `int`/`long` operations. Use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, and `Math.toIntExact` when overflow is unacceptable. If a result cannot be guaranteed within `long`, move the whole calculation to `BigInteger` instead of casting an already overflowed result.

**Integer division discards the fractional part:**

```java
int completed = 7;
int groups = 2;
int each = completed / groups;            // 3
double average = (double) completed / groups; // 3.5
```

Dividing by 0 with integers causes Java to throw `ArithmeticException`. When an exact count must be divided and yields a fraction, decide what that means: it may be an approximate measured ratio (`double`), a business ratio calculation (`BigDecimal`), or an integer quotient/remainder to distribute leftover units.

**BigInteger:** construct with `new BigInteger("9223372036854775808")`, and use `add`, `multiply`, `divide`, and `compareTo`. It is an immutable object; `value.add(BigInteger.ONE)` returns a new object and does not mutate `value`. Do not expect the `+` operator to work on two `BigInteger` objects.

One important note: unsigned representations in external protocols must be handled explicitly. Java's standard integer types are all signed; `Integer.toUnsignedLong`, `Long.compareUnsigned`, and `Long.toUnsignedString` only support **unsigned interpretation/operations on existing bits**, and do not turn `long` into a type with an arbitrary positive integer range. For full 64-bit unsigned values, consider `BigInteger` in the domain layer when a non-negative mathematical value exceeding `Long.MAX_VALUE` is required.

## 5. Choosing Floating-Point: Error and Verification Criteria

`float` and `double` are **binary** floating-point numbers. They can approximate many decimal values yet do not preserve every fraction like `0.1` exactly. For noisy measurements and physical models, numerical error can be a reasonable part of the problem; for money, that error is usually inappropriate.

```java
double measuredTemperature = 23.75;
double a = 0.1;
double b = 0.2;
boolean exactSame = (a + b == 0.3); // false
```

Two pitfalls to avoid:

1. Do not use `==` with two floating-point results when the goal is asking "are they close enough?". Define tolerance by units and magnitude, possibly combining absolute and relative thresholds; a threshold suitable for temperature can be meaningless for astronomical distances.
2. Do not assume `double` has "15 digits after the decimal point". It has roughly 15–16 **significant** digits; resolution depends on magnitude. `float` typically has only about 6–7 significant decimal digits.

`NaN`, `Infinity`, and `-Infinity` exist in floating-point arithmetic. They are not valid measurement data in every domain; check `Double.isFinite(value)` before storing or passing into operations requiring finite values. `Double.isNaN` detects NaN; `NaN == NaN` is `false`. Certain floating-point divisions by 0 return infinity or NaN, unlike integer division by 0.

**When to choose `float`?** Only when a protocol, library, file format, huge numeric array, or computational model permits 32-bit precision and has a clear benefit. In Java, the literal `1.5` defaults to `double`; write `1.5f` for `float`. Do not convert `double` to `float` merely because printed values look similar; precision can be lost.

## 6. Choosing Exact Decimals: BigDecimal and Rounding Policies

`java.math.BigDecimal` represents finite values as **unscaled integer × 10^(-scale)**. A value from the string `"19.95"` is an exact decimal and does not suffer from `double` literal representation error.

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = BigDecimal.valueOf(3L);
BigDecimal subtotal = price.multiply(quantity); // 59.85
```

The snippet above requires `import java.math.BigDecimal;` and placing inside a method. Operations on `BigDecimal` return new objects: you must retain the return value of `add`, `multiply`, `setScale`, etc.

### 6.1. Initializing from the Right Source

Prefer `new BigDecimal("0.1")` if the source is a decimal representation. Avoid `new BigDecimal(0.1)` when the intent is **exactly one tenth**, because that constructor receives the exact binary value of the `double` and builds an exact decimal representation of that binary value. `BigDecimal.valueOf(0.1)` uses `double`'s canonical decimal string and produces `0.1` in this example, yet cannot repair error already introduced by earlier `double` arithmetic.

### 6.2. Precision, Scale, and Rounding Are Three Distinct Decisions

- **Scale** is the number of decimal places in the representation: `12.340` has scale 3.
- **Precision** is the count of significant digits in `BigDecimal`'s representation: `12.340` has precision 5.
- **RoundingMode** decides how digits are dropped when detail must be reduced. `HALF_UP`, `HALF_EVEN`, `DOWN`, and `CEILING` are not equivalent, especially for negative numbers and midpoint values.

```java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP); // 12.35

BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_EVEN); // 0.3333
```

The snippet needs `import java.math.RoundingMode;`. Calling `BigDecimal.ONE.divide(new BigDecimal("3"))` without supplying rounding criteria causes the non-terminating division to throw `ArithmeticException`. When using `MathContext`, precision is the **number of significant digits** for the operation, not the number of places after the decimal point. Monetary problems also often require setting scale after specific steps.

### 6.3. Equal Values with Different Scales

`new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false`, because `equals` checks scale as well. `compareTo` returns `0`, because it compares mathematical value. Choose deliberately based on business rules: equal monetary amounts may be considered the same **value**, while display formatting still needs to preserve 2 decimal places.

### 6.4. BigDecimal or long for Money?

There are two sound designs if the data contract specifies units completely:

- **`BigDecimal` in the main currency unit**: e.g., `19.95` USD, operating in decimals with clear scale/rounding rules.
- **`long` in the smallest unit**: e.g., `1995` cents, integer addition and subtraction; must control overflow and define division/allocation of leftover cents. Never assume every currency has 2 decimal places.

When computing taxes, discounts, exchange rates, interest rates, or allocations, specify whether **rounding happens per line or after summing the total**. The two orders can produce different results even when both use `BigDecimal`. An exact data type does not replace accounting rules.

## 7. Type Boundaries: Null, Boxing, Storage, and Communication

### 7.1. Primitive or Wrapper?

- `int` is a primitive value and cannot be `null`. `Integer` is an object capable of representing `null` in APIs/DTOs, and serves as the type argument for `List<Integer>`.
- `long`/`Long` and `double`/`Double` share the same relationship. Boxing/unboxing occurs automatically in many contexts, yet unboxing `null` triggers `NullPointerException`.
- If "not entered" differs from "equals 0", model that distinction explicitly with a wrapper or an appropriate domain object. Do not choose `Integer` just to allow `null` if the domain requires a value and doing so makes code error-prone.

```java
Integer optionalScore = null;
// int score = optionalScore; // Executing this will throw NullPointerException.
```

Compare wrappers with `equals` when comparing **object values**, rather than relying on `==`, which compares references between two wrappers (and has caching cases that make results misleading). Check for `null` before unboxing.

### 7.2. APIs and Databases Can Change the Decision

A Java type must be compatible with its storage environment. When persisting to a database, check `INTEGER`/`BIGINT` limits, `DECIMAL(p,s)`, driver types, schema migrations, and business constraints. For example, `DECIMAL(10,2)` allows at most 10 total digits and 2 digits after the decimal point; this column type does not automatically accommodate every `BigDecimal` the application might produce.

With JSON/JavaScript, integers larger in magnitude than `2^53 - 1` may not be preserved accurately in JavaScript's `Number` type. A valid Java `long` is not guaranteed safe when serialized directly as a JSON number for JavaScript consumption. You can design JSON strings for large IDs/integers, or explicitly agree on a `BigInt` decoder on the receiving side.

For exact decimals, ensure the JSON/parser layer does not pass through `double` before constructing `BigDecimal`. Transmit decimal format as a string when the protocol requires verbatim preservation or when serialization rules on both sides have been verified.

### 7.3. Units Must Travel with the Data

`long timeout = 5000;` does not tell whether 5000 is milliseconds, seconds, or nanoseconds. In real code, use `Duration.ofSeconds(5)` or a name like `timeoutMillis` when an API must take an integer. Similarly, never add `distanceMeters` and `distanceKilometers` without converting first; consider defining a domain class/record or an API accepting explicit units.

A system can pick the right `long` for the value range and still be wrong if it adds cents to dollars. **Primitive types do not carry units**, so responsibility for preserving units rests on domain design, variable naming, validation, and API contracts.

## 8. Conversions That Easily Lose Meaning

| Conversion or Expression | Risk | How to Handle |
| --- | --- | --- |
| `long` → `int` via cast | Truncates high bits, changes value | `Math.toIntExact(value)` or range check first |
| `int * int` → assign to `long` | Multiplies as `int` before assigning, can overflow | Widen at least one operand to `long` before multiplying |
| `long` → `double` | Not every `long` is represented accurately | Avoid for identifiers/counters requiring exactness |
| `double` → `int` | Truncates fractional part toward 0; out-of-range and NaN have special cast rules | Check `Double.isFinite`, range, and rounding policy |
| `double` → `BigDecimal` | Data may already have been binary-rounded | Capture original decimal string; if source is `double`, understand `valueOf` semantics |
| `BigDecimal` → `double` | Can lose precision or exceed range | Perform only when the application accepts approximation |
| `BigDecimal` → `int`/`long` | `intValue`/`longValue` can drop fractional part or bits | Use `intValueExact()`/`longValueExact()` when exactness is needed |
| `int / int` → assign to `double` | Division already dropped fractional part | Cast one operand before division |
| `String` with locale comma → standard parser | `NumberFormatException` or misread separator | Separate input/display formatting rules from canonical numeric representation |
| `Integer` is `null` → `int` | `NullPointerException` on unboxing | Validate before unboxing or design as non-null |

Not every `long` value can be represented exactly by `double`, even though both are 64 bits: `double` allocates many bits to sign and exponent, leaving a finite number of significand bits. This is particularly dangerous when turning large numeric IDs into floating-point numbers for "convenient processing".

## 9. Scenario Example: Deciding for Each Data Field

Suppose we are building an order processing and device telemetry service:

| Field | Recommended Type | Reasoning |
| --- | --- | --- |
| `orderCode = "0000157"` | `String` | Identifier, preserves leading zeros, no arithmetic |
| `quantity = 3` | `int` | Item count; validate `quantity >= 0` and business maximum |
| `processedBytes = 5_000_000_000` | `long` | Exceeds `Integer.MAX_VALUE`; has byte unit |
| `temperatureCelsius = 23.75` | `double` | Measurement that tolerates binary error |
| `unitPrice = "19.95"` | `BigDecimal` | Exact decimal unit price |
| `taxRate = "0.08"` | `BigDecimal` | Monetary calculation rate subject to rounding rules |
| `globalSequence` exceeding `long` | `BigInteger` (if arithmetic needed) or `String` (if identifier only) | Semantics determine type, not just length |
| `deadline` | `Instant` | Point in time; clearer semantics than raw milliseconds |

**Point to distinguish:** if `globalSequence` is only passed through APIs as an identifier, `String` may fit; if it is an integer that must be incremented, numerically compared, and added/subtracted beyond 64 bits, `BigInteger` is needed. The exact same all-digit character string leads to different decisions because business behavior differs.

## 10. Complete Java 17+ Program: Turning Requirements into Type Choices

Save the file **`NumericTypeChoices.java`**. The program demonstrates keeping an identifier as a string, using `long` for large byte counts, `double` for a measurement, `BigInteger` for a very large integer, `BigDecimal` for money, and checking overflow with `Math.multiplyExact`. In the invoice example, to illustrate a business rule, tax is rounded to two decimal places using `HALF_UP` before being added to the total.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericTypeChoices {
    public static void main(String[] args) {
        String orderCode = "0000157";
        int quantity = 3;
        long processedBytes = 5_000_000_000L;
        double temperatureCelsius = 23.75;

        BigInteger globalSequence =
                new BigInteger("9223372036854775808");

        BigDecimal unitPrice = new BigDecimal("19.95");
        BigDecimal taxRate = new BigDecimal("0.08");
        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(quantity));
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        long checkedProduct =
                Math.multiplyExact(1_500_000_000L, 3L);

        System.out.println("order-code=" + orderCode);
        System.out.println("quantity=" + quantity);
        System.out.println("processed-bytes=" + processedBytes);
        System.out.println("temperature-c=" + temperatureCelsius);
        System.out.println("sequence=" + globalSequence);
        System.out.println("subtotal=" + subtotal);
        System.out.println("tax=" + tax);
        System.out.println("total=" + total);
        System.out.println("checked-product=" + checkedProduct);
    }
}
```

Compile and run:

```bash
javac NumericTypeChoices.java
java NumericTypeChoices
```

Exact stdout result:

```text
order-code=0000157
quantity=3
processed-bytes=5000000000
temperature-c=23.75
sequence=9223372036854775808
subtotal=59.85
tax=4.79
total=64.64
checked-product=4500000000
```

Check the math: `19.95 × 3 = 59.85`; `59.85 × 0.08 = 4.788`; under `HALF_UP` at scale 2 this becomes `4.79`; total is `64.64`. This is a rule **chosen specifically for the example**, not a claim that every invoice or every currency rounds this way.

The example shows that one program needs multiple types because each field plays a different role. Using a single type for every field loses semantics or creates unnecessary risk.

## 11. Design and Testing Techniques After Choosing a Type

After deciding on a type, document the correctness invariants in the data contract:

1. **Valid range:** Can it be negative? Can it be 0? Maximum value? Is `null` allowed?
2. **Units:** Bytes, milliseconds, kilograms, USD or cents? Have units been normalized before arithmetic?
3. **Precision:** Must the result be exact integer/decimal or only approximate? If approximate, how is valid error measured?
4. **Division and rounding:** When does it occur? What scale? Which `RoundingMode`? Is there a policy when numbers do not divide evenly?
5. **Overflow:** Are checks in place before/after multiplication and addition, using `Exact` operations, or switching to `BigInteger`?
6. **Data path:** Do types in Java, JSON, JavaScript, database, and CSV preserve the same value and units?
7. **Missing/invalid values:** How are `null`, empty strings, NaN/infinity, overly long digits, and out-of-policy negatives handled?

Important test cases usually lie at the **boundaries**, not normal examples:

| Test | Purpose |
| --- | --- |
| `Integer.MAX_VALUE + 1` with `Math.addExact` | Detect overflow instead of receiving a wrapped value |
| Multiply two large `int`s and compare against widening to `long` before multiplication | Catch overflow bugs in intermediate expressions |
| `BigDecimal.ONE.divide(new BigDecimal("3"))` | Confirm policy for non-terminating decimal division |
| `0.1 + 0.2` and approximate comparison against `0.3` | Catch false assumptions about `double` |
| `new BigDecimal("2.0")` vs. `"2.00"` | Distinguish value comparison from representation comparison |
| `long` value above `2^53 - 1` passing through JSON/JavaScript | Verify precision is not lost in transit |
| Code `"0000157"` through storage/serialize/deserialize | Verify leading zeros and identifier are preserved |
| Midpoint tax, negative/positive discounts, and multi-line invoices | Verify correct rounding rule and when rounding occurs |
| `null` wrapper in DTO | Catch unintended unboxing |
| Milliseconds vs. seconds | Catch unit-conversion mistakes |

For measurements, test 0, near 0, extremes, NaN, and infinity as appropriate for the data domain; avoid a single absolute tolerance across all scales. For money, focus on values where rounding flips the result and multi-line aggregation totals.

## 12. Practice Exercises

**Exercise 1 — Semantic Classification.** Choose a Java type for each field and explain: `zipCode = "01234"`, `activeUserCount` up to 20 million, `totalBytes` up to 12 billion, `stockPrice = "123.4567"`, `sensorVoltage` approximate reading, `createdAt` UTC timestamp, `isEnabled` true/false only. State validation checks and storage format.

**Exercise 2 — Hidden Overflow.** Write the calculation for the average byte count for 3 billion records, given each record is 4 bytes; try `int`, `long`, and `Math.multiplyExact` expressions. Explain how operand types at the multiplication step determine the outcome.

**Exercise 3 — Money and Accounting Rules.** Build a method calculating the total for unit price `"19.95"`, quantity 3, and 8% tax. Test two approaches: rounding tax per line then summing, versus summing the tax base first and rounding once. Write down which rule is required before picking one result.

**Exercise 4 — API Communication.** A Java service returns `long id = 9_007_199_254_740_993L`. Propose a JSON schema preserving the ID when a JavaScript client uses `Number` by default. Explain why the ID should be treated as an identifier and verify round-trip preservation.

**Exercise 5 — Non-Obvious Choice.** A measurement has 6 significant digits, originating from `float32` hardware; a financial metric also has 6 digits but must compound interest over many periods. Choose a type for each field and explain why "having the same digit count" is not enough to use the same type.

## 13. Pre-Production Decision Checklist

- Determine whether the value is a quantity, identifier, or date/time; do not equate digits with numeric types.
- Record min/max range, signedness, intermediate values, growth horizon, and units.
- Choose `int`/`long`/`BigInteger` for integer quantities by range; guard against overflow.
- Choose `double` for real calculations tolerating error; use `float` when explicitly required.
- Choose `BigDecimal` or integers in the smallest unit for exact decimal business logic; specify scale and rounding.
- Clarify `null` and wrappers; never unbox without checking.
- Verify types and semantics are preserved across APIs, JSON, CSV, databases, and conversions.
- Test boundaries, malformed input, unit conversions, overflow, non-finite values, and rounding cases.

**Core rule:** choosing the right data type starts from **domain semantics and invariants**, and only then considers range, representation, precision, operations, and exchange environment. Types represent values; validation and business rules decide whether those values are valid in the system.