# Avoiding double as an Intermediate Type for Exact Decimal Data in Java

When inputs represent money, unit prices, tax rates, rates defined in decimal digits, or figures requiring exact reconciliation, using `BigDecimal` only **at the final step** is not enough. Even a single **decimal string → `double` → `BigDecimal`** conversion can lose digits and cause the value to differ from the original data. Similarly, a `double` multiplication/addition performed before constructing `BigDecimal` already carries binary errors.

Design principle: **Data requiring decimal exactness must flow through an exact decimal pipeline from ingestion through calculation, validation, storage, and output.** Convert directly from decimal strings, integers, or guaranteed decimal sources into `BigDecimal`; avoid intermediate `double` unless approximation error is permitted by the contract.

This lesson explains why, pinpoints the first point of information loss, compares `BigDecimal` constructors, proposes DTO/API architecture, and illustrates with runnable Java 17+ code.

## 1. `double` Does Not Preserve Every Decimal Number

Java's `double` type is IEEE 754 binary64 floating-point. It has finite precision in base 2. Fractions like 1/2 and 1/4 have finite binary representations, whereas 1/10 does not. Thus the literal `0.1` is rounded to the nearest binary value.

```java
double x = 0.1;
double y = 0.2;
System.out.println(x + y);
```

Stdout:

```text
0.30000000000000004
```

This is not a random bug: the input `double` values and the addition are rounded according to floating-point rules. In simulations, image processing, or measurements where approximation error is acceptable, `double` is entirely useful. However, when the requirement is preserving decimal numbers like `"0.1"` or `"19.99"`, you must separate the **approximate real-number model** from the **exact decimal model**.

`BigDecimal` represents a value as an unscaled integer (`unscaled value`) multiplied by 10 to the negative power of `scale`. When constructed directly from a decimal string, it preserves the numeric value described by that string without passing through binary64 approximation.

Three distinct things are often confused:

- **Decimal source:** e.g., the user enters the string `"0.10000000000000001"`.
- **Parsed `double`:** a binary64 value close to the entered number, carrying none of the source string.
- **`BigDecimal` created after parsing:** the decimal value of that `double`, not necessarily the original decimal.

Once two different source strings become the same `double` value, the information distinguishing them is permanently lost in that branch.

## 2. Counterexample: Passing Through `double` Loses Decimal Values

Wrong when the input decimal value must be preserved exactly:

```java
String input = "19.99";
double intermediate = Double.parseDouble(input);
BigDecimal amount = new BigDecimal(intermediate);
```

`Double.parseDouble` can round a decimal number into the binary64 domain. The `new BigDecimal(double)` constructor creates the **exact decimal of the already-rounded binary64 number**. That differs from the decimal described by the sender.

The clearest example:

```java
System.out.println(new BigDecimal(0.1).toPlainString());
```

Stdout:

```text
0.1000000000000000055511151231257827021181583404541015625
```

This is the exact decimal value of the `double` closest to 0.1, **not** the decimal value 1/10. The constructor is doing its job properly; the mistake is using `double` as an inappropriate intermediate.

Even worse, two different decimal strings can round to the exact same `double`:

```java
String source = "0.10000000000000001";
BigDecimal correct = new BigDecimal(source);
BigDecimal wrong = BigDecimal.valueOf(Double.parseDouble(source));

System.out.println(correct.toPlainString());
System.out.println(wrong.toPlainString());
```

Stdout:

```text
0.10000000000000001
0.1
```

Although `wrong` looks neat and clean, it **no longer equals** the original decimal number. No algorithm can recover the source string from `double` alone in all cases, because many decimal strings map to the same floating-point value.

If you already receive an input string, construct directly:

```java
BigDecimal correct = new BigDecimal(source);
```

Do not parse a decimal string into `double` just to "check if it is a number": if validation is needed, parse with `BigDecimal` and catch `NumberFormatException`, or apply the appropriate format/range rules.

## 3. Distinguishing `new BigDecimal(double)` and `BigDecimal.valueOf(double)`

| Construction | Source | What Is Preserved | When to Use? |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Decimal string | Exact decimal value per string, scale matching representation | Decimal data requiring exactness |
| `new BigDecimal(0.1)` | `double` | Exact stored binary64 value | Inspecting binary64 representation, not recovering source |
| `BigDecimal.valueOf(0.1)` | `double` | Decimal per `Double.toString(double)` | Only a `double` exists and a short decimal representation in that sense is needed |
| `BigDecimal.valueOf(100L)` | `long` | Exact integer 100 | Source integer |
| `new BigDecimal(BigInteger)` | Large integer | Exact large integer | When `long` is insufficient |

`BigDecimal.valueOf(double)` is usually a better choice than the `double` constructor when the source **genuinely only has a `double`** and you want a decimal based on `Double.toString`'s canonical round-trip string. For example:

```java
System.out.println(BigDecimal.valueOf(0.1).toPlainString()); // 0.1
```

Nevertheless, looking like a decimal literal does not prove it matches **the original decimal data**. For example, `"0.10000000000000001"` becomes `"0.1"` after passing through `Double.parseDouble` and `BigDecimal.valueOf`.

`valueOf` also cannot fix calculations already performed in `double`:

```java
double calculated = 0.1 + 0.2;
BigDecimal late = BigDecimal.valueOf(calculated);
System.out.println(late.toPlainString());
```

Stdout:

```text
0.30000000000000004
```

Convert **the operands** to `BigDecimal` from a decimal source **before adding**:

```java
BigDecimal exact = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
System.out.println(exact.toPlainString()); // 0.3
```

`BigDecimal.valueOf(long)` is a **different** overload: it accepts an integer intact without going through binary64, making it suitable for money represented in integer minor units.

## 4. Building an Exact Decimal-Preserving Pipeline

For a monetary/tax field to keep exact decimals, you must control **every type-conversion boundary**, not only the domain-layer class.

A path prone to data loss:

```text
JSON/CSV input containing decimal number
  → parser converts to double
  → DTO or entity holds double
  → add/multiply/divide using double
  → BigDecimal.valueOf(double)
  → database DECIMAL
```

The database may store an exact `BigDecimal`, yet it is **the value of an approximation that already occurred**, not the source decimal data.

The right path when the contract requires exact decimals:

```text
JSON decimal token or raw decimal string
  → parse directly to BigDecimal
  → validate range, unit, and resolution
  → calculate using BigDecimal
  → round at the defined boundary
  → store SQL DECIMAL/NUMERIC or integer minor units via exact conversion
  → serialize as decimal per schema
```

You can use a value object to guard invariants, such as `Money` holding both a currency code and `BigDecimal`, or store integer minor units (`long`) when business rules allow and the representation range is proven wide enough. In either approach, **there is no need to use `double` as a bridge**.

### JSON and Frontend

JSON supports decimal number notation, yet how the parser and DTO map it determines whether the value passes through floating-point. If deserialization parses a token into `double` before building `BigDecimal`, precision loss is risked. Use a `BigDecimal` field type and configure direct decimal parsing in the library.

JavaScript clients typically use `Number` based on binary64. If a user-entered `"19.99"` has already been turned into a `Number` and used in calculations, the backend cannot recover full decimal semantics merely by receiving `BigDecimal`. When exact decimal strings must be preserved, the frontend can transmit decimal strings in a clearly specified schema field or use an appropriate exact decimal library. **Never change a JSON number to a string unilaterally without aligning the API contract.**

Large integers carry their own risk: JavaScript `Number` cannot represent every integer above `2^53 - 1` exactly. If an API sends minor-unit monetary amounts as `long` to a JavaScript client, specify the wire format and write round-trip tests, rather than testing only the backend.

### JDBC, ORM, and Databases

A `DECIMAL(p,s)` or `NUMERIC(p,s)` column suits exact decimals within configured bounds. When reading, prefer the corresponding decimal mapping/getter such as `BigDecimal` instead of calling `getDouble()` and converting afterward. If a column originally stored floating-point values, reading it as `BigDecimal` later cannot restore decimal digits from before the data was approximated.

SQL type, precision, scale, unit, and valid numeric range must match the schema/API. A column supporting 12 digits does not mean the business allows every 12-digit value.

### CSV, Config, and Spreadsheets

CSV stores field text; if decimal values are stored verbatim, they can be parsed directly with `BigDecimal(String)`. Avoid auto-guessing types as `double` in import readers. With spreadsheets, a displayed value `19.99` does not prove the underlying cell wasn't computed via floating-point; if the source lost precision earlier, parsing the display string does not guarantee the original data was recovered.

All decimal ingestion points must agree on **decimal separator**, grouping separators, locale, currency symbols, and whether exponent notation is accepted. The `BigDecimal(String)` constructor does not automatically interpret `"1,25"` as 1.25.

## 5. Exact Decimal Calculations from the First Operand

Suppose unit price is `"19.90"`, quantity is 3, and tax rate is `"0.075"` (7.5%). Do not write:

```java
double unitPrice = 19.90;
double taxRate = 0.075;
double subtotal = unitPrice * 3;
BigDecimal total = BigDecimal.valueOf(subtotal * (1 + taxRate));
```

Even though the final result is `BigDecimal`, the calculation already ran in `double`. Intermediate values and rounding timing are not governed by the decimal contract.

Correct example:

```java
BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);

BigDecimal subtotal = unitPrice.multiply(quantity);
BigDecimal tax = subtotal.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal total = subtotal.add(tax);

System.out.println(subtotal.toPlainString()); // 59.70
System.out.println(tax.toPlainString());      // 4.48
System.out.println(total.toPlainString());    // 64.18
```

This is an illustrative snippet requiring `java.math.BigDecimal` and `java.math.RoundingMode` imports, placed inside a method. Multiplying 59.70 × 0.075 = 4.47750; tax rounds to 4.48 under the **illustrative policy** `HALF_UP`.

No single rounding rule fits every domain. Some products round each invoice line, while others round after summing all lines. Both policies can use `BigDecimal` yet produce different results due to rounding timing.

### Division and `MathContext`

`BigDecimal.add`, `subtract`, and `multiply` without a `MathContext` execute with exact decimal precision. Division can sometimes yield non-terminating decimals, such as 1/3:

```java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333
```

Calling `BigDecimal.ONE.divide(new BigDecimal("3"))` without specifying rounding causes Java to throw `ArithmeticException` because the decimal result does not terminate. `MathContext` can also manage precision and rounding per contract, yet **cannot recover source digits already lost in an earlier `double`**.

The business specification should state resolution, precision, `RoundingMode`, and application timing.

## 6. Scale, Representation, and Resolution Are Not the Same Concept

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(b.scale());           // 2
```

Both have the same numeric value yet different `scale`. `compareTo` compares only numeric value; `equals` also checks scale. If a field has a contract to preserve the number of decimal digits a user entered, routing the value through `double` destroys that representation metadata: from `"1.000"` via `double`, you can no longer tell how many zeros the original source had.

Distinguish:

1. **Exact decimal value:** `"1.0"` and `"1.00"` are arithmetically equal.
2. **Business resolution/scale:** e.g., accepting values representable exactly to 0.01.
3. **Exact text format:** whether the literal string `"1.00"` must be preserved.

To verify an amount is losslessly representable at scale 2:

```java
BigDecimal accepted = new BigDecimal("1.230")
        .setScale(2, RoundingMode.UNNECESSARY);
// accepted.toPlainString() is "1.23".
```

The value `"1.234"` cannot shrink to scale 2 without changing its numeric value, so `RoundingMode.UNNECESSARY` throws `ArithmeticException`. If the contract **allows** rounding, specify the exact mode rather than silently dropping digits.

`BigDecimal` can hold a negative scale; thus "scale" is not simply counting characters after a dot in an arbitrary string. When the contract requires controlling input representation, validate both string syntax and numeric value as needed.

## 7. When Values Can Be Stored as Minor-Unit Integers

One way to avoid floating-point for fixed-resolution decimals is converting **directly from the source decimal** to an integer count of minor units. For example, assuming one major unit equals 100 minor units:

```java
BigDecimal amount = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);

long minorUnits = amount.movePointRight(2).longValueExact();
System.out.println(minorUnits); // 1230
```

`movePointRight(2)` multiplies by 100 decimally; `longValueExact()` rejects if a fractional remainder exists or if it exceeds `long` bounds. This differs completely from:

```java
double amount = Double.parseDouble("12.30");
long minorUnits = (long) (amount * 100); // Should not be used when exactness is needed.
```

Floating-point multiplication can produce a value slightly lower or higher than the expected integer; casting `(long)` silently truncates fractions.

The factor 100 **is not a universal rule for all currencies**. In multi-currency software, attach the currency code and its corresponding unit scale; do not add minor-unit integers of different currencies without an explicit policy-backed conversion step.

Before storing into `long`, also check business min/max bounds: `longValueExact()` only guarantees **exact integer conversion**, without knowing whether negative prices are allowed or whether an amount exceeds transaction limits.

## 8. Complete Runnable Java 17+ Program

The following program illustrates decimal loss when passing through `double`, exact calculation when constructing operands properly, and rejecting values with wrong resolution. Example policy: non-negative unit price, maximum 1,000,000 major units, representable in 0.01 steps; tax rate from 0 to 1, with tax rounded `HALF_UP` to two decimal places.

Save the file **`ExactDecimalPipelineDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class ExactDecimalPipelineDemo {
    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000.00");

    private ExactDecimalPipelineDemo() {}

    static BigDecimal parseAmount(String text) {
        Objects.requireNonNull(text, "amount text");
        BigDecimal amount = new BigDecimal(text)
                .setScale(2, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0 || amount.compareTo(MAX_AMOUNT) > 0) {
            throw new IllegalArgumentException("amount out of range");
        }
        return amount;
    }

    static BigDecimal parseRate(String text) {
        Objects.requireNonNull(text, "rate text");
        BigDecimal rate = new BigDecimal(text);
        if (rate.signum() < 0 || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("rate out of range");
        }
        return rate;
    }

    public static void main(String[] args) {
        String raw = "0.10000000000000001";
        BigDecimal original = new BigDecimal(raw);
        BigDecimal afterDouble =
                BigDecimal.valueOf(Double.parseDouble(raw));

        System.out.println("raw decimal = " + original.toPlainString());
        System.out.println("after double = " + afterDouble.toPlainString());
        System.out.println("value changed = "
                + (original.compareTo(afterDouble) != 0));

        System.out.println("double constructor = "
                + new BigDecimal(0.1).toPlainString());
        System.out.println("valueOf double = "
                + BigDecimal.valueOf(0.1).toPlainString());

        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("binary sum converted = "
                + BigDecimal.valueOf(binarySum).toPlainString());
        System.out.println("decimal sum = "
                + decimalSum.toPlainString());

        BigDecimal unitPrice = parseAmount("19.90");
        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(3L));
        BigDecimal rate = parseRate("0.075");
        BigDecimal tax = subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        System.out.println("subtotal = " + subtotal.toPlainString());
        System.out.println("tax = " + tax.toPlainString());
        System.out.println("total = " + total.toPlainString());
        System.out.println("minor units = "
                + total.movePointRight(2).longValueExact());

        System.out.println("input scale = "
                + new BigDecimal("1.2300").scale());
        System.out.println("normalized scale = "
                + parseAmount("1.2300").scale());

        try {
            parseAmount("19.999");
            System.out.println("extra precision = accepted");
        } catch (ArithmeticException ex) {
            System.out.println("extra precision = rejected");
        }

        try {
            parseAmount("-0.01");
            System.out.println("negative amount = accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative amount = rejected");
        }

        BigDecimal largeExact =
                new BigDecimal("9007199254740993");
        BigDecimal largeViaDouble = BigDecimal.valueOf(
                Double.parseDouble("9007199254740993"));
        System.out.println("large decimal changed = "
                + (largeExact.compareTo(largeViaDouble) != 0));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ExactDecimalPipelineDemo.java
java ExactDecimalPipelineDemo
```

Exact stdout:

```text
raw decimal = 0.10000000000000001
after double = 0.1
value changed = true
double constructor = 0.1000000000000000055511151231257827021181583404541015625
valueOf double = 0.1
binary sum converted = 0.30000000000000004
decimal sum = 0.3
subtotal = 59.70
tax = 4.48
total = 64.18
minor units = 6418
input scale = 4
normalized scale = 2
extra precision = rejected
negative amount = rejected
large decimal changed = true
```

Output explanation:

- Source decimal `"0.10000000000000001"` remains intact when parsed directly, yet turns into `0.1` after `Double.parseDouble` followed by `BigDecimal.valueOf`.
- `new BigDecimal(0.1)` displays the full decimal expansion of binary64; `valueOf(0.1)` shortens to `0.1`, yet is not a tool to recover source strings.
- Converting `double` after adding `0.1 + 0.2` still yields `0.30000000000000004`; adding two `BigDecimal` instances constructed directly from strings yields `0.3`.
- Price 19.90 times 3 equals 59.70; 7.5% tax is 4.47750, rounded per the example policy to 4.48; total is 64.18 and converts exactly to 6,418 minor units.
- String `"1.2300"` has scale 4; it can be normalized to scale 2 without changing its numeric value. String `"19.999"` cannot normalize cleanly to two digits and is rejected.
- `9007199254740993` exceeds the contiguous range of integers exactly representable in binary64, so if parsed via `double`, `BigDecimal` afterward cannot retrieve the exact value.

## 9. Testing Data from Source to Destination

When writing tests for exact decimal requirements, **expected values must derive from the original decimal string** or an independent decimal calculation, never from the very `double` expression under test.

| Input / Operation | Expected |
| --- | --- |
| `"0.1"` → `new BigDecimal(text)` | Exact 0.1 |
| `"0.1"` → `new BigDecimal(Double.parseDouble(text))` | Binary64's decimal near 0.1, not equal to original |
| `"0.10000000000000001"` via `double` | Can become decimal `0.1`; differs from source |
| `BigDecimal("0.1") + BigDecimal("0.2")` | `0.3` |
| `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |
| `"1.2300"` | Preserve original scale or normalize explicitly per contract |
| `"19.999"` with step 0.01 | Reject, or round per defined policy |
| `"-0.01"` in non-negative field | Reject per business range |
| `"9007199254740993"` via `double` | Loses ability to hold exact integer |
| `DECIMAL` data read via `getDouble()` | May round original decimal |
| Price from JSON via JavaScript `Number` | Check conversion risk before sending |
| Decimal value converted to minor units | Use decimal arithmetic and exact conversion, never `double` |

Integration tests should cover the entire **request → DTO → domain → calculation → database → response** path. When discrepancies appear, locate the earliest step using `double`, `float`, `doubleValue()`, `Double.parseDouble()`, `getDouble()`, floating columns, binary math, or a parser defaulting to `Number`.

For historical data already corrupted by floating-point, `setScale(2, ...)` can make results look plausible yet **does not prove the original source number**. If historical data must be repaired, reconcile against authoritative sources or separate business rules; never assume every post-rounding amount equals what the user originally submitted.

### Quick Diagnosis

Before fixing, ask:

1. Does decimal data start from a **string**, `BigDecimal`, integer, or `double`?
2. Is there a string → `Double.parseDouble` → `BigDecimal` anywhere?
3. Do additions, multiplications, or divisions use `double` before saving results?
4. Is `BigDecimal.valueOf(double)` merely converting an existing `double`, or being mistaken for a way to recover decimals?
5. Are unit, range, scale, rounding mode, and rounding timing documented in the contract?
6. Do JSON/JavaScript or SQL/ORM change types to an intermediate floating-point type?
7. Are tricky numbers tested, such as 0.1; 0.1 + 0.2; many-digit decimals; prices with trailing zeros; integers above \(2^{53}\)?

## 10. Common Mistakes and How to Avoid Them

1. **"`double` is only for parsing, then using `BigDecimal` afterward is enough."** False: parsing itself can already drop digits.
2. **"`new BigDecimal(0.1)` means decimal 0.1."** It represents the decimal value of a binary64 number approximating 0.1.
3. **"`BigDecimal.valueOf(d)` always recovers the original decimal."** It uses `Double.toString(d)` and cannot undo rounding from multiple source strings.
4. **"Add with `double` first, convert to `BigDecimal` later for accuracy."** The result `0.30000000000000004` proves the opposite.
5. **"A `double` DTO field doesn't matter because the domain uses `BigDecimal`."** Information may already be lost right at the DTO.
6. **"Calling `setScale(2)` fixes every decimal bug."** Rounding/normalization can alter numbers or mask errors, not recover the source.
7. **"`BigDecimal.equals` and `compareTo == 0` are the same."** `equals` checks scale as well.
8. **"Using `(long)(doubleAmount*100)` is a safe way to get cents."** It can lose precision and cast away fractions silently.
9. **"JSON numbers always preserve all decimal digits."** That depends on each client/server parser and data type.
10. **"`double` must never be used."** If a business domain accepts approximate measurements, `double` can be the right choice. The problem is using it **in a pipeline requiring exact decimals**.

## 11. Pre-Release Checklist

- Determine whether the source requires **exact decimal values** or only approximate measurements.
- Ingest/parse directly into `BigDecimal` from strings or exact decimal types, without passing through `double`.
- Audit all DTOs, serializers, mappers, ORMs, JDBC, CSVs, and clients to eliminate unintended floating-point conversions.
- Perform addition, subtraction, multiplication, and division using `BigDecimal` when the contract requires exact decimals.
- Explicitly specify scale/resolution, min/max range, unit, rounding mode, and rounding **timing**.
- If converting to integer minor units, use `movePointRight` and `longValueExact()`/`intValueExact()`.
- Test decimals not representable in binary64, large integers, many decimal digits, out-of-range inputs, and round-trips through clients/databases.
- When an error is found, locate **the earliest step** that loses information rather than trying to patch it at the end with an arbitrary cast or rounding.

**Conclusion:** Choosing `BigDecimal` only delivers its full value when **data does not pass through `double` on the way to it**. Keep decimals from the source, compute in decimals, check ranges/resolutions explicitly, and round only when the contract calls for it.

### Official Java Documentation

- [`BigDecimal`: constructors, `valueOf`, operations, and scale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Double`: `parseDouble`, `toString`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [JLS §4.2.3: Floating-point types and values](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3)