# Putting Precision, Scale, and Rounding into the Numeric Data Design Contract in Java

## 1. Why Must This Be a Contract, Not Just a Formatting Choice?

A numeric field such as `amount`, `price`, `rate`, `distance`, or `quantity` is not completely defined merely by saying "type `BigDecimal`." Two systems both using `BigDecimal` can still disagree on the number of allowed digits, maximum thresholds, and rounding behavior. The result: input validation errors, a one-minor-unit discrepancy during reconciliation, unintended changes when writing to the database, or mismatches across endpoints.

When designing numeric data, treat the following three factors as **part of the public contract**:

- **Precision (significant digits):** the total number of significant digits the value is permitted to contain.
- **Scale (decimal places):** the number of digits to the right of the decimal point in a `BigDecimal` representation (scale can be negative).
- **Rounding (rounding policy):** what happens when a calculation or input value cannot be represented at the required precision/scale.

In addition, a real-world contract must state **units, value ranges, null handling, parse/serialize rules, operation ordering, and rounding timing**. You cannot infer all of those merely by looking at a `setScale(2)` call.

Concrete contract example:

> `totalAmount`: money in a defined currency, non-negative, up to 10 integer digits and 2 decimal places; data must be representable exactly to 0.01; do not silently round upon input. When calculating tax, round to 2 decimal places **only at the invoice-line tax calculation step**, using `HALF_EVEN`. When outputting via API, the decimal string must retain exactly 2 decimal places.

This policy can be expressed with `DECIMAL(12,2)` in the database and `BigDecimal` in Java, **yet those two declarations are not enough to define the entire calculation flow**. You must add validation, rounding timing, and data transfer formatting.

## 2. Precision, Scale, and Unscaled Value of `BigDecimal`

A `BigDecimal` object's value is described mathematically by:

```text
value = unscaledValue × 10^(-scale)
```

Examples:

| String Used for Construction | `unscaledValue()` | `scale()` | `precision()` | Numeric Value |
|---|---:|---:|---:|---:|
| `"123.45"` | `12345` | `2` | `5` | 123.45 |
| `"123.450"` | `123450` | `3` | `6` | 123.45 |
| `"0.00"` | `0` | `2` | `1` | 0 |
| `"1E+3"` | `1` | `-3` | `1` | 1000 |
| `"0.001"` | `1` | `3` | `1` | 0.001 |

`precision()` is the number of digits in the *unscaled value* (per `BigDecimal` rules), **not the number of digits after the decimal point**. `scale()` is the decimal shift, **not the number of significant digits**. The precision of zero is 1.

The same numeric value can have different precision and scale:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

`compareTo` compares numeric values. `BigDecimal.equals` additionally requires **the same scale**. Therefore, when a contract requires preserving representation (e.g., input must have exactly 2 decimal digits), `compareTo` alone is insufficient to verify that detail.

**Remember:** `DECIMAL(12,2)` in a database typically expresses up to 12 digits of total precision and scale 2 (corresponding to at most 10 integer digits). It does not mean "12 digits to the left of the decimal point and 2 digits to the right." Storage/rounding behavior when exceeding scale can differ across DBMSs and configurations; the application must verify explicitly rather than leaving it to the driver or database.

## 3. `setScale` and `MathContext`: Two Different Kinds of Limits

### 3.1. `setScale(newScale, mode)`: Adjusting Decimal Places

`setScale` creates a `BigDecimal` with the requested scale. When increasing scale, Java pads zeros without changing numeric value; when decreasing scale, rounding may be needed:

```java
new BigDecimal("12.3").setScale(2); // 12.30
new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP); // 12.35
```

If decreasing scale would discard non-zero digits and no appropriate rounding mode is passed, an exact change cannot be performed. `setScale(2, RoundingMode.UNNECESSARY)` is how you **verify that a value can be represented to 2 decimal places without rounding**.

Important distinctions:

- `new BigDecimal("12.300").setScale(2, UNNECESSARY)` succeeds: result is `12.30`, dropped digits are only zero.
- `new BigDecimal("12.301").setScale(2, UNNECESSARY)` throws `ArithmeticException`: dropping digit 1 would lose value.
- `new BigDecimal("12.3").setScale(2, UNNECESSARY)` succeeds: appends zero to produce `12.30`.

Thus, `UNNECESSARY` checks **exact representability**, not whether the input text literally had **exactly** 2 digits. These two contracts must be kept distinct.

### 3.2. `MathContext(precision, mode)`: Limiting Total Significant Digits

`MathContext` applies a precision limit to the result of a `BigDecimal` operation, together with a rounding mode. Example:

```java
BigDecimal x = new BigDecimal("123.456");

System.out.println(x.setScale(2, RoundingMode.HALF_EVEN)); // 123.46
System.out.println(x.round(new MathContext(4, RoundingMode.HALF_EVEN))); // 123.5
```

`setScale(2)` keeps **2 digits to the right of the decimal point**; `MathContext(4)` keeps **4 significant digits across the entire value**. These are two different goals and cannot be used interchangeably.

`MathContext.UNLIMITED` has precision 0, meaning unlimited precision for the operation to which it is applied; it **does not mean** non-terminating divisions like `1/3` can be represented finitely and exactly. For `BigDecimal.ONE.divide(new BigDecimal("3"))` without rounding/scale, Java throws `ArithmeticException` because the quotient has no finite decimal representation.

### 3.3. Easily Misunderstood Results

| Operation | Result / Behavior |
|---|---|
| `new BigDecimal("123.450").precision()` | `6` |
| `new BigDecimal("123.450").scale()` | `3` |
| `new BigDecimal("2.3").setScale(2)` | `2.30` |
| `new BigDecimal("2.345").setScale(2, HALF_UP)` | `2.35` |
| `new BigDecimal("2.345").setScale(2, HALF_EVEN)` | `2.34` |
| `new BigDecimal("2.355").setScale(2, HALF_EVEN)` | `2.36` |
| `new BigDecimal("123.456").round(MathContext(4, HALF_EVEN))` | `123.5` |

Use `MathContext` only if the contract specifies precision on **operation results**; use `setScale` only when adjusting **decimal places**. Many monetary applications need both a precision/scale limit on **stored values**, yet intermediate operations do not necessarily round to that precision at every step.

## 4. RoundingMode: A Business Rule That Must Be Named

`java.math.RoundingMode` includes several modes. When the exact digits cannot be retained at the desired precision/scale, the rounding mode determines the outcome:

| Mode | Meaning | `2.345` → 2 places | `-2.345` → 2 places |
|---|---|---:|---:|
| `UP` | Away from 0 | 2.35 | -2.35 |
| `DOWN` | Toward 0 | 2.34 | -2.34 |
| `CEILING` | Toward +∞ | 2.35 | -2.34 |
| `FLOOR` | Toward -∞ | 2.34 | -2.35 |
| `HALF_UP` | Nearest; ties away from 0 | 2.35 | -2.35 |
| `HALF_DOWN` | Nearest; ties toward 0 | 2.34 | -2.34 |
| `HALF_EVEN` | Nearest; ties to even last kept digit | 2.34 | -2.34 |
| `UNNECESSARY` | Rounding forbidden | Exception | Exception |

Note that the result columns above assume **exact decimal values constructed from strings** `"2.345"` and `"-2.345"`. For `2.355`, `HALF_EVEN` gives `2.36`, because the retained hundredths digit is 6 (even). `HALF_EVEN` is often called *banker's rounding*, yet whether it is appropriate depends on laws, accounting standards, or product rules.

Writing code **without a rounding mode** usually indicates a missing contract. Specifically, determine:

- When to **reject** inputs with more digits than allowed?
- When is **rounding permitted**?
- At which step does rounding happen: per unit price, per line item, pre/post tax, or only at invoice total?
- Which mode is used, who mandates it, and does it vary by fee type or currency?

**Avoid** using `RoundingMode.DOWN` merely because the word "down" sounds like rounding downward: for negative numbers, `DOWN` rounds **toward 0**, whereas `FLOOR` rounds toward negative infinity.

## 5. Numeric Contracts Must Describe Unit, Range, and Representation

An example specification for a `POST /payments` API:

| Contract Attribute | Specified Example |
|---|---|
| Field name | `amount` |
| Unit | A specified currency, never guessed from locale |
| Valid range | `0.00 ≤ amount ≤ 9,999,999,999.99` |
| Storage limit | `precision ≤ 12`, `scale = 2` after normalization |
| Input rule | Accepted if **exact** to 0.01; `19.900` may normalize to `19.90`, `19.999` is rejected |
| Rounding on input | `UNNECESSARY` (forbids losing significant digits) |
| Rounding on tax | `HALF_EVEN` at the defined per-line tax step |
| Output format | Decimal string `"19.90"`; do not cast to `double` |
| Null / missing data | Rejected if `amount` is required |
| Overflow | Rejected if final total exceeds supported range |

This is **one policy example**, not a universal rule for all currencies. Currencies with zero decimal places or different decimal counts must configure their own scales. Valid ranges, refund handling (negatives), tax arithmetic, and error reporting must also follow real requirements.

**Semantic contracts** and **formatting contracts** can differ:

- A semantic contract "value is an exact multiple of 0.01" can accept `"19.900"` and normalize to `19.90`.
- A textual contract "client **must send exactly 2 digits** after the decimal point" will reject `"19.900"`, even though the numeric value is equivalent.

To enforce a formatting contract, validate the input string against the published format before parsing; you cannot rely solely on `setScale(2, UNNECESSARY)` to verify the digit count in the original text.

## 6. Complete Java 17+ Example: Validate Per Contract Then Normalize

Below is an example policy for **non-negative monetary amounts, up to 12 digits with scale 2**. Inputs may contain trailing zeros, yet significant digits must never be discarded to fit the scale.

**File `MoneyContractDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class MoneyContractDemo {
    private static final int SCALE = 2;
    private static final int PRECISION = 12;

    public static BigDecimal parseAmount(String input) {
        Objects.requireNonNull(input, "amount");

        // Limit input length before parsing to avoid oversized data.
        if (input.length() > 100) {
            throw new IllegalArgumentException("Amount is too long");
        }

        BigDecimal parsed;
        try {
            parsed = new BigDecimal(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid decimal", ex);
        }

        BigDecimal normalized;
        try {
            normalized = parsed.setScale(SCALE, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("Fractional cent", ex);
        }

        if (normalized.signum() < 0 || normalized.precision() > PRECISION) {
            throw new IllegalArgumentException("Amount outside contract");
        }

        return normalized;
    }

    private static void test(String input) {
        try {
            System.out.println(input + " -> " + parseAmount(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(input + " -> REJECTED");
        }
    }

    public static void main(String[] args) {
        test("19.90");
        test("19.900");
        test("0");
        test("19.999");
        test("10000000000.00");
        test("-1.00");
        test("9999999999.99");
    }
}
```

Compile and run:

```bash
javac MoneyContractDemo.java
java MoneyContractDemo
```

Output:

```text
19.90 -> 19.90
19.900 -> 19.90
0 -> 0.00
19.999 -> REJECTED
10000000000.00 -> REJECTED
-1.00 -> REJECTED
9999999999.99 -> 9999999999.99
```

Explanation:

1. **Parse with `new BigDecimal(String)`** to preserve the decimal value sent by the client. Do not parse to `double` first.
2. **`setScale(2, UNNECESSARY)`** checks whether significant digits would be lost. `19.900` normalizes to `19.90` without losing value; `19.999` is rejected.
3. **`signum()`** rejects negative numbers per the chosen range.
4. **`precision() <= 12` after scale normalization**: the result has at most 12 significant digits, matching `DECIMAL(12,2)` for non-negative values here. For `10000000000.00`, precision is 13, so it is rejected.
5. **No auto-rounding on input**: instead of silently turning `19.999` into `20.00`, the system returns a clear error.

In a real application, also enforce HTTP/JSON payload size limits, character count limits, and **exponent/scientific notation** rules per policy. The `BigDecimal(String)` constructor accepts exponents like `"1E+3"`; if the API only allows non-exponential decimal notation, run syntax validation before calling the constructor. `Objects.requireNonNull` in the example throws `NullPointerException` for null input; the API layer can map this to a structured validation error per application conventions.

### If Exactly Two Digits in Input Text Are Mandatory

This is **a different contract** requiring format validation, for example:

```java
// Illustrative snippet inside a method taking String text:
if (!text.matches("(0|[1-9][0-9]*)\\.[0-9]{2}")) {
    throw new IllegalArgumentException("Expected decimal with 2 places");
}
```

This expression rejects minus signs, exponents, unnecessary leading zeros, or strings missing a fractional part; that is a specific format choice. In an actual Java source file, the regex string uses `\\.` to match a literal dot. Rules on `+` signs, whitespace, locale, Unicode digits, and length must also be published explicitly if applicable.

## 7. Rounding Contract in Calculation Steps: Order Can Change Results

A classic design bug is specifying "round to 2 decimal places" without clarifying **whether to round before or after multiplying**.

Suppose an exact internal unit price is `0.335` and quantity is `3`; policy is `HALF_UP` to 2 decimal places:

- **Round unit price first**: `0.335 → 0.34`, then `0.34 × 3 = 1.02`.
- **Multiply first, round line total afterward**: `0.335 × 3 = 1.005 → 1.01`.

Both use the **exact same rounding mode and scale**, yet produce **different results**. A sufficiently clear contract must pick one of the two models.

**File `InvoiceRoundingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class InvoiceRoundingDemo {
    private static final int MONEY_SCALE = 2;
    private static final RoundingMode POLICY = RoundingMode.HALF_UP;

    public static void main(String[] args) {
        BigDecimal rawUnitPrice = new BigDecimal("0.335");
        BigDecimal quantity = new BigDecimal("3");

        BigDecimal unitFirst = rawUnitPrice
                .setScale(MONEY_SCALE, POLICY)
                .multiply(quantity);

        BigDecimal lineFirst = rawUnitPrice
                .multiply(quantity)
                .setScale(MONEY_SCALE, POLICY);

        System.out.println("unitFirst=" + unitFirst);
        System.out.println("lineFirst=" + lineFirst);

        // Another example: calculate tax from original value, then round tax separately.
        BigDecimal net = new BigDecimal("19.99");
        BigDecimal rate = new BigDecimal("0.075");
        BigDecimal tax = net.multiply(rate)
                .setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
        BigDecimal gross = net.add(tax);

        System.out.println("tax=" + tax);
        System.out.println("gross=" + gross);
    }
}
```

```bash
javac InvoiceRoundingDemo.java
java InvoiceRoundingDemo
```

```text
unitFirst=1.02
lineFirst=1.01
tax=1.50
gross=21.49
```

These are **two independent policy examples**, not default tax or legal rules. In real projects, clarify whether input prices are tax-inclusive, whether tax is calculated per line or per invoice, how many tax categories exist, remainder allocation rules, currency, refund handling, and mandatory rounding modes.

**Implementation principle:** retain adequate precision in intermediate steps and round **at the contract-specified point**, rather than calling `setScale(2, ...)` indiscriminately after every addition/multiplication. If precision must be bounded in long calculations, use `MathContext` per algorithm design while staying aware that intermediate rounding can affect the final outcome.

## 8. Division and Ratios: Specify Precision/Scale Right in the Operation

Division is a common source of bugs when using `BigDecimal`:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) throws ArithmeticException because 1/3 is a non-terminating decimal.
BigDecimal rounded = one.divide(three, 2, RoundingMode.HALF_UP);
System.out.println(rounded); // 0.33
```

This is an illustrative snippet inside a method, requiring `BigDecimal` and `RoundingMode` imports.

The right decision depends on the contract:

- "Store ratios to 4 decimal places" → consider `divide(divisor, 4, mode)`.
- "Keep 8 significant digits for scientific calculation" → consider `divide(divisor, new MathContext(8, mode))`.
- "Percentage displayed with 2 decimal places" → define whether the stored value is `0.075` or `7.5%`, and whether rounding occurs at **display** or calculation.
- "Must divide exactly, no rounding" → accept the exception if the quotient has no finite decimal representation, or use a dedicated fraction representation.

**Never** write `divide` without a mode and then act surprised by `ArithmeticException` on `1/3`. Conversely, do not default to `HALF_UP` and scale 2 for every division: the system may need extra intermediate digits to avoid losing critical information.

## 9. Contract Across Layers: Java, JSON, Database, and Reports

### 9.1. Java Domain Model

A sound design names numeric configuration, avoiding the "magic number" 2 scattered everywhere:

```java
public final class MoneyPolicy {
    public static final int SCALE = 2;
    public static final int PRECISION = 12;
    public static final java.math.RoundingMode TAX_ROUNDING =
            java.math.RoundingMode.HALF_EVEN;

    private MoneyPolicy() {
    }
}
```

This is a complete class savable as `MoneyPolicy.java` in Java 17+. In real architectures, place policy in the appropriate domain or configuration module; if multiple currencies have different scales, do not use a global constant `SCALE=2` for every object.

Do not hide rounding inside an undocumented setter: `setAmount(input)` silently rounding can mislead the rest of the program into thinking original data was unmodified. Clearer intent-revealing APIs include `parseExactAmount`, `calculateRoundedTax`, and `serializeAmount`.

### 9.2. JSON APIs and Formatting

JSON supports numbers, yet clients may parse them as `double`, JavaScript `Number`, or pass data through a system that does not preserve trailing decimal digits. Thus, for monetary amounts requiring representation preservation, **decimal strings** are often easier to specify cleanly:

```json
{
  "currency": "USD",
  "amount": "19.90"
}
```

The contract must state which rules the `amount` string follows: decimal point, whether exponents are allowed, digit counts, whether minus/plus signs or whitespace are permitted, and which error codes are returned. Never rely on user locale to parse machine-to-machine strings.

If the API uses JSON numbers, explicitly state that both sides must use exact decimal types and safe round-tripping. JSON numbers **do not guarantee** that every client preserves scale like `"19.90"` or avoids converting to IEEE 754.

### 9.3. Database `DECIMAL(P,S)`

For an example SQL schema:

```sql
amount DECIMAL(12, 2) NOT NULL
```

Typically, `P=12` is total digits and `S=2` is stored decimal digits. A value `9999999999.99` fits this limit; `10000000000.00` exceeds the allowed integer digits.

**Do not rely on the database to decide rounding.** Truncation/rounding rules when inserting values with too many digits can vary by database vendor, version, or SQL mode. To prevent drift across dev/staging/production environments, validate in the domain first and integration-test against the real schema. The database acts as a final safety net rejecting out-of-bounds values, not a substitute for business validation.

If original input digit counts must also be preserved (e.g., "2.00" differs from "2.0" as measurement evidence), design corresponding **representation metadata**; fixed `DECIMAL(P,S)` can normalize scale and does not preserve the exact string a user entered.

### 9.4. Reports and CSV

Use `BigDecimal.toPlainString()` when outputting decimal format without scientific notation, while **setting scale per contract** beforehand. `stripTrailingZeros()` can turn `new BigDecimal("1000.00")` into `1E+3` (negative scale), so it must not be treated as a monetary display formatter.

If reports contain multiple currencies, every value needs a concrete unit. Two values both reading "10.00" in different currencies cannot be added without conversion rules, exchange rate sources, timestamps, and associated precision/rounding.

## 10. How to Test to Guarantee the Numeric Contract?

Write tests from **the contract**, not only after finding bugs:

| Group | Cases to Include | What to Verify |
|---|---|---|
| Valid values | `0`, `19.90`, `9999999999.99` | Exact normalization, within range |
| Trailing zero | `19.900` | Accepted if contract is exactness to cents |
| Invalid by scale | `19.999` | Rejected, not silently `20.00` |
| Invalid by precision | `10000000000.00` | Rejected as out of range |
| Negative values | `-1.00` | Rejected or accepted per separate refund rules |
| Non-numeric | `"abc"`, `""` | Structured parse/validation error |
| Out-of-format syntax | `"1E+3"`, `"+1.00"` | Allowed/rejected per input contract |
| Rounding ties | `2.345`, `2.355`, `-2.345` | Matches `HALF_EVEN`/`HALF_UP` |
| Rounding order | `0.335 × 3` | Same policy gives 1.01 or 1.02 depending on rounding point |
| Non-terminating division | `1 / 3` | Mandatory mode/scale or intentional exception |
| Round-trip | Java → JSON → Java → DB → Java | Value and contract-required representation unchanged |

### Framework-Free Java Test Example

**File `MoneyContractChecks.java`**; uses the compiled `MoneyContractDemo` class from Section 6:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyContractChecks {
    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void rejects(String input) {
        try {
            MoneyContractDemo.parseAmount(input);
            throw new AssertionError("Expected rejection: " + input);
        } catch (IllegalArgumentException expected) {
            // Correct: input rejected per contract.
        }
    }

    public static void main(String[] args) {
        check(MoneyContractDemo.parseAmount("19.900")
                .equals(new BigDecimal("19.90")),
                "trailing zero accepted and normalized");

        check(MoneyContractDemo.parseAmount("0")
                .equals(new BigDecimal("0.00")),
                "zero has required scale");

        rejects("19.999");
        rejects("10000000000.00");
        rejects("-1.00");

        check(new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN)
                .equals(new BigDecimal("2.34")),
                "tie-to-even lower");

        check(new BigDecimal("2.355")
                .setScale(2, RoundingMode.HALF_EVEN)
                .equals(new BigDecimal("2.36")),
                "tie-to-even higher");

        System.out.println("Contract checks passed");
    }
}
```

```bash
javac MoneyContractDemo.java MoneyContractChecks.java
java MoneyContractChecks
```

```text
Contract checks passed
```

Note that `rejects()` catches `IllegalArgumentException` thrown by `parseAmount`, while `AssertionError` is a distinct `Error` subtype and is not swallowed by this catch. If you want to test specific exception subclasses, JUnit 5 offers `assertThrows`; this lesson requires no extra libraries.

When testing normalized money values where **scale is part of the contract**, `BigDecimal.equals` is appropriate because it checks both value and scale. When only numeric value is required (e.g., comparing 2.0 with 2.00), `compareTo == 0` is more appropriate. Choose the assertion matching your intent rather than using one comparison style everywhere.

## 11. Common Design Mistakes

### 11.1. Confusing Precision with Scale

Writing "precision = 2" when you mean "2 digits after the decimal point" leads to wrong calculations. For `123.456`, `MathContext(2)` keeps only 2 significant digits (producing roughly `120`), whereas `setScale(2)` keeps 2 decimal digits (`123.46` with `HALF_EVEN`).

### 11.2. Using `double` as an Intermediate Type for Money

`double` does not represent many decimals like `0.1` accurately. `new BigDecimal(0.1)` constructs a `BigDecimal` holding the exact binary value of `double`, not the desired exact decimal `0.1`. Construct from strings `new BigDecimal("0.1")` or an exact decimal source. `BigDecimal.valueOf(double)` uses `double`'s canonical string representation, yet cannot recover original digits already lost beforehand.

### 11.3. Rounding Silently Upon Parsing

A client sending `19.999` might accidentally get converted to `20.00`; that alters business value. If the contract requires exactness to cents, use `UNNECESSARY` and **reject** instead of silently altering data.

### 11.4. Applying `MathContext` Too Early

Using `MathContext(4)` on every addition/multiplication can lose digits at each step. The final result may differ from keeping wider intermediate precision and rounding once at the contract-defined boundary. Pick a justified policy rather than setting an arbitrary "safety" cap.

### 11.5. Using `stripTrailingZeros()` for Display

`stripTrailingZeros()` can produce negative scales and scientific notation, e.g. `1000.00 → 1E+3`. It is useful when canonicalizing values under an explicit policy, but does not replace `setScale(2)` or proper formatting when outputting `1000.00`.

### 11.6. Failing to Publish Units and Rounding Granularity

"Use 2 decimal places" does not answer which currency, which price unit, or whether rounding happens per line or once per order. Different systems can all be "2 decimal places" yet disagree on results. Include concrete numeric examples in the contract.

### 11.7. Not Bounding Ranges and Oversized Inputs

`BigDecimal` supports arbitrary precision, though not for free. Huge strings, extreme exponents, and scale shifts can make the system consume excessive CPU/memory. Enforce payload size limits, string length limits, exponent limits, and range checks before allocating or normalizing large data.

### 11.8. Leaving Rounding to the Database or Serializer

Rounding at the persistence layer can silently alter values relative to the domain; round-tripping across Java/JSON/DB may fail to preserve expected scale. Design should designate a single **source of truth** for numeric policy and verify it with integration tests.

## 12. Checklist for Writing a Numeric Data Contract

Before finalizing a schema or API, document in writing:

1. **Meaning & unit** of the number: money, percentage, 0..1 ratio, measurement, or count.
2. **Numeric type**: `BigDecimal`, integer minor units, `BigInteger`, or `double` (state rationale).
3. **Valid range**: min, max, whether negatives/0/special values are accepted.
4. **Maximum precision** per layer and handling when exceeded.
5. **Scale** on input, during calculation, in storage, and on output.
6. **RoundingMode** and **rounding point**: per unit price, line item, group, tax, or total.
7. **Invalid data policy**: reject, which error to return, whether intentional rounding is allowed.
8. **Wire format**: decimal string or JSON number, permitted syntax, locale, exponents, trailing zeros.
9. **Persistence**: `DECIMAL(P,S)` verified against actual database limits and rounding behavior.
10. **Testing**: boundary cases, ties, negatives, zero, precision overflow, non-terminating division, round-trips.
11. **Versioning compatibility**: changing precision, scale, or rounding is a contract change that can impact stored data, API clients, and accounting results; plan migrations.
12. **Policy governance**: who approves rounding modes, how policy version history is stored, and how to recompute for reconciliation.

For fields where digit count conveys measurement meaning (e.g., `2.0` vs. `2.00` may indicate different measurement resolutions), store separate metadata for resolution or raw text if business rules require it. `BigDecimal` preserves scale when constructed from strings, yet many operations, serializers, or DB saves can normalize representations.

## 13. Self-Check Exercises with Answers

1. **What are `new BigDecimal("123.450").precision()` and `scale()`?**  
   6 and 3, respectively. These two values do not mean the same thing.

2. **Why does `new BigDecimal("19.900").setScale(2, UNNECESSARY)` not throw an exception?**  
   Because dropping trailing decimal zeros does not change numeric value; the result is `19.90`.

3. **Why does `new BigDecimal("19.999").setScale(2, UNNECESSARY)` throw an exception?**  
   Because the exact value cannot be preserved at scale 2: a non-zero digit 9 would have to be dropped.

4. **What does `2.345` rounded to 2 decimal places give under `HALF_UP` and `HALF_EVEN`?**  
   `2.35` and `2.34`, respectively, with `BigDecimal` input from strings.

5. **What does `0.335 × 3` give if unit price is rounded before vs. after multiplying with `HALF_UP`?**  
   `1.02` and `1.01`, respectively; the rounding point is part of the contract.

6. **Does `BigDecimal.ONE.divide(new BigDecimal("3"))` return an infinitely long decimal?**  
   No; if no rounding/scale/MathContext is given and the quotient does not terminate, Java throws `ArithmeticException`.

7. **Does `DECIMAL(12,2)` allow 12 integer digits?**  
   No under common SQL semantics: total precision is 12 and scale is 2, allowing at most 10 integer digits.

8. **If an API mandates literally `"12.30"` instead of `"12.300"`, is `UNNECESSARY` alone sufficient?**  
   No. `UNNECESSARY` checks whether the value is exactly representable after normalization, not the digit count of the input string; separate text-format validation is required.

9. **Should you use `equals` or `compareTo` for two monetary values normalized to scale 2?**  
   `equals` is appropriate when **scale itself** is part of the contract; `compareTo == 0` is appropriate when only equal numeric value is required.

10. **Why can changing rounding mode be a breaking change even if the API field is still named `amount`?**  
    Because identical inputs can produce different outputs, affecting stored data, reconciliation, invoices, and clients; versioning/migration planning is needed if changed.

## 14. Summary and Official Documentation

**Precision, scale, and rounding are part of the numeric data contract, not three arbitrary technical parameters.** `precision` bounds significant digits; `scale` specifies decimal placement; `RoundingMode` governs what happens when precision reduction is forced. A correct system unifies parsing, calculation, storage, exchange, and testing—complete with clear valid ranges, units, and rounding points.

References:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `MathContext`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html)
- [Java 21 — `RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)